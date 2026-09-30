import json
with open("notebooks/roombeacon_eda.ipynb", "r") as f:
    nb = json.load(f)
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        print(f"Cell {i} length: {len(cell.get('source', []))}")
        if len(cell.get('source', [])) > 0:
            print("First line:", cell['source'][0])
