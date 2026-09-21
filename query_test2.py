from sqlalchemy import create_engine
engine = create_engine("mysql+pymysql://codeser_server:codeser_server@mysql-bronze:3306/roombeacon_bronze")
with engine.connect() as conn:
    print("Rental Posts:", conn.execute("SELECT COUNT(*) FROM rental_posts").scalar())
    print("Post Details:", conn.execute("SELECT COUNT(*) FROM post_details").scalar())
    print("Post Addresses:", conn.execute("SELECT COUNT(*) FROM post_addresses").scalar())
