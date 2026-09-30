import re

with open("README.md", "r") as f:
    content = f.read()

# Locate the System Architecture section
architecture_start = content.find("## <img src=\"https://img.icons8.com/fluency/48/flow-chart.png\" width=\"24\" height=\"24\" style=\"vertical-align: middle;\" alt=\"Architecture\"> System Architecture")

architecture_end = content.find("---", architecture_start)

old_arch = content[architecture_start:architecture_end]

new_arch = """## <img src="https://img.icons8.com/fluency/48/flow-chart.png" width="24" height="24" style="vertical-align: middle;" alt="Architecture"> System Architecture

<p align="center">
  <img
    src="architecture/overall-architecture.png"
    alt="RoomBeacon Overall System Architecture"
    width="100%"
  />
</p>

Hệ thống được thiết kế theo kiến trúc **Clean Architecture** và chia làm các Plane (mặt phẳng) trách nhiệm rõ ràng:

1. **Control Plane (Airflow):** Lên lịch, lập kế hoạch crawl, retry và quản lý task.
2. **Execution Plane (Crawler):** Thu thập dữ liệu, phân tích HTML (parsing) và trích xuất.
3. **Persistence Plane (MySQL / Artifacts):** Lưu trữ gốc (Bronze) với độ tin cậy cao.
4. **Analytics Plane (DuckDB / Parquet):** Truy vấn phân tích, flatten dữ liệu và tạo tập dữ liệu sạch (Silver/Gold).
5. **Asset Plane (MinIO):** Quản lý độc lập vòng đời của các file đa phương tiện (hình ảnh).

```mermaid
flowchart LR
    S[Source Websites] -->|Crawl| C[Crawler Engine]
    
    A[Apache Airflow] -.->|Orchestrate| C
    
    C -->|Raw Artifacts| B[(Bronze)]
    C -->|Relational Data| M[(MySQL)]
    
    M -->|Transform| D[DuckDB Analytics]
    D -->|Clean & Flat| P[(Silver/Gold Parquet)]
    
    M -->|Extract URLs| AS[Asset Sync]
    AS -->|Download| O[(MinIO Assets)]
```

### 🕸️ Crawler Internal Flow

Mô hình xử lý bên trong Crawler (`CrawlRunner`) được tổ chức thành các chuỗi processor linh hoạt:

```mermaid
flowchart LR
    A[CrawlRunner]
    B[Deferred Detail Processor]
    C[Page Acquisition]
    D[Card Processing]
    E[Frontier Decision]
    F[Finalize Result]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> C
    E --> F
```

### 🔄 Data & Analytics Flow

Dữ liệu thô (Bronze) được chuyển dần thành các dạng dữ liệu sẵn sàng cho EDA, Data Mining và Feature Engineering:

```mermaid
flowchart LR
    S[Source Websites]
    C[Crawler]

    B[(Bronze)]
    M[(MySQL Bronze)]

    D[DuckDB]
    V[Analytical Views]

    E[EDA]

    S --> C
    C --> B
    C --> M
    M --> D
    D --> V
    V --> E
```
"""

content = content.replace(old_arch, new_arch)

with open("README.md", "w") as f:
    f.write(content)
