import os
import json
from openai import OpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


class ChatOpenAI:
    """
    A custom drop-in replacement for langchain_openai.ChatOpenAI and langchain_ollama.ChatOllama.
    
    This avoids severe dependency version conflicts between litellm, crewai, and
    langchain-openai while keeping the exact same LangChain-style `.invoke()` 
    syntax and message payload classes (SystemMessage, HumanMessage, ToolMessage) across our nodes.
    It natively supports tool calling and auto-handles OpenAI's strict tool/assistant schema rules.
    """
    def __init__(
        self, 
        model: str = None, 
        api_key: str = None, 
        temperature: float = 0.1, 
        format: str = None,
        model_kwargs: dict = None
    ):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.2")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.temperature = temperature
        self.tools = []
        
        self.response_format = None
        if format == "json":
            self.response_format = {"type": "json_object"}
        elif model_kwargs and "response_format" in model_kwargs:
            self.response_format = model_kwargs["response_format"]

    def bind_tools(self, tools: list) -> "ChatOpenAI":
        self.tools = tools
        return self

    def _convert_tool(self, tool) -> dict:
        """Convert a LangChain tool object into OpenAI tool schema format."""
        try:
            from langchain_core.utils.function_calling import convert_to_openai_tool
            return convert_to_openai_tool(tool)
        except Exception:
            # Fallback manual conversion in case of import/compatibility issues
            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.args,
                        "required": list(tool.args.keys())
                    }
                }
            }

    def invoke(self, messages: list) -> AIMessage:
        client = OpenAI(api_key=self.api_key)
        
        formatted_messages = []
        for m in messages:
            if isinstance(m, SystemMessage):
                formatted_messages.append({"role": "system", "content": m.content})
            elif isinstance(m, HumanMessage):
                formatted_messages.append({"role": "user", "content": m.content})
            elif isinstance(m, AIMessage):
                msg = {"role": "assistant", "content": m.content or ""}
                if m.tool_calls:
                    openai_tool_calls = []
                    for tc in m.tool_calls:
                        openai_tool_calls.append({
                            "id": tc.get("id"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("args"))
                            }
                        })
                    msg["tool_calls"] = openai_tool_calls
                formatted_messages.append(msg)
            elif isinstance(m, ToolMessage):
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content
                })
            elif hasattr(m, "type"):
                role = "user" if m.type == "human" else "system" if m.type == "system" else "assistant"
                formatted_messages.append({"role": role, "content": m.content})
            else:
                formatted_messages.append({"role": "user", "content": str(m)})
            
        kwargs = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": self.temperature,
        }
        if self.response_format:
            kwargs["response_format"] = self.response_format
            
        if self.tools:
            kwargs["tools"] = [self._convert_tool(t) for t in self.tools]
            
        response = client.chat.completions.create(**kwargs)
        message = response.choices[0].message
        
        tool_calls = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                    "id": tc.id
                })
                
        return AIMessage(content=message.content or "", tool_calls=tool_calls)
