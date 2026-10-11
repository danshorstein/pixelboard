import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, it, expect } from 'vitest';
import { createGame, pressGame, startGame, stepGame, steerSnake, swing, type ArcadeState, type GameKind, type Direction } from './arcade';
import { arcadeFrame } from './arcade_frame';
import { parseBdf } from './bdf';
import casesJson from '../fixtures/arcade-replays.json';
interface Case { name:string; kind:GameKind; seed?:number; patch?:Record<string, unknown>; operations:{action?:string;press?:string;ticks?:number;held?:string[]}[]; paused?:boolean;expectedState?:unknown;sha256?:string }
const cases=casesJson as Case[];
const font=parseBdf(readFileSync(new URL('../definition/mlb-classic/fonts/4x6.bdf',import.meta.url),'utf8'));
export function replay(c:Case):ArcadeState {
 let s={...createGame(c.kind,c.seed),...c.patch} as ArcadeState;
 for(const op of c.operations){
  if(op.action==='start')s=startGame(s);
  else if(op.action==='swing' && s.kind==='baseball')s=swing(s);
  else if(op.action && s.kind==='snake')s=steerSnake(s,op.action as Direction);
  if(op.press)s=pressGame(s,op.press);
  for(let i=0;i<(op.ticks??0);i++)s=stepGame(s,new Set(op.held));
 }
 return s;
}
describe('Pi arcade reference replays',()=>{for(const c of cases)it(c.name,()=>{
 const s=replay(c);expect(s).toEqual(c.expectedState);
 expect(createHash('sha256').update(arcadeFrame(s,font,c.paused).data).digest('hex')).toBe(c.sha256);
});});
