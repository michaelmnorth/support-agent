# tool_runner.py

import json
# Import mock datasets that simulate a database
from mock_data import CUSTOMERS, ORDERS

def process_refund(customer_id: str, order_id: str, amount: float,
                   session_state: dict) -> str:

    # Gate check 1: Has identity verification happened at all?
    # session_state["verified_customer_id"] is None until get_customer
    # runs successfully. If it's still None, the conversation hasn't
    # gone through verification and we block unconditionally.
    if not session_state.get("verified_customer_id"):
        return json.dumps({
            "error": {
                "type": "permission",
                "retryable": False,
                "message": (
                    "Cannot process a refund before customer identity has been "
                    "verified. Call get_customer first and confirm the customer's "
                    "identity before attempting a refund."
                )
            }
        })

    # Gate check 2: Does the customer_id Claude is trying to refund
    # match the customer who was actually verified in this session?
    # This prevents a subtle but serious bug: if Claude somehow has the
    # wrong customer_id — from a previous message, a misread, or anything
    # else — this check catches it before money moves.
    if customer_id != session_state["verified_customer_id"]:
        return json.dumps({
            "error": {
                "type": "permission",
                "retryable": False,
                "message": (
                    f"Customer ID mismatch. The verified customer in this session is "
                    f"{session_state['verified_customer_id']} but the refund request "
                    f"is for {customer_id}. Do not process this refund. Verify you "
                    f"have the correct customer before continuing."
                )
            }
        })

    # Both gates passed. Now do the actual work.

    # Check the order exists before attempting the refund
    if order_id not in ORDERS:
        return json.dumps({
            "error": {
                "type": "validation",
                "retryable": False,
                "message": (
                    f"Order {order_id} not found. Verify the order ID with the "
                    "customer and try again."
                )
            }
        })

    # Verify the order belongs to the verified customer.
    # Without this check, a verified customer could potentially
    # request a refund on someone else's order ID.
    order = ORDERS[order_id]
    if order["customer_id"] != session_state["verified_customer_id"]:
        return json.dumps({
            "error": {
                "type": "permission",
                "retryable": False,
                "message": (
                    f"Order {order_id} does not belong to the verified customer. "
                    "Do not process this refund."
                )
            }
        })

    # All checks passed — simulate the refund
    return json.dumps({
        "success": True,
        "refund_id": "REF-" + order_id.split("-")[1],
        "customer_id": customer_id,
        "order_id": order_id,
        "amount": amount,
        "status": "initiated",
        "message": (
            f"Refund of ${amount:.2f} for order {order_id} has been initiated. "
            "Funds will return to the original payment method within 3-5 business days."
        )
    })

# Fetch a customer by matching against multiple possible identifiers
def get_customer(query: str, session_state: dict) -> str:
    query = query.strip().lower()

    for customer in CUSTOMERS.values():
        if (
            query == customer["customer_id"].lower()
            or query == customer["email"].lower()
            or query == customer["name"].lower()
        ):
            # Write verified identity into session state before returning.
            # This is what downstream gates check — if these values are set,
            # it means this function ran successfully and found a real customer.
            session_state["verified_customer_id"] = customer["customer_id"]
            session_state["verified_customer_name"] = customer["name"]

            return json.dumps(customer)

    return json.dumps({
        "error": {
            "type": "validation",
            "retryable": False,
            "message": (
                f"No customer found matching '{query}'. The input may be "
                "misspelled or in the wrong format. Customer IDs follow the "
                "format CUST-XXXX. You can also search by full name or "
                "email address. Ask the customer to verify their details."
            )
        }
    })


# Fetch an order using its order ID
def lookup_order(order_id: str, session_state: dict) -> str:
    order_id = order_id.strip().upper()

    if order_id in ORDERS:
        return json.dumps(ORDERS[order_id])

    return json.dumps({
        "error": {
            "type": "validation",
            "retryable": False,
            "message": (
                f"No order found with ID '{order_id}'. "
                "Please check the order ID and try again."
            )
        }
    })

def run_tool(tool_name: str, tool_input: dict, session_state: dict) -> str:
    if tool_name == "get_customer":
        return get_customer(tool_input["query"], session_state)
    elif tool_name == "lookup_order":
        return lookup_order(tool_input["order_id"], session_state)
    elif tool_name == "process_refund":
        return process_refund(
            tool_input["customer_id"],
            tool_input["order_id"],
            tool_input["amount"],
            session_state
        )
    else:
        return json.dumps({
            "error": {
                "type": "validation",
                "retryable": False,
                "message": f"Tool '{tool_name}' is not recognised."
            }
        })