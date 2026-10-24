# agent.py

# Load environment variables (e.g., API keys from .env file)
from dotenv import load_dotenv
# Official Anthropic client for interacting with Claude models
from anthropic import Anthropic
# Tool definitions (what Claude is allowed to use)
from tools import tools
# Local execution layer for actually running tools
from tool_runner import run_tool

# Load environment variables into the runtime
load_dotenv()

# Initialize Anthropic client
client = Anthropic()

# System prompt defines the agent's behavior, constraints, and workflow
SYSTEM_PROMPT = """You are a customer support agent for an online retailer.
You have access to tools that let you look up customer records and order details.

When a customer contacts you:
1. Look up their account using get_customer before doing anything else.
2. Use lookup_order to get details on any specific order they mention.
3. Give clear, helpful responses based on what you find.
4. If you cannot find a customer or order, tell them politely and ask them
   to double-check the information they provided.

Always verify who you are speaking with before discussing account details."""


# Core agent loop: takes a user message and returns a final response
def run_agent(user_message: str) -> str:
    conversation_history = [
        {"role": "user", "content": user_message}
    ]

    # Session state tracks verified identity and anything else
    # that needs to persist across tool calls within this conversation.
    # It starts empty and gets populated as tools run successfully.
    session_state = {
        "verified_customer_id": None,
        "verified_customer_name": None
    }

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=conversation_history
        )

        conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return ""

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    # session_state gets passed into every tool call
                    result = run_tool(block.name, block.input, session_state)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            conversation_history.append({
                "role": "user",
                "content": tool_results
            })


# Entry point for running the agent in a CLI loop
if __name__ == "__main__":
    print("Customer Support Agent, Stage 1")
    print("Type 'quit' to exit")
    print("=" * 40)

    while True:
        # Read user input from terminal
        user_input = input("\nCustomer: ").strip()

        # Ignore empty input
        if not user_input:
            continue

        # Exit conditions
        if user_input.lower() in ("quit", "exit", "q"):
            break

        # Run the agent (tool calls print as they happen), then print its reply
        response = run_agent(user_input)
        print("\nAgent:", response)