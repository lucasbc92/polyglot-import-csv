import uuid

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from datetime import datetime

# Sample log entry
log_entry = {
    "timestamp": "2023-11-03T14:45:30Z",
    "user_id": uuid.uuid4(),
    "action": "purchase",
    "product_id": 1,
    "quantity": 2,
    "unit_price": 49.99,
    "payment_method": "credit_card",
    "shipping_address": {
        "street": "456 Elm St",
        "neighborhood": "Heaven",
        "city": "Anytown",
        "state": "CA",
        "zip_code": "54321"
    }
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

# Create user-defined type (UDT) for shipping_address
create_udt_query = """
    CREATE TYPE IF NOT EXISTS local.shipping_address (
        street TEXT,
        neighborhood TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT
    )
"""
session.execute(create_udt_query)
cluster.register_user_type('local', 'shipping_address', dict)

create_table_query = """
    CREATE TABLE IF NOT EXISTS local.purchase_log (
    timestamp TIMESTAMP,
    user_id UUID,
    action TEXT,
    product_id INT,
    quantity INT,
    unit_price DECIMAL,
    payment_method TEXT,
    shipping_address FROZEN<local.shipping_address>,
    PRIMARY KEY (timestamp, user_id, action)
);
"""

session.execute(create_table_query)

# Insert log entry into Cassandra
insert_query = session.prepare("""
    INSERT INTO local.purchase_log (timestamp, user_id, action, product_id, quantity, unit_price, payment_method, shipping_address)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""")

# Convert log entry to appropriate data types
timestamp = datetime.strptime(log_entry['timestamp'], "%Y-%m-%dT%H:%M:%SZ")
shipping_address = tuple(log_entry["shipping_address"].values())

insert_query_bound = insert_query.bind([
    timestamp,
    log_entry['user_id'],
    log_entry['action'],
    log_entry['product_id'],
    log_entry['quantity'],
    log_entry['unit_price'],
    log_entry['payment_method'],
    shipping_address
])

session.execute(insert_query_bound)

# Close Cassandra connection
session.shutdown()
cluster.shutdown()
