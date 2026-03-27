"""
agents.py
=========
Defines all 7 autonomous agents for the "Meeting to Action" workflow.

Architecture:
  - Each agent is a Python class with a `run(ctx)` method.
  - Agents share a WorkflowContext dataclass.
  - LLM usage is isolated to UnderstandingAgent and AssignmentAgent,
    both of which have full rule-based fallbacks (no API key required).
  - Every _log() call persists a structured record via log_audit_trail()
    which writes to Supabase first, then falls back to logs.json.

Agents (in execution order):
  1. PlannerAgent       – builds the step-by-step plan
  2. UnderstandingAgent – extracts action items from transcript (LLM or rules)
  3. AssignmentAgent    – assigns owners with confidence scores (LLM or rules)
  4. ValidatorAgent     – ensures every task has a valid owner
  5. ExecutorAgent      – calls create_task + send_email tools
  6. RecoveryAgent      – retries failed executions, escalates if needed
  7. LoggerAgent        – writes the final structured audit trail
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from tools import (
    ask_human_clarification,
    create_task,
    log_audit_trail,
    retry_with_escalation,
    send_email,
)

# ---------------------------------------------------------------------------
# Shared Workflow Context
# ---------------------------------------------------------------------------

@dataclass
class ActionItem:
    """Represents a single extracted action item."""
    description: str
    owner:       str   = "Unassigned"
    confidence:  float = 0.0
    owner_source: str  = "unset"       # 'llm', 'rule_based', 'human_clarification'
    task_id:     Optional[str] = None
    exec_status: str   = "pending"     # 'pending', 'success', 'escalated'
    exec_message: str  = ""


@dataclass
class WorkflowContext:
    """State shared across all agents in one run."""
    transcript:    str = ""
    llm_client:    Any = None
    llm_provider:  str = "rule_based"  # 'groq', 'ollama', 'rule_based'
    user_id:       str = None          # Supabase Auth user ID

    plan:          List[str]        = field(default_factory=list)
    action_items:  List[ActionItem] = field(default_factory=list)

    email_status:  str = "pending"
    email_message: str = ""

    audit_log:       List[Dict] = field(default_factory=list)
    agent_reasoning: List[Dict] = field(default_factory=list)

    workflow_status: str = "running"
    start_time:      str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent:
    name: str = "BaseAgent"
    role: str = "Generic Agent"
    goal: str = ""

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        raise NotImplementedError

    # ── Structured logging ───────────────────────────────────────────────────
    def _log(
        self,
        ctx:             WorkflowContext,
        step:            str,
        action:          str,
        status:          str,
        *,
        input_data:      str  = "",
        error:           str  = None,
        retry_count:     int  = 0,
        recovery_action: str  = None,
        final_result:    str  = None,
        reasoning:       str  = "",
    ) -> None:
        """
        Build a structured audit entry, persist it via log_audit_trail()
        (Supabase → logs.json fallback), and store reasoning for the UI.
        """
        entry = {
            "step":            step,
            "action":          action,
            "agent":           self.name,
            "input":           input_data,
            "status":          status,
            "error":           error,
            "retry_count":     retry_count,
            "recovery_action": recovery_action,
            "final_result":    final_result,
            "user_id":         ctx.user_id,
            "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Persist (Supabase or local fallback)
        log_audit_trail(entry)

        # Keep in-memory copy for Streamlit tabs
        ctx.audit_log.append(entry)
        ctx.agent_reasoning.append({
            "agent":     self.name,
            "role":      self.role,
            "step":      step,
            "reasoning": reasoning or action,
            "status":    status,
            "timestamp": entry["timestamp"],
        })

    # ── Optional LLM call ────────────────────────────────────────────────────
    def _call_llm(self, ctx: WorkflowContext, prompt: str) -> Optional[str]:
        if ctx.llm_client is None or ctx.llm_provider == "rule_based":
            return None
        try:
            if ctx.llm_provider == "groq":
                response = ctx.llm_client.chat.completions.create(
                    model="llama3-8b-8192",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                    temperature=0.2,
                )
                return response.choices[0].message.content.strip()
            elif ctx.llm_provider == "ollama":
                import requests  # type: ignore
                response = requests.post(
                    "http://localhost:11434/api/generate",
                    json={"model": "tinyllama", "prompt": prompt, "stream": False},
                    timeout=60,
                )
                response.raise_for_status()
                return response.json().get("response", "").strip()
        except Exception as exc:
            print(f"Fallback triggered: Ollama/LLM failed ({exc})")
            ctx.agent_reasoning.append({
                "agent":     self.name,
                "role":      self.role,
                "step":      "llm_fallback",
                "reasoning": f"LLM call failed ({exc}). Fallback triggered: Using rule-based logic.",
                "status":    "warning",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            return None


# ---------------------------------------------------------------------------
# 1. Planner Agent
# ---------------------------------------------------------------------------

class PlannerAgent(BaseAgent):
    name = "PlannerAgent"
    role = "Meeting Planner"
    goal = "Decompose the meeting transcript into an ordered action plan."

    _PLAN = [
        "Step 1 — Understand: Extract all action items from the transcript.",
        "Step 2 — Assign: Identify the best owner for each action item.",
        "Step 3 — Validate: Confirm every task has an unambiguous owner.",
        "Step 4 — Execute: Create tasks in the system and send a summary email.",
        "Step 5 — Recover: Retry any failed executions and escalate if needed.",
        "Step 6 — Audit: Log the complete workflow outcome to the audit trail.",
    ]

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        ctx.plan = self._PLAN[:]
        reasoning = (
            "Analyzed workflow requirements. Generated a 6-step sequential plan: "
            "extraction → assignment → validation → execution → recovery → audit."
        )
        self._log(
            ctx,
            step="1_planning",
            action="Workflow plan created with 6 sequential steps.",
            status="success",
            input_data=f"Transcript length: {len(ctx.transcript)} chars",
            final_result="; ".join(self._PLAN),
            reasoning=reasoning,
        )
        return ctx


# ---------------------------------------------------------------------------
# 2. Understanding Agent  (LLM call #1)
# ---------------------------------------------------------------------------

class UnderstandingAgent(BaseAgent):
    name = "UnderstandingAgent"
    role = "Transcript Analyst"
    goal = "Extract all action items from the meeting transcript."

    _ACTION_SIGNALS = [
        r"\bwill\b", r"\bgoing to\b", r"\bshould\b", r"\bmust\b",
        r"\bneed to\b", r"\bplease\b", r"\btake\b", r"\bhandle\b",
        r"\bprepare\b", r"\bfinish\b", r"\bcomplete\b", r"\bsetup\b",
        r"\bfix\b", r"\bupdate\b", r"\breview\b", r"\bwrite\b",
        r"\bcreate\b", r"\bbuild\b", r"\bsend\b", r"\bschedule\b",
        r"\btest\b", r"\bdeploy\b", r"\bimplement\b", r"\bcheck\b",
    ]
    _SIGNAL_RE = re.compile("|".join(_ACTION_SIGNALS), re.IGNORECASE)

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        llm_result = self._try_llm(ctx)
        if llm_result:
            ctx.action_items = llm_result
            src = "llm"
        else:
            ctx.action_items = self._rule_based_extract(ctx.transcript)
            src = "rule_based"

        count = len(ctx.action_items)
        reasoning = (
            f"Used {'LLM' if src == 'llm' else 'rule-based regex'} to scan transcript. "
            f"Identified {count} action item(s): "
            + ", ".join(f"'{a.description[:40]}'" for a in ctx.action_items)
        )
        self._log(
            ctx,
            step="2_understanding",
            action=f"Extracted {count} action items (source: {src}).",
            status="success",
            input_data=ctx.transcript[:200],
            final_result=json.dumps([a.description for a in ctx.action_items]),
            reasoning=reasoning,
        )
        return ctx

    def _try_llm(self, ctx: WorkflowContext) -> Optional[List[ActionItem]]:
        prompt = (
            "Read the meeting transcript and extract ALL action items. "
            "For each, identify the responsible person or write 'Unassigned'.\n\n"
            'Respond ONLY with valid JSON:\n[{"description":"...","owner":"..."}]\n\n'
            f"Transcript:\n{ctx.transcript}"
        )
        raw = self._call_llm(ctx, prompt)
        if not raw:
            return None
        try:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if not match:
                return None
            items = json.loads(match.group())
            result = []
            for item in items:
                ai = ActionItem(
                    description=str(item.get("description", "")).strip(),
                    owner=str(item.get("owner", "Unassigned")).strip(),
                    confidence=0.85 if item.get("owner","Unassigned") != "Unassigned" else 0.0,
                    owner_source="llm",
                )
                if ai.description:
                    result.append(ai)
            return result or None
        except (json.JSONDecodeError, TypeError):
            return None

    def _rule_based_extract(self, transcript: str) -> List[ActionItem]:
        sentences = re.split(r"[.!?\n]+", transcript)
        items: List[ActionItem] = []
        seen: set = set()

        for sent in sentences:
            sent_clean = sent.strip()
            if len(sent_clean) < 10 or not self._SIGNAL_RE.search(sent_clean):
                continue
            key = sent_clean.lower()[:60]
            if key in seen:
                continue
            seen.add(key)

            description = re.sub(r"^[A-Za-z]+\s*:\s*", "", sent_clean).strip()
            if not description:
                continue

            owner, confidence = self._detect_owner(sent_clean)
            items.append(ActionItem(
                description=description,
                owner=owner,
                confidence=confidence,
                owner_source="rule_based" if owner != "Unassigned" else "unset",
            ))

        if not items:
            items.append(ActionItem(
                description="Review meeting outcomes and follow up on next steps.",
                owner="Unassigned", confidence=0.0, owner_source="unset",
            ))
        return items

    def _detect_owner(self, sentence: str) -> tuple:
        m = re.match(
            r"^([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s*"
            r"(?:will|should|must|is going to|needs? to)",
            sentence,
        )
        if m:
            return m.group(1), 0.80
        m2 = re.match(r"^([A-Z][a-z]+)\s*:\s*I\b", sentence)
        if m2:
            return m2.group(1), 0.75
        return "Unassigned", 0.0


# ---------------------------------------------------------------------------
# 3. Assignment Agent  (LLM call #2)
# ---------------------------------------------------------------------------

class AssignmentAgent(BaseAgent):
    name = "AssignmentAgent"
    role = "Intelligent Assigner"
    goal = "Assign the best owner with a confidence score to each action item."

    _ROLE_KEYWORDS = {
        "database":      ("DB Engineer",         0.72),
        "schema":        ("DB Engineer",         0.72),
        "sql":           ("DB Engineer",         0.72),
        "test":          ("QA Engineer",         0.70),
        "unit test":     ("QA Engineer",         0.75),
        "qa":            ("QA Engineer",         0.80),
        "deploy":        ("DevOps Engineer",     0.75),
        "infrastructure":("DevOps Engineer",     0.70),
        "email":         ("Marketing Lead",      0.65),
        "client":        ("Account Manager",     0.68),
        "design":        ("UI/UX Designer",      0.70),
        "ui":            ("UI/UX Designer",      0.72),
        "frontend":      ("Frontend Developer",  0.72),
        "backend":       ("Backend Developer",   0.72),
        "api":           ("Backend Developer",   0.70),
        "security":      ("Security Engineer",   0.78),
        "report":        ("Project Manager",     0.65),
        "meeting":       ("Project Manager",     0.60),
        "document":      ("Technical Writer",    0.68),
        "ci":            ("DevOps Engineer",     0.74),
        "pipeline":      ("DevOps Engineer",     0.74),
        "demo":          ("Account Manager",     0.66),
        "stakeholder":   ("Project Manager",     0.68),
    }

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        llm_assignments = self._try_llm(ctx)

        for i, item in enumerate(ctx.action_items):
            if item.owner != "Unassigned" and item.confidence > 0.6:
                continue
            if llm_assignments and i < len(llm_assignments):
                assigned = llm_assignments[i]
                item.owner      = assigned.get("owner", item.owner)
                item.confidence = float(assigned.get("confidence", 0.72))
                item.owner_source = "llm"
            else:
                owner, conf = self._rule_based_assign(item.description)
                if owner != "Unassigned":
                    item.owner       = owner
                    item.confidence  = conf
                    item.owner_source = "rule_based"

        assignments = [
            f"'{a.description[:40]}' → {a.owner} ({a.confidence:.0%})"
            for a in ctx.action_items
        ]
        reasoning = (
            f"Applied {'LLM-assisted' if llm_assignments else 'keyword-based'} assignment.\n"
            + "\n".join(f"  • {a}" for a in assignments)
        )
        self._log(
            ctx,
            step="3_assignment",
            action=f"Assigned owners to {len(ctx.action_items)} tasks.",
            status="success",
            input_data=f"{len(ctx.action_items)} action items",
            final_result="; ".join(assignments),
            reasoning=reasoning,
        )
        return ctx

    def _try_llm(self, ctx: WorkflowContext) -> Optional[List[Dict]]:
        items_json = json.dumps(
            [{"description": a.description, "current_owner": a.owner}
             for a in ctx.action_items],
            indent=2,
        )
        prompt = (
            "Assign the most appropriate owner (name or role) and a confidence "
            "score (0.0–1.0) to each action item.\n\n"
            'Respond ONLY: [{"description":"...","owner":"...","confidence":0.85}]\n\n'
            f"Items:\n{items_json}\n\nContext:\n{ctx.transcript}"
        )
        raw = self._call_llm(ctx, prompt)
        if not raw:
            return None
        try:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            return json.loads(match.group()) if match else None
        except (json.JSONDecodeError, TypeError):
            return None

    def _rule_based_assign(self, description: str) -> tuple:
        desc_lower = description.lower()
        for keyword, (role, conf) in self._ROLE_KEYWORDS.items():
            if keyword in desc_lower:
                return role, conf
        return "Unassigned", 0.0


# ---------------------------------------------------------------------------
# 4. Validator Agent
# ---------------------------------------------------------------------------

class ValidatorAgent(BaseAgent):
    name = "ValidatorAgent"
    role = "Quality Validator"
    goal = "Ensure all tasks have clear, unambiguous owners before execution."

    _AMBIGUOUS = {
        "unassigned","someone","anyone","tbd","n/a","unknown","",
        "someone else","who knows","unclear",
    }

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        clarifications, issues = 0, []

        for item in ctx.action_items:
            if item.owner.lower() in self._AMBIGUOUS or item.confidence < 0.45:
                result = ask_human_clarification(item.description)
                item.owner        = result["assigned_owner"]
                item.confidence   = result["confidence"]
                item.owner_source = "human_clarification"
                clarifications   += 1
                issues.append(f"'{item.description[:40]}' → '{item.owner}'")

        if clarifications:
            reasoning = (
                f"Found {clarifications} ambiguous owner(s). Triggered clarification:\n"
                + "\n".join(f"  • {i}" for i in issues)
            )
        else:
            reasoning = (
                f"All {len(ctx.action_items)} tasks have valid owners (≥45% confidence). "
                "No clarification needed."
            )

        self._log(
            ctx,
            step="4_validation",
            action=f"Validated {len(ctx.action_items)} tasks; {clarifications} clarification(s).",
            status="success",
            input_data=f"{len(ctx.action_items)} tasks reviewed",
            final_result=reasoning,
            reasoning=reasoning,
        )
        return ctx


# ---------------------------------------------------------------------------
# 5. Executor Agent
# ---------------------------------------------------------------------------

class ExecutorAgent(BaseAgent):
    name = "ExecutorAgent"
    role = "Execution Specialist"
    goal = "Create tasks and send summary email. Report failures without retrying."

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        results: List[str] = []

        for item in ctx.action_items:
            result = create_task(item.description, item.owner)
            if result["success"]:
                item.exec_status  = "success"
                item.exec_message = result["message"]
                item.task_id      = f"TASK-{abs(hash(item.description)) % 9999:04d}"
                if item.owner != "Unassigned":
                    from tools import send_owner_notification
                    send_owner_notification(item.description, item.owner, ctx.transcript)
            else:
                item.exec_status  = "failed"
                item.exec_message = result["message"]
            results.append(f"[{item.exec_status.upper()}] {item.description[:40]}")

        summary = self._build_email_summary(ctx)
        email_result       = send_email(summary, "team@example.com")
        ctx.email_status   = "success" if email_result["success"] else "failed"
        ctx.email_message  = email_result["message"]
        results.append(f"[EMAIL {ctx.email_status.upper()}] {ctx.email_message}")

        failed  = sum(1 for a in ctx.action_items if a.exec_status == "failed")
        email_ok = ctx.email_status == "success"
        reasoning = (
            f"Attempted {len(ctx.action_items)} task creation(s). "
            f"{len(ctx.action_items) - failed} succeeded, {failed} failed. "
            f"Email: {'sent' if email_ok else 'FAILED'}."
        )

        self._log(
            ctx,
            step="5_execution",
            action=f"Executed {len(ctx.action_items)} tasks + email. {failed} failure(s).",
            status="partial_failure" if (failed or not email_ok) else "success",
            input_data=f"{len(ctx.action_items)} validated tasks",
            error=f"{failed} task failure(s); email={ctx.email_status}" if (failed or not email_ok) else None,
            final_result="; ".join(results),
            reasoning=reasoning,
        )
        return ctx

    def _build_email_summary(self, ctx: WorkflowContext) -> str:
        lines = [
            "=== AutoFlow AI — Meeting Action Plan Summary ===",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "", "ACTION ITEMS:",
        ]
        for i, item in enumerate(ctx.action_items, 1):
            lines.append(
                f"  {i}. {item.description}\n"
                f"     Owner: {item.owner} ({item.confidence:.0%})\n"
                f"     Status: {item.exec_status}"
            )
        lines += ["", "Auto-generated by AutoFlow AI."]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6. Recovery Agent
# ---------------------------------------------------------------------------

class RecoveryAgent(BaseAgent):
    name = "RecoveryAgent"
    role = "Disaster Recovery Specialist"
    goal = "Retry all failed tasks up to 2×; escalate unrecoverable ones."

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        recovered, escalated, skipped = [], [], []

        for item in ctx.action_items:
            if item.exec_status != "failed":
                skipped.append(item.description[:40])
                continue

            outcome = retry_with_escalation(
                fn=create_task,
                args=(item.description, item.owner),
                step_label=f"recovery_{item.description[:30]}",
                agent_name=self.name,
            )
            if outcome["success"]:
                item.exec_status  = "success"
                item.exec_message = outcome["result"]["message"]
                item.task_id      = f"TASK-{abs(hash(item.description)) % 9999:04d}"
                recovered.append(item.description[:40])
            else:
                item.exec_status  = "escalated"
                item.exec_message = outcome.get("escalation_message", "Escalated")
                escalated.append(item.description[:40])

        # Retry email if it failed
        if ctx.email_status == "failed":
            email_outcome = retry_with_escalation(
                fn=send_email,
                args=("Recovery pass — AutoFlow AI summary email",),
                step_label="recovery_email",
                agent_name=self.name,
            )
            if email_outcome["success"]:
                ctx.email_status  = "success"
                ctx.email_message = email_outcome["result"]["message"] + " [recovered]"
                recovered.append("Summary Email")
            else:
                ctx.email_status  = "escalated"
                ctx.email_message = email_outcome.get("escalation_message", "Escalated")
                escalated.append("Summary Email")

        reasoning = (
            f"Recovery scan:\n"
            f"  • Skipped (OK): {len(skipped)}\n"
            f"  • Recovered:    {len(recovered)} — {recovered}\n"
            f"  • Escalated:    {len(escalated)} — {escalated}"
        )
        self._log(
            ctx,
            step="6_recovery",
            action=f"Recovery: {len(recovered)} recovered, {len(escalated)} escalated.",
            status="success" if not escalated else "partial_escalation",
            input_data=f"{len(skipped)+len(recovered)+len(escalated)} items checked",
            recovery_action=f"Retried up to {MAX_RETRIES} times per item",
            final_result=reasoning,
            reasoning=reasoning,
        )
        return ctx


# keep MAX_RETRIES accessible from tools
from tools import MAX_RETRIES  # noqa: E402


# ---------------------------------------------------------------------------
# 7. Logger Agent
# ---------------------------------------------------------------------------

class LoggerAgent(BaseAgent):
    name = "LoggerAgent"
    role = "Compliance Logger"
    goal = "Persist the full workflow audit trail and produce a final summary."

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        total    = len(ctx.action_items)
        success  = sum(1 for a in ctx.action_items if a.exec_status == "success")
        escalated = sum(1 for a in ctx.action_items if a.exec_status == "escalated")

        final_msg = (
            f"Workflow complete. Tasks: {total} total, {success} succeeded, "
            f"{escalated} escalated. Email: {ctx.email_status}."
        )
        reasoning = (
            f"Persisted {len(ctx.audit_log)} in-memory entries.\n"
            f"Final outcome: {success}/{total} tasks OK, "
            f"{escalated} escalated, email={ctx.email_status}."
        )

        self._log(
            ctx,
            step="7_logging",
            action="Full audit trail written.",
            status="completed",
            input_data=f"{len(ctx.audit_log)} audit entries",
            final_result=final_msg,
            reasoning=reasoning,
        )

        # Extra summary row
        log_audit_trail({
            "step":         "7_audit_final",
            "action":       "Final workflow summary.",
            "agent":        self.name,
            "input":        f"{total} tasks",
            "status":       "completed",
            "retry_count":  0,
            "final_result": final_msg,
        })

        ctx.workflow_status = "completed"
        return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# EMPLOYEE ONBOARDING — Context + Agent Subclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class OnboardingStep:
    """A single onboarding execution step."""
    name:        str
    status:      str = "pending"   # 'pending','success','failed','escalated'
    message:     str = ""
    result_data: Dict = field(default_factory=dict)


@dataclass
class OnboardingContext:
    """State for the Employee Onboarding workflow."""
    employee_name:    str = ""
    employee_email:   str = ""   # Admin-provided real email (SMTP recipient)
    corporate_email:  str = ""   # Auto-generated name@companyname.in
    department:       str = ""
    role:             str = ""
    employee_id:      str = ""
    user_id:          str = None

    buddy_id:       str = None
    buddy_name:     str = ""
    buddy_email:    str = ""
    buddy_source:   str = ""

    meeting_time:   str = ""
    meeting_day:    str = ""

    tasks:     List[str] = field(default_factory=list)

    steps:     List[OnboardingStep] = field(default_factory=list)
    audit_log:       List[Dict] = field(default_factory=list)
    agent_reasoning: List[Dict] = field(default_factory=list)

    workflow_status: str = "running"
    start_time:      str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


class OnboardingBaseAgent(BaseAgent):
    """Base for onboarding agents — injects user_id from OnboardingContext."""

    def _olog(self, ctx, step, action, status, **kwargs):
        """Like _log but takes OnboardingContext instead of WorkflowContext."""
        entry = {
            "step":            step,
            "action":          action,
            "agent":           self.name,
            "input":           kwargs.get("input_data", ""),
            "status":          status,
            "error":           kwargs.get("error"),
            "retry_count":     kwargs.get("retry_count", 0),
            "recovery_action": kwargs.get("recovery_action"),
            "final_result":    kwargs.get("final_result"),
            "user_id":         ctx.user_id,
            "role":            ctx.role,
            "department":      ctx.department,
            "buddy_id":        ctx.buddy_id,
            "email_provider_used": kwargs.get("email_provider_used"),
            "timestamp":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        log_audit_trail(entry)
        ctx.audit_log.append(entry)
        ctx.agent_reasoning.append({
            "agent":     self.name,
            "role":      self.role,
            "step":      step,
            "reasoning": kwargs.get("reasoning", action),
            "status":    status,
            "timestamp": entry["timestamp"],
        })


class OnboardingPlannerAgent(OnboardingBaseAgent):
    name = "PlannerAgent"
    role = "Onboarding Planner"
    goal = "Generate the 7-step onboarding plan."

    _PLAN = [
        "Step 1 — Create email account",
        "Step 2 — Create Jira account",
        "Step 3 — Create Slack account",
        "Step 4 — Assign buddy from DB",
        "Step 5 — Schedule orientation meeting",
        "Step 6 — Send welcome email",
        "Step 7 — Notify onboarding buddy",
    ]

    def run(self, ctx):
        ctx.steps = [OnboardingStep(name=s) for s in self._PLAN]
        self._olog(ctx, "ob_1_planning", "Onboarding plan created (7 steps).", "success",
                   input_data=f"Employee: {ctx.employee_name} ({ctx.role} - {ctx.department})",
                   final_result="; ".join(self._PLAN),
                   reasoning="Generated 7-step onboarding plan: email → Jira → Slack → buddy → meeting → welcome email → notify buddy.")
        return ctx


class OnboardingExecutorAgent(OnboardingBaseAgent):
    name = "ExecutorAgent"
    role = "Onboarding Executor"
    goal = "Execute all 7 onboarding steps."

    def run(self, ctx):
        from tools import (
            create_email_account, create_jira_account, create_slack_account, assign_buddy_from_db,
            schedule_meeting, send_welcome_email, send_buddy_notification_email, generate_employee_id,
            generate_email, insert_new_employee, fetch_onboarding_tasks
        )

        ctx.employee_id = generate_employee_id()
        ctx.corporate_email = generate_email(ctx.employee_name)

        insert_new_employee(ctx.employee_id, ctx.employee_name, ctx.corporate_email, ctx.department, ctx.role)

        results = []

        r_tasks = fetch_onboarding_tasks(ctx.department, ctx.role)
        if r_tasks["success"]:
            ctx.tasks = r_tasks.get("tasks", [])
            results.append(f"[OK] Fetched {len(ctx.tasks)} tasks")

        r = create_email_account(ctx.employee_name)
        ctx.steps[0].status = "success" if r["success"] else "failed"
        ctx.steps[0].message = r["message"]
        ctx.steps[0].result_data = r
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Email")

        r = create_jira_account(ctx.employee_name)
        ctx.steps[1].status = "success" if r["success"] else "failed"
        ctx.steps[1].message = r["message"]
        ctx.steps[1].result_data = r
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Jira")

        r = create_slack_account(ctx.employee_name)
        ctx.steps[2].status = "success" if r["success"] else "failed"
        ctx.steps[2].message = r["message"]
        ctx.steps[2].result_data = r
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Slack")

        r = assign_buddy_from_db()
        ctx.steps[3].status = "success" if r["success"] else "failed"
        ctx.steps[3].message = r["message"]
        ctx.steps[3].result_data = r
        if r["success"]:
            ctx.buddy_id = r.get("buddy_id")
            ctx.buddy_name = r.get("buddy_name", "")
            ctx.buddy_email = r.get("buddy_email", "")
            ctx.buddy_source = r.get("source", "")
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Buddy")

        r = schedule_meeting(ctx.employee_name)
        ctx.steps[4].status = "success" if r["success"] else "failed"
        ctx.steps[4].message = r["message"]
        ctx.steps[4].result_data = r
        if r["success"]:
            ctx.meeting_time = r.get("scheduled_time", "")
            ctx.meeting_day = r.get("day_of_week", "")
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Meeting")

        r = send_welcome_email(
            employee_id=ctx.employee_id,
            corporate_email=ctx.corporate_email,
            contact_email=ctx.employee_email,
            employee_name=ctx.employee_name,
            department=ctx.department,
            role=ctx.role,
            tasks=ctx.tasks,
            buddy_name=ctx.buddy_name,
            meeting_time=ctx.meeting_time
        )
        ctx.steps[5].status = "success" if r["success"] else "failed"
        ctx.steps[5].message = r["message"]
        ctx.steps[5].result_data = r
        welcome_mode = r.get("mode", "unknown")
        results.append(f"[{'OK' if r['success'] else 'FAIL'}] Welcome Email")

        if ctx.buddy_email and ctx.buddy_name:
            r = send_buddy_notification_email(
                buddy_name=ctx.buddy_name,
                buddy_email=ctx.buddy_email,
                new_employee_name=ctx.employee_name,
                role=ctx.role,
                department=ctx.department,
                meeting_time=ctx.meeting_time
            )
            ctx.steps[6].status = "success" if r["success"] else "failed"
            ctx.steps[6].message = r["message"]
            ctx.steps[6].result_data = r
            results.append(f"[{'OK' if r['success'] else 'FAIL'}] Buddy Notification")
        else:
            ctx.steps[6].status = "skipped"
            ctx.steps[6].message = "No buddy assigned, skipped notification."
            results.append("[SKIP] Buddy Notification")

        failed = sum(1 for s in ctx.steps if s.status == "failed")
        self._olog(ctx, "ob_2_execution",
                   f"Executed 7 steps. {7 - failed} OK, {failed} failed.",
                   "partial_failure" if failed else "success",
                   input_data=f"employee_id={ctx.employee_id}",
                   error=f"{failed} step(s) failed" if failed else None,
                   email_provider_used=welcome_mode,
                   final_result="; ".join(results),
                   reasoning=f"Ran all 7 tools. Results: {', '.join(results)}")
        return ctx


class OnboardingValidatorAgent(OnboardingBaseAgent):
    name = "ValidatorAgent"
    role = "Onboarding Validator"
    goal = "Validate no NULL fields and buddy assigned."

    def run(self, ctx):
        issues = []
        if not ctx.employee_id:
            issues.append("employee_id is empty")
        if not ctx.employee_email:
            issues.append("employee_email is empty")
        if not ctx.role:
            issues.append("role is empty")
        if not ctx.department:
            issues.append("department is empty")
        if not ctx.buddy_id:
            issues.append("buddy not assigned")
        if not ctx.meeting_time:
            issues.append("meeting not scheduled")

        status = "success" if not issues else "warning"
        self._olog(ctx, "ob_3_validation",
                   f"Validation: {len(issues)} issue(s) found." if issues else "All fields validated OK.",
                   status,
                   input_data=f"employee_id={ctx.employee_id}",
                   error="; ".join(issues) if issues else None,
                   final_result="PASS" if not issues else f"ISSUES: {'; '.join(issues)}",
                   reasoning=f"Checked core onboarding fields. {'Issues: ' + ', '.join(issues) if issues else 'All OK.'}")
        return ctx


class OnboardingRecoveryAgent(OnboardingBaseAgent):
    name = "RecoveryAgent"
    role = "Onboarding Recovery"
    goal = "Retry failed onboarding steps."

    def run(self, ctx):
        from tools import (
            create_email_account, create_jira_account, create_slack_account, assign_buddy_from_db,
            schedule_meeting, send_welcome_email, send_buddy_notification_email, retry_with_escalation,
        )

        retry_fns = {
            0: (create_email_account, (ctx.employee_name,), {}),
            1: (create_jira_account,  (ctx.employee_name,), {}),
            2: (create_slack_account, (ctx.employee_name,), {}),
            3: (assign_buddy_from_db, (), {}),
            4: (schedule_meeting,     (ctx.employee_name,), {}),
            5: (send_welcome_email, (), {
                "employee_id": ctx.employee_id, "corporate_email": ctx.corporate_email,
                "contact_email": ctx.employee_email, "employee_name": ctx.employee_name,
                "department": ctx.department, "role": ctx.role, "tasks": ctx.tasks,
                "buddy_name": ctx.buddy_name, "meeting_time": ctx.meeting_time
            }),
            6: (send_buddy_notification_email, (), {
                "buddy_name": ctx.buddy_name, "buddy_email": ctx.buddy_email,
                "new_employee_name": ctx.employee_name, "role": ctx.role,
                "department": ctx.department, "meeting_time": ctx.meeting_time
            }),
        }

        recovered, escalated = [], []
        for i, step in enumerate(ctx.steps):
            if step.status not in ["failed", "warning", "skipped"]:
                continue
            if i not in retry_fns or step.status == "skipped":
                continue

            fn, args, kwargs = retry_fns[i]
            outcome = retry_with_escalation(
                fn=fn, args=args, kwargs=kwargs,
                step_label=f"ob_recovery_{step.name[:20]}",
                agent_name=self.name,
            )
            if outcome["success"]:
                step.status = "success"
                step.message = outcome["result"]["message"] + " [recovered]"
                step.result_data = outcome["result"]
                recovered.append(step.name)
                # Update context fields if buddy/meeting recovered
                if i == 3 and outcome["result"].get("buddy_id"):
                    ctx.buddy_id = outcome["result"]["buddy_id"]
                    ctx.buddy_name = outcome["result"].get("buddy_name", "")
                    ctx.buddy_email = outcome["result"].get("buddy_email", "")
                if i == 4 and outcome["result"].get("scheduled_time"):
                    ctx.meeting_time = outcome["result"]["scheduled_time"]
                    ctx.meeting_day = outcome["result"].get("day_of_week", "")
            else:
                step.status = "escalated"
                step.message = outcome.get("escalation_message", "Escalated to HR/IT")
                escalated.append(step.name)

        self._olog(ctx, "ob_4_recovery",
                   f"Recovery: {len(recovered)} recovered, {len(escalated)} escalated.",
                   "success" if not escalated else "partial_escalation",
                   input_data=f"{len(recovered)+len(escalated)} steps retried",
                   recovery_action="Retried up to 2x per step",
                   final_result=f"recovered={recovered}, escalated={escalated}",
                   reasoning=f"Retried failed steps. Recovered: {recovered}. Escalated: {escalated}.")
        return ctx


class OnboardingLoggerAgent(OnboardingBaseAgent):
    name = "LoggerAgent"
    role = "Onboarding Logger"
    goal = "Write final onboarding audit summary."

    def run(self, ctx):
        from tools import update_new_employee
        import os
        from datetime import datetime

        total = len(ctx.steps)
        ok = sum(1 for s in ctx.steps if s.status == "success")
        esc = sum(1 for s in ctx.steps if s.status == "escalated")

        # Generate Structured Documentation Report
        report = []
        report.append(f"# Employee Onboarding Report: {ctx.employee_name}")
        report.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Status:** {'✅ Complete' if esc == 0 else '⚠️ Partial (SLA Risks Present)'}")
        report.append("")
        report.append("## 1. Employee Profile")
        report.append(f"- **ID:** {ctx.employee_id}")
        report.append(f"- **Role:** {ctx.role}")
        report.append(f"- **Department:** {ctx.department}")
        report.append(f"- **Corporate Email:** {ctx.corporate_email}")
        report.append(f"- **Contact Email:** {ctx.employee_email}")
        report.append("")
        report.append("## 2. Buddy Assignment & Orientation")
        if ctx.buddy_id:
            report.append(f"- **Buddy:** {ctx.buddy_name} ({ctx.buddy_email})")
        else:
            report.append("- **Buddy:** *None Assigned (Escalated)*")
        report.append(f"- **Meeting Time:** {ctx.meeting_time or '*Not Scheduled*'}")
        report.append("")
        report.append("## 3. Role-Based Tasks Generated")
        for t in ctx.tasks:
            report.append(f"- {t}")
        if not ctx.tasks:
            report.append("- *No tasks generated.*")
        report.append("")
        report.append("## 4. Execution Steps & SLA Risks")
        for s in ctx.steps:
            icon = "✅" if s.status == "success" else ("⚠️" if s.status == "warning" else ("🚨" if s.status == "escalated" else "❌"))
            report.append(f"- {icon} **{s.name}**: {s.message}")
        
        report_text = "\n".join(report)

        # Save to reports/
        os.makedirs("reports", exist_ok=True)
        report_filename = f"reports/onboarding_{ctx.employee_id}.md"
        try:
            with open(report_filename, "w", encoding="utf-8") as f:
                f.write(report_text)
        except Exception as e:
            print(f"Failed to write report to {report_filename}: {e}")

        # Update new_employees record with final state
        final_status = "completed" if esc == 0 else "partial"
        update_new_employee(ctx.employee_id, {
            "onboarding_status": final_status,
            "buddy_id": ctx.buddy_id,
        })

        final_msg = (
            f"Onboarding {'complete' if esc == 0 else 'partial'}. "
            f"Steps: {total} total, {ok} succeeded, {esc} escalated."
        )
        self._olog(ctx, "ob_5_logging", "Onboarding audit trail finalized.", "completed",
                   input_data=f"employee={ctx.employee_name} id={ctx.employee_id}",
                   final_result=report_text,
                   reasoning=f"Persisted {len(ctx.audit_log)} entries and saved documentation to {report_filename}. Final: {final_msg}")

        ctx.workflow_status = "completed"
        return ctx


# ═══════════════════════════════════════════════════════════════════════════════
# SLA MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

class MonitoringAgent(BaseAgent):
    name = "MonitoringAgent"
    role = "SLA Compliance Officer"
    goal = "Detect pending tasks that have breached SLA and escalate them to IT Support."

    def run(self, ctx: WorkflowContext) -> WorkflowContext:
        from tools import check_and_escalate_sla_breaches, send_escalation_email

        # SLA Check
        result = check_and_escalate_sla_breaches()
        breached = result.get("breaches", [])
        warnings = result.get("warnings", [])

        if not result["success"]:
            self._log(
                ctx,
                step="SLA Check",
                action="Failed to check SLA breaches.",
                status="failed",
                error=result.get("message"),
                reasoning="Database or API error preventing SLA checks."
            )
            return ctx

        # Send emails for breached
        for b in breached:
            subject = f"SLA BREACH ALERT 🚨"
            body = (
                f"Task: {b['name']}\n"
                f"Owner: {b['owner']}\n\n"
                f"Issue:\nTask has exceeded SLA threshold ({b['delay_duration']} delay).\n\n"
                f"Action Taken:\nReassigned to {b['new_owner']} / escalation triggered\n\n"
                f"Impact on workflow:\nPotential delay in downstream deliverables.\n\n"
                f"Suggested next step:\nImmediate attention required. Please assist the new owner."
            )
            send_escalation_email(subject, body, "it_support@companyname.in")

        if breached:
            self._log(
                ctx,
                step="SLA Check",
                action="Breach detected",
                status="escalated",
                recovery_action="Reassigned",
                final_result="email_sent",
                reasoning=f"Reassigned {len(breached)} task(s) and detected {len(warnings)} warning(s)."
            )
        elif warnings:
            self._log(
                ctx,
                step="SLA Check",
                action="Warnings detected",
                status="warning",
                final_result="No breaches yet",
                reasoning=f"Detected {len(warnings)} warning(s) approaching SLA limits."
            )
        else:
            self._log(
                ctx,
                step="SLA Check",
                action="SLA compliance check",
                status="success",
                final_result="No breaches",
                reasoning="All tasks are within SLA boundaries."
            )

        return ctx

