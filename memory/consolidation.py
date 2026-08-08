import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from memory.memory import LongTermMemory


class FactUpdate(BaseModel):
    fact_key: str = Field(
        description="Unique snake_case key (e.g. 'customer_1_allergy', 'customer_1_manager', 'customer_1_occupation')"
    )
    extracted_value: str = Field(
        description="The detailed fact statement including explicit IDs and names."
    )
    resolution_type: str = Field(
        default="new_fact",
        description="One of: 'new_fact', 'update', 'resolve_contradiction'"
    )
    reasoning: str = Field(
        description="Brief explanation of why this fact should be added or updated."
    )


class ConsolidationBatch(BaseModel):
    updates: List[FactUpdate] = Field(
        default_factory=list,
        description="List of extracted facts. MUST NOT be empty if persistent user facts are present."
    )


CONSOLIDATION_PROMPT = """You are the Semantic Memory Consolidation engine for Greenfield Agriculture.
Your job is to analyze new episodic events and extract PERMANENT facts to save into semantic memory.

Current Active Semantic Facts:
{active_facts}

Unconsolidated Episodic Events:
{episodic_batch}

INSTRUCTIONS:
1. Extract ALL persistent user/domain facts from the episodes (e.g. allergies, manager relationships, customer job/role, field preferences).
2. PRESERVE exact details: Customer IDs (Customer 1), chemical/equipment names (SPR-3001), manager names (Abdo).
3. Do NOT skip facts just because they look simple.
   - Example Episode: "Customer 1 is allergic to SPR-3001" -> fact_key: "customer_1_allergy", extracted_value: "Customer 1 is allergic to SPR-3001"
   - Example Episode: "Abdo manages this customer" -> fact_key: "customer_1_manager", extracted_value: "Customer 1 is managed by Abdo"
   - Example Episode: "the customer is a farmer" -> fact_key: "customer_1_occupation", extracted_value: "Customer 1 is a farmer"
4. If an episode contains only tool error logs or routine greetings, ignore that specific line.
5. Return at least one FactUpdate if any persistent fact is present."""


class SemanticConsolidator:
    def __init__(self, long_term_memory: LongTermMemory):
        self.long_term = long_term_memory
        self.model = init_chat_model(
            model="llama-3.3-70b-versatile",
            model_provider="groq",
            temperature=0.0,
            max_tokens=2048,
        ).with_structured_output(ConsolidationBatch)

    def run_consolidation_pass(self) -> int:
        # Collect unprocessed events
        unconsolidated = [
            e for e in self.long_term.episodic_events 
            if not e.get("consolidated", False)
        ]

        if not unconsolidated:
            print("[Consolidation Pass]: No new episodic events to process.")
            return 0

        # Build active facts text
        active_facts = self.long_term.get_active_facts()
        active_facts_str = json.dumps(active_facts, indent=2) if active_facts else "None"

        # Format episode batch (using summary or context)
        batch_lines = []
        for idx, e in enumerate(unconsolidated):
            text = e.get("summary") or e.get("context") or ""
            if text:
                batch_lines.append(f"[{idx+1}] {text}")

        if not batch_lines:
            # Mark useless/empty events as consolidated and return
            for e in unconsolidated:
                e["consolidated"] = True
            self.long_term._save_to_file()
            return 0

        batch_text = "\n".join(batch_lines)
        prompt = CONSOLIDATION_PROMPT.format(
            active_facts=active_facts_str,
            episodic_batch=batch_text
        )

        try:
            result: ConsolidationBatch = self.model.invoke(prompt)

            if result and result.updates:
                self._apply_updates(result.updates)

            # Mark processed episodes as consolidated ONLY after successful extraction pass
            for e in unconsolidated:
                e["consolidated"] = True

            self.long_term._save_to_file()
            print(f"[Consolidation Pass]: Successfully processed {len(unconsolidated)} episodes with {len(result.updates if result else [])} semantic updates.")
            return len(unconsolidated)

        except Exception as e:
            print(f"[Consolidation Pass Error]: {e}")
            return 0

    def _apply_updates(self, updates: List[FactUpdate]):
        now = datetime.utcnow().isoformat()

        for update in updates:
            key = update.fact_key
            existing = self.long_term.semantic_facts.get(key)

            if existing:
                current_val = existing.get("current_value", "").strip().lower()
                new_val = update.extracted_value.strip().lower()

                # Avoid duplicate version bumps if the text value is identical
                if current_val == new_val:
                    continue

                current_version = existing.get("version", 1)
                new_version = current_version + 1

                history = existing.get("history", [])
                history.append({
                    "version": current_version,
                    "value": existing.get("current_value"),
                    "replaced_at": now,
                    "reasoning": update.reasoning,
                })

                self.long_term.semantic_facts[key] = {
                    "current_value": update.extracted_value,
                    "version": new_version,
                    "last_updated": now,
                    "resolution_type": update.resolution_type,
                    "history": history,
                }
                print(f" [Semantic Update v{new_version}] Key '{key}': {update.extracted_value}")

            else:
                self.long_term.semantic_facts[key] = {
                    "current_value": update.extracted_value,
                    "version": 1,
                    "last_updated": now,
                    "resolution_type": "new_fact",
                    "history": [],
                }
                print(f" [New Semantic Fact v1] Key '{key}': {update.extracted_value}")