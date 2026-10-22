import os
import re
import struct
import zlib
from pathlib import Path
from typing import List, Dict, Optional, Any


class PurePythonPNGWriter:
    """
    Encoder PNG Soberano en Python puro (cero dependencias).
    Soporta formato Grayscale (Tipo 0) y RGB (Tipo 2) a 8 bits.
    """

    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    @staticmethod
    def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        crc_bytes = struct.pack(">I", crc)
        return length + chunk_type + data + crc_bytes

    @classmethod
    def encode_png(
        cls, width: int, height: int, pixel_data: bytes, is_grayscale: bool = True
    ) -> bytes:
        color_type = 0 if is_grayscale else 2
        bit_depth = 8
        compression = 0
        filter_method = 0
        interlace = 0

        ihdr_data = struct.pack(
            ">IIBBBBB",
            width,
            height,
            bit_depth,
            color_type,
            compression,
            filter_method,
            interlace,
        )
        ihdr_chunk = cls._make_chunk(b"IHDR", ihdr_data)

        bytes_per_pixel = 1 if is_grayscale else 3
        stride = width * bytes_per_pixel

        scanlines = bytearray()
        for y in range(height):
            scanlines.append(0)  # Filtro 0: None
            row_start = y * stride
            scanlines.extend(pixel_data[row_start : row_start + stride])

        compressed_idat = zlib.compress(bytes(scanlines))
        idat_chunk = cls._make_chunk(b"IDAT", compressed_idat)
        iend_chunk = cls._make_chunk(b"IEND", b"")

        return cls.PNG_SIGNATURE + ihdr_chunk + idat_chunk + iend_chunk


class PurePythonPDFExtractor:
    """
    Parser y Renderizador PDF Soberano en Python Puro (0 dependencias externas).
    Procesa objetos PDF, catálogos /Pages, streams de contenido FlateDecode
    y construye el buffer de píxeles renderizado página por página.
    """

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        with open(self.filepath, "rb") as f:
            self.data = f.read()
        self.objects: Dict[int, bytes] = {}
        self.page_obj_ids: List[int] = []
        self._parse_objects()
        self._build_page_tree()

    def _parse_objects(self):
        """Parseador de objetos indirectos PDF XREF / obj."""
        pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
        matches = list(pattern.finditer(self.data))
        for i, match in enumerate(matches):
            obj_id = int(match.group(1))
            start_pos = match.end()
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(self.data)
            obj_content = self.data[start_pos:end_pos]
            self.objects[obj_id] = obj_content

    def _build_page_tree(self):
        """Construye el catálogo de páginas reales procesando declaraciones de /Type /Page."""
        self.page_obj_ids = []
        for obj_id, content in self.objects.items():
            # Identificar objetos individuales de tipo Página
            if re.search(rb"/Type\s*/Page\b", content) and not re.search(rb"/Type\s*/Pages\b", content):
                self.page_obj_ids.append(obj_id)

        self.page_obj_ids.sort()

    def get_pages_count(self) -> int:
        """Calcula el número real exacto de páginas."""
        if self.page_obj_ids:
            return len(self.page_obj_ids)

        # Fallback: Parsear conteo declarado en catálogo raíz de /Pages
        counts = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", self.data)
        if counts:
            return max(int(c.decode('ascii')) for c in counts)
        return 0

    def extract_stream_content(self, obj_data: bytes) -> bytes:
        """Extrae y descomprime flujos de contenido FlateDecode."""
        stream_start = obj_data.find(b"stream")
        if stream_start == -1:
            return b""

        if obj_data[stream_start + 6 : stream_start + 8] == b"\r\n":
            data_start = stream_start + 8
        else:
            data_start = stream_start + 7

        stream_end = obj_data.find(b"endstream", data_start)
        if stream_end == -1:
            raw_stream = obj_data[data_start:]
        else:
            raw_stream = obj_data[data_start:stream_end].rstrip(b"\r\n")

        if b"/FlateDecode" in obj_data or b"/Fl" in obj_data:
            try:
                return zlib.decompress(raw_stream)
            except Exception:
                try:
                    return zlib.decompress(raw_stream, -zlib.MAX_WBITS)
                except Exception:
                    return raw_stream
        return raw_stream

    def render_page_to_bytes(
        self, page_index: int, width: int = 600, height: int = 800
    ) -> bytes:
        """
        Renderiza la estructura visual de la página especificada a una matriz de píxeles (Grayscale 0-255).
        """
        buffer = bytearray(b"\xFF" * (width * height))

        # Dibujar bordes del lienzo
        for x in range(width):
            buffer[x] = 0
            buffer[(height - 1) * width + x] = 0
        for y in range(height):
            buffer[y * width] = 0
            buffer[y * width + (width - 1)] = 0

        if page_index < len(self.page_obj_ids):
            obj_id = self.page_obj_ids[page_index]
            page_data = self.objects.get(obj_id, b"")
            
            # Recuperar flujos de contenido de la página
            contents_ids = re.findall(rb"/Contents\s+(\d+)\s+\d+\s+R", page_data)
            stream_content = bytearray()
            for c_id in contents_ids:
                c_data = self.objects.get(int(c_id), b"")
                stream_content.extend(self.extract_stream_content(c_data))

            if not stream_content:
                stream_content.extend(self.extract_stream_content(page_data))

            decoded = stream_content.decode("latin1", errors="ignore")
            text_blocks = re.findall(r"\((.*?)\)\s*Tj", decoded)

            # Dibujar marcas de texto binarizadas sobre el mapa de bits
            y_cursor = 40
            line_spacing = max(10, height // (len(text_blocks) + 5 if text_blocks else 40))
            for block in text_blocks:
                if y_cursor >= height - 20:
                    break
                line_len = min(len(block) * 5, width - 40)
                for x in range(20, 20 + line_len):
                    if x < width:
                        buffer[y_cursor * width + x] = 0
                y_cursor += line_spacing

        return bytes(buffer)


# App Version: 0.5.2
# Script Version: 0.5.2.7
# Compatible Schema: 0.5.2