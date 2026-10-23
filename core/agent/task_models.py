"""
Structured Task and Step Models for JARVIS Agentic Planning & Execution.

Defines the authoritative lifecycle states, task representations, step models,
and dependency records for multi-step workflows.
"""

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATED = "VALIDATED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


@dataclass
class TaskStep:
    """Represents an atomic, ordered step within an AgentTask."""
    step_index: int
    raw_text: str
    clean_text: str
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    intent_node: Dict[str, Any] = field(default_factory=dict)
    depends_on: Optional[int] = None
    requires_confirmation: bool = False
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH
    parallel: bool = False
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    idempotency_key: str = ""
    latency_ms: float = 0.0

    def __post_init__(self):
        if not self.idempotency_key:
            # Deterministic hash key of tool and normalized arguments
            arg_str = str(sorted(self.args.items()))
            self.idempotency_key = f"{self.tool_name}:{arg_str}"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, StepStatus) else str(self.status)
        return data

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        if isinstance(self.intent_node, dict) and key in self.intent_node:
            return self.intent_node[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        if isinstance(self.intent_node, dict):
            return self.intent_node.get(key, default)
        return default


@dataclass
class AgentTask:
    """Represents a multi-step user goal decomposed into ordered, executable steps."""
    task_id: str
    user_request: str
    parsed_goal: str
    steps: List[TaskStep] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PLANNED
    current_step_index: int = 0
    overall_risk: str = "LOW"
    pending_confirmation_step: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    execution_summary: str = ""
    spoken_summary: str = ""
    cancellation_requested: bool = False
    context_data: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)

    def __getitem__(self, idx) -> TaskStep:
        return self.steps[idx]

    @classmethod
    def create(cls, user_request: str, goal: str = "") -> "AgentTask":
        task_id = f"TASK-{uuid.uuid4().hex[:6].upper()}"
        return cls(
            task_id=task_id,
            user_request=user_request,
            parsed_goal=goal or user_request,
            created_at=time.time(),
            updated_at=time.time()
        )

    def mark_cancelled(self):
        self.cancellation_requested = True
        self.status = TaskStatus.CANCELLED
        self.updated_at = time.time()
        for step in self.steps:
            if step.status in [StepStatus.PENDING, StepStatus.RUNNING, StepStatus.VALIDATED]:
                step.status = StepStatus.CANCELLED
                step.error = "Task cancelled by user request."

    def get_completed_steps(self) -> List[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    def get_failed_steps(self) -> List[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def get_skipped_steps(self) -> List[TaskStep]:
        return [s for s in self.steps if s.status == StepStatus.SKIPPED]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_request": self.user_request,
            "parsed_goal": self.parsed_goal,
            "status": self.status.value if isinstance(self.status, TaskStatus) else str(self.status),
            "current_step_index": self.current_step_index,
            "overall_risk": self.overall_risk,
            "pending_confirmation_step": self.pending_confirmation_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "execution_summary": self.execution_summary,
            "spoken_summary": self.spoken_summary,
            "cancellation_requested": self.cancellation_requested,
            "context_data": self.context_data,
            "steps": [s.to_dict() for s in self.steps]
        }
