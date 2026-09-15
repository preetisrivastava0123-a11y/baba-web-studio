# ==============================================================
# 🎬 BABA WEB STUDIO: ADVANCED CLIMAX OUTRO ENGINE (climax.py)
# ==============================================================
import os
import re
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip

_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF"
    "\U00002B00-\U00002BFF"
    "]+",
    flags=re.UNICODE,
)

def _find_first_existing(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def _load_font(size, prefer_emoji=False):
    devanagari_candidates = [
        "C:/Windows/Fonts/Nirmala.ttf",
        "C:/Windows/Fonts/NirmalaB.ttf",
        "C:/Windows/Fonts/mangal.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansDevanagari-Regular.otf",
        "/System/Library/Fonts/Supplemental/Devanagari MT.ttf",
        "/System/Library/Fonts/Supplemental/Kohinoor Devanagari.ttc",
        "NotoSansDevanagari-Regular.ttf",
    ]
    emoji_candidates = [
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/noto/NotoColorEmoji.ttf",
        "/System/Library/Fonts/Apple Color Emoji.ttc",
    ]
    generic_candidates = [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]

    ordered = (emoji_candidates + devanagari_candidates) if prefer_emoji else \
              (devanagari_candidates + generic_candidates)

    path = _find_first_existing(ordered)
    if path is None:
        return ImageFont.load_default()

    try:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    except Exception:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            return ImageFont.load_default()

def _draw_mixed_text(draw, xy, text, text_font, emoji_font, fill):
    x, y = xy
    total_w = 0
    pos = 0
    for m in _EMOJI_PATTERN.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            draw.text((x + total_w, y), chunk, font=text_font, fill=fill)
            bbox = draw.textbbox((0, 0), chunk, font=text_font)
            total_w += bbox[2] - bbox[0]
        emoji_chunk = m.group()
        draw.text((x + total_w, y), emoji_chunk, font=emoji_font, fill=fill)
        bbox = draw.textbbox((0, 0), emoji_chunk, font=emoji_font)
        total_w += bbox[2] - bbox[0]
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        draw.text((x + total_w, y), chunk, font=text_font, fill=fill)
        bbox = draw.textbbox((0, 0), chunk, font=text_font)
        total_w += bbox[2] - bbox[0]
    return total_w

def _measure_mixed_text(draw, text, text_font, emoji_font):
    w = 0
    h = 0
    pos = 0
    for m in _EMOJI_PATTERN.finditer(text):
        if m.start() > pos:
            chunk = text[pos:m.start()]
            bbox = draw.textbbox((0, 0), chunk, font=text_font)
            w += bbox[2] - bbox[0]
            h = max(h, bbox[3] - bbox[1])
        emoji_chunk = m.group()
        bbox = draw.textbbox((0, 0), emoji_chunk, font=emoji_font)
        w += bbox[2] - bbox[0]
        h = max(h, bbox[3] - bbox[1])
        pos = m.end()
    if pos < len(text):
        chunk = text[pos:]
        bbox = draw.textbbox((0, 0), chunk, font=text_font)
        w += bbox[2] - bbox[0]
        h = max(h, bbox[3] - bbox[1])
    return w, h

def create_climax_outro_clip(duration=10.0, target_size=(1080, 1920), fps=24):
    w, h = target_size
    np.random.seed(101)

    colors = [
        (255, 50, 150),
        (0, 230, 255),
        (255, 215, 0),
        (50, 255, 100),
        (255, 100, 50),
        (200, 100, 255),
        (255, 255, 255),
    ]

    n_centers = 8
    burst_configs = []
    for i in range(n_centers):
        burst_configs.append({
            "cx": int(w * np.random.uniform(0.15, 0.85)),
            "cy": int(h * np.random.uniform(0.10, 0.40)),
            "color": colors[i % len(colors)],
            "delay": (duration / n_centers) * i * 0.5,
            "period": np.random.uniform(1.6, 2.6),
        })

    sparks = []
    for cfg in burst_configs:
        for _ in range(45):
            sparks.append({
                "cx": cfg["cx"],
                "cy": cfg["cy"],
                "angle": np.random.uniform(0, 2 * math.pi),
                "speed": np.random.uniform(200, 700),
                "color": cfg["color"],
                "delay": cfg["delay"],
                "period": cfg["period"],
            })

    fountains = []
    for _ in range(70):
        fountains.append({
            "x": np.random.uniform(w * 0.08, w * 0.92),
            "speed_y": np.random.uniform(-950, -500),
            "speed_x": np.random.uniform(-100, 100),
            "color": colors[np.random.randint(0, len(colors))],
            "period": np.random.uniform(1.8, 2.4),
            "phase": np.random.uniform(0, 2.0),
        })

    floating_items = [
        {"text": "\U0001F44D LIKE", "bg": (0, 122, 255), "x": int(w * 0.15), "speed": 170, "phase": 0.0},
        {"text": "\U0001F514 BELL", "bg": (255, 149, 0), "x": int(w * 0.38), "speed": 205, "phase": 1.3},
        {"text": "\U0001F534 SUBSCRIBE", "bg": (255, 45, 85), "x": int(w * 0.62), "speed": 185, "phase": 0.7},
        {"text": "\u2197\uFE0F SHARE", "bg": (52, 199, 89), "x": int(w * 0.85), "speed": 200, "phase": 1.9},
    ]

    font_large = _load_font(38, prefer_emoji=False)
    font_large_emoji = _load_font(38, prefer_emoji=True)
    font_btn = _load_font(24, prefer_emoji=False)
    font_btn_emoji = _load_font(24, prefer_emoji=True)

    def make_frame(t):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 1. आतिशबाजी (Fireworks)
        for s in sparks:
            rel_t = t - s["delay"]
            if rel_t <= 0:
                continue
            cycle_t = rel_t % s["period"]
            dist = s["speed"] * cycle_t
            px = int(s["cx"] + dist * math.cos(s["angle"]))
            py = int(s["cy"] + dist * math.sin(s["angle"]) + 120 * (cycle_t ** 2))
            tail_x = int(px - 25 * math.cos(s["angle"]))
            tail_y = int(py - 25 * math.sin(s["angle"]))
            if 0 <= px < w and 0 <= py < h:
                alpha = max(0, int(255 * (1 - cycle_t / s["period"])))
                draw.line([(tail_x, tail_y), (px, py)], fill=s["color"] + (alpha,), width=4)
                draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 255, 255, alpha))

        # 2. फाउंटेन पार्टिकल्स (Fountains)
        for f in fountains:
            ft = (t + f["phase"]) % f["period"]
            fx = int(f["x"] + f["speed_x"] * ft)
            fy = int(h * 0.88 + f["speed_y"] * ft + 350 * (ft ** 2))
            if 0 <= fx < w and 0 <= fy < h:
                alpha = max(0, int(220 * (1 - ft / f["period"])))
                draw.ellipse([fx - 3, fy - 3, fx + 3, fy + 3], fill=f["color"] + (alpha,))

        # 3. गिरते हुए बेज (Badges: Like, Share, Subscribe)
        for item in floating_items:
            curr_y = int(((t + item["phase"]) * item["speed"]) % (h + 100)) - 50
            curr_x = int(item["x"] + 20 * math.sin(t * 3 + item["phase"]))

            bw, bh = 190, 50
            draw.rounded_rectangle(
                [curr_x - bw // 2 + 3, curr_y + 3, curr_x + bw // 2 + 3, curr_y + bh + 3],
                radius=15, fill=(0, 0, 0, 120),
            )
            draw.rounded_rectangle(
                [curr_x - bw // 2, curr_y, curr_x + bw // 2, curr_y + bh],
                radius=15, fill=item["bg"] + (240,), outline=(255, 255, 255, 255), width=2,
            )
            text_w, text_h = _measure_mixed_text(draw, item["text"], font_btn, font_btn_emoji)
            tx = curr_x - text_w // 2
            ty = curr_y + (bh - text_h) // 2
            _draw_mixed_text(draw, (tx, ty), item["text"], font_btn, font_btn_emoji, fill=(255, 255, 255, 255))

        # 4. मुख्य हिंदी CTA बैनर (Bottom Card)
        pulse = 1.0 + 0.04 * math.sin(t * 8)
        bw, bh = int(w * 0.90), int(130 * pulse)
        bx = (w - bw) // 2
        by = int(h * 0.82)

        draw.rounded_rectangle(
            [bx + 4, by + 6, bx + bw + 4, by + bh + 6], radius=22, fill=(0, 0, 0, 180)
        )
        draw.rounded_rectangle(
            [bx, by, bx + bw, by + bh], radius=22, fill=(210, 20, 30, 250),
            outline=(255, 215, 0, 255), width=5,
        )

        text = "\U0001F514 लाइक और सब्सक्राइब जरूर करें!"
        text_w, text_h = _measure_mixed_text(draw, text, font_large, font_large_emoji)
        tx = bx + (bw - text_w) // 2
        ty = by + (bh - text_h) // 2
        _draw_mixed_text(draw, (tx, ty), text, font_large, font_large_emoji, fill=(255, 255, 255, 255))

        return np.array(img)

    return VideoClip(make_frame, duration=duration).with_fps(fps)
