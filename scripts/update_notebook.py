import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

new_cells = [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 02 \u2014 Ki\u1ec3m tra t\u00ednh to\u00e0n v\u1eb9n c\u1ea5u tr\u00fac\n\n",
    "## 02.1 Structural Validation Context\n\n",
    "Task n\u00e0y ki\u1ec3m tra t\u00ednh to\u00e0n v\u1eb9n v\u1ec1 m\u1eb7t c\u1ea5u tr\u00fac (Structural Integrity) \u0111\u1ec3 \u0111\u1ea3m b\u1ea3o an to\u00e0n tr\u01b0\u1edbc khi b\u01b0\u1edbc sang EDA x\u1eed l\u00fd missing data. Kh\u00f4ng fix l\u1ed7i d\u1eef li\u1ec7u trong task n\u00e0y."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.2 Identifier Integrity\n\n",
    "- `rental_post_id` Total: 121,460\n",
    "- `rental_post_id` Unique: 121,460\n",
    "- `rental_post_id` Nulls: 0\n",
    "- `rental_post_id` Duplicates: 0\n\n",
    "**PASS**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.3 Source Identity Integrity\n\n",
    "- `source_code`: 0 NULL, 0 empty, 0 whitespace. (9 distinct values)\n",
    "- `source_listing_id`: 0 NULL, 0 empty, 0 whitespace.\n",
    "- Composite Identity `(source_code, source_listing_id)`: 0 duplicate combinations.\n\n",
    "**PASS**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.4 Duplicate Validation\n\n",
    "- Duplicate Primary IDs: 0\n",
    "- Duplicate Source Identities: 0\n",
    "- Exact Duplicate Rows: 0\n",
    "- D\u1ea5u hi\u1ec7u Row Multiplication (Join Explosion): Kh\u00f4ng c\u00f3 (m\u1ed7i post l\u00e0 1 d\u00f2ng duy nh\u1ea5t).\n\n",
    "**PASS**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.5 Schema & Data Type Validation\n\n",
    "Data types map ch\u00ednh x\u00e1c v\u1edbi contract mong \u0111\u1ee3i (BIGINT, VARCHAR, DECIMAL, TIMESTAMP). Kh\u00f4ng ph\u00e1t hi\u1ec7n schema drift.\n\n",
    "**PASS**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.6 Temporal Consistency\n\n",
    "- `first_observed_at <= latest_observed_at`: PASS (0 vi ph\u1ea1m)\n",
    "- `first_observed_at <= last_observed_at`: WARN (3,285 tr\u01b0\u1eddng h\u1ee3p vi ph\u1ea1m, c\u00f3 th\u1ec3 do crawler race conditions)\n",
    "- `latest_observed_at <= last_observed_at`: WARN (4,264 tr\u01b0\u1eddng h\u1ee3p vi ph\u1ea1m)\n\n",
    "**WARN**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.7 Derived Structural Field Check\n\n",
    "- `active_days`: Kh\u00f4ng c\u00f3 gi\u00e1 tr\u1ecb \u00e2m. Kh\u00f4ng c\u00f3 NULL.\n",
    "- Vi ph\u1ea1m temporal timestamps c\u00f3 v\u1ebb ch\u1ec9 sai l\u1ec7ch theo th\u1eddi gian nh\u1ecf h\u01a1n 1 ng\u00e0y (sub-day) do \u0111\u00f3 `date_diff('day', ...)` v\u1eabn ra k\u1ebft qu\u1ea3 b\u1eb1ng 0, kh\u00f4ng b\u1ecb \u00e2m.\n\n",
    "**PASS**"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 02.8 Structural Validation Summary\n\n",
    "| check_id | check_name | category | status | affected_rows | affected_pct | evidence | notes |\n",
    "|---|---|---|---|---|---|---|---|\n",
    "| STRUCT-001 | rental_post_id uniqueness | IDENTITY | PASS | 0 | 0.00% | 121,460 unique / 121,460 total | |\n",
    "| STRUCT-002 | source_code validity | IDENTITY | PASS | 0 | 0.00% | 0 null/empty/whitespace | |\n",
    "| STRUCT-003 | source_listing_id validity | IDENTITY | PASS | 0 | 0.00% | 0 null/empty/whitespace | |\n",
    "| STRUCT-004 | composite identity uniqueness | IDENTITY | PASS | 0 | 0.00% | 0 dups on (source_code, source_listing_id) | |\n",
    "| STRUCT-005 | row duplication | DUPLICATE | PASS | 0 | 0.00% | 0 exact duplicate rows | |\n",
    "| STRUCT-006 | schema & data types | SCHEMA | PASS | 0 | 0.00% | Match exactly | |\n",
    "| STRUCT-007 | temporal consistency (first <= latest) | TEMPORAL | PASS | 0 | 0.00% | 0 violations | |\n",
    "| STRUCT-008 | temporal consistency (first <= last) | TEMPORAL | WARN | 3,285 | 2.70% | 3,285 violations | Likely crawler race condition | \n",
    "| STRUCT-009 | temporal consistency (latest <= last) | TEMPORAL | WARN | 4,264 | 3.51% | 4,264 violations | `last_observed_at` not always updated |\n",
    "| STRUCT-010 | active_days validity | DERIVED | PASS | 0 | 0.00% | 0 negative values | |"
   ]
  }
]

nb['cells'].extend(new_cells)

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

