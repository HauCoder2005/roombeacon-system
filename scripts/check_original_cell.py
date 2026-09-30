import json

with open("/tmp/original_notebook.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'create_analytics_connection' in source:
            print("--- ORIGINAL CONNECTION CELL ---")
            print(source)
            break
