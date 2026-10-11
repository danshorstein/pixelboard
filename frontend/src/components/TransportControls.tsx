import type {
  NormalizedGameState,
  ScenePlaylistItem,
  StandingsState
} from "../../../shared_ts/models";

interface TransportControlsProps {
  playlist: readonly ScenePlaylistItem[];
  games: readonly NormalizedGameState[];
  standings: readonly StandingsState[];
  index: number;
  playing: boolean;
  pinned: boolean;
  progress: number;
  remainingSec: number;
  holdEndingSec: number | null;
  fireworksActive: boolean;
  fireworksProgress: number;
  onPlayingChange: (playing: boolean) => void;
  onPinnedChange: (pinned: boolean) => void;
  onStep: (direction: -1 | 1) => void;
  onNext: () => void;
  onJump: (index: number) => void;
}

const gameLabel = (game: NormalizedGameState) =>
  `${game.away.abbr} @ ${game.home.abbr}${game.doubleheader ? ` · G${game.gameNumber}` : ""}`;

export function TransportControls({
  playlist,
  games,
  standings,
  index,
  playing,
  pinned,
  progress,
  remainingSec,
  holdEndingSec,
  fireworksActive,
  fireworksProgress,
  onPlayingChange,
  onPinnedChange,
  onStep,
  onNext,
  onJump
}: TransportControlsProps) {
  const current = playlist[index];
  const canWatchLive = current?.kind === "game" && current.scene !== "final";
  const holdLabel = current?.kind === "standings"
    ? pinned ? "Screen held" : "Hold screen"
    : pinned ? "Watching live" : canWatchLive ? "Watch live" : "Hold final";

  const itemLabel = (item: ScenePlaylistItem) => {
    if (item.kind === "game") {
      const game = games.find((candidate) => candidate.gameId === item.gameId);
      return game ? `${gameLabel(game)} — ${item.scene}` : `Game — ${item.scene}`;
    }
    if (item.kind === "standings") {
      const snapshot = standings.find((candidate) => candidate.standingsId === item.standingsId);
      const row = snapshot?.teams.find((candidate) => String(candidate.team.id) === item.teamId);
      return `${snapshot?.division.name ?? "Standings"} — ${row?.rank ? `#${row.rank} ` : ""}${row?.team.abbr ?? "team"}`;
    }
    return "Empty schedule — idle";
  };

  return (
    <section className="transport" aria-label="Scoreboard playback controls">
      <div className="pixelboard-actions">
        <button
          type="button"
          className="pixelboard-action next-action red-button"
          data-button="red"
          onClick={onNext}
          disabled={fireworksActive}
        >
          <span className="action-icon" aria-hidden="true">→</span>
          <span className="action-copy">
            <strong>Next</strong>
            <small>Flip to the next screen</small>
          </span>
        </button>
        <button
          type="button"
          className={pinned ? "pixelboard-action hold-action green-button is-active" : "pixelboard-action hold-action green-button"}
          aria-pressed={pinned}
          onClick={() => onPinnedChange(!pinned)}
          data-button="green"
          disabled={fireworksActive}
        >
          <span className="watch-dot" aria-hidden="true" />
          <span className="action-copy">
            <strong>{holdLabel}</strong>
            <small>{pinned ? "Press again to resume rotation" : canWatchLive ? "Keep this game updating" : "Freeze this screen"}</small>
          </span>
        </button>
      </div>
      {fireworksActive ? (
        <p className="easter-egg-status" role="status">🎆 Fireworks finale · {fireworksProgress}s remaining</p>
      ) : null}

      <div className="transport-secondary">
        <button type="button" onClick={() => onStep(-1)} aria-label="Previous screen">← Previous</button>
        <button
          type="button"
          onClick={() => onPlayingChange(!playing)}
          aria-label={playing ? "Pause automatic rotation" : "Resume automatic rotation"}
        >
          {playing ? "Pause rotation" : "Resume rotation"}
        </button>
      </div>

      <label className="jump-control">
        <span>Jump to screen</span>
        <select value={index} onChange={(event) => onJump(Number(event.target.value))}>
          {playlist.map((item, itemIndex) => (
            <option key={`${item.kind}-${itemIndex}`} value={itemIndex}>
              {itemLabel(item)}
            </option>
          ))}
        </select>
      </label>

      <div className="rotation-progress">
        <div className="progress-copy">
          <span>
            Screen {index + 1} of {playlist.length}
          </span>
          <span>
            {holdEndingSec !== null
              ? `Final · resumes in ${holdEndingSec}s`
              : pinned
                ? current?.kind === "game" ? "Live updates · held" : "Screen held"
                : playing ? `${remainingSec}s` : "Rotation paused"}
          </span>
        </div>
        <progress value={pinned ? 1 : progress} max="1" aria-label="Current screen dwell progress" />
        <span className="sr-only">Current scene: {current?.scene ?? "none"}</span>
      </div>
    </section>
  );
}
