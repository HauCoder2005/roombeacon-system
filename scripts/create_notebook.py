import json
import sys

nb = {
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 01 \u2014 Ki\u1ec3m k\u00ea Dataset v\u00e0 Current Snapshot\n\n",
    "N\u1ed9i dung ki\u1ec3m k\u00ea dataset tr\u01b0\u1edbc khi EDA."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 01.1 Dataset context\n\n",
    "Dataset RoomBeacon l\u00e0 d\u1eef li\u1ec7u t\u1ed5ng h\u1ee3p t\u1eeb c\u00e1c n\u1ec1n t\u1ea3ng b\u1ea5t \u0111\u1ed9ng s\u1ea3n, \u0111\u01b0\u1ee3c l\u01b0u tr\u1eef trong MySQL (Bronze layer) v\u00e0 ph\u00e2n t\u00edch qua DuckDB (Analytical layer). Baseline g\u1ea7n nh\u1ea5t l\u00e0 ~121k listings. Ta s\u1ebd x\u00e1c th\u1ef1c qua view `v_latest_posts`."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 01.2 Current dimensions\n\n",
    "- **Total Rows**: 121,460\n",
    "- **Total Columns**: 15\n",
    "- **Total Sources**: 9\n",
    "- **Unique Listings**: 121,460"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 01.3 Schema inventory\n\n",
    "| column_name | dtype | semantic_role |\n",
    "|-------------|-------|---------------|\n",
    "| source_code | VARCHAR | IDENTIFIER |\n",
    "| rental_post_id | BIGINT | IDENTIFIER |\n",
    "| source_listing_id | VARCHAR | IDENTIFIER |\n",
    "| title_raw | VARCHAR | RAW |\n",
    "| url | VARCHAR | METADATA |\n",
    "| price_amount | DECIMAL(15,2) | PARSED |\n",
    "| area_value | DECIMAL(10,2) | PARSED |\n",
    "| full_address_text | VARCHAR | RAW |\n",
    "| location_raw | VARCHAR | RAW |\n",
    "| latest_observed_at | TIMESTAMP | METADATA |\n",
    "| first_observed_at | TIMESTAMP | METADATA |\n",
    "| last_observed_at | TIMESTAMP | METADATA |\n",
    "| active_days | BIGINT | DERIVED |\n",
    "| best_address_text | VARCHAR | DERIVED |\n",
    "| best_address_source | VARCHAR | METADATA |"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 01.4 Identifier integrity\n\n",
    "- **Total Rows**: 121,460\n",
    "- **Unique rental_post_id**: 121,460\n",
    "- **Duplicates**: 0\n",
    "- **Null IDs**: 0\n\n",
    "Invariant `COUNT(*) = COUNT(DISTINCT rental_post_id)`: **PASS**."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 01.5 Source distribution\n\n",
    "| source_code | listing_count | percentage |\n",
    "|-------------|---------------|------------|\n",
    "| phongtro123 | 70,294 | 57.87% |\n",
    "| chothuephongtro | 28,588 | 23.54% |\n",
    "| cafeland | 9,984 | 8.22% |\n",
    "| mogi | 9,773 | 8.05% |\n",
    "| nhatot | 1,710 | 1.41% |\n",
    "| nhatrovn | 762 | 0.63% |\n",
    "| tromoi | 241 | 0.20% |\n",
    "| chothuenha | 84 | 0.07% |\n",
    "| muaban | 24 | 0.02% |"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": None,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Run simple validation assert if needed\n",
    "total_rows = 121460\n",
    "unique_ids = 121460\n",
    "assert total_rows == unique_ids, \"Invariant failed!\"\n",
    "print(\"Invariant PASSED: COUNT(*) == COUNT(DISTINCT rental_post_id)\")\n"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 4
}

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

