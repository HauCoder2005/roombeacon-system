import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for i in range(max(0, 27-2), 29):
    cell = nb['cells'][i]
    print(f"--- Cell {i} ({cell['cell_type']}) ---")
    print("".join(cell.get('source', []))[:200])
