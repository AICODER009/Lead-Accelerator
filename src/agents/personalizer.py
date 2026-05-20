import json
import os
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from utils.llm import ChatOpenAI

from graph.state import get_current_lead
from mcp_servers.filesystem_server import list_study_files, read_study_file, search_notes
from mcp_servers.memory_server import memory_get, memory_set

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.2")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


@tool
def tool_list_files() -> list[str]:
    """
    List all B2B pitch materials and target profile documents in the materials directory.
    Returns filenames like ['value_proposition.md', 'case_studies.md'].
    Call this FIRST to discover what materials exist before reading any file.
    """
    return list_study_files()


@tool
def tool_read_file(filename: str) -> str:
    """
    Read the complete content of a B2B pitch material or target profile document.
    Args:
        filename: Exact filename as returned by tool_list_files().
    Returns the full file text, or an error string if not found.
    """
    return read_study_file(filename)


@tool
def tool_search_notes(query: str) -> str:
    """
    Search across all B2B materials and case studies for a keyword or phrase.
    Args:
        query: Search term (case-insensitive). Example: 'outsourcing', 'migration'
    Returns a JSON string with matching lines and their file locations.
    """
    results = search_notes(query)
    if not results:
        return "No matches found."
    return json.dumps(results, indent=2)


@tool
def tool_memory_get(session_id: str, key: str) -> str:
    """
    Retrieve a value from the B2B campaign session memory.
    Args:
        session_id: The current campaign session ID (from state).
        key: The memory key to look up.
    Returns the stored value, or 'null' if not found.
    """
    return memory_get(session_id, key)


@tool
def tool_memory_set(session_id: str, key: str, value: str) -> str:
    """
    Store a value in session memory for later agents or logging.
    Args:
        session_id: The current campaign session ID (from state).
        key: Descriptive key name.
        value: String value. Use JSON for complex data.
    """
    return memory_set(session_id, key, value)


@tool
def tool_ask_research_partner(query: str) -> str:
    """
    Delegate complex grounding, competitor research, or copywriting analysis queries to your remote Sales Research Partner agent.
    Args:
        query: Grounding / competitor search or copywriting analysis query.
    Returns:
        The detailed grounding report / research notes from the Sales Research Partner.
    """
    use_buddy = os.getenv("USE_STUDY_BUDDY", "false").lower() == "true"
    buddy_url = os.getenv("STUDY_BUDDY_URL", "http://localhost:9002")
    if use_buddy:
        from utils.a2a_client import call_a2a_agent
        try:
            print(f"[Personalizer] Delegating query '{query}' to remote Sales Research Partner at {buddy_url}")
            return call_a2a_agent(buddy_url, query)
        except Exception as e:
            return f"Error contacting Sales Research Partner A2A agent: {e}. Please use local list, search, and read tools instead."
    else:
        # Fallback local behavior: search our materials directly as a best effort
        from mcp_servers.filesystem_server import search_notes
        results = search_notes(query)
        if not results:
            return f"Sales Research Partner is offline (USE_STUDY_BUDDY=false) and no exact match found in local files for query '{query}'."
        return f"Sales Research Partner is offline (USE_STUDY_BUDDY=false). Found local matches:\n{json.dumps(results, indent=2)}"


@tool
def tool_ask_study_buddy(query: str) -> str:
    """
    (Deprecated Alias) Delegate queries to the remote Sales Research Partner.
    """
    return tool_ask_research_partner.invoke(query)


PERSONALIZER_TOOLS = [
    tool_list_files, tool_read_file, tool_search_notes,
    tool_memory_get, tool_memory_set, tool_ask_research_partner,
    tool_ask_study_buddy,
]
TOOL_MAP = {t.name: t for t in PERSONALIZER_TOOLS}

PERSONALIZER_SYSTEM_PROMPT = """You are an expert B2B outreach copywriter.

Your task is to write highly personalized cold outreach copies for a target lead.
Your personalization must be strictly grounded in our B2B materials (e.g. value propositions, case studies, company descriptions).
Use the available tools to find and read relevant B2B materials before generating the pitch.

APPROACH (follow this sequence):
1. Call tool_list_files() to see what B2B materials are available (e.g., case studies, value propositions).
2. If you need complex grounding, competitor research, or copywriting analysis, call tool_ask_research_partner(query) to delegate research.
3. Otherwise, call tool_search_notes(query) to find which files contain relevant angles or case studies matching the lead's company or industry.
4. Call tool_read_file(filename) to read the content of the selected B2B materials.
5. Check prior context: call tool_memory_get(session_id, 'personalized_leads') to see what leads were already processed in this campaign.
6. Synthesize a highly relevant, compelling, and hyper-personalized outreach sequence based on the company Bio, personalized hook, and grounded B2B materials.

OUTREACH FORMAT:
- Subject Line: Brief, high-impact, custom, and no-spam trigger words.
- Opener: Reference their role and a personalized growth pain point or recent achievement (1-2 sentences).
- Value Hook: A clear connection to our B2B value proposition or relevant case study from our materials (2-3 sentences).
- Call to Action (CTA): Low friction, clear next step (e.g., a short 10-min chat or open-ended question).
- Length: Extremely concise (under 150 words total).

After writing the outreach copy, store that you completed personalization for this lead:
  tool_memory_set(session_id, 'personalized_leads', <lead name or email>)
"""


def execute_tool_call(tool_call: dict) -> str:
    """Execute a tool call and return the result as a string. Never raises."""
    name = tool_call["name"]
    args = tool_call["args"]
    if name not in TOOL_MAP:
        return f"Error: unknown tool '{name}'. Available: {list(TOOL_MAP.keys())}"
    try:
        result = TOOL_MAP[name].invoke(args)
        if isinstance(result, (list, dict)):
            return json.dumps(result)
        return str(result)
    except Exception as e:
        return f"Error executing {name}({args}): {type(e).__name__}: {e}"


def personalizer_node(state: dict) -> dict:
    """
    LangGraph node: Personalizer Agent

    Reads:  state["campaign"], state["current_lead_index"], state["session_id"]
    Writes: state["messages"], state["error"]
    """
    lead = get_current_lead(state)
    if lead is None:
        return {"error": "No current lead found."}

    session_id = state.get("session_id", "unknown")
    print(f"\n[Personalizer] Target Lead: '{lead.name}' ({lead.company})")

    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=0.3,
    ).bind_tools(PERSONALIZER_TOOLS)

    messages = [
        SystemMessage(content=PERSONALIZER_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Please write a personalized outreach email for this lead:\n"
            f"Name: {lead.name}\n"
            f"Company: {lead.company}\n"
            f"Role: {lead.role}\n"
            f"Company Description: {lead.company_description}\n"
            f"Initial Personalization Angle: {lead.personalized_hook}\n"
            f"Session ID for memory calls: {session_id}"
        )),
    ]

    max_iterations = 8
    final_response = None

    for iteration in range(max_iterations):
        print(f"[Personalizer] LLM call {iteration + 1}/{max_iterations}...")
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            final_response = response
            print(f"[Personalizer] Complete after {iteration + 1} LLM call(s)")
            break

        print(f"[Personalizer] {len(response.tool_calls)} tool call(s) requested:")
        for tool_call in response.tool_calls:
            print(f"  -> {tool_call['name']}({tool_call['args']})")
            result = execute_tool_call(tool_call)
            log_result = result[:100] + "..." if len(result) > 100 else result
            print(f"    <- {log_result}")

            # The tool_call_id must match the ID the LLM assigned to the request.
            # Without this, the LLM can't correlate result to request.
            messages.append(ToolMessage(
                content=result,
                tool_call_id=tool_call["id"],
            ))

    if final_response is None:
        return {
            "messages": messages,
            "error": f"Personalizer reached max iterations ({max_iterations}).",
        }

    print(f"[Personalizer] Outreach Copy: {len(final_response.content)} characters")
    return {"messages": messages, "error": None}
