import os
import sys

# Fake env for the test
os.environ["BRONZE_MYSQL_HOST"] = "mysql-bronze"
os.environ["BRONZE_MYSQL_PORT"] = "3306"
os.environ["BRONZE_MYSQL_USER"] = "root"
os.environ["BRONZE_MYSQL_PASSWORD"] = "root"
os.environ["BRONZE_MYSQL_DATABASE"] = "roombeacon_bronze"
os.environ["ENVIRONMENT"] = "development"
os.environ["AIRFLOW_HOME"] = "/opt/airflow"
os.environ["PYTHONPATH"] = "/home/codeser_server/Data/projects/roombeacon/source/roombeacon-system/crawler/src"
sys.path.append(os.environ["PYTHONPATH"])

from roombeacon_crawler.infrastructure.mysql.schema import ensure_mysql_schema
try:
    ensure_mysql_schema()
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
