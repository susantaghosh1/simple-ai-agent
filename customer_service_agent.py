import openai
import os
import json
from datetime import datetime
import tiktoken

openai.api_key = os.getenv("OPENAI_API_KEY")

TODO_FILE = "todos.json"

main_agent_history = []
technical_support_history = []
billing_history = []

CONTEXT_WINDOW_LIMIT = 128000
CONTEXT_THRESHOLD = 0.7
TOKENIZER = tiktoken.encoding_for_model("gpt-4o")

def estimate_tokens(messages):
    total_tokens = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, dict):
            content = json.dumps(content)
        total_tokens += len(TOKENIZER.encode(content))
    return total_tokens

def summarize_chat_history(history):
    history_str = json.dumps(history, indent=2)
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert summarizer for a customer service system. Summarize the provided chat history into a concise, clear narrative  that retains critical details for ongoing interactions. Include:"
                    "\n- Key customer queries and their context (e.g., specific issues like billing errors or technical problems)."
                    "\n- Tasks created, their status (pending, in_progress, completed), and priorities."
                    "\n- Actions taken by sub-agents (e.g., technical support or billing resolutions)."
                    "\n- Current progress and unresolved issues."
                    "\n- Relevant outcomes (e.g., refunds issued, solutions provided)."
                    "\nExclude redundant details, internal tool call data, and timestamps unless critical. Ensure the summary is professional, focused, and suitable for maintaining conversation continuity."
                )
            },
            {"role": "user", "content": f"Summarize this chat history:\n{history_str}"}
        ]
    )
    summary = response.choices[0].message.content
    return [{
        "role": "system",
        "content": f"Summarized chat history: {summary}",
        "timestamp": datetime.now().isoformat()
    }]

def load_todos():
    if os.path.exists(TODO_FILE):
        with open(TODO_FILE, "r") as f:
            return json.load(f)
    return []

def save_todos(todos):
    with open(TODO_FILE, "w") as f:
        json.dump(todos, f, indent=4)

def todo_write(todos):
    save_todos(todos)
    return {"success": True, "message": "Todo list updated and persisted to file."}

def todo_read():
    todos = load_todos()
    return {"todos": todos}

def consult_technical_support(query):
    technical_support_history.append({
        "role": "user",
        "content": query,
        "timestamp": datetime.now().isoformat()
    })
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a technical support specialist. Provide detailed technical assistance based on the query, using the provided conversation history for context."}
        ] + technical_support_history
    )
    response_content = response.choices[0].message.content
    technical_support_history.append({
        "role": "assistant",
        "content": response_content,
        "timestamp": datetime.now().isoformat()
    })
    return {"response": response_content}

def consult_billing(query):
    billing_history.append({
        "role": "user",
        "content": query,
        "timestamp": datetime.now().isoformat()
    })
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a billing specialist. Handle queries related to payments, invoices, refunds, and account balances, using the provided conversation history for context."}
        ] + billing_history
    )
    response_content = response.choices[0].message.content
    billing_history.append({
        "role": "assistant",
        "content": response_content,
        "timestamp": datetime.now().isoformat()
    })
    return {"response": response_content}

tools = [
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": "Create or update the structured task list for the current customer service session. This helps track progress, organize complex queries, and provide visibility to the customer. Persists to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "The full list of todo items to set (overwrites existing list).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique ID for the task (e.g., 'task1')."
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Description of the task."
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "Status of the task."
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Priority of the task."
                                }
                            },
                            "required": ["id", "content", "status", "priority"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "todo_read",
            "description": "Read the current todo list for the session from the persisted file. Use this frequently to check progress and plan next steps. Takes no parameters.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consult_technical_support",
            "description": "Delegate a query to the technical support sub-agent for specialized technical assistance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to send to the technical support sub-agent."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consult_billing",
            "description": "Delegate a query to the billing sub-agent for handling payments, invoices, or account-related issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to send to the billing sub-agent."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

system_prompt = """
You are a professional customer service agent designed to resolve queries efficiently across multiple conversation turns. You have access to specialized tools for task management and sub-agents for executing specific tasks. Separate in-memory chat histories are maintained for the main agent and each sub-agent to provide context for ongoing conversations.

## Task Management Tools
- **todo_write**: Create or update a structured task list for the session, persisted to a file. Use this to plan and track progress.
- **todo_read**: Retrieve the current task list from the file. Use this to review progress and plan next steps.

Use these task management tools frequently to ensure accurate tracking and transparency with the customer. They are essential for breaking down complex queries into manageable steps and preventing oversight.

**When to use task management tools:**
- For complex, multi-step queries (e.g., troubleshooting requiring verification and resolution)
- When queries involve multiple domains (e.g., technical and billing)
- On receiving a new query: Create a todo list with todo_write
- Before starting a task: Use todo_read to review, then mark as in_progress with todo_write
- After completing a task: Mark as completed with todo_write and add follow-up tasks if needed
- Before deciding next steps: Use todo_read to identify pending tasks
- After updates: Use todo_read to verify changes
- When responding to the customer: Use todo_read to include progress updates
- At session start: Use todo_read to check for prior pending tasks
- When uncertain about next steps or when the customer asks about plans or progress

**When NOT to use:** For simple, single-step queries (e.g., "What is your support email?").

Mark tasks as completed immediately after finishing to maintain an accurate task status.

## Sub-Agent Tools
- **consult_technical_support**: Delegates queries to a technical support sub-agent with its own conversation history for specialized assistance.
- **consult_billing**: Delegates queries to a billing sub-agent with its own conversation history for issues related to payments, invoices, or accounts.
- (Additional sub-agents may be available, e.g., sales, general inquiries.)

Use sub-agent tools to execute specific actions required by your todo list. For example, delegate technical issues to consult_technical_support and billing issues to consult_billing.


## Example Workflow
**Customer Query (Turn 1):** "My internet is slow, and I was charged twice."
**Agent Response:** "I'll assist you promptly. Here's the plan:"
- Create tasks with todo_write: Verify account (pending, high), Investigate internet speed (pending, high), Check billing (pending, medium)
- Delegate tasks to sub-agents (consult_technical_support, consult_billing), which use their own histories
- Update task statuses with todo_write and review with todo_read
- Summarize progress in the response
**Customer Query (Turn 2):** "Any updates on my billing issue?"
**Agent Response:** Use todo_read to check task status and main agent history (or its summary) for context, then respond with progress (e.g., "Billing issue resolved; refund processed.") and any next steps.

## Operational Guidelines
- **Single Response per Turn:** Return one message per turn summarizing the resolution or progress for the customer. Internal results are not visible unless included in this summary.
- **Stateless with In-Memory History:** Each invocation uses in-memory chat histories (main agent and sub-agents) for context. If the main agent history is too large, it is summarized to stay within token limits.
- **Output Reliability:** Your outputs are generally trusted.
- **Task Clarity:** Specify whether the task involves writing code or performing research (e.g., file reads, web searches) in your plan.


"""

def handle_customer_query(customer_query):
    main_agent_history.append({
        "role": "user",
        "content": customer_query,
        "timestamp": datetime.now().isoformat()
    })
    token_count = estimate_tokens(main_agent_history + [{"role": "system", "content": system_prompt}])
    if token_count > CONTEXT_WINDOW_LIMIT * CONTEXT_THRESHOLD:
        main_agent_history[:] = summarize_chat_history(main_agent_history)
    messages = [
        {"role": "system", "content": system_prompt}
    ] + main_agent_history
    while True:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        assistant_message = response.choices[0].message
        main_agent_history.append({
            "role": assistant_message.role,
            "content": assistant_message.content,
            "tool_calls": assistant_message.tool_calls,
            "timestamp": datetime.now().isoformat()
        })
        token_count = estimate_tokens(main_agent_history + [{"role": "system", "content": system_prompt}])
        if token_count > CONTEXT_WINDOW_LIMIT * CONTEXT_THRESHOLD:
            main_agent_history[:] = summarize_chat_history(main_agent_history)
        if not assistant_message.tool_calls:
            return assistant_message.content
        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            if function_name == "todo_write":
                result = todo_write(function_args["todos"])
            elif function_name == "todo_read":
                result = todo_read()
            elif function_name == "consult_technical_support":
                result = consult_technical_support(function_args["query"])
            elif function_name == "consult_billing":
                result = consult_billing(function_args["query"])
            else:
                result = {"error": "Unknown function"}
            main_agent_history.append({
                "role": "tool",
                "content": json.dumps(result),
                "tool_call_id": tool_call.id,
                "timestamp": datetime.now().isoformat()
            })
            token_count = estimate_tokens(main_agent_history + [{"role": "system", "content": system_prompt}])
            if token_count > CONTEXT_WINDOW_LIMIT * CONTEXT_THRESHOLD:
                main_agent_history[:] = summarize_chat_history(main_agent_history)
            messages.append({
                "role": "tool",
                "content": json.dumps(result),
                "tool_call_id": tool_call.id
            })

if __name__ == "__main__":
    queries = [
        "My order #12345 hasn't arrived, and I was charged twice. Can you help?",
        "Any updates on my billing issue?"
    ]
    for query in queries:
        print(f"\nCustomer Query: {query}")
        response = handle_customer_query(query)
        print("Agent Response:\n", response)
