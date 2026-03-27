from crewai import Task

def create_tasks(transcript, planner, validator, executor, recovery, logger):
    plan_task = Task(
        description=f"Analyze the following transcript and extract a list of action items with suggested owners.\n\nTranscript:\n{transcript}",
        expected_output="A structured list of action items and their owners.",
        agent=planner
    )

    validate_task = Task(
        description="Review the list of action items. If any item is missing an owner or the owner is ambiguous, use the ask_human_clarification tool to get an explicit owner.",
        expected_output="A validated list of action items where every item has a clear, definitive owner.",
        agent=validator,
        context=[plan_task]
    )

    execute_task = Task(
        description=(
            "For each validated action item, use create_task_in_system to create it in the system. "
            "Then, use send_summary_email to send a final summary email to 'team@example.com'. "
            "IMPORTANT: If any tool returns an ERROR, DO NOT retry. Just note the exact error in your report."
        ),
        expected_output="A status report detailing all successful actions and explicitly listing any ERRORs encountered.",
        agent=executor,
        context=[validate_task]
    )

    recover_task = Task(
        description=(
            "Carefully review the execution report. Find any ERRORs for creating tasks or sending emails. "
            "If found, retry those specific actions using your tools over and over until you receive a SUCCESS."
        ),
        expected_output="A recovery report proving that all previously failed tasks are now successful.",
        agent=recovery,
        context=[execute_task]
    )

    log_task = Task(
        description=(
            "Take the final recovered execution status and use log_audit_trail to log the complete outcome of this workflow. "
            "Summarize the plan, what failed, and what was recovered into a single log entry."
        ),
        expected_output="Confirmation that the workflow was securely logged via the logging tool.",
        agent=logger,
        context=[plan_task, validate_task, execute_task, recover_task]
    )
    
    return [plan_task, validate_task, execute_task, recover_task, log_task]
