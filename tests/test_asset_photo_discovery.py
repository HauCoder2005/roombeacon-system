"""Asset discovery: newest listings first, resumable backfill, own photos only, retry cooldown."""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from roombeacon_crawler.application.assets.asset_reconciler import AssetReconcilerService
from roombeacon_crawler.application.orchestration import assets as asset_orchestration
from roombeacon_crawler.models.asset_item import AssetBatchResult, AssetItem, AssetStatus
from roombeacon_crawler.repositories import local_asset_state_repository
from roombeacon_crawler.repositories.local_asset_state_repository import LocalAssetStateRepository


def _photo(post_id: int, n: int = 1) -> str:
    return f"https://cloud.mogi.vn/images/2026/10/0{n}/1/{post_id}-{n}.jpg"


def _rows(post_id: int, observed: str, urls: list[str]) -> list[dict]:
    base = {"rental_post_id": post_id, "platform_post_id": f"p{post_id}", "last_observed_at": observed, "source": "mogi"}
    if not urls:
        return [dict(base, image_id=None, image_url=None, position=None)]
    return [dict(base, image_id=post_id * 100 + i, image_url=url, position=i) for i, url in enumerate(urls, start=1)]


def _connection(pages: list[list[dict]]):
    cursor = MagicMock()
    cursor.fetchall.side_effect = pages
    cursor.__enter__.return_value = cursor
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value = cursor
    return connection, cursor


class AssetPhotoDiscoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = LocalAssetStateRepository(base_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _service(self, **kwargs):
        return AssetReconcilerService(state_repo=self.state, bucket_name="b", resolver=lambda *_: {"93.184.216.34"}, **kwargs)

    def _discover(self, service, pages, max_per_source=500, s3=None):
        connection, cursor = _connection(pages)
        with patch.object(service, "get_mysql_connection", return_value=connection):
            found = service.discover_actionable_candidates_per_source(["mogi"], max_per_source=max_per_source, s3=s3)
        return found["mogi"], cursor

    def test_only_the_listings_own_photos_become_candidates(self):
        rows = _rows(9, "2026-10-10 08:00:00", [
            "https://mogi.vn/content/Images/logo.svg",
            _photo(9, 1),
            "https://images.dmca.com/Badges/dmca_protected_sml_120m.png",
            _photo(9, 2),
        ])
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        items, _ = self._discover(service, [rows])

        self.assertEqual([(i.position, i.image_url) for i in items], [(2, _photo(9, 1)), (4, _photo(9, 2))])
        self.assertTrue(all(i.object_key.startswith("mogi/p9/img_") for i in items))

    def test_newest_listings_are_scheduled_first(self):
        page = _rows(30, "2026-10-10 09:00:00", [_photo(30)]) + _rows(20, "2026-10-09 09:00:00", [_photo(20)])
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        items, cursor = self._discover(service, [page])

        self.assertEqual([i.platform_post_id for i in items], ["p30", "p20"])
        sql = cursor.execute.call_args_list[0].args[0]
        self.assertIn("ORDER BY rp.last_observed_at DESC, rp.id DESC", sql)

    def test_duplicate_rows_of_one_image_yield_one_candidate(self):
        rows = _rows(7, "2026-10-10 08:00:00", [_photo(7), _photo(7)])
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        items, _ = self._discover(service, [rows])

        self.assertEqual(len(items), 1)

    def test_backfill_resumes_from_the_saved_cursor_and_wraps_at_the_end(self):
        service = self._service(fresh_posts=1, backfill_posts=1, post_page_size=1)
        fresh = _rows(50, "2026-10-10 09:00:00", [_photo(50)])
        older = _rows(40, "2026-10-01 09:00:00", [_photo(40)])

        items, cursor = self._discover(service, [fresh, older])

        self.assertEqual([i.platform_post_id for i in items], ["p50", "p40"])
        backfill_args = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(backfill_args[2:5], ("2026-10-10 09:00:00", "2026-10-10 09:00:00", 50))
        self.assertEqual(self.state.get_cursor("mogi"), ("2026-10-01 09:00:00", 40))

        # Next run: backfill continues below the saved cursor, then reaches the end.
        items, cursor = self._discover(service, [fresh, []])
        self.assertEqual(cursor.execute.call_args_list[1].args[1][2:5], ("2026-10-01 09:00:00", "2026-10-01 09:00:00", 40))
        self.assertIsNone(self.state.get_cursor("mogi"))

    def test_posts_without_photos_still_advance_the_cursor(self):
        service = self._service(fresh_posts=1, backfill_posts=2, post_page_size=2)
        fresh = _rows(50, "2026-10-10 09:00:00", [])
        older = _rows(40, "2026-10-02 09:00:00", ["https://mogi.vn/content/images/logo.svg"]) + _rows(
            30, "2026-10-01 09:00:00", [_photo(30)]
        )

        items, _ = self._discover(service, [fresh, older])

        self.assertEqual([i.platform_post_id for i in items], ["p30"])
        self.assertEqual(self.state.get_cursor("mogi"), ("2026-10-01 09:00:00", 30))

    def test_stored_asset_is_skipped_after_head_check(self):
        url = _photo(8)
        self.state.save_asset(AssetItem(
            asset_id=AssetItem.generate_asset_id("mogi", "p8", url), source="mogi", platform_post_id="p8",
            rental_post_id=8, image_url=url, position=1,
            object_key=AssetItem.generate_object_key("mogi", "p8", 1, url), status=AssetStatus.SUCCESS,
        ))
        s3 = MagicMock()
        s3.head_object.return_value = {"ContentLength": 10}
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        items, _ = self._discover(service, [_rows(8, "2026-10-10 08:00:00", [url])], s3=s3)

        self.assertEqual(items, [])
        self.assertEqual(service._last_already_stored_by_source["mogi"], 1)

    def test_exhausted_retryable_failure_is_retried_after_cooldown(self):
        url = _photo(5)
        asset_id = AssetItem.generate_asset_id("mogi", "p5", url)
        old_attempt = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        recent_attempt = datetime.now(timezone.utc).isoformat()
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        for last_attempt, expected in ((recent_attempt, 0), (old_attempt, 1)):
            self.state.save_asset(AssetItem(
                asset_id=asset_id, source="mogi", platform_post_id="p5", rental_post_id=5, image_url=url,
                position=1, object_key="mogi/p5/img_1_x.jpg", status=AssetStatus.RETRYABLE_FAILURE,
                attempt_count=3, last_attempt_at=last_attempt,
            ))
            items, _ = self._discover(service, [_rows(5, "2026-10-10 08:00:00", [url])])
            self.assertEqual(len(items), expected, last_attempt)
        self.assertEqual(items[0].attempt_count, 0)

    def test_terminal_failure_is_not_retried(self):
        url = _photo(6)
        self.state.save_asset(AssetItem(
            asset_id=AssetItem.generate_asset_id("mogi", "p6", url), source="mogi", platform_post_id="p6",
            rental_post_id=6, image_url=url, position=1, object_key="mogi/p6/img_1_x.jpg",
            status=AssetStatus.TERMINAL_FAILURE, last_attempt_at="2020-01-01T00:00:00+00:00",
        ))
        service = self._service(fresh_posts=10, backfill_posts=0, post_page_size=10)

        items, _ = self._discover(service, [_rows(6, "2026-10-10 08:00:00", [url])])

        self.assertEqual(items, [])


class AssetStatePersistenceTest(unittest.TestCase):
    def test_default_state_lives_under_the_mounted_crawler_data_dir(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            fake_env = SimpleNamespace(crawler=SimpleNamespace(data_dir=str(tmp)))
            with patch.object(local_asset_state_repository, "env", fake_env):
                repo = LocalAssetStateRepository()
            self.assertEqual(repo.base_dir, (tmp / "state" / "assets").resolve())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cursor_round_trip_and_clear(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            repo = LocalAssetStateRepository(base_dir=tmp)
            self.assertIsNone(repo.get_cursor("mogi"))
            repo.save_cursor("mogi", ("2026-10-01 09:00:00", 40))
            self.assertEqual(repo.get_cursor("mogi"), ("2026-10-01 09:00:00", 40))
            repo.save_cursor("mogi", None)
            self.assertIsNone(repo.get_cursor("mogi"))
            # Cursor files never count as per-source asset state.
            self.assertFalse((tmp / "mogi").exists() and any((tmp / "mogi").glob("*.json")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class AssetBatchSizeTest(unittest.TestCase):
    def _run(self, value):
        service = MagicMock()
        service.reconcile_batch.return_value = AssetBatchResult()
        env = {} if value is None else {"ASSET_BATCH_SIZE": value}
        with patch.dict(os.environ, env, clear=False), patch.object(
            asset_orchestration, "ensure_mysql_schema"
        ), patch.object(asset_orchestration, "AssetReconcilerService", return_value=service):
            if value is None:
                os.environ.pop("ASSET_BATCH_SIZE", None)
            asset_orchestration.sync_assets_minio()
        return service.reconcile_batch.call_args.kwargs["batch_size"]

    def test_batch_size_comes_from_env_and_is_bounded(self):
        self.assertEqual(self._run(None), 100)
        self.assertEqual(self._run("600"), 600)
        self.assertEqual(self._run("999999"), 2000)
        self.assertEqual(self._run("abc"), 100)


if __name__ == "__main__":
    unittest.main()
