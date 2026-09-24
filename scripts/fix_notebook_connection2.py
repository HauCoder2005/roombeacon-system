import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = cell.get('source', [])
        for i, line in enumerate(source):
            if 'total_rows = 121460' in line:
                source[i] = 'total_rows = con.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]\n'
            if 'unique_ids = 121460' in line:
                source[i] = 'unique_ids = con.execute("SELECT COUNT(DISTINCT rental_post_id) FROM v_latest_posts").fetchone()[0]\n'

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
