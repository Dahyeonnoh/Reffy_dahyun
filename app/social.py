"""계정(로그인·회원가입)과 소셜 기능: 하트·댓글·팔로우·킵 스페이스·서랍(레퍼런스 북)·알림."""
from __future__ import annotations
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta
from typing import List, Optional

import io
import json

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel
from sqlalchemy import text

from . import config, db

router = APIRouter(prefix="/api")
COOKIE = "reffy_session"
UID_RE = re.compile(r"^[A-Za-z0-9]{6,20}$")


# ------------------------------------------------------------------ 비밀번호·세션
def _hash(pw: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${h}"


def _verify(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash(pw, salt).split("$", 1)[1], h)


def me(request: Request) -> Optional[dict]:
    tok = request.cookies.get(COOKIE)
    if not tok:
        return None
    r = db.rows("SELECT u.id, u.uid, u.nick, u.avatar FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = :t", t=tok)
    return r[0] if r else None


def need(request: Request) -> dict:
    u = me(request)
    if not u:
        raise HTTPException(401, "로그인이 필요해요.")
    return u


def _start_session(resp: Response, user_id: int, keep: bool) -> None:
    tok = secrets.token_urlsafe(32)
    with db.engine.begin() as c:
        c.execute(db.sessions.insert().values(token=tok, user_id=user_id))
    resp.set_cookie(COOKIE, tok, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30 if keep else None, path="/")


# ------------------------------------------------------------------ 로그인·회원가입
class SignupIn(BaseModel):
    nick: str
    uid: str
    pw: str
    pw2: str
    terms: bool = False
    privacy: bool = False
    marketing: bool = False


class LoginIn(BaseModel):
    uid: str
    pw: str
    keep: bool = True


def _nick_error(nick: str) -> str:
    nick = nick.strip()
    if not 2 <= len(nick) <= 20:
        return "닉네임은 2~20자로 입력해 주세요."
    if db.rows("SELECT id FROM users WHERE lower(nick) = lower(:n)", n=nick):
        return "이미 사용 중인 닉네임이에요."
    return ""


@router.get("/auth/nick-check")
def nick_check(nick: str = ""):
    err = _nick_error(nick)
    return {"ok": not err, "message": err or "사용할 수 있는 닉네임이에요."}


@router.post("/auth/signup")
def signup(body: SignupIn, resp: Response):
    nick = body.nick.strip()
    if err := _nick_error(nick):
        raise HTTPException(400, err)
    if not UID_RE.match(body.uid):
        raise HTTPException(400, "아이디는 영문과 숫자 6~20자로 입력해 주세요.")
    if db.rows("SELECT id FROM users WHERE lower(uid) = lower(:u)", u=body.uid):
        raise HTTPException(400, "이미 사용 중인 아이디예요.")
    if len(body.pw) < 8 or not re.search(r"[A-Za-z]", body.pw) or not re.search(r"\d", body.pw):
        raise HTTPException(400, "비밀번호는 영문과 숫자를 포함해 8자 이상이어야 해요.")
    if body.pw != body.pw2:
        raise HTTPException(400, "비밀번호가 서로 달라요.")
    if not (body.terms and body.privacy):
        raise HTTPException(400, "필수 약관에 동의해 주세요.")
    with db.engine.begin() as c:
        uid = c.execute(db.users.insert().values(uid=body.uid, nick=nick, pw_hash=_hash(body.pw), marketing=body.marketing)).inserted_primary_key[0]
    _start_session(resp, uid, True)
    return {"user": {"id": uid, "uid": body.uid, "nick": nick}}


_fails: dict = {}


@router.post("/auth/login")
def login(body: LoginIn, resp: Response):
    key = body.uid.lower()
    n, until = _fails.get(key, (0, 0))
    if until > time.time():
        raise HTTPException(429, "로그인에 여러 번 실패했어요. 1분 뒤에 다시 시도해 주세요.")
    r = db.rows("SELECT id, uid, nick, pw_hash FROM users WHERE lower(uid) = lower(:u)", u=body.uid)
    if not r or not _verify(body.pw, r[0]["pw_hash"]):
        n += 1
        _fails[key] = (n, time.time() + 60 if n >= 5 else 0)
        raise HTTPException(400, "아이디 또는 비밀번호가 맞지 않아요.")
    _fails.pop(key, None)
    _start_session(resp, r[0]["id"], body.keep)
    return {"user": {"id": r[0]["id"], "uid": r[0]["uid"], "nick": r[0]["nick"]}}


@router.post("/auth/logout")
def logout(request: Request, resp: Response):
    tok = request.cookies.get(COOKIE)
    if tok:
        with db.engine.begin() as c:
            c.execute(text("DELETE FROM sessions WHERE token = :t"), {"t": tok})
    resp.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def whoami(request: Request):
    u = me(request)
    unread = db.rows("SELECT COUNT(*) AS n FROM notifications WHERE user_id = :u AND is_read = 0", u=u["id"])[0]["n"] if u else 0
    return {"user": {**u, "avatar": _avatar_url(u["uid"], u["avatar"])} if u else None, "unread": unread}


# ------------------------------------------------------------------ 공통
def cards(ids: List[int]) -> list:
    if not ids:
        return []
    ph = ",".join(f":i{n}" for n in range(len(ids)))
    by = {r["id"]: r for r in db.rows(f"SELECT id, title, author, w, h, views, kind, created_at FROM images WHERE id IN ({ph})", **{f"i{n}": i for n, i in enumerate(ids)})}
    out = []
    for i in ids:
        r = by.get(i)
        if r:
            out.append({"id": r["id"], "title": r["title"], "author": r["author"], "w": r["w"], "h": r["h"], "views": r["views"], "kind": r["kind"] or "illust",
                        "thumb": f"/img/{r['id']}?s=thumb", "created": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])})
    return out


def _image(image_id: int) -> dict:
    r = db.rows("SELECT id, user_id FROM images WHERE id = :i", i=image_id)
    if not r:
        raise HTTPException(404, "이미지를 찾을 수 없어요.")
    return r[0]


def _notify(to: Optional[int], actor: int, kind: str, image_id: Optional[int] = None, body: str = "") -> None:
    if not to or to == actor:
        return
    with db.engine.begin() as c:
        if kind in ("like", "follow"):   # 같은 알림을 반복해서 쌓지 않는다
            c.execute(text("DELETE FROM notifications WHERE user_id=:u AND actor_id=:a AND kind=:k AND COALESCE(image_id,0)=COALESCE(:i,0)"), {"u": to, "a": actor, "k": kind, "i": image_id})
        c.execute(db.notifications.insert().values(user_id=to, actor_id=actor, kind=kind, image_id=image_id, body=body[:200]))


def record_view(request: Request, image_id: int) -> None:
    u = me(request)
    if not u:
        return
    with db.engine.begin() as c:
        n = c.execute(text("UPDATE views SET viewed_at = :t WHERE user_id = :u AND image_id = :i"), {"t": datetime.now(), "u": u["id"], "i": image_id}).rowcount
        if not n:
            c.execute(db.views.insert().values(user_id=u["id"], image_id=image_id))


# ------------------------------------------------------------------ 게시물 소셜 정보
@router.get("/images/{image_id}/social")
def social(image_id: int, request: Request):
    img = _image(image_id)
    u = me(request)
    uid = u["id"] if u else -1
    owner = None
    if img["user_id"]:
        o = db.rows("SELECT id, uid, nick, avatar FROM users WHERE id = :i", i=img["user_id"])
        if o:
            owner = {"uid": o[0]["uid"], "nick": o[0]["nick"], "avatar": _avatar_url(o[0]["uid"], o[0]["avatar"]), "me": o[0]["id"] == uid,
                     "following": bool(db.rows("SELECT 1 AS x FROM follows WHERE follower_id=:a AND followee_id=:b", a=uid, b=o[0]["id"]))}
    cm = db.rows("SELECT c.id, c.body, c.created_at, c.user_id, u.nick FROM comments c JOIN users u ON u.id = c.user_id WHERE c.image_id = :i ORDER BY c.id", i=image_id)
    return {"owner": owner, "editable": bool(u) and (img["user_id"] is None or img["user_id"] == uid),
            "likes": db.rows("SELECT COUNT(*) AS n FROM likes WHERE image_id=:i", i=image_id)[0]["n"],
            "liked": bool(db.rows("SELECT 1 AS x FROM likes WHERE user_id=:u AND image_id=:i", u=uid, i=image_id)),
            "kept": bool(db.rows("SELECT 1 AS x FROM keeps WHERE user_id=:u AND image_id=:i", u=uid, i=image_id)),
            "comments": [{"id": c["id"], "nick": c["nick"], "body": c["body"], "mine": c["user_id"] == uid,
                          "created": c["created_at"].isoformat() if hasattr(c["created_at"], "isoformat") else str(c["created_at"])} for c in cm]}


@router.post("/images/{image_id}/like")
def like(image_id: int, request: Request):
    u, img = need(request), _image(image_id)
    with db.engine.begin() as c:
        if c.execute(text("SELECT 1 FROM likes WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": image_id}).first():
            return {"ok": True}
        c.execute(db.likes.insert().values(user_id=u["id"], image_id=image_id))
    _notify(img["user_id"], u["id"], "like", image_id)
    return {"ok": True}


@router.delete("/images/{image_id}/like")
def unlike(image_id: int, request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM likes WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": image_id})
    return {"ok": True}


class CommentIn(BaseModel):
    body: str


@router.post("/images/{image_id}/comments")
def add_comment(image_id: int, body: CommentIn, request: Request):
    u, img = need(request), _image(image_id)
    b = body.body.strip()
    if not b:
        raise HTTPException(400, "댓글 내용을 입력해 주세요.")
    with db.engine.begin() as c:
        c.execute(db.comments.insert().values(image_id=image_id, user_id=u["id"], body=b[:500]))
    _notify(img["user_id"], u["id"], "comment", image_id, b)
    return {"ok": True}


@router.delete("/comments/{cid}")
def del_comment(cid: int, request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM comments WHERE id=:c AND user_id=:u"), {"c": cid, "u": u["id"]})
    return {"ok": True}


@router.post("/users/{uid}/follow")
def follow(uid: str, request: Request):
    u = need(request)
    t = db.rows("SELECT id FROM users WHERE uid = :u", u=uid)
    if not t or t[0]["id"] == u["id"]:
        raise HTTPException(400, "팔로우할 수 없는 사용자예요.")
    with db.engine.begin() as c:
        if not c.execute(text("SELECT 1 FROM follows WHERE follower_id=:a AND followee_id=:b"), {"a": u["id"], "b": t[0]["id"]}).first():
            c.execute(db.follows.insert().values(follower_id=u["id"], followee_id=t[0]["id"]))
    _notify(t[0]["id"], u["id"], "follow")
    return {"ok": True}


@router.delete("/users/{uid}/follow")
def unfollow(uid: str, request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM follows WHERE follower_id=:a AND followee_id=(SELECT id FROM users WHERE uid=:u)"), {"a": u["id"], "u": uid})
    return {"ok": True}


# ------------------------------------------------------------------ 킵 스페이스
@router.post("/images/{image_id}/keep")
def keep(image_id: int, request: Request):
    u = need(request)
    _image(image_id)
    with db.engine.begin() as c:
        if not c.execute(text("SELECT 1 FROM keeps WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": image_id}).first():
            c.execute(db.keeps.insert().values(user_id=u["id"], image_id=image_id))
    return {"ok": True}


@router.delete("/images/{image_id}/keep")
def unkeep(image_id: int, request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM keeps WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": image_id})
    return {"ok": True}


class IdsIn(BaseModel):
    ids: List[int] = []


@router.get("/me/keeps")
def my_keeps(request: Request, kind: str = ""):
    u = need(request)
    sql = "SELECT k.image_id FROM keeps k JOIN images i ON i.id = k.image_id WHERE k.user_id = :u"
    p = {"u": u["id"]}
    if kind in ("photo", "illust"):
        sql += " AND COALESCE(i.kind,'illust') = :k"
        p["k"] = kind
    ids = [r["image_id"] for r in db.rows(sql + " ORDER BY k.created_at DESC", **p)]
    return {"items": cards(ids), "total": len(ids)}


@router.post("/me/keeps/remove")
def remove_keeps(body: IdsIn, request: Request):
    u = need(request)
    with db.engine.begin() as c:
        for i in body.ids:
            c.execute(text("DELETE FROM keeps WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": i})
    return {"ok": True}


# ------------------------------------------------------------------ 서랍: 최근 본 / 반응한 게시물
@router.get("/me/viewed")
def my_viewed(request: Request):
    u = need(request)
    since = datetime.now() - timedelta(days=7)      # 화면 문구: 최근 일주일 동안 본 게시물
    ids = [r["image_id"] for r in db.rows("SELECT image_id FROM views WHERE user_id=:u AND viewed_at >= :s ORDER BY viewed_at DESC", u=u["id"], s=since)]
    return {"items": cards(ids), "total": len(ids)}


@router.get("/me/liked")
def my_liked(request: Request):
    u = need(request)
    ids = [r["image_id"] for r in db.rows("SELECT image_id FROM likes WHERE user_id=:u ORDER BY created_at DESC", u=u["id"])]
    return {"items": cards(ids), "total": len(ids)}


# ------------------------------------------------------------------ 서랍: 레퍼런스 북
class BookIn(BaseModel):
    name: str
    description: str = ""


class BookItemsIn(BaseModel):
    ids: List[int] = []
    remove_from_keep: bool = False


def _book(book_id: int, u: dict) -> dict:
    r = db.rows("SELECT id, name, description, cover, updated_at FROM books WHERE id = :b AND user_id = :u", b=book_id, u=u["id"])
    if not r:
        raise HTTPException(404, "북을 찾을 수 없어요.")
    return r[0]


def _touch(book_id: int) -> None:
    with db.engine.begin() as c:
        c.execute(text("UPDATE books SET updated_at = :t WHERE id = :b"), {"t": datetime.now(), "b": book_id})


def _book_out(b: dict) -> dict:
    ids = [r["image_id"] for r in db.rows("SELECT image_id FROM book_items WHERE book_id=:b ORDER BY added_at DESC", b=b["id"])]
    return {"id": b["id"], "name": b["name"], "description": b["description"] or "", "count": len(ids), "covers": ids[:3], "cover": f"/api/books/{b['id']}/cover?v={b['cover']}" if b.get("cover") else None,
            "updated": b["updated_at"].isoformat() if hasattr(b["updated_at"], "isoformat") else str(b["updated_at"])}


@router.get("/books")
def list_books(request: Request, sort: str = "recent"):
    u = need(request)
    order = "name" if sort == "name" else "updated_at DESC"
    out = [_book_out(b) for b in db.rows(f"SELECT id, name, description, cover, updated_at FROM books WHERE user_id = :u ORDER BY {order}", u=u["id"])]
    return {"items": out, "total": len(out)}


@router.post("/books")
def create_book(body: BookIn, request: Request):
    u = need(request)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "북 이름을 입력해 주세요.")
    with db.engine.begin() as c:
        bid = c.execute(db.books.insert().values(user_id=u["id"], name=name[:40], description=body.description.strip()[:200])).inserted_primary_key[0]
    return _book_out(_book(bid, u))


@router.get("/books/{book_id}")
def get_book(book_id: int, request: Request):
    u = need(request)
    b = _book(book_id, u)
    ids = [r["image_id"] for r in db.rows("SELECT image_id FROM book_items WHERE book_id=:b ORDER BY added_at DESC", b=book_id)]
    return {**_book_out(b), "items": cards(ids)}


@router.put("/books/{book_id}")
def edit_book(book_id: int, body: BookIn, request: Request):
    u = need(request)
    _book(book_id, u)
    if not body.name.strip():
        raise HTTPException(400, "북 이름을 입력해 주세요.")
    with db.engine.begin() as c:
        c.execute(text("UPDATE books SET name=:n, description=:d, updated_at=:t WHERE id=:b"), {"n": body.name.strip()[:40], "d": body.description.strip()[:200], "t": datetime.now(), "b": book_id})
    return _book_out(_book(book_id, u))


@router.delete("/books/{book_id}")
def delete_book(book_id: int, request: Request):
    u = need(request)
    _book(book_id, u)
    with db.engine.begin() as c:
        c.execute(text("DELETE FROM book_items WHERE book_id=:b"), {"b": book_id})
        c.execute(text("DELETE FROM books WHERE id=:b"), {"b": book_id})
    return {"ok": True}


@router.post("/books/{book_id}/items")
def add_items(book_id: int, body: BookItemsIn, request: Request):
    u = need(request)
    _book(book_id, u)
    with db.engine.begin() as c:
        for i in body.ids:
            if not c.execute(text("SELECT 1 FROM images WHERE id=:i"), {"i": i}).first():
                continue
            if not c.execute(text("SELECT 1 FROM book_items WHERE book_id=:b AND image_id=:i"), {"b": book_id, "i": i}).first():
                c.execute(db.book_items.insert().values(book_id=book_id, image_id=i))
            if body.remove_from_keep:
                c.execute(text("DELETE FROM keeps WHERE user_id=:u AND image_id=:i"), {"u": u["id"], "i": i})
    _touch(book_id)
    return _book_out(_book(book_id, u))


@router.post("/books/{book_id}/items/remove")
def remove_items(book_id: int, body: IdsIn, request: Request):
    u = need(request)
    _book(book_id, u)
    with db.engine.begin() as c:
        for i in body.ids:
            c.execute(text("DELETE FROM book_items WHERE book_id=:b AND image_id=:i"), {"b": book_id, "i": i})
    _touch(book_id)
    return {"ok": True}


# ------------------------------------------------------------------ 알림
@router.get("/notifications")
def notifications(request: Request, kind: str = ""):
    u = need(request)
    sql = "SELECT n.id, n.kind, n.image_id, n.body, n.is_read, n.created_at, a.uid, a.nick FROM notifications n JOIN users a ON a.id = n.actor_id WHERE n.user_id = :u"
    p = {"u": u["id"]}
    if kind in ("like", "comment", "follow"):
        sql += " AND n.kind = :k"
        p["k"] = kind
    out = []
    for r in db.rows(sql + " ORDER BY n.id DESC LIMIT 60", **p):
        following = bool(db.rows("SELECT 1 AS x FROM follows f JOIN users a ON a.id = f.followee_id WHERE f.follower_id=:u AND a.uid=:a", u=u["id"], a=r["uid"])) if r["kind"] == "follow" else None
        out.append({"id": r["id"], "kind": r["kind"], "image_id": r["image_id"], "body": r["body"], "read": bool(r["is_read"]), "actor": r["nick"], "actor_uid": r["uid"],
                    "following": following, "thumb": f"/img/{r['image_id']}?s=thumb" if r["image_id"] else None,
                    "created": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])})
    return {"items": out}


@router.post("/notifications/read")
def read_all(request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("UPDATE notifications SET is_read = 1 WHERE user_id = :u"), {"u": u["id"]})
    return {"ok": True}


# ------------------------------------------------------------------ 북 커버 이미지
def _save_square(data: bytes, dest, size: int, limit_mb: int = 5):
    if len(data) > limit_mb << 20:
        raise HTTPException(413, f"{limit_mb}MB 이하의 이미지만 올릴 수 있어요.")
    try:
        im = Image.open(io.BytesIO(data))
        if im.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        raise HTTPException(400, "JPG · PNG 이미지만 올릴 수 있어요.")
    im = ImageOps.fit(im, (size, size))
    im.save(dest, "JPEG", quality=88)


@router.post("/books/{book_id}/cover")
async def set_cover(book_id: int, request: Request, file: UploadFile = File(...)):
    u = need(request)
    _book(book_id, u)
    name = f"{secrets.token_hex(4)}.jpg"
    _save_square(await file.read(), config.UPLOADS / f"bc_{book_id}_{name}", 480)
    with db.engine.begin() as c:
        c.execute(text("UPDATE books SET cover = :c WHERE id = :b"), {"c": name, "b": book_id})
    _touch(book_id)
    return {"ok": True}


@router.get("/books/{book_id}/cover")
def get_cover(book_id: int, v: str = ""):
    r = db.rows("SELECT cover FROM books WHERE id = :b", b=book_id)
    if not r or not r[0]["cover"]:
        raise HTTPException(404, "커버가 없어요.")
    return FileResponse(config.UPLOADS / f"bc_{book_id}_{r[0]['cover']}", headers={"Cache-Control": "public, max-age=31536000"})


# ------------------------------------------------------------------ 마이페이지(프로필)
LINK_MAX = 5


def _avatar_url(uid: str, avatar: Optional[str]) -> Optional[str]:
    return f"/api/users/{uid}/avatar?v={avatar}" if avatar else None


def _clean_link(v: str) -> str:
    v = v.strip()[:120]
    if not v:
        return ""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", v) and not re.match(r"^https?://", v, re.I):
        raise HTTPException(400, "링크는 http(s) 주소만 등록할 수 있어요.")
    if not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+", v, re.I):
        raise HTTPException(400, "올바른 링크 주소를 입력해 주세요.")
    return v


def _user_row(uid: str) -> dict:
    r = db.rows("SELECT id, uid, nick, bio, links, avatar FROM users WHERE uid = :u", u=uid)
    if not r:
        raise HTTPException(404, "사용자를 찾을 수 없어요.")
    return r[0]


def _count(sql: str, **p) -> int:
    return db.rows(sql, **p)[0]["n"]


@router.get("/users/{uid}")
def profile(uid: str, request: Request):
    v = me(request)
    t = _user_row(uid)
    try:
        links = json.loads(t["links"]) if t["links"] else []
    except Exception:
        links = []
    return {"uid": t["uid"], "nick": t["nick"], "bio": t["bio"] or "", "links": links, "avatar": _avatar_url(t["uid"], t["avatar"]),
            "posts": _count("SELECT COUNT(*) AS n FROM images WHERE user_id = :i", i=t["id"]),
            "books": _count("SELECT COUNT(*) AS n FROM books WHERE user_id = :i", i=t["id"]) if v and v["id"] == t["id"] else None,
            "followers": _count("SELECT COUNT(*) AS n FROM follows WHERE followee_id = :i", i=t["id"]),
            "following": _count("SELECT COUNT(*) AS n FROM follows WHERE follower_id = :i", i=t["id"]),
            "me": bool(v and v["id"] == t["id"]),
            "isFollowing": bool(v) and bool(db.rows("SELECT 1 AS x FROM follows WHERE follower_id=:a AND followee_id=:b", a=v["id"], b=t["id"]))}


@router.get("/users/{uid}/posts")
def user_posts(uid: str, offset: int = 0, limit: int = 60):
    t = _user_row(uid)
    ids = [r["id"] for r in db.rows("SELECT id FROM images WHERE user_id = :i ORDER BY id DESC LIMIT :l OFFSET :o", i=t["id"], l=min(limit, 100), o=max(0, offset))]
    return {"items": cards(ids)}


@router.get("/users/{uid}/books")
def user_books(uid: str, request: Request):
    u = need(request)
    t = _user_row(uid)
    if t["id"] != u["id"]:
        raise HTTPException(403, "내 북만 볼 수 있어요.")
    return list_books(request)


@router.get("/users/{uid}/follows")
def follow_list(uid: str, request: Request, kind: str = "followers"):
    v = me(request)
    t = _user_row(uid)
    if kind == "following":
        sql = "SELECT u.id, u.uid, u.nick, u.bio, u.avatar FROM follows f JOIN users u ON u.id = f.followee_id WHERE f.follower_id = :i ORDER BY f.created_at DESC"
    else:
        sql = "SELECT u.id, u.uid, u.nick, u.bio, u.avatar FROM follows f JOIN users u ON u.id = f.follower_id WHERE f.followee_id = :i ORDER BY f.created_at DESC"
    mine = {r["followee_id"] for r in db.rows("SELECT followee_id FROM follows WHERE follower_id = :a", a=v["id"])} if v else set()
    items = [{"uid": r["uid"], "nick": r["nick"], "bio": r["bio"] or "", "avatar": _avatar_url(r["uid"], r["avatar"]), "me": bool(v and v["id"] == r["id"]), "isFollowing": r["id"] in mine}
             for r in db.rows(sql, i=t["id"])]
    return {"items": items}


class ProfileIn(BaseModel):
    nick: str
    bio: str = ""
    links: List[str] = []


@router.put("/me/profile")
def edit_profile(body: ProfileIn, request: Request):
    u = need(request)
    nick = body.nick.strip()
    err = _nick_error(nick) if nick != u["nick"] else ""
    if err:
        raise HTTPException(400, err)
    bio = body.bio.strip()
    if len(bio) > 100:
        raise HTTPException(400, "소개는 100자 이하로 써 주세요.")
    links = []
    for raw in body.links:
        c = _clean_link(raw)
        if c and c not in links:
            links.append(c)
    if len(links) > LINK_MAX:
        raise HTTPException(400, f"외부 링크는 최대 {LINK_MAX}개까지 등록할 수 있어요.")
    with db.engine.begin() as c:
        c.execute(text("UPDATE users SET nick = :n, bio = :b, links = :l WHERE id = :i"), {"n": nick, "b": bio, "l": json.dumps(links, ensure_ascii=False), "i": u["id"]})
        if nick != u["nick"]:
            c.execute(text("UPDATE images SET author = :n WHERE user_id = :i"), {"n": nick, "i": u["id"]})
    return {"ok": True, "nick": nick}


@router.post("/me/avatar")
async def set_avatar(request: Request, file: UploadFile = File(...)):
    u = need(request)
    name = secrets.token_hex(4)
    _save_square(await file.read(), config.UPLOADS / f"av_{u['id']}_{name}.jpg", 320)
    with db.engine.begin() as c:
        c.execute(text("UPDATE users SET avatar = :a WHERE id = :i"), {"a": name, "i": u["id"]})
    return {"avatar": _avatar_url(u["uid"], name)}


@router.delete("/me/avatar")
def clear_avatar(request: Request):
    u = need(request)
    with db.engine.begin() as c:
        c.execute(text("UPDATE users SET avatar = NULL WHERE id = :i"), {"i": u["id"]})
    return {"ok": True}


@router.get("/users/{uid}/avatar")
def avatar_file(uid: str, v: str = ""):
    t = _user_row(uid)
    if not t["avatar"]:
        raise HTTPException(404, "프로필 사진이 없어요.")
    return FileResponse(config.UPLOADS / f"av_{t['id']}_{t['avatar']}.jpg", headers={"Cache-Control": "public, max-age=31536000"})
