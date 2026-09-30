import json
with open("/tmp/original_notebook.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)
for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'create_analytics_connection' in source:
            for j in range(i+1, len(nb['cells'])):
                if nb['cells'][j]['cell_type'] == 'code':
                    print("--- NEXT CODE CELL ---")
                    print("".join(nb['cells'][j].get('source', [])))
                    break
            break
