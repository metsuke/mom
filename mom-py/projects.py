import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Set, Any
from schemas import MOMItem, format_item_id

class MOMProjectConfig:
    """Configuración del proyecto y sus relaciones de herencia DAG."""
    def __init__(
        self,
        name: str,
        parents: Optional[List[str]] = None,
        is_private: bool = False,
        target_docs_dir: Optional[str] = None,
        mandatory: bool = True
    ) -> None:
        self.name = name
        self.parents = parents or []
        self.is_private = is_private
        self.target_docs_dir = target_docs_dir
        self.mandatory = mandatory

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "name": self.name,
            "parents": self.parents,
            "is_private": self.is_private,
            "mandatory": self.mandatory
        }
        if self.target_docs_dir:
            data["target_docs_dir"] = self.target_docs_dir
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MOMProjectConfig":
        return cls(
            name=data["name"],
            parents=data.get("parents", []),
            is_private=data.get("is_private", False),
            target_docs_dir=data.get("target_docs_dir"),
            mandatory=data.get("mandatory", True)
        )

class MOMInheritedRepository:
    """Maneja la carga, resolución DAG de herencia y filtrado mandatorio/referencial de proyectos MOM."""
    def __init__(self, projects_root: Path, target_project_name: str) -> None:
        self.projects_root = projects_root
        self.project_name = target_project_name
        self.project_dir = projects_root / target_project_name
        
        if not self.project_dir.exists():
            raise FileNotFoundError(f"El proyecto '{target_project_name}' no existe en {projects_root}")

        self.config = self._load_config(self.project_dir)
        self.chain = self._resolve_inheritance_chain(target_project_name)

    def _load_config(self, project_path: Path) -> MOMProjectConfig:
        config_file = project_path / "project.json"
        if not config_file.exists():
            # Configuración por defecto si no existe project.json
            return MOMProjectConfig(name=project_path.name)
        with open(config_file, "r", encoding="utf-8") as f:
            return MOMProjectConfig.from_dict(json.load(f))

    def _save_config(self, project_path: Path, config: MOMProjectConfig) -> None:
        config_file = project_path / "project.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    def _resolve_inheritance_chain(self, start_project: str) -> List[str]:
        """Resuelve el orden topológico de herencia (DAG) desde los ancestros raíz hasta el proyecto hijo."""
        visited: Set[str] = set()
        chain: List[str] = []

        def dfs(p_name: str):
            if p_name in visited:
                return
            visited.add(p_name)
            p_dir = self.projects_root / p_name
            if p_dir.exists():
                cfg = self._load_config(p_dir)
                for parent in cfg.parents:
                    dfs(parent)
            chain.append(p_name)

        dfs(start_project)
        return chain

    @property
    def target_docs_dir(self) -> Optional[Path]:
        if self.config.target_docs_dir:
            return Path(self.config.target_docs_dir)
        return None

    def list_local_items(self) -> List[MOMItem]:
        """Lista los ítems declarados exclusivamente en el proyecto objetivo actual."""
        items: List[MOMItem] = []
        specs_dir = self.project_dir / "specs"
        if not specs_dir.exists():
            return items

        for json_file in specs_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    item = MOMItem.from_dict(data)
                    items.append(item)
            except Exception as e:
                print(f"⚠️ Error cargando especificación '{json_file.name}': {e}")
        return items

    def list_all_consolidated(self) -> Dict[str, MOMItem]:
        """
        Acumula y consolida todas las especificaciones a lo largo de la cadena DAG de herencia.
        Respeta la regla global 'mandatory':
          - mandatory = True: El proyecto aporta la totalidad de sus especificaciones.
          - mandatory = False: El proyecto sólo aporta las especificaciones citadas explícitamente 
            como 'parent_ids' por algún proyecto hijo.
        """
        # Cargar todas las especificaciones por proyecto en la cadena
        project_items_map: Dict[str, Dict[str, MOMItem]] = {}
        project_configs: Dict[str, MOMProjectConfig] = {}

        for proj_name in self.chain:
            p_dir = self.projects_root / proj_name
            if not p_dir.exists():
                continue

            cfg = self._load_config(p_dir)
            project_configs[proj_name] = cfg
            items_dict: Dict[str, MOMItem] = {}

            specs_dir = p_dir / "specs"
            if specs_dir.exists():
                for json_file in specs_dir.glob("*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            item = MOMItem.from_dict(json.load(f))
                            # Registrar origen si no está marcado
                            if not item.metadata.declared_in_project:
                                item.metadata.declared_in_project = proj_name
                            items_dict[item.id] = item
                    except Exception as e:
                        print(f"⚠️ Error en '{json_file.name}' de '{proj_name}': {e}")

            project_items_map[proj_name] = items_dict

        # El proyecto objetivo (el último en la cadena) siempre se consolida completo
        consolidated: Dict[str, MOMItem] = dict(project_items_map.get(self.project_name, {}))

        # Iterar hacia atrás desde los ancestros
        # Para proyectos con mandatory=False, recopilaremos sólo los IDs necesitados por los hijos
        for proj_name in reversed(self.chain[:-1]):
            cfg = project_configs.get(proj_name, MOMProjectConfig(name=proj_name))
            ancestor_items = project_items_map.get(proj_name, {})

            if cfg.mandatory:
                # Herencia mandatoria: Se importan todos los ítems del ancestro
                for item_id, item in ancestor_items.items():
                    if item_id not in consolidated:
                        consolidated[item_id] = item
            else:
                # Herencia no mandatoria (condicional por referencia/bibliografía):
                # Se buscan los parent_ids citados activamente por los ítems ya consolidados
                referenced_ids: Set[str] = set()
                for active_item in list(consolidated.values()):
                    for pid in active_item.parent_ids:
                        referenced_ids.add(pid)

                # Importar sólo los ítems referenciados
                for ref_id in referenced_ids:
                    if ref_id in ancestor_items and ref_id not in consolidated:
                        consolidated[ref_id] = ancestor_items[ref_id]

        return consolidated

    def save_item(self, item: MOMItem) -> Path:
        """Guarda o actualiza una especificación atómica MOMItem en el proyecto local."""
        specs_dir = self.project_dir / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)

        if not item.metadata.declared_in_project:
            item.metadata.declared_in_project = self.project_name

        file_path = specs_dir / f"{item.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

        return file_path

    def sync_gitignore(self) -> None:
        """Sincroniza dinámicamente las entradas del archivo .gitignore de la raíz del repositorio según visibilidad."""
        repo_root = self.projects_root.parent
        gitignore_path = repo_root / ".gitignore"

        # Leer entradas existentes
        lines: List[str] = []
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines()]

        # Buscar todos los proyectos privados
        private_projects: List[str] = []
        for p_dir in self.projects_root.iterdir():
            if p_dir.is_dir():
                cfg = self._load_config(p_dir)
                if cfg.is_private:
                    private_projects.append(f"data/projects/{p_dir.name}/")

        # Reconstruir o actualizar la sección bloqueada de MOM Privacy Sync
        new_lines: List[str] = []
        in_mom_section = False

        for line in lines:
            if line == "# BEGIN MOM PRIVACY SYNC":
                in_mom_section = True
                continue
            if line == "# END MOM PRIVACY SYNC":
                in_mom_section = False
                continue
            if not in_mom_section:
                new_lines.append(line)

        # Añadir bloque actualizado
        new_lines.append("# BEGIN MOM PRIVACY SYNC")
        for priv_entry in sorted(private_projects):
            new_lines.append(priv_entry)
        new_lines.append("# END MOM PRIVACY SYNC")

        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

class MOMProjectManager:
    """Gestor global para la creación, enumeración y administración de proyectos en data/projects/."""
    def __init__(self, projects_root: Path) -> None:
        self.projects_root = projects_root
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def list_projects(self) -> List[MOMProjectConfig]:
        configs: List[MOMProjectConfig] = []
        for p_dir in self.projects_root.iterdir():
            if p_dir.is_dir():
                config_file = p_dir / "project.json"
                if config_file.exists():
                    with open(config_file, "r", encoding="utf-8") as f:
                        configs.append(MOMProjectConfig.from_dict(json.load(f)))
                else:
                    configs.append(MOMProjectConfig(name=p_dir.name))
        return sorted(configs, key=lambda x: x.name)

    def create_project(
        self,
        name: str,
        parents: Optional[List[str]] = None,
        is_private: bool = False,
        target_docs_dir: Optional[str] = None,
        mandatory: bool = True
    ) -> MOMInheritedRepository:
        project_dir = self.projects_root / name
        project_dir.mkdir(parents=True, exist_ok=True)

        (project_dir / "specs").mkdir(exist_ok=True)
        (project_dir / "doc").mkdir(exist_ok=True)
        (project_dir / "vault").mkdir(exist_ok=True)
        (project_dir / "templates").mkdir(exist_ok=True)

        config = MOMProjectConfig(
            name=name,
            parents=parents or [],
            is_private=is_private,
            target_docs_dir=target_docs_dir,
            mandatory=mandatory
        )

        config_file = project_dir / "project.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

        repo = MOMInheritedRepository(self.projects_root, name)
        repo.sync_gitignore()
        return repo

# Version: 0.5.0