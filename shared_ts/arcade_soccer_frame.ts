// Soccer picture, pixel-exact counterpart of shared_py/arcade_soccer_frame.py.
import type { PixelBuffer } from "./renderer";
import { FP, type SoccerFields } from "./arcade_soccer";

type Color = readonly [number, number, number, number];
type Text = (s: string, x: number, y: number, color?: Color) => void;
interface State extends SoccerFields { status: string }
const WHITE: Color = [221, 240, 237, 255], TEAL: Color = [58, 226, 180, 255], GOLD: Color = [255, 201, 58, 255], BLACK: Color = [0, 0, 0, 255];
const PITCH: Color = [0, 40, 12, 255], STRIPE: Color = [0, 48, 15, 255], LINE: Color = [80, 120, 95, 255], NET: Color = [120, 130, 125, 255];
const KEEPERS: Color[] = [[40, 120, 255, 255], [255, 110, 40, 255]]; // keepers wear a different colour
const CIRCLE = [[-5, -1], [-5, 0], [-5, 1], [5, -1], [5, 0], [5, 1], [-1, -5], [0, -5], [1, -5], [-1, 5], [0, 5], [1, 5],
  [-4, -3], [-3, -4], [4, -3], [3, -4], [-4, 3], [-3, 4], [4, 3], [3, 4]];
const px = (v: number) => Math.floor((v + FP / 2) / FP);

let pitchCache: Uint8ClampedArray | null = null; // the empty pitch, drawn once
function pitch(b: PixelBuffer) {
  b.fillRect(1, 6, 126, 26, PITCH);
  for (let x = 9; x < 120; x += 16) b.fillRect(x, 7, 8, 24, STRIPE);
  b.strokeRect(1, 6, 126, 26, LINE);
  b.drawLine(64, 6, 64, 31, LINE);
  for (const [dx, dy] of CIRCLE) b.setPixel(64 + dx, 18 + dy, LINE);
  b.strokeRect(1, 10, 12, 18, LINE); b.strokeRect(115, 10, 12, 18, LINE);
  for (const x of [0, 127]) { b.fillRect(x, 12, 1, 14, NET); b.setPixel(x, 12, WHITE); b.setPixel(x, 25, WHITE); }
  b.fillRect(0, 12, 2, 1, WHITE); b.fillRect(126, 12, 2, 1, WHITE); b.fillRect(0, 25, 2, 1, WHITE); b.fillRect(126, 25, 2, 1, WHITE);
}
export function soccerFrame(b: PixelBuffer, s: State, text: Text) {
  if (!pitchCache) { pitch(b); pitchCache = b.data.slice(); }
  b.data.set(pitchCache);
  s.players.forEach((p, i) => {
    const x = px(p[0]), y = px(p[1]);
    const color = i === 0 || i === 3 ? KEEPERS[i === 0 ? 0 : 1] : i < 3 ? TEAL : GOLD;
    b.fillRect(x - 1, y - 2, 2, 3, color);
    if (i === s.control && s.phase === "play") b.fillRect(x - 1, y - 4, 2, 1, WHITE);
  });
  b.fillRect(px(s.ball[0]) - 1, px(s.ball[1]) - 1, 2, 2, WHITE);
  const you = `YOU ${s.you}`, pi = `PI ${s.pi}`;
  text(you, 1, 0, TEAL); text(pi, 128 - pi.length * 4, 0, GOLD);
  const clock = s.golden ? "GOLDEN GOAL" : `${Math.floor(s.clock / 60000)}:${String(Math.floor(s.clock / 1000) % 60).padStart(2, "0")}`;
  text(clock, 64 - clock.length * 2, 0, s.golden ? GOLD : WHITE);
  if (s.banner && s.status === "running") {
    const w = s.banner.length * 4;
    b.fillRect(62 - Math.floor(w / 2), 13, w + 4, 8, BLACK);
    text(s.banner, 64 - Math.floor(w / 2), 14, s.banner !== "PI SCORES" ? GOLD : WHITE);
  }
}
