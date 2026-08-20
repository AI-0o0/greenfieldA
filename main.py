import asyncio
import sys
import os

from agent.agent import (
    agent_step,
    get_base_llm,
    execute_subtask_with_algorithm,
)
from memory.memory import ShortTermMemory, LongTermMemory
from memory.consolidation import SemanticConsolidator
from client.client import create_client
from algorithms.environment import GreenfieldEnvironment
from algorithms.decomposition import decompose_goal, execute_plan, final_output


# Parse transport mode from CLI args (default to stdio)
MODE = sys.argv[1] if len(sys.argv) > 1 else "stdio"

# Initialize long-term and short-term memory
long_term = LongTermMemory()
memory = ShortTermMemory(max_turns=2, long_term_memory=long_term)
# Initialize the semantic consolidator
consolidator = SemanticConsolidator(long_term)


def print_algorithms_menu():
    print("""
================================================================================
           GREENFIELD AGENTIC PLANNING & REASONING ALGORITHMS
================================================================================
All 7 repository algorithms are available for direct execution and evaluation:

1. Static DAG Decomposition:
   Command: /plan <goal>  (or /dag <goal>)
   Desc   : Decomposes goal into a validated DAG and executes nodes in parallel.

2. Dynamic Adaptive Decomposition:
   Command: /dynamic <goal>
   Desc   : Step-by-step adaptive loop: decides next sub-task from past observations.

3. Plan-and-Solve (PS):
   Command: /ps <question>
   Desc   : Zero-shot 2-stage planning prompt (devises plan, then executes step-by-step).

4. Tree-of-Thoughts (ToT):
   Command: /tot <problem>
   Desc   : Multi-branch beam search generating distinct thoughts with scoring.

5. Language Agent Tree Search (LATS):
   Command: /lats <task>
   Desc   : Monte Carlo tree search with value estimation & Greenfield environment feedback.

6. Reflexion:
   Command: /reflexion <task>
   Desc   : Multi-trial self-correction with episodic memory & environment feedback.

7. Self-Refine:
   Command: /refine <goal> [| <draft>]
   Desc   : Iterative refinement using deterministic checks + independent critic.

Or type any standard natural language request to run the full Autonomous Support Agent.
Type 'exit' to quit.
================================================================================
""")


async def handle_algorithm_command(user_input: str) -> bool:
    """
    Checks if the user requested a direct planning algorithm command and executes it.
    Routes execution through the centralized execute_subtask_with_algorithm router.
    Returns True if handled, False otherwise.
    """
    cmd = user_input.strip()
    llm = get_base_llm()
    env = GreenfieldEnvironment()

    if cmd.lower() in ("/algorithms", "/help", "help", "algorithms"):
        print_algorithms_menu()
        return True

    # 1. Static DAG Decomposition (/plan or /dag)
    if cmd.startswith("/plan ") or cmd.startswith("/dag "):
        goal = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 1: Static DAG Decomposition for Goal]: '{goal}'")
        try:
            plan = decompose_goal(goal=goal, llm=llm)
            print(f"\nGenerated DAG Plan with {len(plan.tasks)} tasks:")
            for t in plan.tasks:
                deps = f"(depends on: {', '.join(t.depends_on)})" if t.depends_on else "(root parallel)"
                print(f"  [{t.id}] {t.instruction} {deps}")
            print("\nExecuting tasks in topological batches...")
            outputs = execute_plan(plan=plan, llm=llm, max_workers=4)
            for tid, out in outputs.items():
                print(f"\n--- Output of [{tid}] ---:\n{out}")
            synthesis = final_output(plan=plan, outputs=outputs)
            print(f"\n=== Final Synthesized Output ===\n{synthesis}\n")
        except Exception as e:
            print(f"[Decomposition Error]: {e}\n")
        return True

    # 2. Dynamic Adaptive Decomposition (/dynamic)
    if cmd.startswith("/dynamic "):
        goal = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 2: Dynamic Adaptive Decomposition for Goal]: '{goal}'")
        try:
            history = await execute_subtask_with_algorithm(
                task_instruction=goal,
                method="dynamic_decomposition",
                llm=llm,
                max_steps=4,
            )
            print(f"\nDynamic Loop Completed in {len(history)} steps:")
            for i, (task, res) in enumerate(history, 1):
                print(f"\n[Step {i}] Next Task: {task}")
                print(f"[Step {i}] Execution Result:\n{res}")
            print("\n=== Dynamic Decomposition Finished ===\n")
        except Exception as e:
            print(f"[Dynamic Decomposition Error]: {e}\n")
        return True

    # 3. Plan-and-Solve (/ps)
    if cmd.startswith("/ps "):
        question = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 3: Plan-and-Solve Prompting for Question]: '{question}'")
        try:
            output = await execute_subtask_with_algorithm(
                task_instruction=question,
                method="plan_and_solve",
                llm=llm,
            )
            print(f"\n=== Plan-and-Solve Output ===\n{output}\n")
        except Exception as e:
            print(f"[Plan-and-Solve Error]: {e}\n")
        return True

    # 4. Tree-of-Thoughts (/tot)
    if cmd.startswith("/tot "):
        problem = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 4: Tree-of-Thoughts Beam Search for Problem]: '{problem}'")
        try:
            thoughts = await execute_subtask_with_algorithm(
                task_instruction=problem,
                method="tree_of_thoughts",
                llm=llm,
                depth=2,
                beam_width=2,
            )
            print(f"\nExplored {len(thoughts)} frontier thought paths:")
            for i, t in enumerate(thoughts, 1):
                print(f"\n[Path {i}] (Score: {t.score:.2f}) Rationale: {t.rationale}")
                print(f"Candidate State:\n{t.state}")
            print(f"\n=== Best Selected Thought (Score {thoughts[0].score:.2f}) ===\n{thoughts[0].state}\n")
        except Exception as e:
            print(f"[Tree-of-Thoughts Error]: {e}\n")
        return True

    # 5. Language Agent Tree Search (/lats)
    if cmd.startswith("/lats "):
        task = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 5: Language Agent Tree Search (LATS) for Task]: '{task}'")
        try:
            result = await execute_subtask_with_algorithm(
                task_instruction=task,
                method="lats",
                llm=llm,
                environment=env,
                iterations=2,
                n_actions=2,
            )
            print(f"\nLATS Search Result: Success={result.success} | Best Score={result.best_score:.4f} | Iterations={result.iterations}")
            print(f"\n=== Selected Solution ===\n{result.output}\n")
        except Exception as e:
            print(f"[LATS Error]: {e}\n")
        return True

    # 6. Reflexion (/reflexion)
    if cmd.startswith("/reflexion "):
        task = cmd.split(" ", 1)[1].strip()
        print(f"\n[Running Algorithm 6: Reflexion Self-Correction Loop for Task]: '{task}'")
        try:
            result = await execute_subtask_with_algorithm(
                task_instruction=task,
                method="reflexion",
                llm=llm,
                environment=env,
                max_trials=3,
                memory_size=3,
            )
            print(f"\nReflexion Search Result: Success={result.success} across {len(result.trials)} trial(s)")
            for t in result.trials:
                print(f"\n--- Trial #{t.number} ---")
                print(f"Attempt: {t.attempt[:120]}...")
                print(f"Feedback Score: {t.feedback.score} (Success: {t.feedback.success})")
                if t.feedback.details:
                    print(f"Feedback Details: {t.feedback.details}")
                if t.reflection:
                    print(f"Episodic Reflection Learned: {t.reflection}")
            print(f"\n=== Best Converged Deliverable ===\n{result.output}\n")
        except Exception as e:
            print(f"[Reflexion Error]: {e}\n")
        return True

    # 7. Self-Refine (/refine)
    if cmd.startswith("/refine "):
        raw = cmd.split(" ", 1)[1].strip()
        if "|" in raw:
            goal, draft = raw.split("|", 1)
            goal, draft = goal.strip(), draft.strip()
        else:
            goal = raw
            draft = f"Initial brief schedule plan for {goal}."

        print(f"\n[Running Algorithm 7: Self-Refine for Goal]: '{goal}'")
        print(f"Initial Draft:\n{draft}\n")
        try:
            result = await execute_subtask_with_algorithm(
                task_instruction=goal,
                method="self_refine",
                draft=draft,
                llm=llm,
            )
            print(f"Deterministic Grounded Checks: {result.grounded_issues or 'Passed'}")
            print(f"Critic Rubric Critique:\n{result.critique}\n")
            print(f"=== Revised & Refined Deliverable ===\n{result.revised}\n")
        except Exception as e:
            print(f"[Self-Refine Error]: {e}\n")
        return True

    return False


async def main():
    async with create_client(mode="stdio") as client:
        # Pre-warm or discover client capabilities
        await client.list_tools()

        print("================================================================================")
        print("                   GREENFIELD AGRICULTURAL DISPATCH AGENT                       ")
        print("================================================================================")
        print("Type '/algorithms' or '/help' to see and run any of the 7 planning algorithms.")
        print("Type 'exit' to quit.\n")

        while True:
            try:
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

            # Check if user invoked a direct planning algorithm command
            handled = await handle_algorithm_command(user_input)
            if handled:
                continue

            # Standard Autonomous Agent Step with MCP Tools & Planning Scratchpad
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
                answer = None
                if isinstance(step.action_input, dict):
                    answer = step.action_input.get("answer")
                if not answer and hasattr(step, "final_answer"):
                    answer = step.final_answer
                if not answer:
                    answer = str(step.action_input or "Task completed.")

                print(f"\nAgent: {answer}\n")

            # --- RUN PERIODIC SEMANTIC CONSOLIDATION PASS ---
            consolidator.run_consolidation_pass()

            if step.action in ("end_conversation", "escalate"):
                print("Conversation ended.")
                break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted. Exiting...")