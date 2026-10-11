from __future__ import annotations

import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def encode_rgba_png(width: int, height: int, data: bytes | bytearray) -> bytes:
    width, height = int(width), int(height)
    expected = width * height * 4
    if width <= 0 or height <= 0 or len(data) != expected:
        raise ValueError(f"RGBA payload must contain exactly {expected} bytes")
    stride = width * 4
    scanlines = b"".join(b"\x00" + bytes(data[offset:offset + stride]) for offset in range(0, expected, stride))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(scanlines, 9)) + _chunk(b"IEND", b"")


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_upper_left = abs(estimate - upper_left)
    if distance_left <= distance_up and distance_left <= distance_upper_left:
        return left
    if distance_up <= distance_upper_left:
        return up
    return upper_left


def decode_rgba_png(payload: bytes | bytearray) -> tuple[int, int, bytes]:
    """Decode the small, non-interlaced 8-bit RGBA sprites used by the device."""
    value = bytes(payload)
    if not value.startswith(PNG_SIGNATURE):
        raise ValueError("Invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    width = height = 0
    compressed = bytearray()
    saw_header = False
    while offset + 12 <= len(value):
        length = struct.unpack(">I", value[offset:offset + 4])[0]
        kind = value[offset + 4:offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(value):
            raise ValueError("Truncated PNG chunk")
        chunk = value[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", value[offset + 8 + length:chunk_end])[0]
        if zlib.crc32(kind + chunk) & 0xFFFFFFFF != expected_crc:
            raise ValueError("PNG chunk checksum mismatch")
        if kind == b"IHDR":
            if length != 13 or saw_header:
                raise ValueError("Invalid PNG header")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
            if (
                width <= 0 or height <= 0 or width > 4096 or height > 4096 or
                bit_depth != 8 or color_type != 6 or compression != 0 or
                filtering != 0 or interlace != 0
            ):
                raise ValueError("Only non-interlaced 8-bit RGBA PNGs are supported")
            saw_header = True
        elif kind == b"IDAT":
            compressed.extend(chunk)
        elif kind == b"IEND":
            break
        offset = chunk_end

    if not saw_header or not compressed:
        raise ValueError("PNG is missing required image data")
    stride = width * 4
    raw = zlib.decompress(bytes(compressed))
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError("PNG scanline size does not match its dimensions")

    output = bytearray()
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + stride])
        cursor += stride
        if filter_type not in {0, 1, 2, 3, 4}:
            raise ValueError("Unsupported PNG scanline filter")
        for index in range(stride):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            predictor = (
                0 if filter_type == 0 else
                left if filter_type == 1 else
                up if filter_type == 2 else
                (left + up) // 2 if filter_type == 3 else
                _paeth(left, up, upper_left)
            )
            row[index] = (row[index] + predictor) & 0xFF
        output.extend(row)
        previous = row
    return width, height, bytes(output)
