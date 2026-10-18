# mock_data.py

CUSTOMERS = {
    "CUST-4492": {
        "customer_id": "CUST-4492",
        "name": "Sarah Chen",
        "email": "sarah.chen@email.com",
        "account_status": "active",
        "member_since": "2021-03-14",
        "total_orders": 12,
        "orders": ["ORD-8821", "ORD-7103", "ORD-6897"]
    },
    "CUST-2201": {
        "customer_id": "CUST-2201",
        "name": "James Okafor",
        "email": "james.okafor@email.com",
        "account_status": "active",
        "member_since": "2023-07-22",
        "total_orders": 1,
        "orders": []
    }
}

ORDERS = {
    "ORD-8821": {
        "order_id": "ORD-8821",
        "customer_id": "CUST-4492",
        "status": "processing",
        "items": [
            {"product": "Wireless Keyboard", "quantity": 1, "price": 79.99}
        ],
        "placed_at": "2024-01-08T14:23:00Z",
        "estimated_ship_date": "2024-01-12T00:00:00Z",
        "actual_ship_date": None,
        "carrier": None,
        "tracking_number": None,
        "notes": "Item held for warehouse inventory check. Expected to resolve within 24-48 hours."
    },
    "ORD-9999": {
        "order_id": "ORD-9999",
        "customer_id": "CUST-9999",
        "status": "delivered",
        "items": [
            {"product": "USB-C Hub", "quantity": 2, "price": 34.99}
        ],
        "placed_at": "2024-01-01T09:00:00Z",
        "estimated_ship_date": "2024-01-03T00:00:00Z",
        "actual_ship_date": "2024-01-03T11:42:00Z",
        "carrier": "FedEx",
        "tracking_number": "FX-442819203",
        "notes": None
    }
}