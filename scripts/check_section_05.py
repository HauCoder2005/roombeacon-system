import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'markdown' and '05 \u2014' in "".join(cell.get('source', [])):
        print("--- SECTION 05 ---")
        # Print next 3 code cells
        count = 0
        for j in range(i+1, len(nb['cells'])):
            if nb['cells'][j]['cell_type'] == 'code':
                print("--- CODE ---")
                print("".join(nb['cells'][j]['source']))
                count += 1
                if count >= 3:
                    break
        break
