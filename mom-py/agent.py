from typing import Dict, Any
from projects import MOMInheritedRepository
from compiler import MOMCompiler
from schemas import MOMItem

class MOMAgentInterface:
    """Interfaz estándar para que los agentes de IA interactúen con MOM sin romper contratos."""
    def __init__(self, repo: MOMInheritedRepository) -> None:
        self.repo = repo
        self.compiler = MOMCompiler(repo)

    def get_context_for_task(self, item_id: str) -> Dict[str, Any]:
        """Obtiene el contexto de un ítem y sus padres inmutables para consumo del agente."""
        all_items = self.repo.list_all_consolidated()
        item = all_items.get(item_id)
        if not item:
            return {"error": f"Ítem {item_id} no encontrado en el proyecto o sus ancestros."}

        parents = [all_items[pid].to_dict() for pid in item.parent_ids if pid in all_items]
        
        return {
            "target_item": item.to_dict(),
            "immutable_parents_context": parents,
            "ai_guardrails": item.metadata.ai_guardrails,
            "instruction": (
                "NO PUEDES modificar la firma de entrada/salida ni romper los contratos "
                "de los parent_ids proporcionados. Cualquier cambio debe ceñirse a ai_guardrails."
            )
        }

    def validate_agent_proposal(self, proposed_item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Valida que la propuesta del agente mantenga la integridad del grafo ESA."""
        try:
            _ = MOMItem.from_dict(proposed_item_data)
            errors = self.compiler.validate_graph()
            if errors:
                return {"valid": False, "errors": errors}
            return {"valid": True, "message": "Propuesta válida acorde a las reglas ESA PSS-05."}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}

# Version: 0.2.2