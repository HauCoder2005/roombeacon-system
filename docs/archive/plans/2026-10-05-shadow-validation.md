> **ARCHIVED** — superseded by [PRICE_MODEL.md](../../05-analytics-ml/PRICE_MODEL.md).

# RoomBeacon Shadow Validation Implementation Plan

1. Lock the existing LightGBM/RAW/F4 champion contract and add serialization/reference-profile persistence to Notebook 04's builder without changing selection logic.
2. Implement target-free reusable inference, schema validation, drift, evaluation, readiness, versioning, and append-only persistence helpers in `notebooks/utils/shadow_validation.py` using tests first.
3. Materialize the missing champion with one fit of the already-locked configuration; do not benchmark, tune, or reselect.
4. Generate Notebook 06 from `build_shadow_validation_notebook.py` with the required 01–22 monitoring sections and no training calls.
5. Update notebook architecture tests and documentation maps/explanation.
6. Execute Notebook 06 cleanly as `HISTORICAL_DRY_RUN`, inspect persisted evidence, then run targeted and regression tests before reporting candidate status.
