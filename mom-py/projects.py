import json
import shutil
from pathlib import Path
from typing import List, Dict, Set, Optional
from schemas import MOMItem, ESAPhase

class ProjectManager:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            # Ubica 'data' dinámicamente en la raíz del repositorio MOM (sube 2 niveles desde mom-py)
            self.root_dir = Path(__file__).resolve().parent.parent
            self.data_dir = self.root_dir / "data" / "projects"
            self.ai_proposals_dir = self.root_dir / "data" / "ai-proposals"
            self.global_templates_dir = self.root_dir / "data" / "templates"
        else:
            self.root_dir = data_dir.parent.parent
            self.data_dir = data_dir
            self.ai_proposals_dir = data_dir.parent / "ai-proposals"
            self.global_templates_dir = data_dir.parent / "templates"

        self.gitignore_path = self.root_dir / ".gitignore"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.ai_proposals_dir.mkdir(parents=True, exist_ok=True)
        self.global_templates_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_default_templates()

    def _ensure_default_templates(self) -> None:
        """Crea las plantillas agnósticas por defecto en data/templates/ si no existen."""
        default_urd = """# Documento de Requisitos de Usuario (URD) - {{PROJECT_NAME}}\n\n## 1. Introducción y Alcance\nEste documento define los Requisitos de Usuario para el proyecto **{{PROJECT_NAME}}**.\n\n## 2. Especificaciones Atómicas de Usuario\n{{MOM_ATOMIC_ITEMS}}\n"""
        default_srd = """# Documento de Requisitos de Software (SRD) - {{PROJECT_NAME}}\n\n## 1. Introducción y Alcance\nEste documento especifica las capacidades funcionales y no funcionales para **{{PROJECT_NAME}}**.\n\n## 2. Especificaciones Atómicas de Software\n{{MOM_ATOMIC_ITEMS}}\n"""
        default_add = """# Documento de Diseño Arquitectónico (ADD) - {{PROJECT_NAME}}\n\n## 1. Arquitectura General\nDefinición de componentes y límites del sistema para **{{PROJECT_NAME}}**.\n\n## 2. Especificaciones Atómicas de Arquitectura\n{{MOM_ATOMIC_ITEMS}}\n"""
        default_ddd = """# Documento de Diseño Detallado (DDD) - {{PROJECT_NAME}}\n\n## 1. Diseño Estructurado\nDetalle de implementación e interfaces internas para **{{PROJECT_NAME}}**.\n\n## 2. Especificaciones Atómicas de Diseño Detallado\n{{MOM_ATOMIC_ITEMS}}\n"""
        default_index = """---\nproject: "{{PROJECT_NAME}}"\ntype: "vault-index"\n---\n\n# Vault de Navegación ESA PSS-05: {{PROJECT_NAME}}\n\nBienvenido al espacio de documentación navegable del proyecto **{{PROJECT_NAME}}**.\n\n## Documentos de Fase Completos\n* [[URD]]: Documento de Requisitos de Usuario\n* [[SRD]]: Documento de Requisitos de Software\n* [[ADD]]: Documento de Diseño Arquitectónico\n* [[DDD]]: Documento de Diseño Detallado\n\n## Trazabilidad y Herencia DAG\n* **Cadena de Herencia:** {{INHERITANCE_CHAIN}}\n"""

        templates = {
            "URD.md.template": default_urd,
            "SRD.md.template": default_srd,
            "ADD.md.template": default_add,
            "DDD.md.template": default_ddd,
            "INDEX.md.template": default_index,
        }

        for filename, content in templates.items():
            tpl_path = self.global_templates_dir / filename
            if not tpl_path.exists():
                with open(tpl_path, "w", encoding="utf-8") as f:
                    f.write(content)

    def sync_gitignore_privacy(self, project_name: str, is_private: bool) -> None:
        """Añade o elimina la ruta del proyecto privado en el archivo .gitignore raíz."""
        if not self.gitignore_path.exists():
            return

        rule = f"data/projects/{project_name}/"
        with open(self.gitignore_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        rule_exists = any(line.strip() == rule for line in lines)

        if is_private and not rule_exists:
            # Añadir la regla de exclusión al final del gitignore
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(f"{rule}\n")
            with open(self.gitignore_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        elif not is_private and rule_exists:
            # Eliminar la regla de exclusión si pasó a ser público
            new_lines = [line for line in lines if line.strip() != rule]
            with open(self.gitignore_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

    def create_project(self, project_name: str, parent_projects: Optional[List[str]] = None, target_docs_dir: Optional[str] = None, is_private: bool = False) -> Path:
        proj_dir = self.data_dir / project_name
        if proj_dir.exists():
            raise FileExistsError(f"El proyecto '{project_name}' ya existe.")

        for phase in ESAPhase:
            (proj_dir / "src" / phase.value).mkdir(parents=True, exist_ok=True)
        
        (proj_dir / "doc").mkdir(parents=True, exist_ok=True)
        (proj_dir / "vault").mkdir(parents=True, exist_ok=True)
        (proj_dir / "templates").mkdir(parents=True, exist_ok=True)
        
        meta = {
            "name": project_name,
            "version": "0.1.0",
            "is_private": is_private,
            "parent_projects": parent_projects or [],
            "target_docs_dir": target_docs_dir or ""
        }
        with open(proj_dir / "project.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # Sincronizar estado con .gitignore
        self.sync_gitignore_privacy(project_name, is_private)

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
        
        self.target_docs_dir: Optional[Path] = None
        self.is_private: bool = False
        proj_json = self.project_dir / "project.json"
        if proj_json.exists():
            with open(proj_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.is_private = data.get("is_private", False)
                target_raw = data.get("target_docs_dir", "").strip()
                if target_raw:
                    self.target_docs_dir = Path(target_raw)

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

# Version: 0.3.0