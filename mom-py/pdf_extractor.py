import os
import re
import struct
import zlib


class PurePythonPNGWriter:
    """Encoder de PNG escrito completamente en Python puro."""

    PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

    @staticmethod
    def _make_chunk(chunk_type: bytes, data: bytes) -> bytes:
        """Construye un Chunk PNG: Length (4B) + Type (4B) + Data + CRC32 (4B)."""
        length = struct.pack(">I", len(data))
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        crc_bytes = struct.pack(">I", crc)
        return length + chunk_type + data + crc_bytes

    @classmethod
    def encode_png(
        cls, width: int, height: int, pixel_data: bytes, is_grayscale: bool
    ) -> bytes:
        """Genera los bytes binarios de una imagen PNG válida."""
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
            scanlines.append(0)  # Filter byte: None
            row_start = y * stride
            scanlines.extend(pixel_data[row_start : row_start + stride])

        compressed_idat = zlib.compress(scanlines)
        idat_chunk = cls._make_chunk(b"IDAT", compressed_idat)
        iend_chunk = cls._make_chunk(b"IEND", b"")

        return cls.PNG_SIGNATURE + ihdr_chunk + idat_chunk + iend_chunk


class PurePythonPDFExtractor:

    def __init__(self, filepath: str):
        with open(filepath, "rb") as f:
            self.data = f.read()
        self.objects = {}
        self._parse_objects()

    def _parse_objects(self):
        """Identifica los Objetos Indirectos dentro del PDF."""
        pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\r?\n")
        for match in pattern.finditer(self.data):
            obj_id = int(match.group(1))
            start_pos = match.end()
            end_pos = self.data.find(b"endobj", start_pos)
            if end_pos != -1:
                self.objects[obj_id] = self.data[start_pos:end_pos]

    def get_pages_count(self) -> int:
        """Obtiene el recuento exacto de páginas leyendo la raíz /Pages -> /Count."""
        for content in self.objects.values():
            if b"/Type" in content and b"/Pages" in content and b"/Count" in content:
                match = re.search(rb"/Count\s+(\d+)", content)
                if match:
                    return int(match.group(1))
        return 0

    def extract_stream_content(self, obj_data: bytes) -> bytes:
        """Extrae y descomprime flujos FlateDecode (zlib) de los streams de PDF."""
        stream_start = obj_data.find(b"stream")
        if stream_start == -1:
            return b""

        if obj_data[stream_start + 6 : stream_start + 8] == b"\r\n":
            data_start = stream_start + 8
        else:
            data_start = stream_start + 7

        stream_end = obj_data.find(b"endstream", data_start)
        if stream_end == -1:
            return b""

        raw_stream = obj_data[data_start:stream_end].rstrip(b"\r\n")

        if b"/FlateDecode" in obj_data:
            try:
                return zlib.decompress(raw_stream)
            except Exception:
                try:
                    return zlib.decompress(raw_stream, -zlib.MAX_WBITS)
                except Exception:
                    return raw_stream
        return raw_stream

    def extract_image_xobject(self, obj_id: int):
        """Parsea la imagen y retorna sus dimensiones y bytes de píxeles."""
        obj_data = self.objects.get(obj_id, b"")
        if b"/Subtype" not in obj_data or b"/Image" not in obj_data:
            return None

        w_match = re.search(rb"/Width\s+(\d+)", obj_data)
        h_match = re.search(rb"/Height\s+(\d+)", obj_data)
        if not w_match or not h_match:
            return None

        width = int(w_match.group(1))
        height = int(h_match.group(1))
        image_bytes = self.extract_stream_content(obj_data)

        invert = False
        if b"/Decode" in obj_data and b"[1 0]" in obj_data:
            invert = True

        is_grayscale = b"/DeviceGray" in obj_data

        if invert and is_grayscale:
            image_bytes = bytes([255 - b for b in image_bytes])

        return {
            "width": width,
            "height": height,
            "bytes": image_bytes,
            "is_grayscale": is_grayscale,
        }


# App Version: 0.5.2
# Script Version: 0.5.2.1
# Compatible Schema: 0.5.2