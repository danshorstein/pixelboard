import {describe,it,expect} from 'vitest';
import {headline,selectedGames,type Game,type Snapshot} from './sportsModel';
const game:Game={id:'nba:1',league:'nba',away:{id:'1',abbr:'BOS',name:'Boston',color:'007a33',score:118},home:{id:'2',abbr:'NY',name:'New York',color:'006bb6',score:123},date:'2026-10-24T23:00Z',state:'in',completed:false,status:'In progress',period:6,clock:'1:24'};
describe('sports preview semantics',()=>{
 it('distinguishes NBA quarters and overtime from NHL periods',()=>{
  expect(headline(game)).toBe('2OT 1:24');
  expect(headline({...game,league:'nhl',period:3})).toBe('P3 1:24');
  expect(headline({...game,league:'nhl',period:4})).toBe('OT 1:24');
  expect(headline({...game,league:'nhl',period:5,status:'Shootout'})).toBe('SO');
 });
 it('preserves special provider states rather than faking a running clock',()=>{
  for(const status of ['HALFTIME','INTERMISSION','POSTPONED','DELAYED','FINAL/SO'])expect(headline({...game,status})).toBe(status);
  expect(headline({...game,state:'unknown',status:'TBD'})).toBe('TBD');
 });
 it('filters favorites by league and sorts live games first',()=>{
  const snapshot={games:[{...game,id:'nba:2',state:'post'},game,{...game,id:'nhl:1',league:'nhl'}]} as Snapshot;
  expect(selectedGames([snapshot],['nba:BOS'],true).map(g=>g.id)).toEqual(['nba:1','nba:2']);
  expect(selectedGames([snapshot],[],true)).toEqual([]);
  expect(selectedGames([snapshot],[],false)).toHaveLength(3);
 });
});
