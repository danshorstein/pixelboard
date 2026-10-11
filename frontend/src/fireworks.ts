import { PixelBuffer, type Rgba } from "../../shared_ts/renderer";

const COLORS: readonly Rgba[] = [
  [255, 82, 104, 255],
  [255, 208, 71, 255],
  [88, 214, 141, 255],
  [127, 221, 255, 255],
  [190, 121, 255, 255]
];

const burst = (frame: PixelBuffer, centerX: number, centerY: number, radius: number, color: Rgba) => {
  for (let ray = 0; ray < 18; ray += 1) {
    const angle = (Math.PI * 2 * ray) / 18;
    const length = radius * (0.68 + ((ray * 7) % 5) / 10);
    for (let point = 1; point <= length; point += 1) {
      if (point < length * 0.35 || point % 2 === 0) {
        const fade = 1 - point / (length + 2);
        const x = Math.round(centerX + Math.cos(angle) * point);
        const y = Math.round(centerY + Math.sin(angle) * point + (point * point) / 120);
        const spark: Rgba = [color[0], color[1], color[2], Math.round(255 * Math.max(0.25, fade))];
        frame.blendPixel(x, y, spark);
        frame.blendPixel(x + 1, y, spark);
        if (point < length * 0.75) frame.blendPixel(x, y + 1, spark);
      }
    }
  }
  frame.setPixel(centerX, centerY, [255, 255, 255, 255]);
};

/** A deliberately low-resolution celebration frame for the physical 128x32 display. */
export const createFireworksFrame = (width: number, height: number, elapsedMs: number) => {
  const frame = new PixelBuffer(width, height, [5, 12, 34, 255]);
  frame.fillRect(0, height - 5, width, 5, [11, 18, 42, 255]);
  const beat = (elapsedMs % 3_600) / 3_600;
  const centers = [
    [width * 0.22, height * 0.43, 0.0],
    [width * 0.52, height * 0.26, 0.31],
    [width * 0.79, height * 0.49, 0.62]
  ] as const;

  for (let index = 0; index < centers.length; index += 1) {
    const [x, y, offset] = centers[index];
    const phase = (beat + offset) % 1;
    if (phase < 0.18) {
      frame.drawLine(x, height - 2, x + (index - 1) * 5, y, [215, 226, 255, 210]);
      continue;
    }
    if (phase < 0.82) {
      burst(frame, Math.round(x), Math.round(y), 4 + phase * Math.min(width, height) * 0.52, COLORS[index % COLORS.length]);
    }
  }

  for (let star = 0; star < Math.max(12, Math.floor(width / 6)); star += 1) {
    const x = (star * 37 + 11) % width;
    const y = (star * 13 + 5) % Math.max(1, height - 4);
    if ((star + Math.floor(elapsedMs / 220)) % 3 === 0) {
      frame.setPixel(x, y, [190, 220, 255, 255]);
      frame.setPixel(x + 1, y, [120, 170, 255, 255]);
    }
  }
  return frame;
};
