from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from roombeacon_crawler.enums.crawl_mode import CrawlMode
from roombeacon_crawler.enums.crawl_status import CrawlStatus
from roombeacon_crawler.models.crawl_plan import CrawlPlan
from roombeacon_crawler.models.crawl_target_state import CrawlTargetState
from roombeacon_crawler.models.source_health_state import (
    SourceHealthOutcome,
    SourceHealthState,
)
from roombeacon_crawler.policies.source_health_policy import SourceHealthPolicy
from roombeacon_crawler.repositories.local_crawl_state_repository import (
    LocalCrawlStateRepository,
)
from roombeacon_crawler.repositories.local_source_health_repository import (
    LocalSourceHealthRepository,
)


class TestSourceHealthAndAdaptiveBackoff(unittest.TestCase):
    """Kiểm thử toàn diện hệ thống Source Health, Failure Backoff, Cooldown Gate và Checkpoint Safety."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.health_repo = LocalSourceHealthRepository(base_data_dir=self.tmp_dir.name)
        self.state_repo = LocalCrawlStateRepository(base_data_dir=self.tmp_dir.name)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_health_policy_cooldown_escalation(self) -> None:
        """Kiểm tra chuỗi thời gian backoff tăng dần (15m, 30m, 60m, 6h, 12h, 24h)."""
        policy = SourceHealthPolicy()
        now = datetime(2026, 8, 21, 10, 0, 0, tzinfo=timezone.utc)

        # Failure 1 -> 15m
        cd1 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 1, current_time=now)
        self.assertEqual(cd1, now + timedelta(minutes=15))

        # Failure 2 -> 30m
        cd2 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 2, current_time=now)
        self.assertEqual(cd2, now + timedelta(minutes=30))

        # Failure 3 -> 60m
        cd3 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 3, current_time=now)
        self.assertEqual(cd3, now + timedelta(minutes=60))

        # Failure 4 -> 360m (6h)
        cd4 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 4, current_time=now)
        self.assertEqual(cd4, now + timedelta(minutes=360))

        # Failure 5 -> 720m (12h)
        cd5 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 5, current_time=now)
        self.assertEqual(cd5, now + timedelta(minutes=720))

        # Failure 6+ -> 1440m (24h bounded)
        cd6 = policy.calculate_cooldown(SourceHealthOutcome.ACCESS_CHALLENGE, 6, current_time=now)
        self.assertEqual(cd6, now + timedelta(minutes=1440))

    def test_access_challenge_backoff_lifecycle(self) -> None:
        """Test Section 21: Vòng đời thất bại liên tiếp do ACCESS_CHALLENGE và tăng cooldown."""
        t0 = datetime(2026, 8, 21, 8, 0, 0, tzinfo=timezone.utc)

        # Run 1: Thất bại lần 1
        h1 = self.health_repo.record_failure(
            source="batdongsan",
            target_id="hcm_phongtro",
            outcome=SourceHealthOutcome.ACCESS_CHALLENGE,
            reason="Cloudflare challenge (HTTP 403)",
            http_status=403,
            current_time=t0,
        )
        self.assertEqual(h1.consecutive_failures, 1)
        self.assertEqual(h1.cooldown_until, (t0 + timedelta(minutes=15)).isoformat())
        self.assertTrue(h1.is_in_cooldown(t0 + timedelta(minutes=10)))
        self.assertFalse(h1.is_in_cooldown(t0 + timedelta(minutes=16)))

        # Run 2: Thất bại lần 2 sau khi hết cooldown 15m
        t1 = t0 + timedelta(minutes=20)
        h2 = self.health_repo.record_failure(
            source="batdongsan",
            target_id="hcm_phongtro",
            outcome=SourceHealthOutcome.ACCESS_CHALLENGE,
            reason="Cloudflare challenge (HTTP 403)",
            http_status=403,
            current_time=t1,
        )
        self.assertEqual(h2.consecutive_failures, 2)
        self.assertEqual(h2.cooldown_until, (t1 + timedelta(minutes=30)).isoformat())

        # Run 3: Thất bại lần 3 sau khi hết cooldown 30m
        t2 = t1 + timedelta(minutes=35)
        h3 = self.health_repo.record_failure(
            source="batdongsan",
            target_id="hcm_phongtro",
            outcome=SourceHealthOutcome.ACCESS_CHALLENGE,
            reason="Cloudflare challenge (HTTP 403)",
            http_status=403,
            current_time=t2,
        )
        self.assertEqual(h3.consecutive_failures, 3)
        self.assertEqual(h3.cooldown_until, (t2 + timedelta(minutes=60)).isoformat())

    def test_success_resets_health_state(self) -> None:
        """Test Section 22: Truy cập thành công reset hoàn toàn failure counter và cooldown."""
        t0 = datetime(2026, 8, 21, 8, 0, 0, tzinfo=timezone.utc)
        # Giả lập đã thất bại 3 lần trước đó
        for i in range(3):
            self.health_repo.record_failure(
                source="batdongsan",
                target_id="hcm_phongtro",
                outcome=SourceHealthOutcome.ACCESS_CHALLENGE,
                current_time=t0 + timedelta(minutes=i * 60),
            )

        current_h = self.health_repo.get_health("batdongsan", "hcm_phongtro")
        self.assertIsNotNone(current_h)
        self.assertEqual(current_h.consecutive_failures, 3)

        # Tiếp theo thành công (sau khi hết cooldown)
        t_success = t0 + timedelta(hours=5)
        h_recovered = self.health_repo.record_success(
            source="batdongsan",
            target_id="hcm_phongtro",
            current_time=t_success,
        )
        self.assertEqual(h_recovered.last_outcome, SourceHealthOutcome.HEALTHY)
        self.assertEqual(h_recovered.consecutive_failures, 0)
        self.assertIsNone(h_recovered.last_failure_reason)
        self.assertIsNone(h_recovered.cooldown_until)
        self.assertEqual(h_recovered.last_access_success_at, t_success.isoformat())

    def test_checkpoint_preservation_on_failure(self) -> None:
        """Test Section 23: Thất bại challenge cập nhật Health State nhưng bảo toàn tuyệt đối Crawl Synchronization Checkpoint."""
        # Giả lập state ban đầu đang ở BOOTSTRAP_CONTINUE tại page 51
        initial_state = CrawlTargetState(
            source="phongtro123",
            target_id="hcm_phongtro",
            bootstrap_completed=False,
            bootstrap_next_page=51,
            last_success_at="2026-08-20T12:00:00+00:00",
        )
        self.state_repo.save_state(initial_state)

        # Mô phỏng task update_checkpoint khi gặp ACCESS_CHALLENGE tại page 51
        from airflow.dags.crawler.roombeacon_crawler import update_checkpoint

        result_payload = {
            "source": "phongtro123",
            "target_id": "hcm_phongtro",
            "crawl_status": "cloudflare_challenge",
            "action": "ACCESS_CHALLENGE",
            "failure_reason": "HTTP 403 Cloudflare challenge",
            "plan": {"mode": "BOOTSTRAP_CONTINUE", "interval_minutes": 60},
        }

        with patch("airflow.dags.crawler.roombeacon_crawler.LocalCrawlStateRepository", return_value=self.state_repo), \
             patch("airflow.dags.crawler.roombeacon_crawler.LocalSourceHealthRepository", return_value=self.health_repo):
            cp_res = update_checkpoint.function(result_payload=result_payload)

        self.assertTrue(cp_res["target_state_persisted"])
        self.assertFalse(cp_res["success_checkpoint_advanced"])
        self.assertTrue(cp_res["health_state_updated"])

        # Kiểm tra sync state được bảo toàn: bootstrap_next_page vẫn là 51
        saved_state = self.state_repo.get_state("phongtro123", "hcm_phongtro")
        self.assertEqual(saved_state.bootstrap_next_page, 51)
        self.assertEqual(saved_state.last_success_at, "2026-08-20T12:00:00+00:00")

        # Kiểm tra health state được cập nhật: failure count = 1
        health = self.health_repo.get_health("phongtro123", "hcm_phongtro")
        self.assertEqual(health.consecutive_failures, 1)
        self.assertEqual(health.last_outcome, SourceHealthOutcome.ACCESS_CHALLENGE)
        self.assertIsNotNone(health.cooldown_until)

    def test_robots_fetch_error_and_root_cause_preservation(self) -> None:
        """Test Section 24: Robots.txt trả về HTTP 403 lưu đúng root cause ROBOTS_FETCH_ERROR và không advance success checkpoint."""
        from airflow.dags.crawler.roombeacon_crawler import qualify_target, update_checkpoint

        plan = {
            "source": "muaban",
            "target_id": "hcm_phongtro",
            "target_url": "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro",
            "mode": "BOOTSTRAP_FULL",
            "interval_minutes": 60,
        }

        # Mock RobotsPolicy evaluate trả về ERROR với error_details
        mock_policy = MagicMock()
        mock_policy.evaluate.return_value = ("ERROR", "https://muaban.net/robots.txt")
        mock_policy.get_error_details.return_value = {
            "status_code": 403,
            "reason": "Forbidden",
            "failure_type": "ROBOTS_FETCH_ERROR",
        }

        with patch("airflow.dags.crawler.roombeacon_crawler.RobotsPolicy", return_value=mock_policy), \
             patch("airflow.dags.crawler.roombeacon_crawler.LocalSourceHealthRepository", return_value=self.health_repo):
            qual_res = qualify_target.function(plan=plan)

        self.assertEqual(qual_res["qualification_status"], "CHECK_FAILED")
        self.assertEqual(qual_res["failure_reason"], "ROBOTS_FETCH_ERROR")
        self.assertEqual(qual_res["http_status"], 403)

        # Chạy update_checkpoint cho qualification thất bại này
        result_payload = {
            "source": "muaban",
            "target_id": "hcm_phongtro",
            "crawl_status": "check_failed",
            "action": "SKIPPED",
            "failure_reason": qual_res["failure_reason"],
            "http_status": qual_res["http_status"],
            "plan": plan,
        }

        with patch("airflow.dags.crawler.roombeacon_crawler.LocalCrawlStateRepository", return_value=self.state_repo), \
             patch("airflow.dags.crawler.roombeacon_crawler.LocalSourceHealthRepository", return_value=self.health_repo):
            cp_res = update_checkpoint.function(result_payload=result_payload)

        self.assertFalse(cp_res["success_checkpoint_advanced"])
        self.assertTrue(cp_res["health_state_updated"])

        health = self.health_repo.get_health("muaban", "hcm_phongtro")
        self.assertEqual(health.last_outcome, SourceHealthOutcome.ROBOTS_FETCH_ERROR)
        self.assertEqual(health.last_http_status, 403)
        self.assertEqual(health.consecutive_failures, 1)

    def test_cooldown_gate_makes_zero_network_requests(self) -> None:
        """Test Section 25: Target đang trong cooldown kích hoạt Health Gate DEFER mà không gửi bất kỳ request mạng nào."""
        from airflow.dags.crawler.roombeacon_crawler import qualify_target, execute_crawl, update_checkpoint

        # Thiết lập health state đang trong cooldown
        future_time = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        active_cd_state = SourceHealthState(
            source="muaban",
            target_id="hcm_phongtro",
            last_outcome=SourceHealthOutcome.ACCESS_CHALLENGE,
            consecutive_failures=2,
            cooldown_until=future_time,
        )
        self.health_repo.save_health(active_cd_state)

        plan = {
            "source": "muaban",
            "target_id": "hcm_phongtro",
            "target_url": "https://muaban.net/bat-dong-san/cho-thue-phong-tro-nha-tro",
            "mode": "BOOTSTRAP_FULL",
            "interval_minutes": 60,
        }

        # Mock URLValidator, RobotsPolicy và CrawlRunner để xác nhận chúng KHÔNG được gọi
        with patch("airflow.dags.crawler.roombeacon_crawler.LocalSourceHealthRepository", return_value=self.health_repo), \
             patch("airflow.dags.crawler.roombeacon_crawler.URLValidator.validate") as mock_url_val, \
             patch("airflow.dags.crawler.roombeacon_crawler.RobotsPolicy") as mock_rp, \
             patch("roombeacon_crawler.pipeline.crawl_runner.CrawlRunner.execute_crawl") as mock_runner:

            qual_res = qualify_target.function(plan=plan)

            # Khẳng định 0 request mạng và 0 validation được gọi
            mock_url_val.assert_not_called()
            mock_rp.assert_not_called()
            self.assertEqual(qual_res["qualification_status"], "COOLDOWN_ACTIVE")
            self.assertEqual(qual_res["action"], "DEFERRED")

            exec_res = execute_crawl.function(qual_payload=qual_res)
            mock_runner.assert_not_called()
            self.assertEqual(exec_res["action"], "DEFERRED")
            self.assertEqual(exec_res["crawl_status"], "cooldown_active")

            with patch("airflow.dags.crawler.roombeacon_crawler.LocalCrawlStateRepository", return_value=self.state_repo):
                cp_res = update_checkpoint.function(result_payload=exec_res)

            self.assertFalse(cp_res["target_state_persisted"])
            self.assertFalse(cp_res["success_checkpoint_advanced"])
            self.assertFalse(cp_res["health_state_updated"])
            self.assertTrue(cp_res["deferred_cooldown"])

    def test_summary_semantics_refined(self) -> None:
        """Test Section 26: Thống kê tổng hợp phân biệt rõ ràng giữa target persisted, checkpoint advanced và health updated."""
        from airflow.dags.crawler.roombeacon_crawler import summarize_run

        plans = [
            {"mode": "BOOTSTRAP_FULL"},
            {"mode": "BOOTSTRAP_CONTINUE"},
            {"mode": "INCREMENTAL"},
        ]
        qualifications = [
            {"qualification_status": "READY"},
            {"qualification_status": "COOLDOWN_ACTIVE", "is_cooldown": True},
            {"qualification_status": "CHECK_FAILED"},
        ]
        crawl_results = [
            {"crawl_status": "success", "records_created": 20, "details_success": 2, "action": "CRAWLED"},
            {"crawl_status": "cooldown_active", "records_created": 0, "details_success": 0, "action": "DEFERRED"},
            {"crawl_status": "check_failed", "records_created": 0, "details_success": 0, "action": "SKIPPED"},
        ]
        checkpoints = [
            {"target_state_persisted": True, "success_checkpoint_advanced": True, "health_state_updated": True, "deferred_cooldown": False},
            {"target_state_persisted": False, "success_checkpoint_advanced": False, "health_state_updated": False, "deferred_cooldown": True},
            {"target_state_persisted": True, "success_checkpoint_advanced": False, "health_state_updated": True, "deferred_cooldown": False},
        ]

        summary = summarize_run.function(
            plans=plans,
            qualifications=qualifications,
            crawl_results=crawl_results,
            checkpoints=checkpoints,
        )

        self.assertEqual(summary["targets_due"], 3)
        self.assertEqual(summary["targets_executable"], 2)
        self.assertEqual(summary["targets_deferred_cooldown"], 1)
        self.assertEqual(summary["bootstrap_planned"], 1)
        self.assertEqual(summary["bootstrap_continue_planned"], 1)
        self.assertEqual(summary["incremental_planned"], 1)
        self.assertEqual(summary["crawl_success"], 1)
        self.assertEqual(summary["records_created"], 20)
        self.assertEqual(summary["target_states_persisted"], 2)
        self.assertEqual(summary["success_checkpoints_advanced"], 1)
        self.assertEqual(summary["health_states_updated"], 2)


if __name__ == "__main__":
    unittest.main()
