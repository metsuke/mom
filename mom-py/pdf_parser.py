import re
import zlib
from pathlib import Path
from typing import List, Tuple
from schemas import CURRENT_SCHEMA_VERSION

class MOMPurePDFExtractor:
    """
    Extractor de texto plano y estructura de páginas para archivos PDF.
    Implementación nativa Pure-Python (cero dependencias externas / cero pip install).
    Procesa estructuras PDF de objeto, tablas xref y streams comprimidos con FlateDecode/zlib.
    """

    def __init__(self, pdf_path: Path) -> None:
        self.pdf_path = Path(pdf_path)
        with open(self.pdf_path, "rb") as f:
            self.data = f.read()

    def _extract_streams(self) -> List[bytes]:
        """Localiza y descomprime todos los bloques stream /FlateDecode del PDF."""
        streams = []
        stream_pattern = re.compile(rb'stream[\r\n]+([\s\S]*?)[\r\n]+endstream')
        
        for match in stream_pattern.finditer(self.data):
            raw_stream = match.group(1)
            try:
                decompressed = zlib.decompress(raw_stream)
                streams.append(decompressed)
            except Exception:
                streams.append(raw_stream)
                
        return streams

    def _parse_pdf_text_operators(self, stream_bytes: bytes) -> str:
        """Extrae operandos de texto Tj, TJ y comillas sencillas dentro de los streams de comando PDF."""
        extracted_text = []
        try:
            text_content = stream_bytes.decode('latin-1', errors='ignore')
        except Exception:
            return ""

        # Operador Tj: (Texto) Tj
        tj_matches = re.findall(r'\((.*?)\)\s*Tj', text_content)
        for text in tj_matches:
            extracted_text.append(text)

        # Operador TJ: [(Texto1) -10 (Texto2)] TJ
        array_matches = re.findall(r'\[(.*?)\]\s*TJ', text_content, re.DOTALL)
        for arr in array_matches:
            items = re.findall(r'\((.*?)\)', arr)
            extracted_text.append("".join(items))

        return " ".join(extracted_text)

    def extract_text_by_pages(self) -> List[Tuple[int, str]]:
        """
        Extrae el texto delimitado por páginas.
        Devuelve una lista de tuplas: (número_página, texto_extraído).
        """
        streams = self._extract_streams()
        extracted_pages: List[Tuple[int, str]] = []
        current_page = 1

        for stream in streams:
            page_text = self._parse_pdf_text_operators(stream)
            clean_text = (
                page_text.replace(r'\(', '(')
                .replace(r'\)', ')')
                .replace(r'\\', '\\')
                .strip()
            )
            
            if clean_text and len(clean_text) > 10:
                extracted_pages.append((current_page, clean_text))
                current_page += 1

        if not extracted_pages:
            raw_latin = self.data.decode('latin-1', errors='ignore')
            clean_fallback = re.sub(r'[^\w\s\.\,\;\:\-\(\)\[\]\/]', ' ', raw_latin)
            clean_fallback = re.sub(r'\s+', ' ', clean_fallback)
            extracted_pages.append((1, clean_fallback))

        return extracted_pages

    def extract_full_text_with_page_markers(self) -> str:
        """Genera una cadena con marcas formales de página <!-- PAGE X --> para el parser del ingest_agent."""
        pages = self.extract_text_by_pages()
        full_doc = []
        for pnum, ptext in pages:
            full_doc.append(f"<!-- PAGE {pnum} -->\n{ptext}\n")
        return "\n".join(full_doc)

# Version: 0.5.3
# File_Version: 0.5.2.1
# Schema_Version: 0.5.3