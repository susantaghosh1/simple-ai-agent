import os
import openai
import json
from typing import List, Dict
import asyncio


openai.api_key = os.getenv("OPENAI_API_KEY")


async def call_llm(prompt: str, system_message: str = "You are a helpful assistant.", model: str = "gpt-4") -> str:
    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error in LLM call: {str(e)}"


ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT = """Below I will present you a request.

Before we begin addressing the request, please answer the following pre-survey to the best of your ability.
Keep in mind that you are Ken Jennings-level with trivia, and Mensa-level with puzzles, so there should be
a deep well to draw from.

Here is the request:

{{$task}}

Here is the pre-survey:

    1. Please list any specific facts or figures that are GIVEN in the request itself. It is possible that
       there are none.
    2. Please list any facts that may need to be looked up, and WHERE SPECIFICALLY they might be found.
       In some cases, authoritative sources are mentioned in the request itself.
    3. Please list any facts that may need to be derived (e.g., via logical deduction, simulation, or computation)
    4. Please list any facts that are recalled from memory, hunches, well-reasoned guesses, etc.

When answering this survey, keep in mind that "facts" will typically be specific names, dates, statistics, etc.
Your answer should use headings:

    1. GIVEN OR VERIFIED FACTS
    2. FACTS TO LOOK UP
    3. FACTS TO DERIVE
    4. EDUCATED GUESSES

DO NOT include any other headings or sections in your response. DO NOT list next steps or plans until asked to do so.
"""

ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT = """Fantastic. To address this request we have assembled the following team:

{{$team}}

Based on the team composition, and known and unknown facts, please devise a short bullet-point plan for addressing the
original request. Remember, there is no requirement to involve all team members -- a team member's particular expertise
may not be needed for this task.
"""

ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT = """
We are working to address the following user request:

{{$task}}

To answer this request we have assembled the following team:

{{$team}}

Here is an initial fact sheet to consider:

{{$facts}}

Here is the plan to follow as best as possible:

{{$plan}}
"""

ORCHESTRATOR_PROGRESS_LEDGER_PROMPT = """
Recall we are working on the following request:

{{$task}}

And we have assembled the following team:

{{$team}}

Here is the current fact sheet:

{{$facts}}

Here is the current plan:

{{$plan}}


To make progress on the request, please answer the following questions, including necessary reasoning:

    - Is the request fully satisfied? (True if complete, or False if the original request has yet to be
      SUCCESSFULLY and FULLY addressed)
    - Are we in a loop where we are repeating the same requests and / or getting the same responses as before?
      Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a
      handful of times.
    - Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent
      messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success
      such as the inability to read from a required file)
    - Who should speak next? (select from: {{$names}})
    - What instruction or question would you give this team member? (Phrase as if speaking directly to them, and
      include any specific information they may need)

Please output an answer in pure JSON format according to the following schema. The JSON object must be parsable as-is.
DO NOT OUTPUT ANYTHING OTHER THAN JSON, AND DO NOT DEVIATE FROM THIS SCHEMA:

{
    "is_request_satisfied": {
        "reason": string,
        "answer": boolean
    },
    "is_in_loop": {
        "reason": string,
        "answer": boolean
    },
    "is_progress_being_made": {
        "reason": string,
        "answer": boolean
    },
    "next_speaker": {
        "reason": string,
        "answer": string
    },
    "instruction_or_question": {
        "reason": string,
        "answer": string
    }
}
"""

ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT = """As a reminder, we are working to solve the following task:

{{$task}}

It's clear we aren't making as much progress as we would like, but we may have learned something new.
Please rewrite the following fact sheet, updating it to include anything new we have learned that may be helpful.

Example edits can include (but are not limited to) adding new guesses, moving educated guesses to verified facts
if appropriate, etc. Updates may be made to any section of the fact sheet, and more than one section of the fact
sheet can be edited. This is an especially good time to update educated guesses, so please at least add or update
one educated guess or hunch, and explain your reasoning.

Here is the old fact sheet:

{{$old_facts}}
"""

ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT = """Please briefly explain what went wrong on this last run (the root
cause of the failure), and then come up with a new plan that takes steps and/or includes hints to overcome prior
challenges and especially avoids repeating the same mistakes. As before, the new plan should be concise, be expressed
in bullet-point form, and consider the following team composition (do not involve any other outside people since we
cannot contact anyone else):

{{$team}}
"""

ORCHESTRATOR_FINAL_ANSWER_PROMPT = """
We are working on the following task:
{{$task}}

We have completed the task.

The above messages contain the conversation that took place to complete the task.

Based on the information gathered, provide the final answer to the original request.
The answer should be phrased as if you were speaking to the user.
"""


class MagenticContext:
    def __init__(self, task: str, participant_descriptions: Dict[str, str]):
        self.task = task
        self.participant_descriptions = participant_descriptions
        self.chat_history: List[Dict[str, str]] = []
        self.round_count = 0
        self.stall_count = 0
        self.reset_count = 0
        self.facts = ""
        self.plan = ""

    def reset(self):
        self.chat_history = []
        self.stall_count = 0
        self.reset_count += 1

    def add_message(self, role: str, content: str, name: str = None):
        message = {"role": role, "content": content}
        if name:
            message["name"] = name
        self.chat_history.append(message)


class ProgressLedger:
    def __init__(self, is_request_satisfied: bool, is_in_loop: bool, is_progress_being_made: bool, next_speaker: str, instruction_or_question: str):
        self.is_request_satisfied = is_request_satisfied
        self.is_in_loop = is_in_loop
        self.is_progress_being_made = is_progress_being_made
        self.next_speaker = next_speaker
        self.instruction_or_question = instruction_or_question


class Agent:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    async def respond(self, context: MagenticContext) -> str:
        prompt = f"""
        You are {self.name}, {self.description}.
        Task: {context.task}
        Current plan: {context.plan}
        Instruction: {context.chat_history[-1]['content'] if context.chat_history else 'Provide your input.'}
        Chat history: {json.dumps(context.chat_history, indent=2)}
        Provide a concise response to advance the task.
        """
        return await call_llm(prompt, system_message=f"You are {self.name}, an expert {self.description}.")


class MagenticManager:
    def __init__(self, max_stall_count: int = 3, max_round_count: int = 10, max_reset_count: int = None):
        self.max_stall_count = max_stall_count
        self.max_round_count = max_round_count
        self.max_reset_count = max_reset_count

    async def plan(self, context: MagenticContext) -> str:
        facts_prompt = ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT.replace("{{$task}}", context.task)
        context.facts = await call_llm(facts_prompt)
        team_str = json.dumps(context.participant_descriptions, indent=2)
        plan_prompt = ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT.replace("{{$team}}", team_str)
        context.plan = await call_llm(plan_prompt)
        return ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT.replace(
            "{{$task}}", context.task
        ).replace(
            "{{$team}}", team_str
        ).replace(
            "{{$facts}}", context.facts
        ).replace(
            "{{$plan}}", context.plan
        )

    async def replan(self, context: MagenticContext) -> str:
        facts_prompt = ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT.replace(
            "{{$task}}", context.task
        ).replace(
            "{{$old_facts}}", context.facts
        )
        context.facts = await call_llm(facts_prompt)
        team_str = json.dumps(context.participant_descriptions, indent=2)
        plan_prompt = ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT.replace("{{$team}}", team_str)
        context.plan = await call_llm(plan_prompt)
        return ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT.replace(
            "{{$task}}", context.task
        ).replace(
            "{{$team}}", team_str
        ).replace(
            "{{$facts}}", context.facts
        ).replace(
            "{{$plan}}", context.plan
        )

    async def create_progress_ledger(self, context: MagenticContext) -> ProgressLedger:
        team_str = json.dumps(context.participant_descriptions, indent=2)
        names = ", ".join(context.participant_descriptions.keys())
        prompt = ORCHESTRATOR_PROGRESS_LEDGER_PROMPT.replace(
            "{{$task}}", context.task
        ).replace(
            "{{$team}}", team_str
        ).replace(
            "{{$names}}", names
        ).replace(
            "{{$facts}}", context.facts
        ).replace(
            "{{$plan}}", context.plan
        )
        response = await call_llm(prompt, system_message="You are a task manager analyzing progress.")
        try:
            ledger_data = json.loads(response)
            return ProgressLedger(
                ledger_data["is_request_satisfied"]["answer"],
                ledger_data["is_in_loop"]["answer"],
                ledger_data["is_progress_being_made"]["answer"],
                ledger_data["next_speaker"]["answer"],
                ledger_data["instruction_or_question"]["answer"]
            )
        except Exception as e:
            print(f"Error parsing progress ledger: {e}")
            return ProgressLedger(
                False, False, True, 
                list(context.participant_descriptions.keys())[0], 
                "Continue with the next step."
            )

    async def prepare_final_answer(self, context: MagenticContext) -> str:
        prompt = ORCHESTRATOR_FINAL_ANSWER_PROMPT.replace("{{$task}}", context.task)
        return await call_llm(prompt)


class MagenticOrchestration:
    def __init__(self, agents: List[Agent], manager: MagenticManager):
        self.agents = {agent.name: agent for agent in agents}
        self.manager = manager

    async def run(self, task: str):
        context = MagenticContext(task, {agent.name: agent.description for agent in self.agents.values()})
        
        # Initial planning
        task_ledger = await self.manager.plan(context)
        context.add_message("assistant", task_ledger, "Manager")
        print(f"Initial Task Ledger:\n{task_ledger}\n")

        is_completed = False
        while context.round_count < self.manager.max_round_count and not is_completed:
            # Check reset limit
            if self.manager.max_reset_count is not None and context.reset_count > self.manager.max_reset_count:
                print("Max reset count reached.")
                partial_result = next(
                    (m["content"] for m in reversed(context.chat_history) if m["role"] == "assistant"),
                    "Stopped due to max reset limit. No partial result available."
                )
                print(f"Partial Result:\n{partial_result}")
                return partial_result

            context.round_count += 1

            # Evaluate progress
            progress = await self.manager.create_progress_ledger(context)
            print(f"Progress Ledger: {json.dumps(vars(progress), indent=2)}")

            # Check for completion
            if progress.is_request_satisfied:
                is_completed = True
                final_answer = await self.manager.prepare_final_answer(context)
                print(f"Final Answer:\n{final_answer}")
                return final_answer

            # Check for stalling
            if not progress.is_progress_being_made or progress.is_in_loop:
                context.stall_count += 1
                if context.stall_count > self.manager.max_stall_count:
                    print("Stalling detected. Replanning...")
                    task_ledger = await self.manager.replan(context)
                    context.reset()
                    context.add_message("assistant", task_ledger, "Manager")
                    print(f"Updated Task Ledger:\n{task_ledger}\n")
                    continue
                else:
                    print("Progress stalled, but continuing...")

            # Request next speaker
            next_speaker = progress.next_speaker
            if next_speaker not in self.agents:
                print(f"Error: Unknown speaker {next_speaker}")
                break

            context.add_message("assistant", progress.instruction_or_question, "Manager")
            print(f"Manager: {progress.instruction_or_question}")
            response = await self.agents[next_speaker].respond(context)
            context.add_message("user", response, next_speaker)
            print(f"{next_speaker}: {response}\n")

        print("Max rounds reached." if not is_completed else "Task completed.")
        partial_result = next(
            (m["content"] for m in reversed(context.chat_history) if m["role"] == "assistant"),
            "Stopped due to max round limit. No partial result available."
        )
        print(f"Partial Result:\n{partial_result}")
        return partial_result


async def main():
    agents = [
        Agent("Analyst", "expert in market research and data analysis"),
        Agent("Strategist", "expert in creating marketing strategies"),
        Agent("Writer", "expert in crafting marketing content")
    ]
    manager = MagenticManager(max_stall_count=3, max_round_count=10, max_reset_count=3)
    orchestration = MagenticOrchestration(agents, manager)
    
    task = "Plan a marketing campaign for a new eco-friendly product."
    await orchestration.run(task)

if __name__ == "__main__":
    asyncio.run(main())
