import json
import logging
import os
import sys
import uvicorn
from fastapi import FastAPI

# Set IS_QUIZ_SERVICE before imports to ensure objection_simulator does not delegate recursively
os.environ["IS_QUIZ_SERVICE"] = "true"

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
from agents.objection_simulator import generate_objections, grade_response

logger = logging.getLogger("ObjectionService")

class ObjectionServiceRequestHandler(RequestHandler):
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

        logger.info(f"Received message content: {text_content}")

        if "generate_objections" in text_content:
            try:
                payload = text_content.split("generate_objections:", 1)[1].strip()
                data = json.loads(payload)
                lead_name = data["lead_name"]
                company = data["company"]
                explanation = data["explanation"]
                n = data.get("n", 3)
            except Exception as e:
                logger.error(f"Failed to parse generate_objections payload: {e}")
                return create_text_message_object(
                    role="agent",
                    content=json.dumps({"error": f"Invalid payload: {e}"})
                )

            objs = generate_objections(lead_name, company, explanation, n=n)
            return create_text_message_object(
                role="agent",
                content=json.dumps({"questions": objs})
            )

        elif "grade_response" in text_content:
            try:
                payload = text_content.split("grade_response:", 1)[1].strip()
                data = json.loads(payload)
                question = data["question"]
                expected = data["expected"]
                sdr_response = data.get("sdr_response") or data.get("student_answer", "")
            except Exception as e:
                logger.error(f"Failed to parse grade_response payload: {e}")
                return create_text_message_object(
                    role="agent",
                    content=json.dumps({"error": f"Invalid payload: {e}"})
                )

            grade = grade_response(question, expected, sdr_response)
            return create_text_message_object(
                role="agent",
                content=json.dumps(grade)
            )

        return create_text_message_object(
            role="agent",
            content="Unknown command. Objection Service supports 'generate_objections' and 'grade_response'."
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
        name="B2B Sales Objection Simulator Service",
        version="1.0.0",
        description="An A2A service that generates realistic B2B buyer objections and grades SDR objection handling responses.",
        url="http://localhost:9001",
        preferred_transport="jsonrpc",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[],
    )
    handler = ObjectionServiceRequestHandler()
    a2a_app = A2AFastAPIApplication(agent_card=agent_card, http_handler=handler)
    
    app = FastAPI(title="A2A B2B Sales Objection Simulator Service")
    a2a_app.add_routes_to_app(app)
    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    port = int(os.getenv("QUIZ_SERVICE_PORT", 9001))
    uvicorn.run(app, host="127.0.0.1", port=port)
