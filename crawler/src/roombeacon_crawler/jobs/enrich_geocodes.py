"""Run bounded, serialized geocoding independently of listing acquisition."""

import time

from roombeacon_crawler.infrastructure.mysql.repositories.geocode_repository import MySQLGeocodeRepository
from roombeacon_crawler.services.reverse_geocoder import NominatimReverseGeocoder


class GeocodeEnrichmentJob:
    def __init__(self, *, repository=None, geocoder=None, sleep=time.sleep):
        self.repo = repository if repository is not None else MySQLGeocodeRepository()
        self.geocoder = geocoder if geocoder is not None else NominatimReverseGeocoder()
        self.sleep = sleep

    def run(self, max_records: int = 10) -> dict:
        if isinstance(max_records, bool) or not isinstance(max_records, int) or not 1 <= max_records <= 100:
            raise ValueError("max_records must be an integer between 1 and 100")
        self.repo.ensure_table()
        summary = {"status": "SUCCESS", "attempted": 0, "saved": 0, "failed": 0}
        if getattr(self.geocoder, "enabled", True) is False:
            return {**summary, "status": "DISABLED_PROVIDER"}
        with self.repo.enrichment_lock() as acquired:
            if not acquired:
                return {**summary, "status": "SKIPPED_LOCKED"}
            for lat, lon in self.repo.pending_coordinates(max_records):
                lat, lon = float(lat), float(lon)
                if self.repo.get_cached(lat, lon):
                    continue
                summary["attempted"] += 1
                try:
                    result = self.geocoder.reverse(lat, lon)
                    if result is not None:
                        self.repo.save(result)
                        summary["saved"] += 1
                    else:
                        self.repo.defer_failure(lat, lon)
                        summary["failed"] += 1
                finally:
                    # Regular public Nominatim batches: <=4 requests/minute.
                    # Hold the cross-process lock through the final interval too.
                    self.sleep(16)
        if summary["failed"]:
            summary["status"] = "PARTIAL"
        return summary
