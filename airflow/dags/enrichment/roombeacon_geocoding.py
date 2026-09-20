"""Hourly bounded enrichment; provider latency never blocks the crawler DAG."""

from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task


@dag(
    dag_id="roombeacon_geocoding",
    schedule="17 * * * *",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["roombeacon", "enrichment"],
)
def roombeacon_geocoding():
    @task(execution_timeout=timedelta(minutes=5), retries=0)
    def enrich_addresses():
        from roombeacon_crawler.jobs.enrich_geocodes import GeocodeEnrichmentJob
        from airflow.sdk import Variable
        from roombeacon_crawler.services.reverse_geocoder import NominatimReverseGeocoder
        allow_public = Variable.get("roombeacon_geocoding_allow_public", default="false").lower() == "true"
        return GeocodeEnrichmentJob(
            geocoder=NominatimReverseGeocoder(allow_public=allow_public)
        ).run(max_records=10)

    @task(pool="duckdb_analytics_pool", execution_timeout=timedelta(minutes=3))
    def refresh_addresses(summary):
        from roombeacon_crawler.application.orchestration.analytics import refresh_duckdb_analytics
        return refresh_duckdb_analytics([])

    refresh_addresses(enrich_addresses())


roombeacon_geocoding_dag = roombeacon_geocoding()
