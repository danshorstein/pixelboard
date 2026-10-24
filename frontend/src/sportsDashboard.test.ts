// @vitest-environment jsdom
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
import {describe,it,expect} from 'vitest';
import catalog from './sportsTeams.json';
const root=resolve(import.meta.dirname,'../..');
const js=execFileSync(resolve(root,'.venv/bin/python'),['-c','from shared_py.sports_dashboard import SPORTS_JS; print(SPORTS_JS)'],{cwd:root,encoding:'utf8'});
function setup(){
 document.body.innerHTML='<div id="sports-settings"></div><input id="nfl-enabled" type="checkbox">';
 const run=new Function(js+'; return {set:(v,c)=>{sportsSettings=v;sportsCatalog=c;renderSports();},get:()=>sportsSettings};')();
 run.set(Object.fromEntries(['mlb','nfl','nba','nhl','team'].map(k=>[k,{enabled:k==='mlb'||k==='team',teams:null}])),catalog);
 return run;
}
describe('dashboard sport and team controls',()=>{
 it('selects NHL alone and preserves the saved selection model',()=>{
  const run=setup();const section=Array.from(document.querySelector('#sports-settings')!.children).find(el=>el.querySelector('label')?.textContent===' NHL')!;
  (section.querySelector('button') as HTMLButtonElement).click();
  expect(Object.entries(run.get()).filter(([,v])=>(v as {enabled:boolean}).enabled).map(([k])=>k)).toEqual(['nhl']);
 });
 it('offers all teams even on off-days, with an explicit empty selection',()=>{
  const run=setup();const section=Array.from(document.querySelector('#sports-settings')!.children).find(el=>el.querySelector('label')?.textContent===' NHL')!;
  const select=section.querySelector('select')!;select.value='selected';select.dispatchEvent(new Event('change',{bubbles:true}));
  expect(run.get().nhl.teams).toEqual([]);
  expect(section.querySelectorAll('details input[type=checkbox]')).toHaveLength(32);
  (section.querySelector('details input[type=checkbox]') as HTMLInputElement).click();
  expect(run.get().nhl.teams).toHaveLength(1);
  select.value='all';select.dispatchEvent(new Event('change',{bubbles:true}));expect(run.get().nhl.teams).toBeNull();
 });
});
