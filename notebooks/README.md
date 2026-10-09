# RoomBeacon notebooks

The repository has seven canonical notebooks. The main data/model path runs through
01 → 02 → 03 → 04 → 06 / 07; Notebook 05 is an independent product-retrieval prototype:

1. [01 — RAW EDA](01_roombeacon_eda.ipynb) inspects the current raw snapshot without creating downstream datasets.
2. [02 — Canonical Silver](02_roombeacon_silver.ipynb) performs deterministic Bronze cleaning, validation, and quality classification, then safely writes `data/silver/rental_listings.parquet` and its metadata.
3. [03 — Post-Silver Processing](03_roombeacon_processing.ipynb) reads only `data/silver/rental_listings.parquet` and prepares analytical/model-ready variables without fitting a model.
4. [04 — Rental Price Modeling](04_roombeacon_modeling.ipynb) benchmarks leakage-safe price regression candidates and train-only baselines under one group-aware temporal evaluation protocol.
5. [05 — Nearby Rental Search](05_roombeacon_nearby_rental_search.ipynb) validates retrieval and fallback behavior directly from canonical Silver; it is independent of the price-model path.
6. [06 — Shadow Validation](06_roombeacon_shadow_validation.ipynb) loads the locked LightGBM/RAW/F4 champion, applies target-free inference eligibility, predicts, applies target/trust eligibility only for post-prediction evaluation, monitors drift and error, and persists append-only shadow evidence without training or selecting a model.
7. [07 — Performance Benchmark](07_roombeacon_performance_benchmark.ipynb) measures runtime latency, throughput, memory usage, CPU scaling, cold vs warm performance, and edge-case stability for the frozen champion without training or selecting a model.

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
├── 05_roombeacon_nearby_rental_search.ipynb
├── 06_roombeacon_shadow_validation.ipynb
├── 07_roombeacon_performance_benchmark.ipynb
├── README.md
├── requirements.txt
├── drafts/       # Non-canonical experiments and legacy notebooks
├── docs/         # Methodology and historical findings
├── utils/        # Reusable transformations and quality gates
├── configs/
├── enums/
└── sql/
```

## Notebook layout

Every canonical notebook follows the same structure so they read alike:

1. **Header** — objective, input, output and what is out of scope.
2. **Where this notebook sits** — a pipeline diagram (Mermaid) highlighting the current step.
3. **Setup** — imports and paths only.
4. **Numbered sections `## 01.` …** — each opens with a one-line *Why*, then code, a chart and a table.
5. **Summary** — key findings computed at runtime (never hard-coded numbers) and the next step.

Charts are static matplotlib PNGs (visible on GitHub) built with the shared helpers in
[`utils/notebook_style.py`](utils/notebook_style.py): one validated palette, status colors only for
status, and labels on every bar.

Cells that write artifacts (Notebook 04 champion package, 05 CSVs, 06 shadow runs, 07 benchmark runs) carry
the `skip-execution` tag: they are kept in the notebook but skipped when outputs are regenerated, so a normal
run never overwrites the locked champion. Run them manually only when that write is intended. Notebook 04 also
compares its selection with the locked champion and reports any difference instead of re-selecting.

Select the **RoomBeacon (venv)** kernel. The notebooks are the source of truth; the former generator scripts
live in `drafts/legacy_builders/` for history only.

Use the Python environment from [requirements.txt](requirements.txt), configure `.env`, refresh the Bronze checkpoint, and run the notebooks from the repository root or `notebooks/`. Notebook 02 publishes canonical Silver Parquet only after its pre-Silver gate passes; normal notebook execution requires the local checkpoint rather than a live database connection.

Legacy experiments remain under [drafts](drafts/README.md). Notebook 04 is the
canonical Benchmark V3 selection report and publishes the locked champion
artifact. Notebook 06 is validation/monitoring—not a serving implementation—and
current historical dry-run evidence cannot establish production readiness.
