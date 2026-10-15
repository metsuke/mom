from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

class ESAPhase(str, Enum):
    URD = "urd"
    SRD = "srd"
    ADD = "add"
    DDD = "ddd"

class PriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class StatusEnum(str, Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DEPRECATED = "DEPRECATED"

class VerificationMethod(str, Enum):
    INSPECTION = "INSPECTION"
    ANALYSIS = "ANALYSIS"
    DEMONSTRATION = "DEMONSTRATION"
    UNIT_TEST = "UNIT_TEST"
    INTEGRATION_TEST = "INTEGRATION_TEST"
    SYSTEM_TEST = "SYSTEM_TEST"

@dataclass
class ItemAttributes:
    priority: PriorityEnum = PriorityEnum.MEDIUM
    verification_method: VerificationMethod = VerificationMethod.UNIT_TEST
    status: StatusEnum = StatusEnum.DRAFT
    is_user_doc: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ItemMetadata:
    author: str = "Metsuke"
    declared_in_project: str = ""
    ai_guardrails: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class MOMItem:
    id: str
    phase: ESAPhase
    title: str
    description: str
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    attributes: ItemAttributes = field(default_factory=ItemAttributes)
    metadata: ItemMetadata = field(default_factory=ItemMetadata)

    def __post_init__(self) -> None:
        if isinstance(self.phase, str):
            self.phase = ESAPhase(self.phase)
        
        prefix = self.phase.value.upper()
        if not self.id.startswith(f"{prefix}-"):
            raise ValueError(f"El ID '{self.id}' debe comenzar con el prefijo '{prefix}-'")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MOMItem":
        attr_data = data.get("attributes", {})
        meta_data = data.get("metadata", {})
        
        attr = ItemAttributes(
            priority=PriorityEnum(attr_data.get("priority", "MEDIUM")),
            verification_method=VerificationMethod(attr_data.get("verification_method", "UNIT_TEST")),
            status=StatusEnum(attr_data.get("status", "DRAFT")),
            is_user_doc=attr_data.get("is_user_doc", False),
            extra=attr_data.get("extra", {})
        )
        meta = ItemMetadata(
            author=meta_data.get("author", "Metsuke"),
            declared_in_project=meta_data.get("declared_in_project", ""),
            ai_guardrails=meta_data.get("ai_guardrails"),
            created_at=meta_data.get("created_at"),
            updated_at=meta_data.get("updated_at")
        )
        return cls(
            id=data["id"],
            phase=ESAPhase(data["phase"]),
            title=data["title"],
            description=data["description"],
            parent_ids=data.get("parent_ids", []),
            child_ids=data.get("child_ids", []),
            attributes=attr,
            metadata=meta
        )

# Version: 0.2.0