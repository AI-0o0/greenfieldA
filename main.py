import asyncio
import sys

from agent.agent import run_agent
from client.client import create_client


mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"


async def main():
    async with create_client() as client:
        await client.list_tools()

        print("===================================")
        print("GREENFIELD Support Agent")
        print("Type 'exit' to quit")
        print("===================================\n")

        # Temporary single-session user
        user_id = "default_user"

        while True:
            user_input = input("User: ").strip()

            if user_input.lower() == "exit":
                print("Goodbye!")
                break

            step = await run_agent(
                client=client,
                user_input=user_input,
                user_id=user_id,
            )

            if step and step.action == "end_conversation":
                print("Conversation ended.")
                break


if __name__ == "__main__":
    asyncio.run(main())