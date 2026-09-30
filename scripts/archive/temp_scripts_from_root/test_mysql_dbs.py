import os
import pymysql
from dotenv import load_dotenv

load_dotenv('.env')

connection = pymysql.connect(
    host='127.0.0.1',
    user=os.getenv('BRONZE_MYSQL_USER'),
    password=os.getenv('BRONZE_MYSQL_PASSWORD'),
    port=int(os.getenv('BRONZE_MYSQL_HOST_PORT', 3306))
)

with connection.cursor() as cursor:
    cursor.execute("SHOW DATABASES;")
    for row in cursor.fetchall():
        print(row[0])
