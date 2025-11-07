import os
import json
import openai
from openai import OpenAI

# Set up the OpenAI client (requires OPENAI_API_KEY environment variable)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class Agent:
    def __init__(self, name, instructions, handoff_description=None, tools=None):
        self.name = name
        self.instructions = instructions
        self.handoff_description = handoff_description
        self.tools = tools or []

def create_handoff_tool(target_agent):
    """Create a tool definition for handoff to another agent, including a required reason."""
    return {
        "type": "function",
        "function": {
            "name": f"handoff_to_{target_agent.name.lower().replace(' ', '_')}",
            "description": f"Handoff the query to the {target_agent.name} ({target_agent.handoff_description})",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Explain the reason for handing off to this agent."
                    }
                },
                "required": ["reason"]
            },
        }
    }

async def run_agent(initial_agent, query, tool_functions=None):
    """Custom runner implementation for agents with handoff support, structured handoff reasons, and general tool call handling.
    
    This is a simple asynchronous runner that handles agent execution, tool calls (including handoffs with reasons and other general tools),
    and switches agents when a handoff tool is called. It uses OpenAI's chat completions API directly for full control.
    The handoff reason is extracted from the tool call arguments (structured as JSON) and inserted into the conversation history for transparency.
    
    General tools are executed via the provided tool_functions dict (tool_name -> callable), and their results are appended back to the messages.
    
    Args:
        initial_agent: The starting Agent instance.
        query: The initial user query.
        tool_functions: Optional dict of tool_name to callable functions for non-handoff tools.
    
    Returns the final response from the agent.
    """
    tool_functions = tool_functions or {}
    current_agent = initial_agent
    messages = [
        {"role": "system", "content": current_agent.instructions},
        {"role": "user", "content": query}
    ]
    
    while True:
        response = await client.chat.completions.create(
            model="gpt-4o",  # Or any model you prefer, e.g., "gpt-3.5-turbo"
            messages=messages,
            tools=current_agent.tools or None,
            tool_choice="auto" if current_agent.tools else None
        )
        
        choice = response.choices[0]
        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls
            messages.append(choice.message)  # Add assistant's message with tool calls
            
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                # Parse the structured arguments (JSON)
                arguments = json.loads(tool_call.function.arguments)
                
                if tool_name.startswith("handoff_to_"):
                    # Handle handoff tools specially
                    target_name = tool_name.replace("handoff_to_", "").replace("_", " ").title()
                    reason = arguments.get("reason", "No reason provided")
                    
                    # Switch to the target agent (in a real setup, map names to agents)
                    if target_name == "History Tutor":
                        current_agent = history_tutor_agent
                    elif target_name == "Math Tutor":
                        current_agent = math_tutor_agent
                    else:
                        raise ValueError(f"Unknown handoff target: {target_name}")
                    
                    # Insert the handoff reason into the conversation history as an assistant message
                    messages.append({
                        "role": "assistant",
                        "content": f"Handing off to {current_agent.name}. Reason: {reason}"
                    })
                    
                    # Append a tool response to confirm handoff (required for the API loop)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": "Handoff successful."
                    })
                    
                    # Update system prompt for the new agent
                    messages[0] = {"role": "system", "content": current_agent.instructions}
                
                else:
                    # Handle general (non-handoff) tools
                    if tool_name not in tool_functions:
                        raise ValueError(f"Unknown tool: {tool_name}. No function provided.")
                    
                    # Execute the tool function with the arguments
                    try:
                        result = tool_functions[tool_name](**arguments)
                    except Exception as e:
                        result = f"Error executing tool {tool_name}: {str(e)}"
                    
                    # Append the tool result back to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result)
                    })
            
            # Continue the loop after handling tools
            continue
        else:
            # No more tool calls; return the final content
            return choice.message.content

# Define the agents (similar to your previous example)
history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly."
)

math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples."
)

# Triage agent with handoff tools (now requiring reasons)
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question. Use the handoff tools to route to the appropriate specialist, and always provide a reason in the tool call.",
    tools=[
        create_handoff_tool(history_tutor_agent),
        create_handoff_tool(math_tutor_agent)
    ]
)

# Example: Add a general tool to the Math Tutor for demonstration
def calculate_expression(expression: str) -> str:
    """A simple calculator tool that evaluates a math expression safely."""
    try:
        from math import sqrt, sin, cos, tan, pi, e  # Import safe math functions
        result = eval(expression, {"__builtins__": {}}, {"sqrt": sqrt, "sin": sin, "cos": cos, "tan": tan, "pi": pi, "e": e})
        return f"The result is {result}"
    except Exception as ex:
        return f"Error calculating: {str(ex)}"

math_tutor_agent.tools = [{
    "type": "function",
    "function": {
        "name": "calculate_expression",
        "description": "Evaluate a mathematical expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "The math expression to evaluate (e.g., '2 + 2')."}
            },
            "required": ["expression"]
        }
    }
}]

# Example usage with tool_functions
import asyncio

async def main():
    query = "What is the square root of 16?"  # This should handoff to Math Tutor and use the calculate tool
    tool_functions = {
        "calculate_expression": calculate_expression
    }
    result = await run_agent(triage_agent, query, tool_functions=tool_functions)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
