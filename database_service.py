from sqlalchemy import Index
from sqlalchemy import MetaData
metadata = MetaData()
index = Index('ix_orders_user_id', 'user_id')
index.create(session.bind)
result = session.execute(query)