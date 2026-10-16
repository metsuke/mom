import datetime
import re
from enum import Enum
from typing import List, Optional, Dict, Any

CURRENT_SCHEMA_VERSION = "0.5.2"

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

class MetsuOSKnowledgeLevel(str, Enum):
    DARK1 = "⚫① Dark1 (Conocimiento en Bruto)"
    ROJO2 = "🔴② Rojo2 (Conocimiento Impulsivo)"
    YELLOW3 = "🟡③ Yellow3 (Conocimiento Crítico)"
    GREEN4 = "🟢④ Green4 (Conocimiento Natural)"
    BLUE5 = "🔵⑤ Blue5 (Conocimiento Científico)"
    LIGHT6 = "⚪⑥ Light6 (Conocimiento Consolidado)"

    @classmethod
    def parse_flexible(cls, raw_value: str) -> Optional["MetsuOSKnowledgeLevel"]:
        """Parsea cadenas flexibles (código, clave o representación formateada) de forma segura."""
        if not raw_value:
            return None
        
        normalized = str(raw_value).strip().upper()
        
        mapping = {
            "DARK1": cls.DARK1,
            "ROJO2": cls.ROJO2,
            "RED2": cls.ROJO2,
            "YELLOW3": cls.YELLOW3,
            "GREEN4": cls.GREEN4,
            "BLUE5": cls.BLUE5,
            "LIGHT6": cls.LIGHT6
        }
        
        if normalized in mapping:
            return mapping[normalized]
            
        for item in cls:
            if item.value.upper() == normalized or normalized in item.value.upper():
                return item
                
        return None

class ItemAttributes:
    def __init__(
        self,
        status: StatusEnum = StatusEnum.DRAFT,
        priority: PriorityEnum = PriorityEnum.MEDIUM,
        verification_method: VerificationMethod = VerificationMethod.TEST,
        is_user_doc: bool = False,
        tags: Optional[List[str]] = None,
        bib_authors: Optional[List[str]] = None,
        bib_title: Optional[str] = None,
        bib_source: Optional[str] = None,
        bib_citation_detail: Optional[str] = None,
        metsuos_knowledge_level: Optional[MetsuOSKnowledgeLevel] = None,
        nato_source_reliability: Optional[str] = None,
        nato_information_credibility: Optional[str] = None
    ) -> None:
        self.status = status
        self.priority = priority
        self.verification_method = verification_method
        self.is_user_doc = is_user_doc
        self.tags = tags or []
        self.bib_authors = bib_authors or []
        self.bib_title = bib_title
        self.bib_source = bib_source
        self.bib_citation_detail = bib_citation_detail
        self.metsuos_knowledge_level = metsuos_knowledge_level
        self.nato_source_reliability = nato_source_reliability
        self.nato_information_credibility = nato_information_credibility

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "status": self.status.value,
            "priority": self.priority.value,
            "verification_method": self.verification_method.value,
            "is_user_doc": self.is_user_doc,
            "tags": self.tags
        }
        if self.bib_authors:
            data["bib_authors"] = self.bib_authors
        if self.bib_title:
            data["bib_title"] = self.bib_title
        if self.bib_source:
            data["bib_source"] = self.bib_source
        if self.bib_citation_detail:
            data["bib_citation_detail"] = self.bib_citation_detail
        if self.metsuos_knowledge_level:
            data["metsuos_knowledge_level"] = self.metsuos_knowledge_level.value
        if self.nato_source_reliability:
            data["nato_source_reliability"] = self.nato_source_reliability
        if self.nato_information_credibility:
            data["nato_information_credibility"] = self.nato_information_credibility
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ItemAttributes":
        raw_method = data.get("verification_method", VerificationMethod.TEST.value)
        try:
            verif_enum = VerificationMethod(raw_method)
        except ValueError:
            verif_enum = VerificationMethod.TEST

        raw_kl = data.get("metsuos_knowledge_level")
        kl_enum = MetsuOSKnowledgeLevel.parse_flexible(raw_kl) if raw_kl else None

        return cls(
            status=StatusEnum(data.get("status", StatusEnum.DRAFT.value)),
            priority=PriorityEnum(data.get("priority", PriorityEnum.MEDIUM.value)),
            verification_method=verif_enum,
            is_user_doc=data.get("is_user_doc", False),
            tags=data.get("tags", []),
            bib_authors=data.get("bib_authors", []),
            bib_title=data.get("bib_title"),
            bib_source=data.get("bib_source"),
            bib_citation_detail=data.get("bib_citation_detail"),
            metsuos_knowledge_level=kl_enum,
            nato_source_reliability=data.get("nato_source_reliability"),
            nato_information_credibility=data.get("nato_information_credibility")
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
        metadata: Optional[ItemMetadata] = None,
        schema_version: str = CURRENT_SCHEMA_VERSION
    ) -> None:
        self.schema_version = schema_version
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
            "schema_version": self.schema_version,
            "id": self.id,
            "phase": self.phase.value if hasattr(self.phase, "value") else str(self.phase),
            "title": self.title,
            "description": self.description,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "attributes": self.attributes.to_dict(),
            "metadata": self.metadata.to_dict()
        }

    @classmethod
    def _migrate_raw_data(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Asegura la migración automática y transparente de datos antiguos sin pérdida de campos."""
        migrated = dict(data)
        
        # 1. Normalizar la fase
        raw_phase = str(migrated.get("phase", "urd")).lower()
        phase_map = {p.value: p.value for p in ESAPhase}
        migrated["phase"] = phase_map.get(raw_phase, "urd")

        # 2. Migrar versión del esquema
        migrated["schema_version"] = CURRENT_SCHEMA_VERSION
        return migrated

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MOMItem":
        # Ejecuta automigración si no coincide con la versión actual
        if data.get("schema_version") != CURRENT_SCHEMA_VERSION:
            data = cls._migrate_raw_data(data)

        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            phase=ESAPhase(data["phase"]),
            title=data["title"],
            description=data["description"],
            parent_ids=data.get("parent_ids", []),
            child_ids=data.get("child_ids", []),
            attributes=ItemAttributes.from_dict(data.get("attributes", {})),
            metadata=ItemMetadata.from_dict(data.get("metadata", {}))
        )

def format_item_id(project_prefix: str, phase_code: str, num: int, min_digits: int = 3) -> str:
    """Genera IDs formateados dinámicamente ajustando el acolchado de ceros al número de dígitos real."""
    digits = max(min_digits, len(str(num)))
    return f"{project_prefix.upper()}-{phase_code.upper()}-{num:0{digits}d}"

# Version: 0.5.2