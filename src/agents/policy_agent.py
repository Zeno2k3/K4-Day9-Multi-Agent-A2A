"""Policy Agent.

Scoped data: none directly — receives only the consolidated CaseFacts sheet
built by the Coordinator from the other 4 agents' handoffs. Never touches
the DataStore. Applies EC_POLICY_V2 via src.tools.policy_tools (the
deterministic "gold" answer) and cross-checks it against an independent
LLM classification of the same fact sheet.
"""
from __future__ import annotations

from src.agents.common import llm_trace_summary
from src.llm.groq_client import GroqClient
from src.llm.prompts import POLICY_SYSTEM_PROMPT
from src.schemas.handoff_models import CaseFacts, PolicyDecision
from src.tools import policy_tools
from src.tracing.trace_logger import TraceLogger


class PolicyAgent:
    name = "policy_agent"

    def __init__(self, llm: GroqClient):
        self.llm = llm

    def run(
        self,
        case_id: str,
        facts: CaseFacts,
        multi_item_order: bool,
        multi_seller_order: bool,
        split_payment: bool,
        repeat_customer: bool,
        multiple_categories: bool,
        trace: TraceLogger,
    ) -> PolicyDecision:
        primary_issue, matched = policy_tools.classify_primary_issue(facts)
        secondary_issues = policy_tools.compute_secondary_issues(
            multi_item_order, multi_seller_order, split_payment, repeat_customer, multiple_categories
        )
        case_status = policy_tools.compute_case_status(primary_issue)
        refund = policy_tools.compute_recommended_refund_brl(
            primary_issue, facts.payment_total_brl, facts.freight_total_brl
        )
        responsible_parties = policy_tools.compute_responsible_parties(
            primary_issue, facts.late_handoff_seller_ids
        )
        actions = policy_tools.compute_resolution_actions(
            primary_issue, multi_seller_order, split_payment
        )
        root_cause_code = policy_tools.PRIMARY_ISSUE_ROOT_CAUSE[primary_issue]

        llm_result = self.llm.call_json(POLICY_SYSTEM_PROMPT, facts.model_dump())
        llm_primary = None
        llm_agrees = True
        llm_unavailable = not llm_result.success
        if llm_result.success and llm_result.parsed:
            llm_primary = llm_result.parsed.get("primary_issue")
            llm_agrees = llm_primary == primary_issue

        trace.agent_run(
            case_id,
            self.name,
            inputs_summary=facts.model_dump(),
            tool_calls=[
                {"name": "classify_primary_issue", "result": primary_issue, "matched_defined_row": matched},
                {"name": "compute_secondary_issues", "result": secondary_issues},
                {"name": "compute_recommended_refund_brl", "result": refund},
            ],
            llm_call=llm_trace_summary(llm_result),
            output_summary={
                "primary_issue": primary_issue,
                "primary_issue_llm": llm_primary,
                "llm_agrees": llm_agrees,
                "case_status": case_status,
                "resolution_actions": actions,
                "policy_edge_case": not matched,
            },
        )

        return PolicyDecision(
            primary_issue=primary_issue,
            primary_issue_llm=llm_primary,
            llm_agrees=llm_agrees,
            llm_unavailable=llm_unavailable,
            secondary_issues=secondary_issues,
            root_cause_codes=[root_cause_code],
            responsible_parties=responsible_parties,
            recommended_refund_brl=refund,
            resolution_actions=actions,
            case_status=case_status,
            policy_edge_case=not matched,
        )
