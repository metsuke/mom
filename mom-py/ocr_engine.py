import math
import os
import re
import sys
import hashlib
import subprocess
import tkinter as tk
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional, Callable

from schemas import CURRENT_SCHEMA_VERSION

class MOMOCREngine:
    """
    Motor de Reconocimiento Óptico de Caracteres (OCR) Pure-Python sin dependencias externas.
    Procesa imágenes PGM/PPM utilizando la librería estándar (tkinter.PhotoImage)
    para binarizar, segmentar glifos por inundación y clasificar glifos mediante vectores de características.
    Soporta callbacks de progreso para retroalimentación en tiempo real en la terminal.
    """

    def __init__(self, templates: Optional[Dict[str, List[float]]] = None) -> None:
        # Base de datos de plantillas [Relación de aspecto, Q1, Q2, Q3, Q4]
        self.templates = templates or {
            'A': [0.85, 0.20, 0.20, 0.30, 0.30],
            'B': [0.75, 0.30, 0.25, 0.25, 0.20],
            'C': [0.80, 0.30, 0.20, 0.25, 0.25],
            'D': [0.85, 0.30, 0.25, 0.25, 0.20],
            'E': [0.70, 0.30, 0.20, 0.30, 0.20],
            'F': [0.65, 0.35, 0.20, 0.25, 0.20],
            'G': [0.85, 0.25, 0.20, 0.30, 0.25],
            'H': [0.80, 0.25, 0.25, 0.25, 0.25],
            'I': [0.25, 0.25, 0.25, 0.25, 0.25],
            'J': [0.40, 0.15, 0.25, 0.30, 0.30],
            'K': [0.75, 0.30, 0.20, 0.25, 0.25],
            'L': [0.60, 0.30, 0.10, 0.40, 0.20],
            'M': [0.95, 0.35, 0.35, 0.15, 0.15],
            'N': [0.85, 0.30, 0.20, 0.20, 0.30],
            'O': [0.90, 0.25, 0.25, 0.25, 0.25],
            'P': [0.70, 0.35, 0.25, 0.25, 0.15],
            'Q': [0.95, 0.25, 0.25, 0.25, 0.25],
            'R': [0.80, 0.30, 0.25, 0.25, 0.20],
            'S': [0.75, 0.25, 0.20, 0.20, 0.35],
            'T': [0.75, 0.40, 0.40, 0.10, 0.10],
            'U': [0.80, 0.25, 0.25, 0.25, 0.25],
            'V': [0.85, 0.25, 0.25, 0.25, 0.25],
            'W': [1.10, 0.20, 0.20, 0.30, 0.30],
            'X': [0.80, 0.25, 0.25, 0.25, 0.25],
            'Y': [0.80, 0.30, 0.30, 0.20, 0.20],
            'Z': [0.75, 0.30, 0.20, 0.20, 0.30],
            '0': [0.85, 0.25, 0.25, 0.25, 0.25],
            '1': [0.30, 0.30, 0.20, 0.25, 0.25],
            '2': [0.75, 0.25, 0.25, 0.30, 0.20],
            '3': [0.75, 0.25, 0.25, 0.20, 0.30],
            '4': [0.80, 0.30, 0.20, 0.35, 0.15],
            '5': [0.75, 0.35, 0.15, 0.20, 0.30],
            '6': [0.80, 0.25, 0.15, 0.30, 0.30],
            '7': [0.75, 0.35, 0.35, 0.15, 0.15],
            '8': [0.80, 0.25, 0.25, 0.25, 0.25],
            '9': [0.80, 0.30, 0.30, 0.15, 0.25],
            '.': [0.20, 0.00, 0.00, 0.50, 0.50],
            ',': [0.20, 0.00, 0.00, 0.40, 0.60],
            '-': [0.60, 0.00, 0.00, 0.50, 0.50]
        }

    @staticmethod
    def deduplicate_raw_directory(raw_dir: Path) -> Path:
        """
        Escanea la carpeta 'raw', calcula el hash SHA-256 de todos los archivos,
        elimina duplicados automáticamente y devuelve la ruta del archivo único conservado.
        """
        raw_files = [f for f in raw_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        if not raw_files:
            raise FileNotFoundError(f"No se encontraron archivos en el directorio RAW: {raw_dir}")

        seen_hashes = {}
        kept_file = None

        for file_path in sorted(raw_files, key=lambda x: x.stat().st_mtime):
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            file_hash = sha256.hexdigest()

            if file_hash in seen_hashes:
                os.remove(file_path)
            else:
                seen_hashes[file_hash] = file_path
                if kept_file is None:
                    kept_file = file_path

        return kept_file

    def convert_pdf_page_to_pgm(self, pdf_path: Path, page_num: int, output_dir: Path) -> Path:
        """Convierte una página del PDF a formato PGM mediante pdftoppm."""
        output_prefix = output_dir / f"page_{page_num}"
        cmd = [
            "pdftoppm",
            "-pgm",
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
            str(output_prefix)
        ]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(f"Error al ejecutar pdftoppm para conversión a PGM: {e}")

        pgm_file = output_dir / f"page_{page_num}-1.pgm"
        if not pgm_file.exists():
            candidates = list(output_dir.glob(f"page_{page_num}*.pgm"))
            if candidates:
                return candidates[0]
            raise FileNotFoundError(f"No se pudo generar la imagen PGM para la página {page_num}")

        return pgm_file

    def load_pgm_image(self, pgm_path: Path) -> Tuple[List[List[int]], int, int]:
        """Carga la imagen PGM utilizando la clase PhotoImage nativa de tkinter."""
        root = tk.Tk()
        root.withdraw()
        
        img = tk.PhotoImage(file=str(pgm_path))
        ancho = img.width()
        alto = img.height()

        matriz = []
        for y in range(alto):
            fila = []
            for x in range(ancho):
                r, g, b = img.get(x, y)
                luminancia = 0.299 * r + 0.587 * g + 0.114 * b
                fila.append(0 if luminancia < 128 else 1)  # Binarización: 0 = Negro (Texto)
            matriz.append(fila)

        root.destroy()
        return matriz, ancho, alto

    def segment_glyphs(self, matriz: List[List[int]], ancho: int, alto: int) -> List[Tuple[int, int, int, int, List[Tuple[int, int]]]]:
        """Aísla cada glifo mediante un algoritmo de inundación (Flood-Fill)."""
        visited = [[False] * ancho for _ in range(alto)]
        glyphs = []

        for y in range(alto):
            for x in range(ancho):
                if matriz[y][x] == 0 and not visited[y][x]:
                    min_x, max_x, min_y, max_y = x, x, y, y
                    stack = [(x, y)]
                    glyph_pixels = []
                    visited[y][x] = True

                    while stack:
                        cx, cy = stack.pop()
                        glyph_pixels.append((cx, cy))
                        min_x, max_x = min(min_x, cx), max(max_x, cx)
                        min_y, max_y = min(min_y, cy), max(max_y, cy)

                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < ancho and 0 <= ny < alto:
                                if matriz[ny][nx] == 0 and not visited[ny][nx]:
                                    visited[ny][nx] = True
                                    stack.append((nx, ny))

                    if (max_x - min_x >= 2) and (max_y - min_y >= 2):
                        glyphs.append((min_x, min_y, max_x, max_y, glyph_pixels))

        glyphs.sort(key=lambda g: (g[1] // 20, g[0]))
        return glyphs

    def extract_feature_vector(self, min_x: int, min_y: int, max_x: int, max_y: int, pixels: List[Tuple[int, int]]) -> List[float]:
        """Extrae el vector de características [Relación de aspecto, Densidad Q1, Q2, Q3, Q4]."""
        w = max_x - min_x + 1
        h = max_y - min_y + 1
        aspect_ratio = w / h

        quadrants = [0, 0, 0, 0]
        mid_x = min_x + w / 2
        mid_y = min_y + h / 2

        for px, py in pixels:
            if px < mid_x and py < mid_y:
                quadrants[0] += 1
            elif px >= mid_x and py < mid_y:
                quadrants[1] += 1
            elif px < mid_x and py >= mid_y:
                quadrants[2] += 1
            else:
                quadrants[3] += 1

        total_pixels = len(pixels)
        density_vector = [q / total_pixels for q in quadrants]
        return [aspect_ratio] + density_vector

    def classify_glyph(self, feature_vector: List[float]) -> str:
        """Clasifica el glifo buscando la menor distancia euclidiana en la matriz de plantillas."""
        best_char = "?"
        min_dist = float('inf')

        for char, ref_vector in self.templates.items():
            dist = math.sqrt(sum((v - r) ** 2 for v, r in zip(feature_vector, ref_vector)))
            if dist < min_dist:
                min_dist = dist
                best_char = char

        return best_char

    def process_pgm_page(self, pgm_path: Path, progress_callback: Optional[Callable[[int, int, str], None]] = None) -> str:
        """Procesa una imagen PGM notificando el avance glifo a glifo si existe callback."""
        matriz, ancho, alto = self.load_pgm_image(pgm_path)
        glyphs = self.segment_glyphs(matriz, ancho, alto)

        extracted_chars = []
        total_glyphs = len(glyphs)

        for i, g in enumerate(glyphs, 1):
            min_x, min_y, max_x, max_y, pixels = g
            feat = self.extract_feature_vector(min_x, min_y, max_x, max_y, pixels)
            char = self.classify_glyph(feat)
            extracted_chars.append(char)

            if progress_callback and (i % 10 == 0 or i == total_glyphs):
                curr_text = "".join(extracted_chars[-40:])  # Muestra los últimos 40 caracteres reconocidos
                progress_callback(i, total_glyphs, curr_text)

        return "".join(extracted_chars)

# Version: 0.5.4
# File_Version: 0.5.3.1
# Schema_Version: 0.5.3