import json
import os
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from utils.llm import ChatOpenAI

from graph.state import get_latest_simulation_result, LeadCampaign
from mcp_servers.memory_server import memory_set

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.2")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PASS_THRESHOLD = 0.5

COACHING_PROMPT = """You are an encouraging sales manager reviewing a sales representative's objection-handling simulation results.

Provide a brief, warm coaching message (2-3 sentences max) based on:
  - The prospect studied
  - Their simulation score (0.0 = 0%, 1.0 = 100%)
  - Any weak areas identified in handling objections

Return ONLY valid JSON:
{{
  "summary": "2-3 sentence encouraging summary of their objection-handling skills",
  "encouragement": "One short motivational sentence for next steps with this lead or campaign"
}}

Be specific. Reference the prospect's company and any weak areas by name.
Never be discouraging. A low score means "more practice needed", not "you failed."
"""


def get_coaching_message(lead_name: str, company: str, score: float, weak_areas: list[str]) -> dict:
    """Ask the LLM for a personalised B2B coaching message."""
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=0.4,
        format="json",
    )
    context = {
        "lead_name":     lead_name,
        "company":       company,
        "score_percent": f"{score:.0%}",
        "weak_areas":    weak_areas if weak_areas else ["none identified"],
    }
    try:
        response = llm.invoke([
            SystemMessage(content=COACHING_PROMPT),
            HumanMessage(content=json.dumps(context)),
        ])
        return json.loads(response.content)
    except Exception as e:
        print(f"[CRM Coach] LLM call failed: {e}")
        return {
            "summary":      f"You scored {score:.0%} on objection handling for {lead_name} at {company}. Keep practicing!",
            "encouragement": "Every simulation prepares you for real-world deals.",
        }


def crm_coach_node(state: dict) -> dict:
    """
    LangGraph node: CRM Coach / Progress Coach Counterpart

    Reads:  state["simulation_results"], state["campaign"],
            state["current_lead_index"], state["session_id"]
    Writes: state["campaign"], state["current_lead_index"],
            state["messages"], state["error"]
    """
    latest = get_latest_simulation_result(state)
    if latest is None:
        return {"error": "No simulation results. Objection Simulator must run first"}

    campaign = state.get("campaign")
    if campaign is None:
        return {"error": "No campaign found"}
    if isinstance(campaign, dict):
        campaign = LeadCampaign.from_dict(campaign)

    idx = state.get("current_lead_index", 0)
    session_id = state.get("session_id", "unknown")
    score = latest.score

    # Fetch corresponding lead details
    leads = campaign.leads
    lead = leads[idx]

    print(f"\n[CRM Coach] Lead: '{latest.lead_name}' ({lead.company})")
    print(f"[CRM Coach] SDR Score: {score:.0%}")
    if latest.weak_areas:
        print(f"[CRM Coach] Weak areas identified: {', '.join(latest.weak_areas)}")

    # Get coaching message from LLM
    coaching = get_coaching_message(latest.lead_name, lead.company, score, latest.weak_areas)

    # Update lead status in the campaign
    new_status = "approved" if score >= PASS_THRESHOLD else "needs_review"
    lead.status = new_status

    # Advance the lead index
    next_idx = idx + 1
    all_done = next_idx >= len(leads)

    # Persist progress to Memory MCP
    memory_set(session_id, f"progress_lead_{idx}", json.dumps({
        "lead_name":  latest.lead_name,
        "score":      score,
        "weak_areas": latest.weak_areas,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }))

    # Print coaching feedback
    print(f"\n{'─'*60}")
    print(f"Coach: {coaching['summary']}")
    print(f"{coaching['encouragement']}")

    if all_done:
        results = state.get("simulation_results", [])
        avg = sum(r.score for r in results) / max(len(results), 1)
        print(f"\nCampaign simulation complete! Average SDR Score: {avg:.0%}")
    else:
        next_lead = leads[next_idx]
        print(f"\nNext target prospect: '{next_lead.name}' ({next_lead.company})")
    print(f"{'─'*60}\n")

    return {
        "campaign":             campaign,
        "current_lead_index":   next_idx,
        "messages":             [AIMessage(content=coaching["summary"])],
        "error":                None,
    }
