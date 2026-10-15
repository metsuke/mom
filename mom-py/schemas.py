import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

class ESAPhase(str, Enum):
    COR = "cor"  # Phase 0: Corpus de Filosofía, Axiomas y Estándares
    URD = "urd"  # Phase 1: User Requirements Document
    SRD = "srd"  # Phase 2: Software Requirements Document
    ADD = "add"  # Phase 3: Architectural Design Document
    DDD = "ddd"  # Phase 4: Detailed Design Document

class StatusEnum(str, Enum):
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"

class PriorityEnum(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class VerificationMethod(str, Enum):
    TEST = "TEST"
    UNIT_TEST = "UNIT_TEST"
    INSPECTION = "INSPECTION"
    ANALYSIS = "ANALYSIS"
    DEMONSTRATION = "DEMONSTRATION"

class ItemAttributes:
    def __init__(
        self,
        status: StatusEnum = StatusEnum.DRAFT,
        priority: PriorityEnum = PriorityEnum.MEDIUM,
        verification_method: VerificationMethod = VerificationMethod.TEST,
        is_user_doc: bool = False,
        tags: Optional[List[str]] = None
    ) -> None:
        self.status = status
        self.priority = priority
        self.verification_method = verification_method
        self.is_user_doc = is_user_doc
        self.tags = tags or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "priority": self.priority.value,
            "verification_method": self.verification_method.value,
            "is_user_doc": self.is_user_doc,
            "tags": self.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemAttributes":
        raw_method = data.get("verification_method", VerificationMethod.TEST.value)
        
        # Mapeo de seguridad para normalizar cadenas no contempladas originalmente
        try:
            verif_enum = VerificationMethod(raw_method)
        except ValueError:
            verif_enum = VerificationMethod.TEST

        return cls(
            status=StatusEnum(data.get("status", StatusEnum.DRAFT.value)),
            priority=PriorityEnum(data.get("priority", PriorityEnum.MEDIUM.value)),
            verification_method=verif_enum,
            is_user_doc=data.get("is_user_doc", False),
            tags=data.get("tags", [])
        )

class ItemMetadata:
    def __init__(
        self,
        author: str,
        declared_in_project: Optional[str] = None,
        ai_guardrails: Optional[str] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None
    ) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.author = author
        self.declared_in_project = declared_in_project
        self.ai_guardrails = ai_guardrails
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "author": self.author,
            "declared_in_project": self.declared_in_project,
            "ai_guardrails": self.ai_guardrails,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemMetadata":
        return cls(
            author=data.get("author", "Unknown"),
            declared_in_project=data.get("declared_in_project"),
            ai_guardrails=data.get("ai_guardrails"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at")
        )

class MOMItem:
    def __init__(
        self,
        id: str,
        phase: ESAPhase,
        title: str,
        description: str,
        parent_ids: Optional[List[str]] = None,
        child_ids: Optional[List[str]] = None,
        attributes: Optional[ItemAttributes] = None,
        metadata: Optional[ItemMetadata] = None
    ) -> None:
        self.id = id
        self.phase = phase
        self.title = title
        self.description = description
        self.parent_ids = parent_ids or []
        self.child_ids = child_ids or []
        self.attributes = attributes or ItemAttributes()
        self.metadata = metadata or ItemMetadata(author="Human")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase.value,
            "title": self.title,
            "description": self.description,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "attributes": self.attributes.to_dict(),
            "metadata": self.metadata.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MOMItem":
        return cls(
            id=data["id"],
            phase=ESAPhase(data["phase"]),
            title=data["title"],
            description=data["description"],
            parent_ids=data.get("parent_ids", []),
            child_ids=data.get("child_ids", []),
            attributes=ItemAttributes.from_dict(data.get("attributes", {})),
            metadata=ItemMetadata.from_dict(data.get("metadata", {}))
        )

# Version: 0.4.1