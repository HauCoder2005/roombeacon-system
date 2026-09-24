import json
with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        print(f"Cell {i}:")
        print("".join(cell.get('source', []))[:100])
