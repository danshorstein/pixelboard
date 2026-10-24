"""NBA/NHL card composition, byte-identical to shared_ts/sports_frame.ts."""
from datetime import datetime
from zoneinfo import ZoneInfo
import re
from shared_py.bdf import glyph_for
from shared_py.renderer import PixelBuffer

def sports_headline(g, timezone_name='America/New_York'):
    s = g['status'].upper()
    if re.search('POSTPON|DELAY|CANCEL|SUSPEND|HALF|INTERMISSION|END OF|FINAL|SO|SHOOTOUT', s):
        return s.replace('SHOOTOUT', 'SO', 1)
    if g['completed']: return 'FINAL'
    if g['state'] == 'pre':
        return datetime.fromisoformat(g['date'].replace('Z','+00:00')).astimezone(ZoneInfo(timezone_name)).strftime('%-I:%M %p') if g.get('date') else 'SCHEDULED'
    if g['state'] != 'in': return s
    p = g.get('period') or 0
    regular = 3 if g['league'] == 'nhl' else 4
    period = (str(p-regular) if p > regular+1 else '') + 'OT' if p > regular else ('P' if g['league']=='nhl' else 'Q') + str(p)
    return (period + ' ' + (g.get('clock') or '')).strip()

def sports_frame(game, fonts, stale=False, held=False, timezone_name='America/New_York'):
    frame = PixelBuffer(128,32,(3,8,7,255))
    def text(value,x,y,font,color,max_x=128):
        for ch in str(value).upper():
            glyph = glyph_for(font,ord(ch))
            if not glyph: continue
            if x+glyph.width > max_x: break
            for row in range(glyph.height):
                for col in range(glyph.width):
                    if glyph.bitmap[row*glyph.width+col]: frame.set_pixel(x+col,y+row,color)
            x += glyph.advance_x
    small,large = fonts['4x6'],fonts['6x10']
    white,gold = (255,255,255,255),(255,194,117,255)
    if not game:
        text('NO SELECTED GAMES',3,6,small,white)
        text('DATA OFFLINE' if stale else 'CHECK FILTERS',3,20,small,gold)
        return frame
    for i,team in enumerate((game['away'],game['home'])):
        raw = team.get('color') or ''
        if not re.fullmatch('[a-fA-F0-9]{6}',raw): raw='394b64'
        color=tuple(int(raw[j:j+2],16)*7//15 for j in (0,2,4))+(255,)
        frame.fill_rect(0,i*16,60,15,color)
        text(team['abbr'],3,i*16+5,small,white,26)
        score='--' if game['state']=='pre' or team.get('score') is None else str(team['score'])
        text(score,60-len(score)*6-3,i*16+2,large,white,59)
    text(game['league'].upper()+(' HOLD' if held else ''),64,2,small,(155,230,181,255))
    lines,line=[],''
    for word in ('DATA STALE' if stale else sports_headline(game,timezone_name)).split(' '):
        if len((line+' '+word).strip())>15 and line: lines.append(line);line=word
        else: line=(line+' '+word).strip()
    if line: lines.append(line)
    for i,value in enumerate(lines[:2]): text(value,64,13+i*10,small,white if i else gold)
    return frame
