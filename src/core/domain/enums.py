from __future__ import annotations

from enum import Enum, IntEnum


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return str(self.value)


class AlertSeverity(_StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


class EventSeverity(_StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class QcSeverity(_StrEnum):
    BLOCKER = "BLOCKER"
    MAJOR = "MAJOR"
    MINOR = "MINOR"


class AlertStatus(_StrEnum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class TaskStatus(_StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ApprovalStatus(_StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"


class FeedbackDecision(_StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RecommendationDecision(_StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    DEFER = "defer"


class TaskPriority(IntEnum):
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    P5 = 5


class WorklistType(_StrEnum):
    REPRODUCTION = "reproduction"
    VET = "vet"
    HEALTH_FOLLOW_UP = "health_follow_up"
    MILK_QUALITY = "milk_quality"
    MOVEMENT = "movement"
    CULLING_REVIEW = "culling_review"
    DATA_CLEANUP = "data_cleanup"
    MANAGER_REVIEW = "manager_review"


class WorklistOutcomeStatus(_StrEnum):
    DONE = "done"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"
    NO_EFFECT = "no_effect"
    ESCALATED = "escalated"






class VetProtocolExecutionStatus(_StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class VetProtocolStepStatus(_StrEnum):
    PENDING = "pending"
    DONE = "done"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ReproductionState(_StrEnum):
    ELIGIBLE = "eligible"
    HEAT = "heat"
    BRED = "bred"
    PREG_CHECK_DUE = "preg_check_due"
    PREGNANT = "pregnant"
    OPEN = "open"
    REPEAT = "repeat"
    FRESH = "fresh"
    DRY = "dry"
    CULL_CANDIDATE = "cull_candidate"


class ReproductionReasonCode(_StrEnum):
    REPRO_HEAT_EVENT = "REPRO_HEAT_EVENT"
    REPRO_BRED_EVENT = "REPRO_BRED_EVENT"
    REPRO_PREG_CHECK_DUE = "REPRO_PREG_CHECK_DUE"
    REPRO_PREGNANT_CONFIRMED = "REPRO_PREGNANT_CONFIRMED"
    REPRO_OPEN_AFTER_NEGATIVE_CHECK = "REPRO_OPEN_AFTER_NEGATIVE_CHECK"
    REPRO_REPEAT_AFTER_MULTIPLE_SERVICES = "REPRO_REPEAT_AFTER_MULTIPLE_SERVICES"
    REPRO_FRESH_AFTER_CALVING = "REPRO_FRESH_AFTER_CALVING"
    REPRO_ELIGIBLE_AFTER_VWP = "REPRO_ELIGIBLE_AFTER_VWP"
    REPRO_DRY_OFF_EVENT = "REPRO_DRY_OFF_EVENT"
    REPRO_CULL_EVENT = "REPRO_CULL_EVENT"
    REPRO_NO_DATA = "REPRO_NO_DATA"

class AnimalEventType(_StrEnum):
    HEAT = "heat"
    INSEMINATION = "insemination"
    PREG_CHECK = "preg_check"
    CALVING = "calving"
    DRY_OFF = "dry_off"
    TREATMENT = "treatment"
    CULL = "cull"
    DEATH = "death"
    PEN_MOVE = "pen_move"
    COMMENT = "comment"
    MANUAL_NOTE = "manual_note"
    CUSTOM_OPERATIONAL_EVENT = "custom_operational_event"


class AnimalEventActorType(_StrEnum):
    USER = "user"
    SYSTEM = "system"
    CONNECTOR = "connector"
    IMPORT = "import"
    API = "api"
    UNKNOWN = "unknown"


class AnimalEventSource(_StrEnum):
    MANUAL_UI = "manual_ui"
    API = "api"
    IMPORT = "import"
    CONNECTOR = "connector"
    SYSTEM = "system"
    MIGRATION = "migration"
    UNKNOWN = "unknown"


class AnimalEventReasonCode(_StrEnum):
    HEAT_OBSERVED = "HEAT_OBSERVED"
    HEAT_SENSOR_FLAG = "HEAT_SENSOR_FLAG"
    INSEMINATION_PERFORMED = "INSEMINATION_PERFORMED"
    PREGNANCY_CONFIRMED = "PREGNANCY_CONFIRMED"
    PREGNANCY_OPEN = "PREGNANCY_OPEN"
    CALVING_NORMAL = "CALVING_NORMAL"
    CALVING_ABORTION = "CALVING_ABORTION"
    CALVING_STILLBIRTH = "CALVING_STILLBIRTH"
    DRY_PERIOD_START = "DRY_PERIOD_START"
    TREATMENT_PROTOCOL = "TREATMENT_PROTOCOL"
    MASTITIS_PROTOCOL = "MASTITIS_PROTOCOL"
    LAMENESS_PROTOCOL = "LAMENESS_PROTOCOL"
    METRITIS_PROTOCOL = "METRITIS_PROTOCOL"
    CULL_LOW_PRODUCTIVITY = "CULL_LOW_PRODUCTIVITY"
    CULL_REPRO_FAILURE = "CULL_REPRO_FAILURE"
    CULL_HEALTH = "CULL_HEALTH"
    CULL_AGE = "CULL_AGE"
    DEATH_ON_FARM = "DEATH_ON_FARM"
    PEN_REBALANCE = "PEN_REBALANCE"
    PEN_PROTOCOL = "PEN_PROTOCOL"
    CHECK_ASSIGNED = "CHECK_ASSIGNED"
    FOLLOW_UP_ASSIGNED = "FOLLOW_UP_ASSIGNED"
    STATUS_CLOSED = "STATUS_CLOSED"
    COMMENT_ADDED = "COMMENT_ADDED"
    MANUAL_NOTE_ADDED = "MANUAL_NOTE_ADDED"
    CUSTOM_OTHER = "CUSTOM_OTHER"

class FeedbackReasonCode(_StrEnum):
    CONFIRMED_BY_SPECIALIST = "CONFIRMED_BY_SPECIALIST"
    CONFIRMED_BY_MANAGER = "CONFIRMED_BY_MANAGER"
    ALREADY_ACTIONED = "ALREADY_ACTIONED"
    ACCEPTED_OTHER = "ACCEPTED_OTHER"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    DATA_ISSUE = "DATA_ISSUE"
    NOT_FEASIBLE = "NOT_FEASIBLE"
    CONTRADICTS_FIELD_OBSERVATION = "CONTRADICTS_FIELD_OBSERVATION"
    DUPLICATE_RECOMMENDATION = "DUPLICATE_RECOMMENDATION"
    REJECTED_OTHER = "REJECTED_OTHER"


ALERT_OPEN_STATUSES = frozenset({AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value})
ALERT_STATUSES = frozenset({item.value for item in AlertStatus})
TASK_ACTIVE_STATUSES = frozenset({TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value})
TASK_CLOSED_STATUSES = frozenset({TaskStatus.DONE.value, TaskStatus.CANCELLED.value})
TASK_STATUSES = frozenset({item.value for item in TaskStatus})
WORKLIST_TYPES = frozenset({item.value for item in WorklistType})
WORKLIST_OUTCOME_STATUSES = frozenset({item.value for item in WorklistOutcomeStatus})
VET_PROTOCOL_EXECUTION_STATUSES = frozenset({item.value for item in VetProtocolExecutionStatus})
VET_PROTOCOL_STEP_STATUSES = frozenset({item.value for item in VetProtocolStepStatus})
REPRODUCTION_STATES = frozenset({item.value for item in ReproductionState})
REPRODUCTION_REASON_CODES = frozenset({item.value for item in ReproductionReasonCode})
APPROVAL_STATUSES = frozenset({item.value for item in ApprovalStatus})
QC_SEVERITIES = frozenset({item.value for item in QcSeverity})

DEFAULT_ACCEPTED_REASON_CODES = (
    FeedbackReasonCode.CONFIRMED_BY_SPECIALIST.value,
    FeedbackReasonCode.CONFIRMED_BY_MANAGER.value,
    FeedbackReasonCode.ALREADY_ACTIONED.value,
    FeedbackReasonCode.ACCEPTED_OTHER.value,
)

ANIMAL_EVENT_TYPES = frozenset({item.value for item in AnimalEventType})
ANIMAL_EVENT_SOURCES = frozenset({item.value for item in AnimalEventSource})
ANIMAL_EVENT_ACTOR_TYPES = frozenset({item.value for item in AnimalEventActorType})
ANIMAL_EVENT_REASON_CODES = frozenset({item.value for item in AnimalEventReasonCode})

DEFAULT_REJECTED_REASON_CODES = (
    FeedbackReasonCode.FALSE_POSITIVE.value,
    FeedbackReasonCode.LOW_CONFIDENCE.value,
    FeedbackReasonCode.DATA_ISSUE.value,
    FeedbackReasonCode.NOT_FEASIBLE.value,
    FeedbackReasonCode.CONTRADICTS_FIELD_OBSERVATION.value,
    FeedbackReasonCode.DUPLICATE_RECOMMENDATION.value,
    FeedbackReasonCode.REJECTED_OTHER.value,
)

__all__ = [
    "ALERT_OPEN_STATUSES",
    "ALERT_STATUSES",
    "ANIMAL_EVENT_ACTOR_TYPES",
    "ANIMAL_EVENT_REASON_CODES",
    "ANIMAL_EVENT_SOURCES",
    "ANIMAL_EVENT_TYPES",
    "APPROVAL_STATUSES",
    "DEFAULT_ACCEPTED_REASON_CODES",
    "DEFAULT_REJECTED_REASON_CODES",
    "QC_SEVERITIES",
    "TASK_ACTIVE_STATUSES",
    "TASK_CLOSED_STATUSES",
    "TASK_STATUSES",
    "WORKLIST_TYPES",
    "WORKLIST_OUTCOME_STATUSES",
    "VET_PROTOCOL_EXECUTION_STATUSES",
    "VET_PROTOCOL_STEP_STATUSES",
    "REPRODUCTION_STATES",
    "REPRODUCTION_REASON_CODES",
    "AlertSeverity",
    "AnimalEventActorType",
    "AnimalEventReasonCode",
    "AnimalEventSource",
    "AnimalEventType",
    "AlertStatus",
    "ApprovalStatus",
    "EventSeverity",
    "FeedbackDecision",
    "FeedbackReasonCode",
    "ReproductionReasonCode",
    "ReproductionState",
    "QcSeverity",
    "RecommendationDecision",
    "TaskPriority",
    "TaskStatus",
    "WorklistOutcomeStatus",
    "WorklistType",
]
