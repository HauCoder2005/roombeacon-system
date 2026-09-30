import duckdb
con = duckdb.connect('/tmp/copy.duckdb', read_only=True)
views = con.execute("SELECT view_name, sql FROM duckdb_views() WHERE schema_name='main'").fetchall()
for v in views:
    print(f"\nVIEW {v[0]}:")
    print(v[1])
