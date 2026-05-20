import asyncio
import logging
from a2a.client.client_factory import ClientFactory
from a2a.types import Message
from a2a.client import create_text_message_object

logger = logging.getLogger(__name__)

async def call_a2a_agent_async(agent_url: str, message_content: str) -> str:
    """
    Connect to a remote A2A agent, send a text message, and aggregate the response text.
    """
    logger.info(f"Connecting to A2A agent at {agent_url}...")
    client = await ClientFactory.connect(agent_url)
    try:
        msg = create_text_message_object(content=message_content)
        final_text = ""
        
        async for event in client.send_message(msg):
            if isinstance(event, Message):
                for part in event.parts:
                    # parts is a list of Part, each Part has a root which could be a TextPart
                    if hasattr(part, "text") and part.text:
                        final_text += part.text
                    elif hasattr(part, "root"):
                        root = part.root
                        if hasattr(root, "text") and root.text:
                            final_text += root.text
            elif isinstance(event, tuple):
                # ClientEvent: (Task, UpdateEvent)
                task, update = event
                if update and hasattr(update, "content") and update.content:
                    final_text += update.content
                elif task and hasattr(task, "artifacts") and task.artifacts:
                    # Check if there are any text artifacts
                    for art in task.artifacts:
                        if hasattr(art, "content") and art.content:
                            final_text += str(art.content)
                            
        # If still empty, try to get the last message from client task history
        if not final_text.strip():
            logger.warning("Empty response from A2A stream, check fallback messaging.")
            
        return final_text.strip()
    except Exception as e:
        logger.error(f"Error calling A2A agent at {agent_url}: {e}")
        raise e
    finally:
        await client.close()

def call_a2a_agent(agent_url: str, message_content: str) -> str:
    """
    Synchronous wrapper to call a remote A2A agent.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Run in a thread or separate runner to avoid blocking the loop
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(call_a2a_agent_async(agent_url, message_content))
    else:
        return asyncio.run(call_a2a_agent_async(agent_url, message_content))
