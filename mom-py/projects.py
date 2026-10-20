import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Set, Any
from schemas import MOMItem, format_item_id, CURRENT_SCHEMA_VERSION

class MOMProjectConfig:
    """Configuración del proyecto y sus relaciones de herencia DAG."""
    def __init__(
        self,
        name: str,
        parents: Optional[List[str]] = None,
        is_private: bool = True,
        target_docs_dir: Optional[str] = None,
        mandatory: bool = True,
        schema_version: str = CURRENT_SCHEMA_VERSION
    ) -> None:
        self.name = name
        self.parents = parents or []
        self.is_private = is_private
        self.target_docs_dir = target_docs_dir
        self.mandatory = mandatory
        self.schema_version = schema_version

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "schema_version": self.schema_version,
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
        # Interpretación de valores por defecto si no existen en esquemas antiguos: Privado (True) y Obligatorio/Mandatory (True)
        return cls(
            name=data.get("name", "Un-named"),
            parents=data.get("parents", data.get("parent_projects", [])),
            is_private=data.get("is_private", True),
            target_docs_dir=data.get("target_docs_dir"),
            mandatory=data.get("mandatory", True),
            schema_version=data.get("schema_version", CURRENT_SCHEMA_VERSION)
        )

class MOMInheritedRepository:
    """Maneja la carga, resolución DAG de herencia, filtrado mandatorio y automigración de esquema."""
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
            config = MOMProjectConfig(name=project_path.name, is_private=True, mandatory=True)
            self._save_config(project_path, config)
            return config

        with open(config_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        config = MOMProjectConfig.from_dict(raw_data)

        # Si el project.json no tenía schema_version, is_private o mandatory, lo migramos y guardamos en disco
        if raw_data.get("schema_version") != CURRENT_SCHEMA_VERSION or "is_private" not in raw_data or "mandatory" not in raw_data:
            config.schema_version = CURRENT_SCHEMA_VERSION
            self._save_config(project_path, config)

        return config

    def _save_config(self, project_path: Path, config: MOMProjectConfig) -> None:
        config_file = project_path / "project.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    def _resolve_inheritance_chain(self, start_project: str) -> List[str]:
        """Resuelve el orden topológico de herencia (DAG)."""
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

    def _load_and_migrate_item(self, json_file: Path) -> Optional[MOMItem]:
        """Carga una especificación, la migra si es de un esquema antiguo y actualiza el fichero en disco."""
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            item = MOMItem.from_dict(raw_data)

            # Si el fichero no tenía la versión actual del esquema, se reescribe actualizado
            if raw_data.get("schema_version") != CURRENT_SCHEMA_VERSION:
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

            return item
        except Exception as e:
            print(f"⚠️ Error cargando/migrando especificación '{json_file.name}': {e}")
            return None

    def list_local_items(self) -> List[MOMItem]:
        """Lista los ítems declarados exclusivamente en el proyecto objetivo actual con automigración."""
        items: List[MOMItem] = []
        
        # Buscar en todo el subárbol del proyecto excluyendo project.json, doc y vault
        for json_file in self.project_dir.rglob("*.json"):
            if json_file.name == "project.json" or "doc/" in str(json_file) or "vault/" in str(json_file):
                continue
            item = self._load_and_migrate_item(json_file)
            if item:
                items.append(item)
        return items

    def list_all_consolidated(self) -> Dict[str, MOMItem]:
        """
        Consolida todas las especificaciones a lo largo de la cadena DAG.
        Garantiza que las URD y COR (nodos raíz) se mantengan incluso con mandatory=False.
        Soporta resolución de referencias activas (soporte, refutación y bibliografía).
        """
        project_items_map: Dict[str, Dict[str, MOMItem]] = {}
        project_configs: Dict[str, MOMProjectConfig] = {}

        for proj_name in self.chain:
            p_dir = self.projects_root / proj_name
            if not p_dir.exists():
                continue

            cfg = self._load_config(p_dir)
            project_configs[proj_name] = cfg
            items_dict: Dict[str, MOMItem] = {}

            # Carga recursiva de cualquier especificación dentro del proyecto
            for json_file in p_dir.rglob("*.json"):
                if json_file.name == "project.json" or "doc/" in str(json_file) or "vault/" in str(json_file):
                    continue

                item = self._load_and_migrate_item(json_file)
                if item:
                    if not item.metadata.declared_in_project:
                        item.metadata.declared_in_project = proj_name
                    items_dict[item.id] = item

            project_items_map[proj_name] = items_dict

        # El proyecto actual siempre se incluye 100% completo
        consolidated: Dict[str, MOMItem] = dict(project_items_map.get(self.project_name, {}))

        # Iterar ancestros respetando 'mandatory' pero preservando URD y COR (nodos raíz primarios)
        for proj_name in reversed(self.chain[:-1]):
            cfg = project_configs.get(proj_name, MOMProjectConfig(name=proj_name, is_private=True, mandatory=True))
            ancestor_items = project_items_map.get(proj_name, {})

            if cfg.mandatory:
                for item_id, item in ancestor_items.items():
                    if item_id not in consolidated:
                        consolidated[item_id] = item
            else:
                referenced_ids: Set[str] = set()
                for active_item in list(consolidated.values()):
                    for pid in active_item.parent_ids:
                        referenced_ids.add(pid)
                    if hasattr(active_item.attributes, 'supports_item_ids') and active_item.attributes.supports_item_ids:
                        for sid in active_item.attributes.supports_item_ids:
                            referenced_ids.add(sid)
                    if hasattr(active_item.attributes, 'refutes_item_ids') and active_item.attributes.refutes_item_ids:
                        for rid in active_item.attributes.refutes_item_ids:
                            referenced_ids.add(rid)

                for item_id, ancestor_item in ancestor_items.items():
                    phase_str = ancestor_item.phase.value if hasattr(ancestor_item.phase, 'value') else str(ancestor_item.phase)
                    if item_id not in consolidated:
                        # Preserva el ítem si está referenciado O si pertenece a URD/COR (raíces)
                        if item_id in referenced_ids or phase_str.lower() in ("urd", "cor"):
                            consolidated[item_id] = ancestor_item

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
        """Sincroniza las entradas del archivo .gitignore de la raíz según visibilidad."""
        repo_root = self.projects_root.parent
        gitignore_path = repo_root / ".gitignore"

        lines: List[str] = []
        if gitignore_path.exists():
            with open(gitignore_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines()]

        private_projects: List[str] = []
        for p_dir in self.projects_root.iterdir():
            if p_dir.is_dir():
                cfg = self._load_config(p_dir)
                if cfg.is_private:
                    private_projects.append(f"data/projects/{p_dir.name}/")

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

        new_lines.append("# BEGIN MOM PRIVACY SYNC")
        for priv_entry in sorted(private_projects):
            new_lines.append(priv_entry)
        new_lines.append("# END MOM PRIVACY SYNC")

        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

class MOMProjectManager:
    """Gestor global para la administración de proyectos en data/projects/."""
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
                    configs.append(MOMProjectConfig(name=p_dir.name, is_private=True, mandatory=True))
        return sorted(configs, key=lambda x: x.name)

    def create_project(
        self,
        name: str,
        parents: Optional[List[str]] = None,
        is_private: bool = True,
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

# Version: 0.5.2
# File_Version: 0.5.2.34
# Schema_Version: 0.5.3