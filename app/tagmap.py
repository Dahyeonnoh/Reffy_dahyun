"""태그 사전(ia.json = 라벨링 기준표)과 이미지 태깅 파이프라인.

이미지 -> WD tagger 태그 확률 -> (1) 기준표 Safebooru 태그 매핑 (2) 팀 분류기 -> 키워드(ikey) 후보
-> 같은 단일 축은 가장 확률 높은 하나만 -> AI 태그.
"""
from __future__ import annotations
import json

from . import config
from .classifier import C
from .suggest import suggest
from .tagger import T

IA = json.loads((config.DATA / "ia.json").read_text(encoding="utf-8"))
VOCAB = [{"keyword": it["keyword"], "category": it["group"], "path": "|".join(it["path"]), "mode": it["mode"],
          "aliases": it["tags"], "ikey": it["key"], "ord": it["ord"], "label": it["label"], "note": it.get("note", ""),
          "parts": it["path"]} for it in IA["items"]]
BY_IKEY = {v["ikey"]: v for v in VOCAB}
BY_KEYWORD = {v["keyword"]: v for v in VOCAB}


def axis(v) -> tuple:
    return (v["category"], v["path"])


def tag_image(im) -> dict:
    """반환: {"tags": [{ikey, prob, src}], "wd": {태그: 확률}(화면 비노출, 검색용)}"""
    wd = T.predict(im) if T.ready else {}
    cands = {}   # ikey -> (prob, src)
    if wd:
        hit = [t for t, p in wd.items() if p >= config.WD_THRESHOLD]
        kws, why = suggest(hit, VOCAB)
        for k in kws:
            v = BY_KEYWORD[k]
            cands[v["ikey"]] = (wd.get(why[k], 0.9), "wd")
        for k, p in C.predict(wd).items():
            v = BY_KEYWORD.get(k)
            if v is not None:
                old = cands.get(v["ikey"], (0, ""))[0]
                cands[v["ikey"]] = (max(p, old), "team")
    # 단일 축: 가장 확률 높은 하나만
    best = {}
    for ik, (p, s) in cands.items():
        v = BY_IKEY[ik]
        if v["mode"] == "단일":
            a = axis(v)
            if a not in best or p > cands[best[a]][0]:
                best[a] = ik
    out = []
    for ik, (p, s) in cands.items():
        v = BY_IKEY[ik]
        if v["mode"] == "단일" and best[axis(v)] != ik:
            continue
        out.append({"ikey": ik, "prob": round(float(p), 3), "src": s})
    out.sort(key=lambda r: BY_IKEY[r["ikey"]]["ord"])
    top = sorted(((t, p) for t, p in wd.items() if p >= config.WD_THRESHOLD), key=lambda kv: -kv[1])[:40]
    return {"tags": out, "wd": dict(top)}
