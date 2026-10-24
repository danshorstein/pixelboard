// @vitest-environment jsdom
import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {SportsPreview} from './SportsPreview';
const game={id:'nba:1',league:'nba',away:{id:'a',abbr:'BOS',name:'Boston',color:'007a33',score:118},home:{id:'b',abbr:'NY',name:'New York',color:'006bb6',score:123},date:'2026-10-24T23:00Z',state:'in',completed:false,status:'LIVE',period:3,clock:'4:21'};
const snapshot=(league:string,mode:string)=>({league,date:'2026-10-24',mode,games:league==='nba'?[game]:[],source:{provider:mode==='live'?'ESPN':'Synthetic demo',freshness:mode==='live'?'fresh':mode,refreshSec:30,fetchedUtc:null,error:null},metrics:null});
let container:HTMLDivElement,root:Root;
const button=(text:string)=>Array.from(container.querySelectorAll('button')).find(b=>b.textContent===text)!;
async function click(el:HTMLElement){await act(async()=>el.click());}
async function mode(value:string){await act(async()=>{const select=container.querySelector('select')!;select.value=value;select.dispatchEvent(new Event('change',{bubbles:true}));});}
beforeEach(()=>{
 Object.assign(globalThis,{IS_REACT_ACT_ENVIRONMENT:true});vi.useFakeTimers();
 const storage=new Map<string,string>();vi.stubGlobal('localStorage',{getItem:(k:string)=>storage.get(k)??null,setItem:(k:string,v:string)=>storage.set(k,v),clear:()=>storage.clear()});
 vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue({createImageData:()=>({data:new Uint8ClampedArray(128*32*4)}),putImageData:()=>{}} as unknown as CanvasRenderingContext2D);
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{const league=url.split('/').pop()!.split('?')[0];const mode=new URL(url,'http://local').searchParams.get('mode')!;return {ok:true,json:async()=>snapshot(league,mode)};}));
 container=document.createElement('div');document.body.append(container);root=createRoot(container);
});
afterEach(async()=>{await act(async()=>root.unmount());container.remove();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
describe('sports preview controls',()=>{
 it('holds the selected card while new score data renders, and Next releases hold',async()=>{
  await act(async()=>root.render(<SportsPreview/>));
  await click(button('Hold / watch live'));
  expect(container.textContent).toContain('Holding this card');
  await click(button('Simulate +1 home score'));
  expect(container.querySelector('canvas')!.getAttribute('aria-label')).toContain('NY 124');
  expect(container.querySelector('canvas')!.getAttribute('aria-label')).toContain('held');
  await act(async()=>vi.advanceTimersByTimeAsync(16000));
  expect(container.textContent).toContain('Holding this card');
  await click(button('Next →'));
  expect(container.textContent).not.toContain('Holding this card');
 });
 it('filters favorites and preserves saved selections',async()=>{
  await act(async()=>root.render(<SportsPreview/>));
  const only=Array.from(container.querySelectorAll('input')).find(el=>el.parentElement?.textContent===' Favorites only')!;
  await click(only);expect(container.textContent).toContain('0 cards');
  const favorite=Array.from(container.querySelectorAll('input')).find(el=>el.parentElement?.textContent==='NBA · Boston')!;
  await click(favorite);expect(container.textContent).toContain('1 cards');
  expect(JSON.parse(localStorage.getItem('sports-preview-favorites')!)).toEqual(['nba:BOS']);
 });
 it('keeps polling in live mode while held',async()=>{
  await act(async()=>root.render(<SportsPreview/>));await mode('live');
  await click(button('Hold / watch live'));
  const count=vi.mocked(fetch).mock.calls.length;
  await act(async()=>vi.advanceTimersByTimeAsync(31000));
  expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(count);
  expect(container.textContent).toContain('Holding this card');
 });
 it('rejects a late live response after switching to sample mode',async()=>{
  await act(async()=>root.render(<SportsPreview/>));
  let finish:((value:unknown)=>void)|undefined;
  vi.mocked(fetch).mockImplementation((url)=>new Promise(resolve=>{if(String(url).includes('/nba?'))finish=resolve as (v:unknown)=>void;}));
  await mode('live');
  vi.mocked(fetch).mockImplementation(async(url)=>({ok:true,json:async()=>snapshot(String(url).includes('/nba?')?'nba':'nhl','demo')}) as Response);
  await mode('demo');
  await act(async()=>finish?.({ok:true,json:async()=>({...snapshot('nba','live'),games:[{...game,home:{...game.home,score:999}}]})}));
  expect(container.querySelector('canvas')!.getAttribute('aria-label')).toContain('NY 123');
  expect(container.textContent).toContain('SYNTHETIC SAMPLE');
 });
});
