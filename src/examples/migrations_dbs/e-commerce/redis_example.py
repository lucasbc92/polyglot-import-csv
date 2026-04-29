import redis
import uuid
import json

# Connect to Redis server
redis_host = 'localhost'
redis_port = 6379
redis_password = 'P455w0rd.'
redis_db = 0

redis_client = redis.StrictRedis(host=redis_host, port=redis_port, password=redis_password, db=redis_db)

# Sample shopping cart data
cart_data = {
    "user_id": str(uuid.uuid4()),
    "items": [
        {"product_id": 1, "quantity": 2},
        {"product_id": 2, "quantity": 1}
    ]
}

# Convert cart data to JSON string
cart_json = json.dumps(cart_data)

# Save cart data in Redis
redis_key = f"user:{cart_data['user_id']}:cart"
redis_client.set(redis_key, cart_json)

# Retrieve cart data from Redis
saved_cart_json = redis_client.get(redis_key)

# Parse JSON string back to dictionary
saved_cart_data = json.loads(saved_cart_json)

print("Saved Cart Data:")
print(saved_cart_data)