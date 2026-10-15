import json
from pathlib import Path
from typing import List, Optional
from schemas import MOMItem, ESAPhase

class MOMRepository:
    """Gestor de persistencia atómica para un proyecto concreto."""
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self.src_dir = project_dir / "src"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for phase in ESAPhase:
            (self.src_dir / phase.value).mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, phase: ESAPhase, item_id: str) -> Path:
        return self.src_dir / phase.value / f"{item_id}.json"

    def create_item(self, item: MOMItem) -> MOMItem:
        file_path = self._get_file_path(item.phase, item.id)
        if file_path.exists():
            raise FileExistsError(f"El ítem {item.id} ya existe en {file_path}")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

        self._sync_parent_references(item, add=True)
        return item

    def read_item(self, item_id: str) -> Optional[MOMItem]:
        for phase in ESAPhase:
            file_path = self._get_file_path(phase, item_id)
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return MOMItem.from_dict(data)
        return None

    def update_item(self, item: MOMItem) -> MOMItem:
        existing = self.read_item(item.id)
        if not existing:
            raise FileNotFoundError(f"El ítem {item.id} no existe.")

        file_path = self._get_file_path(item.phase, item.id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

        self._sync_parent_references(item, add=True)
        return item

    def delete_item(self, item_id: str) -> bool:
        item = self.read_item(item_id)
        if not item:
            return False

        self._sync_parent_references(item, add=False)
        file_path = self._get_file_path(item.phase, item.id)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_all(self, phase: Optional[ESAPhase] = None) -> List[MOMItem]:
        items: List[MOMItem] = []
        phases_to_scan = [phase] if phase else list(ESAPhase)
        for p in phases_to_scan:
            p_dir = self.src_dir / p.value
            if p_dir.exists():
                for f_path in p_dir.glob("*.json"):
                    with open(f_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        items.append(MOMItem.from_dict(data))
        return items

    def _sync_parent_references(self, item: MOMItem, add: bool = True) -> None:
        for parent_id in item.parent_ids:
            parent = self.read_item(parent_id)
            if parent:
                if add and item.id not in parent.child_ids:
                    parent.child_ids.append(item.id)
                    self._save_raw(parent)
                elif not add and item.id in parent.child_ids:
                    parent.child_ids.remove(item.id)
                    self._save_raw(parent)

    def _save_raw(self, item: MOMItem) -> None:
        file_path = self._get_file_path(item.phase, item.id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)

# Version: 0.2.2