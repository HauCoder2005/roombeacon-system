import logging
import unittest
from unittest.mock import MagicMock, patch

from roombeacon_crawler.application.persistence.persist_observations import (
    BronzeImportResult,
    PersistBronzeObservationsUseCase,
)
from roombeacon_crawler.domain.errors.domain_error import PersistenceError
from roombeacon_crawler.domain.models.bronze_observation import BronzeObservation
from roombeacon_crawler.security.url_safety import (
    URLSafetyError,
    validate_public_http_url,
)


PUBLIC_IP = "93.184.216.34"


class TestDeadlockRetry(unittest.TestCase):
    def setUp(self):
        self.platform = MagicMock()
        self.platform.get_or_create_platform.return_value = 1
        self.posts = MagicMock()
        self.posts.upsert_post.return_value = (2, True)
        self.observations = MagicMock()
        self.observations.insert_observation.return_value = (3, True)
        self.children = MagicMock()
        self.tx = MagicMock()
        self.use_case = PersistBronzeObservationsUseCase(
            self.platform, self.posts, self.observations, self.children, self.tx
        )
        self.observation = BronzeObservation(
            source="test", listing_id="1", run_id="run-1", url="https://example.com/1"
        )

    @patch("time.sleep", return_value=None)
    def test_first_deadlock_then_success_returns_real_result(self, _sleep):
        self.platform.get_or_create_platform.side_effect = [
            Exception("deadlock 1213"),
            1,
        ]
        result = self.use_case.execute([self.observation])
        self.assertIsInstance(result, BronzeImportResult)
        self.assertEqual(result.observations_inserted, 1)
        self.assertEqual(self.tx.begin.call_count, 2)
        self.assertEqual(self.tx.rollback.call_count, 1)
        self.tx.commit.assert_called_once()

    @patch("time.sleep", return_value=None)
    def test_deadlock_retry_limit_surfaces_safe_persistence_error(self, _sleep):
        self.platform.get_or_create_platform.side_effect = Exception("1213 deadlock")
        with self.assertRaisesRegex(PersistenceError, "transaction failed"):
            self.use_case.execute([self.observation])
        self.assertEqual(self.tx.begin.call_count, 3)
        self.assertEqual(self.tx.rollback.call_count, 3)
        self.tx.commit.assert_not_called()

    @patch("time.sleep", return_value=None)
    def test_non_deadlock_is_not_retried(self, _sleep):
        self.platform.get_or_create_platform.side_effect = Exception("synthetic database failure")
        with self.assertRaises(PersistenceError):
            self.use_case.execute([self.observation])
        self.tx.begin.assert_called_once()
        self.tx.rollback.assert_called_once()
        _sleep.assert_not_called()

    def test_first_attempt_success_is_unchanged(self):
        result = self.use_case.execute([self.observation])
        self.assertIsInstance(result, BronzeImportResult)
        self.tx.begin.assert_called_once()
        self.tx.commit.assert_called_once()
        self.tx.rollback.assert_not_called()

    def test_database_exception_details_are_not_logged_or_propagated(self):
        marker = "SENSITIVE_SQL_PARAMETER_MARKER"
        self.platform.get_or_create_platform.side_effect = Exception(
            f"DataError [parameters: seller_phone={marker}]"
        )
        with self.assertLogs(
            "roombeacon_crawler.application.persistence.persist_observations",
            level=logging.ERROR,
        ) as captured:
            with self.assertRaises(PersistenceError) as raised:
                self.use_case.execute([self.observation])

        self.assertNotIn(marker, "\n".join(captured.output))
        self.assertNotIn(marker, str(raised.exception))
        self.assertNotIn("parameters", "\n".join(captured.output).lower())


class TestOutboundURLSafety(unittest.TestCase):
    @staticmethod
    def public_resolver(_host, _port):
        return {PUBLIC_IP}

    def test_public_https_is_allowed(self):
        validate_public_http_url(
            "https://public.example/image.jpg", resolver=self.public_resolver
        )

    def test_unsafe_destinations_are_blocked(self):
        blocked = [
            "http://127.0.0.1/x",
            "http://localhost/x",
            "http://10.0.0.1/x",
            "http://172.16.0.1/x",
            "http://192.168.1.1/x",
            "http://169.254.169.254/x",
            "http://[::1]/x",
            "http://[fc00::1]/x",
            "http://[fe80::1]/x",
            "file:///etc/passwd",
            "data:image/png;base64,AAAA",
        ]
        for url in blocked:
            with self.subTest(url=url), self.assertRaises(URLSafetyError):
                validate_public_http_url(url, resolver=self.public_resolver)

    def test_hostname_resolving_private_is_blocked(self):
        with self.assertRaises(URLSafetyError):
            validate_public_http_url(
                "https://public-looking.example/image.jpg",
                resolver=lambda _host, _port: {"10.0.0.8"},
            )

    def test_any_private_address_in_dns_set_blocks(self):
        with self.assertRaises(URLSafetyError):
            validate_public_http_url(
                "https://mixed.example/image.jpg",
                resolver=lambda _host, _port: {PUBLIC_IP, "192.168.1.2"},
            )

    def test_dns_failure_is_fail_closed(self):
        def failing_resolver(_host, _port):
            raise OSError("synthetic DNS failure")

        with self.assertRaises(URLSafetyError):
            validate_public_http_url(
                "https://unresolved.example/image.jpg", resolver=failing_resolver
            )


class TestAssetRedirectAndSizeHardening(unittest.TestCase):
    def setUp(self):
        from roombeacon_crawler.application.assets.asset_reconciler import (
            AssetReconcilerService,
        )

        self.service = AssetReconcilerService.__new__(AssetReconcilerService)
        self.service.timeout = 1
        self.service.resolver = lambda _host, _port: {PUBLIC_IP}

    @patch("requests.get")
    def test_redirect_to_private_is_blocked_before_second_request(self, get):
        redirect = MagicMock(status_code=302, headers={"Location": "http://127.0.0.1/x"})
        get.return_value = redirect
        with self.assertRaises(URLSafetyError):
            self.service._request_public_asset(
                "https://public.example/image.jpg", headers={}
            )
        get.assert_called_once()
        redirect.close.assert_called_once()

    @patch("requests.get")
    def test_redirect_limit_is_bounded(self, get):
        get.return_value = MagicMock(status_code=302, headers={"Location": "/again"})
        with self.assertRaises(URLSafetyError):
            self.service._request_public_asset(
                "https://public.example/image.jpg", headers={}
            )
        self.assertEqual(get.call_count, 6)

    def test_streaming_limit_rejects_oversized_body(self):
        from roombeacon_crawler.application.assets.asset_reconciler import (
            AssetReconcilerService,
            MAX_ASSET_BYTES,
        )

        response = MagicMock(headers={})
        response.iter_content.return_value = [b"x" * MAX_ASSET_BYTES, b"y"]
        with self.assertRaises(ValueError):
            AssetReconcilerService._read_bounded_content(response)


class TestDuckDBCredentialSafety(unittest.TestCase):
    def test_attach_failure_does_not_leak_synthetic_secret(self):
        import analytics.duckdb.connection as module

        marker = "SUPER_SECRET_TEST_MARKER"
        fake_conn = MagicMock()

        def execute(sql):
            if str(sql).startswith("ATTACH"):
                raise RuntimeError(f"failed SQL: {sql}")
            return MagicMock()

        fake_conn.execute.side_effect = execute
        mysql_cfg = MagicMock(
            host="db.example", port=3306, user="reader", password=marker, database="bronze"
        )
        fake_env = MagicMock(mysql_bronze=mysql_cfg)

        module.DuckDBConnectionFactory._connection = None
        with (
            patch.object(module, "env", fake_env),
            patch.object(module.duckdb, "connect", return_value=fake_conn),
            self.assertLogs(module.logger, level=logging.WARNING) as captured,
        ):
            conn = module.DuckDBConnectionFactory.get_connection(
                db_path=":memory:", create_views=False
            )

        self.assertIs(conn, fake_conn)
        rendered = "\n".join(captured.output)
        self.assertNotIn(marker, rendered)
        self.assertNotIn("password=", rendered)
        module.DuckDBConnectionFactory._connection = None


if __name__ == "__main__":
    unittest.main()
