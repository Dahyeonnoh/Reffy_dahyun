"""이미지의 Safebooru 태그를 보고 라벨링 키워드를 '추천'합니다. 추천은 눌러야 선택됩니다.

규칙
1. 키워드의 원본 태그(시트의 Safebooru 태그 칸)가 이미지 태그에 있으면 후보.
2. 인원은 태그 숫자를 합산해 계산합니다 (1girl + 1boy = 2명, 3girls = 3명 …).
   multiple_girls 처럼 숫자가 없는 태그는 몇 명인지 모르므로 추천하지 않습니다.
3. 같은 묶음(축) 안에서 한 태그가 여러 키워드에 걸리면(from_above → 하이앵글/버드아이) 시트에서 앞에 있는 것만.
4. 한 태그가 서로 다른 묶음에 걸려 있으면(nature → 머리 자연물/배경 자연) 어느 쪽인지 알 수 없어 추천하지 않습니다.
5. '단일' 축에서 서로 다른 후보가 둘 이상이면(1girl 과 1boy 가 같이 있는 성별 등) 사람이 판단하도록 추천하지 않습니다.
"""
import re

COUNT_TAG = re.compile(r"^(\d)(\+?)(girl|boy|other)s?$")
COUNT_KEYS = ["count_1", "count_2", "count_3", "count_4", "count_5over"]


def people_count(tags) -> int:
    """태그에서 인원수를 계산합니다. 알 수 없으면 0."""
    total = 0
    for t in tags:
        m = COUNT_TAG.match(t)
        if m:
            total += int(m.group(1))
    if total == 0 and "solo" in tags:
        total = 1
    return total


def suggest(tags, vocab):
    """vocab: 사용 중인 키워드 행들(keyword, category, path, mode, aliases, ikey, ord).
    반환: (추천 키워드 목록, {키워드: 근거 태그})"""
    tagset = {t.lower() for t in tags}
    cand = {}  # keyword -> (row, 근거 태그)
    for v in vocab:
        hit = next((t for t in (v["aliases"] or "").split() if t in tagset), None)
        if hit and not str(v.get("ikey") or "").startswith("count_"):
            cand[v["keyword"]] = (v, hit)
    n = people_count(tagset)
    if n:
        key = COUNT_KEYS[min(n, 5) - 1]
        for v in vocab:
            if v.get("ikey") == key:
                cand[v["keyword"]] = (v, f"인원 {n}명" if n < 6 else "인원 5명 이상")
    axis = lambda v: (v["category"], v.get("path") or "")
    # 사전 전체에서 한 태그가 서로 다른 묶음에 걸려 있으면 추천하지 않음
    tag_axes = {}
    for v in vocab:
        for t in (v["aliases"] or "").split():
            tag_axes.setdefault(t, set()).add(axis(v))
    cand = {k: (v, t) for k, (v, t) in cand.items() if len(tag_axes.get(t, ())) <= 1 or t.startswith("인원")}
    # 같은 축 안에서 태그가 겹치면 시트 순서가 앞선 것만
    by_axis_tag = {}
    for kw, (v, tag) in cand.items():
        by_axis_tag.setdefault((axis(v), tag), []).append(v)
    drop = set()
    for lst in by_axis_tag.values():
        for v in sorted(lst, key=lambda r: r.get("ord", 0))[1:]:
            drop.add(v["keyword"])
    # 단일 축에 서로 다른 후보가 둘 이상이면 모두 보류
    by_axis = {}
    for kw, (v, tag) in cand.items():
        if kw not in drop:
            by_axis.setdefault(axis(v), []).append(v)
    for lst in by_axis.values():
        if len(lst) > 1 and all(v.get("mode") == "단일" for v in lst):
            drop.update(v["keyword"] for v in lst)
    out = sorted((kw for kw in cand if kw not in drop), key=lambda k: cand[k][0].get("ord", 0))
    return out, {kw: cand[kw][1] for kw in out}
