import os
import sys
import json
import re
import datetime
import hashlib
import shutil
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from projects import MOMProjectManager as ProjectManager
from schemas import CURRENT_SCHEMA_VERSION
from pdf_extractor_ultra import extract_pdf_ultra


def calculate_sha256(file_path: Path) -> str:
    """Calcula el hash SHA-256 para garantizar la cadena de custodia de la fuente matriz."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def clean_extracted_line(line_str: str) -> str:
    """Limpia marcas de agua, pies de página y encabezados ruidosos."""
    if "everyspec.com" in line_str.lower():
        return ""
    if re.search(r'downloaded from https?://', line_str, re.IGNORECASE):
        return ""
    return line_str.strip()


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


class AtomicGraphParser:
    """
    Parser Atómico Jerárquico Causal para Metodología MOM / ESA PSS-05.
    Despieza el texto en:
      - Páginas (COR)
      - Capítulos (URD)
      - Secciones / Tablas (SRD)
      - Párrafos / Filas de Tabla (ADD)
      - Frases / Axiomas / Celdas (DDD)
      - Bibliografía (COR-BIB)
    Filtra automáticamente tablas de contenidos / índices.
    """

    @staticmethod
    def is_toc_line(line_str: str) -> bool:
        """Combinación de filtros para detectar líneas pertenecientes a un Índice o Tabla de Contenidos."""
        clean = line_str.strip()
        if not clean:
            return False
        
        # Filtro 1: Puntos o guiones suspensivos de relleno hacia un número de página (ej: '1.2 Introducción ..... 14')
        if re.search(r'[\.\-\_\s]{4,}\s*\d+\s*$', clean):
            return True
        
        # Filtro 2: Patrón estricto de número de sección + título + número de página al final
        if re.match(r'^(?:\d+\.)+\d*\s+[\w\s\.\,\-\(\)]+\s+\d+$', clean, re.IGNORECASE):
            return True

        return False

    @staticmethod
    def is_toc_header(header_text: str) -> bool:
        """Detecta encabezados explícitos de Índice / Table of Contents."""
        clean = header_text.lower().strip()
        toc_keywords = ["table of contents", "contents", "index", "índice", "indice", "tabla de contenidos", "tabla de contenido"]
        return any(kw in clean for kw in toc_keywords)

    @staticmethod
    def is_bibliography_header(header_text: str) -> bool:
        """Detecta encabezados de Bibliografía o Referencias."""
        clean = header_text.lower().strip()
        keywords = ["bibliografía", "bibliografia", "references", "referencias", "works cited", "citaciones", "fuentes"]
        return any(kw in clean for kw in keywords)

    @classmethod
    def parse_document_to_graph(cls, raw_text: str) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
        """
        Analiza el documento entero y devuelve:
          1. Diccionario de páginas: {num_pagina: texto_completo_pagina}
          2. Lista de nodos del grafo con sus jerarquías y referencias de páginas.
        """
        lines = raw_text.splitlines()

        pages_map: Dict[int, List[str]] = {}
        current_page = 1
        pages_map[current_page] = []

        # Paso 1: Mapeo completo de texto por páginas
        for line in lines:
            line_str = clean_extracted_line(line)
            page_match = re.search(r'<!--\s*PAGE\s+(\d+)\s*-->', line_str, re.IGNORECASE)
            if page_match:
                current_page = int(page_match.group(1))
                if current_page not in pages_map:
                    pages_map[current_page] = []
                continue
            
            pages_map[current_page].append(line_str)

        pages_text_map: Dict[int, str] = {p: "\n".join(lines_list).strip() for p, lines_list in pages_map.items()}

        # Paso 2: Despiece Jerárquico en Árbol Causal
        graph_nodes = []
        is_in_toc = False
        is_in_bib = False

        current_chapter_title = "Capítulo General"
        current_chapter_lines: List[str] = []
        current_chapter_start_page = 1
        current_chapter_end_page = 1

        current_section_title = "Sección Principal"
        current_section_lines: List[str] = []
        current_section_start_page = 1
        current_section_end_page = 1

        active_page = 1

        for line in lines:
            line_str = clean_extracted_line(line)
            if not line_str:
                continue

            page_match = re.search(r'<!--\s*PAGE\s+(\d+)\s*-->', line_str, re.IGNORECASE)
            if page_match:
                active_page = int(page_match.group(1))
                continue

            # Detectar si estamos entrando o saliendo de un Índice
            if cls.is_toc_header(line_str):
                is_in_toc = True
                continue

            # Si es una línea con formato claro de índice, omitir
            if is_in_toc:
                if line_str.startswith("# ") or line_str.startswith("## "):
                    if not cls.is_toc_header(line_str):
                        is_in_toc = False
                elif cls.is_toc_line(line_str):
                    continue

            if cls.is_toc_line(line_str):
                continue

            # Detectar Bibliografía
            if cls.is_bibliography_header(line_str):
                is_in_bib = True

            # Detectar Cambio de Capítulo (# o CHAPTER)
            if line_str.startswith("# ") or re.match(r'^(CAPÍTULO|CHAPTER)\s+[\d\w]+', line_str, re.IGNORECASE):
                current_chapter_title = line_str.lstrip("# ").strip()
                current_chapter_start_page = active_page
                current_chapter_end_page = active_page
                current_section_title = "Sección General"
                current_section_start_page = active_page
                current_section_end_page = active_page
                continue

            # Detectar Cambio de Sección (## o ###)
            if line_str.startswith("## ") or line_str.startswith("### ") or re.match(r'^\d+\.\d+\s+', line_str):
                current_section_title = line_str.lstrip("#").strip()
                current_section_start_page = active_page
                current_section_end_page = active_page
                continue

            # Caso especial: Bloques de Bibliografía
            if is_in_bib:
                graph_nodes.append({
                    "type": "BIB",
                    "chapter": "Bibliografía",
                    "section": "Referencias",
                    "content": line_str,
                    "start_page": active_page,
                    "end_page": active_page
                })
                continue

            # Procesamiento de Contenido Normal (Párrafos y Tablas)
            graph_nodes.append({
                "type": "CONTENT",
                "chapter": current_chapter_title,
                "section": current_section_title,
                "content": line_str,
                "start_page": active_page,
                "end_page": active_page
            })

        return pages_text_map, graph_nodes


class MOMMultilingualIngestionAgent:
    """Agente Ingestor ULTRA: Emite propuestas atómicas organizadas por el Grafo Causal ESA."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.projects_dir = data_dir / "projects"
        self.library_dir = data_dir / "library" / "bib"
        self.proposals_dir = data_dir / "ai-proposals"
        self.root_dir = data_dir.parent
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

    def generate_html_graph_viewer(self, work_project_id: str, total_proposals: int) -> Path:
        """Genera un visor HTML interactivo con Mermaid CDN en la raíz del proyecto para visualizar el grafo."""
        proposal_files = sorted(list(self.proposals_dir.glob(f"prop_{work_project_id}_*.json")))

        mermaid_edges = []
        node_labels = []

        for pf in proposal_files:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                node_id = data["id"]
                title = data["title"].replace('"', "'")
                parents = data.get("parent_ids", [])
                
                # Etiqueta compacta
                node_labels.append(f'  {node_id}["<b>{node_id}</b><br/>{title[:35]}..."]')
                
                for p_id in parents:
                    mermaid_edges.append(f'  {p_id} --> {node_id}')
            except Exception:
                continue

        mermaid_content = "graph TD\n" + "\n".join(node_labels[:300]) + "\n" + "\n".join(mermaid_edges[:500])

        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grafo de Propuestas MOM - {work_project_id}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #0d1117;
            color: #c9d1d9;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            background-color: #161b22;
            padding: 15px 25px;
            border-radius: 8px;
            border: 1px solid #30363d;
            margin-bottom: 20px;
        }}
        h1 {{ color: #58a6ff; margin: 0 0 10px 0; font-size: 24px; }}
        .stats {{ color: #8b949e; font-size: 14px; }}
        .mermaid-container {{
            background-color: #161b22;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #30363d;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Grafo Causal Atómico de Propuestas: {work_project_id}</h1>
        <div class="stats">
            • Total propuestas atómicas generadas: <strong>{total_proposals}</strong><br/>
            • Visualizando vista jerárquica DAG (Páginas COR ➔ Capítulos URD ➔ Secciones SRD ➔ Párrafos ADD ➔ Axiomas DDD)
        </div>
    </div>
    <div class="mermaid-container">
        <pre class="mermaid">
{mermaid_content}
        </pre>
    </div>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'dark', flowChart: {{ curve: 'basis' }} }});
    </script>
</body>
</html>
"""
        html_file = self.root_dir / "graph_proposal_viewer.html"
        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"🌐 [VISOR GRAFO HTML] Generado con éxito en la raíz: {html_file.name}")
        return html_file

    def ingest_registered_work(self, work_dir: Path, source_lang: str = "en") -> Dict[str, Any]:
        """Ejecuta la ingesta ULTRA leyendo la carpeta de una obra ya registrada."""
        meta_file = work_dir / "metadata.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"❌ No se encontró metadata.json en {work_dir}")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        raw_dir = work_dir / "raw"
        raw_files = [f for f in raw_dir.glob("*") if f.is_file() and not f.name.startswith(".")] if raw_dir.exists() else []

        if not raw_files:
            raise FileNotFoundError(f"❌ No hay ningún archivo fuente en la carpeta RAW de {work_dir}")

        orig_file = raw_files[0]

        return self.ingest_work(
            original_file=orig_file,
            author_id=meta.get("author_id"),
            work_code=meta.get("work_id"),
            title=meta.get("title", meta.get("work_id")),
            publisher=meta.get("publisher", "Desconocido"),
            year=meta.get("year", 2026),
            license_type=meta.get("license_type", "Copyright"),
            allow_public_export=meta.get("allow_full_text_export", False),
            source_lang=source_lang
        )

    def ingest_work(
        self,
        original_file: Path,
        author_id: str,
        work_code: str,
        title: str,
        publisher: str = "Desconocido",
        year: int = 2026,
        license_type: str = "Copyright",
        allow_public_export: bool = False,
        source_lang: str = "en"
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

        dest_orig = raw_bib_dir / f"original_{original_file.name}"
        if original_file.resolve() != dest_orig.resolve():
            shutil.copy(original_file, dest_orig)
        sha256_orig = calculate_sha256(dest_orig)

        # Extracción vía Motor ULTRA
        if dest_orig.suffix.lower() == ".pdf":
            extracted_md_path = extract_pdf_ultra(str(dest_orig), str(split_bib_dir))
            with open(extracted_md_path, "r", encoding="utf-8") as f:
                orig_text = f.read()
        else:
            with open(dest_orig, "r", encoding="utf-8", errors="ignore") as f:
                orig_text = f.read()

        extracted_orig_md = split_bib_dir / "original_extracted.md"
        with open(extracted_orig_md, "w", encoding="utf-8") as f:
            f.write(orig_text)

        ensure_project_exists(self.pm, "MOSBIB", "Pilar Global de Bibliografía", [], False, "Pilar herencial de obras y fuentes bibliográficas")
        ensure_project_exists(self.pm, raw_project_id, f"Fuente Matriz RAW: {title}", [], raw_is_private, f"Archivo maestro original de {title}")
        ensure_project_exists(self.pm, work_project_id, title, [raw_project_id], False, f"Despiece atómico de {title}")
        ensure_project_exists(self.pm, author_clean, author_clean, [work_project_id, "MOSBIB"], False, f"Autor consolidador {author_clean}")

        # Parseo Atómico
        pages_text_map, raw_nodes = AtomicGraphParser.parse_document_to_graph(orig_text)

        generated_proposals = 0
        proposal_counter = 1

        # 1. EMITIR NODOS COR PARA LAS PÁGINAS INDIVIDUALES
        page_node_ids: Dict[int, str] = {}
        for page_num, p_text in pages_text_map.items():
            pag_item_id = f"COR-{work_project_id}-PAG-{page_num:03d}"
            page_node_ids[page_num] = pag_item_id

            pag_proposal_data = {
                "id": pag_item_id,
                "phase": "cor",
                "title": f"[Página {page_num}] Texto Íntegro de la Página {page_num}",
                "description": p_text if p_text else f"[Página {page_num} sin texto extraíble]",
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
                    "ai_guardrails": f"Obra: {title} | Página {page_num}",
                    "multilingual_triplet": {
                        "source_language": source_lang,
                        "text_original": p_text,
                        "text_es_raw": None,
                        "text_es_curated": None,
                        "translation_status": "ORIGINAL_ONLY"
                    }
                }
            }

            filename = f"prop_{work_project_id}_{proposal_counter:04d}_PAG.json"
            with open(self.proposals_dir / filename, "w", encoding="utf-8") as f:
                json.dump(pag_proposal_data, f, indent=2, ensure_ascii=False)
            generated_proposals += 1
            proposal_counter += 1

        # 2. EMITIR NODOS JERÁRQUICOS Y BIBLIOGRAFÍA
        chapter_cache: Dict[str, str] = {}
        section_cache: Dict[str, str] = {}
        paragraph_counter = 1
        axiom_counter = 1
        bib_counter = 1

        for node in raw_nodes:
            p_start = node["start_page"]
            p_end = node["end_page"]
            
            p_start_id = page_node_ids.get(p_start, f"COR-{work_project_id}-PAG-{p_start:03d}")
            p_end_id = page_node_ids.get(p_end, f"COR-{work_project_id}-PAG-{p_end:03d}")
            
            page_parents = list(set([p_start_id, p_end_id]))

            # CASO A: ELEMENTOS DE BIBLIOGRAFÍA (COR-BIB-*)
            if node["type"] == "BIB":
                bib_id = f"COR-{work_project_id}-BIB-{bib_counter:03d}"
                bib_counter += 1

                proposal_data = {
                    "id": bib_id,
                    "phase": "cor",
                    "title": f"[Bibliografía] Cita/Fuente #{bib_counter-1}",
                    "description": node["content"],
                    "parent_ids": page_parents,
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
                        "ai_guardrails": f"Obra: {title} | Referencia Bibliográfica",
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": node["content"],
                            "text_es_raw": None,
                            "text_es_curated": None,
                            "translation_status": "ORIGINAL_ONLY"
                        }
                    }
                }

                filename = f"prop_{work_project_id}_{proposal_counter:04d}_BIB.json"
                with open(self.proposals_dir / filename, "w", encoding="utf-8") as f:
                    json.dump(proposal_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1
                continue

            # CASO B: CONTENIDO REGULAR DE LA OBRA (URD -> SRD -> ADD -> DDD)
            c_title = node["chapter"]
            if c_title not in chapter_cache:
                cap_id = f"URD-{work_project_id}-CAP-{len(chapter_cache)+1:03d}"
                chapter_cache[c_title] = cap_id

                cap_data = {
                    "id": cap_id,
                    "phase": "urd",
                    "title": f"[Capítulo] {c_title}",
                    "description": f"Capítulo completo: {c_title}",
                    "parent_ids": page_parents,
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
                        "ai_guardrails": f"Obra: {title} | Capítulo",
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": c_title,
                            "text_es_raw": None,
                            "text_es_curated": None,
                            "translation_status": "ORIGINAL_ONLY"
                        }
                    }
                }
                with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_CAP.json", "w", encoding="utf-8") as f:
                    json.dump(cap_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1

            current_cap_id = chapter_cache[c_title]

            s_title = node["section"]
            sec_key = f"{c_title}::{s_title}"
            if sec_key not in section_cache:
                sec_id = f"SRD-{work_project_id}-SEC-{len(section_cache)+1:03d}"
                section_cache[sec_key] = sec_id

                sec_data = {
                    "id": sec_id,
                    "phase": "srd",
                    "title": f"[Sección] {s_title}",
                    "description": f"Sección completa: {s_title}",
                    "parent_ids": list(set([current_cap_id] + page_parents)),
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
                        "ai_guardrails": f"Obra: {title} | Sección",
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": s_title,
                            "text_es_raw": None,
                            "text_es_curated": None,
                            "translation_status": "ORIGINAL_ONLY"
                        }
                    }
                }
                with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_SEC.json", "w", encoding="utf-8") as f:
                    json.dump(sec_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1

            current_sec_id = section_cache[sec_key]

            # PÁRRAFO (ADD)
            par_id = f"ADD-{work_project_id}-PAR-{paragraph_counter:03d}"
            paragraph_counter += 1

            par_data = {
                "id": par_id,
                "phase": "add",
                "title": f"[Párrafo #{paragraph_counter-1}] {node['content'][:40]}...",
                "description": node["content"],
                "parent_ids": list(set([current_sec_id] + page_parents)),
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
                    "ai_guardrails": f"Obra: {title} | Párrafo",
                    "multilingual_triplet": {
                        "source_language": source_lang,
                        "text_original": node["content"],
                        "text_es_raw": None,
                        "text_es_curated": None,
                        "translation_status": "ORIGINAL_ONLY"
                    }
                }
            }
            with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_PAR.json", "w", encoding="utf-8") as f:
                json.dump(par_data, f, indent=2, ensure_ascii=False)
            generated_proposals += 1
            proposal_counter += 1

            # AXIOMAS / FRASES (DDD)
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z1-9\*\-\"\(])', node["content"]) if len(s.strip()) > 5]
            if not sentences:
                sentences = [node["content"]]

            for s_text in sentences:
                axi_id = f"DDD-{work_project_id}-AXI-{axiom_counter:03d}"
                axiom_counter += 1

                axi_data = {
                    "id": axi_id,
                    "phase": "ddd",
                    "title": f"[Axioma Atómico] {s_text[:40]}...",
                    "description": s_text,
                    "parent_ids": list(set([par_id] + page_parents)),
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
                        "ai_guardrails": f"Obra: {title} | Axioma Atómico",
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": s_text,
                            "text_es_raw": None,
                            "text_es_curated": None,
                            "translation_status": "ORIGINAL_ONLY"
                        }
                    }
                }
                with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_AXI.json", "w", encoding="utf-8") as f:
                    json.dump(axi_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1

        # Generar visor HTML con Mermaid CDN
        self.generate_html_graph_viewer(work_project_id, generated_proposals)

        print("\n=======================================================")
        print(" 🤖 RESULTADO DE CAPTURA ATÓMICA Y GRAFO ESA")
        print("=======================================================")
        print(f"  • Proyecto Obra Despiece:    {work_project_id}")
        print(f"  • SHA-256 Fuente Original:   {sha256_orig}")
        print(f"  • Páginas Creadas (COR):     {len(pages_text_map)}")
        print(f"  • Capítulos Creados (URD):   {len(chapter_cache)}")
        print(f"  • Secciones Creadas (SRD):   {len(section_cache)}")
        print(f"  • Párrafos Creados (ADD):    {paragraph_counter-1}")
        print(f"  • Axiomas Creados (DDD):     {axiom_counter-1}")
        print(f"  • Citas Bibliográficas (BIB): {bib_counter-1}")
        print(f"  • Propuestas Generadas:      {generated_proposals} en 'data/ai-proposals/'")
        print(f"  • Visor HTML Creado:         graph_proposal_viewer.html")
        print("=======================================================")

        return {
            "status": "SUCCESS",
            "work_project_id": work_project_id,
            "raw_project_id": raw_project_id,
            "sha256_original": sha256_orig,
            "proposals_generated": generated_proposals
        }


def main():
    parser = argparse.ArgumentParser(description="MOM Agent: Ingestor ULTRA y Generador del Grafo Causal ESA")
    parser.add_argument("--original", required=True, help="Ruta al archivo original (ej. PDF/MD en inglés)")
    parser.add_argument("--author", required=True, help="ID de Autor Principal (ej. ESA)")
    parser.add_argument("--work", required=True, help="ID corto de la obra (ej. PSS05)")
    parser.add_argument("--title", required=True, help="Título completo de la obra")
    parser.add_argument("--publisher", default="ESA", help="Entidad emisora/editorial")
    parser.add_argument("--year", type=int, default=1991, help="Año de publicación")
    parser.add_argument("--license", default="Public Domain", help="Tipo de Licencia")
    parser.add_argument("--public", action="store_true", help="Permitir exportación pública completa")
    parser.add_argument("--lang", default="en", help="Código de idioma de origen (ej. en, es)")

    args = parser.parse_args()
    data_dir = current_dir.parent / "data"

    agent = MOMMultilingualIngestionAgent(data_dir=data_dir)
    agent.ingest_work(
        original_file=Path(args.original),
        author_id=args.author,
        work_code=args.work,
        title=args.title,
        publisher=args.publisher,
        year=args.year,
        license_type=args.license,
        allow_public_export=args.public,
        source_lang=args.lang
    )


if __name__ == "__main__":
    main()

# App Version: 0.7.0
# Script Version: 0.7.0.0
# Compatible Schema: 0.5.3