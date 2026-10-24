import {glyphForCodePoint, type BdfFont} from './bdf';
import {PixelBuffer, type Rgba} from './renderer';
export interface SportsFrameGame {
  league: string; away: {abbr:string;color?:string;score?:number|string|null}; home: {abbr:string;color?:string;score?:number|string|null};
  date?:string|null; state:string; completed:boolean; status:string; period?:number|null; clock?:string|null;
}
export function sportsHeadline(g:SportsFrameGame,timeZone='America/New_York') {
  const s=g.status.toUpperCase();
  if(/POSTPON|DELAY|CANCEL|SUSPEND|HALF|INTERMISSION|END OF|FINAL|SO|SHOOTOUT/.test(s))return s.replace('SHOOTOUT','SO');
  if(g.completed)return 'FINAL';
  if(g.state==='pre')return g.date?new Date(g.date).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone}):'SCHEDULED';
  if(g.state!=='in')return s;
  const p=g.period||0;
  const period=g.league==='nhl'?(p>3?`${p>4?p-3:''}OT`:`P${p}`):(p>4?`${p>5?p-4:''}OT`:`Q${p}`);
  return `${period} ${g.clock||''}`.trim();
}
export function sportsFrame(game:SportsFrameGame|undefined,fonts:Record<string,BdfFont>,stale=false,held=false,timeZone='America/New_York') {
  const frame=new PixelBuffer(128,32,[3,8,7,255]);
  function text(value:string,x:number,y:number,font:BdfFont,color:Rgba,max=128){
    for(const ch of value.toUpperCase()){
      const g=glyphForCodePoint(font,ch.codePointAt(0)!);if(!g)continue;
      if(x+g.width>max)break;
      for(let row=0;row<g.height;row++)for(let col=0;col<g.width;col++)if(g.bitmap[row*g.width+col])frame.setPixel(x+col,y+row,color);
      x+=g.advanceX;
    }
  }
  const small=fonts['4x6'],large=fonts['6x10'],white:Rgba=[255,255,255,255],gold:Rgba=[255,194,117,255];
  if(!game){text('NO SELECTED GAMES',3,6,small,white);text(stale?'DATA OFFLINE':'CHECK FILTERS',3,20,small,gold);return frame;}
  [game.away,game.home].forEach((team,i)=>{
    const raw=/^[\da-f]{6}$/i.test(team.color||'')?team.color!:'394b64';
    const channel=(j:number)=>Math.floor(parseInt(raw.slice(j,j+2),16)*7/15);
    const color:Rgba=[channel(0),channel(2),channel(4),255];
    frame.fillRect(0,i*16,60,15,color);
    text(team.abbr,3,i*16+5,small,white,26);
    const score=game.state==='pre'||team.score==null?'--':String(team.score);
    text(score,60-score.length*6-3,i*16+2,large,white,59);
  });
  text(game.league.toUpperCase()+(held?' HOLD':''),64,2,small,[155,230,181,255]);
  const lines:string[]=[];let line='';
  for(const word of (stale?'DATA STALE':sportsHeadline(game,timeZone)).split(' ')){
    if((line+' '+word).trim().length>15&&line){lines.push(line);line=word;}else line=(line+' '+word).trim();
  }if(line)lines.push(line);
  lines.slice(0,2).forEach((v,i)=>text(v,64,13+i*10,small,i?white:gold));
  return frame;
}
