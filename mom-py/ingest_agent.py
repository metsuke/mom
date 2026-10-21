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
from pdf_parser import MOMPurePDFExtractor

def calculate_sha256(file_path: Path) -> str:
    """Calcula el hash SHA-256 de cualquier archivo para garantizar la cadena de custodia de la fuente matriz."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def extract_text_from_file(file_path: Path) -> str:
    """Extrae texto plano deterministamente desde archivos .md, .txt o .pdf usando el extractor nativo pure-python."""
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        try:
            extractor = MOMPurePDFExtractor(file_path)
            extracted = extractor.extract_full_text_with_page_markers()
            if extracted.strip():
                return extracted
        except Exception as e:
            print(f"⚠️ Extractor PDF nativo reportó advertencia ({e}), intentando fallback de lectura directa...")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="latin-1", errors="ignore") as f:
            return f.read()

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

class MultilingualDeterministicParser:
    """Parser determinista que extrae la jerarquía de despiece y soporta fuentes pareadas."""

    @staticmethod
    def is_bibliography_header(header_text: str) -> bool:
        clean = header_text.lower().strip()
        keywords = ["bibliografía", "bibliografia", "references", "referencias", "works cited", "citaciones", "fuentes"]
        return any(kw in clean for kw in keywords)

    @classmethod
    def parse_text(cls, text: str) -> Tuple[List[Dict[str, Any]], List[str]]:
        nodes = []
        extracted_references = []

        lines = text.splitlines()

        current_page_start = None
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
            p_start = current_page_start
            p_end = current_page_end if current_page_end is not None else current_page_start

            if is_in_bib_section:
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

            page_match = (
                re.search(r'<!--\s*PAGE\s+(\d+)\s*-->', line_str, re.IGNORECASE) or
                re.search(r'^[\-\*\_]{3,}\s*(?:PAGE|PÁGINA|PÁG\.)\s*(\d+)\s*[\-\*\_]{3,}$', line_str, re.IGNORECASE) or
                re.search(r'^(?:PAGE|PÁGINA|PÁG\.)\s+(\d+)$', line_str, re.IGNORECASE)
            )

            if page_match or '\f' in line:
                if buffer_lines:
                    next_page = int(page_match.group(1)) if page_match else (current_page_start + 1 if current_page_start else 1)
                    current_page_end = next_page
                    flush_paragraph()
                    current_page_start = next_page
                    current_page_end = next_page
                else:
                    current_page_start = int(page_match.group(1)) if page_match else (current_page_start + 1 if current_page_start else 1)
                    current_page_end = current_page_start

                cleaned_line = re.sub(r'<!--\s*PAGE\s+\d+\s*-->', '', line_str, flags=re.IGNORECASE).strip()
                cleaned_line = cleaned_line.replace('\f', '').strip()
                if not cleaned_line:
                    continue
                line_str = cleaned_line

            if line_str.startswith("# ") or re.match(r'^(CAPÍTULO|CHAPTER)\s+[\d\w]+', line_str, re.IGNORECASE):
                flush_paragraph()
                paragraph_idx = 0
                current_chapter = line_str.lstrip("# ").strip()
                current_section = "Sección General"
                is_in_bib_section = cls.is_bibliography_header(current_chapter)
                continue

            if line_str.startswith("## ") or line_str.startswith("### ") or re.match(r'^\d+\.\d+\s+', line_str):
                flush_paragraph()
                paragraph_idx = 0
                current_section = line_str.lstrip("#").strip()
                is_in_bib_section = cls.is_bibliography_header(current_section) or cls.is_bibliography_header(current_chapter)
                continue

            buffer_lines.append(line_str)

        flush_paragraph()
        return nodes, extracted_references

class MOMMultilingualIngestionAgent:
    """Agente Ingestor Multilingüe con soporte para pares RAW (Original + Traducción) y Cero Traducción Automática."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.projects_dir = data_dir / "projects"
        self.library_dir = data_dir / "library" / "bib"
        self.proposals_dir = data_dir / "ai-proposals"
        self.pm = ProjectManager(projects_root=self.projects_dir)

        config_path = data_dir / "config.json"
        self.supervisor_name = "Supervisor Humano a Cargo"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.supervisor_name = cfg.get("supervisor_name", self.supervisor_name)
            except Exception:
                pass

        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)

    def ingest_registered_work(self, work_dir: Path) -> Dict[str, Any]:
        """Ejecuta el troceo agéntico directamente leyendo la carpeta de una obra ya registrada por la CLI."""
        meta_file = work_dir / "metadata.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"❌ No se encontró metadata.json en {work_dir}")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        raw_dir = work_dir / "raw"
        raw_files = list(raw_dir.glob("*")) if raw_dir.exists() else []

        orig_file = None
        trans_file = None

        for rf in raw_files:
            if rf.name.startswith("original_"):
                orig_file = rf
            elif rf.name.startswith("translation_"):
                trans_file = rf

        if not orig_file and raw_files:
            orig_file = raw_files[0]

        if not orig_file:
            raise FileNotFoundError(f"❌ No hay ningún archivo fuente en la carpeta RAW de {work_dir}")

        print(f"\n🚀 Iniciando troceo agéntico para la obra registrada '{meta.get('work_id')}'...")
        print(f"  • Archivo Original: {orig_file.name}")
        if trans_file:
            print(f"  • Archivo Traducción: {trans_file.name}")

        return self.ingest_work(
            original_file=orig_file,
            translation_file=trans_file,
            author_id=meta.get("author_id"),
            translator_author_id=None,
            work_code=meta.get("work_id"),
            title=meta.get("title", meta.get("work_id")),
            publisher=meta.get("publisher", "Desconocido"),
            year=meta.get("year", 2026),
            license_type=meta.get("license_type", "Copyright"),
            allow_public_export=meta.get("allow_full_text_export", False)
        )

    def ingest_work(
        self,
        original_file: Path,
        translation_file: Optional[Path],
        author_id: str,
        translator_author_id: Optional[str],
        work_code: str,
        title: str,
        publisher: str = "Desconocido",
        year: int = 2026,
        license_type: str = "Copyright",
        allow_public_export: bool = False
    ) -> Dict[str, Any]:

        if not original_file.exists():
            raise FileNotFoundError(f"❌ El archivo original no existe: {original_file}")

        author_clean = author_id.upper() if author_id.startswith("AUTHOR-") else f"AUTHOR-{author_id.upper()}"
        work_code_clean = work_code.upper()
        work_project_id = f"{author_clean}-{work_code_clean}"
        raw_project_id = f"{work_project_id}-RAW"

        raw_is_private = not allow_public_export

        work_bib_dir = self.library_dir / author_clean / work_code_clean
        raw_bib_dir = work_bib_dir / "raw"
        split_bib_dir = work_bib_dir / "split"
        raw_bib_dir.mkdir(parents=True, exist_ok=True)
        split_bib_dir.mkdir(parents=True, exist_ok=True)

        # 1. Copiar archivo original
        dest_orig = raw_bib_dir / f"original_{original_file.name}"
        if original_file.resolve() != dest_orig.resolve():
            shutil.copy(original_file, dest_orig)
        sha256_orig = calculate_sha256(dest_orig)

        # 2. Copiar archivo de traducción si existe
        dest_trans = None
        sha256_trans = None
        if translation_file and translation_file.exists():
            dest_trans = raw_bib_dir / f"translation_{translation_file.name}"
            if translation_file.resolve() != dest_trans.resolve():
                shutil.copy(translation_file, dest_trans)
            sha256_trans = calculate_sha256(dest_trans)

        # 3. Inicializar Proyectos y Jerarquía Herencial
        ensure_project_exists(self.pm, "MOSBIB", "Pilar Global de Bibliografía", [], False, "Pilar herencial de obras y fuentes bibliográficas")
        ensure_project_exists(self.pm, raw_project_id, f"Fuente Matriz RAW: {title}", [], raw_is_private, f"Archivo maestro original de {title}")
        ensure_project_exists(self.pm, work_project_id, title, [raw_project_id], False, f"Despiece atómico de {title}")
        ensure_project_exists(self.pm, author_clean, author_clean, [work_project_id, "MOSBIB"], False, f"Autor consolidador {author_clean}")
        ensure_project_exists(self.pm, "MOSAUTHOR", "Consolidador Global de Autores", [author_clean], False, "Nodo central de herencia global")

        # 4. Extraer y parsear
        orig_text = extract_text_from_file(dest_orig)
        orig_nodes, orig_refs = MultilingualDeterministicParser.parse_text(orig_text)

        trans_nodes = []
        if dest_trans:
            trans_text = extract_text_from_file(dest_trans)
            trans_nodes, _ = MultilingualDeterministicParser.parse_text(trans_text)

        # Guardar lista de referencias extraídas
        ref_file_path = work_bib_dir / "extracted_references.txt"
        with open(ref_file_path, "w", encoding="utf-8") as f:
            for ref in orig_refs:
                f.write(f"{ref}\n\n")

        # 5. Generar propuestas con trazabilidad de 3 capas
        generated_proposals = 0
        for idx, o_node in enumerate(orig_nodes, 1):
            item_id = f"COR-{work_project_id}-{idx:03d}"
            
            t_node_content = trans_nodes[idx - 1]["content"] if idx <= len(trans_nodes) else None

            p_start = o_node["page_start"]
            page_str = f"Pág. {p_start}" if p_start else "Pág. N/A"

            translation_status = "TRADUCCION_ORIGEN" if t_node_content else "PENDIENTE_TRADUCCION_HUMANA"

            proposal_data = {
                "id": item_id,
                "phase": "cor",
                "title": f"[{page_str}] [{o_node['chapter']}] {o_node['section']} - Pág {o_node['paragraph_num']}.{o_node['sentence_num']}",
                "description": t_node_content or "[PENDIENTE DE TRADUCCIÓN POR EL SUPERVISOR HUMANO]",
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
                    "author": "MOMMultilingualAgent",
                    "created_at": datetime.datetime.now().isoformat(),
                    "version": CURRENT_SCHEMA_VERSION,
                    "declared_in_project": work_project_id,
                    "ai_guardrails": f"Obra: {title} | Supervisor Responsable: {self.supervisor_name}",
                    "multilingual_triplet": {
                        "text_original_en": o_node["content"],
                        "text_es_raw": t_node_content,
                        "text_es_curated": None,
                        "translator_author_id": translator_author_id,
                        "translation_status": translation_status
                    }
                }
            }

            proposal_filename = f"prop_{work_project_id}_{idx:03d}.json"
            with open(self.proposals_dir / proposal_filename, "w", encoding="utf-8") as f:
                json.dump(proposal_data, f, indent=2, ensure_ascii=False)
            generated_proposals += 1

        print("\n=======================================================")
        print(" 🤖 RESULTADO DE INGESTA MULTILINGÜE SOBERANA")
        print("=======================================================")
        print(f"  • Proyecto Obra Despiece:    {work_project_id}")
        print(f"  • Proyecto Fuente RAW:       {raw_project_id}")
        print(f"  • SHA-256 Fuente Original:   {sha256_orig}")
        print(f"  • SHA-256 Traducción Origen: {sha256_trans or 'Sin traducción de origen'}")
        print(f"  • Total Nodos Extraídos:     {len(orig_nodes)}")
        print(f"  • Referencias Bibliográficas: {len(orig_refs)}")
        print(f"  • Propuestas Generadas:      {generated_proposals} en 'data/ai-proposals/'")
        print("=======================================================")

        return {
            "work_project_id": work_project_id,
            "raw_project_id": raw_project_id,
            "sha256_original": sha256_orig,
            "sha256_translation": sha256_trans,
            "total_items": len(orig_nodes),
            "total_references": len(orig_refs),
            "proposals_generated": generated_proposals
        }

def main():
    parser = argparse.ArgumentParser(description="MOM Agent: Ingestor Multilingüe Soberano")
    parser.add_argument("--original", required=True, help="Ruta al archivo original (ej. PDF/MD en inglés)")
    parser.add_argument("--translation", help="Ruta al archivo de traducción de origen (opcional)")
    parser.add_argument("--author", required=True, help="ID de Autor Principal (ej. ESA)")
    parser.add_argument("--translator-author", help="ID de Autor Traductor (ej. AUTHOR-UCHILE)")
    parser.add_argument("--work", required=True, help="ID corto de la obra (ej. PSS05)")
    parser.add_argument("--title", required=True, help="Título completo de la obra")
    parser.add_argument("--publisher", default="ESA", help="Entidad emisora/editorial")
    parser.add_argument("--year", type=int, default=1991, help="Año de publicación")
    parser.add_argument("--license", default="Public Domain", help="Tipo de Licencia")
    parser.add_argument("--public", action="store_true", help="Permitir exportación pública completa")

    args = parser.parse_args()
    data_dir = current_dir.parent / "data"

    agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
    res = agent.ingest_work(
        original_file=Path(args.original),
        translation_file=Path(args.translation) if args.translation else None,
        author_id=args.author,
        translator_author_id=args.translator_author,
        work_code=args.work,
        title=args.title,
        publisher=args.publisher,
        year=args.year,
        license_type=args.license,
        allow_public_export=args.public
    )

if __name__ == "__main__":
    main()

# Version: 0.5.3
# File_Version: 0.5.2.11
# Schema_Version: 0.5.3