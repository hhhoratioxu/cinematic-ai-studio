"""Select a local CJK font without redistributing proprietary font files."""
from __future__ import annotations

import os
from pathlib import Path

from common import CinemaError


def select_font(spec, needed=True):
    from PIL import ImageFont
    candidates = [spec.font_file, os.environ.get("CINEMA_FONT")]
    candidates += [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf",
                   "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]
    for value in candidates:
        if value and Path(value).is_file():
            font = ImageFont.truetype(str(value), 32)
            return spec.model_copy(update={"font_file": str(Path(value).resolve()),
                                            "font_name": font.getname()[0]})
    if needed:
        raise CinemaError("CJK subtitle font not found; set output.font_file or CINEMA_FONT to a licensed "
                          "Chinese font (e.g. Noto Sans CJK). No font is downloaded automatically.")
    return spec
