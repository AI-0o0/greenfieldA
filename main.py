import asyncio
import sys

from agent.agent import agent_step
from memory.memory import ShortTermMemory, LongTermMemory
from client.client import create_client 


# Parse transport mode from CLI args (default to stdio)
MODE = sys.argv[1] if len(sys.argv) > 1 else "stdio"

# Initialize long-term and short-term memory
long_term = LongTermMemory()
memory = ShortTermMemory(max_turns=20, long_term_memory=long_term)

async def main():
    async with create_client(mode=MODE) as client:
        # Pre-warm or discover client capabilities
        await client.list_tools()

        print("===================================")
        print("GREENFIELD Support Agent")
        print("Type 'exit' to quit")
        print("===================================\n")

        user_id = "default_user"

        while True:
            try:
                # Non-blocking input to allow asyncio event loop processing
                user_input = await asyncio.to_thread(input, "User: ")
                user_input = user_input.strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_input:
                continue

            if user_input.lower() == "exit":
                print("Goodbye!")
                break

            step = await agent_step(
                client=client,
                user_input=user_input,
                memory=memory,
            )

            if not step:
                print("Agent: I encountered an issue processing that request.\n")
                continue

            # Output the agent's answer if a terminal state was reached
            if step.action == "final_answer":
                answer = step.action_input.get("answer") if isinstance(step.action_input, dict) else step.action_input
                print(f"Agent: {answer}\n")
            elif step.action == "escalate":
                print("Agent: Escalating this issue to a human support representative.\n")
            
            if step.action in ("end_conversation", "escalate"):
                print("Conversation ended.")
                break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted. Exiting...")