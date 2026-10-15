import json
from pathlib import Path
from typing import Dict, Any
from projects import MOMInheritedRepository, ProjectManager
from compiler import MOMCompiler
from schemas import MOMItem

class MOMAgentInterface:
    """Interfaz estándar para que los agentes de IA interactúen con MOM guardando propuestas en data/ai-proposals/."""
    def __init__(self, repo: MOMInheritedRepository, pm: Optional[ProjectManager] = None) -> None:
        self.repo = repo
        self.compiler = MOMCompiler(repo)
        self.pm = pm or ProjectManager()

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

    def submit_proposal(self, proposed_item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Guarda la propuesta del agente en data/ai-proposals/ para revisión humana posterior."""
        try:
            item = MOMItem.from_dict(proposed_item_data)
            project_name = item.metadata.declared_in_project or self.repo.project_name
            item.metadata.declared_in_project = project_name

            proposal_file = self.pm.ai_proposals_dir / f"{item.id}_{project_name}.json"
            with open(proposal_file, "w", encoding="utf-8") as f:
                json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

            return {
                "success": True, 
                "message": f"Propuesta para '{item.id}' guardada en 'data/ai-proposals/'. Pendiente de revisión humana."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

# Version: 0.2.7