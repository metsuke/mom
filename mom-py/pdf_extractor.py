import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple


# Fuente bitmap vectorial nativa de 5x7 píxeles (Pure Python Standard Library Fallback)
FONT_5X7 = {
    'A': [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'B': [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    'C': [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    'D': [0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C],
    'E': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    'F': [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    'G': [0x0E, 0x11, 0x10, 0x13, 0x11, 0x11, 0x0F],
    'H': [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'J': [0x1F, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    'K': [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    'L': [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    'M': [0x11, 0x1B, 0x15, 0x11, 0x11, 0x11, 0x11],
    'N': [0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11],
    'O': [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'P': [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    'Q': [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    'R': [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    'S': [0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E],
    'T': [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    'U': [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    'V': [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    'W': [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    'X': [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    'Y': [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    'Z': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    '0': [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    '1': [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    '2': [0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F],
    '3': [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    '4': [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    '5': [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    '6': [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    '7': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    '8': [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    '9': [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C],
    ',': [0x00, 0x00, 0x00, 0x00, 0x0C, 0x04, 0x08],
    '-': [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    ':': [0x00, 0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x00],
    '(': [0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02],
    ')': [0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08],
    '/': [0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
}


class PurePythonPNGWriter:
    """
    Encoder PNG Soberano en Python puro (cero dependencias).
    Soporta formato Grayscale (Tipo 0) a 8 bits.
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

        ihdr_data = struct.pack(
            ">IIBBBBB",
            width,
            height,
            bit_depth,
            color_type,
            0,
            0,
            0,
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
    Extractor y Renderizador PDF Multi-SO con Descubrimiento Activo e Instrucciones
    de Instalación POSIX Interactivas.
    """

    def __init__(self, filepath: str):
        self.filepath = Path(filepath).resolve()
        with open(self.filepath, "rb") as f:
            self.data = f.read()
        self.objects: Dict[int, bytes] = {}
        self.page_obj_ids: List[int] = []
        self._parse_objects()
        self._resolve_page_tree()
        self.system_renderer = self._ensure_posix_renderer()

    def _ensure_posix_renderer(self) -> Optional[str]:
        """Detecta o sugiere el comando de instalación nativo para el usuario."""
        if shutil.which("pdftoppm"):
            print("⚡ [MetsuOS POSIX] Detectado 'pdftoppm' en el PATH del sistema.")
            return "pdftoppm"

        if shutil.which("gs") or shutil.which("gswin64c"):
            print("⚡ [MetsuOS POSIX] Detectado 'Ghostscript' en el sistema.")
            return "ghostscript"

        # Identificar comando según gestor de paquetes del SO host
        cmd_suggestion = None
        if shutil.which("brew"):
            cmd_suggestion = "brew install poppler"
        elif shutil.which("apt-get"):
            cmd_suggestion = "sudo apt-get install -y poppler-utils"
        elif shutil.which("dnf"):
            cmd_suggestion = "sudo dnf install -y poppler-utils"
        elif shutil.which("pacman"):
            cmd_suggestion = "sudo pacman -S --noconfirm poppler"
        elif shutil.which("apk"):
            cmd_suggestion = "apk add poppler-utils"

        if cmd_suggestion:
            print("\n" + "=" * 72)
            print("⚠️ [MetsuOS POSIX Dependency Check] No se encontró 'pdftoppm'.")
            print("Para renderizado de alta velocidad/fidelidad, ejecuta en tu terminal:")
            print(f"\n    👉  \033[1;32m{cmd_suggestion}\033[0m\n")
            print("Una vez completado, vuelve a lanzar esta opción.")
            print("=" * 72 + "\n")
            input("🔻 Presiona [Enter] para continuar con el renderizado Pure-Python o cancelar...")

        print("ℹ️ [MetsuOS Fallback] Ejecutando renderizador nativo Soberano en Pure-Python...")
        return None

    def _parse_objects(self):
        """Parseador universal de objetos indirectos PDF XREF / obj."""
        pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\b")
        matches = list(pattern.finditer(self.data))
        for i, match in enumerate(matches):
            obj_id = int(match.group(1))
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(self.data)
            self.objects[obj_id] = self.data[start_pos:end_pos]

    def _resolve_page_tree(self):
        """Resuelve la estructura completa del árbol de páginas (/Pages -> /Kids /Page)."""
        self.page_obj_ids = []
        root_pages_id = None
        for obj_id, content in self.objects.items():
            if re.search(rb"/Type\s*/Pages\b", content) and not re.search(rb"/Parent\b", content):
                root_pages_id = obj_id
                break

        def traverse_node(node_id: int):
            content = self.objects.get(node_id, b"")
            if re.search(rb"/Type\s*/Page\b", content) and not re.search(rb"/Type\s*/Pages\b", content):
                if node_id not in self.page_obj_ids:
                    self.page_obj_ids.append(node_id)
            elif re.search(rb"/Type\s*/Pages\b", content) or b"/Kids" in content:
                kids_match = re.search(rb"/Kids\s*\[(.*?)\]", content, re.DOTALL)
                if kids_match:
                    child_ids = re.findall(rb"(\d+)\s+\d+\s+R", kids_match.group(1))
                    for c_id in child_ids:
                        traverse_node(int(c_id))

        if root_pages_id:
            traverse_node(root_pages_id)

        if not self.page_obj_ids:
            for obj_id, content in self.objects.items():
                if re.search(rb"/Type\s*/Page\b", content) and not re.search(rb"/Type\s*/Pages\b", content):
                    self.page_obj_ids.append(obj_id)
            self.page_obj_ids.sort()

    def get_pages_count(self) -> int:
        """Calcula el número exacto de páginas resueltas."""
        if self.page_obj_ids:
            return len(self.page_obj_ids)
        counts = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", self.data)
        if counts:
            return max(int(c.decode('ascii')) for c in counts)
        return 0

    def export_all_pages_to_dir(self, output_dir: Path) -> List[Path]:
        """
        Exporta todas las páginas del PDF a PNG en la carpeta de destino.
        Soporta aceleración POSIX nativa y fallback Soberano en Pure-Python.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        generated_files = []

        # 1. Ruta POSIX Native Executable (pdftoppm)
        if self.system_renderer == "pdftoppm":
            prefix = output_dir / f"{self.filepath.stem}_page"
            cmd = ["pdftoppm", "-png", "-r", "150", str(self.filepath), str(prefix)]
            print(f"🚀 Renderizando páginas vía comando POSIX: {' '.join(cmd)}")
            try:
                subprocess.run(cmd, check=True)
                generated_files = sorted(list(output_dir.glob("*.png")))
                if generated_files:
                    return generated_files
            except Exception as e:
                print(f"⚠️ Error al ejecutar pdftoppm ({e}). Cambiando a Fallback Pure-Python...")

        # 2. Ruta POSIX Ghostscript
        elif self.system_renderer == "ghostscript":
            gs_bin = shutil.which("gs") or shutil.which("gswin64c") or "gswin32c"
            out_pattern = str(output_dir / f"{self.filepath.stem}_page_%04d.png")
            cmd = [
                gs_bin,
                "-sDEVICE=png16m",
                "-r150",
                "-dNOPAUSE",
                "-dBATCH",
                "-dSAFER",
                f"-sOutputFile={out_pattern}",
                str(self.filepath)
            ]
            print(f"🚀 Renderizando páginas vía Ghostscript POSIX: {' '.join(cmd)}")
            try:
                subprocess.run(cmd, check=True)
                generated_files = sorted(list(output_dir.glob("*.png")))
                if generated_files:
                    return generated_files
            except Exception as e:
                print(f"⚠️ Error al ejecutar Ghostscript ({e}). Cambiando a Fallback Pure-Python...")

        # 3. Fallback Nativo Soberano Pure-Python
        page_count = self.get_pages_count()
        print(f"⚙️ Procesando {page_count} páginas con el motor de renderizado Pure-Python...")
        for idx in range(page_count):
            img_bytes = self.render_page_to_bytes(idx)
            out_file = output_dir / f"{self.filepath.stem}_page_{idx+1:04d}.png"
            png_bytes = PurePythonPNGWriter.encode_png(600, 800, img_bytes, is_grayscale=True)
            with open(out_file, "wb") as f:
                f.write(png_bytes)
            generated_files.append(out_file)

        return generated_files

    def extract_stream_content(self, obj_data: bytes) -> bytes:
        """Extrae y descomprime flujos de contenido FlateDecode."""
        stream_start = obj_data.find(b"stream")
        if stream_start == -1:
            return b""

        data_start = stream_start + (8 if obj_data[stream_start + 6 : stream_start + 8] == b"\r\n" else 7)
        stream_end = obj_data.find(b"endstream", data_start)
        raw_stream = obj_data[data_start:stream_end].rstrip(b"\r\n") if stream_end != -1 else obj_data[data_start:]

        if b"/FlateDecode" in obj_data or b"/Fl" in obj_data:
            try:
                return zlib.decompress(raw_stream)
            except Exception:
                try:
                    return zlib.decompress(raw_stream, -zlib.MAX_WBITS)
                except Exception:
                    return raw_stream
        return raw_stream

    def _get_page_stream_content(self, page_obj_id: int) -> bytes:
        """Obtiene recursivamente todos los flujos de comandos vectoriales de una página."""
        page_data = self.objects.get(page_obj_id, b"")
        combined_stream = bytearray()

        contents_match = re.search(rb"/Contents\s+\[(.*?)\]", page_data, re.DOTALL)
        if contents_match:
            ref_ids = re.findall(rb"(\d+)\s+\d+\s+R", contents_match.group(1))
            for r_id in ref_ids:
                c_data = self.objects.get(int(r_id), b"")
                combined_stream.extend(self.extract_stream_content(c_data))
        else:
            single_match = re.search(rb"/Contents\s+(\d+)\s+\d+\s+R", page_data)
            if single_match:
                c_data = self.objects.get(int(single_match.group(1)), b"")
                combined_stream.extend(self.extract_stream_content(c_data))

        if not combined_stream:
            combined_stream.extend(self.extract_stream_content(page_data))

        return bytes(combined_stream)

    def _draw_char(self, buffer: bytearray, width: int, height: int, char: str, x: int, y: int):
        """Estampa un carácter mediante la fuente vectorial nativa de 5x7 píxeles."""
        glyph = FONT_5X7.get(char.upper(), FONT_5X7.get(' '))
        if not glyph:
            return

        for row_idx, row_val in enumerate(glyph):
            py = y + row_idx
            if 0 <= py < height:
                for col_idx in range(5):
                    px = x + col_idx
                    if 0 <= px < width:
                        if (row_val >> (4 - col_idx)) & 1:
                            buffer[py * width + px] = 0

    def render_page_to_bytes(
        self, page_index: int, width: int = 600, height: int = 800
    ) -> bytes:
        """Fallback de renderizado Pure-Python si no hay binario del SO disponible."""
        buffer = bytearray(b"\xFF" * (width * height))

        for x in range(width):
            buffer[x] = 0
            buffer[(height - 1) * width + x] = 0
        for y in range(height):
            buffer[y * width] = 0
            buffer[y * width + (width - 1)] = 0

        if page_index >= len(self.page_obj_ids):
            return bytes(buffer)

        page_obj_id = self.page_obj_ids[page_index]
        stream_bytes = self._get_page_stream_content(page_obj_id)
        
        if stream_bytes:
            stream_str = stream_bytes.decode("latin1", errors="ignore")
            scale_x = width / 595.0
            scale_y = height / 842.0

            cursor_x = 40.0
            cursor_y = 50.0
            line_start_x = 40.0

            tokens = re.findall(r'(\(.*?\)|<.*?>|\[.*?\]|[-+]?\d*\.\d+|[-+]?\d+|[a-zA-Z*\'"]+)', stream_str, re.DOTALL)
            stack = []

            for token in tokens:
                if token.startswith('(') and token.endswith(')'):
                    stack.append(('STR', token[1:-1]))
                elif token.startswith('<') and token.endswith('>'):
                    hex_str = token[1:-1]
                    try:
                        decoded_hex = bytes.fromhex(hex_str).decode('latin1', errors='ignore')
                        stack.append(('STR', decoded_hex))
                    except Exception:
                        stack.append(('STR', hex_str))
                elif token.startswith('[') and token.endswith(']'):
                    inner_strings = re.findall(r'\((.*?)\)|<([^>]+)>', token)
                    combined = []
                    for s_paren, s_hex in inner_strings:
                        if s_paren:
                            combined.append(s_paren)
                        elif s_hex:
                            try:
                                combined.append(bytes.fromhex(s_hex).decode('latin1', errors='ignore'))
                            except Exception:
                                combined.append(s_hex)
                    stack.append(('STR', "".join(combined)))
                elif re.match(r'^[-+]?\d*\.?\d+$', token):
                    stack.append(('NUM', float(token)))
                else:
                    op = token
                    if op in ('Td', 'TD'):
                        if len(stack) >= 2 and stack[-1][0] == 'NUM' and stack[-2][0] == 'NUM':
                            dy = stack.pop()[1]
                            dx = stack.pop()[1]
                            cursor_x += dx * scale_x
                            cursor_y -= dy * scale_y
                            line_start_x = cursor_x
                        stack.clear()
                    elif op == 'Tm':
                        if len(stack) >= 6:
                            nums = [stack.pop()[1] for _ in range(6)][::-1]
                            cursor_x = nums[4] * scale_x
                            cursor_y = (842.0 - nums[5]) * scale_y
                            line_start_x = cursor_x
                        stack.clear()
                    elif op in ('Tj', 'TJ', "'", '"'):
                        text_to_draw = ""
                        if stack and stack[-1][0] == 'STR':
                            text_to_draw = stack.pop()[1]
                        elif len(stack) >= 2 and stack[-1][0] == 'STR':
                            text_to_draw = stack[-1][1]

                        if text_to_draw:
                            clean_text = text_to_draw.replace(r'\(', '(').replace(r'\)', ')').replace(r'\\', '\\')
                            start_px = int(cursor_x)
                            start_py = int(cursor_y)

                            for char_idx, ch in enumerate(clean_text):
                                px = start_px + (char_idx * 6)
                                py = start_py
                                if 10 <= px < width - 10 and 10 <= py < height - 10:
                                    self._draw_char(buffer, width, height, ch, px, py)

                            cursor_x += len(clean_text) * 6
                        stack.clear()
                    elif op == 'T*':
                        cursor_y += 12 * scale_y
                        cursor_x = line_start_x
                        stack.clear()

        return bytes(buffer)


# Version: 0.5.2
# File_Version: 0.5.2.17
# Schema_Version: 0.5.2