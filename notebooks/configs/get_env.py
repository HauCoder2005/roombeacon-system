import os
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

def get_db_url() -> str:
    return os.getenv("BRONZE_DATABASE_URL", "")