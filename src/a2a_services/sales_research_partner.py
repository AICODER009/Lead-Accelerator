import json
import logging
import os
import sys
import uvicorn
from fastapi import FastAPI

# Add parent directories to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers.request_handler import RequestHandler
from a2a.types import (
    AgentCard, AgentCapabilities, Message, Task, TaskQueryParams,
    TaskIdParams, MessageSendParams, TaskPushNotificationConfig,
    GetTaskPushNotificationConfigParams, ListTaskPushNotificationConfigParams,
    DeleteTaskPushNotificationConfigParams
)
from a2a.server.context import ServerCallContext
from a2a.client import create_text_message_object

# CrewAI imports
from crewai import Agent, Task as CrewTask, Crew

logger = logging.getLogger("SalesResearchPartnerService")

class ResearchPartnerRequestHandler(RequestHandler):
    async def on_get_task(self, params: TaskQueryParams, context: ServerCallContext | None = None) -> Task | None:
        return None

    async def on_cancel_task(self, params: TaskIdParams, context: ServerCallContext | None = None) -> Task | None:
        return None

    async def on_message_send(
        self,
        params: MessageSendParams,
        context: ServerCallContext | None = None,
    ) -> Message:
        msg = params.message
        text_content = ""
        if msg.parts:
            for part in msg.parts:
                if hasattr(part, "text") and part.text:
                    text_content += part.text
                elif hasattr(part, "root"):
                    root = part.root
                    if hasattr(root, "text") and root.text:
                        text_content += root.text

        logger.info(f"Received Sales Research Partner query: {text_content}")

        # Construct a CrewAI Agent and run a B2B sales research task
        try:
            # Import our custom LLM to bind to gpt-5.2 and keep consistent
            from utils.llm import ChatOpenAI
            llm = ChatOpenAI(model="gpt-5.2", api_key=os.getenv("OPENAI_API_KEY"), temperature=0.2)

            # Let's import our tools
            from agents.personalizer import tool_search_notes, tool_read_file, tool_list_files

            researcher_agent = Agent(
                role="B2B Copywriting & Competitor Researcher",
                goal="Conduct high-quality B2B marketing/copywriting analysis and competitor search using local B2B pitch materials.",
                backstory="You are an expert sales strategist and copywriting coach. You specialize in analyzing value propositions, competitor positions, and case studies to extract optimal messaging angles.",
                verbose=True,
                allow_delegation=False,
                llm=llm,
                tools=[tool_list_files, tool_search_notes, tool_read_file]
            )

            research_task = CrewTask(
                description=f"Using the available tools to list, search, and read local B2B pitch materials, perform detailed grounding/competitor research for the following query: '{text_content}'",
                expected_output="A structured research report containing specific case studies, key messaging points, value hooks, or competitor differentiators grounded strictly in our local materials.",
                agent=researcher_agent
            )

            crew = Crew(
                agents=[researcher_agent],
                tasks=[research_task],
                verbose=True
            )

            # Execute the crew task
            logger.info("Executing CrewAI task...")
            import asyncio
            result = await asyncio.to_thread(crew.kickoff)
            logger.info(f"CrewAI task complete. Result length: {len(str(result))}")

            return create_text_message_object(
                role="agent",
                content=str(result)
            )

        except Exception as e:
            logger.error(f"Error executing CrewAI: {e}")
            return create_text_message_object(
                role="agent",
                content=f"Error executing CrewAI sales research partner: {e}"
            )

    async def on_set_task_push_notification_config(self, params: TaskPushNotificationConfig, context: ServerCallContext | None = None) -> TaskPushNotificationConfig:
        return params

    async def on_get_task_push_notification_config(self, params: TaskIdParams | GetTaskPushNotificationConfigParams, context: ServerCallContext | None = None) -> TaskPushNotificationConfig:
        return TaskPushNotificationConfig(task_id=params.id, push_notification_config={})

    async def on_list_task_push_notification_config(self, params: ListTaskPushNotificationConfigParams, context: ServerCallContext | None = None) -> list[TaskPushNotificationConfig]:
        return []

    async def on_delete_task_push_notification_config(self, params: DeleteTaskPushNotificationConfigParams, context: ServerCallContext | None = None) -> None:
        pass

    async def on_message_send_stream(self, params, context: ServerCallContext | None = None):
        pass

    async def on_resubscribe_to_task(self, params, context: ServerCallContext | None = None):
        pass

def create_app() -> FastAPI:
    agent_card = AgentCard(
        name="CrewAI Sales Research Partner",
        version="1.0.0",
        description="An A2A service wrapping a CrewAI research agent that analyzes B2B copywriting, competitor dynamics, and grounds outreach ideas.",
        url="http://localhost:9002",
        preferred_transport="jsonrpc",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[],
    )
    handler = ResearchPartnerRequestHandler()
    a2a_app = A2AFastAPIApplication(agent_card=agent_card, http_handler=handler)
    
    app = FastAPI(title="A2A CrewAI Sales Research Partner")
    a2a_app.add_routes_to_app(app)
    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    port = int(os.getenv("STUDY_BUDDY_PORT", 9002))
    uvicorn.run(app, host="127.0.0.1", port=port)
