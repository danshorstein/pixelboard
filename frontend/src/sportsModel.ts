export type League = 'nba' | 'nhl' | 'nfl';
export interface Team { id: string; abbr: string; name: string; color: string; score: number | null }
export interface Game { id: string; league: League; away: Team; home: Team; date: string | null; state: string; completed: boolean; status: string; period: number | null; clock: string | null }
export interface Snapshot { league: League; date: string; mode: string; games: Game[]; source: {provider: string; freshness: string; fetchedUtc: string | null; refreshSec: number; error: string | null}; metrics: {bytes:number;requestMs:number;parseMs:number;games:number} | null }
export function selectedGames(snapshots: Snapshot[], favorites: string[], only: boolean) {
  return snapshots.flatMap(s => s.games).filter(g => !only || [g.away,g.home].some(t => favorites.includes(`${g.league}:${t.abbr}`))).sort((a,b) => Number(b.state==='in')-Number(a.state==='in') || a.league.localeCompare(b.league) || a.id.localeCompare(b.id));
}
export {sportsHeadline as headline} from '../../shared_ts/sports_frame';
