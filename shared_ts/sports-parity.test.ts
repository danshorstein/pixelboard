import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {describe,it,expect} from 'vitest';
import {parseBdf} from './bdf';
import {sportsFrame, type SportsFrameGame} from './sports_frame';
const root=resolve(import.meta.dirname,'..');
const fonts=Object.fromEntries(['4x6','6x10'].map(n=>[n,parseBdf(readFileSync(resolve(root,`definition/mlb-classic/fonts/${n}.bdf`),'utf8'))]));
const cases=JSON.parse(readFileSync(resolve(root,'fixtures/sports-frame-cases.json'),'utf8')) as {name:string;game:SportsFrameGame|null;stale:boolean;held:boolean;sha256:string}[];
describe('NBA/NHL exact Python/TypeScript frames',()=>{
 it('matches every state, stale and HOLD reference',()=>{
  for(const c of cases)expect(createHash('sha256').update(sportsFrame(c.game||undefined,fonts,c.stale,c.held).data).digest('hex'),c.name).toBe(c.sha256);
 });
});
