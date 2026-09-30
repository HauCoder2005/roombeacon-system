import duckdb
import os
from dotenv import load_dotenv
load_dotenv('.env')

con = duckdb.connect(database=':memory:')
con.execute("INSTALL mysql; LOAD mysql;")
host = '127.0.0.1'
port = os.getenv('BRONZE_MYSQL_HOST_PORT', 3306)
user = os.getenv('BRONZE_MYSQL_USER')
password = os.getenv('BRONZE_MYSQL_PASSWORD')
database = os.getenv('BRONZE_MYSQL_DATABASE')
con.execute(f"ATTACH 'host={host} port={port} user={user} password={password} database={database}' AS mysql_db (TYPE MYSQL, READ_ONLY);")

print(con.execute("SELECT COUNT(*) FROM mysql_db.rental_posts").df())
print(con.execute("SELECT COUNT(*) FROM mysql_db.rental_post_versions").df())
