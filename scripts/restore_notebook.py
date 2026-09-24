import json

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = cell.get('source', [])
        new_source = []
        for line in source:
            # Drop injected connection logic
            if 'import duckdb' in line and not 'from analytics.duckdb' in line:
                if len(source) < 10: # Just a heuristic, if it's my injected block
                    continue
            if 'duckdb.connect' in line:
                continue
            if 'plt.style.use' in line and len(source) < 10:
                continue
                
            # Replace con with conn
            line = line.replace('con.execute', 'conn.execute')
            
            # Replace hardcoded counts
            if 'total_rows = 121' in line:
                line = 'total_rows = conn.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]\n'
            if 'unique_ids = 121' in line:
                line = 'unique_ids = conn.execute("SELECT COUNT(DISTINCT rental_post_id) FROM v_latest_posts").fetchone()[0]\n'
                
            new_source.append(line)
        
        # Clean up empty code cells if they were just injected connection blocks
        cell['source'] = new_source

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
print("Notebook restored")
