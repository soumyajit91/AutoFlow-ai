"""
main.py
=======
Standalone workflow orchestrator for the "Meeting to Action" multi-agent system.

Can be run directly:  python main.py
Also imported by app.py (Streamlit UI).

Workflow Steps (7 Agents):
  1. PlannerAgent       → builds the workflow plan
  2. UnderstandingAgent → extracts action items (LLM or rules)
  3. AssignmentAgent    → assigns owners with confidence scores (LLM or rules)
  4. ValidatorAgent     → resolves ambiguous owners via clarification
  5. ExecutorAgent      → creates tasks + sends email (mock API)
  6. RecoveryAgent      → retries failures, escalates if needed
  7. LoggerAgent        → writes structured JSON audit trail

LLM providers supported: Groq (free tier), Ollama (local), or Pure Rule-Based (no API).
"""

import os
import sys
import time
from typing import Any, Optional

from agents import (
    ActionItem,
    AssignmentAgent,
    ExecutorAgent,
    LoggerAgent,
    PlannerAgent,
    RecoveryAgent,
    UnderstandingAgent,
    ValidatorAgent,
    WorkflowContext,
)
from tools import clear_logs, LOGS_FILE

# ---------------------------------------------------------------------------
# LLM Client Factory
# ---------------------------------------------------------------------------

def build_llm_client(provider: str, api_key: str = "") -> tuple:
    """
    Returns (client, provider_name) ready for injection into WorkflowContext.
    Falls back to (None, 'rule_based') on any error.
    """
    if provider == "groq":
        try:
            from groq import Groq  # type: ignore
            client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY", ""))
            return client, "groq"
        except Exception as exc:
            print(f"[WARNING] Groq init failed: {exc} — falling back to rule-based logic.")
            return None, "rule_based"

    elif provider == "ollama":
        # No client object needed; UnderstandingAgent/AssignmentAgent will
        # call the local Ollama REST API directly via requests.
        return "ollama_placeholder", "ollama"

    # Default: rule_based — no external calls
    return None, "rule_based"


# ---------------------------------------------------------------------------
# Core Run Function
# ---------------------------------------------------------------------------

def run_workflow(
    transcript: str,
    provider: str = "rule_based",
    api_key: str = "",
    sender_email: str = "",
    email_password: str = "",
    progress_callback=None,    # Optional callable(step_num, total, label)
    user_id: str = None,       # Supabase Auth user ID (for per-user logs)
) -> WorkflowContext:
    """
    Execute the full 7-agent workflow for the given transcript.

    Parameters
    ----------
    transcript      : Raw meeting transcript text.
    provider        : 'groq', 'ollama', or 'rule_based'.
    api_key         : API key for Groq (ignored for other providers).
    sender_email    : Optional Gmail address for real email sending.
    email_password  : Optional Gmail App Password.
    progress_callback: Optional callable for UI progress updates.

    Returns
    -------
    WorkflowContext with all results, reasoning steps, and audit log populated.
    """
    # --- Validate input ---
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("Transcript cannot be empty.")

    # --- Environment for email tool ---
    if sender_email and email_password:
        os.environ["SENDER_EMAIL"] = sender_email
        os.environ["EMAIL_PASSWORD"] = email_password
    else:
        os.environ["SENDER_EMAIL"] = ""
        os.environ["EMAIL_PASSWORD"] = ""

    # --- Clear previous logs ---
    clear_logs()

    # --- Build LLM client ---
    llm_client, effective_provider = build_llm_client(provider, api_key)

    # --- Initialize shared context ---
    ctx = WorkflowContext(
        transcript=transcript,
        llm_client=llm_client,
        llm_provider=effective_provider,
        user_id=user_id,
    )

    # --- Define pipeline ---
    pipeline = [
        (PlannerAgent(),       "Building Workflow Plan"),
        (UnderstandingAgent(), "Extracting Action Items"),
        (AssignmentAgent(),    "Assigning Task Owners"),
        (ValidatorAgent(),     "Validating Assignments"),
        (ExecutorAgent(),      "Executing Tasks & Email"),
        (RecoveryAgent(),      "Recovering Failures"),
        (LoggerAgent(),        "Writing Audit Trail"),
    ]
    total_steps = len(pipeline)

    # --- Run pipeline ---
    for step_num, (agent, label) in enumerate(pipeline, 1):
        if progress_callback:
            progress_callback(step_num, total_steps, f"[{step_num}/{total_steps}] {agent.name}: {label}")

        print(f"\n{'='*60}")
        print(f"  [{step_num}/{total_steps}] {agent.name} — {label}")
        print(f"{'='*60}")

        try:
            ctx = agent.run(ctx)
        except Exception as exc:
            # Catch unexpected agent-level crash → log and continue
            error_msg = f"AGENT CRASH in {agent.name}: {exc}"
            print(f"[ERROR] {error_msg}")
            ctx.agent_reasoning.append({
                "agent": agent.name,
                "role": agent.role,
                "step": f"step_{step_num}_crash",
                "reasoning": error_msg,
                "status": "error",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        # Print agent's last reasoning entry to console
        if ctx.agent_reasoning:
            print(f"  Reasoning: {ctx.agent_reasoning[-1]['reasoning'][:200]}")

    print(f"{'='*60}\n")

    return ctx


# ---------------------------------------------------------------------------
# EMPLOYEE ONBOARDING — Run Function
# ---------------------------------------------------------------------------

def run_onboarding_workflow(
    employee_name: str,
    employee_email: str = "",
    department: str = "",
    role: str = "",
    user_id: str = None,
    progress_callback=None,
) -> "OnboardingContext":
    """
    Execute the 5-agent onboarding workflow.
    """
    from agents import (
        OnboardingContext,
        OnboardingPlannerAgent,
        OnboardingExecutorAgent,
        OnboardingValidatorAgent,
        OnboardingRecoveryAgent,
        OnboardingLoggerAgent,
    )

    employee_name = (employee_name or "").strip()
    if not employee_name:
        raise ValueError("Employee name cannot be empty.")

    clear_logs()

    ctx = OnboardingContext(
        employee_name=employee_name,
        employee_email=employee_email.strip() if employee_email else "",
        department=department,
        role=role,
        user_id=user_id,
    )

    pipeline = [
        (OnboardingPlannerAgent(),   "Building Onboarding Plan"),
        (OnboardingExecutorAgent(),  "Executing Onboarding Steps"),
        (OnboardingValidatorAgent(), "Validating Employee Data"),
        (OnboardingRecoveryAgent(),  "Recovering Failures"),
        (OnboardingLoggerAgent(),    "Writing Audit Trail"),
    ]
    total_steps = len(pipeline)

    for step_num, (agent, label) in enumerate(pipeline, 1):
        if progress_callback:
            progress_callback(step_num, total_steps,
                              f"[{step_num}/{total_steps}] {agent.name}: {label}")

        print(f"\n{'='*60}")
        print(f"  [{step_num}/{total_steps}] {agent.name} — {label}")
        print(f"{'='*60}")

        try:
            ctx = agent.run(ctx)
        except Exception as exc:
            error_msg = f"AGENT CRASH in {agent.name}: {exc}"
            print(f"[ERROR] {error_msg}")
            ctx.agent_reasoning.append({
                "agent": agent.name,
                "role": agent.role,
                "step": f"ob_step_{step_num}_crash",
                "reasoning": error_msg,
                "status": "error",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

        if ctx.agent_reasoning:
            print(f"  Reasoning: {ctx.agent_reasoning[-1]['reasoning'][:200]}")

    print(f"\n{'='*60}")
    print("  ONBOARDING WORKFLOW COMPLETE")
    print(f"  Audit log: {LOGS_FILE}")
    print(f"{'='*60}\n")

    return ctx


# ---------------------------------------------------------------------------
# Pretty console summary
# ---------------------------------------------------------------------------

def print_summary(ctx: WorkflowContext) -> None:
    """Print a formatted summary of the workflow results."""
    print("\n📋 EXTRACTED ACTION ITEMS:")
    for i, item in enumerate(ctx.action_items, 1):
        badge = "✅" if item.exec_status == "success" else ("⚠️" if item.exec_status == "escalated" else "⏳")
        print(f"  {badge} {i}. {item.description}")
        print(f"       Owner: {item.owner} | Confidence: {item.confidence:.0%} | Source: {item.owner_source}")
        print(f"       Exec: {item.exec_status} — {item.exec_message}")

    print(f"\n📧 EMAIL STATUS: {ctx.email_status} — {ctx.email_message}")
    print(f"\n🗂  AUDIT LOG written to: {LOGS_FILE}")


def print_onboarding_summary(ctx) -> None:
    """Print a formatted summary of the onboarding results."""
    print(f"\n👤 EMPLOYEE: {ctx.employee_name}")
    print(f"   ID:    {ctx.employee_id}")
    print(f"   Email: {ctx.employee_email}")
    print(f"   Buddy: {ctx.buddy_name} ({ctx.buddy_id})")
    print(f"   Meeting: {ctx.meeting_time} ({ctx.meeting_day})")
    print(f"\n📋 STEPS:")
    for s in ctx.steps:
        badge = "✅" if s.status == "success" else ("⚠️" if s.status == "escalated" else "❌")
        print(f"  {badge} {s.name}: {s.message}")
    print(f"\n🗂  AUDIT LOG written to: {LOGS_FILE}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

DEFAULT_TRANSCRIPT = """
Alice: Good morning everyone. Let's get started with the sprint planning.

Bob: I will take care of the database schema migration by end of week.

Alice: Great. We also need someone to write unit tests for the new login module.
Charlie: I'm still wrapping up my current task, maybe someone else can handle it?
Alice: Let's leave the unit tests unassigned for now.

Bob: Should we also update the deployment pipeline? I think the CI config needs fixing.
DevOps Lead: I'll look into the CI/CD infrastructure improvements.

Alice: Perfect. Can someone send a summary of this meeting to the stakeholders?
Charlie: I can do the stakeholder email summary.

Alice: Excellent. Let's also schedule a follow-up demo with the client next Thursday.
"""
# ---------------------------------------------------------------------------
# SLA Monitoring Workflow
# ---------------------------------------------------------------------------

def run_sla_monitoring(user_id: str = None) -> WorkflowContext:
    """Run the standalone SLA MonitoringAgent."""
    from agents import MonitoringAgent, WorkflowContext
    ctx = WorkflowContext(user_id=user_id)
    agent = MonitoringAgent()
    return agent.run(ctx)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AutoFlow AI — Multi-Agent Workflows")
    parser.add_argument("--workflow", choices=["meeting", "onboarding"], default="meeting")
    parser.add_argument("--name", default="", help="Employee name (for onboarding)")
    args = parser.parse_args()

    if args.workflow == "onboarding":
        name = args.name or "John Doe"
        print(f"🚀 AutoFlow AI — Employee Onboarding")
        print(f"   Employee: {name}\n")
        ctx = run_onboarding_workflow(
            employee_name=name,
            progress_callback=lambda s, t, l: print(f"  ▶ {l}"),
        )
        print_onboarding_summary(ctx)
    else:
        api_key = os.environ.get("GROQ_API_KEY", "")
        provider = "groq" if api_key else "rule_based"
        print(f"🚀 AutoFlow AI — Meeting to Action Workflow")
        print(f"   Provider: {provider}")
        print(f"   Transcript length: {len(DEFAULT_TRANSCRIPT)} chars\n")
        ctx = run_workflow(
            transcript=DEFAULT_TRANSCRIPT,
            provider=provider,
            api_key=api_key,
            progress_callback=lambda s, t, l: print(f"  ▶ {l}"),
        )
        print_summary(ctx)

