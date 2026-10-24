import {useEffect, useMemo, useRef, useState} from 'react';
import {drawCard} from './sportsCanvas';
import {selectedGames, type Game, type League, type Snapshot} from './sportsModel';
import './sportsPreview.css';
const leagues: League[]=['nba','nhl','nfl'];
const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
function Panel({game,stale,held,scale}:{game:Game|undefined;stale:boolean;held:boolean;scale:number}) {
  const ref=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{if(ref.current)drawCard(ref.current,game,stale,held);},[game,stale,held]);
  return <canvas ref={ref} width={128} height={32} style={{width:128*scale,height:32*scale}} role="img" aria-label={game?`${game.league.toUpperCase()} ${game.away.abbr} ${game.away.score??'unknown'} at ${game.home.abbr} ${game.home.score??'unknown'}, ${game.status}${held?', held':''}`:'No selected games'}/>;
}
export function SportsPreview() {
  const [mode,setMode]=useState('demo'),[day,setDay]=useState(today),[enabled,setEnabled]=useState<League[]>(['nba','nhl']);
  const [snapshots,setSnapshots]=useState<Snapshot[]>([]),[errors,setErrors]=useState<Record<string,string>>({});
  const [loading,setLoading]=useState(true),[favorites,setFavorites]=useState<string[]>([]),[only,setOnly]=useState(false);
  const [id,setId]=useState<string|null>(null),[held,setHeld]=useState(false),[dwell,setDwell]=useState(8),[scale,setScale]=useState(6);
  const [tick,setTick]=useState(0);
  useEffect(()=>{
    document.title='NBA / NHL · Scoreboard Lab';
    try{const saved=JSON.parse(localStorage.getItem('sports-preview-favorites')||'[]');if(Array.isArray(saved)&&saved.every(x=>typeof x==='string'))setFavorites(saved);}catch{/* Local storage is optional. */}
  },[]);
  useEffect(()=>{
    const controller=new AbortController();let stopped=false;const timers:ReturnType<typeof setTimeout>[]=[];
    setSnapshots([]);setErrors({});setLoading(enabled.length>0);setId(null);setHeld(false);
    let waiting=enabled.length;
    for(const league of enabled){
      const poll=async()=>{
        let delay=30000;
        try{
          const r=await fetch(`/api/sports/${league}?day=${encodeURIComponent(day)}&mode=${mode}`,{signal:controller.signal});
          if(!r.ok)throw new Error(`Preview server returned ${r.status}`);
          const value=await r.json() as Snapshot;
          if(stopped)return;
          delay=Math.max(30000,value.source.refreshSec*1000);
          setSnapshots(old=>[...old.filter(s=>s.league!==league),value]);
          setErrors(old=>{const next={...old};delete next[league];return next;});
        }catch(e){if(!stopped){setErrors(old=>({...old,[league]:e instanceof Error?e.message:'Request failed'}));setSnapshots(old=>old.map(s=>s.league===league?{...s,source:{...s.source,freshness:'stale'}}:s));}}
        finally{if(!stopped){waiting=Math.max(0,waiting-1);if(!waiting)setLoading(false);if(mode==='live')timers.push(setTimeout(()=>void poll(),delay));}}
      };void poll();
    }
    return()=>{stopped=true;controller.abort();timers.forEach(clearTimeout);};
  },[day,mode,enabled,tick]);
  const games=useMemo(()=>selectedGames(snapshots,favorites,only),[snapshots,favorites,only]);
  const current=games.find(g=>g.id===id)||games[0];
  const currentId=current?.id;
  const move=(delta:number)=>{setHeld(false);if(games.length){const index=games.findIndex(g=>g.id===currentId);setId(games[(index+delta+games.length)%games.length].id);}};
  useEffect(()=>{
    const keyboard=(event:KeyboardEvent)=>{
      if(event.target instanceof HTMLElement && event.target.closest('input,select,textarea,button'))return;
      if(event.key.toLowerCase()==='h'){event.preventDefault();if(currentId)setHeld(h=>!h);}
      if(event.key==='ArrowRight'){event.preventDefault();move(1);}
      if(event.key==='ArrowLeft'){event.preventDefault();move(-1);}
    };
    window.addEventListener('keydown',keyboard);return()=>window.removeEventListener('keydown',keyboard);
  },[currentId,games]);
  useEffect(()=>{
    if(held||!games.length)return;
    const timer=setTimeout(()=>{const i=games.findIndex(g=>g.id===currentId);setId(games[(i+1)%games.length].id);},dwell*1000);
    return()=>clearTimeout(timer);
  },[held,currentId,games,dwell]);
  useEffect(()=>{if(!games.some(g=>g.id===id)){setId(games[0]?.id||null);setHeld(false);}},[games,id]);
  useEffect(()=>{
    if(!held||!current?.completed)return;
    const timer=setTimeout(()=>setHeld(false),60000);return()=>clearTimeout(timer);
  },[held,current?.completed,currentId]);
  const teams=useMemo(()=>Array.from(new Map(snapshots.flatMap(s=>s.games.flatMap(g=>[g.home,g.away].map(t=>[`${g.league}:${t.abbr}`,`${g.league.toUpperCase()} · ${t.name}`] as const)))).entries()).sort((a,b)=>a[1].localeCompare(b[1])),[snapshots]);
  const toggleFavorite=(key:string)=>setFavorites(old=>{const next=old.includes(key)?old.filter(x=>x!==key):[...old,key];try{localStorage.setItem('sports-preview-favorites',JSON.stringify(next));}catch{/* Optional persistence. */}return next;});
  const source=snapshots.find(s=>s.league===current?.league)?.source;
  const stale=source?['stale','failed'].includes(source.freshness):mode==='failed'||Object.keys(errors).length>0;
  const simulate=()=>setSnapshots(old=>old.map(s=>({...s,games:s.games.map(g=>g.id===currentId?{...g,home:{...g.home,score:(g.home.score||0)+1}}:g)})));
  return <main className="sports-preview">
    <header><p className="eyebrow">PIXELBOARD · BROWSER LAB</p><h1>Two more leagues.<br/><span>The same little board.</span></h1><p>Try NBA and NHL scores in 128 × 32 pixels. Your Pi keeps running its current build.</p></header>
    <section className="sports-controls" aria-label="Feed controls">
      <label>Data source<select value={mode} onChange={e=>setMode(e.target.value)}><option value="demo">Sample games</option><option value="live">Live ESPN</option><option value="stale">Sample: stale data</option><option value="failed">Sample: provider offline</option><option value="empty">Sample: no games</option></select></label>
      <label>Scoreboard date (Eastern)<input type="date" value={day} onChange={e=>{if(e.target.value)setDay(e.target.value);}}/></label>
      <fieldset><legend>Leagues</legend>{leagues.map(l=><label key={l}><input type="checkbox" checked={enabled.includes(l)} onChange={()=>setEnabled(old=>old.includes(l)?old.filter(x=>x!==l):[...old,l])}/>{l.toUpperCase()}</label>)}</fieldset>
      <label>Seconds per card<input type="number" min={3} max={60} value={dwell} onChange={e=>setDwell(Math.max(3,Math.min(60,Number(e.target.value)||8)))}/></label>
    </section>
    <section className="sports-stage" aria-label="Scoreboard preview">
      <div className="sports-stage-title"><strong>{mode==='live'?'LIVE ESPN · 30s minimum polling':'SYNTHETIC SAMPLE · NOT LIVE'}</strong><span>{loading?'Loading feeds…':`${games.length} cards · ${games.length*dwell}s full loop`}</span></div>
      <div className="sports-canvas"><Panel game={current} stale={stale} held={held} scale={scale}/></div>
      <div className="sports-transport"><button onClick={()=>move(-1)} disabled={!current}>← Previous</button><button className={held?'active':''} onClick={()=>setHeld(h=>!h)} disabled={!current}>{held?'Resume rotation':'Hold / watch live'}</button><button onClick={()=>move(1)} disabled={!current}>Next →</button><label>Zoom<select value={scale} onChange={e=>setScale(Number(e.target.value))}>{[2,4,6].map(n=><option key={n} value={n}>{n}×</option>)}</select></label></div>
      <div className="sports-native"><span>Native pixel size (physical size depends on your screen)</span><Panel game={current} stale={stale} held={held} scale={1}/></div>
      {held&&<p role="status">Holding this card. Live polling continues.{current?.completed?' Rotation resumes after 60 seconds on this final.':''}</p>}
      {mode!=='live'&&current&&<button onClick={simulate}>Simulate +1 home score</button>}
      <p className="sports-note">Keyboard: H holds, ← / → change cards. Provider clock is shown as received, without a simulated countdown. Badges use team colors; official logos are not loaded.</p>
    </section>
    <div className="sports-columns"><section className="sports-box"><h2>Game rotation</h2><label><input type="checkbox" checked={only} onChange={e=>setOnly(e.target.checked)}/> Favorites only</label>
      {!games.length&&<p>{loading?'Loading…':'No selected games. Check leagues, date and favorites.'}</p>}
      <div className="sports-games">{games.map(g=><button key={g.id} aria-pressed={g.id===currentId} onClick={()=>{setId(g.id);setHeld(false);}}><span>{g.league.toUpperCase()} · {g.away.abbr} @ {g.home.abbr}</span><strong>{g.state==='pre'?'—':`${g.away.score??'?'} – ${g.home.score??'?'}`}</strong><small>{g.status}</small></button>)}</div>
    </section><aside><section className="sports-box"><h2>Feed health & measurements</h2><p>Local browser-server measurements. These do not measure Pi performance.</p>
      {enabled.map(l=>{const s=snapshots.find(v=>v.league===l);return <div key={l} className="sports-health"><strong>{l.toUpperCase()} · {s?.source.freshness||'loading'}</strong><p role={errors[l]||s?.source.error?'status':undefined}>{errors[l]||s?.source.error||s?.source.provider}</p>{s?.source.fetchedUtc&&<small>Last success {new Date(s.source.fetchedUtc).toLocaleTimeString()}</small>}{s?.metrics&&<p>{(s.metrics.bytes/1024).toFixed(1)} KiB body · {s.metrics.requestMs.toFixed(0)} ms request · {s.metrics.parseMs.toFixed(2)} ms parse · {s.metrics.games} games</p>}</div>;})}
      <button onClick={()=>setTick(v=>v+1)}>Reload preview</button><p className="sports-note">Server caching limits requests even when reloaded. ESPN’s website feed has no verified service guarantee.</p></section>
      <section className="sports-box"><h2>Favorites</h2><p>Saved only in this browser. Teams below come from the selected date’s games.</p>{teams.map(([key,name])=><label className="sports-favorite" key={key}><input type="checkbox" checked={favorites.includes(key)} onChange={()=>toggleFavorite(key)}/>{name}</label>)}</section></aside></div>
  </main>;
}
