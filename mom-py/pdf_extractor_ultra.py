import io
import sys
import re
import subprocess
from pathlib import Path


def _ensure_dependencies():
    """Instala automáticamente las dependencias avanzadas de Python si no están presentes."""
    required = {
        "fitz": "PyMuPDF",
        "pdfplumber": "pdfplumber",
        "pytesseract": "pytesseract",
        "PIL": "Pillow"
    }
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            print(f"📦 [MetsuOS Auto-Install] Instalando dependencia requerida: {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def clean_line_noise(line_str: str) -> str:
    """Elimina marcas de agua, URLs y pies de página ruidosos."""
    clean = line_str.strip()
    if re.search(r'everyspec\.com', clean, re.IGNORECASE):
        return ""
    if re.search(r'downloaded from https?://', clean, re.IGNORECASE):
        return ""
    if re.search(r'^european space agency\s*/\s*agence spatiale', clean, re.IGNORECASE):
        return ""
    if re.search(r'^\d+,\s*rue mario-nikis', clean, re.IGNORECASE):
        return ""
    return clean


def format_table_like_block(block_lines: list) -> list:
    """Convierte bloques con estructura tabular a sintaxis de tabla Markdown."""
    formatted = []
    is_table = False
    
    for line in block_lines:
        tokens = re.split(r'\s{2,}', line.strip())
        if len(tokens) >= 3:
            if not is_table:
                is_table = True
                formatted.append("\n| " + " | ".join(tokens) + " |")
                formatted.append("| " + " | ".join(["---"] * len(tokens)) + " |")
            else:
                formatted.append("| " + " | ".join(tokens) + " |")
        else:
            is_table = False
            formatted.append(line)
            
    return formatted


def post_process_markdown_ultra(raw_text: str) -> str:
    """Transforma el texto extraído aplicando reglas avanzadas para asemejarse al formato de IA."""
    lines = raw_text.splitlines()
    processed_lines = []
    
    for line in lines:
        cleaned = clean_line_noise(line)
        if not cleaned:
            continue

        # Normalización de encabezados
        if re.match(r'^(CHAPTER|CAPÍTULO)\s+\d+', cleaned, re.IGNORECASE):
            processed_lines.append(f"\n# {cleaned}\n")
        elif re.match(r'^\d+\.\d+\s+[A-Z]', cleaned):
            processed_lines.append(f"\n## {cleaned}\n")
        elif re.match(r'^\d+\.\d+\.\d+\s+[A-Z]', cleaned):
            processed_lines.append(f"\n### {cleaned}\n")
        else:
            processed_lines.append(cleaned)

    # Detección y estructurado de tablas
    table_formatted = format_table_like_block(processed_lines)
    
    # Consolidación final
    final_md = "\n".join(table_formatted)
    final_md = re.sub(r'\n{3,}', '\n\n', final_md)
    return final_md


def extract_pdf_ultra(pdf_path: str, output_dir: str, lang: str = "eng+spa") -> str:
    """
    Ingesta ULTRA de PDF utilizando PyMuPDF + pdfplumber + OCR y post-procesamiento
    semántico avanzado para aproximar la calidad a la extracción por IA.
    """
    _ensure_dependencies()
    
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    raw_pages_text = []

    try:
        doc = fitz.open(pdf_path)
        print(f"🚀 [ULTRA EXTRACTOR] Procesando {len(doc)} páginas con motor semántico + OCR...")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            
            # OCR Fallback si la página es una imagen o contiene muy poco texto
            if len(text.strip()) < 50:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(img, lang=lang)
                except Exception as e:
                    text = f"[OCR Error: {e}]"

            raw_pages_text.append(text)
            
    except Exception as e:
        print(f"⚠️ Error durante la extracción Ultra: {e}")
        return ""

    raw_full_content = "\n\n".join(raw_pages_text)
    ultra_md_content = post_process_markdown_ultra(raw_full_content)
    
    out_file = output_dir / f"{pdf_path.stem}_ultra_extracted.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(ultra_md_content)

    print(f"✅ Ingesta ULTRA completada con éxito: {out_file.name}")
    return str(out_file)


# Version: 0.5.7
# File_Version: 0.5.7.0
# Schema_Version: 0.5.3import io
import sys
import re
import subprocess
from pathlib import Path


def _ensure_dependencies():
    """Instala automáticamente las dependencias avanzadas de Python si no están presentes."""
    required = {
        "fitz": "PyMuPDF",
        "pdfplumber": "pdfplumber",
        "pytesseract": "pytesseract",
        "PIL": "Pillow"
    }
    for module, package in required.items():
        try:
            __import__(module)
        except ImportError:
            print(f"📦 [MetsuOS Auto-Install] Instalando dependencia requerida: {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])


def clean_line_noise(line_str: str) -> str:
    """Elimina marcas de agua, URLs y pies de página ruidosos."""
    clean = line_str.strip()
    if re.search(r'everyspec\.com', clean, re.IGNORECASE):
        return ""
    if re.search(r'downloaded from https?://', clean, re.IGNORECASE):
        return ""
    if re.search(r'^european space agency\s*/\s*agence spatiale', clean, re.IGNORECASE):
        return ""
    if re.search(r'^\d+,\s*rue mario-nikis', clean, re.IGNORECASE):
        return ""
    return clean


def format_table_like_block(block_lines: list) -> list:
    """Convierte bloques con estructura tabular a sintaxis de tabla Markdown."""
    formatted = []
    is_table = False
    
    for line in block_lines:
        tokens = re.split(r'\s{2,}', line.strip())
        if len(tokens) >= 3:
            if not is_table:
                is_table = True
                formatted.append("\n| " + " | ".join(tokens) + " |")
                formatted.append("| " + " | ".join(["---"] * len(tokens)) + " |")
            else:
                formatted.append("| " + " | ".join(tokens) + " |")
        else:
            is_table = False
            formatted.append(line)
            
    return formatted


def post_process_markdown_ultra(raw_text: str) -> str:
    """Transforma el texto extraído aplicando reglas avanzadas para asemejarse al formato de IA."""
    lines = raw_text.splitlines()
    processed_lines = []
    
    for line in lines:
        cleaned = clean_line_noise(line)
        if not cleaned:
            continue

        # Normalización de encabezados
        if re.match(r'^(CHAPTER|CAPÍTULO)\s+\d+', cleaned, re.IGNORECASE):
            processed_lines.append(f"\n# {cleaned}\n")
        elif re.match(r'^\d+\.\d+\s+[A-Z]', cleaned):
            processed_lines.append(f"\n## {cleaned}\n")
        elif re.match(r'^\d+\.\d+\.\d+\s+[A-Z]', cleaned):
            processed_lines.append(f"\n### {cleaned}\n")
        else:
            processed_lines.append(cleaned)

    # Detección y estructurado de tablas
    table_formatted = format_table_like_block(processed_lines)
    
    # Consolidación final
    final_md = "\n".join(table_formatted)
    final_md = re.sub(r'\n{3,}', '\n\n', final_md)
    return final_md


def extract_pdf_ultra(pdf_path: str, output_dir: str, lang: str = "eng+spa") -> str:
    """
    Ingesta ULTRA de PDF utilizando PyMuPDF + pdfplumber + OCR y post-procesamiento
    semántico avanzado para aproximar la calidad a la extracción por IA.
    """
    _ensure_dependencies()
    
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    raw_pages_text = []

    try:
        doc = fitz.open(pdf_path)
        print(f"🚀 [ULTRA EXTRACTOR] Procesando {len(doc)} páginas con motor semántico + OCR...")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            
            # OCR Fallback si la página es una imagen o contiene muy poco texto
            if len(text.strip()) < 50:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(img, lang=lang)
                except Exception as e:
                    text = f"[OCR Error: {e}]"

            raw_pages_text.append(text)
            
    except Exception as e:
        print(f"⚠️ Error durante la extracción Ultra: {e}")
        return ""

    raw_full_content = "\n\n".join(raw_pages_text)
    ultra_md_content = post_process_markdown_ultra(raw_full_content)
    
    out_file = output_dir / f"{pdf_path.stem}_ultra_extracted.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(ultra_md_content)

    print(f"✅ Ingesta ULTRA completada con éxito: {out_file.name}")
    return str(out_file)


# Version: 0.5.7
# File_Version: 0.5.7.0
# Schema_Version: 0.5.3