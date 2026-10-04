# RoomBeacon notebooks

The repository has four canonical notebooks, in execution order:

1. [01 — RAW EDA](01_roombeacon_eda.ipynb) inspects the current raw snapshot without creating downstream datasets.
2. [02 — Canonical Silver](02_roombeacon_silver.ipynb) performs deterministic Bronze cleaning, validation, and quality classification, then safely writes `data/silver/rental_listings.parquet` and its metadata.
3. [03 — Post-Silver Processing](03_roombeacon_processing.ipynb) reads only `data/silver/rental_listings.parquet` and prepares analytical/model-ready variables without fitting a model.
4. [04 — Rental Price Modeling](04_roombeacon_modeling.ipynb) benchmarks leakage-safe price regression candidates and train-only baselines under one group-aware temporal evaluation protocol.

MySQL remains canonical Bronze. Refresh the disposable analytical checkpoint explicitly before running notebooks 01 or 02:

```bash
./venv/bin/python -m analytics.bronze.snapshot
```

The command safely publishes `data/bronze/snapshot/latest_posts.parquet`, `raw_evidence.parquet`, and `metadata.json`. Notebooks 01 and 02 load these local files and therefore analyze the same snapshot ID without contacting MySQL. DuckDB remains the embedded analytical/query and Parquet engine; a physical DuckDB Silver table is not required for persistence.

```text
notebooks/
├── 01_roombeacon_eda.ipynb
├── 02_roombeacon_silver.ipynb
├── 03_roombeacon_processing.ipynb
├── 04_roombeacon_modeling.ipynb
├── README.md
├── requirements.txt
├── drafts/       # Non-canonical experiments and legacy notebooks
├── docs/         # Methodology and historical findings
├── utils/        # Reusable transformations and quality gates
├── configs/
├── enums/
└── sql/
```

Use the Python environment from [requirements.txt](requirements.txt), configure `.env`, refresh the Bronze checkpoint, and run the notebooks from the repository root or `notebooks/`. Notebook 02 publishes canonical Silver Parquet only after its pre-Silver gate passes; normal notebook execution requires the local checkpoint rather than a live database connection.

Legacy experiments remain under [drafts](drafts/README.md). Notebook 04 is the canonical Benchmark V1 report; it does not deploy a model or implement recommendation/search-ranking ML.
