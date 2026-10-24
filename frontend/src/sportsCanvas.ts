import {parseBdf} from '../../shared_ts/bdf';
import {sportsFrame} from '../../shared_ts/sports_frame';
import smallRaw from '../../definition/mlb-classic/fonts/4x6.bdf?raw';
import largeRaw from '../../definition/mlb-classic/fonts/6x10.bdf?raw';
import type {Game} from './sportsModel';
const fonts={'4x6':parseBdf(smallRaw),'6x10':parseBdf(largeRaw)};
export function drawCard(canvas:HTMLCanvasElement,game:Game|undefined,stale:boolean,held:boolean){
  const ctx=canvas.getContext('2d');if(!ctx)return;
  const frame=sportsFrame(game,fonts,stale,held);
  const image=ctx.createImageData(128,32);image.data.set(frame.data);ctx.putImageData(image,0,0);
}
