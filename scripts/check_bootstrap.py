import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'duckdb.connect' in source:
            print("--- BOOTSTRAP CELL ---")
            print(source)
            break
