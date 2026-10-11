from __future__ import annotations

import inspect
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import monotonic
from typing import Any, Callable

LOGGER = logging.getLogger("scoreboard-status")
MAX_JSON_BYTES = 64 * 1024

DASHBOARD_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pixelboard Scoreboard — Control & Settings</title>
<style>
:root {
  --bg: #0b122a;
  --card-bg: #141f45;
  --card-border: #22326b;
  --text: #e8edff;
  --text-muted: #9fb0ff;
  --primary: #3fd67a;
  --primary-hover: #32ba68;
  --primary-text: #04220f;
  --secondary: #242f5c;
  --secondary-hover: #2f3e7a;
  --accent: #4e85ff;
  --accent-hover: #3b74f0;
  --danger: #5a2130;
  --danger-hover: #752a3e;
  --danger-text: #ffd9df;
  --amber: #fca311;
  --amber-dark: #b87304;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font: 15px/1.5 system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  padding: 1.5rem 1rem 3rem;
  max-width: 620px;
  margin: 0 auto;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.25rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--card-border);
}
h1 { font-size: 1.25rem; font-weight: 700; color: #fff; letter-spacing: -0.01em; }
.subtitle { font-size: 0.8rem; color: var(--text-muted); }
.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--secondary);
  color: var(--text-muted);
}
.badge.online { background: #0c361e; color: #57ec93; }
.badge.quiet { background: #3b2d13; color: var(--amber); }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.2rem;
  margin-bottom: 1rem;
  box-shadow: 0 4px 16px rgba(0,0,0,0.25);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.card-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: #fff;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.75rem 1rem;
  margin: 0.35rem 0;
  font-size: 0.95rem;
  font-weight: 600;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.05s ease;
}
button:active { transform: scale(0.985); }
.btn-primary { background: var(--primary); color: var(--primary-text); }
.btn-primary:hover { background: var(--primary-hover); }
.btn-secondary { background: var(--secondary); color: var(--text); border: 1px solid var(--card-border); }
.btn-secondary:hover { background: var(--secondary-hover); }
.btn-accent { background: var(--accent); color: #fff; }
.btn-accent:hover { background: var(--accent-hover); }
.btn-danger { background: var(--danger); color: var(--danger-text); }
.btn-danger:hover { background: var(--danger-hover); }
.btn-amber { background: var(--amber); color: #231600; }
.btn-amber:hover { background: var(--amber-dark); }
.btn-amber.active { outline: 2px solid #fff; }

.controls-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.6rem;
}

.form-group {
  margin-bottom: 1rem;
}
.form-label {
  display: flex;
  justify-content: space-between;
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-bottom: 0.35rem;
  font-weight: 500;
}
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
input[type="time"], input[type="date"], select {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  color: #fff;
  padding: 0.6rem 0.75rem;
  font-size: 0.95rem;
}
input[type="range"] {
  width: 100%;
  accent-color: var(--primary);
  cursor: pointer;
  margin: 0.35rem 0;
}
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  font-size: 0.95rem;
  user-select: none;
}
.checkbox-label input[type="checkbox"] {
  width: 1.15rem;
  height: 1.15rem;
  accent-color: var(--primary);
}

.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(52px, 1fr));
  gap: 0.4rem;
  margin-top: 0.6rem;
  max-height: 190px;
  overflow-y: auto;
  padding: 0.2rem;
}
.team-chip {
  padding: 0.4rem 0.2rem;
  font-size: 0.8rem;
  font-weight: 700;
  text-align: center;
  border-radius: 6px;
  background: var(--secondary);
  color: var(--text-muted);
  border: 1px solid var(--card-border);
  cursor: pointer;
  transition: all 0.1s ease;
  user-select: none;
}
.team-chip.active {
  background: var(--accent);
  color: #fff;
  border-color: #88afff;
  box-shadow: 0 0 6px rgba(78,133,255,0.4);
}

.toast {
  min-height: 1.4em;
  font-size: 0.85rem;
  margin-top: 0.5rem;
  color: var(--text-muted);
  text-align: center;
}
.toast.success { color: var(--primary); font-weight: 600; }
.toast.error { color: #ff8b9e; font-weight: 600; }

.collapsible-header {
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.collapsible-header:hover .card-title { color: var(--accent); }
.collapsible-content { margin-top: 1rem; }
.hidden { display: none !important; }

.commit-list {
  margin-top: 0.75rem;
  background: var(--bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 0.6rem 0.8rem;
  font-family: monospace;
  font-size: 0.8rem;
  max-height: 140px;
  overflow-y: auto;
}
.commit-item {
  padding: 0.25rem 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  color: #cad6ff;
}
.commit-item:last-child { border-bottom: none; }
</style>
</head>
<body>

<header>
  <div>
    <h1>Pixelboard Scoreboard</h1>
    <div class="subtitle">128x32 P4 Bedroom Ticker</div>
  </div>
  <div id="live-badge" class="badge online">
    <div class="badge-dot"></div>
    <span id="badge-text">Online</span>
  </div>
</header>

<!-- Live Scoreboard Display Preview -->
<div class="card" style="text-align: center;">
  <div class="card-header" style="justify-content: space-between; align-items: center;">
    <div class="card-title">🖥️ Live Scoreboard Display</div>
    <div class="subtitle" id="live-scene-tag">Connecting…</div>
  </div>

  <div style="margin: 0.5rem auto; max-width: 512px; background: #000; padding: 6px; border-radius: 10px; border: 2px solid #233152; box-shadow: 0 4px 25px rgba(0,0,0,0.7);">
    <img id="screen-preview" src="/api/screen.png" alt="Scoreboard Display" style="display: block; width: 100%; aspect-ratio: 4 / 1; image-rendering: pixelated; border-radius: 4px;">
  </div>

  <div id="live-info-banner" style="margin-top: 0.8rem; padding: 0.75rem 1rem; background: var(--bg); border: 1px solid var(--card-border); border-radius: 8px; text-align: left;">
    <div id="live-primary-text" style="font-weight: 700; color: #fff; font-size: 0.95rem;">Loading scoreboard feed…</div>
    <div id="live-secondary-text" style="color: var(--text-muted); font-size: 0.84rem; margin-top: 0.25rem;">Waiting for device response</div>
  </div>
</div>

<div class="card">
  <div class="card-title">Pixelboard Arcade</div>
  <p id="arcade-status" style="margin-top:0.6rem">Scoreboard mode</p>
  <p style="font-size:0.85rem;color:var(--text-muted)">Remote: Press Select once for the main menu, then choose Arcade Games. D-pad chooses, A plays/swings, Start pauses, X restarts, B returns to the game menu. Select returns to the main menu. Big League: D-pad aims, A swings or sends runners; when pitching, L/R picks the pitch and A twice throws it. Soccer: D-pad runs, A kicks (or tackles without the ball). Rainbow Unicorn: A toots, B throws a bomb, R horn-dashes with 1–2 headbands; A confirms the SIX SEVEN dance. Start then B leaves a game.</p>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Past Scores</div></div>
  <p class="subtitle">Final MLB and NFL scores for one date. Returns to live after 10 minutes.</p>
  <label class="form-label" for="history-date">Game date</label>
  <input id="history-date" type="date" min="1900-01-01" class="form-input">
  <div class="controls-grid">
    <button onclick="setHistory(false)">Show Final Scores</button>
    <button class="btn-secondary" onclick="setHistory(true)">Back to Live</button>
  </div>
  <p id="history-status" class="subtitle">Uses the household PIN in Preferences below.</p>
</div>

<!-- Quick Navigation Controls -->
<div class="card">
  <div class="card-header">
    <div class="card-title">Live Controls</div>
    <div class="subtitle" id="uptime-text">--</div>
  </div>
  <div class="controls-grid">
    <button class="btn-secondary" onclick="control('home')">🏠 Home Clock</button>
    <button class="btn-secondary" onclick="control('next')">⏩ Next Screen</button>
    <button id="btn-hold" class="btn-secondary" onclick="control('hold')">⏸️ Hold Game</button>
  </div>
  <p id="control-status" class="subtitle">Uses the household PIN in Scoreboard Settings below.</p>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Team Schedule</div></div>
  <p id="team-record" style="font-size:2rem;font-weight:bold">0–0</p>
  <p class="subtitle">Team results and ranking are maintained locally.</p>
  <h3>Next games</h3><div id="team-games"></div>
  <h3>Next practices</h3><div id="team-practices"></div>
  <p class="subtitle">Games stay here through game day. Each doubleheader game has its own result.</p>
  <label class="form-label" for="team-rank">Ranking</label>
  <input id="team-rank" type="number" min="1" max="99" value="1">
  <label class="form-label" for="team-event">Game result</label>
  <select id="team-event" onchange="selectTeamResult()"></select>
  <select id="team-result"><option value="">Not recorded</option><option value="win">Win</option><option value="loss">Loss</option><option value="tie">Tie</option></select>
  <p class="subtitle">Enter the Household PIN in Scoreboard Settings below before saving.</p>
  <div class="controls-grid"><button onclick="saveTeam()">Save Team</button><button class="btn-secondary" onclick="showTeam()">Show on Scoreboard</button></div>
  <p id="team-feedback" role="status"></p>
  <p class="subtitle">Remote: R opens Team. A advances; B holds the card.</p>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Pixelboard Arcade</div></div>
  <p id="arcade-happy" class="subtitle">Loading…</p>
  <p id="arcade-gems-total" style="font-size:1.5rem;font-weight:bold"></p>
  <div id="arcade-scores"></div>
  <label class="form-label" for="arcade-gems">Gems to add to the jar (negative takes away)</label>
  <input id="arcade-gems" type="number" min="-10000" max="10000" value="25">
  <p class="subtitle">Enter the Household PIN in Scoreboard Settings below first.</p>
  <div class="controls-grid"><button onclick="arcadeAction('gems')">Add Gems</button><button class="btn-secondary" onclick="arcadeAction('resetScores')">Reset High Scores</button></div>
  <p id="arcade-feedback" role="status"></p>
  <p class="subtitle">One shared gem jar and style for the household. Games are closed during quiet hours. Happy Hour: triple gems for 10 minutes every 3 hours.</p>
</div>

<!-- Preferences & Settings -->
<div class="card">
  <div class="card-header">
    <div class="card-title">Scoreboard Settings</div>
  </div>

  <form id="settings-form" onsubmit="saveSettings(event); return false;">
    <!-- Quiet Hours -->
    <div class="form-group">
      <label class="checkbox-label" style="margin-bottom: 0.6rem;">
        <input type="checkbox" id="qh-enabled">
        <span><strong>Enable Quiet Hours</strong></span>
      </label>
      <div class="form-row">
        <div>
          <div class="form-label"><span>Start Time</span></div>
          <input type="time" id="qh-start" value="21:00" required>
        </div>
        <div>
          <div class="form-label"><span>End Time</span></div>
          <input type="time" id="qh-end" value="06:00" required>
        </div>
      </div>
      <div style="margin-top: 0.6rem;">
        <div class="form-label"><span>Quiet Hours Mode</span></div>
        <select id="qh-behavior">
          <option value="dim">Dim Display (Keep showing scores at low brightness)</option>
          <option value="sleep">Sleep (Turn display completely off)</option>
        </select>
      </div>
    </div>

    <hr style="border: 0; border-top: 1px solid var(--card-border); margin: 1rem 0;">

    <div style="margin-bottom: 1rem;">
      <label class="form-label" for="display-layout">Scoreboard layout</label>
      <select id="display-layout">
        <option value="classic">Original · stacked teams with logos</option>
        <option value="broadcastRows">Preview 3 · horizontal team rows & ticker</option>
        <option value="broadcastLogos">Broadcast · logos side by side & ticker</option>
      </select>
      <p class="subtitle">Choose a design, then Save Preferences. Live data stays the same.</p>
    </div>
    <div style="margin-bottom: 1rem;">
      <label class="form-label" for="preferences-pin">Household PIN</label>
      <input id="preferences-pin" type="password" inputmode="numeric" maxlength="6" autocomplete="off" placeholder="6-digit PIN">
      <p class="subtitle">Use the household PIN for messages, settings, and software updates.</p>
    </div>

    <div class="form-group">
      <label class="form-label" for="wake-duration">Temporary wake duration (seconds)</label>
      <input id="wake-duration" type="number" min="10" max="600" value="60">
      <p class="subtitle">During sleep hours, any controller button wakes the screen temporarily. Press Select once for the main menu and settings.</p>
    </div>
    <div class="form-group">
      <label><input type="checkbox" id="nfl-enabled"> Include NFL scores</label>
      <label class="form-label" for="nfl-dwell">NFL seconds per game</label>
      <input id="nfl-dwell" type="number" min="3" max="60" value="8">
      <p class="subtitle">Press Select once on the remote to pick NFL games, favorite teams, filters, and layout. NFL joins the MLB and Team rotation.</p>
    </div>
    <!-- Brightness -->
    <div class="form-group">
      <div class="form-label">
        <span>Normal Brightness</span>
        <span id="normal-val">35%</span>
      </div>
      <input type="range" id="br-normal" min="1" max="100" value="35" oninput="document.getElementById('normal-val').textContent = this.value + '%'">

      <div class="form-label" style="margin-top: 0.6rem;">
        <span>Quiet Hours Dim Brightness</span>
        <span id="dim-val">10%</span>
      </div>
      <input type="range" id="br-dim" min="1" max="100" value="10" oninput="document.getElementById('dim-val').textContent = this.value + '%'">
    </div>

    <hr style="border: 0; border-top: 1px solid var(--card-border); margin: 1rem 0;">

    <!-- Favorite Teams -->
    <div class="form-group">
      <div class="form-label">
        <span>Favorite Teams (Highlighted in rotation)</span>
        <span id="fav-count">0 selected</span>
      </div>
      <div id="teams-container" class="teams-grid"></div>
    </div>

    <button type="submit" class="btn-primary" id="btn-save">Save Preferences</button>
    <div id="save-toast" class="toast"></div>
  </form>
</div>

<!-- Software Updates -->
<div class="card">
  <div class="card-header">
    <div class="card-title">Software Updates</div>
    <div class="subtitle" id="git-commit-tag">Commit: --</div>
  </div>
  <p style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.8rem;">
    Pull new code directly from the GitHub repository and restart the scoreboard service automatically. Use the same six-digit household PIN as messages and settings.
  </p>
  <button class="btn-secondary" id="btn-check-updates" onclick="checkUpdates()">🔍 Check for Updates</button>
  <div id="update-banner" class="hidden" style="margin-top: 0.75rem;">
    <div id="update-msg" style="font-size: 0.9rem; font-weight: 600; margin-bottom: 0.4rem;"></div>
    <div id="commit-list" class="commit-list hidden"></div>
    <button id="btn-apply-update" class="btn-primary hidden" onclick="applyUpdate()" style="margin-top: 0.75rem;">
      🚀 Update from GitHub Now
    </button>
  </div>
  <div id="update-toast" class="toast"></div>
</div>

<!-- Stadium Announcement & Custom Message Control -->
<div class="card">
  <div class="card-header collapsible-header" onclick="toggleRevealCard()">
    <div>
      <div class="card-title">📢 Stadium Announcements & Custom Messages</div>
      <div class="subtitle">Broadcast live ticker messages or arm a celebration surprise</div>
    </div>
    <div class="subtitle" id="reveal-toggle-icon">▼ Click to Expand</div>
  </div>
  <div id="reveal-content" class="collapsible-content">
    <div style="margin-bottom: 0.75rem;">
      <span class="label-text">Quick Presets:</span>
      <div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.35rem;">
        <button type="button" class="btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;" onclick="applyPreset('birthday')">🎂 Birthday Celebration</button>
        <button type="button" class="btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;" onclick="applyPreset('gameday')">⚾ Game Day!</button>
        <button type="button" class="btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;" onclick="applyPreset('morning')">☀️ Good Morning</button>
        <button type="button" class="btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.78rem;" onclick="applyPreset('grandslam')">🏆 Grand Slam!</button>
      </div>
    </div>

    <div style="margin-bottom: 0.75rem;">
      <label class="label-text" for="custom-msg-lines">Message Lines (1 per screen):</label>
      <textarea id="custom-msg-lines" rows="3" style="width: 100%; box-sizing: border-box; background: var(--bg); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem; font-family: monospace; font-size: 0.88rem; resize: vertical;" placeholder="WELCOME&#10;HAPPY CELEBRATION!"></textarea>
    </div>

    <div style="display: flex; gap: 1.25rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.9rem;">
      <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.85rem; color: var(--text);">
        <input type="checkbox" id="msg-fireworks" checked style="accent-color: var(--accent); width: 18px; height: 18px;">
        Include Fireworks Finale
      </label>
      <div style="display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; color: var(--text);">
        <span>Seconds per line:</span>
        <input type="number" id="msg-dwell" min="1" max="20" value="4" style="width: 55px; background: var(--bg); color: var(--text); border: 1px solid var(--card-border); border-radius: 6px; padding: 0.3rem 0.4rem; text-align: center;">
      </div>
    </div>

    <div class="form-group" style="margin-bottom: 0.9rem;">
      <label class="form-label" for="broadcast-pin">Household PIN for messages & preferences</label>
      <input type="password" id="broadcast-pin" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="off" placeholder="6-digit PIN" style="width: 100%; background: var(--bg); color: var(--text); border: 1px solid var(--card-border); border-radius: 8px; padding: 0.6rem 0.75rem; font-size: 0.95rem;">
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; margin-top: 0.5rem;">
        <label class="checkbox-label" style="font-size: 0.82rem;">
          <input type="checkbox" id="remember-broadcast-pin" checked onchange="if (!this.checked) localStorage.removeItem('scoreboard-broadcast-pin')">
          Remember on this browser
        </label>
        <button type="button" class="btn-secondary" style="font-size: 0.8rem;" onclick="forgetBroadcastPin()">Forget PIN</button>
      </div>
    </div>

    <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
      <button class="btn-primary" onclick="broadcastCustomMessage(false)">📢 Broadcast to Scoreboard Now</button>
      <button class="btn-secondary" onclick="broadcastCustomMessage(true)">🎁 Arm as Boot Surprise</button>
      <button class="btn-secondary" onclick="broadcastCustomMessage(false, true)">Load reveal &amp; wait for controller</button>
      <button class="btn-danger" onclick="act('disarm')">Cancel / Disarm</button>
    </div>

    <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--card-border); padding-top: 0.6rem; margin-top: 0.5rem;">
      <span>Reveal status: <strong id="state" style="color: #fff;">loading…</strong></span>
      <button class="btn-secondary" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="act('trigger')">Play reveal now</button>
    </div>
    <div id="message" class="toast"></div>
  </div>
</div>

<script>
let allTeamsList = [];
let selectedFavorites = new Set();
let isUpdating = false;
let configVersion = null;
let nflSettings = {};

function dashboardHouseholdPin() {
  const remembered = localStorage.getItem('scoreboard-broadcast-pin') || '';
  const broadcastInput = document.getElementById('broadcast-pin');
  const preferencesInput = document.getElementById('preferences-pin');
  let pin = (preferencesInput && preferencesInput.value.trim()) ||
    (broadcastInput && broadcastInput.value.trim()) || remembered;
  if (!/^[0-9]{6}$/.test(pin)) {
    pin = window.prompt('Enter the 6-digit household PIN used for messages and settings') || '';
    pin = pin.trim();
  }
  if (/^[0-9]{6}$/.test(pin)) {
    if (broadcastInput) broadcastInput.value = pin;
    if (preferencesInput) preferencesInput.value = pin;
  }
  return pin;
}

async function adminFetch(path, options = {}) {
  const pin = dashboardHouseholdPin();
  if (!/^[0-9]{6}$/.test(pin)) throw new Error('Enter the 6-digit household PIN');
  const headers = new Headers(options.headers || {});
  headers.set('X-Scoreboard-Broadcast-Pin', pin);
  const response = await fetch(path, {...options, headers});
  if (response.ok && document.getElementById('remember-broadcast-pin')?.checked) {
    localStorage.setItem('scoreboard-broadcast-pin', pin);
  }
  if (response.status === 401 || response.status === 403) forgetBroadcastPin();
  return response;
}

function forgetBroadcastPin() {
  localStorage.removeItem('scoreboard-broadcast-pin');
  document.getElementById('broadcast-pin').value = '';
  document.getElementById('preferences-pin').value = '';
}

async function broadcastFetch(path, options = {}) {
  const input = document.getElementById((path === '/api/config' || path === '/api/history' || path.startsWith('/api/control/') || path.startsWith('/api/team') || path === '/api/arcade') ? 'preferences-pin' : 'broadcast-pin');
  const pin = input.value.trim();
  if (!/^[0-9]{6}$/.test(pin)) throw new Error('Enter the 6-digit household PIN');
  const headers = new Headers(options.headers || {});
  headers.set('X-Scoreboard-Broadcast-Pin', pin);
  const response = await fetch(path, {...options, headers});
  if (response.ok && document.getElementById('remember-broadcast-pin').checked) {
    localStorage.setItem('scoreboard-broadcast-pin', pin);
  } else if (response.status === 401) {
    forgetBroadcastPin();
  }
  return response;
}

function arcadeDuration(seconds) {
  return seconds >= 3600 ? Math.floor(seconds / 3600) + 'h ' + Math.floor(seconds % 3600 / 60) + 'm' : Math.max(1, Math.floor(seconds / 60)) + ' min';
}
function renderArcade(data) {
  const happy = data.happyHour || {};
  document.getElementById('arcade-happy').textContent = (data.available ? 'Open' : 'Closed for quiet hours') + ' · ' +
    (happy.active ? 'Happy Hour now, ' + arcadeDuration(happy.seconds) + ' left' : happy.seconds != null ? 'Next Happy Hour in ' + arcadeDuration(happy.seconds) : 'No Happy Hour soon');
  document.getElementById('arcade-gems-total').textContent = data.gems + ' gems';
  document.getElementById('arcade-scores').textContent = 'High scores: Neon Rider ' + data.best.rider + ' · Snake ' + data.best.snake +
    ' · Baseball ' + data.best.baseball + ' · Big League runs ' + (data.best.bigleague || 0) +
    ' · Soccer goals ' + (data.best.soccer || 0) + ' · Rainbow Unicorn stars ' + (data.best.unicorn || 0) +
    ' · Pong wins ' + data.pongWins;
}
async function loadArcade() {
  try {
    const response = await fetch('/api/arcade', {cache:'no-store'});
    renderArcade(await response.json());
  } catch (error) { document.getElementById('arcade-feedback').textContent = error.message; }
}
async function arcadeAction(action) {
  const feedback = document.getElementById('arcade-feedback');
  try {
    if (action === 'resetScores' && !window.confirm('Clear every high score?')) return;
    const payload = {action, amount: Number(document.getElementById('arcade-gems').value)};
    const response = await broadcastFetch('/api/arcade', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Arcade update failed');
    renderArcade(data); feedback.textContent = 'Saved';
  } catch (error) { feedback.textContent = error.message; }
}

let teamData = null;
async function loadTeam() {
  try {
    const response = await fetch('/api/team', {cache:'no-store'});
    if (!response.ok) throw new Error('Cannot load Team');
    teamData = await response.json();
    document.getElementById('team-record').textContent = teamData.wins + '–' + teamData.losses + (teamData.ties ? '–' + teamData.ties : '') + ' · #' + teamData.rank;
    document.getElementById('team-rank').value = teamData.rank;
    const games = document.getElementById('team-games'); games.replaceChildren();
    const formatTime = value => new Date(value).toLocaleTimeString('en-US', {timeZone:'America/New_York',hour:'numeric',minute:'2-digit'});
    for (const group of teamData.groups) {
      const line = document.createElement('p');
      line.textContent = group.date + (group.away ? ' @ ' : ' vs ') + group.opponent + ': ' + group.games.map(g => formatTime(g.startUtc) + (g.endUtc ? '–' + formatTime(g.endUtc) : '')).join(' / ');
      games.appendChild(line);
    }
    if (!teamData.groups.length) games.textContent = teamData.fetchedUtc ? 'No upcoming games listed.' : 'Schedule loading…';
    const practices = document.getElementById('team-practices'); practices.replaceChildren();
    for (const practice of teamData.upcomingPractices || []) {
      const line = document.createElement('p');
      line.textContent = new Date(practice.startUtc).toLocaleDateString('en-US', {timeZone:'America/New_York'}) + ': ' + formatTime(practice.startUtc) + (practice.endUtc ? '–' + formatTime(practice.endUtc) : '') + ' · ' + (practice.location || 'Location TBA');
      practices.appendChild(line);
    }
    if (!(teamData.upcomingPractices || []).length) practices.textContent = teamData.fetchedUtc ? 'No upcoming practices listed.' : 'Schedule loading…';
    document.getElementById('team-feedback').textContent = teamData.error || '';
    const events = document.getElementById('team-event'); events.replaceChildren(new Option('Choose a game to update', ''));
    for (const game of [...teamData.events].reverse().filter(game => !game.includedInStartingRecord)) {
      events.add(new Option(new Date(game.startUtc).toLocaleDateString('en-US', {timeZone:'America/New_York'}) + ' ' + formatTime(game.startUtc) + ' ' + game.opponent, game.id));
    }
    selectTeamResult();
  } catch (error) { document.getElementById('team-feedback').textContent = error.message; }
}
function selectTeamResult() {
  document.getElementById('team-result').value = teamData?.results[document.getElementById('team-event').value] || '';
}
async function saveTeam() {
  try {
    if (!teamData) throw new Error('Reload Team before saving');
    const payload = {expectedVersion:teamData.version,rank:Number(document.getElementById('team-rank').value)};
    const eventId = document.getElementById('team-event').value;
    if (eventId) { payload.eventId = eventId; payload.result = document.getElementById('team-result').value || null; }
    const response = await broadcastFetch('/api/team', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Could not save');
    await loadTeam(); document.getElementById('team-feedback').textContent = 'Saved';
  } catch (error) { document.getElementById('team-feedback').textContent = error.message; }
}
async function showTeam() {
  try {
    const response = await broadcastFetch('/api/team/show', {method:'POST'});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Could not show Team');
    document.getElementById('team-feedback').textContent = 'Showing Team';
  } catch (error) { document.getElementById('team-feedback').textContent = error.message; }
}
loadTeam();
loadArcade();

// Refresh scoreboard status
async function refreshStatus() {
  try {
    const res = await fetch('/status', {cache: 'no-store'});
    if (!res.ok) throw new Error();
    const data = await res.json();

    // Status badge
    const badge = document.getElementById('live-badge');
    const badgeText = document.getElementById('badge-text');
    if (data.status === 'ok') {
      badge.className = 'badge online';
      badgeText.textContent = data.quietHoursActive ? 'Quiet Hours (' + (data.brightness || 'dim') + ')' : 'Live (' + (data.gameCount || 0) + ' games)';
    }

    // Uptime
    if (data.uptimeSec) {
      const hrs = Math.floor(data.uptimeSec / 3600);
      const mins = Math.floor((data.uptimeSec % 3600) / 60);
      document.getElementById('uptime-text').textContent = 'Up ' + hrs + 'h ' + mins + 'm';
    }

    if (data.history) {
      const h = data.history;
      const picker = document.getElementById('history-date');
      picker.max = h.today;
      if (!picker.value) {
        const previous = new Date(h.today + 'T12:00:00Z'); previous.setUTCDate(previous.getUTCDate()-1);
        picker.value = previous.toISOString().slice(0,10);
      }
      document.getElementById('history-status').textContent = h.active ?
        h.label + ' · ' + (h.loading ? 'Loading finals' : h.games + ' final games') +
        ' · Live in ' + Math.ceil(h.remainingSec/60) + ' min' + (h.errors.length ? ' · ' + h.errors.join(', ') : '') :
        'Live date · Use the household PIN in Preferences to browse past scores';
    }

    // Hold state
    const holdBtn = document.getElementById('btn-hold');
    if ((data.history && data.history.active) ? data.history.held : data.isHeld) {
      holdBtn.className = 'btn-amber active';
      holdBtn.textContent = '▶️ Resume Rotation';
    } else {
      holdBtn.className = 'btn-secondary';
      holdBtn.textContent = '⏸️ Hold Game';
    }

    // Commit tag
    if (data.installedBuild && data.installedBuild.buildId && data.installedBuild.buildId !== 'unknown') {
      document.getElementById('git-commit-tag').textContent = 'Build: ' + data.installedBuild.buildId;
    } else if (data.currentCommit && data.currentCommit !== 'unknown') {
      document.getElementById('git-commit-tag').textContent = 'Commit: ' + data.currentCommit;
    } else if (data.project && data.project.version) {
      document.getElementById('git-commit-tag').textContent = 'Project v' + data.project.version;
    }

    // Refresh live display preview image
    const screenImg = document.getElementById('screen-preview');
    if (screenImg) {
      screenImg.src = '/api/screen.png?t=' + Date.now();
    }

    // Update live display banner
    if (data.arcade) {
      const a = data.arcade;
      document.getElementById('arcade-status').textContent = !a.active ? 'Scoreboard mode · press Select for main menu' : a.menu ? 'Choose a game on the remote' : a.game.toUpperCase() + (a.paused ? ' · paused' : ' · ' + a.gameStatus);
    }
    if (data.display) {
      const d = data.display;
      const sceneTag = document.getElementById('live-scene-tag');
      const primaryText = document.getElementById('live-primary-text');
      const secondaryText = document.getElementById('live-secondary-text');

      if (d.scene === 'reveal' || d.isReveal) {
        if (sceneTag) sceneTag.textContent = '📢 Announcement';
        if (primaryText) primaryText.textContent = '📢 Custom Message Broadcasting Live';
        if (secondaryText) secondaryText.textContent = 'Showing custom announcement on scoreboard';
      } else if (d.scene === 'fireworks' || d.isFireworks) {
        if (sceneTag) sceneTag.textContent = '🎆 Fireworks Finale';
        if (primaryText) primaryText.textContent = '🎆 Fireworks Celebration Active';
        if (secondaryText) secondaryText.textContent = 'Animated pyrotechnics on display';
      } else if (d.scene === 'history') {
        if (sceneTag) sceneTag.textContent = 'Past Scores · FINAL ONLY';
        if (primaryText) primaryText.textContent = d.history.label;
        if (secondaryText) secondaryText.textContent = 'Returns to live in ' + Math.ceil(d.history.remainingSec/60) + ' minutes';
      } else if (d.scene === 'scoringAlert') {
        if (sceneTag) sceneTag.textContent = d.alert.message;
        if (primaryText) primaryText.textContent = d.alert.team;
        if (secondaryText) secondaryText.textContent = 'Confirmed scoring play in the displayed game';
      } else if (d.scene === 'home') {
        if (sceneTag) sceneTag.textContent = '🏠 Home';
        if (primaryText) primaryText.textContent = 'Home Clock';
        if (secondaryText) secondaryText.textContent = 'Y Home · A Scores · Select Menu';
      } else if (d.game) {
        const g = d.game;
        const away = g.away || {};
        const home = g.home || {};
        const awayStr = (away.abbr || 'AWAY') + (away.score !== undefined ? ' ' + away.score : '');
        const homeStr = (home.abbr || 'HOME') + (home.score !== undefined ? ' ' + home.score : '');
        const venueStr = g.venue ? ' · 📍 ' + g.venue : '';
        const dateStr = g.gameDate || 'Today';

        if (g.isFinal) {
          if (sceneTag) sceneTag.textContent = 'Game: FINAL';
          if (primaryText) primaryText.textContent = '🏆 FINAL: ' + awayStr + ' — ' + homeStr;
          if (secondaryText) secondaryText.textContent = '📅 ' + dateStr + (g.startTime ? ' · Started at ' + g.startTime : '') + venueStr;
        } else if (g.status === 'in_progress') {
          if (sceneTag) sceneTag.textContent = 'Game: LIVE';
          if (primaryText) primaryText.textContent = (d.scene === 'nfl' ? '🏈 NFL: ' : '⚾ LIVE: ') + awayStr + ' @ ' + homeStr;
          if (secondaryText) secondaryText.textContent = '📅 ' + dateStr + (g.statusDetail ? ' · ' + g.statusDetail : '') + venueStr;
        } else {
          if (sceneTag) sceneTag.textContent = 'Game: PREGAME';
          if (primaryText) primaryText.textContent = '⏳ PREGAME: ' + (away.abbr || 'AWAY') + ' @ ' + (home.abbr || 'HOME');
          if (secondaryText) secondaryText.textContent = '📅 ' + dateStr + (g.startTime ? ' · Starts at ' + g.startTime : '') + venueStr;
        }
      } else if (d.standings) {
        const s = d.standings;
        if (sceneTag) sceneTag.textContent = 'Standings';
        if (primaryText) primaryText.textContent = '📊 ' + (s.division || 'MLB Standings');
        if (secondaryText) secondaryText.textContent = (s.team || 'Team') + ' — Rank #' + (s.rank || '-') + ' (' + (s.record || '--') + ')';
      } else {
        if (sceneTag) sceneTag.textContent = 'Rotating';
        if (primaryText) primaryText.textContent = '⚾ Pixelboard Active';
        if (secondaryText) secondaryText.textContent = 'Rotating through live MLB games and standings';
      }
    }
  } catch (e) {
    document.getElementById('live-badge').className = 'badge';
    document.getElementById('badge-text').textContent = 'Connecting…';
  }
}

// Load settings
async function loadConfig() {
  try {
    const res = await fetch('/api/config', {cache: 'no-store'});
    if (!res.ok) return;
    const config = await res.json();

    // Quiet hours
    if (config.quietHours) {
      document.getElementById('qh-enabled').checked = Boolean(config.quietHours.enabled);
      document.getElementById('qh-start').value = config.quietHours.start || '21:00';
      document.getElementById('qh-end').value = config.quietHours.end || '06:00';
      document.getElementById('qh-behavior').value = config.quietHours.behavior || 'dim';
    }

    // Brightness
    if (config.brightness) {
      document.getElementById('br-normal').value = config.brightness.normal || 35;
      document.getElementById('normal-val').textContent = (config.brightness.normal || 35) + '%';
      document.getElementById('br-dim').value = config.brightness.dim || 10;
      document.getElementById('dim-val').textContent = (config.brightness.dim || 10) + '%';
    }

    // Favorites & Teams
    allTeamsList = config.allTeams || [];
    selectedFavorites = new Set(config.favorites || []);
    document.getElementById('display-layout').value = config.layoutPreset || 'classic';
    configVersion = config.version;
    nflSettings = config.nfl || {};
    document.getElementById('nfl-enabled').checked = Boolean(nflSettings.enabled);
    document.getElementById('nfl-dwell').value = nflSettings.dwellSec || 8;
    document.getElementById('wake-duration').value = config.wakeDurationSec || 60;
    renderTeams();
  } catch (e) {
    console.error('Failed to load configuration:', e);
  }
}

function renderTeams() {
  const container = document.getElementById('teams-container');
  container.innerHTML = '';
  document.getElementById('fav-count').textContent = selectedFavorites.size + ' selected';

  allTeamsList.forEach(team => {
    const chip = document.createElement('div');
    chip.className = 'team-chip' + (selectedFavorites.has(team) ? ' active' : '');
    chip.textContent = team;
    chip.onclick = () => {
      if (selectedFavorites.has(team)) {
        selectedFavorites.delete(team);
      } else {
        selectedFavorites.add(team);
      }
      chip.classList.toggle('active', selectedFavorites.has(team));
      document.getElementById('fav-count').textContent = selectedFavorites.size + ' selected';
    };
    container.appendChild(chip);
  });
}

// Save Settings
async function saveSettings(e) {
  e.preventDefault();
  const toast = document.getElementById('save-toast');
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  toast.className = 'toast';
  toast.textContent = 'Saving preferences to scoreboard…';

  const payload = {
    expectedVersion: configVersion,
    wakeDurationSec: parseInt(document.getElementById('wake-duration').value, 10),
    layoutPreset: document.getElementById('display-layout').value,
    quietHours: {
      enabled: document.getElementById('qh-enabled').checked,
      start: document.getElementById('qh-start').value,
      end: document.getElementById('qh-end').value,
      behavior: document.getElementById('qh-behavior').value
    },
    brightness: {
      normal: parseInt(document.getElementById('br-normal').value, 10),
      dim: parseInt(document.getElementById('br-dim').value, 10)
    },
    nfl: {...nflSettings, enabled:document.getElementById('nfl-enabled').checked, dwellSec:parseInt(document.getElementById('nfl-dwell').value,10)},
    favorites: Array.from(selectedFavorites)
  };

  try {
    const res = await broadcastFetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    if (res.ok) {
      configVersion = result.config.version;
      toast.className = 'toast success';
      toast.textContent = '✓ Preferences saved & applied to display!';
      setTimeout(() => { toast.textContent = ''; }, 3500);
    } else {
      toast.className = 'toast error';
      toast.textContent = 'Error: ' + (result.error || 'Failed to save');
    }
  } catch (err) {
    toast.className = 'toast error';
    toast.textContent = 'Network error saving preferences: ' + err;
  } finally {
    btn.disabled = false;
  }
}

async function setHistory(live) {
  const output = document.getElementById('history-status');
  try {
    const response = await broadcastFetch('/api/history', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date:live ? null : document.getElementById('history-date').value})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to change game date');
    refreshStatus();
  } catch (e) { output.textContent = e.message; }
}

// Quick controls
async function control(action) {
  try {
    const response = await broadcastFetch('/api/control/' + action, {method: 'POST'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to change screen');
    document.getElementById('control-status').textContent = '';
    refreshStatus();
  } catch (e) {
    document.getElementById('control-status').textContent = e.message;
  }
}

// Software Updates
async function checkUpdates() {
  const toast = document.getElementById('update-toast');
  const banner = document.getElementById('update-banner');
  const msg = document.getElementById('update-msg');
  const commitsDiv = document.getElementById('commit-list');
  const applyBtn = document.getElementById('btn-apply-update');
  const checkBtn = document.getElementById('btn-check-updates');

  checkBtn.disabled = true;
  checkBtn.textContent = 'Checking GitHub…';
  toast.textContent = '';
  banner.classList.remove('hidden');
  msg.textContent = 'Fetching latest changes from origin/main…';

  try {
    const res = await fetch('/api/update/check');
    const data = await res.json();

    if (!res.ok || data.error) {
      msg.textContent = '⚠️ Check failed: ' + (data.error || 'Unknown error');
      commitsDiv.classList.add('hidden');
      applyBtn.classList.add('hidden');
      return;
    }

    document.getElementById('git-commit-tag').textContent = 'Commit: ' + data.currentCommit;

    if (data.available) {
      msg.innerHTML = '🎉 <span style="color:var(--primary);">New update available!</span> (' + data.currentCommit + ' → ' + data.remoteCommit + ')';
      if (data.commits && data.commits.length > 0) {
        commitsDiv.innerHTML = data.commits.map(c => '<div class="commit-item">' + c + '</div>').join('');
        commitsDiv.classList.remove('hidden');
      } else {
        commitsDiv.classList.add('hidden');
      }
      applyBtn.classList.remove('hidden');
    } else {
      msg.textContent = data.message || ('✓ Scoreboard software is up to date (' + data.currentCommit + ').');
      commitsDiv.classList.add('hidden');
      applyBtn.classList.add('hidden');
    }
  } catch (err) {
    msg.textContent = 'Network error checking updates: ' + err;
  } finally {
    checkBtn.disabled = false;
    checkBtn.textContent = '🔍 Check for Updates';
  }
}

async function applyUpdate() {
  if (!confirm('Update scoreboard software from GitHub and restart the background service?')) return;
  const toast = document.getElementById('update-toast');
  const applyBtn = document.getElementById('btn-apply-update');
  applyBtn.disabled = true;
  applyBtn.textContent = 'Updating...';
  toast.className = 'toast';
  toast.textContent = 'Pulling code and restarting service. Reconnecting in a few seconds…';

  try {
    const res = await adminFetch('/api/update/apply', {method: 'POST'});
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) {
        forgetBroadcastPin();
        throw new Error('The household PIN was not accepted. No update started.');
      }
      throw new Error(data.error || 'Update failed');
    }

    // Poll until scoreboard reconnects
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      toast.textContent = 'Waiting for scoreboard to restart (' + attempts + 's)…';
      try {
        const ping = await fetch('/status', {cache: 'no-store'});
        if (ping.ok) {
          clearInterval(interval);
          toast.className = 'toast success';
          toast.textContent = '✓ Scoreboard updated successfully! Reloading…';
          setTimeout(() => { window.location.reload(); }, 1500);
        }
      } catch (e) {
        // Still restarting
      }
      if (attempts > 30) {
        clearInterval(interval);
        toast.className = 'toast error';
        toast.textContent = 'Update was triggered, but reconnection timed out. Refresh the page manually.';
        applyBtn.disabled = false;
        applyBtn.textContent = 'Apply Update';
      }
    }, 1000);
  } catch (err) {
    toast.className = 'toast error';
    toast.textContent = 'Error applying update: ' + err.message;
    applyBtn.disabled = false;
    applyBtn.textContent = 'Apply Update';
  }
}

// Reveal Controls
function toggleRevealCard() {
  const content = document.getElementById('reveal-content');
  const icon = document.getElementById('reveal-toggle-icon');
  content.classList.toggle('hidden');
  icon.textContent = content.classList.contains('hidden') ? '▼ Click to Expand' : '▲ Click to Collapse';
}

async function refreshReveal() {
  try {
    const response = await fetch('/reveal/status', {cache: 'no-store'});
    const body = await response.json();
    document.getElementById('state').textContent = body.waitingForController ? 'Waiting for controller · prompt displayed' : body.state;
  } catch (error) {
    document.getElementById('state').textContent = 'unavailable';
  }
}

// Stadium Announcement & Custom Message Controls
const MESSAGE_PRESETS = {
  birthday: {
    lines: ['WELCOME', 'LET'S CELEBRATE!'],
    fireworks: true,
    dwell: 4
  },
  gameday: {
    lines: ["IT'S GAME DAY!", "PLAY BALL!"],
    fireworks: true,
    dwell: 4
  },
  morning: {
    lines: ['GOOD MORNING', 'CHAMPION!'],
    fireworks: false,
    dwell: 3
  },
  grandslam: {
    lines: ['IT IS OUTTA HERE!', 'GRAND SLAM!'],
    fireworks: true,
    dwell: 4
  }
};

function applyPreset(key) {
  const p = MESSAGE_PRESETS[key];
  if (!p) return;
  document.getElementById('custom-msg-lines').value = p.lines.join('\\n');
  document.getElementById('msg-fireworks').checked = p.fireworks;
  document.getElementById('msg-dwell').value = p.dwell;
}

async function broadcastCustomMessage(armForBoot, waitForController = false) {
  const raw = document.getElementById('custom-msg-lines').value;
  const lines = raw.split('\\n').map(s => s.trim()).filter(Boolean);
  const fireworks = document.getElementById('msg-fireworks').checked;
  const dwellSec = parseFloat(document.getElementById('msg-dwell').value) || 4;
  const msgToast = document.getElementById('message');

  msgToast.className = 'toast';
  msgToast.textContent = armForBoot ? 'Arming message for next boot…' : 'Broadcasting message to scoreboard…';

  try {
    const res = await (armForBoot ? adminFetch : broadcastFetch)('/api/message', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        lines: lines.length ? lines : ['HAPPY CELEBRATION!'],
        fireworks,
        dwellSec,
        armForBoot,
        waitForController
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Server error');
    msgToast.className = 'toast success';
    msgToast.textContent = data.message || 'Success!';
    refreshReveal();
  } catch (err) {
    msgToast.className = 'toast error';
    msgToast.textContent = 'Failed: ' + err.message;
  }
}

async function act(action) {
  const message = document.getElementById('message');
  message.textContent = 'Working…';
  try {
    const response = await (action === 'disarm' || action === 'wait' ? broadcastFetch : adminFetch)('/reveal/' + action, {method: 'POST'});
    const body = await response.json();
    message.textContent = response.ok ? JSON.stringify(body) : ('Error: ' + (body.error || response.status));
  } catch (error) {
    message.textContent = 'Request failed: ' + error;
  }
  refreshReveal();
}

// Initial bootstrap
document.getElementById('broadcast-pin').value = localStorage.getItem('scoreboard-broadcast-pin') || '';
document.getElementById('preferences-pin').value = localStorage.getItem('scoreboard-broadcast-pin') || '';
loadConfig();
refreshStatus();
refreshReveal();
setInterval(refreshStatus, 4000);
setInterval(refreshReveal, 4000);
</script>
</body>
</html>
"""


class StatusServer:
    def __init__(
        self,
        host: str,
        port: int,
        status: Callable[[], dict[str, Any]],
        *,
        actions: dict[str, Callable[..., dict[str, Any]]] | None = None,
        authorize_broadcast: Callable[[str | None], bool] | None = None,
    ) -> None:
        callback = status
        action_handlers = dict(actions or {})
        broadcast_failures: dict[str, tuple[int, float]] = {}
        broadcast_lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
                body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _same_origin(self) -> bool:
                origin = self.headers.get("Origin")
                if not origin:
                    return True
                host = self.headers.get("Host", "")
                return origin in {f"http://{host}", f"https://{host}"}

            def _require_admin(self) -> bool:
                if not self._same_origin():
                    self._send_json({"error": "Same-origin request is required"}, status_code=403)
                    return False
                return self._require_broadcast_pin()

            def _require_broadcast_pin(self) -> bool:
                client = self.client_address[0]
                now = monotonic()
                with broadcast_lock:
                    attempts, started = broadcast_failures.get(client, (0, now))
                    if now - started >= 60:
                        attempts, started = 0, now
                    if attempts >= 5:
                        self._send_json({"error": "Too many PIN attempts; try again in a minute"}, status_code=429)
                        return False
                    pin = self.headers.get("X-Scoreboard-Broadcast-Pin")
                    if authorize_broadcast is not None and authorize_broadcast(pin):
                        broadcast_failures.pop(client, None)
                        return True
                    broadcast_failures[client] = (attempts + 1, started)
                self._send_json({"error": "Household PIN is required"}, status_code=401)
                return False

            def _require_preferences(self) -> bool:
                if not self._same_origin():
                    self._send_json({"error": "Same-origin request is required"}, status_code=403)
                    return False
                return self._require_broadcast_pin()

            def _read_json_body(self) -> dict[str, Any]:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ValueError("Content-Length is required")
                try:
                    content_length = int(raw_length)
                except ValueError as error:
                    raise ValueError("Content-Length must be an integer") from error
                if content_length <= 0:
                    return {}
                if content_length > MAX_JSON_BYTES:
                    raise ValueError(f"Request body exceeds {MAX_JSON_BYTES} bytes")
                if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                    raise ValueError("Content-Type must be application/json")
                body = self.rfile.read(content_length).decode("utf-8")
                payload = json.loads(body) if body.strip() else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON body must be an object")
                return payload

            def do_GET(self) -> None:  # noqa: N802
                req_path = self.path.split("?")[0]
                if req_path in ("/", "/reveal"):
                    body = DASHBOARD_PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if req_path in {"/status", "/health"}:
                    payload = callback() if req_path == "/status" else {"status": "ok"}
                    self._send_json(payload)
                    return
                if req_path == "/api/screen.png" and "get_screen" in action_handlers:
                    try:
                        png_bytes = action_handlers["get_screen"]()
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=500)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(png_bytes)))
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(png_bytes)
                    return
                if req_path == "/reveal/status" and "reveal_status" in action_handlers:
                    self._send_json(action_handlers["reveal_status"]())
                    return
                if req_path == "/api/arcade" and "get_arcade" in action_handlers:
                    self._send_json(action_handlers["get_arcade"]())
                    return
                if req_path == "/api/team" and "get_team" in action_handlers:
                    self._send_json(action_handlers["get_team"]())
                    return
                if req_path == "/api/history" and "get_history" in action_handlers:
                    self._send_json(action_handlers['get_history']())
                    return
                if req_path == "/api/config" and "get_config" in action_handlers:
                    try:
                        self._send_json(action_handlers["get_config"]())
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=500)
                    return
                if req_path == "/api/update/check" and "check_update" in action_handlers:
                    try:
                        self._send_json(action_handlers["check_update"]())
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"available": False, "error": str(error)})
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                req_path = self.path.split("?")[0]
                if req_path == "/api/history" and "set_history" in action_handlers:
                    if not self._require_preferences(): return
                    try:
                        self._send_json(action_handlers['set_history'](self._read_json_body()))
                    except (ValueError,TypeError) as error:
                        self._send_json({'error':str(error)},status_code=400)
                    return
                # Live messages and boot surprises use the same household PIN.
                if req_path == "/api/message" and "play_message" in action_handlers:
                    if not self._same_origin():
                        self._send_json({"error": "Same-origin request is required"}, status_code=403)
                        return
                    try:
                        payload = self._read_json_body()
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=400)
                        return
                    if not self._require_broadcast_pin():
                        return
                    try:
                        result = action_handlers["play_message"](payload)
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=400)
                        return
                    self._send_json(result)
                    return

                if req_path == '/api/arcade' and 'update_arcade' in action_handlers:
                    if not self._require_preferences(): return
                    try:
                        self._send_json(action_handlers['update_arcade'](self._read_json_body()))
                    except (ValueError, TypeError) as error:
                        self._send_json({'error': str(error)}, status_code=400)
                    return

                if req_path in ('/api/team', '/api/team/show'):
                    if not self._require_preferences(): return
                    try:
                        result = action_handlers['show_team']() if req_path.endswith('/show') else action_handlers['update_team'](self._read_json_body())
                        self._send_json(result)
                    except RuntimeError as error:
                        self._send_json({'error': str(error)}, status_code=409)
                    except (ValueError, TypeError) as error:
                        self._send_json({'error': str(error)}, status_code=400)
                    return

                # API configuration update
                if req_path == "/api/config":
                    if not self._require_preferences():
                        return
                    if "update_config" not in action_handlers:
                        self.send_error(404)
                        return
                    try:
                        payload = self._read_json_body()
                        result = action_handlers["update_config"](payload)
                    except Exception as error:  # noqa: BLE001
                        body = {"error": str(error)}
                        if getattr(error, "current_config", None) is not None:
                            body["currentConfig"] = error.current_config
                            self._send_json(body, status_code=409)
                        else:
                            self._send_json(body, status_code=400)
                        return
                    self._send_json(result)
                    return


                if req_path in ('/reveal/wait', '/reveal/disarm'):
                    if not self._require_preferences():
                        return
                    try:
                        self._send_json(action_handlers[req_path.removeprefix('/reveal/')]())
                    except Exception as error:
                        self._send_json({'error': str(error)}, status_code=409)
                    return
                if req_path in ("/api/control/home", "/api/control/next", "/api/control/hold"):
                    if not self._require_preferences(): return
                    name = "control_" + req_path.rsplit("/", 1)[-1]
                    if name not in action_handlers:
                        self.send_error(404)
                        return
                    self._send_json(action_handlers[name]())
                    return

                if not self._require_admin():
                    return
                # Reveal legacy actions
                if req_path.startswith("/reveal/"):
                    name = req_path.removeprefix("/reveal/")
                    if name not in action_handlers:
                        self.send_error(404)
                        return
                    try:
                        result = action_handlers[name]()
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=409)
                        return
                    self._send_json(result)
                    return

                # API controls
                if req_path == "/api/control/home" and "control_home" in action_handlers:
                    self._send_json(action_handlers["control_home"]())
                    return
                if req_path == "/api/control/next" and "control_next" in action_handlers:
                    self._send_json(action_handlers["control_next"]())
                    return
                if req_path == "/api/control/hold" and "control_hold" in action_handlers:
                    self._send_json(action_handlers["control_hold"]())
                    return

                # API update
                if req_path == "/api/update/apply" and "apply_update" in action_handlers:
                    try:
                        result = action_handlers["apply_update"]()
                    except Exception as error:  # noqa: BLE001
                        self._send_json({"error": str(error)}, status_code=500)
                        return
                    self._send_json(result)
                    return

                self.send_error(404)

            def log_message(self, format: str, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, name="scoreboard-status", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
