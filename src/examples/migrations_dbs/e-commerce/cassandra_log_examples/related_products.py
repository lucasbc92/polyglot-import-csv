from datetime import datetime
import uuid
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

product_jeggings = {
  'product_id': 'SKU_123',
  'product_name': 'jeggings',
  'product_category': 'pants',
  'product_variant': 'black',
  'product_brand': 'Google',
  'price': 9.99
}

product_boots = {
  'product_id': 'SKU_456',
  'product_name': 'boots',
  'product_category': 'shoes',
  'product_variant': 'brown',
  'product_brand': 'Google',
  'price': 24.99
}

product_socks = {
  'product_id': 'SKU_789',
  'product_name': 'ankle_socks',
  'product_category': 'socks',
  'product_variant': 'red',
  'product_brand': 'Google',
  'price': 5.99
}

log_entry_select = {
    'timestamp': '2023-11-03T15:46:30Z',
    'user_id': uuid.UUID("ecc69d51-da34-4b5b-b89c-c8df997242da"),
    'action': 'select_product',
    'products': [product_jeggings, product_boots, product_socks],
    'selected_product': product_jeggings
}

# Cassandra connection details
cassandra_host = 'localhost'
cassandra_port = 9042
cassandra_username = 'picsv'
cassandra_password = 'P455w0rd.'

# Establish Cassandra connection
auth_provider = PlainTextAuthProvider(username=cassandra_username, password=cassandra_password)
cluster = Cluster([cassandra_host], port=cassandra_port, auth_provider=auth_provider)
session = cluster.connect()

# Create keyspace 'local'
create_keyspace_query = """
    CREATE KEYSPACE IF NOT EXISTS local
    WITH replication = {
      'class': 'SimpleStrategy',
      'replication_factor': 3
    }
"""
session.execute(create_keyspace_query)
# Set the keyspace for the session
session.set_keyspace('local')

# Create user-defined type (UDT) for product
create_udt_query = """
    CREATE TYPE IF NOT EXISTS local.product (
        product_id TEXT,
        product_name TEXT,
        product_category TEXT,
        product_variant TEXT,
        product_brand TEXT,
        price DECIMAL
    )
"""
session.execute(create_udt_query)
cluster.register_user_type('local', 'product', dict)

create_table_query = """
    CREATE TABLE IF NOT EXISTS local.product_list_log (
        timestamp TIMESTAMP,
        user_id UUID,
        action TEXT,
        products FROZEN<list<product>>,
        selected_product FROZEN<product>,
        PRIMARY KEY (timestamp, user_id, action)
    );
"""

session.execute(create_table_query)

# Insert log entry into Cassandra
insert_query = session.prepare("""
    INSERT INTO local.product_list_log (timestamp, user_id, action, products, selected_product)
    VALUES (?, ?, ?, ?, ?)
""")

# Convert log entry to appropriate data types
timestamp = datetime.strptime(log_entry_select['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
products = [tuple(product.values()) for product in log_entry_select["products"]]
selected_product = tuple(log_entry_select["selected_product"].values())

insert_query_bound = insert_query.bind([
    timestamp,
    log_entry_select['user_id'],
    log_entry_select['action'],
    products,
    selected_product
])

session.execute(insert_query_bound)

# Close Cassandra connection
session.shutdown()
cluster.shutdown()
