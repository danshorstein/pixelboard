/** A decoded glyph from a Glyph Bitmap Distribution Format (BDF) font. */
export interface BdfGlyph {
  readonly name: string;
  readonly encoding: number;
  readonly advanceX: number;
  readonly width: number;
  readonly height: number;
  readonly xOffset: number;
  readonly yOffset: number;
  /** Row-major 0/1 pixels, with exactly width * height entries. */
  readonly bitmap: Uint8Array;
}

/** The subset of BDF metrics needed by both M1 renderer implementations. */
export interface BdfFont {
  readonly name: string;
  readonly width: number;
  readonly height: number;
  readonly xOffset: number;
  readonly yOffset: number;
  readonly ascent: number;
  readonly descent: number;
  readonly defaultChar: number;
  readonly glyphs: ReadonlyMap<number, BdfGlyph>;
}

interface MutableGlyph {
  name: string;
  encoding: number;
  advanceX: number;
  width: number;
  height: number;
  xOffset: number;
  yOffset: number;
  bitmapRows: string[];
}

const integers = (value: string): number[] =>
  value
    .trim()
    .split(/\s+/)
    .map(Number)
    .filter(Number.isFinite);

const decodeBitmap = (rows: readonly string[], width: number, height: number): Uint8Array => {
  const bitmap = new Uint8Array(Math.max(0, width * height));
  for (let y = 0; y < height; y += 1) {
    const row = (rows[y] ?? "").trim();
    for (let x = 0; x < width; x += 1) {
      const nibble = Number.parseInt(row[Math.floor(x / 4)] ?? "0", 16);
      if (Number.isFinite(nibble) && (nibble & (1 << (3 - (x % 4)))) !== 0) {
        bitmap[y * width + x] = 1;
      }
    }
  }
  return bitmap;
};

/**
 * Parses an in-memory BDF file. It deliberately performs no I/O, which keeps
 * font loading identical in browsers, tests, and the future device twin.
 */
export const parseBdf = (source: string): BdfFont => {
  if (typeof source !== "string" || !/^STARTFONT\s/m.test(source)) {
    throw new Error("Invalid BDF: missing STARTFONT");
  }

  const lines = source.replace(/\r/g, "").split("\n");
  let name = "unnamed-bdf";
  let width = 0;
  let height = 0;
  let xOffset = 0;
  let yOffset = 0;
  let ascent = 0;
  let descent = 0;
  let defaultChar = 0;
  let current: MutableGlyph | null = null;
  let inBitmap = false;
  const glyphs = new Map<number, BdfGlyph>();

  const finishGlyph = () => {
    if (!current) return;
    if (current.encoding >= 0) {
      glyphs.set(current.encoding, {
        name: current.name,
        encoding: current.encoding,
        advanceX: current.advanceX || current.width || width,
        width: current.width,
        height: current.height,
        xOffset: current.xOffset,
        yOffset: current.yOffset,
        bitmap: decodeBitmap(current.bitmapRows, current.width, current.height)
      });
    }
    current = null;
    inBitmap = false;
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (inBitmap && current) {
      if (line === "ENDCHAR") {
        finishGlyph();
      } else if (/^[0-9A-Fa-f]*$/.test(line.trim())) {
        current.bitmapRows.push(line.trim());
      }
      continue;
    }

    if (line.startsWith("STARTCHAR ")) {
      finishGlyph();
      current = {
        name: line.slice(10).trim(),
        encoding: -1,
        advanceX: 0,
        width: 0,
        height: 0,
        xOffset: 0,
        yOffset: 0,
        bitmapRows: []
      };
    } else if (current && line.startsWith("ENCODING ")) {
      current.encoding = integers(line.slice(9))[0] ?? -1;
    } else if (current && line.startsWith("DWIDTH ")) {
      current.advanceX = integers(line.slice(7))[0] ?? 0;
    } else if (current && line.startsWith("BBX ")) {
      const values = integers(line.slice(4));
      current.width = Math.max(0, values[0] ?? 0);
      current.height = Math.max(0, values[1] ?? 0);
      current.xOffset = values[2] ?? 0;
      current.yOffset = values[3] ?? 0;
    } else if (current && line === "BITMAP") {
      inBitmap = true;
    } else if (line.startsWith("FONT ")) {
      name = line.slice(5).trim();
    } else if (line.startsWith("FONTBOUNDINGBOX ")) {
      const values = integers(line.slice(16));
      width = Math.max(0, values[0] ?? 0);
      height = Math.max(0, values[1] ?? 0);
      xOffset = values[2] ?? 0;
      yOffset = values[3] ?? 0;
    } else if (line.startsWith("FONT_ASCENT ")) {
      ascent = integers(line.slice(12))[0] ?? 0;
    } else if (line.startsWith("FONT_DESCENT ")) {
      descent = integers(line.slice(13))[0] ?? 0;
    } else if (line.startsWith("DEFAULT_CHAR ")) {
      defaultChar = integers(line.slice(13))[0] ?? 0;
    }
  }
  finishGlyph();

  if (width <= 0 || height <= 0 || glyphs.size === 0) {
    throw new Error("Invalid BDF: missing font metrics or glyphs");
  }

  return {
    name,
    width,
    height,
    xOffset,
    yOffset,
    ascent: ascent || Math.max(0, height + yOffset),
    descent: descent || Math.max(0, -yOffset),
    defaultChar,
    glyphs
  };
};

export const glyphForCodePoint = (font: BdfFont, codePoint: number): BdfGlyph | undefined =>
  font.glyphs.get(codePoint) ?? font.glyphs.get(font.defaultChar) ?? font.glyphs.get(0);

export const measureBdfText = (font: BdfFont, text: string): number => {
  let width = 0;
  for (const character of String(text)) {
    width += glyphForCodePoint(font, character.codePointAt(0) ?? 0)?.advanceX ?? font.width;
  }
  return width;
};
