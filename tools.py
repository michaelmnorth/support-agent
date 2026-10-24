tools = [
    {
        "name": "get_customer",
        "description": (
            "Look up a customer record by name, email address, or customer ID. "
            "Use this tool when you need to verify who you are speaking with or "
            "retrieve account information. Returns the customer's full profile "
            "including account status, contact details, and a list of their order IDs. "
            "Do not use this tool to look up order details — use lookup_order for that."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search term to find the customer. Can be a full name "
                        "(e.g. 'Sarah Chen'), an email address (e.g. 'sarah@email.com'), "
                        "or a customer ID (e.g. 'CUST-4492')."
                    )
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "lookup_order",
        "description": (
            "Look up a specific order by order ID. Use this tool when you need "
            "details about a particular order — status, items, shipping information, "
            "estimated delivery dates, or notes. Requires a valid order ID. "
            "To find a customer's order IDs, call get_customer first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": (
                        "The order ID to look up. Order IDs follow the format ORD-XXXX "
                        "(e.g. 'ORD-8821'). Must be an exact match."
                    )
                }
            },
            "required": ["order_id"]
        }
    },
    {
        "name": "process_refund",
        "description": (
            "Process a refund to the customer's original payment method. "
            "Requires a verified customer ID and a valid order ID. "
            "Only use this tool after get_customer has successfully confirmed "
            "the customer's identity. Do not call this tool before identity "
            "has been verified — it will fail and you will need to verify first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": (
                        "The verified customer ID returned by get_customer "
                        "(e.g. 'CUST-4492'). Must match the currently verified customer."
                    )
                },
                "order_id": {
                    "type": "string",
                    "description": "The order ID to refund (e.g. 'ORD-8821')."
                },
                "amount": {
                    "type": "number",
                    "description": "The refund amount in USD."
                }
            },
            "required": ["customer_id", "order_id", "amount"]
        }
    }
]
