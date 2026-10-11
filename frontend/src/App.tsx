import { useEffect, useMemo, useRef, useState } from "react";
import type {
  ContentMode,
  DesignOverrides as RendererOverrides,
  DisplayDefinition,
  GameStatus,
  NormalizedGameState,
  ScenePlaylistItem,
  StandingTeamState,
  StandingsState
} from "../../shared_ts/models";
import { renderScene, resolveDesignSettings } from "../../shared_ts/renderer";
import { buildPlaylist } from "../../shared_ts/rotation";
import { CalibrationPanel } from "./components/CalibrationPanel";
import { DesignPanel, type DesignOverrides, type ParameterBlock } from "./components/DesignPanel";
import { EmulatorCanvas } from "./components/EmulatorCanvas";
import { ProfilePanel } from "./components/ProfilePanel";
import { ProjectPanel } from "./components/ProjectPanel";
import { DeviceBuildPanel } from "./components/DeviceBuildPanel";
import { PartsSection } from "./components/PartsSection";
import { PreferencesPanel } from "./components/PreferencesPanel";
import { PitchComparison } from "./components/PitchComparison";
import { TransportControls } from "./components/TransportControls";
import { ViewModeControls, type ViewMode } from "./components/ViewModeControls";
import {
  definition as definitionJson,
  demoDay,
  demoStandings,
  emptyDay,
  profiles,
  teamStandings
} from "./catalog";
import { describeRotation } from "./describeRotation";
import { useCalibration } from "./useCalibration";
import { useProject } from "./useProject";
import { useTransport } from "./useTransport";
import { useLogoAssets } from "./useLogoAssets";
import { useScoreboardData, type StudioDataMode } from "./useScoreboardData";
import { useDeviceBuild } from "./useDeviceBuild";
import { useBdfFonts } from "./useBdfFonts";
import { useFireworksEgg } from "./easterEgg";
import { createFireworksFrame } from "./fireworks";
import {
  BROADCAST_PREVIEW_MOMENTS,
  withBroadcastPreviewMoment,
  type BroadcastPreviewMoment
} from "./broadcastPreview";

const activeDateInNewYork = () => {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hourCycle: "h23",
    hour: "2-digit"
  }).formatToParts(now);
  const hour = Number(parts.find((part) => part.type === "hour")?.value ?? 12);
  const activeInstant = hour < 3 ? new Date(now.getTime() - 86_400_000) : now;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).format(activeInstant);
};

const STATUS_COPY: Record<GameStatus, string> = {
  pregame: "Pregame",
  in_progress: "Live",
  final: "Final",
  delayed: "Rain delay",
  postponed: "Postponed",
  suspended: "Suspended",
  canceled: "Canceled",
  unknown: "Status unavailable"
};

const localClockString = (date: Date, dateText: string) =>
  `${dateText}T${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}:00`;

export function App() {
  const {
    project,
    syncState,
    syncMessage,
    selectProfile,
    setProjectPreference,
    setDesignOverride,
    resetDesignOverrides,
    exportProject,
    importProject
  } = useProject();
  const calibration = useCalibration();
  const deviceBuild = useDeviceBuild(project.id, project.meta.version);
  const fontPack = useBdfFonts();
  const [dataMode, setDataMode] = useState<StudioDataMode>("live");
  const [replayDate, setReplayDate] = useState("2026-07-12");
  const [contentMode, setContentMode] = useState<ContentMode>("mixed");
  const [viewMode, setViewMode] = useState<ViewMode>("fit");
  const [workspaceView, setWorkspaceView] = useState<"everyday" | "setup">("everyday");
  const [zoom, setZoom] = useState(8);
  const [grid, setGrid] = useState(false);
  const [ledLook, setLedLook] = useState(true);
  const [calibrationOpen, setCalibrationOpen] = useState(false);
  const [broadcastMoment, setBroadcastMoment] = useState<BroadcastPreviewMoment>("live");
  const [now, setNow] = useState(() => new Date());
  const fireworks = useFireworksEgg();
  const transportBeforeFireworks = useRef<{ playing: boolean; pinned: boolean } | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const definition = definitionJson as unknown as DisplayDefinition;
  const requestedDate = dataMode === "demo"
    ? "2026-07-15"
    : dataMode === "replay"
      ? replayDate
      : activeDateInNewYork();
  const data = useScoreboardData(dataMode, requestedDate);
  const games = dataMode === "empty"
    ? emptyDay
    : data.snapshot?.games ?? (dataMode === "demo" ? demoDay : emptyDay);
  const standings = useMemo(() => {
    const mlbStandings = dataMode === "empty"
      ? []
      : data.snapshot?.standings ?? (dataMode === "demo" ? demoStandings : []);
    // Locally maintained team records use the same normalized model and
    // standings scene as the live division rows.
    return [...mlbStandings, ...teamStandings];
  }, [data.snapshot?.standings, dataMode]);
  const logoPack = useLogoAssets();
  const selectedProfile =
    profiles.find((profile) => profile.id === project.profileId) ?? profiles.find((profile) => profile.id === "ticker-128x32-p4")!;
  const fonts = fontPack.fonts;
  const rotationLocalMinute = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  const rotationUtcMinute = `${now.toISOString().slice(0, 16)}:00Z`;
  const rotationClock = useMemo(() => ({
    nowUtc: rotationUtcMinute,
    localTime: rotationLocalMinute
  }), [rotationLocalMinute, rotationUtcMinute]);

  const playlist = useMemo(() => {
    const items = buildPlaylist(
      games,
      {
        ...project.rotation,
        favorites: project.favorites,
        quietHours: project.quietHours
      },
      rotationClock,
      { standings, contentMode }
    );
    return items.filter((item): item is ScenePlaylistItem => item.kind !== "directive");
  }, [
    contentMode,
    rotationClock,
    project.favorites,
    project.quietHours,
    project.rotation,
    games,
    standings
  ]);
  const transport = useTransport(playlist);
  useEffect(() => {
    if (fireworks.isActive) {
      if (transportBeforeFireworks.current === null) {
        transportBeforeFireworks.current = { playing: transport.playing, pinned: transport.pinned };
        transport.setPlaying(false);
        transport.setPinned(true);
      }
      return;
    }
    const prior = transportBeforeFireworks.current;
    if (prior !== null) {
      transport.setPlaying(prior.playing);
      transport.setPinned(prior.pinned);
      transportBeforeFireworks.current = null;
    }
  }, [fireworks.isActive, transport.pinned, transport.playing, transport.setPinned, transport.setPlaying]);
  const currentItem = transport.current;
  const currentGame = currentItem?.kind === "game"
    ? games.find((game) => game.gameId === currentItem.gameId) ?? null
    : null;
  const currentStandings: StandingsState | null = currentItem?.kind === "standings"
    ? standings.find((snapshot) => snapshot.standingsId === currentItem.standingsId) ?? null
    : null;
  const currentStandingTeam: StandingTeamState | null = currentItem?.kind === "standings"
    ? currentStandings?.teams.find((row) => String(row.team.id) === currentItem.teamId) ?? null
    : null;
  const logoAssetKey = currentStandingTeam ? logoPack.keyFor(currentStandingTeam.team.id, 16) : null;
  const awayLogoAssetKey = currentGame ? logoPack.keyFor(currentGame.away.id, 16) : null;
  const homeLogoAssetKey = currentGame ? logoPack.keyFor(currentGame.home.id, 16) : null;
  const currentFavorite = transport.current?.favorite ?? false;
  const overrides = project.designOverrides as DesignOverrides;
  const rendererOverrides = project.designOverrides as RendererOverrides;
  const resolvedDesign = useMemo(
    () => resolveDesignSettings(definition, rendererOverrides),
    [definition, rendererOverrides]
  );
  const broadcastActive = resolvedDesign.layoutPreset === "broadcast";
  // A synthetic event must never reach a non-demo scene, even if the broadcast
  // layout stays selected after leaving Demo — enforced here at render, not
  // only by clearing state when Demo is left (see the effect below).
  const previewGame = useMemo(
    () => broadcastActive && dataMode === "demo" ? withBroadcastPreviewMoment(currentGame, broadcastMoment) : currentGame,
    [broadcastActive, broadcastMoment, currentGame, dataMode]
  );

  useEffect(() => {
    if (dataMode !== "demo") setBroadcastMoment("live");
  }, [dataMode]);

  const frame = useMemo(
    () =>
      renderScene({
        definition,
        scene: transport.current?.scene ?? "idle",
        game: previewGame,
        standings: currentStandings,
        standingTeam: currentStandingTeam,
        logoAssetKey,
        awayLogoAssetKey,
        homeLogoAssetKey,
        fonts,
        logical: selectedProfile.logical,
        overrides: rendererOverrides,
        favorites: project.favorites,
        favorite: currentFavorite,
        assets: logoPack.assets,
        idleMessage: data.snapshot
          ? "OFF DAY · NEXT FAVORITE MATCHUP COMING SOON"
          : dataMode === "empty"
            ? "OFF DAY · NEXT FAVORITE MATCHUP COMING SOON"
            : "CONNECTING TO LIVE BASEBALL",
        now: localClockString(now, requestedDate),
        elapsedMs: now.getTime(),
        transportHeld: transport.pinned,
        dataFreshness: data.snapshot?.source.freshness ?? (data.connection === "offline" ? "failed" : "loading"),
        dataError: data.snapshot?.source.error ?? null
      }),
    [
      currentFavorite,
      previewGame,
      currentStandingTeam,
      currentStandings,
      definition,
      fonts,
      awayLogoAssetKey,
      homeLogoAssetKey,
      logoAssetKey,
      logoPack.assets,
      now,
      data.connection,
      data.snapshot?.source.error,
      data.snapshot?.source.freshness,
      dataMode,
      project.favorites,
      rendererOverrides,
      selectedProfile.logical,
      transport.current?.scene,
      transport.pinned
    ]
  );
  const fireworksFrame = useMemo(
    () => createFireworksFrame(selectedProfile.logical.width, selectedProfile.logical.height, fireworks.elapsedMs),
    [fireworks.elapsedMs, selectedProfile.logical.height, selectedProfile.logical.width]
  );

  const matchup = currentGame
    ? `${currentGame.away.abbr} at ${currentGame.home.abbr}${
        currentGame.doubleheader ? ` · Game ${currentGame.gameNumber}` : ""
      }`
    : currentStandingTeam && currentStandings
      ? `${currentStandings.division.name} · #${currentStandingTeam.rank} ${currentStandingTeam.team.name}`
      : "Empty schedule";
  const sceneCopy = currentGame
    ? currentGame.statusDetail || STATUS_COPY[currentGame.status]
    : currentStandingTeam
      ? `${currentStandingTeam.wins}-${currentStandingTeam.losses}`
      : "Idle";
  const canvasLabel = currentGame
    ? `${matchup}. ${sceneCopy}. ${currentGame.away.score ?? "no score"} to ${
        currentGame.home.score ?? "no score"
      }.`
    : currentStandingTeam && currentStandings
      ? `${currentStandingTeam.team.name}, rank ${currentStandingTeam.rank} in the ${currentStandings.division.name}, ${currentStandingTeam.wins} wins and ${currentStandingTeam.losses} losses.`
      : "No games today. Idle scoreboard scene.";
  const currentContentKey = transport.current?.kind === "game"
    ? transport.current.gameId
    : transport.current?.kind === "standings"
      ? `${transport.current.standingsId}:${transport.current.teamId}`
      : "idle";
  const frameKey = `${currentContentKey}:${transport.current?.scene ?? "idle"}:${
    resolvedDesign.layoutPreset
  }:${broadcastMoment}:${selectedProfile.id}`;
  const visibleFrame = fireworks.isActive ? fireworksFrame : frame;
  const visibleFrameKey = fireworks.isActive ? `fireworks:${Math.floor(fireworks.elapsedMs / 100)}` : frameKey;
  const visibleCanvasLabel = fireworks.isActive
    ? `Fireworks celebration. ${fireworks.remainingSec} seconds remaining.`
    : canvasLabel;
  const handleNextButton = () => {
    transport.next();
    fireworks.press("next");
  };
  const handleHoldButton = (pinned: boolean) => {
    transport.setPinned(pinned);
    fireworks.press("hold");
  };
  const freshness = dataMode === "empty"
    ? "fresh"
    : data.connection === "connected"
      ? data.snapshot?.source.freshness ?? "stale"
      : data.snapshot
        ? "stale"
        : data.connection === "offline" ? "failed" : "stale";
  const dataBadge = dataMode === "empty"
    ? "Empty-day test · offline"
    : dataMode === "demo"
      ? "Demo fixtures · deterministic"
      : data.snapshot
        ? `${dataMode === "live" ? "Live MLB" : "Replay"} · ${freshness} · ${data.snapshot.source.refreshSec || "fixed"}s`
        : `${dataMode === "live" ? "Live MLB" : "Replay"} · ${data.connection}`;
  const divisionOptions = useMemo(
    () =>
      Array.from(
        new Set([
          ...(project.rotation.standings?.divisions ?? []),
          ...standings.map((snapshot) => snapshot.division.name)
        ])
      ),
    [project.rotation.standings?.divisions, standings]
  );
  const rotationDescription = describeRotation(project, {
    playlistLength: playlist.length,
    standingsAvailable: standings.length > 0
  });
  const fetchedUtc = data.snapshot?.source.fetchedUtc ?? null;
  const lastUpdateLabel = useMemo(() => {
    if (dataMode === "empty") return "Offline test";
    if (!fetchedUtc) return data.connection === "offline" ? "No successful update yet" : "Connecting…";
    const secondsAgo = Math.max(0, Math.round((now.getTime() - new Date(fetchedUtc).getTime()) / 1000));
    if (secondsAgo < 60) return `${secondsAgo}s ago`;
    if (secondsAgo < 3600) return `${Math.floor(secondsAgo / 60)}m ago`;
    return `${Math.floor(secondsAgo / 3600)}h ago`;
  }, [dataMode, fetchedUtc, data.connection, now]);
  const previewBroadcast = () => {
    setDataMode("demo");
    setContentMode("games");
    setBroadcastMoment("live");
    setDesignOverride(["layoutPreset"], "broadcast");
    transport.jump(0);
  };
  const previewClassic = () => {
    setBroadcastMoment("live");
    setDesignOverride(["layoutPreset"], "classic");
  };
  const previewMoment = (moment: BroadcastPreviewMoment) => {
    setDataMode("demo");
    setContentMode("games");
    setBroadcastMoment(moment);
    transport.jump(0);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden="true" />
          <div className="brand-copy">
            <strong>Scoreboard Studio</strong>
            <span>Pixelboard's display lab · games, standings &amp; device proof</span>
          </div>
        </div>
        <div className="topbar-controls">
          <div className="segmented" role="group" aria-label="Workspace view">
            <button
              type="button"
              aria-pressed={workspaceView === "everyday"}
              onClick={() => setWorkspaceView("everyday")}
            >
              Everyday
            </button>
            <button
              type="button"
              aria-pressed={workspaceView === "setup"}
              onClick={() => setWorkspaceView("setup")}
            >
              Setup
            </button>
          </div>
          <span className={`demo-badge data-${freshness}`}>
            {dataBadge}
          </span>
          <label className="fixture-select">
            <span>Data</span>
            <select value={dataMode} onChange={(event) => setDataMode(event.target.value as StudioDataMode)}>
              <option value="live">Live MLB · today</option>
              <option value="demo">Demo day · all edge cases</option>
              <option value="replay">Historical replay</option>
              <option value="empty">Empty schedule · idle test</option>
            </select>
          </label>
          {dataMode === "replay" ? (
            <label className="replay-date">
              <span>Replay date</span>
              <input type="date" value={replayDate} max={activeDateInNewYork()} onChange={(event) => setReplayDate(event.target.value)} />
            </label>
          ) : null}
          <label className="fixture-select content-select">
            <span>Rotation</span>
            <select value={contentMode} onChange={(event) => setContentMode(event.target.value as ContentMode)}>
              <option value="mixed">Games + standings mix</option>
              <option value="games">Games only</option>
              <option value="standings">Standings only</option>
            </select>
          </label>
          {dataMode !== "empty" ? (
            <button type="button" className="refresh-data" onClick={() => void data.refresh()}>
              Refresh
            </button>
          ) : null}
          {workspaceView === "setup" ? (
            <a className="parts-shortcut" href="#parts">
              Parts &amp; build ↓
            </a>
          ) : null}
        </div>
      </header>

      <main className="workspace">
        <div className="sidebar-stack">
          {workspaceView === "setup" ? (
            <ProfilePanel
              profiles={profiles}
              selected={selectedProfile}
              definitionLogical={definition.targetLogical}
              calibrated={calibration.calibrated}
              onSelect={selectProfile}
              onCalibrate={() => setCalibrationOpen(true)}
            />
          ) : null}

          <ProjectPanel
            name={project.name}
            version={project.meta.version}
            state={syncState}
            message={syncMessage}
            onExport={exportProject}
            onImport={importProject}
          />

          <PreferencesPanel
            project={project}
            onChange={setProjectPreference}
            divisionOptions={divisionOptions}
          />

          {workspaceView === "setup" ? (
            <DeviceBuildPanel
              syncReady={syncState === "saved"}
              action={deviceBuild.action}
              report={deviceBuild.report}
              build={deviceBuild.build}
              error={deviceBuild.error}
              logs={deviceBuild.logs}
              onValidate={deviceBuild.validate}
              onBuild={deviceBuild.buildArtifact}
            />
          ) : null}

          <section className="panel-card" aria-labelledby="fixture-contract-title">
            <div className="panel-heading compact">
              <div>
                <span className="eyebrow">Experience contract</span>
                <h2 id="fixture-contract-title">Pixelboard's rotation</h2>
              </div>
              <span className={freshness === "fresh" ? "status-pill good" : "status-pill warning"}>
                {freshness === "fresh" ? "Ready" : freshness}
              </span>
            </div>
            <dl className="profile-metrics">
              <div>
                <dt>Games</dt>
                <dd>{games.length}</dd>
              </div>
              <div>
                <dt>Standings</dt>
                <dd>{standings.length ? `${standings.length} division${standings.length === 1 ? "" : "s"} loaded` : "Unavailable"}</dd>
              </div>
              <div>
                <dt>Favorites</dt>
                <dd>{project.favorites.join(" + ")}</dd>
              </div>
              <div>
                <dt>Game feed</dt>
                <dd>{dataMode === "empty" ? "Offline test" : `${data.snapshot?.source.provider ?? "Connecting"} · ${data.connection}`}</dd>
              </div>
              <div>
                <dt>Last update</dt>
                <dd>{lastUpdateLabel}</dd>
              </div>
            </dl>
            <p className="inline-notice">{rotationDescription}</p>
            {data.snapshot?.source.error ? (
              <p className="inline-notice warning" role="status">
                The live source is degraded. The last known data remains visible and is marked {data.snapshot.source.freshness}.
              </p>
            ) : null}
            {fontPack.status === "error" ? (
              <p className="inline-notice warning" role="alert">
                Pixel fonts could not load. Refresh the studio before approving a device build.
              </p>
            ) : null}
            <p className={logoPack.status === "invalid" ? "inline-notice warning" : "inline-notice"}>
              {logoPack.status === "available"
                ? `Optional logo pack active with ${logoPack.loadedCount} verified pixel sprites.`
                : "Team-color monogram badges are active. A locally configured logo pack can replace them without changing the layout."}
            </p>
          </section>
        </div>

        <div className="preview-column">
          <section className="preview-card" aria-labelledby="preview-title">
            <header className="preview-header">
              <div className="preview-title">
                <span className="eyebrow">Logical output</span>
                <h1 id="preview-title">{fireworks.isActive ? "Fireworks finale" : matchup}</h1>
                <div className="preview-meta">
                  <span>{fireworks.isActive ? "Secret celebration" : sceneCopy}</span>
                  <span>{transport.current?.kind ?? "idle"}</span>
                  <span>{transport.current?.scene ?? "idle"}</span>
                  <span>
                    {selectedProfile.logical.width} × {selectedProfile.logical.height}
                  </span>
                  {currentFavorite ? <span className="favorite-tag">Favorite priority</span> : null}
                </div>
              </div>
              <ViewModeControls
                mode={viewMode}
                zoom={zoom}
                grid={grid}
                ledLook={ledLook}
                calibrated={calibration.calibrated}
                onModeChange={setViewMode}
                onZoomChange={setZoom}
                onGridChange={setGrid}
                onLedLookChange={setLedLook}
              />
            </header>

            <div className={broadcastActive ? "broadcast-preview-bar is-active" : "broadcast-preview-bar"}>
              <div className="broadcast-preview-copy">
                <span className="v2-badge">V2</span>
                <div>
                  <strong>Broadcast preview</strong>
                  <span>
                    {broadcastActive
                      ? "Live score blocks, base state, count, outs, pitcher, batter and pitch strip"
                      : "Try the new broadcast-inspired screen without removing Classic"}
                  </span>
                </div>
              </div>
              <div className="layout-preview-actions" role="group" aria-label="Preview scoreboard layout">
                <button type="button" aria-pressed={!broadcastActive} onClick={previewClassic}>
                  Classic
                </button>
                <button type="button" className="broadcast-button" aria-pressed={broadcastActive} onClick={previewBroadcast}>
                  Preview Broadcast V2
                </button>
              </div>
            </div>

            {broadcastActive ? (
              <div className="event-preview-bar">
                <div className="event-preview-copy">
                  <strong>Event preview</strong>
                  <span>Browser simulation only · nothing is sent to the live feed or Pi</span>
                </div>
                <div className="event-preview-actions" role="group" aria-label="Preview a game event">
                  {BROADCAST_PREVIEW_MOMENTS.map((moment) => (
                    <button
                      key={moment.id}
                      type="button"
                      className={moment.id === "homeRun" || moment.id === "grandSlam" ? "celebration-event" : undefined}
                      aria-pressed={broadcastMoment === moment.id}
                      onClick={() => previewMoment(moment.id)}
                    >
                      {moment.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <EmulatorCanvas
              frame={visibleFrame}
              profile={selectedProfile}
              mode={viewMode}
              zoom={zoom}
              pxPerMm={calibration.pxPerMm}
              calibrated={calibration.calibrated}
              grid={grid}
              ledLook={ledLook}
              transition={resolvedDesign.transition}
              frameKey={visibleFrameKey}
              label={visibleCanvasLabel}
            />

            {transport.timingWarning ? (
              <div className="timing-warning" role="status">
                <span>The tab was hidden long enough to affect rotation timing. The current screen was preserved.</span>
                <button type="button" onClick={transport.dismissTimingWarning}>
                  Dismiss
                </button>
              </div>
            ) : null}
          </section>

          {workspaceView === "setup" ? (
            <PitchComparison
              profiles={profiles}
              selectedProfileId={selectedProfile.id}
              frame={frame}
              onSelect={selectProfile}
            />
          ) : null}

          <p className="inline-notice" role="note">
            Preview controls — NEXT, WATCH LIVE and jump drive this browser preview only. Nothing is
            sent to a device; saving the project does not deploy it.
          </p>

          <TransportControls
            playlist={playlist}
            games={games as NormalizedGameState[]}
            standings={standings as StandingsState[]}
            index={transport.index}
            playing={transport.playing}
            pinned={transport.pinned}
            progress={transport.progress}
            remainingSec={transport.remainingSec}
            holdEndingSec={transport.holdEndingSec}
            fireworksActive={fireworks.isActive}
            fireworksProgress={fireworks.remainingSec}
            onPlayingChange={transport.setPlaying}
            onPinnedChange={handleHoldButton}
            onStep={transport.step}
            onNext={handleNextButton}
            onJump={transport.jump}
          />
        </div>

        {workspaceView === "setup" ? (
          <DesignPanel
            parameters={definition.parameters as unknown as ParameterBlock}
            overrides={overrides}
            onChange={setDesignOverride}
            onReset={resetDesignOverrides}
          />
        ) : null}
      </main>

      {workspaceView === "setup" ? <PartsSection /> : null}

      <CalibrationPanel
        open={calibrationOpen}
        current={calibration.record}
        onClose={() => setCalibrationOpen(false)}
        onSave={calibration.save}
        onClear={calibration.clear}
      />
    </div>
  );
}
