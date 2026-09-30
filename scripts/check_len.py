import json
with open("/tmp/original_notebook.ipynb", "r") as f:
    nb = json.load(f)
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] == "code":
        source = "".join(cell.get("source", []))
        if "create_analytics_connection" in source:
            print(f"Cell {i} length: {len(cell.get('source', []))}")
