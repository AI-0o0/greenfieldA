from __future__ import annotations

import random
import re
from typing import List, Optional

from .models import EnvironmentFeedback


class Environment:
    """
    Evaluator for Greenfield Agricultural Agency dispatch operations.
    Combines agricultural domain compliance checks with stochastic grounding
    to evaluate candidate plans, dispatch actions, and operational decisions.
    """

    def __init__(
        self,
        success_threshold: float = 0.6,
        rng: random.Random | None = None,
        enable_domain_checks: bool = True,
    ):
        if not 0.0 <= success_threshold <= 1.0:
            raise ValueError("success_threshold must be between zero and one")
        self.success_threshold = success_threshold
        self.rng = rng or random.Random()
        self.enable_domain_checks = enable_domain_checks

    def _check_agricultural_constraints(self, state: str) -> tuple[float, list[str]]:
        """
        Evaluate domain-specific constraints for agricultural dispatch operations.
        Returns a base compliance score (0.0 - 1.0) and a list of feedback details.
        """
        text = state.lower()
        details: list[str] = []
        score = 0.85  # Base favorable score

        # 1. Chemical Safety & Canal Buffer Zone Compliance
        if "canal" in text or "irrigation" in text:
            has_negative = "no buffer" in text or "without buffer" in text or "ignore buffer" in text
            has_buffer = ("15" in text or "buffer" in text or "low-hazard" in text or "adjust" in text) and not has_negative
            if not has_buffer:
                score -= 0.35
                details.append("Violates canal buffer policy: Restricted chemicals require at least a 15m buffer zone.")
            else:
                details.append("Canal buffer compliance verified (15m buffer zone).")

        # 2. Organic Boundary Buffer Zone
        if "organic" in text:
            has_organic_buf = ("50" in text or "buffer" in text) and "no buffer" not in text
            if not has_organic_buf:
                score -= 0.3
                details.append("Violates organic neighbor boundary policy: Mandatory 50m drift buffer required.")
            else:
                details.append("Organic boundary drift buffer confirmed.")

        # 3. Weather & Wind Compliance
        if "wind" in text and ("18" in text or "exceed" in text or "high" in text or "advisory" in text):
            mitigated = any(kw in text for kw in ["halt", "reschedule", "swap", "tillage", "hold", "pause", "reassign"])
            if not mitigated:
                score -= 0.35
                details.append("Weather violation: Spraying in wind speeds exceeding 15 km/h violates chemical application policy.")
            else:
                details.append("High wind policy adhered to: Spraying halted/rescheduled.")

        # 4. Temperature / Heat Evaporation Restrictions
        if "heat" in text or "38" in text or "evaporation" in text or "hot" in text:
            mitigated = any(kw in text for kw in ["split", "morning", "evening", "06:00", "17:00", "reschedule", "shift"])
            if not mitigated:
                score -= 0.3
                details.append("Temperature violation: Midday spray ban (over 35°C) requires splitting schedule into early morning/evening.")
            else:
                details.append("Heat advisory mitigation applied: Schedule split into morning/evening windows.")

        # 5. Soil Compaction & Moisture
        if "moisture" in text or "clay" in text or "wet" in text or "compaction" in text:
            uses_heavy = "trc-205" in text or "heavy" in text
            mitigated = any(kw in text for kw in ["trc-201", "lightweight", "replace", "avoid", "swap", "delay", "tillage"])
            if uses_heavy and not mitigated:
                score -= 0.35
                details.append("Soil safety violation: Operating heavy equipment (TRC-205) in high moisture conditions causes root zone compaction.")
            else:
                details.append("Soil compaction protection verified.")

        # 6. Sprayer Calibration & SOP Compliance
        if "psi" in text or "calibration" in text or "spr-3002" in text:
            out_of_spec = "22" in text or "out-of-spec" in text or "low pressure" in text
            mitigated = any(kw in text for kw in ["shop", "recalibration", "recalibrate", "spr-3003", "30 psi", "30psi", "backup"])
            if out_of_spec and not mitigated:
                score -= 0.3
                details.append("Equipment safety violation: Sprayer with out-of-spec pressure (22 PSI) must be recalibrated to 30 PSI.")
            else:
                details.append("Equipment calibration and SOP verified.")

        # 7. Restricted Chemicals & Sign-off SOP
        if "sop-chem-4040" in text or "restricted" in text or "glyphosate" in text or "chemical_id=1" in text:
            has_signoff = any(kw in text for kw in ["sign-off", "signoff", "supervisor", "hold", "alert", "approval", "approve"])
            if not has_signoff:
                score -= 0.3
                details.append("Compliance hold: Restricted chemical dispatch requires supervisor sign-off per SOP-CHEM-4040.")
            else:
                details.append("SOP sign-off requirement verified.")

        # 8. Financial / Credit Hold Checks
        if "unpaid" in text or "credit hold" in text or "overdue" in text or "balance" in text:
            enforced = any(kw in text for kw in ["hold", "reassign", "payment", "pause", "block", "freed"])
            if not enforced:
                score -= 0.35
                details.append("Financial policy violation: Cannot dispatch equipment to customer with active credit hold.")
            else:
                details.append("Credit hold policy enforced.")

        # 9. Allergy & Chemical Contamination Checks
        if "allergy" in text or "organophosphate" in text:
            decontaminated = any(kw in text for kw in ["decontamination", "decontaminate", "clean", "flush", "wash", "safety"])
            if not decontaminated:
                score -= 0.35
                details.append("Health & safety hazard: Spray tank must undergo verified decontamination for allergy conflicts.")
            else:
                details.append("Allergy safety decontamination protocol satisfied.")

        # 10. Basic Content Sanity Check
        if len(text.strip().split()) < 4:
            score -= 0.4
            details.append("Candidate solution is too brief or incomplete.")

        return max(0.0, min(1.0, score)), details

    def evaluate(self, state: str) -> EnvironmentFeedback:
        """
        Evaluates a candidate state or action against Greenfield agricultural criteria.
        """
        if not self.enable_domain_checks:
            # Pure stochastic evaluator biased toward favorable results
            score = round(self.rng.betavariate(5.0, 2.0), 4)
            success = score >= self.success_threshold
            details = [] if success else ["The randomized evaluator rejected this attempt."]
            return EnvironmentFeedback(success=success, score=score, details=details)

        domain_score, details = self._check_agricultural_constraints(state)

        # Add slight realistic stochastic variance
        noise = self.rng.uniform(-0.04, 0.04)
        final_score = round(max(0.0, min(1.0, domain_score + noise)), 4)

        success = final_score >= self.success_threshold
        if not success and not details:
            details.append("The evaluation did not meet the required threshold for Greenfield dispatch criteria.")

        return EnvironmentFeedback(success=success, score=final_score, details=details)


class GreenfieldEnvironment(Environment):
    """Greenfield Agricultural Dispatch Environment Evaluator."""
    pass
