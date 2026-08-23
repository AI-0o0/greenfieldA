import asyncio
import sys
import os

from agent.agent import (
    agent_step,
    get_base_llm,
    execute_subtask_with_algorithm,
)
from agent.memory.memory import ShortTermMemory, LongTermMemory
from agent.memory.consolidation import SemanticConsolidator
from mcp_client.client import create_client
from agent.algorithms.environment import GreenfieldEnvironment
from agent.algorithms.decomposition import decompose_goal, execute_plan, final_output
from agent.workflows.finance_agent import (
    create_finance_agent,
    run_finance_turn,
    fetch_farmer_db_profile,
)
from langgraph.checkpoint.memory import MemorySaver


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
All 8 planning algorithms & state graph workflows are available:

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

8. Autonomous Finance & Lending Agent (LangGraph StateGraph):
   Command: /finance <request> (or /loan <request>)
   Desc   : 27-node state machine with real-time underwriting, ToT structuring,
            HITL manager sign-off, provider integrations, and disbursement verification.

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

    # 8. Autonomous Finance & Lending Agent (/finance or /loan)
    if cmd.startswith("/finance ") or cmd.startswith("/loan ") or cmd.startswith("/fund "):
        req = cmd.split(" ", 1)[1].strip()
        await handle_finance_agent_cli(prompt=req)
        return True

    return False


async def handle_finance_agent_cli(prompt: str, farmer_id: int = 1):
    """Executes an interactive turn-by-turn CLI session with the LangGraph Finance Agent."""
    import uuid

    checkpointer = MemorySaver()
    graph = create_finance_agent(checkpointer=checkpointer, interactive=True)
    thread_id = str(uuid.uuid4())[:8]

    farmer_profile = fetch_farmer_db_profile(farmer_id)
    farmer_name = farmer_profile.get("company_name", f"Farmer #{farmer_id}")

    print(f"\n================================================================================")
    print(f"   AUTONOMOUS FINANCE STATEGRAPH AGENT (Thread: {thread_id} | Applicant: {farmer_name})")
    print(f"================================================================================")
    print(f"Farmer Inquiry: '{prompt}'\n")

    state_input: dict = {"farmer_id": farmer_id, "farmer_request": prompt}

    while True:
        run_finance_turn(graph, thread_id, state_input)
        config = {"configurable": {"thread_id": thread_id}}
        snap = graph.get_state(config)

        # Print latest execution steps trace
        logs = snap.values.get("execution_log", [])
        if logs:
            print("[Execution Trace]: " + " -> ".join([s.split(":")[0] for s in logs[-5:]]))

        next_nodes = list(snap.next) if snap.next else []

        if not next_nodes:
            out = snap.values.get("final_output") or snap.values.get("recommendation") or "Financial workflow completed."
            print(f"\n=== Financial Deliverable ===\n{out}\n")
            break

        current_node = next_nodes[0]

        if current_node == "wait_farmer":
            docs = snap.values.get("documents_required", ["government_id", "farm_tax_return", "bank_statements", "land_deed_or_lease"])
            print(f"\n[Checkpoint: Awaiting Verification Documents]")
            print(f"Required Documents: {', '.join(docs)}")
            ans = await asyncio.to_thread(input, "Upload verified documents now? [Y/n] (default: Y): ")
            if ans.strip().lower() in ("n", "no"):
                print("Document upload cancelled by user.")
                break
            state_input = {
                "documents_submitted": {
                    "government_id": "id_verified.pdf",
                    "farm_tax_return": "tax_2025.pdf",
                    "bank_statements": "bank_statements_6m.pdf",
                    "land_deed_or_lease": "field_lease.pdf",
                }
            }

        elif current_node == "admin_review":
            analysis = snap.values.get("financial_analysis", {})
            amt = analysis.get("assessed_amount", 50000.0)
            dscr = analysis.get("dscr", 1.35)
            risk = analysis.get("risk_level", "medium")
            print(f"\n[⚠️ Checkpoint: Senior Admin / HITL Underwriting Review]")
            print(f"Assessed Amount: ${amt:,.2f} | DSCR: {dscr:.2f} | Risk Rating: {risk.upper()}")
            ans = await asyncio.to_thread(input, "Administrator Decision [approve / reject] (default: approve): ")
            dec = "reject" if ans.strip().lower().startswith("r") else "approve"
            state_input = {"admin_decision": dec}

        elif current_node == "wait_provider":
            sub = snap.values.get("submitted_application", {})
            pref = sub.get("provider_reference", "EXT-PROV-101")
            print(f"\n[Checkpoint: Awaiting Lending Provider Terms (Ref: {pref})]")
            ans = await asyncio.to_thread(input, "Simulate Provider Decision [approve / reject] (default: approve): ")
            p_res = "rejected" if ans.strip().lower().startswith("r") else "approved"
            state_input = {"provider_response": p_res}

        elif current_node == "farmer_confirm":
            terms = snap.values.get("provider_terms", {})
            amt = terms.get("approved_amount", 0)
            ir = terms.get("interest_rate", 0.055) * 100
            tm = terms.get("term_months", 36)
            mp = terms.get("monthly_payment", 0)
            print(f"\n[Checkpoint: Farmer Loan Agreement Confirmation]")
            print(f"Approved Principal: ${amt:,.2f} | Rate: {ir:.1f}% APR | Horizon: {tm} mos | Mo. Payment: ${mp:,.2f}")
            ans = await asyncio.to_thread(input, "Farmer accepts and signs terms? [Y/n] (default: Y): ")
            accept = not ans.strip().lower().startswith("n")
            state_input = {"farmer_accepts": accept}

        else:
            state_input = {}


async def main():
    async with create_client(mode="stdio") as client:
        # Pre-warm or discover client capabilities
        await client.list_tools()

        print("================================================================================")
        print("                   GREENFIELD AGRICULTURAL DISPATCH AGENT                       ")
        print("================================================================================")
        print("Type '/algorithms' or '/help' to see and run any of the 8 planning algorithms.")
        print("Type '/finance <inquiry>' to run the Autonomous Finance & Lending Agent.")
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