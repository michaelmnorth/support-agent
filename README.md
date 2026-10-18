# Customer Support Agent

A command-line customer support agent for an online retailer, built on Claude with the Anthropic Python SDK.

You type a message as a customer. Claude decides which lookups to run, calls the tools to fetch customer and order records, and answers from what it finds. Each tool call and its result prints in the terminal, so you can follow each step the agent takes.

## Example

```
Customer: Hi, I'm Sarah Chen (sarah.chen@email.com). What's the status of order ORD-8821?

  [tool call]   get_customer({'query': 'sarah.chen@email.com'})
  [tool result] {"customer_id": "CUST-4492", "name": "Sarah Chen", ...}

  [tool call]   lookup_order({'order_id': 'ORD-8821'})
  [tool result] {"order_id": "ORD-8821", "status": "processing", ...}

Agent: Hi Sarah! I've verified your account and pulled up your order...
```

## How it works

The agent runs a tool-use loop:

1. The customer's message goes to Claude along with a system prompt and the available tools.
2. If Claude asks for a tool, the agent runs it locally and sends the result back.
3. This repeats until Claude has what it needs and writes its final reply.

The system prompt tells Claude to verify the customer's identity before discussing account details, and to ask politely for corrected information when a customer or order can't be found.

## Tools

| Tool | What it does |
|------|--------------|
| `get_customer` | Finds a customer by name, email, or customer ID. Returns their profile and a list of their order IDs. |
| `lookup_order` | Finds an order by ID (e.g. `ORD-8821`). Returns status, items, shipping details, and notes. |

The data comes from sample records in `mock_data.py`, not a real database.

## Project structure

| File | Purpose |
|------|---------|
| `agent.py` | The agent loop, system prompt, and command-line interface |
| `tools.py` | Tool definitions Claude sees: names, descriptions, input schemas |
| `tool_runner.py` | Runs each tool against the data and returns JSON |
| `mock_data.py` | Sample customers and orders |

## Setup

1. Install the dependencies:

   ```
   pip install anthropic python-dotenv
   ```

2. Create a `.env` file in the project folder with your Anthropic API key:

   ```
   ANTHROPIC_API_KEY=your-key-here
   ```

   `.env` is listed in `.gitignore`, so your key is never committed.

3. Run the agent:

   ```
   python agent.py
   ```

   Type `quit` to exit.

## Test cases

The sample data includes a few situations worth trying:

- **Normal lookup:** Sarah Chen asking about `ORD-8821`, an order delayed for an inventory check.
- **Missing order:** `ORD-7103` is on Sarah's account but has no order record.
- **Mismatched owner:** `ORD-9999` belongs to customer `CUST-9999`, who doesn't exist.
- **No orders:** James Okafor (`james.okafor@email.com`) has no orders listed.
