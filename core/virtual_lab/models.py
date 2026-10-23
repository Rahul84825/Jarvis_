"""Data models and enums for the SANTRA Virtual Testing Room."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class ExecutionMode(str, Enum):
    """Execution modes for the Virtual Testing Room."""
    SIMULATION = "simulation"                  # Default: 100% isolated virtual environment
    CONTROLLED_INTEGRATION = "controlled_integration"  # Disabled by default: real components with safety boundary


class ScenarioCategory(str, Enum):
    """The 10 functional scenario categories for comprehensive Santra testing."""
    APP_CONTROL = "app_control"
    NAVIGATION_SEARCH = "navigation_search"
    SCREEN_UNDERSTANDING = "screen_understanding"
    FILESYSTEM_MANAGEMENT = "filesystem_management"
    CONVERSATIONAL_CONTEXT = "conversational_context"
    SLEEP_WAKE_AUDIO = "sleep_wake_audio"
    AI_CACHE = "ai_cache"
    KNOWLEDGE_REASONING = "knowledge_reasoning"
    AMBIGUITY_ADVERSARIAL = "ambiguity_adversarial"
    STRESS_CONCURRENCY = "stress_concurrency"


class FailureCategory(str, Enum):
    """Root-cause classification categories for scenario failures."""
    INTENT_RESOLUTION = "intent_resolution"
    TOOL_EXECUTION = "tool_execution"
    STATE_VERIFICATION = "state_verification"
    PROVIDER = "provider"
    TIMING = "timing"
    SAFETY = "safety"
    TEST_INFRASTRUCTURE = "test_infrastructure"


class TestStatus(str, Enum):
    """Outcome status for test scenarios."""
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class CommandScenario:
    """Specification of an automated command test scenario."""
    scenario_id: str
    category: ScenarioCategory
    command: str
    description: str
    natural_variations: List[str] = field(default_factory=list)
    initial_state: Dict[str, Any] = field(default_factory=dict)
    expected_intent: Any = ""
    expected_action: Any = None
    expected_tool: Optional[str] = None
    expected_state_changes: Dict[str, Any] = field(default_factory=dict)
    requires_clarification: bool = False
    expected_clarification_phrase: Optional[str] = None
    is_sensitive: bool = False
    timeout_sec: float = 10.0
    verification_method: str = "state_and_intent"  # intent_only, state_diff, tool_call, safety_gate
    pass_criteria: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    """Detailed diagnostic outcome of an executed test scenario."""
    scenario_id: str
    command: str
    mode: ExecutionMode
    status: TestStatus
    duration_ms: float
    timestamp: str
    failure_category: Optional[FailureCategory] = None
    failure_reason: Optional[str] = None
    intent_matched: Optional[str] = None
    action_matched: Optional[str] = None
    tool_invoked: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    output_message: Optional[str] = None
    simulated_state_diff: Optional[Dict[str, Any]] = None
    telemetry: Optional[Dict[str, Any]] = None
    reproduction_instructions: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "command": self.command,
            "mode": self.mode.value if hasattr(self.mode, "value") else str(self.mode),
            "status": self.status.value if hasattr(self.status, "value") else str(self.status),
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "failure_reason": self.failure_reason,
            "intent_matched": self.intent_matched,
            "action_matched": self.action_matched,
            "tool_invoked": self.tool_invoked,
            "tool_args": self.tool_args,
            "output_message": self.output_message,
            "simulated_state_diff": self.simulated_state_diff,
            "telemetry": self.telemetry,
            "reproduction_instructions": self.reproduction_instructions
        }
