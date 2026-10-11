from __future__ import annotations

import json
import re
import urllib.request
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from shared_py.renderer import PixelBuffer, WHITE, Clip, _draw_text, _draw_element


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.touch(mode=0o600)
    temporary.chmod(0o600)
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def _read(path, default):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, type(default)) else deepcopy(default)
    except (OSError, ValueError):
        return deepcopy(default)


def _unescape(value):
    return value.replace(r'\n', ' ').replace(r'\N', ' ').replace(r'\,', ',').replace(r'\;', ';').replace(r'\\', '\\')


def parse_calendar(text, timezone_name='America/New_York'):
    """Read games and practices from one feed, preserving per-event identity."""
    if 'BEGIN:VCALENDAR' not in text or 'END:VCALENDAR' not in text:
        raise ValueError('Invalid calendar')
    text = re.sub(r'\r?\n[ \t]', '', text)
    events = {}
    def date_value(prop):
        value, params = prop
        if len(value) == 8:
            return datetime.strptime(value, '%Y%m%d').replace(tzinfo=ZoneInfo(timezone_name))
        zone = timezone.utc if value.endswith('Z') else ZoneInfo(params.get('TZID', timezone_name).strip('"'))
        return datetime.strptime(value.rstrip('Z'), '%Y%m%dT%H%M%S').replace(tzinfo=zone)
    for block in text.split('BEGIN:VEVENT')[1:]:
        props = {}
        for line in block.split('END:VEVENT')[0].splitlines():
            if ':' not in line: continue
            key, value = line.split(':', 1)
            bits = key.split(';'); params = dict(bit.split('=', 1) for bit in bits[1:] if '=' in bit)
            props[bits[0]] = (value, params)
        uid = props.get('UID', ('', {}))[0]
        summary = _unescape(props.get('SUMMARY', ('', {}))[0])
        match = re.search(r'\s+(vs\.?|@)\s+(.+)', summary, re.I)
        if not uid: continue
        revision = (int(props.get('SEQUENCE', ('0', {}))[0]), props.get('LAST-MODIFIED', ('', {}))[0])
        if uid in events and events[uid][0] > revision: continue
        if props.get('STATUS', ('', {}))[0] == 'CANCELLED':
            events[uid] = (revision, None); continue
        practice = bool(re.search(r'\b(practice|training)\b', summary, re.I))
        if 'DTSTART' not in props or (not practice and not match): continue
        start = date_value(props['DTSTART']); end = date_value(props['DTEND']) if 'DTEND' in props else None
        events[uid] = (revision, {'id': uid, 'kind': 'practice' if practice else 'game', 'title': summary,
            'location': _unescape(props.get('LOCATION', ('', {}))[0]),
            'opponent': match[2].strip() if not practice else '', 'away': match[1] == '@' if not practice else False,
            'startUtc': start.astimezone(timezone.utc).isoformat(),
            'endUtc': end.astimezone(timezone.utc).isoformat() if end else None})
    return sorted([event for _, event in events.values() if event], key=lambda event: (event['startUtc'], event['id']))


def short_opponent(name):
    name = name.upper()
    name = re.sub(r'^(VBA|JCB)\s+', '', name)
    name = re.sub(r'\s+(SELECT\s+)?10U[A-Z]?$', '', name)
    return name.replace('DIAMOND KINGS', 'DMD KINGS').replace('ARROWS - RED', 'ARROWS')[:10]


def upcoming_groups(events, now, timezone_name='America/New_York'):
    zone = ZoneInfo(timezone_name); today = now.astimezone(zone).date()
    groups = {}
    for event in events:
        if event.get('kind', 'game') != 'game': continue
        start = datetime.fromisoformat(event['startUtc']).astimezone(zone)
        # Keep every game on the paper until the following local calendar day.
        if start.date() < today: continue
        key = (start.date().isoformat(), event['opponent'], bool(event['away']))
        group = groups.setdefault(key, {'id': '|'.join((key[0], key[1], str(key[2]))), 'date': key[0],
            'opponent': key[1], 'away': key[2], 'games': []})
        group['games'].append(deepcopy(event))
    return sorted(groups.values(), key=lambda group: group['games'][0]['startUtc'])[:3]


def upcoming_practices(events, now, timezone_name='America/New_York'):
    today = now.astimezone(ZoneInfo(timezone_name)).date()
    return sorted([
        deepcopy(event) for event in events if event.get('kind') == 'practice'
        and datetime.fromisoformat(event['startUtc']).astimezone(ZoneInfo(timezone_name)).date() >= today
        and datetime.fromisoformat(event.get('endUtc') or event['startUtc']) > now
    ], key=lambda event: (event['startUtc'], event['id']))[:3]


class TeamSchedule:
    def __init__(self, state_dir, timezone_name='America/New_York'):
        self.state_dir = Path(state_dir)
        self.timezone_name = timezone_name
        self.calendar = _read(self.state_dir / 'team-schedule.json', {'events': [], 'fetchedUtc': None})
        try:
            for event in self.calendar['events']:
                assert isinstance(event['id'], str) and isinstance(event['opponent'], str)
                assert event.get('kind', 'game') in ('game', 'practice')
                assert isinstance(event.get('title', ''), str) and isinstance(event.get('location', ''), str)
                assert datetime.fromisoformat(event['startUtc']).tzinfo is not None
                if event.get('endUtc'): assert datetime.fromisoformat(event['endUtc']).tzinfo is not None
                assert type(event['away']) is bool
        except (KeyError, TypeError, ValueError, AssertionError):
            self.calendar = {'events': [], 'fetchedUtc': None}
        self.record = _read(self.state_dir / 'team-record.json', {'version': 1, 'rank': 1, 'results': {}})
        if (not isinstance(self.record.get('results'), dict)
            or type(self.record.get('version')) is not int or self.record['version'] < 1
            or type(self.record.get('rank')) is not int or not 1 <= self.record['rank'] <= 99
            or any(v not in ('win', 'loss', 'tie') for v in self.record['results'].values())):
            self.record = {'version': 1, 'rank': 1, 'results': {}}
        self.error = None

    def refresh(self):
        source = self.state_dir / 'team-calendar-url'
        if not source.is_file(): return False
        try:
            url = source.read_text().strip().replace('webcal://', 'https://', 1)
            if not url.startswith('https://'): raise ValueError('Calendar requires HTTPS')
            with urllib.request.urlopen(url, timeout=10) as response:
                text = response.read(2_000_001)
            if len(text) > 2_000_000: raise ValueError('Calendar too large')
            events = parse_calendar(text.decode('utf-8-sig'), self.timezone_name)
            calendar = {'events': events, 'fetchedUtc': datetime.now(timezone.utc).isoformat()}
            _write(self.state_dir / 'team-schedule.json', calendar)
            self.calendar = calendar
            self.error = None
            return True
        except Exception:
            # Exception strings may include the credential-bearing URL.
            self.error = 'Calendar temporarily unavailable; showing saved schedule'
            return False

    def snapshot(self, now):
        practice_ids = {event['id'] for event in self.calendar['events'] if event.get('kind') == 'practice'}
        results = {uid: result for uid, result in self.record.get('results', {}).items() if uid not in practice_ids}
        practices = [deepcopy(event) for event in self.calendar['events'] if event.get('kind') == 'practice']
        return {'version': self.record.get('version', 1), 'rank': self.record.get('rank', 1),
            'wins': list(results.values()).count('win'), 'losses': list(results.values()).count('loss'),
            'ties': list(results.values()).count('tie'), 'results': dict(results),
            'events': [dict(event, includedInStartingRecord=False) for event in self.calendar['events'] if event.get('kind', 'game') == 'game'],
            'practices': practices, 'upcomingPractices': upcoming_practices(practices, now, self.timezone_name),
            'groups': upcoming_groups(self.calendar['events'], now, self.timezone_name),
            'fetchedUtc': self.calendar.get('fetchedUtc'), 'error': self.error,
            'recordSource': 'Manually maintained team record'}

    def update(self, payload):
        if not isinstance(payload, dict) or set(payload) - {'expectedVersion', 'rank', 'eventId', 'result'}:
            raise ValueError('Invalid Team preferences')
        if type(payload.get('expectedVersion')) is not int or payload['expectedVersion'] != self.record.get('version', 1):
            raise RuntimeError('Team record changed; reload before saving')
        candidate = deepcopy(self.record)
        if 'rank' in payload:
            if type(payload['rank']) is not int or not 1 <= payload['rank'] <= 99: raise ValueError('Rank must be 1-99')
            candidate['rank'] = payload['rank']
        if 'eventId' in payload or 'result' in payload:
            uid, result = payload.get('eventId'), payload.get('result')
            practice_ids = {event['id'] for event in self.calendar['events'] if event.get('kind') == 'practice'}
            if isinstance(uid, str) and uid in practice_ids:
                raise ValueError('Practices cannot have game results')
            known = {event['id'] for event in self.calendar['events']} | set(candidate['results'])
            if not isinstance(uid, str) or uid not in known or result not in ('win', 'loss', 'tie', None): raise ValueError('Choose a scheduled game and result')
            if result is None: candidate['results'].pop(uid, None)
            else: candidate['results'][uid] = result
        candidate['version'] = self.record.get('version', 1) + 1
        _write(self.state_dir / 'team-record.json', candidate)
        self.record = candidate


def team_schedule_frame(snapshot, fonts, assets, group=None, timezone_name='America/New_York', practice=None, practice_summary=False):
    """Device-only paper-inspired card composed from existing drawing primitives."""
    frame = PixelBuffer(128, 32)
    cyan = (64, 210, 255, 255); gold = (255, 210, 90, 255)
    font = fonts['4x6']; clip = Clip(0, 0, 128, 32)
    key = 'team-logo:sample-team:16'
    _draw_element(frame, {'type': 'sprite', 'x': 1, 'y': 0, 'mode': 'rgb', 'asset': key}, {'assets': assets, 'bindings': {}})
    _draw_text(frame, font, 'TEAM', 20, 2, cyan, outer_clip=clip)
    _draw_text(frame, font, '#' + str(snapshot['rank']), 20, 10, gold, outer_clip=clip)
    record = str(snapshot['wins']) + '-' + str(snapshot['losses']) + ('-' + str(snapshot['ties']) if snapshot['ties'] else '')
    _draw_text(frame, fonts['6x10'], record, 24, 19, WHITE, align='center', outer_clip=Clip(0, 17, 48, 15))
    frame.draw_line(49, 0, 49, 31, cyan)
    if practice_summary:
        lines = ['NEXT PRACTICES']
        zone = ZoneInfo(timezone_name)
        for event in snapshot['upcomingPractices']:
            start = datetime.fromisoformat(event['startUtc']).astimezone(zone)
            lines.append(f'{start.month}/{start.day} ' + start.strftime('%I:%M%p').lstrip('0'))
        if len(lines) == 1: lines.append('NONE LISTED' if snapshot['fetchedUtc'] else 'SCHEDULE LOADING')
    elif practice is not None:
        zone = ZoneInfo(timezone_name)
        start = datetime.fromisoformat(practice['startUtc']).astimezone(zone)
        end = datetime.fromisoformat(practice['endUtc']).astimezone(zone) if practice.get('endUtc') else None
        time = start.strftime('%I:%M').lstrip('0')
        if end: time += '-' + end.strftime('%I:%M').lstrip('0')
        time += (end or start).strftime('%p')
        lines = ['PRACTICE', f'{start.month}/{start.day} ' + start.strftime('%a').upper(), time,
                 practice.get('location') or 'LOCATION TBA']
    elif group is None:
        lines = ['NEXT GAMES']
        for g in snapshot['groups']:
            date = datetime.fromisoformat(g['date'])
            lines.append(str(date.month) + '/' + str(date.day) + (' @ ' if g['away'] else ' ') + short_opponent(g['opponent']) + (' DH' if len(g['games']) > 1 else ''))
        if len(lines) == 1: lines.append('NO GAMES LISTED' if snapshot['fetchedUtc'] else 'SCHEDULE LOADING')
    else:
        date = datetime.fromisoformat(group['date'])
        lines = [str(date.month) + '/' + str(date.day) + (' @ ' if group['away'] else ' VS ') + short_opponent(group['opponent'])]
        zone = ZoneInfo(timezone_name)
        for event in group['games'][:2]:
            start = datetime.fromisoformat(event['startUtc']).astimezone(zone)
            label = start.strftime('%I:%M').lstrip('0')
            end = datetime.fromisoformat(event['endUtc']).astimezone(zone) if event['endUtc'] else None
            label += '-' + end.strftime('%I:%M').lstrip('0') if end else ''
            label += (end or start).strftime('%p')
            lines.append(label)
        lines.append('DOUBLEHEADER' if len(group['games']) > 1 else 'GAME DAY')
    for index, text in enumerate(lines[:4]):
        _draw_text(frame, font, text, 54, 1 + index * 8, cyan if index == 0 else WHITE, max_width=73, outer_clip=clip)
    return frame
