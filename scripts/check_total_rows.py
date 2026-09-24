import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'total_rows =' in source:
            print(f"--- Cell {i} ---")
            print(source)
