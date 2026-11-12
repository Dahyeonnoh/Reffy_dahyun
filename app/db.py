from __future__ import annotations
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine, event, inspect, text)
from datetime import datetime

from . import config

engine = create_engine(config.DB_URL, pool_pre_ping=True, future=True)
if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _pragma(dbapi, _):  # noqa: ANN001
        dbapi.execute("PRAGMA journal_mode=WAL")
        dbapi.execute("PRAGMA foreign_keys=ON")

md = MetaData()
images = Table("images", md,
               Column("id", Integer, primary_key=True, autoincrement=True),
               Column("title", String(120), nullable=False, default=""),
               Column("author", String(40), nullable=False, default="익명"),
               Column("file", String(80), nullable=False),
               Column("w", Integer, default=0), Column("h", Integer, default=0),
               Column("views", Integer, default=0),
               Column("user_id", Integer),                  # 올린 사람 (로그인 도입 전 이미지는 NULL)
               Column("kind", String(8), default="illust"),  # illust(일러스트) / photo(사진)
               Column("colors", Text),                      # 대표색 [[hex, 비율], ...] (컬러 팔레트 검색)
               Column("wd_json", Text),                     # 검색용 WD 원본 태그 {태그: 확률}
               Column("created_at", DateTime, default=datetime.now))
# 태그: AI 예측(ai_prob)과 사용자 수정(user_state)을 따로 보관. 최종 = AI(확률>=임계값) + 사용자 추가 - 사용자 삭제 (PRD 8.2)
image_tags = Table("image_tags", md,
                   Column("image_id", Integer, ForeignKey("images.id", ondelete="CASCADE"), primary_key=True),
                   Column("ikey", String(60), primary_key=True),
                   Column("ai_prob", Float), Column("ai_src", String(8)),
                   Column("user_state", String(4)))          # NULL / 'add' / 'del'

# ---- 계정·소셜 (로그인, 하트, 댓글, 팔로우, 킵 스페이스, 서랍(레퍼런스 북), 알림)
users = Table("users", md,
              Column("id", Integer, primary_key=True, autoincrement=True),
              Column("uid", String(20), nullable=False, unique=True),
              Column("nick", String(20), nullable=False, unique=True),
              Column("pw_hash", String(200), nullable=False),
              Column("marketing", Boolean, default=False),
              Column("bio", String(200), default=""),          # 한 줄 소개
              Column("links", Text),                           # 외부 링크 JSON (최대 5개)
              Column("avatar", String(40)),                    # 프로필 사진 파일명 (없으면 NULL)
              Column("created_at", DateTime, default=datetime.now))
sessions = Table("sessions", md,
                 Column("token", String(64), primary_key=True),
                 Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
                 Column("created_at", DateTime, default=datetime.now))
likes = Table("likes", md, Column("user_id", Integer, primary_key=True), Column("image_id", Integer, primary_key=True),
              Column("created_at", DateTime, default=datetime.now))
comments = Table("comments", md,
                 Column("id", Integer, primary_key=True, autoincrement=True),
                 Column("image_id", Integer, nullable=False, index=True), Column("user_id", Integer, nullable=False),
                 Column("body", String(500), nullable=False), Column("created_at", DateTime, default=datetime.now))
follows = Table("follows", md, Column("follower_id", Integer, primary_key=True), Column("followee_id", Integer, primary_key=True),
                Column("created_at", DateTime, default=datetime.now))
keeps = Table("keeps", md, Column("user_id", Integer, primary_key=True), Column("image_id", Integer, primary_key=True),
              Column("created_at", DateTime, default=datetime.now))
books = Table("books", md,
              Column("id", Integer, primary_key=True, autoincrement=True),
              Column("user_id", Integer, nullable=False, index=True), Column("name", String(40), nullable=False),
              Column("description", String(200), default=""), Column("cover", String(40)),
              Column("updated_at", DateTime, default=datetime.now))
book_items = Table("book_items", md, Column("book_id", Integer, primary_key=True), Column("image_id", Integer, primary_key=True),
                   Column("added_at", DateTime, default=datetime.now))
views = Table("views", md, Column("user_id", Integer, primary_key=True), Column("image_id", Integer, primary_key=True),
              Column("viewed_at", DateTime, default=datetime.now))
notifications = Table("notifications", md,
                      Column("id", Integer, primary_key=True, autoincrement=True),
                      Column("user_id", Integer, nullable=False, index=True),          # 받는 사람
                      Column("actor_id", Integer, nullable=False), Column("kind", String(8), nullable=False),   # like / comment / follow
                      Column("image_id", Integer), Column("body", String(200), default=""),
                      Column("is_read", Boolean, default=False), Column("created_at", DateTime, default=datetime.now))

ACTIVE = "((t.user_state = 'add') OR (t.user_state IS NULL AND t.ai_prob >= :thr))"


def init():
    md.create_all(engine)
    # 예전에 만든 DB 에는 없는 열을 채워 넣는다 (데이터는 그대로 유지)
    cols = {c["name"] for c in inspect(engine).get_columns("images")}
    with engine.begin() as c:
        if "user_id" not in cols:
            c.execute(text("ALTER TABLE images ADD COLUMN user_id INTEGER"))
        if "kind" not in cols:
            c.execute(text("ALTER TABLE images ADD COLUMN kind VARCHAR(8) DEFAULT 'illust'"))
        if "colors" not in cols:
            c.execute(text("ALTER TABLE images ADD COLUMN colors TEXT"))
        ucols = {x["name"] for x in inspect(engine).get_columns("users")}
        for name, ddl in (("bio", "VARCHAR(200) DEFAULT ''"), ("links", "TEXT"), ("avatar", "VARCHAR(40)")):
            if name not in ucols:
                c.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
        bcols = {x["name"] for x in inspect(engine).get_columns("books")}
        if "cover" not in bcols:
            c.execute(text("ALTER TABLE books ADD COLUMN cover VARCHAR(40)"))


def rows(sql: str, **p):
    with engine.connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]
