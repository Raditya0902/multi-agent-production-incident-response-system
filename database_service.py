from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, orders

engine = create_engine('postgresql://user:password@host:port/dbname')
Session = sessionmaker(bind=engine)
session = Session()

def execute_query(query, params):
    result = session.execute(query)
    return result.fetchall()
# Add the missing index to the orders table
Base.metadata.create_all(engine)
# Create the index on the user_id column
from sqlalchemy import Index
Index('idx_orders_user_id', orders.c.user_id).create(engine)