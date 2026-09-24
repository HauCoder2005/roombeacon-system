import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

new_cells = [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# 03 \u2014 Ng\u1eef ngh\u0129a d\u1eef li\u1ec7u thi\u1ebfu\n\n",
    "## 03.1 Missing Data l\u00e0 g\u00ec?\n\n",
    "Missing Data l\u00e0 t\u00ecnh tr\u1ea1ng m\u1ed9t thu\u1ed9c t\u00ednh (field) kh\u00f4ng c\u00f3 th\u00f4ng tin h\u1ee3p l\u1ec7. Tr\u1ea1ng th\u00e1i Missing c\u00f3 th\u1ec3 bi\u1ec3u hi\u1ec7n qua NULL, v\u00e0 string r\u1ed7ng hay string ch\u1ec9 c\u00f3 kho\u1ea3ng tr\u1eafng. C\u1ea7n ph\u00e2n bi\u1ec7t r\u00f5 v\u1edbi Invalid (d\u1eef li\u1ec7u sai logic) v\u00e0 Not Applicable (kh\u00f4ng \u00e1p d\u1ee5ng).\n\n",
    "*L\u01b0u \u00fd:* T\u1ea1i \u0111\u00e2y t\u1eadp trung \u0111\u1ecbnh ngh\u0129a lu\u1eadt, kh\u00f4ng th\u1ef1c hi\u1ec7n clean \u0111\u1ec3 \u0111\u1ea3m b\u1ea3o t\u00ednh to\u00e0n v\u1eb9n ph\u00e2n t\u00edch."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.2 Semantic States\n\n",
    "- **VALID**: C\u00f3 gi\u00e1 tr\u1ecb h\u1ee3p l\u1ec7.\n",
    "- **MISSING**: Kh\u00f4ng c\u00f3 gi\u00e1 tr\u1ecb.\n",
    "- **INVALID**: C\u00f3 gi\u00e1 tr\u1ecb nh\u01b0ng vi ph\u1ea1m contract.\n",
    "- **SUSPICIOUS**: B\u1ea5t th\u01b0\u1eddng c\u1ea7n review.\n",
    "- **NOT_APPLICABLE**: Kh\u00f4ng \u00e1p d\u1ee5ng."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.3 Field Semantic Contract\n\n",
    "(Tham kh\u1ea3o b\u1ea3ng t\u1ea1i `docs/03_missing_data_semantics.md` cho \u0111\u1ea7y \u0111\u1ee7 15 fields)."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.4 String Missing Representation\n\n",
    "- `title_raw`: 295 NULL, 0 empty, 0 whitespace.\n",
    "- `url`: 0 NULL, 0 empty, 0 whitespace.\n",
    "- `full_address_text`: 91,523 NULL, 0 empty, 0 whitespace.\n",
    "- `location_raw`: 26,881 NULL, 0 empty, 0 whitespace.\n",
    "- `best_address_text`: 26,720 NULL, 0 empty, 0 whitespace.\n",
    "- `best_address_source`: 0 NULL, 0 empty, 0 whitespace."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.5 Numeric Semantic Inspection\n\n",
    "- `price_amount`: 531 NULL, 0 zero, 0 negative.\n",
    "- `area_value`: 483 NULL, 0 zero, 0 negative.\n",
    "- `active_days`: 0 NULL, 91,320 zero, 0 negative. (Zero \u1edf \u0111\u00e2y ho\u00e0n to\u00e0n l\u00e0 VALID, kh\u00f4ng ph\u1ea3i missing hay invalid)."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.6 Address Semantic Relationships\n\n",
    "- `full_address_text`: \u0110\u1ecba ch\u1ec9 \u0111\u01b0\u1eddng b\u00f3c t\u00e1ch.\n",
    "- `location_raw`: Ph\u01b0\u1eddng/x\u00e3/qu\u1eadn b\u00f3c t\u00e1ch.\n",
    "- `best_address_text`: Fallback (tr\u00edch xu\u1ea5t t\u1ed1t nh\u1ea5t) t\u1eeb nhi\u1ec1u tr\u01b0\u1eddng raw (Derived).\n",
    "- `best_address_source`: Metadata k\u00e8m theo."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## 03.7 Limitations\n\n",
    "Kh\u00f4ng th\u1ec3 ph\u00e2n bi\u1ec7t r\u1ea1ch r\u00f2i Raw Missing (b\u00e0i \u0111\u0103ng kh\u00f4ng ghi gi\u00e1) v\u1edbi Parse Failure (crawler l\u1ed7i) ch\u1ec9 b\u1eb1ng field `price_amount` b\u1ecb NULL, v\u00ec trong schema thi\u1ebfu field raw t\u01b0\u01a1ng \u1ee9ng \u0111\u1ec3 \u0111\u1ed1i chi\u1ebfu tr\u1ef1c ti\u1ebfp."
   ]
  }
]

nb['cells'].extend(new_cells)

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

