from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BdfGlyph:
    name: str
    encoding: int
    advance_x: int
    width: int
    height: int
    x_offset: int
    y_offset: int
    bitmap: bytes


@dataclass(frozen=True)
class BdfFont:
    name: str
    width: int
    height: int
    x_offset: int
    y_offset: int
    ascent: int
    descent: int
    default_char: int
    glyphs: dict[int, BdfGlyph]


def _integers(value: str) -> list[int]:
    result: list[int] = []
    for part in value.strip().split():
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


def _decode_bitmap(rows: list[str], width: int, height: int) -> bytes:
    bitmap = bytearray(max(0, width * height))
    for y in range(height):
        row = (rows[y] if y < len(rows) else "").strip()
        for x in range(width):
            try:
                nibble = int(row[x // 4] if x // 4 < len(row) else "0", 16)
            except ValueError:
                nibble = 0
            if nibble & (1 << (3 - (x % 4))):
                bitmap[y * width + x] = 1
    return bytes(bitmap)


def parse_bdf(source: str) -> BdfFont:
    if not isinstance(source, str) or "STARTFONT" not in source:
        raise ValueError("Invalid BDF: missing STARTFONT")
    name = "unnamed-bdf"
    width = height = x_offset = y_offset = ascent = descent = default_char = 0
    current: dict[str, object] | None = None
    in_bitmap = False
    glyphs: dict[int, BdfGlyph] = {}

    def finish() -> None:
        nonlocal current, in_bitmap
        if current is None:
            return
        encoding = int(current["encoding"])
        if encoding >= 0:
            glyph_width = int(current["width"])
            glyph_height = int(current["height"])
            glyphs[encoding] = BdfGlyph(
                name=str(current["name"]),
                encoding=encoding,
                advance_x=int(current["advance_x"]) or glyph_width or width,
                width=glyph_width,
                height=glyph_height,
                x_offset=int(current["x_offset"]),
                y_offset=int(current["y_offset"]),
                bitmap=_decode_bitmap(list(current["rows"]), glyph_width, glyph_height),
            )
        current = None
        in_bitmap = False

    for raw_line in source.replace("\r", "").split("\n"):
        line = raw_line.rstrip()
        if in_bitmap and current is not None:
            if line == "ENDCHAR":
                finish()
            elif all(character in "0123456789abcdefABCDEF" for character in line.strip()):
                current["rows"].append(line.strip())  # type: ignore[union-attr]
            continue
        if line.startswith("STARTCHAR "):
            finish()
            current = {
                "name": line[10:].strip(),
                "encoding": -1,
                "advance_x": 0,
                "width": 0,
                "height": 0,
                "x_offset": 0,
                "y_offset": 0,
                "rows": [],
            }
        elif current is not None and line.startswith("ENCODING "):
            values = _integers(line[9:])
            current["encoding"] = values[0] if values else -1
        elif current is not None and line.startswith("DWIDTH "):
            values = _integers(line[7:])
            current["advance_x"] = values[0] if values else 0
        elif current is not None and line.startswith("BBX "):
            values = _integers(line[4:]) + [0, 0, 0, 0]
            current["width"] = max(0, values[0])
            current["height"] = max(0, values[1])
            current["x_offset"] = values[2]
            current["y_offset"] = values[3]
        elif current is not None and line == "BITMAP":
            in_bitmap = True
        elif line.startswith("FONT "):
            name = line[5:].strip()
        elif line.startswith("FONTBOUNDINGBOX "):
            values = _integers(line[16:]) + [0, 0, 0, 0]
            width, height = max(0, values[0]), max(0, values[1])
            x_offset, y_offset = values[2], values[3]
        elif line.startswith("FONT_ASCENT "):
            values = _integers(line[12:])
            ascent = values[0] if values else 0
        elif line.startswith("FONT_DESCENT "):
            values = _integers(line[13:])
            descent = values[0] if values else 0
        elif line.startswith("DEFAULT_CHAR "):
            values = _integers(line[13:])
            default_char = values[0] if values else 0
    finish()
    if width <= 0 or height <= 0 or not glyphs:
        raise ValueError("Invalid BDF: missing font metrics or glyphs")
    return BdfFont(
        name=name,
        width=width,
        height=height,
        x_offset=x_offset,
        y_offset=y_offset,
        ascent=ascent or max(0, height + y_offset),
        descent=descent or max(0, -y_offset),
        default_char=default_char,
        glyphs=glyphs,
    )


def glyph_for(font: BdfFont, code_point: int) -> BdfGlyph | None:
    return font.glyphs.get(code_point) or font.glyphs.get(font.default_char) or font.glyphs.get(0)


def measure_text(font: BdfFont, text: str) -> int:
    return sum((glyph_for(font, ord(character)) or BdfGlyph("", 0, font.width, 0, 0, 0, 0, b"")).advance_x for character in str(text))
