"""Dashboard controls shared by personal and generic installations."""
SPORTS_HTML = '''<div class="form-group" id="sports-preferences">
<h3>Sports &amp; teams in rotation</h3>
<p class="subtitle">Turn sports on or off. Selected teams includes games involving either team; both opponents remain visible. Favorites below control MLB emphasis separately.</p>
<div id="sports-settings"></div>
</div>'''
SPORTS_JS = r'''
let sportsSettings = {};
let sportsCatalog = {};
function renderSports() {
  const container = document.getElementById('sports-settings');
  container.replaceChildren();
  ['mlb','nfl','nba','nhl','team'].forEach(league => {
    const policy = sportsSettings[league];
    if (!policy) return;
    const section = document.createElement('div');
    section.style.cssText = 'border-top:1px solid var(--card-border);padding:12px 0';
    const label = document.createElement('label');
    const toggle = document.createElement('input');
    toggle.type = 'checkbox'; toggle.checked = policy.enabled;
    toggle.onchange = () => { policy.enabled = toggle.checked; syncNflToggle(); };
    label.append(toggle, ' ' + (league === 'team' ? 'Team calendar / local record' : league.toUpperCase()));
    section.append(label);
    const only = document.createElement('button');
    only.type = 'button'; only.textContent = 'Only this sport';
    only.style.cssText = 'margin-left:12px;padding:5px 9px';
    only.onclick = () => { Object.keys(sportsSettings).forEach(k => sportsSettings[k].enabled = k === league); syncNflToggle(); renderSports(); };
    section.append(only);
    if (league !== 'team') {
      const details = document.createElement('details'); details.style.marginTop='8px';
      const summary = document.createElement('summary');
      summary.textContent = policy.teams === null ? 'All teams' : policy.teams.length + ' teams selected';
      const select = document.createElement('select');
      select.setAttribute('aria-label', league.toUpperCase() + ' team selection');
      [['all','All teams'],['selected','Selected teams only']].forEach(([value,text]) => { const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option); });
      select.value = policy.teams === null ? 'all' : 'selected';
      const list = document.createElement('div'); list.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:6px;max-height:250px;overflow:auto;margin-top:10px';
      const update = () => {
        summary.textContent = policy.teams === null ? 'All teams' : policy.teams.length + ' teams selected';
        list.replaceChildren();
        if (policy.teams === null) return;
        (sportsCatalog[league] || []).forEach(team => {
          const l=document.createElement('label'), checkbox=document.createElement('input');
          checkbox.type='checkbox';checkbox.checked=policy.teams.includes(team.abbr);
          checkbox.onchange=()=>{policy.teams=checkbox.checked?[...policy.teams,team.abbr]:policy.teams.filter(t=>t!==team.abbr);summary.textContent=policy.teams.length+' teams selected';};
          l.append(checkbox,' '+team.name);list.append(l);
        });
      };
      select.onchange=()=>{policy.teams=select.value==='all'?null:[];update();};
      const all=document.createElement('button'), none=document.createElement('button');
      all.type=none.type='button';all.textContent='Select all';none.textContent='Select none';
      all.style.cssText=none.style.cssText='padding:5px 9px;margin:6px';
      all.onclick=()=>{policy.teams=(sportsCatalog[league]||[]).map(t=>t.abbr);select.value='selected';update();};
      none.onclick=()=>{policy.teams=[];select.value='selected';update();};
      details.append(summary,select,all,none,list);section.append(details);update();
    }
    container.append(section);
  });
}
function syncNflToggle() {
  const toggle=document.getElementById('nfl-enabled');
  if(toggle && sportsSettings.nfl)toggle.checked=sportsSettings.nfl.enabled;
}
'''
