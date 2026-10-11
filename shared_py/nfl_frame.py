"""NFL frame mirrored byte-for-byte by shared_ts/nfl_frame.ts."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from shared_py.bdf import glyph_for
from shared_py.renderer import PixelBuffer, _draw_element

def nfl_frame(game, fonts, layout='rows', stale=False, timezone_name='America/New_York', assets=None):
    frame=PixelBuffer(128,32,(3,8,7,255))
    def text(value,font,x,y,color,max_x=128):
        for ch in str(value).upper():
            g=glyph_for(font,ord(ch))
            if not g: continue
            if x+g.width>max_x: break
            for row in range(g.height):
                for col in range(g.width):
                    if g.bitmap[row*g.width+col]: frame.set_pixel(x+col,y+row,(*color,255))
            x+=g.advance_x
    small=fonts['4x6']
    if not game:
        text('NO NFL GAMES',small,4,5,(255,255,255));text('SELECT: MENU',small,4,18,(255,180,115));return frame
    start='KICKOFF'
    if game.get('date'):
        try: start=datetime.fromisoformat(game['date'].replace('Z','+00:00')).astimezone(ZoneInfo(timezone_name)).strftime('%-I:%M %p')
        except (ValueError,TypeError): pass
    def score(t): return '--' if game['state']=='pre' else str(t.get('score') or '0')
    if layout=='compact':
        lines=[f"{game['away']['abbr']} {score(game['away'])}  {game['home']['abbr']} {score(game['home'])}",
               'DATA STALE' if stale else game['status'],
               (game.get('downDistance') or game.get('fieldPosition') or '') if game['state']=='in' else start if game['state']=='pre' else '']
        for i,line in enumerate(lines): text(line,small,2,2+i*10,(255,255,255) if i==0 else (255,194,117))
        return frame
    assets = assets or {}
    keys = [f"team-logo:nfl:{team['id']}:16" for team in (game['away'], game['home'])]
    def visible(key):
        asset = assets.get(key, {})
        data = asset.get('data', [])
        return asset.get('width') == 16 and asset.get('height') == 16 and len(data) == 1024 and any(data[3::4])
    logos = all(visible(key) for key in keys)
    for i,team in enumerate((game['away'],game['home'])):
        raw=team.get('color','')
        color=tuple(int(raw[j:j+2],16) for j in (0,2,4)) if re.fullmatch('[a-fA-F0-9]{6}',raw) else (36,59,87)
        dim=tuple((c*2+1)//3 for c in color)
        y=i*16
        frame.fill_rect(0,y,58,15,(*dim,255))
        if logos:
            _draw_element(frame, {'type': 'sprite', 'x': 3, 'y': y, 'mode': 'rgb', 'asset': keys[i]},
                          {'assets': assets, 'bindings': {}})
            text(team['abbr'],small,21,y+5,(255,255,255),37)
        else:
            text(team['abbr'],fonts['5x7'],5,y+4,(255,255,255),27)
        text(score(team),fonts['6x10'],38 if logos else 33,y+2,(255,255,255),58 if logos else 56)
        if str(game.get('possession'))==team['id']: frame.fill_rect(1,y+6,2,3,(255,202,116,255))
    frame.fill_rect(60,0,1,32,(52,71,93,255))
    period=game.get('period'); headline='FINAL' if game['completed'] else start if game['state']=='pre' else 'HALFTIME' if 'halftime' in game['status'].lower() else f"{'OT' if period and period>4 else 'Q'+str(period) if period else ''} {game.get('clock') or game['status']}"
    text('STALE' if stale else headline,small,65,3,(255,194,117),126)
    text(game.get('downDistance') or ('KICKOFF' if game['state']=='pre' else 'FULL TIME' if game['completed'] else ''),small,65,13,(255,255,255),126)
    text(game.get('fieldPosition') or ('RED ZONE' if game.get('redZone') else 'NFL'),small,65,23,(155,230,181),126)
    return frame
