import json
import duckdb

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

# Combine code cells for Section 01
code_to_run = ""
for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'duckdb.connect' in source:
            code_to_run += source + "\n"
            break # Just need the bootstrap

print("Running bootstrap...")
# Execute the python code in the current context
exec(code_to_run, globals())

print("Testing query...")
count = con.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]
print(f"Count: {count}")

print("Testing Section 05 logic...")
# Section 05 logic
df_missing_summary = con.execute("""
    SELECT 
        COUNT(*) as total_rows,
        SUM(CASE WHEN full_address_text IS NULL THEN 1 ELSE 0 END) as missing_full_address,
        SUM(CASE WHEN location_raw IS NULL THEN 1 ELSE 0 END) as missing_location,
        SUM(CASE WHEN price_amount IS NULL THEN 1 ELSE 0 END) as missing_price
    FROM v_latest_posts
""").df()
print(df_missing_summary)

print("Testing Section 08 logic...")
# test random logic
con.execute("SELECT COUNT(*) FROM v_latest_posts").df()
print("Success!")
