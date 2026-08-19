# 09 — Crawl Run Flow

Tài liệu này mô tả chi tiết luồng thực thi đầy đủ của một phiên crawl trong RoomBeacon Crawler.

---

## 1. Sequence Flow của CrawlRunner

```mermaid
sequenceDiagram
    autonumber
    participant Main as main.py / Airflow
    participant Runner as CrawlRunner
    participant Robots as RobotsPolicy
    participant ListPipe as ListingCrawlPipeline
    participant DetPipe as DetailCrawlPipeline
    participant Mapper as BronzeMapper
    participant Storage as Bronze Storage

    Main->>Runner: run(max_pages, max_records)
    Runner->>Runner: Sinh run_id (run_YYYYMMDD_HHMMSS)
    
    loop Từng Listing Page
        Runner->>Robots: is_allowed(listing_url)
        alt Bị cấm bởi robots.txt
            Robots-->>Runner: False (ROBOTS_DENIED)
        else Được phép
            Runner->>ListPipe: execute(listing_target)
            ListPipe->>ListPipe: Fetch + Classify + Extract Cards
            ListPipe-->>Runner: valid_cards, detail_targets, meta
        end

        loop Từng Detail Target
            alt Chưa crawl URL này
                Runner->>DetPipe: execute(detail_target, card)
                DetPipe->>DetPipe: Fetch + Classify + Extract Detail
                DetPipe->>Mapper: map(card, detail, run_id)
                Mapper-->>DetPipe: RentalBronzeRecord
                DetPipe-->>Runner: bronze_record, meta
            end
        end
        Runner->>Runner: Kiểm tra DateCutoff & MaxRecords
    end

    Runner->>Storage: Ghi listings.json, metadata.json, manifest.json
    Runner-->>Main: records, CrawlRunResult
```

---

## 2. Cách thức gọi từ Python Code / Apache Airflow

```python
from roombeacon_crawler.config.crawler_settings import CrawlerSettings
from roombeacon_crawler.pipeline.crawl_runner import CrawlRunner
from roombeacon_crawler.sources.nhatot.adapter import NhatotSourceAdapter

settings = CrawlerSettings(
    max_pages=2,
    max_total_records=50,
)
adapter = NhatotSourceAdapter()
runner = CrawlRunner(adapter=adapter, settings=settings)

# Chạy async trong Python hoặc Airflow PythonOperator:
records, result = await runner.run()
```
