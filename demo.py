"""End-to-end demo for the Greenfield MCP Dispatch project.

Runs the real MCP server (server/server.py) as a stdio subprocess against
an isolated throwaway database, then walks through discovery, resources,
prompts, every tool (including elicitation and progress), negative security
cases, and verifies the resulting database state.

The live LLM agent phase (agent/agent.py) runs only when GROQ_API_KEY is set;
everything else works without any API key.

Usage:
    uv run python demo.py
"""

import asyncio
import os
import sqlite3
import sys
import tempfile
from dotenv import load_dotenv
load_dotenv() 

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult, ElicitRequestParams, RequestContext

REPO = os.path.dirname(os.path.abspath(__file__))
SERVER_SCRIPT = os.path.join(REPO, "server", "server.py")

passed = []
failed = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        passed.append(name)
        print(f"  [PASS] {name}")
    else:
        failed.append(name)
        print(f"  [FAIL] {name}  {detail}")


def is_error(res) -> bool:
    return bool(getattr(res, "is_error", getattr(res, "isError", False)))


def result_text(res) -> str:
    items = res.content if hasattr(res, "content") else res
    return " ".join(getattr(c, "text", str(c)) for c in items)


async def on_progress(progress: float, total: float | None, message: str | None):
    pct = progress if not total else (progress / total) * 100
    print(f"  [PROGRESS] {pct:.0f}% {message or ''}")


async def on_elicitation(
    message: str,
    response_type: type | None,
    params: ElicitRequestParams,
    context: RequestContext,
):
    print(f"  [ELICITATION] {message}")
    return ElicitResult(
        action="accept",
        content={"approved": True, "notes": "auto-approved by demo"},
    )


def make_demo_db() -> str:
    tmp = tempfile.mkdtemp(prefix="greenfield-demo-")
    db_path = os.path.join(tmp, "farm.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(open(os.path.join(REPO, "db", "schema.sql"), encoding="utf-8").read())
    conn.executescript(open(os.path.join(REPO, "db", "seed.sql"), encoding="utf-8").read())
    conn.commit()
    conn.close()
    return db_path


async def main():
    os.environ["GREENFIELD_DB_PATH"] = db_path = make_demo_db()
    print("=" * 60)
    print("GREENFIELD MCP DISPATCH - END-TO-END DEMO")
    print("=" * 60)

    config = {
        "mcpServers": {
            "GREENFIELD_server": {
                "command": sys.executable,
                "args": [SERVER_SCRIPT, "stdio"],
                "env": {"GREENFIELD_DB_PATH": db_path},
            }
        }
    }

    async with Client(
        config,
        elicitation_handler=on_elicitation,
        progress_handler=on_progress,
    ) as client:

        # ---------------------------------------------------------------
        print("\n[1] Discovery")
        # ---------------------------------------------------------------
        tools = await client.list_tools()
        check("tools/list", len(tools) >= 4, f"got {len(tools)}")
        for t in tools:
            print(f"    - {t.name}: {t.description[:70]}")

        resources = await client.list_resources()
        check("resources/list", len(resources) == 2, f"got {len(resources)}")

        prompts = await client.list_prompts()
        check("prompts/list", len(prompts) >= 1, f"got {len(prompts)}")

        # ---------------------------------------------------------------
        print("\n[2] Resources & Prompts")
        # ---------------------------------------------------------------
        policy = await client.read_resource("policy://pesticide-compliance")
        check("policy resource", "SIGN-OFF REQUIREMENT" in result_text(policy).upper())

        fleet = await client.read_resource("fleet://equipment-status")
        fleet_text = result_text(fleet)
        check("fleet snapshot resource", "equipment_id | serial" in fleet_text)

        prompt = await client.get_prompt("draft_delay_explanation", arguments={"dispatch_id": 2})
        check("prompt fill", "Spray" in str(prompt) or "spray" in str(prompt).lower())

        # ---------------------------------------------------------------
        print("\n[3] dispatch_equipment - till job (no sign-off)")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "dispatch_equipment",
            {"input_data": {"equipment_id": 1, "field_id": 1, "job_type": "till", "customer_id": 1}},
        )
        text = result_text(res)
        check("till dispatch ok", not is_error(res) and "SUCCESS" in text, text)

        # ---------------------------------------------------------------
        print("\n[4] dispatch_equipment - restricted spray (elicitation)")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "dispatch_equipment",
            {"input_data": {"equipment_id": 3, "field_id": 2, "job_type": "spray",
                            "chemical_id": 1, "customer_id": 1}},
        )
        text = result_text(res)
        check("restricted spray ok", not is_error(res) and "SUCCESS" in text, text)

        # ---------------------------------------------------------------
        print("\n[5] Security blocks")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "dispatch_equipment",
            {"input_data": {"equipment_id": 2, "field_id": 1, "job_type": "till", "customer_id": 1}},
            raise_on_error=False,
        )
        text = result_text(res)
        check("busy equipment blocked", is_error(res) and "cannot be dispatched" in text, text)

        res = await client.call_tool(
            "dispatch_equipment",
            {"input_data": {"equipment_id": 1, "field_id": 5, "job_type": "till", "customer_id": 1}},
            raise_on_error=False,
        )
        text = result_text(res)
        check("cross-customer field blocked", is_error(res) and "SECURITY BLOCK" in text, text)

        # ---------------------------------------------------------------
        print("\n[6] batch_dispatch (progress)")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "batch_dispatch",
            {"input_data": {"equipment_ids": [5], "field_id": 3}},
            progress_handler=on_progress,
        )
        text = result_text(res)
        check("batch dispatch ok", not is_error(res) and "SUCCESS" in text, text)

        # ---------------------------------------------------------------
        print("\n[7] process_payment (credit hold)")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "process_payment",
            {"input_data": {"customer_id": 2}},
        )
        text = result_text(res)
        check("payment ok", not is_error(res) and "SUCCESS" in text, text)

        # ---------------------------------------------------------------
        print("\n[8] log_incident_note (LLM sampling)")
        # ---------------------------------------------------------------
        res = await client.call_tool(
            "log_incident_note",
            {"input_data": {"raw_note": "Sprayer 3002 nozzle clogged, chemical residue leaking from side panel."}},
        )
        text = result_text(res)
        check("incident note recorded", "Incident logged" in text, text)

        # ---------------------------------------------------------------
        print("\n[9] Database state verification")
        # ---------------------------------------------------------------
        db_path = os.environ["GREENFIELD_DB_PATH"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        jobs = conn.execute("SELECT * FROM Dispatch_Jobs WHERE dispatch_id >= 6").fetchall()
        check("dispatch jobs recorded", len(jobs) == 2, f"got {len(jobs)}")

        eq1 = conn.execute("SELECT status FROM Equipment WHERE equipment_id = 1").fetchone()
        check("equipment 1 now dispatched", eq1["status"] == "dispatched", eq1["status"])

        eq3 = conn.execute("SELECT status FROM Equipment WHERE equipment_id = 3").fetchone()
        check("equipment 3 now dispatched", eq3["status"] == "dispatched", eq3["status"])

        spray_job = conn.execute(
            "SELECT approval_status, approved_by FROM Dispatch_Jobs WHERE dispatch_id = 7"
        ).fetchone()
        check(
            "sign-off recorded as approved",
            spray_job and spray_job["approval_status"] == "approved" and spray_job["approved_by"] is not None,
            dict(spray_job) if spray_job else "missing",
        )

        hold = conn.execute("SELECT credit_hold FROM Customers WHERE customer_id = 2").fetchone()
        check("customer 2 hold cleared", hold["credit_hold"] == 0, hold["credit_hold"])
        conn.close()

    # ---------------------------------------------------------------
    print("\n[10] Live agent (requires GROQ_API_KEY)")
    # ---------------------------------------------------------------
    if os.environ.get("GROQ_API_KEY"):
        from agent.agent import run_agent

        async with Client(
            config,
            elicitation_handler=on_elicitation,
            progress_handler=on_progress,
        ) as client:
            turns = [
                "Dispatch equipment 5 to field 5 for harvest, customer 3.",
                "Show me the current fleet status.",
            ]
            for i, user_input in enumerate(turns, 1):
                print(f"\n  [AGENT] user: {user_input}")
                step = await run_agent(client=client, user_input=user_input, user_id="C001")
                check(f"agent turn {i} completed", step is not None)
    else:
        print("  [SKIP] GROQ_API_KEY not set - agent loop demo skipped.")
        print("  Set GROQ_API_KEY in the environment to exercise the live LLM loop.")

    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
    if failed:
        print("FAILED:", ", ".join(failed))
    print("=" * 60)
    print(f"Demo database: {os.environ['GREENFIELD_DB_PATH']}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
