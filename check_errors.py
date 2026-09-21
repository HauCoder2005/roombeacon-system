from sqlalchemy import create_engine
import pandas as pd
engine = create_engine("mysql+pymysql://root:root@mysql-bronze:3306/roombeacon_bronze")
with engine.connect() as conn:
    print("Recent Crawl Runs:")
    runs = pd.read_sql("SELECT source, target_id, start_time, end_time, status, items_discovered, items_processed, items_failed, error_message FROM crawl_runs ORDER BY start_time DESC LIMIT 15", conn)
    print(runs.to_string())
