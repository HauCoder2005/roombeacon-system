"""Regression checks for bounded work, durable storage and scheduled enrichment."""
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from roombeacon_crawler.application.crawl.deferred_details import DeferredDetailProcessor
from roombeacon_crawler.application.orchestration.persistence import persist_bronze_mysql
from roombeacon_crawler.application.orchestration.errors import CrawlerWorkflowError
from roombeacon_crawler.jobs.enrich_geocodes import GeocodeEnrichmentJob
from roombeacon_crawler.domain.models.geocoded_location import GeocodedLocation
from roombeacon_crawler.policies.deferred_budget_scheduler import DeferredBudgetScheduler


@contextmanager
def acquired_lock():
    yield True


def geocode_repo():
    repo = MagicMock()
    repo.enrichment_lock.side_effect = acquired_lock
    repo.get_cached.return_value = None
    return repo


def test_geocode_failure_defers_coordinate_and_batch_continues():
    repo = geocode_repo()
    repo.pending_coordinates.return_value = [(10, 106), (11, 107)]
    provider = MagicMock()
    loc = GeocodedLocation(11, 107, geocoded_address_text='123 Lê Lợi')
    provider.reverse.side_effect = [None, loc]
    sleep = MagicMock()
    result = GeocodeEnrichmentJob(repository=repo, geocoder=provider, sleep=sleep).run(2)
    assert result == {'status': 'PARTIAL', 'attempted': 2, 'saved': 1, 'failed': 1}
    repo.defer_failure.assert_called_once_with(10.0, 106.0)
    repo.save.assert_called_once_with(loc)
    assert [call.args for call in sleep.call_args_list] == [(16,), (16,)]


def test_geocode_cache_and_lock_prevent_network_requests():
    repo = geocode_repo()
    repo.pending_coordinates.return_value = [(10, 106)]
    repo.get_cached.return_value = GeocodedLocation(10, 106)
    provider = MagicMock()
    job = GeocodeEnrichmentJob(repository=repo, geocoder=provider, sleep=MagicMock())
    assert job.run()['attempted'] == 0
    provider.reverse.assert_not_called()
    @contextmanager
    def locked():
        yield False
    repo.enrichment_lock.side_effect = locked
    repo.pending_coordinates.reset_mock()
    assert job.run()['status'] == 'SKIPPED_LOCKED'
    repo.pending_coordinates.assert_not_called()


def test_invalid_batch_never_creates_tables():
    repo = geocode_repo()
    with pytest.raises(ValueError):
        GeocodeEnrichmentJob(repository=repo).run(0)
    repo.ensure_table.assert_not_called()


def test_expired_deadline_leaves_backlog_pending():
    import asyncio
    repo = MagicMock()
    repo.count_backlog.return_value = 2
    repo.get_backlog.return_value = [object(), object()]
    pipeline = SimpleNamespace(execute=AsyncMock())
    processor = DeferredDetailProcessor(
        adapter=SimpleNamespace(SOURCE_NAME='test'), detail_pipeline=pipeline,
        repository=repo, scheduler=DeferredBudgetScheduler(),
    )
    result = asyncio.run(processor.execute(
        run_id='r', target_id='t', now=datetime.now(timezone.utc),
        crawl_details=True, max_details_per_run=2,
        bronze_records=[], detail_records=[], metadata=[], updated_seen_meta={}, deadline=0,
    ))
    assert result.attempted == 0
    pipeline.execute.assert_not_called()
    repo.record_success.assert_not_called()
    repo.record_failure.assert_not_called()


def test_mirror_failure_prevents_mysql_persistence():
    payload = dict(source='test', target_id='t', run_id='r', action='CRAWLED',
                   crawl_status='success', bronze_path='/tmp/test-bronze')
    from roombeacon_crawler.enums.crawl_status import CrawlStatus
    payload['crawl_status'] = CrawlStatus.SUCCESS.value
    with (
        patch('roombeacon_crawler.infrastructure.mysql.schema.ensure_mysql_schema'),
        patch('roombeacon_crawler.mappers.bronze_observation_loader.BronzeObservationLoader.load_from_bronze_dir', return_value=[object()]),
        patch('roombeacon_crawler.infrastructure.storage.minio.raw_artifact_mirror.MinIORawArtifactMirror.mirror_directory', side_effect=RuntimeError('unavailable')),
        patch('roombeacon_crawler.application.persistence.persist_observations.PersistBronzeObservationsUseCase') as use_case,
    ):
        with pytest.raises(CrawlerWorkflowError, match='mirror failed'):
            persist_bronze_mysql(payload)
        use_case.assert_not_called()
