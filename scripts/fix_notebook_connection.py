import json
import re

with open("notebooks/roombeacon_eda.ipynb", "r", encoding="utf-8") as f:
    nb = json.load(f)

# Find bootstrap connection
bootstrap_found = False
for cell in nb['cells']:
    if cell['cell_type'] == 'code':
        source = "".join(cell.get('source', []))
        if 'duckdb.connect' in source and 'roombeacon_analytics.duckdb' in source:
            print("Found canonical connection in early cell:")
            print(source[:200])
            bootstrap_found = True
            break

duplicate_connects = 0
sections_modified = set()
hard_coded_counts_removed = 0

current_section = "00"

for cell in nb['cells']:
    if cell['cell_type'] == 'markdown':
        source = "".join(cell.get('source', []))
        # track section
        m = re.search(r'#\s*(\d+)', source)
        if m:
            current_section = m.group(1)
            
    if cell['cell_type'] == 'code':
        source_lines = cell.get('source', [])
        new_source = []
        modified = False
        
        # We only want to remove duckdb.connect if we already have the bootstrap,
        # but wait, let's just look for lines containing `duckdb.connect` inside cells after section 01.
        
        if int(current_section) >= 5:
            i = 0
            while i < len(source_lines):
                line = source_lines[i]
                
                # Check for duckdb.connect
                if 'duckdb.connect' in line and 'read_only' in line:
                    duplicate_connects += 1
                    modified = True
                    sections_modified.add(current_section)
                    # skip this line
                    # if it's a multi-line connect, skip next lines too
                    while i < len(source_lines) and not line.strip().endswith(')'):
                        i += 1
                        line = source_lines[i]
                        modified = True
                    i += 1
                    continue
                    
                if 'total_rows = ' in line and ('121687' in line or '121913' in line or '121' in line):
                    # Replace hard-coded total rows
                    new_source.append('total_rows = con.execute("SELECT COUNT(*) FROM v_latest_posts").fetchone()[0]\n')
                    hard_coded_counts_removed += 1
                    modified = True
                    sections_modified.add(current_section)
                    i += 1
                    continue
                    
                new_source.append(line)
                i += 1
                
        else:
            new_source = source_lines
            
        if modified:
            cell['source'] = new_source

print(f"Duplicates removed: {duplicate_connects}")
print(f"Sections modified: {list(sections_modified)}")
print(f"Hard-coded counts removed: {hard_coded_counts_removed}")

with open("notebooks/roombeacon_eda.ipynb", "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
