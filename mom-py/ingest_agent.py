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
      - Capítulos (URD)
      - Secciones (SRD)
      - Párrafos (ADD)
      - Axiomas / Frases (DDD)
    Filtra rigurosamente tablas de contenidos / índices para evitar contaminación en proposals.
    """

    @staticmethod
    def is_toc_line(line_str: str) -> bool:
        clean = line_str.strip()
        if not clean:
            return False
        if re.search(r'[\.\-\_\s]{4,}\s*\d+\s*$', clean):
            return True
        if re.match(r'^(?:\d+\.)+\d*\s+[\w\s\.\,\-\(\)]+\s+\d+$', clean, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def is_toc_header(header_text: str) -> bool:
        clean = header_text.lower().strip()
        toc_keywords = ["table of contents", "contents", "index", "índice", "indice", "tabla de contenidos", "tabla de contenido"]
        return any(kw in clean for kw in toc_keywords)

    @staticmethod
    def is_bibliography_header(header_text: str) -> bool:
        clean = header_text.lower().strip()
        keywords = ["bibliografía", "bibliografia", "references", "referencias", "works cited", "citaciones", "fuentes"]
        return any(kw in clean for kw in keywords)

    @classmethod
    def parse_document_to_graph(cls, raw_text: str) -> Tuple[Dict[int, str], List[Dict[str, Any]]]:
        lines = raw_text.splitlines()

        pages_map: Dict[int, List[str]] = {}
        current_page = 1
        pages_map[current_page] = []

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

        graph_nodes = []
        is_in_toc = False
        is_in_bib = False

        current_chapter_title = "Capítulo General"
        current_section_title = "Sección Principal"
        active_page = 1

        for line in lines:
            line_str = clean_extracted_line(line)
            if not line_str:
                continue

            page_match = re.search(r'<!--\s*PAGE\s+(\d+)\s*-->', line_str, re.IGNORECASE)
            if page_match:
                active_page = int(page_match.group(1))
                continue

            # DETECCIÓN Y EXCLUSIÓN ESTRICTA DEL ÍNDICE / TOC
            if cls.is_toc_header(line_str):
                is_in_toc = True
                continue

            if is_in_toc:
                if line_str.startswith("# ") or line_str.startswith("## "):
                    if not cls.is_toc_header(line_str):
                        is_in_toc = False
                elif cls.is_toc_line(line_str):
                    continue

            if cls.is_toc_line(line_str):
                continue

            if cls.is_bibliography_header(line_str):
                is_in_bib = True

            if line_str.startswith("# ") or re.match(r'^(CAPÍTULO|CHAPTER)\s+[\d\w]+', line_str, re.IGNORECASE):
                current_chapter_title = line_str.lstrip("# ").strip()
                current_section_title = "Sección General"
                continue

            if line_str.startswith("## ") or line_str.startswith("### ") or re.match(r'^\d+\.\d+\s+', line_str):
                current_section_title = line_str.lstrip("#").strip()
                continue

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
        self.root_dir = Path(__file__).resolve().parent.parent
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

    def _purge_existing_proposals_for_work(self, work_project_id: str) -> int:
        """Borra todas las propuestas creadas previamente para este proyecto de obra en ai-proposals/."""
        purged_count = 0
        if not self.proposals_dir.exists():
            return 0

        for pf in self.proposals_dir.glob("*.json"):
            try:
                if f"_{work_project_id}_" in pf.name or pf.name.startswith(f"prop_{work_project_id}_"):
                    pf.unlink()
                    purged_count += 1
                else:
                    with open(pf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("metadata", {}).get("declared_in_project") == work_project_id:
                        pf.unlink()
                        purged_count += 1
            except Exception:
                pass

        if purged_count > 0:
            print(f"🧹 [PURGA PREVIA] Se han eliminado {purged_count} propuesta(s) obsoleta(s) de '{work_project_id}'.")
        return purged_count

    def generate_html_graph_viewer(self, work_project_id: str, target_split_dir: Path) -> Path:
        """
        Genera el visor HTML interactivo con inspección inferior del texto RAW completo,
        reconstrucción bottom-up y comparador Diff estilo GitHub estricto.
        """
        proposal_files = list(self.proposals_dir.glob("*.json"))

        proposals_dict: Dict[str, Dict[str, Any]] = {}
        chapters_master_list: List[Dict[str, str]] = []

        total_analyzed = 0
        for pf in proposal_files:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    data = json.load(f)

                declared_proj = data.get("metadata", {}).get("declared_in_project", "")
                if work_project_id and work_project_id != "ALL" and work_project_id not in declared_proj:
                    continue

                total_analyzed += 1
                n_id = data.get("id")
                proposals_dict[n_id] = data

                if data.get("phase") == "urd" and n_id.startswith(f"URD-{work_project_id}-CAP-"):
                    raw_title = data.get("title", n_id)
                    clean_title = raw_title.replace("[Capítulo]", "").strip()
                    chapters_master_list.append({
                        "id": n_id,
                        "title": clean_title,
                        "raw_title": raw_title
                    })
            except Exception:
                continue

        chapters_master_list.sort(key=lambda x: x["id"])

        all_nodes_json_raw = json.dumps(proposals_dict, ensure_ascii=False)
        chapters_json_raw = json.dumps(chapters_master_list, ensure_ascii=False)

        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Visor e Inspector de Grafo MOM - {work_project_id}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/diff@5.1.0/dist/diff.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0d1117;
            color: #c9d1d9;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            background-color: #161b22;
            padding: 12px 20px;
            border-radius: 8px;
            border: 1px solid #30363d;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        h1 {{ color: #58a6ff; margin: 0; font-size: 20px; }}
        .stats {{ color: #8b949e; font-size: 13px; }}

        .controls-wrapper {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            background-color: #161b22;
            padding: 10px 15px;
            border-radius: 8px;
            border: 1px solid #30363d;
            margin-bottom: 15px;
        }}
        .btn {{
            background-color: #21262d;
            color: #58a6ff;
            border: 1px solid #30363d;
            padding: 6px 14px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .btn:hover:not(:disabled) {{
            background-color: #30363d;
            border-color: #8b949e;
        }}
        .btn:disabled {{
            color: #484f58;
            cursor: not-allowed;
            border-color: #21262d;
        }}
        select.custom-select {{
            background-color: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
            max-width: 450px;
            text-overflow: ellipsis;
        }}

        .main-layout {{
            display: flex;
            gap: 15px;
            align-items: flex-start;
        }}
        .sidebar {{
            width: 280px;
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 12px;
            max-height: 85vh;
            overflow-y: auto;
            flex-shrink: 0;
        }}
        .sidebar h3 {{
            color: #79c0ff;
            font-size: 14px;
            margin-top: 0;
            margin-bottom: 10px;
            border-bottom: 1px solid #30363d;
            padding-bottom: 5px;
        }}
        .chapter-item {{
            padding: 8px 10px;
            margin-bottom: 5px;
            background-color: #21262d;
            border: 1px solid #30363d;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            color: #c9d1d9;
            transition: background 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .chapter-item:hover, .chapter-item.active {{
            background-color: #1f6feb;
            color: #ffffff;
            border-color: #58a6ff;
        }}

        .content-area {{
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            gap: 15px;
            width: calc(100% - 295px);
        }}

        .graph-card {{
            background-color: #161b22;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #30363d;
            min-height: 380px;
            overflow-x: auto;
        }}
        #mermaid-target {{
            width: 100%;
        }}

        /* PANEL INFERIOR DE INSPECCIÓN Y DIFF ESTILO GITHUB */
        .inspection-panel {{
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px;
            width: 100%;
        }}
        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #30363d;
            padding-bottom: 10px;
            margin-bottom: 12px;
        }}
        .panel-title {{
            font-size: 15px;
            font-weight: bold;
            color: #58a6ff;
        }}
        .panel-meta {{
            font-size: 12px;
            color: #8b949e;
        }}

        .diff-columns {{
            display: flex;
            gap: 15px;
            width: 100%;
        }}
        .diff-col {{
            flex: 1;
            width: 50%;
            background-color: #0d1117;
            border: 1px solid #21262d;
            border-radius: 6px;
            padding: 12px;
            display: flex;
            flex-direction: column;
        }}
        .diff-col-title {{
            font-size: 13px;
            font-weight: 600;
            color: #79c0ff;
            margin-bottom: 8px;
            padding-bottom: 4px;
            border-bottom: 1px solid #21262d;
        }}
        .text-box {{
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            font-size: 12px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            color: #c9d1d9;
            max-height: 300px;
            overflow-y: auto;
        }}

        /* ESTILOS DIFF GITHUB ESTRICTO */
        .diff-added {{
            background-color: rgba(46, 160, 67, 0.25);
            color: #3fb950;
            text-decoration: none;
        }}
        .diff-removed {{
            background-color: rgba(248, 81, 73, 0.25);
            color: #f85149;
            text-decoration: line-through;
        }}
        .diff-match {{
            color: #8b949e;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Visor Inspector del Grafo: {work_project_id}</h1>
        <div class="stats">
            Nodos Atómicos: <strong>{total_analyzed}</strong> | Capítulos: <strong>{len(chapters_master_list)}</strong>
        </div>
    </div>

    <div class="controls-wrapper">
        <button id="btn-prev" class="btn" onclick="navigateChapter(-1)">◀ Cap. Anterior</button>
        <select id="master-select" class="custom-select" onchange="onChapterSelectChange(this.value)"></select>
        <button id="btn-next" class="btn" onclick="navigateChapter(1)">Cap. Siguiente ▶</button>
    </div>

    <div class="main-layout">
        <div class="sidebar">
            <h3>📚 Capítulos (Nodos Maestro)</h3>
            <div id="chapters-list"></div>
        </div>

        <div class="content-area">
            <!-- VISOR GRAFO MERMAID -->
            <div class="graph-card">
                <div id="mermaid-target"></div>
            </div>

            <!-- PANEL INFERIOR COMPLEMENTARIO DE RECONSTRUCCIÓN Y DIFF -->
            <div class="inspection-panel">
                <div class="panel-header">
                    <div id="panel-node-title" class="panel-title">Seleccione un nodo en el diagrama</div>
                    <div id="panel-node-meta" class="panel-meta">Fase: - | ID: -</div>
                </div>

                <div class="diff-columns">
                    <!-- MITAD IZQUIERDA: TEXTO RAW COMPLETO ALMACENADO EN EL NODO -->
                    <div class="diff-col">
                        <div class="diff-col-title">📄 Texto RAW Íntegro Almacenado en el Nodo (Padre)</div>
                        <div id="stored-text-box" class="text-box">Seleccione un nodo para inspeccionar su contenido.</div>
                    </div>

                    <!-- MITAD DERECHA: RECONSTRUCCIÓN BOTTOM-UP + DIFF GITHUB -->
                    <div class="diff-col">
                        <div class="diff-col-title">🔍 Reconstrucción Bottom-Up (Concatenación Hijos) + Diff</div>
                        <div id="reconstructed-diff-box" class="text-box">Esperando selección de nodo...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const allNodes = {all_nodes_json_raw};
        const masterChapters = {chapters_json_raw};
        let currentChapterIdx = 0;
        let currentParentId = "";

        mermaid.initialize({{
            startOnLoad: false,
            theme: 'dark',
            flowChart: {{ curve: 'basis' }}
        }});

        function initViewer() {{
            const select = document.getElementById('master-select');
            const listContainer = document.getElementById('chapters-list');
            
            select.innerHTML = '';
            listContainer.innerHTML = '';

            if (masterChapters.length === 0) {{
                document.getElementById('mermaid-target').innerHTML = '<div style="color:#8b949e; text-align:center;">ℹ️ No hay Capítulos registrados.</div>';
                return;
            }}

            masterChapters.forEach((ch, idx) => {{
                const chapNum = (idx + 1).toString().padStart(2, '0');
                const labelText = "Capítulo " + chapNum + ": " + ch.title.substring(0, 35);

                const opt = document.createElement('option');
                opt.value = idx;
                opt.innerText = labelText;
                select.appendChild(opt);

                const item = document.createElement('div');
                item.className = 'chapter-item' + (idx === 0 ? ' active' : '');
                item.id = 'chap-item-' + idx;
                item.title = ch.raw_title;
                item.innerText = labelText;
                item.onclick = () => selectChapterIndex(idx);
                listContainer.appendChild(item);
            }});

            selectChapterIndex(0);
        }}

        function selectChapterIndex(idx) {{
            currentChapterIdx = idx;
            document.getElementById('master-select').value = idx;
            
            document.querySelectorAll('.chapter-item').forEach((el, i) => {{
                el.classList.toggle('active', i === idx);
            }});

            const chap = masterChapters[idx];
            if (chap) {{
                focusOnNode(chap.id);
            }}
        }}

        function onChapterSelectChange(valStr) {{
            selectChapterIndex(parseInt(valStr, 10));
        }}

        function navigateChapter(delta) {{
            const newIdx = currentChapterIdx + delta;
            if (newIdx >= 0 && newIdx < masterChapters.length) {{
                selectChapterIndex(newIdx);
            }}
        }}

        function getNodeRawContent(node) {{
            if (!node) return "";
            return node.raw_content || node.metadata?.multilingual_triplet?.text_original || node.description || "";
        }}

        /* RECONSTRUCCIÓN BOTTOM-UP Y INSPECCIÓN EN EL PANEL INFERIOR */
        function inspectNodeDetails(nodeId) {{
            const parentNode = allNodes[nodeId];
            if (!parentNode) return;

            document.getElementById('panel-node-title').innerText = (parentNode.title || nodeId);
            document.getElementById('panel-node-meta').innerText = "ID: " + nodeId + " | Fase: " + (parentNode.phase || 'N/A').toUpperCase();

            // Texto RAW literal almacenado directo en el padre
            const storedRaw = getNodeRawContent(parentNode);
            document.getElementById('stored-text-box').innerText = storedRaw || "(Nodo sin contenido raw registrado)";

            // Búsqueda y ordenación estricta de Hijos Directos
            const children = [];
            for (const [nid, ndata] of Object.entries(allNodes)) {{
                const parents = ndata.parent_ids || [];
                if (parents.includes(nodeId)) {{
                    children.push(ndata);
                }}
            }}

            // Ordenar hijos por el atributo sequence_index
            children.sort((a, b) => {{
                const seqA = a.attributes?.sequence_index ?? 9999;
                const seqB = b.attributes?.sequence_index ?? 9999;
                return seqA - seqB;
            }});

            const diffBox = document.getElementById('reconstructed-diff-box');

            if (children.length === 0) {{
                diffBox.innerHTML = '<i style="color:#8b949e;">(Nodo atómico hoja - No tiene nodos hijos para reconstruir)</i>';
                return;
            }}

            // Reconstruir texto concatenando el raw_content de los hijos
            let reconstructedText = "";
            children.forEach((c, index) => {{
                const sep = c.attributes?.separator_before ?? (index === 0 ? "" : "\\n\\n");
                const cRaw = getNodeRawContent(c);
                if (index === 0) {{
                    reconstructedText += cRaw;
                }} else {{
                    reconstructedText += sep + cRaw;
                }}
            }});

            // CALCULAR Y RENDERIZAR DIFF ESTILO GITHUB (ESTRICTO)
            const diffs = Diff.diffChars(storedRaw, reconstructedText);
            let diffHtml = "";

            diffs.forEach(part => {{
                const colorClass = part.added ? 'diff-added' : (part.removed ? 'diff-removed' : 'diff-match');
                const escapedText = part.value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
                diffHtml += '<span class="' + colorClass + '">' + escapedText + '</span>';
            }});

            diffBox.innerHTML = diffHtml;
        }}

        async function focusOnNode(parentId) {{
            currentParentId = parentId;
            inspectNodeDetails(parentId);

            const target = document.getElementById('mermaid-target');
            const btnPrev = document.getElementById('btn-prev');
            const btnNext = document.getElementById('btn-next');

            btnPrev.disabled = (currentChapterIdx === 0);
            btnNext.disabled = (currentChapterIdx === masterChapters.length - 1);

            // Filtrar Hijos Directos de Nivel 1
            const directChildren = [];
            for (const [nid, ndata] of Object.entries(allNodes)) {{
                const parents = ndata.parent_ids || [];
                if (parents.includes(parentId)) {{
                    directChildren.push(nid);
                }}
            }}

            const parentNode = allNodes[parentId];
            const parentTitle = parentNode ? (parentNode.title || parentId).replace('"', "'").replace("\\n", " ").trim() : parentId;

            const nodeLabels = [];
            const edges = [];

            nodeLabels.push('  ' + parentId + '["<b>ROOT: ' + parentId + '</b><br/><i>' + parentTitle.substring(0, 35) + '...</i>"]');

            if (directChildren.length === 0) {{
                nodeLabels.push('  EMPTY_CHILD["<i>(Sin nodos hijos directos)</i>"]');
                edges.push('  ' + parentId + ' --> EMPTY_CHILD');
            }} else {{
                directChildren.forEach(childId => {{
                    const cNode = allNodes[childId];
                    const cTitle = cNode ? (cNode.title || childId).replace('"', "'").replace("\\n", " ").trim() : childId;
                    nodeLabels.push('  ' + childId + '["<b>' + childId + '</b><br/>' + cTitle.substring(0, 30) + '..."]');
                    edges.push('  ' + parentId + ' --> ' + childId);
                }});
            }}

            const mermaidCode = "graph LR\\n" + nodeLabels.join("\\n") + "\\n" + edges.join("\\n");

            try {{
                const {{ svg }} = await mermaid.render('mermaid-svg-' + Date.now(), mermaidCode);
                target.innerHTML = svg;

                setTimeout(() => {{
                    const svgContainer = target.querySelector('svg');
                    if (svgContainer) {{
                        const nodes = svgContainer.querySelectorAll('.node');
                        nodes.forEach(n => {{
                            n.style.cursor = 'pointer';
                            n.onclick = (e) => {{
                                e.stopPropagation();
                                const fullId = n.id || '';
                                for (const nid of Object.keys(allNodes)) {{
                                    if (fullId.includes(nid) || n.textContent.includes(nid)) {{
                                        focusOnNode(nid);
                                        break;
                                    }}
                                }}
                            }};
                        }});
                    }}
                }}, 100);

            }} catch (err) {{
                target.innerHTML = '<div style="color:#f85149; text-align:center;">❌ Error al renderizar vista del grafo.</div>';
                console.error(err);
            }}
        }}

        window.addEventListener('DOMContentLoaded', initViewer);
    </script>
</body>
</html>
"""
        dest_html = target_split_dir / "graph_proposal_viewer.html"
        with open(dest_html, "w", encoding="utf-8") as f:
            f.write(html_content)

        print(f"🌐 [VISOR HTML CON DIFF Y RECONSTRUCCIÓN BOTTOM-UP GENERADO]:")
        print(f"  • Guardado en: {dest_html.resolve()}")

        return dest_html

    def ingest_registered_work(self, work_dir: Path, source_lang: str = "en") -> Dict[str, Any]:
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

        self._purge_existing_proposals_for_work(work_project_id)

        orig_name = original_file.name
        clean_name = re.sub(r'^(original_)+', '', orig_name, flags=re.IGNORECASE)
        target_raw_filename = f"original_{clean_name}"
        dest_orig = raw_bib_dir / target_raw_filename

        if original_file.resolve() != dest_orig.resolve():
            shutil.copy(original_file, dest_orig)

        sha256_orig = calculate_sha256(dest_orig)

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

        pages_text_map, raw_nodes = AtomicGraphParser.parse_document_to_graph(orig_text)

        generated_proposals = 0
        proposal_counter = 1

        # 1. ACUMULACIÓN PREVIA DE TEXTO BRUTO ("RAW") REAL PARA CAPÍTULOS Y SECCIONES
        chapters_raw_map: Dict[str, List[str]] = {}
        sections_raw_map: Dict[str, List[str]] = {}

        for node in raw_nodes:
            if node["type"] == "BIB":
                continue
            c_title = node["chapter"]
            s_title = node["section"]
            sec_key = f"{c_title}::{s_title}"
            content = node["content"]

            if c_title not in chapters_raw_map:
                chapters_raw_map[c_title] = []
            chapters_raw_map[c_title].append(content)

            if sec_key not in sections_raw_map:
                sections_raw_map[sec_key] = []
            sections_raw_map[sec_key].append(content)

        # 2. EMISIÓN DE PROPROPUESTAS CON CAMPO `raw_content` LITERAL
        chapter_cache: Dict[str, str] = {}
        section_cache: Dict[str, str] = {}
        chapter_children_count: Dict[str, int] = {}
        section_children_count: Dict[str, int] = {}
        paragraph_axiom_count: Dict[str, int] = {}

        paragraph_counter = 1
        axiom_counter = 1
        bib_counter = 1

        for node in raw_nodes:
            if node["type"] == "BIB":
                bib_id = f"COR-{work_project_id}-BIB-{bib_counter:03d}"
                bib_counter += 1

                raw_text = node["content"]
                proposal_data = {
                    "id": bib_id,
                    "phase": "cor",
                    "title": f"Cita/Fuente #{bib_counter-1}",
                    "description": f"Referencia bibliográfica #{bib_counter-1}",
                    "raw_content": raw_text,
                    "parent_ids": [raw_project_id],
                    "attributes": {
                        "priority": "HIGH",
                        "status": "PROPOSED",
                        "sequence_index": bib_counter - 1,
                        "separator_before": "\n"
                    },
                    "metadata": {
                        "author": "MOMMultilingualAgent",
                        "created_at": datetime.datetime.now().isoformat(),
                        "version": CURRENT_SCHEMA_VERSION,
                        "declared_in_project": work_project_id,
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": raw_text
                        }
                    }
                }

                filename = f"prop_{work_project_id}_{proposal_counter:04d}_BIB.json"
                with open(self.proposals_dir / filename, "w", encoding="utf-8") as f:
                    json.dump(proposal_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1
                continue

            c_title = node["chapter"]
            if c_title not in chapter_cache:
                cap_id = f"URD-{work_project_id}-CAP-{len(chapter_cache)+1:03d}"
                chapter_cache[c_title] = cap_id
                chapter_children_count[cap_id] = 0

                # Contenido RAW completo del Capítulo
                cap_raw_content = "\n\n".join(chapters_raw_map.get(c_title, [c_title]))

                cap_data = {
                    "id": cap_id,
                    "phase": "urd",
                    "title": c_title,
                    "description": f"Nodo contenedor del capítulo: {c_title}",
                    "raw_content": cap_raw_content,
                    "parent_ids": [work_project_id],
                    "attributes": {
                        "priority": "HIGH",
                        "status": "PROPOSED",
                        "sequence_index": len(chapter_cache),
                        "separator_before": "\n\n"
                    },
                    "metadata": {
                        "author": "MOMMultilingualAgent",
                        "created_at": datetime.datetime.now().isoformat(),
                        "version": CURRENT_SCHEMA_VERSION,
                        "declared_in_project": work_project_id,
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": cap_raw_content
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
                section_children_count[sec_id] = 0

                chapter_children_count[current_cap_id] += 1
                sec_seq = chapter_children_count[current_cap_id]

                # Contenido RAW completo de la Sección
                sec_raw_content = "\n\n".join(sections_raw_map.get(sec_key, [s_title]))

                sec_data = {
                    "id": sec_id,
                    "phase": "srd",
                    "title": s_title,
                    "description": f"Nodo contenedor de la sección: {s_title}",
                    "raw_content": sec_raw_content,
                    "parent_ids": [current_cap_id],
                    "attributes": {
                        "priority": "HIGH",
                        "status": "PROPOSED",
                        "sequence_index": sec_seq,
                        "separator_before": "\n\n"
                    },
                    "metadata": {
                        "author": "MOMMultilingualAgent",
                        "created_at": datetime.datetime.now().isoformat(),
                        "version": CURRENT_SCHEMA_VERSION,
                        "declared_in_project": work_project_id,
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": sec_raw_content
                        }
                    }
                }
                with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_SEC.json", "w", encoding="utf-8") as f:
                    json.dump(sec_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1

            current_sec_id = section_cache[sec_key]

            par_id = f"ADD-{work_project_id}-PAR-{paragraph_counter:03d}"
            paragraph_counter += 1

            section_children_count[current_sec_id] += 1
            par_seq = section_children_count[current_sec_id]

            par_raw_content = node["content"]
            par_data = {
                "id": par_id,
                "phase": "add",
                "title": f"Párrafo #{paragraph_counter-1}",
                "description": f"Bloque de párrafo {paragraph_counter-1}",
                "raw_content": par_raw_content,
                "parent_ids": [current_sec_id],
                "attributes": {
                    "priority": "HIGH",
                    "status": "PROPOSED",
                    "sequence_index": par_seq,
                    "separator_before": "\n\n"
                },
                "metadata": {
                    "author": "MOMMultilingualAgent",
                    "created_at": datetime.datetime.now().isoformat(),
                    "version": CURRENT_SCHEMA_VERSION,
                    "declared_in_project": work_project_id,
                    "multilingual_triplet": {
                        "source_language": source_lang,
                        "text_original": par_raw_content
                    }
                }
            }
            with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_PAR.json", "w", encoding="utf-8") as f:
                json.dump(par_data, f, indent=2, ensure_ascii=False)
            generated_proposals += 1
            proposal_counter += 1

            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z1-9\*\-\"\(])', node["content"]) if len(s.strip()) > 5]
            if not sentences:
                sentences = [node["content"]]

            paragraph_axiom_count[par_id] = 0
            for s_text in sentences:
                axi_id = f"DDD-{work_project_id}-AXI-{axiom_counter:03d}"
                axiom_counter += 1

                paragraph_axiom_count[par_id] += 1
                axi_seq = paragraph_axiom_count[par_id]

                axi_data = {
                    "id": axi_id,
                    "phase": "ddd",
                    "title": f"Axioma Atómico #{axiom_counter-1}",
                    "description": f"Frase atómica #{axiom_counter-1}",
                    "raw_content": s_text,
                    "parent_ids": [par_id],
                    "attributes": {
                        "priority": "HIGH",
                        "status": "PROPOSED",
                        "sequence_index": axi_seq,
                        "separator_before": " "
                    },
                    "metadata": {
                        "author": "MOMMultilingualAgent",
                        "created_at": datetime.datetime.now().isoformat(),
                        "version": CURRENT_SCHEMA_VERSION,
                        "declared_in_project": work_project_id,
                        "multilingual_triplet": {
                            "source_language": source_lang,
                            "text_original": s_text
                        }
                    }
                }
                with open(self.proposals_dir / f"prop_{work_project_id}_{proposal_counter:04d}_AXI.json", "w", encoding="utf-8") as f:
                    json.dump(axi_data, f, indent=2, ensure_ascii=False)
                generated_proposals += 1
                proposal_counter += 1

        self.generate_html_graph_viewer(work_project_id, target_split_dir=split_bib_dir)

        print("\n=======================================================")
        print(" 🤖 RESULTADO DE CAPTURA ATÓMICA Y GRAFO ESA")
        print("=======================================================")
        print(f"  • Proyecto Obra Despiece:    {work_project_id}")
        print(f"  • SHA-256 Fuente Original:   {sha256_orig}")
        print(f"  • Propuestas Creadas:        {generated_proposals} en 'data/ai-proposals/'")
        print(f"  • Visor HTML Creado:         {split_bib_dir / 'graph_proposal_viewer.html'}")
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
    parser.add_argument("--original", required=True, help="Ruta al archivo original")
    parser.add_argument("--author", required=True, help="ID de Autor Principal")
    parser.add_argument("--work", required=True, help="ID corto de la obra")
    parser.add_argument("--title", required=True, help="Título completo")
    parser.add_argument("--publisher", default="ESA", help="Editorial")
    parser.add_argument("--year", type=int, default=1991, help="Año")
    parser.add_argument("--license", default="Public Domain", help="Licencia")
    parser.add_argument("--public", action="store_true", help="Exportación pública")
    parser.add_argument("--lang", default="en", help="Idioma origen")

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

# App Version: 0.8.1
# Script Version: 0.8.1.0
# Compatible Schema: 0.5.3