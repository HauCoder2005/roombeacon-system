# RoomBeacon notebooks

The repository has three canonical notebooks, in execution order:

1. [01 — RAW EDA](01_roombeacon_eda.ipynb) inspects the current raw snapshot without creating downstream datasets.
2. [02 — Canonical Silver](02_roombeacon_silver.ipynb) performs deterministic Bronze cleaning, validation, and quality classification, then safely writes `data/silver/rental_listings.parquet` and its metadata.
3. [03 — Post-Silver Processing](03_roombeacon_processing.ipynb) reads only `data/silver/rental_listings.parquet` and prepares analytical/model-ready variables without fitting a model.

DuckDB remains the analytical/query engine; a physical DuckDB Silver table is not required for persistence.

```text
notebooks/
├── 01_roombeacon_eda.ipynb
├── 02_roombeacon_silver.ipynb
├── 03_roombeacon_processing.ipynb
├── README.md
├── requirements.txt
├── drafts/       # Non-canonical experiments and legacy notebooks
├── docs/         # Methodology and historical findings
├── utils/        # Reusable transformations and quality gates
├── configs/
├── enums/
└── sql/
```

Use the Python environment from [requirements.txt](requirements.txt), configure `.env`, and run the notebooks from the repository root or `notebooks/`. Notebook 02 requires the Bronze database to be reachable and publishes canonical Silver Parquet only after its pre-Silver gate passes.

Model experiments remain under [drafts](drafts/README.md); no canonical modeling notebook is required until actual model fitting is promoted into the official workflow.
