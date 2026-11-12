"""검색어 -> 태그 매핑과 이미지 검색. 검색 방식: 태그 일치(한국어 키워드·시트 설명·Safebooru 태그) + 이미지의 WD 원본 태그/제목 문자열."""
from __future__ import annotations
import json
import re

from . import config, db
from .tagmap import BY_IKEY, VOCAB, axis

# 말투를 그대로 친 검색어를 키워드로 연결하는 작은 동의어 (필요하면 계속 추가하세요)
SYN = {"앉은": ["pose_sitting"], "앉아": ["pose_sitting"], "앉아있는": ["pose_sitting"], "앉기": ["pose_sitting"],
       "선": ["pose_standing"], "서있는": ["pose_standing"], "서있기": ["pose_standing"], "서기": ["pose_standing"], "서있": ["pose_standing"],
       "뒤돌아": ["face_back_three_quarter", "face_back"], "뒤돌아보기": ["face_back_three_quarter"], "뒷모습": ["face_back"], "후면": ["face_back", "face_back_three_quarter"],
       "정면": ["face_front"], "측면": ["face_profile", "face_three_quarter"], "옆모습": ["face_profile"],
       "전신": ["shot_full"], "상반신": ["shot_upper"], "얼굴": ["shot_head"], "클로즈업": ["shot_head"],
       "로우앵글": ["angle_low"], "로우": ["angle_low"], "하이앵글": ["angle_high"], "아래에서": ["angle_low"], "위에서": ["angle_high"],
       "웃는": ["emo_joy"], "웃음": ["emo_joy"], "미소": ["emo_joy"], "우는": ["emo_sad", "fx_tears"],
       "교복": ["outfit_school"], "갑옷": ["outfit_armor"], "한복": ["outfit_traditional_clothes"], "수영복": ["outfit_swimsuit"],
       "안경": ["acc_glasses"], "모자": ["acc_hat"], "긴머리": ["hair_long_hair", "hair_very_long_hair"], "단발": ["hair_short_hair"],
       "트윈테일": ["hairstyle_twintails"], "포니테일": ["hairstyle_ponytail"], "꼬리": ["nonhuman_tail"], "고양이귀": ["nonhuman_animal_ears"],
       "실내": ["bg_indoor"], "도시": ["bg_city"], "하늘": ["bg_sky"], "밤": ["bg_night"], "노을": ["bg_sunset"], "비": ["weather_rain"], "눈": ["weather_snow"]}
JOSA = re.compile(r"(이|가|은|는|을|를|의|에|에서|으로|로|과|와|도|인|한|된|하는|있는|입은|쓴|든)$")


def norm(s: str) -> str:
    return re.sub(r"[\s#_\-]+", "", s.lower())


_INDEX = None


def _index():
    global _INDEX
    if _INDEX is None:
        _INDEX = [(v["ikey"], norm(v["label"]), norm(v["keyword"]), [norm(p) for p in v["parts"]], [norm(a) for a in v["aliases"].split()], norm(v["note"])) for v in VOCAB]
    return _INDEX


def match_tags(token: str) -> dict:
    """검색어 한 토큰 -> {ikey: 가중치}. 이름 일치 > 묶음 이름 > 영어 태그 > 설명 일치."""
    t = norm(token)
    if not t:
        return {}
    cands = {t, JOSA.sub("", t)} if len(t) >= 3 else {t}
    out = {}
    for c in list(cands):
        for ik in SYN.get(c, []):
            out[ik] = max(out.get(ik, 0), 1.0)
    for ik, label, kw, parts, aliases, note in _index():
        for c in cands:
            if not c:
                continue
            w = 0
            if c == label or c == kw:
                w = 1.0
            elif len(c) >= 2 and (c in label or (len(label) >= 2 and label in c)):
                w = 0.8
            elif len(c) >= 2 and any(c == p for p in parts):
                w = 0.5
            elif c in aliases:
                w = 0.7
            elif len(c) >= 2 and note and c in note:
                w = 0.3
            if w:
                out[ik] = max(out.get(ik, 0), w)
    return out


def parse_query(q: str):
    tokens = [t for t in re.split(r"[\s,]+", q.strip()) if t]
    return tokens, [match_tags(t) for t in tokens]


def search(q: str, tags: list, sort: str, offset: int, limit: int):
    """반환: (이미지 id 목록, 전체 개수, 검색어에서 찾은 태그 ikey 목록)"""
    thr = config.TAG_THRESHOLD
    ids = None
    # 체크한 태그: 같은 축 안은 OR, 축끼리는 AND
    if tags:
        groups = {}
        for ik in tags:
            v = BY_IKEY.get(ik)
            if v:
                groups.setdefault(axis(v), []).append(ik)
        for g in groups.values():
            ph = ",".join(f":k{i}" for i in range(len(g)))
            r = db.rows(f"SELECT DISTINCT t.image_id FROM image_tags t WHERE t.ikey IN ({ph}) AND {db.ACTIVE}", thr=thr, **{f"k{i}": k for i, k in enumerate(g)})
            s = {x["image_id"] for x in r}
            ids = s if ids is None else ids & s
    score, found = None, []
    tokens, maps = parse_query(q) if q.strip() else ([], [])
    if tokens:
        wd_rows = {r["id"]: r for r in db.rows("SELECT id, title, wd_json FROM images")}
        allk = {k for m in maps for k in m}
        act = {}
        if allk:
            ph = ",".join(f":k{i}" for i in range(len(allk)))
            for r in db.rows(f"SELECT t.image_id, t.ikey, t.ai_prob, t.user_state FROM image_tags t WHERE t.ikey IN ({ph}) AND {db.ACTIVE}", thr=thr, **{f"k{i}": k for i, k in enumerate(allk)}):
                act.setdefault(r["image_id"], {})[r["ikey"]] = 1.0 if r["user_state"] == "add" else float(r["ai_prob"] or 0.5)
        score = {}
        for iid, row in wd_rows.items():
            have = act.get(iid, {})
            wd = json.loads(row["wd_json"] or "{}")
            hit, total = 0, 0.0
            for tok, m in zip(tokens, maps):
                best = max(((w * (0.5 + 0.5 * have[ik])) for ik, w in m.items() if ik in have), default=0)
                if not best:   # 태그로 못 찾으면 제목·WD 영어 태그 문자열로
                    nt = norm(tok)
                    if len(nt) >= 2 and (nt in norm(row["title"] or "") or any(nt == norm(x) for x in wd)):
                        best = 0.4
                if best:
                    hit += 1
                    total += best
            if hit:
                score[iid] = (hit, total)
        for m in maps:
            found += [k for k in m if k not in found]
        ids = set(score) if ids is None else ids & set(score)
    if ids is None:
        order = {"recent": "id DESC", "popular": "views DESC, id DESC", "relevance": "id DESC"}.get(sort, "id DESC")
        total = db.rows("SELECT COUNT(*) AS n FROM images")[0]["n"]
        page = db.rows(f"SELECT id FROM images ORDER BY {order} LIMIT :l OFFSET :o", l=limit, o=offset)
        return [r["id"] for r in page], total, found
    lst = list(ids)
    if sort == "relevance" and score:
        lst.sort(key=lambda i: (-score.get(i, (0, 0))[0], -score.get(i, (0, 0))[1], -i))
    elif sort == "popular":
        views = {r["id"]: r["views"] for r in db.rows("SELECT id, views FROM images")}
        lst.sort(key=lambda i: (-views.get(i, 0), -i))
    else:
        lst.sort(reverse=True)
    return lst[offset:offset + limit], len(lst), found
