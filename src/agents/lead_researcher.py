import json
import os

from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm import ChatOpenAI

from graph.state import LeadCampaign, Lead

# Pull model from environment, default to gpt-4o
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.2")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

RESEARCHER_SYSTEM_PROMPT = """You are an expert lead generation specialist. Your job is to
research and compile a targeted lead list based on a lead campaign criteria or B2B target goal.

Return ONLY valid JSON with no prose, no markdown code fences, no explanation.
The JSON must match this exact schema:

{
  "goal": "the original targeting goal or ICP criteria exactly as given",
  "total_leads_target": <integer between 2 and 6>,
  "outreach_channel": "email",
  "leads": [
    {
      "name": "Full Name",
      "company": "Company Name",
      "role": "Lead's role (e.g. Founder, CEO, VP Sales)",
      "email": "professional email address (e.g. name@company.com)",
      "company_description": "One clear sentence describing their business model and product offering",
      "personalized_hook": "A unique personalization angle (e.g., matching their recent launch, value proposition, or growth pain point)",
      "status": "pending"
    }
  ]
}

Rules:
- Generate high-quality, realistic, and highly relevant leads that perfectly fit the target criteria
- Aim for 3 to 5 leads
- status must always be "pending"
"""

def build_researcher_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=0.1,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

def parse_campaign_json(json_string: str) -> LeadCampaign:
    """Parse the LLM's JSON output into a LeadCampaign dataclass."""
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned invalid JSON.\n"
            f"Error: {e}\n"
            f"Raw output (first 300 chars): {json_string[:300]}"
        )

    required = ["goal", "total_leads_target", "leads"]
    for field_name in required:
        if field_name not in data:
            raise ValueError(f"LLM JSON missing required field: '{field_name}'")

    if not isinstance(data["leads"], list) or len(data["leads"]) == 0:
        raise ValueError("LLM JSON 'leads' must be a non-empty list")

    leads = []
    for i, l in enumerate(data["leads"]):
        for field_name in ["name", "company", "role", "email", "company_description"]:
            if field_name not in l:
                raise ValueError(f"Lead {i} missing required field: '{field_name}'")
        leads.append(Lead(
            name=l["name"],
            company=l["company"],
            role=l["role"],
            email=l["email"],
            company_description=l["company_description"],
            personalized_hook=l.get("personalized_hook", ""),
            status=l.get("status", "pending"),
        ))

    return LeadCampaign(
        goal=data["goal"],
        total_leads_target=int(data["total_leads_target"]),
        outreach_channel=data.get("outreach_channel", "email"),
        leads=leads,
    )

def lead_researcher_node(state: dict) -> dict:
    """
    LangGraph node: Lead Researcher

    Reads:  state["goal"]
    Writes: state["campaign"], state["messages"], state["error"]
    """
    goal = state.get("goal", "").strip()
    if not goal:
        return {"error": "No lead target criteria provided."}

    print(f"\n[Lead Researcher] Targeting criteria: '{goal}'")

    llm = build_researcher_llm()
    messages = [
        SystemMessage(content=RESEARCHER_SYSTEM_PROMPT),
        HumanMessage(content=f"Create a targeted lead generation campaign list for: {goal}"),
    ]

    print(f"[Lead Researcher] Calling {MODEL_NAME}...")
    response = llm.invoke(messages)

    try:
        campaign = parse_campaign_json(response.content)
    except ValueError as e:
        print(f"[Lead Researcher] Parse error: {e}")
        return {
            "error": str(e),
            "messages": messages + [response],
        }

    print(f"[Lead Researcher] Compiled {len(campaign.leads)} matching leads")

    return {
        "campaign": campaign,
        "messages": messages + [response],
        "error": None,
    }
