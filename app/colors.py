"""이미지 대표 색상 추출 + 색 거리(Lab ΔE) 계산 — 컬러 팔레트 검색용."""
from __future__ import annotations
import colorsys
import json
import math
import re

from PIL import Image

HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_hex(r, g, b) -> str:
    return "#%02x%02x%02x" % (r, g, b)


def _lab(rgb):
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    t = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116
    fx, fy, fz = t(x), t(y), t(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(a_rgb, b_rgb) -> float:
    la, lb = _lab(a_rgb), _lab(b_rgb)
    return math.dist(la, lb)


def _palette(sm: Image.Image, n: int):
    q = sm.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    cnt = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in cnt) or 1
    out = []
    for c, idx in cnt:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        for o in out:
            if delta_e(rgb, o[0]) < 12:
                o[1] += c / total
                break
        else:
            out.append([rgb, c / total])
    out.sort(key=lambda o: -o[1])
    return [[rgb_to_hex(*rgb), round(r, 3)] for rgb, r in out[:n]]


def _is_chromatic(s, l):
    return s >= 0.2 and 0.12 <= l <= 0.92


def _neutral_bin(l):
    return 0 if l < 0.3 else (2 if l > 0.75 else 1)      # 검정 / 회색 / 흰색 계열


def extract(im: Image.Image, n: int = 5):
    """대표색 최대 n개('p') + 이미지 면적 중 색상 계열별 비율('h': 10°씩 36칸, 'n': 검정·회색·흰색)."""
    sm = im.convert("RGB")
    sm.thumbnail((64, 64))
    hist, neu, tot = [0] * 36, [0, 0, 0], 0
    for r, g, b in sm.getdata():
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        tot += 1
        if _is_chromatic(s, l):
            hist[int(h * 360 // 10) % 36] += 1
        else:
            neu[_neutral_bin(l)] += 1
    tot = tot or 1
    return {"p": _palette(sm, n), "h": [round(x / tot, 3) for x in hist], "n": [round(x / tot, 3) for x in neu]}


def dumps(cols) -> str:
    return json.dumps(cols)


def loads(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def palette_of(raw):
    """저장된 값(예전 형식: 리스트 / 새 형식: dict) -> [[hex, 비율], ...]"""
    if isinstance(raw, dict):
        return raw.get("p", [])
    return raw or []


def is_current(raw) -> bool:
    return isinstance(raw, dict) and "h" in raw


MIN_SHARE = 0.30     # 그 색 계열이 이미지의 30% 이상이면 검색에 나온다
HUE_TOL = 30.0       # 유채색: 색상이 ±30° 이내면 같은 계열


def _target_class(hexv):
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in hex_to_rgb(hexv)))
    return ("c", h * 360) if _is_chromatic(s, l) else ("n", _neutral_bin(l))


def coverage(raw, target):
    """이미지에서 목표색과 같은 계열이 차지하는 비율(0~1)."""
    if not is_current(raw):
        return 0.0
    kind, v = _target_class(target)
    if kind == "n":
        return raw["n"][v]
    tot = 0.0
    for i, share in enumerate(raw["h"]):
        d = abs((i * 10 + 5) - v)
        d = min(d, 360 - d)
        if d <= HUE_TOL:
            tot += share
    return tot


def score(raw, targets):
    """모든 목표색 계열이 기준(30%) 이상이어야 함. 점수는 작을수록 좋음(= 점유율이 클수록), 아니면 None."""
    if not targets or not is_current(raw):
        return None
    need = min(MIN_SHARE, 0.9 / len(targets))
    tot = 0.0
    for t in targets:
        c = coverage(raw, t)
        if c < need:
            return None
        tot -= c
    return tot
