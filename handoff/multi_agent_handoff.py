import os
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
    """Create a tool definition for handoff to another agent."""
    return {
        "type": "function",
        "function": {
            "name": f"handoff_to_{target_agent.name.lower().replace(' ', '_')}",
            "description": f"Handoff the query to the {target_agent.name} ({target_agent.handoff_description})",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
    }

async def run_agent(initial_agent, query):
    """Custom runner implementation for agents with handoff support.
    
    This is a simple asynchronous runner that handles agent execution, tool calls (including handoffs),
    and switches agents when a handoff tool is called. It uses OpenAI's chat completions API directly
    for full control.
    
    Returns the final response from the agent.
    """
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
                # Handle handoff tools
                if tool_name.startswith("handoff_to_"):
                    target_name = tool_name.replace("handoff_to_", "").replace("_", " ").title()
                    # Switch to the target agent (in a real setup, map names to agents)
                    if target_name == "History Tutor":
                        current_agent = history_tutor_agent
                    elif target_name == "Math Tutor":
                        current_agent = math_tutor_agent
                    else:
                        raise ValueError(f"Unknown handoff target: {target_name}")
                    
                    # Append a tool response to confirm handoff (required for the API loop)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": "Handoff successful. Now handling with the new agent."
                    })
                    
                    # Update system prompt for the new agent
                    messages[0] = {"role": "system", "content": current_agent.instructions}
            
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

# Triage agent with handoff tools
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question. Use the handoff tools to route to the appropriate specialist.",
    tools=[
        create_handoff_tool(history_tutor_agent),
        create_handoff_tool(math_tutor_agent)
    ]
)

# Example usage
import asyncio

async def main():
    query = "What is the capital of France?"
    result = await run_agent(triage_agent, query)
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
