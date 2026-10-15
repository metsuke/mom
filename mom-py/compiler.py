import shutil
from pathlib import Path
from typing import Dict, List, Optional
from projects import MOMInheritedRepository
from schemas import ESAPhase, MOMItem

class MOMCompiler:
    """Compilador de especificaciones atómicas y generador de entregables con soporte de herencia."""
    def __init__(self, repo: MOMInheritedRepository, target_docs_dir: Optional[Path] = None) -> None:
        self.repo = repo
        self.project_dir = repo.project_dir
        self.doc_out = self.project_dir / "doc"
        self.vault_out = self.project_dir / "vault"
        self.agents_out = self.project_dir / "AGENTS.md"
        self.target_docs_dir = target_docs_dir

    def validate_graph(self) -> List[str]:
        """Valida la integridad del grafo ESA acumulado por herencia."""
        errors: List[str] = []
        all_items = self.repo.list_all_consolidated()

        for item_id, item in all_items.items():
            for pid in item.parent_ids:
                if pid not in all_items:
                    errors.append(f"[{item.id}] (de '{item.metadata.declared_in_project}') apunta a parent_id inexistente: '{pid}'")

            if item.phase != ESAPhase.URD and not item.parent_ids:
                errors.append(f"[{item.id}] El elemento de fase '{item.phase.value}' no tiene padres.")

        return errors

    def compile_obsidian_vault(self) -> None:
        """Genera notas Markdown individuales en vault/ con Frontmatter YAML y Wikilinks."""
        self.vault_out.mkdir(parents=True, exist_ok=True)
        all_items = self.repo.list_all_consolidated()

        for item in all_items.values():
            phase_dir = self.vault_out / item.phase.value.upper()
            phase_dir.mkdir(parents=True, exist_ok=True)

            parents_links = ", ".join([f"[[{pid}]]" for pid in item.parent_ids]) if item.parent_ids else "Ninguno (Raíz URD)"
            children_links = ", ".join([f"[[{cid}]]" for cid in item.child_ids]) if item.child_ids else "Ninguno"
            guardrail = f"\n> 🛑 **AI Guardrails (Inmutable):** {item.metadata.ai_guardrails}" if item.metadata.ai_guardrails else ""

            file_content = f"""---
id: "{item.id}"
phase: "{item.phase.value}"
title: "{item.title}"
status: "{item.attributes.status.value}"
priority: "{item.attributes.priority.value}"
author: "{item.metadata.author}"
declared_in: "{item.metadata.declared_in_project}"
---

# {item.id}: {item.title}

## Descripción
{item.description}

## Trazabilidad y Relaciones
* **Origen:** `{item.metadata.declared_in_project}`
* **Padres:** {parents_links}
* **Hijos:** {children_links}
{guardrail}
"""
            note_file = phase_dir / f"{item.id}.md"
            with open(note_file, "w", encoding="utf-8") as f:
                f.write(file_content)

    def compile_all(self) -> None:
        """Genera todos los entregables (doc/*.md, vault/, AGENTS.md) y despliega si hay carpeta target."""
        self.doc_out.mkdir(parents=True, exist_ok=True)
        self.vault_out.mkdir(parents=True, exist_ok=True)
        all_items = self.repo.list_all_consolidated()

        # 1. Compilación de documentos consolidados por fase
        for phase in ESAPhase:
            phase_items = [i for i in all_items.values() if i.phase == phase]
            phase_items.sort(key=lambda x: x.id)

            blocks: List[str] = []
            for item in phase_items:
                guardrail = f"\n> ⚠️ **AI Guardrails:** {item.metadata.ai_guardrails}\n" if item.metadata.ai_guardrails else ""
                parents = f"**Padres:** {', '.join(item.parent_ids)}\n" if item.parent_ids else ""
                children = f"**Hijos:** {', '.join(item.child_ids)}\n" if item.child_ids else ""
                origin = f"**Origen:** `{item.metadata.declared_in_project}`\n"
                
                block = f"## {item.id}: {item.title}\n" \
                        f"**Estado:** `{item.attributes.status.value}` | **Prioridad:** `{item.attributes.priority.value}` | {origin}\n\n" \
                        f"### Descripción\n{item.description}\n\n" \
                        f"{parents}{children}{guardrail}\n---"
                blocks.append(block)

            content = f"# Documentación Consolidada ESA PSS-05 - Fase {phase.value.upper()}\n\n" + "\n\n".join(blocks)
            with open(self.doc_out / f"{phase.value.upper()}.md", "w", encoding="utf-8") as f:
                f.write(content)

        # 2. Compilación del Vault para Obsidian
        self.compile_obsidian_vault()

        # 3. Compilación de AGENTS.md acumulado
        guardrail_items = [i for i in all_items.values() if i.metadata.ai_guardrails]
        blocks = [f"### Componente `{i.id}` ({i.title}) - Origen: `{i.metadata.declared_in_project}`\n> 🛑 **Guardrail Inmutable:** {i.metadata.ai_guardrails}\n" for i in guardrail_items]
        agents_content = "# AGENTS.md - Contexto de Onboarding e Instrucciones para IA\n\n" + "\n".join(blocks)
        with open(self.agents_out, "w", encoding="utf-8") as f:
            f.write(agents_content)

        # 4. Despliegue en la carpeta target de destino
        if self.target_docs_dir:
            self.target_docs_dir.mkdir(parents=True, exist_ok=True)
            for md_file in self.doc_out.glob("*.md"):
                shutil.copy(md_file, self.target_docs_dir / md_file.name)
            if self.agents_out.exists():
                shutil.copy(self.agents_out, self.target_docs_dir / "AGENTS.md")

# Version: 0.2.2