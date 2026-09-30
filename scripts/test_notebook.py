import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

print("Running BOOTSTRAP cells (0-4)...")
for i in range(5): # cells 0 to 4 contain bootstrap imports
    cell = nb['cells'][i]
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        try:
            exec(source, globals())
        except Exception as e:
            print(f"Error in cell {i}: {e}")

print("Checking connection...")
try:
    count = conn.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]
    print(f"Current Runtime Row Count: {count}")
except Exception as e:
    print(f"Connection failed: {e}")

print("Running Section 05 start...")
for i in range(27, 29): # Section 05 first cells
    cell = nb['cells'][i]
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        try:
            exec(source, globals())
            print("Section 05 executed PASS")
        except Exception as e:
            print(f"Error in Section 05 cell: {e}")

print("Testing a query from later section...")
try:
    df = conn.execute("SELECT COUNT(*) as test_count FROM v_latest_posts").df()
    print("Later query PASS:", df.iloc[0]['test_count'])
except Exception as e:
    print(f"Later section query failed: {e}")

print("Done.")
