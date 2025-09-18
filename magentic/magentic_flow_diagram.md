[Start]
   |
   v
[Initialize MagenticContext]
   - task, participant_descriptions
   - chat_history=[], facts="", plan=""
   - round_count=0, stall_count=0, reset_count=0
   |
   v
[manager.plan()]
   - LLM: ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT -> context.facts
   - LLM: ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT -> context.plan
   - String format: ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT -> task_ledger
   - context.add_message("assistant", task_ledger, "Manager")
   |
   v
[Set is_completed=False]
   |
   v
[While round_count < max_round_count and not is_completed]
   |
   v
[Check max_reset_count]
   - If reset_count > max_reset_count: Return partial result, Exit
   |
   v
[Increment round_count]
   |
   v
[manager.create_progress_ledger()]
   - LLM: ORCHESTRATOR_PROGRESS_LEDGER_PROMPT
     (with task, team, facts, plan, chat_history)
   - Returns ProgressLedger:
     - is_request_satisfied
     - is_in_loop
     - is_progress_being_made
     - next_speaker
     - instruction_or_question
   |
   v
[Check is_request_satisfied]
   - If True:
     - Set is_completed=True
     - manager.prepare_final_answer() (LLM)
     - Return final answer, Exit
   |
   v
[Check Stall: !is_progress_being_made or is_in_loop]
   - If True:
     - Increment stall_count
     - If stall_count > max_stall_count:
       - manager.replan() (LLM for facts/plan, string format for ledger)
       - context.reset()
       - Add new ledger to chat_history
       - Continue loop
     - Else: Log "Progress stalled, but continuing..."
   |
   v
[Select next_speaker]
   - If invalid speaker: Log error, Break
   - Add instruction_or_question to chat_history ("assistant", "Manager")
   |
   v
[agent.respond()]
   - LLM: Uses task, plan, instruction, chat_history
   - Add response to chat_history ("user", agent name)
   |
   v
[Loop Back]
   |
   v
[If max_round_count reached]
   - Return partial result, Exit
