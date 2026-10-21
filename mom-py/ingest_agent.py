import sys
import os
import json
import re
import datetime
import hashlib
import shutil
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from projects import MOMProjectManager as ProjectManager, MOMInheritedRepository
from schemas import MOMItem, ESAPhase, PriorityEnum, StatusEnum, ItemAttributes, ItemMetadata, CURRENT_SCHEMA_VERSION

def calculate_sha256(file_path: Path) -> str:
    """Calcula el hash SHA-256 de cualquier archivo para garantizar la cadena de custodia de la fuente matriz."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def ensure_project_exists(pm: ProjectManager, proj_id: str, name: str, parents: List[str], is_private: bool, desc: str) -> None:
    """Crea o actualiza el project.json de un nodo en el disco respetando sus padres y visibilidad."""
    proj_dir = pm.projects_root / proj_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "specs").mkdir(exist_ok=True)

    json_path = proj_dir / "project.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        curr_parents = meta.get("parents", [])
        for p in parents:
            if p not in curr_parents:
                curr_parents.append(p)
        meta["parents"] = curr_parents
    else:
        meta = {
            "project_id": proj_id,
            "name": name,
            "phase": "COR",
            "parents": parents,
            "is_private": is_private,
            "mandatory": False,
            "description": desc,
            "schema_version": CURRENT_SCHEMA_VERSION
        }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

class DeterministicTextParser:
    """Parser determinista que realiza el despiece atómico:
       Obra ➔ Capítulo ➔ Sección ➔ Párrafo ➔ Frase (Axioma Atómico)
       Mantiene un índice paralelo de paginación y detecta secciones de Bibliografía.
    """

    @staticmethod
    def is_bibliography_header(header_text: str) -> bool:
        """Determina si un capítulo o sección corresponde a la bibliografía / referencias."""
        clean = header_text.lower().strip()
        keywords = ["bibliografía", "bibliografia", "references", "referencias", "works cited", "citaciones", "fuentes"]
        return any(kw in clean for kw in keywords)

    @classmethod
    def parse_document(cls, text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        nodes = []
        extracted_references = []

        lines = text.splitlines()

        current_page_start = None  # None indica que no se han detectado marcas explícitas de página
        current_page_end = None
        current_chapter = "Capítulo General"
        current_section = "Sección Principal"
        
        paragraph_idx = 0
        buffer_lines = []
        is_in_bib_section = False

        def flush_paragraph():
            nonlocal paragraph_idx, buffer_lines, is_in_bib_section
            if not buffer_lines:
                return
            p_text = " ".join(buffer_lines).strip()
            buffer_lines = []
            if not p_text:
                return

            paragraph_idx += 1

            # Rango de páginas paralelas
            p_start = current_page_start
            p_end = current_page_end if current_page_end is not None else current_page_start

            if is_in_bib_section:
                # Tratar cada entrada de la bibliografía como un bloque único/referencia
                extracted_references.append(p_text)
                nodes.append({
                    "page_start": p_start,
                    "page_end": p_end,
                    "chapter": current_chapter,
                    "section": current_section,
                    "paragraph_num": paragraph_idx,
                    "sentence_num": 1,
                    "content": p_text,
                    "is_reference_item": True
                })
            else:
                # Segmentar párrafos comunes en frases (axiomas atómicos)
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', p_text) if len(s.strip()) > 5]
                for s_idx, sentence in enumerate(sentences, 1):
                    nodes.append({
                        "page_start": p_start,
                        "page_end": p_end,
                        "chapter": current_chapter,
                        "section": current_section,
                        "paragraph_num": paragraph_idx,
                        "sentence_num": s_idx,
                        "content": sentence,
                        "is_reference_item": False
                    })

        for line in lines:
            line_str = line.strip()
            if not line_str:
                flush_paragraph()
                continue

            # 1. DETECCIÓN DE PÁGINAS EN PARALELO
            page_match = (
                re.search(r'<!--\s*PAGE\s+(\d+)\s*-->', line_str, re.IGNORECASE) or
                re.search(r'^[\-\*\_]{3,}\s*(?:PAGE|PÁGINA|PÁG\.)\s*(\d+)\s*[\-\*\_]{3,}$', line_str, re.IGNORECASE) or
                re.search(r'^(?:PAGE|PÁGINA|PÁG\.)\s+(\d+)$', line_str, re.IGNORECASE)
            )

            if page_match or '\f' in line:
                if buffer_lines:
                    # El párrafo actual cruza de la página previa a la nueva página
                    if page_match:
                        next_page = int(page_match.group(1))
                    elif current_page_start is not None:
                        next_page = current_page_start + 1
                    else:
                        next_page = 1
                    current_page_end = next_page
                    flush_paragraph()
                    current_page_start = next_page
                    current_page_end = next_page
                else:
                    if page_match:
                        current_page_start = int(page_match.group(1))
                    elif current_page_start is not None:
                        current_page_start += 1
                    else:
                        current_page_start = 1
                    current_page_end = current_page_start

                cleaned_line = re.sub(r'<!--\s*PAGE\s+\d+\s*-->', '', line_str, flags=re.IGNORECASE).strip()
                cleaned_line = cleaned_line.replace('\f', '').strip()
                if not cleaned_line:
                    continue
                line_str = cleaned_line

            # 2. DETECCIÓN DE CAPÍTULOS
            if line_str.startswith("# ") or re.match(r'^(CAPÍTULO|CHAPTER)\s+[\d\w]+', line_str, re.IGNORECASE):
                flush_paragraph()
                paragraph_idx = 0
                current_chapter = line_str.lstrip("# ").strip()
                current_section = "Sección General"
                is_in_bib_section = cls.is_bibliography_header(current_chapter)
                continue

            # 3. DETECCIÓN DE SECCIONES
            if line_str.startswith("## ") or line_str.startswith("### ") or re.match(r'^\d+\.\d+\s+', line_str):
                flush_paragraph()
                paragraph_idx = 0
                current_section = line_str.lstrip("#").strip()
                is_in_bib_section = cls.is_bibliography_header(current_section) or cls.is_bibliography_header(current_chapter)
                continue

            buffer_lines.append(line_str)

        flush_paragraph()
        return nodes, extracted_references

class MOMIngestionAgent:
    """Agente principal de ingesta, despiece y generación de propuestas en data/ai-proposals/."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.projects_dir = data_dir / "projects"
        self.library_dir = data_dir / "library" / "bib"
        self.proposals_dir = data_dir / "ai-proposals"
        self.pm = ProjectManager(projects_root=self.projects_dir)

        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def ingest_bibliographic_work(
        self,
        source_file_path: Path,
        author_id: str,
        work_code: str,
        title: str,
        publisher: str = "Desconocido",
        year: int = 2026,
        license_type: str = "Copyright",
        allow_public_export: bool = False
    ) -> Dict[str, Any]:
        """Ingiere un archivo desde cualquier ruta hacia la biblioteca y genera el despiece atómico con paginación paralela."""

        if not source_file_path.exists():
            raise FileNotFoundError(f"❌ El archivo fuente no existe en: {source_file_path}")

        author_clean = author_id.upper() if author_id.startswith("AUTHOR-") else f"AUTHOR-{author_id.upper()}"
        work_code_clean = work_code.upper()
        work_project_id = f"{author_clean}-{work_code_clean}"
        raw_project_id = f"{work_project_id}-RAW"

        raw_is_private = not allow_public_export

        # 1. Copiar archivo a la estructura de data/library/bib/{AUTHOR}/{WORK}/
        work_bib_dir = self.library_dir / author_clean / work_code_clean
        raw_bib_dir = work_bib_dir / "raw"
        split_bib_dir = work_bib_dir / "split"
        raw_bib_dir.mkdir(parents=True, exist_ok=True)
        split_bib_dir.mkdir(parents=True, exist_ok=True)

        dest_file = raw_bib_dir / source_file_path.name
        shutil.copy(source_file_path, dest_file)
        sha256_hash = calculate_sha256(dest_file)

        # 2. Inicializar Nodos de Proyecto y Cadena de Herencia DAG
        ensure_project_exists(self.pm, "MOSBIB", "Pilar Global de Bibliografía", [], False, "Pilar herencial de obras y fuentes bibliográficas")
        ensure_project_exists(self.pm, raw_project_id, f"Fuente Matriz RAW: {title}", [], raw_is_private, f"Archivo maestro original de {title}")
        ensure_project_exists(self.pm, work_project_id, title, [raw_project_id], False, f"Despiece atómico de {title}")
        ensure_project_exists(self.pm, author_clean, author_clean, [work_project_id, "MOSBIB"], False, f"Autor consolidador {author_clean}")
        ensure_project_exists(self.pm, "MOSAUTHOR", "Consolidador Global de Autores", [author_clean], False, "Nodo central de herencia global")

        # 3. Guardar metadata.json de la obra
        bib_meta = {
            "project_id": work_project_id,
            "raw_project_id": raw_project_id,
            "author_id": author_clean,
            "work_id": work_code_clean,
            "title": title,
            "publisher": publisher,
            "year": year,
            "license_type": license_type,
            "allow_full_text_export": allow_public_export,
            "kill_switch_enabled": False,
            "sha256_hash": sha256_hash,
            "ingested_at": datetime.datetime.now().isoformat()
        }
        with open(work_bib_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(bib_meta, f, indent=2, ensure_ascii=False)

        # 4. Parsing Determinista
        with open(dest_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read()

        parsed_nodes, extracted_references = DeterministicTextParser.parse_document(raw_text)

        # Guardar nodos brutos del despiece
        with open(split_bib_dir / "nodes.json", "w", encoding="utf-8") as f:
            json.dump(parsed_nodes, f, indent=2, ensure_ascii=False)

        # Generar extracted_references.txt con la lista limpia para rastreo agéntico futuro
        ref_file_path = work_bib_dir / "extracted_references.txt"
        with open(ref_file_path, "w", encoding="utf-8") as f:
            for ref in extracted_references:
                f.write(f"{ref}\n\n")

        # 5. Depositar propuestas JSON en data/ai-proposals/
        generated_proposals = 0
        for idx, node in enumerate(parsed_nodes, 1):
            item_id = f"COR-{work_project_id}-{idx:03d}"
            
            p_start = node["page_start"]
            p_end = node["page_end"]
            
            if p_start is None:
                page_str = "Pág. N/A"
            elif p_start == p_end or p_end is None:
                page_str = f"Pág. {p_start}"
            else:
                page_str = f"Págs. {p_start}-{p_end}"

            type_tag = "[REF]" if node.get("is_reference_item") else "[AXIOMA]"
            title_header = f"{type_tag} [{page_str}] [{node['chapter']}] {node['section']} - Pág {node['paragraph_num']}.{node['sentence_num']}"

            proposal_data = {
                "id": item_id,
                "phase": "cor",
                "title": title_header,
                "description": node["content"],
                "parent_ids": [],
                "attributes": {
                    "priority": "HIGH",
                    "status": "PROPOSED",
                    "verification_method": "ANALYSIS",
                    "is_user_doc": True,
                    "decay_rate": 0.05,
                    "supports_item_ids": [],
                    "refutes_item_ids": []
                },
                "metadata": {
                    "author": "MOMIngestAgent",
                    "created_at": datetime.datetime.now().isoformat(),
                    "version": "1.0.0",
                    "declared_in_project": work_project_id,
                    "ai_guardrails": f"Fragmento extraído de {title} ({page_str}, {node['chapter']}, {node['section']}) | Hash: {sha256_hash[:8]}"
                }
            }

            proposal_filename = f"prop_{work_project_id}_{idx:03d}.json"
            with open(self.proposals_dir / proposal_filename, "w", encoding="utf-8") as f:
                json.dump(proposal_data, f, indent=2, ensure_ascii=False)
            generated_proposals += 1

        return {
            "work_project_id": work_project_id,
            "raw_project_id": raw_project_id,
            "sha256_hash": sha256_hash,
            "total_nodes_extracted": len(parsed_nodes),
            "total_references_extracted": len(extracted_references),
            "references_file": str(ref_file_path),
            "proposals_generated": generated_proposals
        }

def main():
    parser = argparse.ArgumentParser(description="MOM Agent: Ingestor y Despiece Soberano")
    parser.add_argument("--file", required=True, help="Ruta al archivo original (desde cualquier carpeta)")
    parser.add_argument("--author", required=True, help="ID de Autor (ej: W3C)")
    parser.add_argument("--work", required=True, help="ID corto de la obra (ej: WCAG22)")
    parser.add_argument("--title", required=True, help="Título completo de la obra")
    parser.add_argument("--publisher", default="W3C", help="Entidad emisora/editorial")
    parser.add_argument("--year", type=int, default=2026, help="Año de publicación")
    parser.add_argument("--license", default="W3C", help="Tipo de Licencia")
    parser.add_argument("--public", action="store_true", help="Permitir exportación pública completa")

    args = parser.parse_args()
    data_dir = current_dir.parent / "data"

    agent = MOMIngestionAgent(data_dir=data_dir)
    result = agent.ingest_bibliographic_work(
        source_file_path=Path(args.file),
        author_id=args.author,
        work_code=args.work,
        title=args.title,
        publisher=args.publisher,
        year=args.year,
        license_type=args.license,
        allow_public_export=args.public
    )

    print("\n=======================================================")
    print(" 🤖 RESULTADO DE LA INGESTA AGÉNTICA DETERMINISTA")
    print("=======================================================")
    print(f"  • Proyecto Obra Despiece:    {result['work_project_id']}")
    print(f"  • Proyecto Fuente RAW:       {result['raw_project_id']}")
    print(f"  • Hash SHA-256 Custodia:     {result['sha256_hash']}")
    print(f"  • Nodos Extraídos:           {result['total_nodes_extracted']}")
    print(f"  • Referencias Bibliográficas: {result['total_references_extracted']} (guardadas en '{result['references_file']}')")
    print(f"  • Propuestas Generadas:      {result['proposals_generated']} en 'data/ai-proposals/'")
    print("=======================================================")
    print("👉 Ejecuta `python mom-py/cli.py` y usa la Opción [9] para revisar y aprobar las propuestas.")

if __name__ == "__main__":
    main()

# Version: 0.5.3
# File_Version: 0.5.2.9
# Schema_Version: 0.5.3