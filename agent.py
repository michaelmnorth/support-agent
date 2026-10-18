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
    # Initialize conversation history with the user's first message
    conversation_history = [
        {"role": "user", "content": user_message}
    ]

    # Loop until Claude finishes the interaction
    while True:
        # Send current state (history + tools + system prompt) to Claude
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=conversation_history
        )

        # Always append Claude's response immediately
        # This preserves the full chain: assistant → tool call → tool result → next turn
        conversation_history.append({
            "role": "assistant",
            "content": response.content
        })

        # If Claude has finished responding (no more tool calls needed)
        if response.stop_reason == "end_turn":
            # Extract and return the text response from content blocks
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            # Fallback in case no text block is found
            return ""

        # If Claude wants to use tools
        if response.stop_reason == "tool_use":
            tool_results = []

            # Iterate through all tool_use blocks (Claude may call multiple tools at once)
            for block in response.content:
                if block.type == "tool_use":
                    # Show which tool Claude chose and what it passed in
                    print(f"\n  [tool call]   {block.name}({block.input})")

                    # Execute the tool locally with provided inputs
                    result = run_tool(block.name, block.input)

                    # Show what the tool sent back to Claude
                    print(f"  [tool result] {result}")

                    # Collect tool results in the required format
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,  # Links result to specific tool call
                        "content": result
                    })

            # Send all tool results back in a single user message
            # This allows Claude to continue reasoning with fresh data
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