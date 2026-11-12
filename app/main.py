"""REFFY — 레퍼런스 검색 서비스 (MVP): 업로드 -> AI 태깅 -> 태그·검색어로 찾기."""
from __future__ import annotations
import io
import json
import secrets
import time
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlalchemy import text

from . import colors as colormod, config, db, social
from .classifier import C
from .search import match_tags, search
from .tagger import T
from .tagmap import BY_IKEY, IA, VOCAB, tag_image

app = FastAPI(title="REFFY")
app.include_router(social.router)
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


@app.on_event("startup")
def _start():
    db.init()
    _backfill_colors()
    T.start([v["aliases"] for v in VOCAB])
    C.load()


def _backfill_colors():
    """대표색이 아직 없는 이미지(이전 버전에서 올린 것)를 채운다."""
    for r in db.rows("SELECT id, file, colors FROM images"):
        if colormod.is_current(colormod.loads(r["colors"])):
            continue
        f = config.UPLOADS / f"t_{r['id']}.jpg"
        f = f if f.exists() else config.UPLOADS / r["file"]
        try:
            with Image.open(f) as im:
                cols = colormod.extract(im)
        except Exception:
            cols = []
        with db.engine.begin() as c:
            c.execute(text("UPDATE images SET colors = :c WHERE id = :i"), {"c": colormod.dumps(cols), "i": r["id"]})


def _open(data: bytes) -> Image.Image:
    if len(data) > config.MAX_UPLOAD_MB << 20:
        raise HTTPException(413, f"이미지는 {config.MAX_UPLOAD_MB}MB 이하만 올릴 수 있어요.")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "이미지 파일을 읽을 수 없어요. JPG, PNG, WEBP, GIF 파일을 올려 주세요.")
    if im.format not in FORMATS:
        raise HTTPException(400, "JPG, PNG, WEBP, GIF 파일만 올릴 수 있어요.")
    return im


def _public_tag(ikey: str, prob, src, state, active: bool) -> dict:
    v = BY_IKEY[ikey]
    return {"ikey": ikey, "label": v["keyword"], "keyword": v["keyword"], "group": v["category"], "path": v["parts"],
            "prob": prob, "src": src, "user": state, "active": active}


def _tags_of(image_id: int) -> list:
    out = []
    for r in db.rows("SELECT ikey, ai_prob, ai_src, user_state FROM image_tags WHERE image_id = :i", i=image_id):
        if r["ikey"] not in BY_IKEY:
            continue
        active = r["user_state"] == "add" or (r["user_state"] is None and (r["ai_prob"] or 0) >= config.TAG_THRESHOLD)
        out.append(_public_tag(r["ikey"], r["ai_prob"], r["ai_src"], r["user_state"], active))
    out.sort(key=lambda t: BY_IKEY[t["ikey"]]["ord"])
    return out


def _card(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "author": r["author"], "w": r["w"], "h": r["h"], "views": r["views"],
            "thumb": f"/img/{r['id']}?s=thumb", "created": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])}


# ------------------------------------------------------------------ 태그 사전·상태
@app.get("/api/vocab")
def vocab():
    """필터 패널용: 분류 > 축 > 태그(+이미지 수)."""
    cnt = {r["ikey"]: r["n"] for r in db.rows(
        f"SELECT t.ikey, COUNT(*) AS n FROM image_tags t WHERE {db.ACTIVE} GROUP BY t.ikey", thr=config.TAG_THRESHOLD)}
    groups = []
    for v in VOCAB:
        g = next((x for x in groups if x["name"] == v["category"]), None)
        if g is None:
            groups.append((g := {"name": v["category"], "axes": []}))
        an = " › ".join(v["parts"])
        a = next((x for x in g["axes"] if x["name"] == an), None)
        if a is None:
            g["axes"].append((a := {"name": an, "mode": v["mode"], "tags": []}))
        a["tags"].append({"ikey": v["ikey"], "label": v["label"], "kw": v["keyword"], "n": cnt.get(v["ikey"], 0)})
    total = db.rows("SELECT COUNT(*) AS n FROM images")[0]["n"]
    return {"groups": groups, "total": total}


@app.get("/api/popular")
def popular():
    r = db.rows(f"SELECT t.ikey, COUNT(*) AS n FROM image_tags t WHERE {db.ACTIVE} GROUP BY t.ikey ORDER BY n DESC LIMIT 10", thr=config.TAG_THRESHOLD)
    return [{"ikey": x["ikey"], "label": BY_IKEY[x["ikey"]]["keyword"], "n": x["n"]} for x in r if x["ikey"] in BY_IKEY]


@app.get("/api/status")
def status():
    return {"tagger": {"status": T.status, "message": T.message, "model": T.model_id, "mock": T.mock},
            "classifier": {"ready": C.ready, "keywords": len(C.models), "message": C.error, "info": C.info if C.ready else {}},
            "images": db.rows("SELECT COUNT(*) AS n FROM images")[0]["n"], "threshold": config.TAG_THRESHOLD}


# ------------------------------------------------------------------ 피드·검색
@app.get("/api/images")
def list_images(q: str = "", tags: str = "", sort: str = "", offset: int = 0, limit: int = config.PAGE, color: str = ""):
    tl = [t for t in tags.split(",") if t]
    cl = [("#" + c.lstrip("#")).lower() for c in color.split(",") if colormod.HEX.match(c.strip())][:5]
    sort = sort or ("relevance" if (q.strip() or cl) else "recent")
    offset, limit = max(0, offset), min(max(1, limit), 100)
    if cl:   # 색을 지정하면 그 색이 들어 있는 이미지만, 가까운 순(또는 선택한 정렬)으로
        all_ids, _, found = search(q, tl, sort, 0, 100000)
        pal = {r["id"]: colormod.loads(r["colors"]) for r in db.rows("SELECT id, colors FROM images")}
        sc = {i: colormod.score(pal.get(i), cl) for i in all_ids}
        ids_all = [i for i in all_ids if sc[i] is not None]
        if sort == "relevance":      # 선택한 색에 가까운 순
            ids_all.sort(key=lambda i: sc[i])
        total = len(ids_all)
        ids = ids_all[offset:offset + limit]
    else:
        ids, total, found = search(q, tl, sort, offset, limit)
    cards = []
    if ids:
        ph = ",".join(f":i{n}" for n in range(len(ids)))
        by = {r["id"]: r for r in db.rows(f"SELECT id, title, author, w, h, views, created_at FROM images WHERE id IN ({ph})", **{f"i{n}": i for n, i in enumerate(ids)})}
        cards = [_card(by[i]) for i in ids if i in by]
    return {"items": cards, "total": total, "sort": sort, "colors": cl,
            "matched": [{"ikey": k, "label": BY_IKEY[k]["keyword"]} for k in found[:8] if k in BY_IKEY] if q.strip() else []}


@app.get("/api/images/{image_id}/colors")
def image_colors(image_id: int):
    r = db.rows("SELECT colors FROM images WHERE id = :i", i=image_id)
    if not r:
        raise HTTPException(404, "이미지를 찾을 수 없어요.")
    return {"colors": colormod.palette_of(colormod.loads(r[0]["colors"]))[:5]}


@app.get("/api/images/{image_id}")
def detail(image_id: int, request: Request):
    r = db.rows("SELECT id, title, author, w, h, views, created_at FROM images WHERE id = :i", i=image_id)
    if not r:
        raise HTTPException(404, "이미지를 찾을 수 없어요.")
    with db.engine.begin() as c:
        c.execute(text("UPDATE images SET views = views + 1 WHERE id = :i"), {"i": image_id})
    social.record_view(request, image_id)
    d = _card(r[0])
    d["views"] += 1
    d["full"] = f"/img/{image_id}?s=full"
    d["tags"] = _tags_of(image_id)
    d["colors"] = colormod.palette_of(colormod.loads((db.rows("SELECT colors FROM images WHERE id = :i", i=image_id) or [{}])[0].get("colors")))
    return d


@app.get("/img/{image_id}")
def image_file(image_id: int, s: str = "thumb"):
    r = db.rows("SELECT file FROM images WHERE id = :i", i=image_id)
    if not r:
        raise HTTPException(404)
    f = r[0]["file"]
    p = (config.UPLOADS / ("t_" + f.rsplit(".", 1)[0] + ".jpg")) if s == "thumb" else (config.UPLOADS / f)
    if not p.exists():
        p = config.UPLOADS / f
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


# ------------------------------------------------------------------ 업로드: 분석 -> (태그 수정) -> 게시
@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    data = await file.read()
    im = _open(data)
    ext = FORMATS[im.format]
    token = secrets.token_hex(12)
    (config.TMP / f"{token}.{ext}").write_bytes(data)
    t0 = time.time()
    res = tag_image(ImageOps.exif_transpose(im))
    tags = [_public_tag(t["ikey"], t["prob"], t["src"], None, t["prob"] >= config.TAG_THRESHOLD) for t in res["tags"]]
    (config.TMP / f"{token}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return {"token": token, "tags": tags, "seconds": round(time.time() - t0, 2),
            "aiReady": T.ready, "message": "" if T.ready else "AI 태깅 모델이 아직 준비되지 않았어요. 태그를 직접 골라 주세요."}


class PublishIn(BaseModel):
    token: str
    title: str = ""
    kind: str = "illust"           # illust(일러스트) / photo(사진)
    tags: List[str] = []          # 사용자가 최종 확정한 ikey 목록


@app.post("/api/images")
def publish(body: PublishIn, request: Request):
    user = social.need(request)
    tok = "".join(ch for ch in body.token if ch.isalnum())
    files = list(config.TMP.glob(f"{tok}.*"))
    img_f = next((f for f in files if f.suffix != ".json"), None)
    if not tok or img_f is None:
        raise HTTPException(400, "업로드가 만료됐어요. 이미지를 다시 올려 주세요.")
    res = json.loads((config.TMP / f"{tok}.json").read_text(encoding="utf-8")) if (config.TMP / f"{tok}.json").exists() else {"tags": [], "wd": {}}
    im = _open(img_f.read_bytes())
    im = ImageOps.exif_transpose(im)
    with db.engine.begin() as c:
        rid = c.execute(db.images.insert().values(title=body.title.strip()[:120], author=user["nick"], user_id=user["id"], kind="photo" if body.kind == "photo" else "illust", file="pending",
                                                  w=im.width, h=im.height, views=0, wd_json=json.dumps(res.get("wd", {}), ensure_ascii=False)))
        iid = rid.inserted_primary_key[0]
        name = f"{iid}.{img_f.suffix[1:]}"
        c.execute(text("UPDATE images SET file = :f WHERE id = :i"), {"f": name, "i": iid})
        ai = {t["ikey"]: t for t in res["tags"]}
        final = {k for k in body.tags if k in BY_IKEY}
        for ik in set(ai) | final:
            a = ai.get(ik)
            ai_on = a is not None and a["prob"] >= config.TAG_THRESHOLD
            state = "add" if (ik in final and not ai_on) else ("del" if (ik not in final and ai_on) else None)
            c.execute(db.image_tags.insert().values(image_id=iid, ikey=ik, ai_prob=a["prob"] if a else None, ai_src=a["src"] if a else None, user_state=state))
    img_f.replace(config.UPLOADS / name)
    with db.engine.begin() as c:
        c.execute(text("UPDATE images SET colors = :c WHERE id = :i"), {"c": colormod.dumps(colormod.extract(im)), "i": iid})
    thumb = im.convert("RGB")
    thumb.thumbnail((520, 1400))
    thumb.save(config.UPLOADS / f"t_{iid}.jpg", "JPEG", quality=85)
    for f in files:
        f.unlink(missing_ok=True)
    return {"id": iid}


class TagEdit(BaseModel):
    add: List[str] = []
    remove: List[str] = []
    restore: List[str] = []       # 사용자 수정을 취소하고 AI 판단으로 되돌림


@app.put("/api/images/{image_id}/tags")
def edit_tags(image_id: int, body: TagEdit, request: Request):
    user = social.need(request)
    own = db.rows("SELECT user_id FROM images WHERE id = :i", i=image_id)
    if not own:
        raise HTTPException(404, "이미지를 찾을 수 없어요.")
    if own[0]["user_id"] not in (None, user["id"]):
        raise HTTPException(403, "내가 올린 게시물만 수정할 수 있어요.")
    with db.engine.begin() as c:
        for ik in body.add:
            if ik in BY_IKEY:
                n = c.execute(text("UPDATE image_tags SET user_state = 'add' WHERE image_id = :i AND ikey = :k"), {"i": image_id, "k": ik}).rowcount
                if not n:
                    c.execute(db.image_tags.insert().values(image_id=image_id, ikey=ik, user_state="add"))
        for ik in body.remove:
            c.execute(text("UPDATE image_tags SET user_state = 'del' WHERE image_id = :i AND ikey = :k"), {"i": image_id, "k": ik})
        for ik in body.restore:
            c.execute(text("UPDATE image_tags SET user_state = NULL WHERE image_id = :i AND ikey = :k"), {"i": image_id, "k": ik})
        c.execute(text("DELETE FROM image_tags WHERE image_id = :i AND ai_prob IS NULL AND (user_state IS NULL OR user_state = 'del')"), {"i": image_id})
    return {"tags": _tags_of(image_id)}


@app.delete("/api/images/{image_id}")
def delete_image(image_id: int, request: Request):
    user = social.need(request)
    r = db.rows("SELECT file, user_id FROM images WHERE id = :i", i=image_id)
    if not r:
        raise HTTPException(404)
    if r[0]["user_id"] not in (None, user["id"]):
        raise HTTPException(403, "내가 올린 게시물만 삭제할 수 있어요.")
    with db.engine.begin() as c:
        for t in ("image_tags", "likes", "comments", "keeps", "book_items", "views", "notifications"):
            c.execute(text(f"DELETE FROM {t} WHERE " + ("image_id" if t != "image_tags" else "image_id") + " = :i"), {"i": image_id})
        c.execute(text("DELETE FROM images WHERE id = :i"), {"i": image_id})
    for p in (config.UPLOADS / r[0]["file"], config.UPLOADS / f"t_{image_id}.jpg"):
        p.unlink(missing_ok=True)
    return {"ok": True}


app.mount("/", StaticFiles(directory=str(config.BASE / "static"), html=True), name="static")
