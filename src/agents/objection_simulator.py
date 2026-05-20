import json
import os
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from utils.llm import ChatOpenAI

from graph.state import SimulationQuestion, SimulationResult, get_current_lead

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.2")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

GENERATION_PROMPT = """You are an expert sales objection designer for B2B tech cold outreach.

Given a prospect profile, company bio, and a drafted cold outreach email, generate {n} critical objection scenarios that this specific prospect is highly likely to raise.

Good objections:
  - Challenge the core value proposition based on the prospect's industry/company profile.
  - Represent realistic B2B pushbacks (e.g., budget/ROI concerns, internal resource constraints, existing competitor locking, timing, security/data privacy).
  - Require the salesperson/outreach copy to demonstrate deep understanding and strong objection handling.

Return ONLY valid JSON with no prose or markdown:
{{
  "questions": [
    {{
      "question": "Specific, realistic prospect objection text ending with ?",
      "expected_answer": "Model response/argument in 1-3 sentences that smoothly handles this objection",
      "difficulty": "easy|medium|hard"
    }}
  ]
}}

Rules:
  - Include at least one highly specific objection addressing budget/ROI or a direct competitor.
  - expected_answer should be concise, professional, and convincing.
  - Avoid generic questions. Make it sound like a real prospect pushing back.
"""

GRADING_PROMPT = """You are an expert sales manager coaching a B2B sales development representative (SDR).

Objection raised by Prospect: {question}
Model Best Practice handling: {expected_answer}
SDR's actual response: {sdr_response}

Grade the SDR's response honestly. Be generous with partial credit:
  - Professional, disarming, and addresses the concern: 0.7-0.9
  - Good concept but slightly defensive or wordy: 0.5-0.7
  - Partially correct but misses the core hook/value: 0.3-0.5
  - Defiant, defensive, or completely off-topic: 0.0-0.2

Return ONLY valid JSON with no prose or markdown:
{{
  "correct": true,
  "score": 0.85,
  "feedback": "One specific sentence of coaching feedback",
  "missing_concept": "Key value proposition or emotional hook missed, or empty string if response is perfect"
}}
"""


def generate_objections_local(lead_name: str, company: str, explanation: str, n: int = 3) -> list[dict]:
    """Generate n B2B sales objections from the outreach copy draft locally using LLM."""
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=0.4,
        format="json",
    )

    prompt = GENERATION_PROMPT.format(n=n)
    try:
        response = llm.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"Lead: {lead_name} at {company}\n\nEmail Draft:\n{explanation}"),
        ])
        data = json.loads(response.content)
        questions = data.get("questions", [])
        if questions and isinstance(questions, list):
            return questions
    except Exception as e:
        print(f"[Objection Simulator] LLM call failed during objection generation: {e}")

    # Fallback: one generic objection
    return [{
        "question": f"We are currently happy with our current processes. Why should we hop on a call with you?",
        "expected_answer": "Validate their satisfaction, reference a key outcome, and ask an open ended question about their current scaling speed.",
        "difficulty": "medium",
    }]


def generate_objections(lead_name: str, company: str, explanation: str, n: int = 3) -> list[dict]:
    """Generate objections, delegating to A2A Objection Service if configured."""
    use_a2a = os.getenv("USE_A2A_QUIZ", "false").lower() == "true"
    is_quiz_service = os.getenv("IS_QUIZ_SERVICE", "false").lower() == "true"

    if use_a2a and not is_quiz_service:
        from utils.a2a_client import call_a2a_agent
        url = os.getenv("QUIZ_SERVICE_URL", "http://localhost:9001")
        payload = json.dumps({
            "lead_name": lead_name,
            "company": company,
            "explanation": explanation,
            "n": n
        })
        try:
            print(f"[Objection Simulator] Delegating generate_objections to A2A service at {url}")
            res_str = call_a2a_agent(url, f"generate_objections: {payload}")
            data = json.loads(res_str)
            return data.get("questions", [])
        except Exception as e:
            print(f"[Objection Simulator] A2A call failed, falling back to local: {e}")
            return generate_objections_local(lead_name, company, explanation, n)
    else:
        return generate_objections_local(lead_name, company, explanation, n)


def grade_response_local(question: str, expected: str, sdr_response: str) -> dict:
    """Grade SDR objection-handling response locally using LLM-as-judge."""
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        temperature=0.1,   # Analytical: grading must be consistent
        format="json",
    )

    prompt = GRADING_PROMPT.format(
        question=question,
        expected_answer=expected,
        sdr_response=sdr_response,
    )

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return json.loads(response.content)
    except Exception as e:
        print(f"[Objection Simulator] LLM call failed during grading: {e}")
        return {
            "correct": False,
            "score": 0.5,
            "feedback": "Could not grade automatically. Please review manually.",
            "missing_concept": "",
        }


def grade_response(question: str, expected: str, sdr_response: str) -> dict:
    """Grade response, delegating to A2A Objection Service if configured."""
    use_a2a = os.getenv("USE_A2A_QUIZ", "false").lower() == "true"
    is_quiz_service = os.getenv("IS_QUIZ_SERVICE", "false").lower() == "true"

    if use_a2a and not is_quiz_service:
        from utils.a2a_client import call_a2a_agent
        url = os.getenv("QUIZ_SERVICE_URL", "http://localhost:9001")
        payload = json.dumps({
            "question": question,
            "expected": expected,
            "sdr_response": sdr_response,
            "student_answer": sdr_response  # backwards compatibility with older quiz servers
        })
        try:
            print(f"[Objection Simulator] Delegating grade_response to A2A service at {url}")
            res_str = call_a2a_agent(url, f"grade_response: {payload}")
            return json.loads(res_str)
        except Exception as e:
            print(f"[Objection Simulator] A2A call failed, falling back to local: {e}")
            return grade_response_local(question, expected, sdr_response)
    else:
        return grade_response_local(question, expected, sdr_response)


def run_simulation(lead_name: str, company: str, explanation: str) -> SimulationResult:
    """Run an interactive objection handling simulation in the terminal."""
    print(f"\n{'='*60}")
    print(f"Objection Simulation: {lead_name} ({company})")
    print(f"{'='*60}")
    print("Respond to each prospect objection in your own words. Press Enter to submit.\n")

    objections_data = generate_objections(lead_name, company, explanation, n=3)
    graded_questions = []
    total_score = 0.0
    weak_areas = []

    for i, q_data in enumerate(objections_data, 1):
        question_text = q_data["question"]
        expected = q_data["expected_answer"]
        difficulty = q_data.get("difficulty", "medium")

        print(f"Objection {i} [{difficulty}]: {question_text}")
        
        if os.getenv("STREAMLIT_RUN", "false").lower() == "true":
            # Autonomous Demo Mode: Generate Simulated SDR Response using LLM
            print("[Objection Simulator] Autonomous Mode: Simulating SDR response...")
            sdr_llm = ChatOpenAI(
                model=MODEL_NAME,
                api_key=OPENAI_API_KEY,
                temperature=0.7,
            )
            sim_prompt = f"You are a junior B2B SDR. Formulate a short, professional, and convincing 1-2 sentence response to this prospect objection: '{question_text}' based on this outreach copy draft: '{explanation}'"
            try:
                res = sdr_llm.invoke([HumanMessage(content=sim_prompt)])
                user_answer = res.content.strip()
                print(f"[Objection Simulator] Simulated SDR Response: {user_answer}")
            except Exception as e:
                print(f"[Objection Simulator] Failed to generate simulated response: {e}")
                user_answer = "We offer a highly optimized solution that scales B2B outreach automatically with grounded materials."
        else:
            user_answer = input("Your response: ").strip()
            
        if not user_answer:
            user_answer = "(no response provided)"

        print("Grading SDR response...")
        grade = grade_response(question_text, expected, user_answer)

        score = float(grade.get("score", 0.0))
        correct = bool(grade.get("correct", False))
        feedback = grade.get("feedback", "")
        missing = grade.get("missing_concept", "")

        total_score += score
        status = "[PASS]" if correct else "[FAIL]"
        print(f"{status} Score: {score:.0%}. {feedback}\n")

        if missing:
            weak_areas.append(missing)

        graded_questions.append(SimulationQuestion(
            question=question_text,
            expected_answer=expected,
            user_answer=user_answer,
            correct=correct,
            feedback=feedback,
            score=score,
        ))

    avg_score = total_score / len(objections_data) if objections_data else 0.0
    correct_count = sum(1 for q in graded_questions if q.correct)

    print(f"{'='*60}")
    print(f"Simulation complete! SDR Score: {avg_score:.0%} ({correct_count}/{len(graded_questions)} handled)")
    if weak_areas:
        print(f"Coaching Areas to Improve: {', '.join(set(weak_areas))}")
    print(f"{'='*60}\n")

    return SimulationResult(
        lead_name=lead_name,
        questions=graded_questions,
        score=avg_score,
        weak_areas=list(set(weak_areas)),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def objection_simulator_node(state: dict) -> dict:
    """
    LangGraph node: Objection Simulator

    Reads:  state["campaign"], state["current_lead_index"], state["messages"]
    Writes: state["simulation_results"], state["weak_areas"], state["error"]
    """
    lead = get_current_lead(state)
    if lead is None:
        return {"error": "No current lead. Lead Researcher must run first"}

    # Extract Personalizer's final response from message history.
    messages = state.get("messages", [])
    explanation = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
            explanation = msg.content
            break

    if not explanation:
        print("[Objection Simulator] Warning: no outreach copy found, generating generic simulation")
        explanation = f"Lead: {lead.name} from {lead.company}. {lead.company_description}"

    print(f"\n[Objection Simulator] Generating pitch objections for lead: '{lead.name}'")
    simulation_result = run_simulation(lead.name, lead.company, explanation)

    existing_results = state.get("simulation_results", []) or []
    all_weak_areas = list(set(
        (state.get("weak_areas", []) or []) + simulation_result.weak_areas
    ))

    return {
        "simulation_results": existing_results + [simulation_result],
        "weak_areas": all_weak_areas,
        "error": None,
        # Pass state forward explicitly to preserve it across interrupt/resume
        "campaign": state.get("campaign"),
        "current_lead_index": state.get("current_lead_index", 0),
        "session_id": state.get("session_id", ""),
    }
