import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

print("Running BOOTSTRAP...")
bootstrap_code = ""
for i in range(30):
    cell = nb['cells'][i]
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'create_analytics_connection' in source:
            bootstrap_code += source + "\n"

exec(bootstrap_code, globals())
print("Bootstrap connection successful.")

print("Testing query on conn...")
count = conn.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]
print(f"Count: {count}")

