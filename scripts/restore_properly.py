import json

with open("/tmp/original_notebook.ipynb", "r", encoding="utf-8") as f:
    orig = json.load(f)
    
with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    current = json.load(f)

# Just copy cells 0 to 6 from orig to current
for i in range(7):
    current['cells'][i] = orig['cells'][i]

# In the rest of the notebook, replace con.execute with conn.execute
# And remove any `con = duckdb.connect` or `import duckdb` blocks that I injected.
for cell in current['cells'][7:]:
    if cell['cell_type'] == 'code':
        source = cell.get('source', [])
        new_source = []
        skip_cell = False
        for line in source:
            if 'con = duckdb.connect' in line:
                skip_cell = True
            if 'import duckdb' in line and len(source) < 8:
                skip_cell = True
        
        if not skip_cell:
            for line in source:
                line = line.replace('con.execute', 'conn.execute')
                if 'total_rows = 121' in line:
                    line = 'total_rows = conn.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]\n'
                new_source.append(line)
            cell['source'] = new_source
        else:
            cell['source'] = []

# Filter out empty cells
current['cells'] = [c for c in current['cells'] if c.get('source')]

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(current, f, indent=1)
