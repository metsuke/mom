import io
import sys
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


def extract_pdf_advanced(pdf_path: str, output_dir: str, lang: str = "eng+spa") -> str:
    """
    Ingesta avanzada de PDF utilizando librerías de alto nivel y OCR.
    Extrae texto directo si existe y aplica OCR si detecta páginas escaneadas.
    """
    _ensure_dependencies()
    
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    pdf_path = Path(pdf_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    extracted_text = []

    try:
        doc = fitz.open(pdf_path)
        print(f"🚀 Procesando {len(doc)} páginas con PyMuPDF + OCR...")
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            
            # Si la página tiene poco texto (ej. PDF escaneado o imagen), aplicamos OCR
            if len(text.strip()) < 50:
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(img, lang=lang)
                except Exception as e:
                    text = f"[OCR No disponible o error: {e}]"

            extracted_text.append(f"<!-- Page {page_num + 1} -->\n{text}")
            
    except Exception as e:
        print(f"⚠️ Error durante la extracción avanzada: {e}")
        return ""

    full_md_content = "\n\n".join(extracted_text)
    out_file = output_dir / f"{pdf_path.stem}_advanced_extracted.md"
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(full_md_content)

    print(f"✅ Ingesta avanzada completada: {out_file}")
    return str(out_file)


# Version: 0.5.2
# File_Version: 0.5.2.1
# Schema_Version: 0.5.2