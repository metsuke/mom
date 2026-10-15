import json
import shutil
from pathlib import Path
from typing import List, Dict, Set, Optional
from mom.schemas import MOMItem, ESAPhase

class ProjectManager:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            # Ubica 'data/projects' dinámicamente en la raíz del repositorio MOM (sube 2 niveles desde mom-py)
            root_dir = Path(__file__).resolve().parent.parent
            self.data_dir = root_dir / "data" / "projects"
        else:
            self.data_dir = data_dir

        # Auto-inicialización: crea la carpeta de datos automáticamente si no existe
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_project(self, project_name: str, parent_projects: Optional[List[str]] = None) -> Path:
        proj_dir = self.data_dir / project_name
        if proj_dir.exists():
            raise FileExistsError(f"El proyecto '{project_name}' ya existe.")

        for phase in ESAPhase:
            (proj_dir / "src" / phase.value).mkdir(parents=True, exist_ok=True)
        
        (proj_dir / "doc").mkdir(parents=True, exist_ok=True)
        (proj_dir / "vault").mkdir(parents=True, exist_ok=True)
        
        meta = {
            "name": project_name,
            "version": "0.1.0",
            "parent_projects": parent_projects or []
        }
        with open(proj_dir / "project.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return proj_dir

    def get_inheritance_chain(self, target_project: str) -> List[str]:
        """Calcula el orden topológico de resolución de proyectos evitando ciclos."""
        resolved: List[str] = []
        visited: Set[str] = set()

        def dfs(p_name: str, path: Set[str]) -> None:
            if p_name in path:
                raise ValueError(f"Ciclo de herencia detectado: {' -> '.join(path)} -> {p_name}")
            if p_name not in visited:
                visited.add(p_name)
                path.add(p_name)
                p_json = self.data_dir / p_name / "project.json"
                if p_json.exists():
                    with open(p_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for parent in data.get("parent_projects", []):
                        dfs(parent, path)
                path.remove(p_name)
                resolved.append(p_name)

        dfs(target_project, set())
        return resolved

class MOMInheritedRepository:
    """Repositorio que agrega y consolida los elementos del proyecto objetivo y todos sus ancestros."""
    def __init__(self, pm: ProjectManager, project_name: str) -> None:
        self.pm = pm
        self.project_name = project_name
        self.chain = pm.get_inheritance_chain(project_name)
        self.project_dir = pm.data_dir / project_name

    def list_all_consolidated(self) -> Dict[str, MOMItem]:
        """Devuelve un mapa con los elementos acumulados, aplicando sobrescritura de especialización."""
        items: Dict[str, MOMItem] = {}
        for proj_name in self.chain:
            proj_src = self.pm.data_dir / proj_name / "src"
            for phase in ESAPhase:
                p_dir = proj_src / phase.value
                if p_dir.exists():
                    for f_path in p_dir.glob("*.json"):
                        with open(f_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            item = MOMItem.from_dict(data)
                            if not item.metadata.declared_in_project:
                                item.metadata.declared_in_project = proj_name
                            items[item.id] = item
        return items

# Version: 0.2.2