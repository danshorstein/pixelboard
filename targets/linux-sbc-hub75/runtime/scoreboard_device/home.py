from __future__ import annotations

from shared_py.renderer import Clip, PixelBuffer, _draw_text


def home_frame(now, fonts, width=128, height=32):
    """Device-only clock composed with the existing bitmap text renderer."""
    frame = PixelBuffer(width, height)
    clip = Clip(0, 0, width, height)
    time = now.strftime('%I:%M %p').lstrip('0')
    date = f"{now.strftime('%a %b').upper()} {now.day}, {now.year}"
    for text, font, y, color in (
        (time, fonts['6x10'], 1, (70, 220, 255, 255)),
        (date, fonts['4x6'], 16, (255, 210, 100, 255)),
        ('A SCORES  SELECT MENU', fonts['4x6'], 25, (125, 150, 170, 255)),
    ):
        _draw_text(frame, font, text, width // 2, y, color, align='center', outer_clip=clip)
    return frame
