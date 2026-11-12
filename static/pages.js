"use strict";
/* REFFY — 라우팅과 홈 밖의 화면: 로그인·회원가입, 킵 스페이스, 서랍(레퍼런스 북), 알림. app.js 의 공통 함수를 사용합니다. */
const when = (iso) => new Date(String(iso).replace(" ", "T"));
function ago(iso) {
  const s = (Date.now() - when(iso)) / 1000;
  if (s < 60) return "방금"; if (s < 3600) return Math.floor(s / 60) + "분 전"; if (s < 86400) return Math.floor(s / 3600) + "시간 전";
  if (s < 604800) return Math.floor(s / 86400) + "일 전"; return when(iso).toLocaleDateString("ko-KR");
}
const btn = (label, cls, fn, attrs) => h("button", { class: "btn " + (cls || ""), type: "button", onclick: fn, ...(attrs || {}) }, label);
function page(el) { $("#layout").hidden = true; const p = $("#page"); p.hidden = false; p.replaceChildren(el); window.scrollTo(0, 0); }
function popMenu(anchor, items) {
  document.querySelector(".pop-menu")?.remove();
  const r = anchor.getBoundingClientRect();
  const m = h("div", { class: "pop-menu", role: "menu", style: `left:${Math.max(8, r.right - 140 + window.scrollX)}px;top:${r.bottom + 4 + window.scrollY}px` },
    items.map(([l, fn]) => h("button", { type: "button", role: "menuitem", onclick: () => { m.remove(); fn(); } }, l)));
  document.body.append(m);
  setTimeout(() => document.addEventListener("click", () => m.remove(), { once: true }), 0);
}

/* 확인 모달: 제목 + [아니요][네] (Figma 삭제 확인 양식) */
function confirmDialog(title, sub, opt = {}) {
  if (opt.remember && store.get(opt.remember, false)) return Promise.resolve(true);   // ‘다시 보지 않기’를 고른 뒤에는 바로 진행
  return new Promise((res) => {
    let skip = false;
    const done = (v) => { if (v && skip && opt.remember) store.set(opt.remember, true); m.remove(); document.removeEventListener("keydown", key); res(v); };
    const key = (e) => { if (e.key === "Escape") done(false); };
    const m = h("div", { class: "modal", onmousedown: (e) => e.target === m && done(false) },
      h("div", { class: "dlg confirm" + (title.length > 24 ? " long" : ""), role: "alertdialog", "aria-modal": "true", "aria-label": title },
        h("div", { class: "chd" }, h("h2", {}, title), h("button", { class: "icon-btn", type: "button", "aria-label": "닫기", onclick: () => done(false) }, icon("close", 24))),
        sub ? h("p", { class: "csub" }, sub) : null,
        h("div", { class: "cft" }, opt.remember ? h("label", { class: "cskip" }, h("input", { class: "cbx", type: "checkbox", onchange: (e) => (skip = e.target.checked) }), "다시 보지 않기") : null,
          btn("아니요", "", () => done(false)), btn("네", "primary", () => done(true), { id: "cYes" }))));
    document.body.append(m); document.addEventListener("keydown", key); setTimeout(() => $("#cYes")?.focus(), 0);
  });
}
/* 프로필 사진(없으면 첫 글자) */
function avatarEl(u, size, cls) {
  const el = h("span", { class: (cls || "") + " avt", style: `width:${size}px;height:${size}px;border-radius:${size / 2}px;font-size:${Math.round(size * .4)}px` });
  if (u && u.avatar) el.append(h("img", { src: u.avatar, alt: "" })); else el.append(((u && (u.nick || u.uid)) || "?").slice(0, 1).toUpperCase());
  return el;
}
function modal(title, body, foot) {
  const m = h("div", { class: "modal", onmousedown: (e) => e.target === m && m.remove() },
    h("div", { class: "dlg sm", role: "dialog", "aria-modal": "true", "aria-label": title },
      h("header", {}, h("h2", {}, title), h("button", { class: "icon-btn", type: "button", "aria-label": "닫기", onclick: () => m.remove() }, icon("close", 24))),
      h("div", { class: "body" }, body), foot));
  document.body.append(m); return m;
}

/* ---------------------------------------------------------------- 카드·그리드 */
function pcard(it, o = {}) {
  const el = h("div", { class: "card" + (o.on ? " on" : ""), "data-id": it.id, role: "button", tabindex: "0", onclick: () => (o.click ? o.click(it, el) : goPost(it.id)),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.click(); } } },
    h("span", { class: "im" }, h("img", { src: it.thumb, alt: it.title || "레퍼런스 이미지", loading: "lazy", width: it.w || null, height: it.h || null })), h("span", { class: "ck" }),
    h("span", { class: "meta" }, h("span", { class: "av" }, (it.author || "?").slice(0, 1)), h("span", { class: "tx" }, h("b", {}, it.title || "제목 없음"), h("span", {}, it.author)),
      o.more ? h("button", { class: "more-btn", type: "button", "aria-label": "더보기", onclick: (e) => { e.stopPropagation(); o.more(e.currentTarget, it); } }, moreIc()) : moreIc()));
  return el;
}
const pgrid = (items, o, cls) => h("div", { class: "grid " + (cls || "c6") }, items.map((it) => pcard(it, typeof o === "function" ? o(it) : o)));
const notice = (t, p, b) => h("div", { class: "notice" }, h("h2", {}, t), h("p", {}, p), b || null);

/* ---------------------------------------------------------------- 저장하기(북 고르기) */
async function saveToBook(ids, o = {}) {
  let books;
  try { books = (await api("/api/books")).items; } catch (e) { toast(e.message); return; }
  let chosen = books[0]?.id ?? null, rm = false;
  const list = h("div", {});
  const name = h("input", { type: "text", maxlength: "40", placeholder: "예) 앉은 포즈 모음", "aria-label": "새 북 이름" });
  const drawList = () => list.replaceChildren(...(books.length ? books.map((b) => h("button", { class: "brow-pick" + (chosen === b.id ? " on" : ""), type: "button", role: "radio", "aria-checked": String(chosen === b.id), onclick: () => { chosen = b.id; drawList(); } },
    b.covers[0] ? h("img", { src: `/img/${b.covers[0]}?s=thumb`, alt: "" }) : h("span", { class: "th" }), h("span", { class: "bt" }, h("b", {}, b.name), h("span", {}, `${b.count}개`)), h("span", { class: "radio" })))
    : [h("p", { class: "hint" }, "아직 북이 없어요. 위에서 새 북을 만들어 주세요.")]));
  drawList();
  const make = async () => {
    const v = name.value.trim(); if (!v) return toast("북 이름을 입력해 주세요.");
    try { const b = await api("/api/books", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: v }) }); books.unshift(b); chosen = b.id; name.value = ""; drawList(); } catch (e) { toast(e.message); }
  };
  const cb = h("input", { class: "cbx", type: "checkbox", onchange: (e) => (rm = e.target.checked) });
  const m = modal("저장하기", h("div", {}, h("div", { class: "newbook" }, h("b", {}, "+ 새 북 만들기"), h("span", { class: "lbl", style: "margin-top:0" }, "새 북 이름"), h("div", { class: "row" }, name, btn("만들기", "", make, { style: "height:44px" }))), h("span", { class: "lbl" }, "내 북"), list),
    h("div", { class: "foot" }, h("label", {}, cb, "저장 후 킵 스페이스에서 비우기"), btn("취소", "", () => m.remove()), btn("저장하기", "primary", async () => {
      if (chosen == null) return toast("저장할 북을 골라 주세요.");
      try { const b = await api(`/api/books/${chosen}/items`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids, remove_from_keep: rm }) }); m.remove(); toast(`“${b.name}”에 저장했어요`); o.after && o.after(); } catch (e) { toast(e.message); }
    })));
  setTimeout(() => name.focus(), 0);
}
function bookDialog(book, done) {
  let file = null;
  const name = h("input", { type: "text", maxlength: "40", value: book?.name || "", placeholder: "예: 앉은 포즈 모음", "aria-label": "북 이름" });
  const desc = h("textarea", { maxlength: "200", placeholder: "북에 대한 메모를 남겨 보세요", "aria-label": "북 설명" }, book?.description || "");
  const prev = h("span", { class: "cvprev" });
  const showPrev = (url) => prev.replaceChildren(url ? h("img", { src: url, alt: "커버 미리보기" }) : "");
  showPrev(book?.cover || (book?.covers?.[0] ? `/img/${book.covers[0]}?s=thumb` : null));
  const pick = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", hidden: true, onchange: (e) => { const f = e.target.files[0]; if (!f) return; if (f.size > 5 << 20) { toast("5MB 이하의 이미지만 올릴 수 있어요."); return; } file = f; showPrev(URL.createObjectURL(f)); } });
  const m = h("div", { class: "modal", onmousedown: (e) => e.target === m && m.remove() },
    h("div", { class: "dlg bk", role: "dialog", "aria-modal": "true", "aria-label": book ? "북 편집" : "새 북 만들기" },
      h("div", { class: "chd" }, h("h2", {}, book ? "북 편집" : "새 북 만들기"), h("button", { class: "icon-btn", type: "button", "aria-label": "닫기", onclick: () => m.remove() }, icon("close", 24))),
      h("div", { class: "cvrow" }, prev, h("div", { class: "cvtx" }, h("b", {}, "커버 이미지"), h("span", {}, "이미지를 고르면 커버로 지정돼요"),
        h("button", { class: "btn", type: "button", onclick: () => pick.click() }, icon("image", 20), "업로드"), pick)),
      h("label", { class: "fl2" }, "북 이름"), name,
      h("label", { class: "fl2" }, "설명 (선택)"), desc,
      h("div", { class: "cft" }, btn("취소", "", () => m.remove()), btn(book ? "저장" : "만들기", "primary", async () => {
        if (!name.value.trim()) return toast("북 이름을 입력해 주세요.");
        try {
          const b = await api(book ? `/api/books/${book.id}` : "/api/books", { method: book ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: name.value, description: desc.value }) });
          if (file) { const fd = new FormData(); fd.append("file", file); await api(`/api/books/${b.id}/cover`, { method: "POST", body: fd }); }
          m.remove(); done();
        } catch (e) { toast(e.message); }
      }))));
  document.body.append(m); setTimeout(() => name.focus(), 0);
}

/* ---------------------------------------------------------------- 킵 스페이스 */
async function keepPage() {
  if (!needLogin()) return;
  let kind = "", sel = false, data = { items: [] }; const picked = new Set();
  const root = h("div", { class: "pad" }); page(root);
  async function load() { try { data = await api("/api/me/keeps" + (kind ? "?kind=" + kind : "")); } catch (e) { toast(e.message); return; } draw(); }
  function bar() {
    const b = h("div", { class: "selbar", hidden: !sel });
    const n = picked.size;
    b.append(`${n}개 선택`, btn("북에 저장", "", () => n ? saveToBook([...picked], { after: () => { picked.clear(); sel = false; load(); } }) : toast("저장할 이미지를 골라 주세요.")),
      btn("삭제", "primary", async () => {
        if (!n) return toast("삭제할 이미지를 골라 주세요.");
        if (!(await confirmDialog(`선택한 레퍼런스 ${n}개를 삭제할까요?`))) return;
        try { await api("/api/me/keeps/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [...picked] }) }); picked.clear(); sel = false; load(); } catch (e) { toast(e.message); }
      }));
    return b;
  }
  function draw() {
    root.classList.toggle("selecting", sel);
    const chips = [["", "전체"], ["photo", "사진"], ["illust", "일러스트"]].map(([k, l]) => h("button", { class: "pill" + (kind === k ? " on" : ""), type: "button", onclick: () => { kind = k; picked.clear(); load(); } }, l));
    root.replaceChildren(h("div", { class: "kbar" }, chips, h("span", { class: "sp" }),
      data.items.length ? (sel ? btn("취소", "", () => { sel = false; picked.clear(); draw(); }) : btn("선택", "primary", () => { sel = true; draw(); })) : null),
      data.items.length ? pgrid(data.items, (it) => ({ on: picked.has(it.id), click: (_, el) => { if (!sel) return goPost(it.id); picked.has(it.id) ? picked.delete(it.id) : picked.add(it.id); el.classList.toggle("on", picked.has(it.id)); root.querySelector(".selbar").replaceWith(bar()); } }), "c6")
        : notice(kind ? "이 종류의 킵이 없어요" : "킵 스페이스가 비었어요", "홈에서 마음에 드는 레퍼런스를 ‘킵에 담기’로 모아 보세요.", btn("홈으로", "primary", () => (location.hash = "#/"))),
      bar());
  }
  load();
}

/* ---------------------------------------------------------------- 서랍 */
async function drawerPage(sub, id) {
  if (!needLogin()) return;
  const link = (t, href, on) => h("a", { href, class: on ? "on" : "", "aria-current": on ? "page" : null }, t);
  const main = h("div", { class: "dmain" });
  page(h("div", { class: "drawer" }, h("aside", { class: "dnav" }, h("h2", {}, "서랍"), link("레퍼런스 북", "#/drawer", !sub || sub === "book"), h("small", {}, "내 활동"),
    link("최근 본 게시물", "#/drawer/recent", sub === "recent"), link("반응한 게시물", "#/drawer/liked", sub === "liked")), main));
  try {
    if (sub === "recent" || sub === "liked") {
      const d = await api(sub === "recent" ? "/api/me/viewed" : "/api/me/liked");
      main.append(h("h1", {}, sub === "recent" ? "최근 본 게시물" : "반응한 게시물"), h("p", { class: "sub", style: "margin-bottom:28px" }, sub === "recent" ? "최근 일주일 동안 본 게시물이에요" : "하트를 누른 게시물이에요"),
        d.items.length ? pgrid(d.items, {}, "c5") : notice(sub === "recent" ? "최근 본 게시물이 없어요" : "아직 반응한 게시물이 없어요", "홈에서 마음에 드는 레퍼런스를 찾아 보세요.", btn("홈으로", "primary", () => (location.hash = "#/"))));
    } else if (sub === "book") await bookDetail(main, id); else await bookList(main);
  } catch (e) { main.replaceChildren(notice("불러오지 못했어요", e.message)); }
}
async function bookList(main, sort = "recent") {
  const d = await api("/api/books?sort=" + sort);
  const redo = () => bookList(main, sort);
  const sortBtn = h("button", { class: "sortbtn", type: "button", onclick: (e) => { e.stopPropagation(); popMenu(e.currentTarget, [["최근 수정 순", () => { sort = "recent"; redo(); }], ["이름 순", () => { sort = "name"; redo(); }]]); } }, sort === "name" ? "이름 순" : "최근 수정 순", icon("chevronDown"));
  main.replaceChildren(h("div", { class: "dhead" }, h("div", {}, h("h1", {}, "레퍼런스 북"), h("p", { class: "sub" }, `북 ${d.total}개`)), h("span", { class: "sp" }), sortBtn, btn("+ 새 북 만들기", "primary", () => bookDialog(null, redo))),
    d.items.length ? h("div", { class: "books" }, d.items.map((b) => h("div", { class: "bk" },
      h("button", { class: "book", type: "button", "aria-label": `${b.name} 열기`, onclick: () => (location.hash = "#/drawer/book/" + b.id) }, h("span", { class: "cover" + (b.cover ? " one" : "") }, b.cover ? h("img", { src: b.cover, alt: "" }) : [0, 1, 2].map((i) => h("span", {}, b.covers[i] ? h("img", { src: `/img/${b.covers[i]}?s=thumb`, alt: "" }) : null)))),
      h("div", { class: "brow" }, h("button", { class: "bt", type: "button", style: "text-align:left", onclick: () => (location.hash = "#/drawer/book/" + b.id) }, h("b", {}, b.name), h("span", {}, `${b.count}개 · ${ago(b.updated)}`)),
        h("button", { class: "more-btn", type: "button", "aria-label": `${b.name} 더보기`, onclick: (e) => { e.stopPropagation(); popMenu(e.currentTarget, [["편집", () => bookDialog(b, redo)], ["삭제", async () => { if (await confirmDialog(`“${b.name}” 북을 삭제할까요? 담긴 게시물은 삭제되지 않아요.`)) { try { await api("/api/books/" + b.id, { method: "DELETE" }); redo(); } catch (er) { toast(er.message); } } }]]); } }, moreIc())))))
      : notice("아직 북이 없어요", "마음에 드는 레퍼런스를 주제별로 모아 보세요.", btn("+ 새 북 만들기", "primary", () => bookDialog(null, redo))));
}
async function bookDetail(main, id) {
  const b = await api("/api/books/" + id); const redo = () => bookDetail(main, id);
  main.replaceChildren(h("div", { class: "back-row" }, h("button", { class: "icon-btn", type: "button", "aria-label": "북 목록으로", onclick: () => (location.hash = "#/drawer") }, icon("back", 24)),
    h("button", { class: "more-btn", type: "button", "aria-label": "북 메뉴", onclick: (e) => { e.stopPropagation(); popMenu(e.currentTarget, [["북 삭제", async () => { if (await confirmDialog(`“${b.name}” 북을 삭제할까요? 담긴 게시물은 삭제되지 않아요.`)) { try { await api("/api/books/" + id, { method: "DELETE" }); location.hash = "#/drawer"; } catch (er) { toast(er.message); } } }]]); } }, moreIc())),
    h("div", { class: "dhead" }, h("div", {}, h("h1", { style: "font-size:28px" }, b.name), h("p", { class: "sub" }, `총 ${b.count}장 · ${ago(b.updated)}`), b.description ? h("p", { class: "sub" }, b.description) : null), h("span", { class: "sp" }), btn("편집", "primary", () => bookDialog(b, redo))),
    b.items.length ? pgrid(b.items, { more: (a, it) => popMenu(a, [["북에서 빼기", async () => { try { await api(`/api/books/${id}/items/remove`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [it.id] }) }); redo(); } catch (e) { toast(e.message); } }]]) }, "c5")
      : notice("이 북은 비어 있어요", "게시물 상세에서 ‘북에 저장’을 눌러 담아 보세요.", btn("홈으로", "primary", () => (location.hash = "#/"))));
}

/* ---------------------------------------------------------------- 알림 */
let nTab = "";
function bucket(iso) { const d = when(iso), n = new Date(); if (d.toDateString() === n.toDateString()) return "오늘"; return n - d < 6048e5 ? "이번 주" : "이전"; }
async function drawNotif() {
  const box = $("#notif"); let r;
  try { r = await api("/api/notifications" + (nTab ? "?kind=" + nTab : "")); } catch (e) { box.replaceChildren(h("p", { class: "nempty" }, e.message)); return; }
  const text = (n) => n.kind === "like" ? `${n.actor}님이 회원님의 게시물에 하트를 눌렀어요` : n.kind === "comment" ? `${n.actor}님이 댓글을 남겼어요: “${n.body}”` : `${n.actor}님이 회원님을 팔로우해요`;
  const groups = {}; r.items.forEach((n) => (groups[bucket(n.created)] ||= []).push(n));
  box.replaceChildren(h("div", { class: "hd" }, h("h2", {}, "알림"), h("button", { type: "button", onclick: async () => { try { await api("/api/notifications/read", { method: "POST" }); UNREAD = 0; drawMe(); drawNotif(); } catch (e) { toast(e.message); } } }, "모두 읽음")),
    h("div", { class: "ntabs", role: "tablist" }, [["", "전체"], ["like", "하트"], ["comment", "댓글"], ["follow", "팔로잉"]].map(([k, l]) => h("button", { type: "button", role: "tab", class: nTab === k ? "on" : "", "aria-selected": String(nTab === k), onclick: () => { nTab = k; drawNotif(); } }, l))),
    ...(r.items.length ? ["오늘", "이번 주", "이전"].filter((k) => groups[k]).map((k) => h("div", {}, h("h4", {}, k), groups[k].map((n) => h("div", { class: "nitem" + (n.read ? "" : " unread") },
      h("button", { class: "nitem", type: "button", style: "flex:1;padding:0", onclick: () => { box.hidden = true; if (n.image_id) goPost(n.image_id); }, },
        h("span", { class: "av" }, n.actor.slice(0, 1)), h("span", { class: "nt" }, text(n), h("small", {}, ago(n.created))), n.thumb ? h("img", { src: n.thumb, alt: "" }) : null),
      n.kind === "follow" && !n.following ? btn("맞팔로우", "primary", async () => { try { await api(`/api/users/${n.actor_uid}/follow`, { method: "POST" }); drawNotif(); } catch (e) { toast(e.message); } }) : null))))
      : [h("p", { class: "nempty" }, "새 알림이 없어요")]));
}
$("#bell").onclick = (e) => {
  e.stopPropagation(); if (!needLogin()) return;
  const box = $("#notif"); box.hidden = !box.hidden; $("#bell").setAttribute("aria-expanded", String(!box.hidden));
  if (!box.hidden) drawNotif();
};
document.addEventListener("click", (e) => { if (!e.target.closest("#notif, #bell")) { $("#notif").hidden = true; $("#bell").setAttribute("aria-expanded", "false"); } });
async function doLogout() { try { await api("/api/auth/logout", { method: "POST" }); } catch { /* 이미 만료 */ } ME = null; UNREAD = 0; drawMe(); location.hash = "#/"; toast("로그아웃했어요"); }
$("#me").onclick = (e) => {
  e.stopPropagation();
  if (!ME) return needLogin();
  popMenu(e.currentTarget, [["마이페이지", () => (location.hash = "#/me")], ["로그아웃", doLogout]]);
};

/* ---------------------------------------------------------------- 로그인 · 회원가입 */
function authLayout(inner) {
  const col = (hs) => h("div", {}, hs.map((x) => h("i", { style: `height:${x}px` })));
  return h("div", { class: "authwrap" }, h("div", { class: "aside-art" }, h("b", {}, "REFFY"), h("div", { class: "art", "aria-hidden": "true" }, col([300, 260, 280]), col([220, 240, 320, 240]), col([360, 340, 250]))), h("div", { class: "formcol" }, h("div", { class: "fbox" }, inner)));
}
const goNext = () => { const n = sessionStorage.getItem("reffy.next") || "#/"; sessionStorage.removeItem("reffy.next"); location.hash = n.startsWith("#/login") || n.startsWith("#/signup") ? "#/" : n; };
const snsRow = () => h("div", { class: "snsrow" }, [["G", "#fff", "#4285f4", "Google"], ["K", "#fee500", "#3c1e1e", "카카오"], ["N", "#03c75a", "#fff", "네이버"], ["X", "#000", "#fff", "X"]].map(([t, bg, fg, n]) =>
  h("button", { type: "button", disabled: true, title: `${n} 로그인은 준비 중이에요`, "aria-label": `${n} 로그인 (준비 중)`, style: `background:${bg};color:${fg}` }, t)));
function loginPage() {
  const uid = h("input", { class: "inp", id: "lu", name: "username", autocomplete: "username", placeholder: "영문과 숫자 6~20자리" });
  const pw = h("input", { class: "inp", id: "lp", name: "password", type: "password", autocomplete: "current-password", placeholder: "8자 이상 입력" });
  const keepc = h("input", { class: "cbx", type: "checkbox", checked: true });
  const msg = h("p", { class: "msg bad", role: "alert" });
  const go = h("button", { class: "cta", type: "submit" }, "로그인");
  const f = h("form", { onsubmit: async (e) => {
    e.preventDefault(); msg.textContent = "";
    if (!uid.value.trim() || !pw.value) { msg.textContent = "아이디와 비밀번호를 입력해 주세요."; return; }
    go.disabled = true;
    try { await api("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ uid: uid.value.trim(), pw: pw.value, keep: keepc.checked }) }); await loadMe(); goNext(); }
    catch (er) { msg.textContent = er.message; go.disabled = false; }
  } },
    h("h1", {}, "만나서 반가워요"), h("p", { class: "lead" }, "레퍼런스를 모아 정리해 보세요"),
    h("label", { class: "fl", for: "lu", style: "margin-top:0" }, "아이디"), uid, h("label", { class: "fl", for: "lp" }, "비밀번호"), pw, msg,
    h("div", { class: "rowline" }, h("label", {}, keepc, "로그인 상태 유지"), h("button", { class: "linkbtn", type: "button", disabled: true, title: "준비 중이에요", style: "color:var(--ink3)" }, "비밀번호 찾기")),
    go, h("div", { class: "sns" }, "SNS 계정으로 계속하기"), snsRow(), h("p", { class: "foot-link", style: "margin-top:157px" }, "아직 계정이 없나요? ", h("a", { href: "#/signup" }, "회원가입")));
  page(authLayout(f)); uid.focus();
}
function signupPage() {
  const nick = h("input", { class: "inp", id: "sn", maxlength: "20", placeholder: "닉네임 입력", autocomplete: "nickname" });
  const uid = h("input", { class: "inp", id: "su", maxlength: "20", placeholder: "영문과 숫자 6~20자리", autocomplete: "username" });
  const pw = h("input", { class: "inp", id: "sp", type: "password", placeholder: "영문 · 숫자 포함 8자 이상", autocomplete: "new-password" });
  const pw2 = h("input", { class: "inp", id: "sp2", type: "password", placeholder: "비밀번호를 한 번 더 입력", autocomplete: "new-password" });
  const mNick = h("p", { class: "msg" }), mUid = h("p", { class: "msg" }), mPw = h("p", { class: "msg" }), mPw2 = h("p", { class: "msg" }), mAll = h("p", { class: "msg bad", role: "alert" });
  const set = (el, t, k) => { el.textContent = t; el.className = "msg " + (k || ""); };
  let nickOk = "";
  const check = async () => { const v = nick.value.trim(); if (!v) return set(mNick, "닉네임을 입력해 주세요.", "bad"); try { const r = await api("/api/auth/nick-check?nick=" + encodeURIComponent(v)); nickOk = r.ok ? v : ""; set(mNick, r.message, r.ok ? "ok" : "bad"); } catch (e) { set(mNick, e.message, "bad"); } };
  nick.oninput = () => { nickOk = ""; set(mNick, ""); };
  uid.onblur = () => set(mUid, uid.value && !/^[A-Za-z0-9]{6,20}$/.test(uid.value) ? "아이디는 영문과 숫자 6~20자로 입력해 주세요." : "", "bad");
  pw.onblur = () => set(mPw, pw.value && (pw.value.length < 8 || !/[A-Za-z]/.test(pw.value) || !/\d/.test(pw.value)) ? "영문과 숫자를 포함해 8자 이상이어야 해요." : "", "bad");
  pw2.oninput = () => set(mPw2, pw2.value && pw.value !== pw2.value ? "비밀번호가 서로 달라요." : "", "bad");
  const boxes = ["terms", "privacy", "marketing"].map(() => h("input", { class: "cbx", type: "checkbox" }));
  const all = h("input", { class: "cbx", type: "checkbox", onchange: (e) => boxes.forEach((b) => (b.checked = e.target.checked)) });
  boxes.forEach((b) => (b.onchange = () => (all.checked = boxes.every((x) => x.checked))));
  const see = () => modal("약관", h("p", {}, "약관 전문은 서비스 공개 전에 등록할 예정이에요."), h("div", { class: "foot" }, btn("확인", "primary", (e) => e.target.closest(".modal").remove())));
  const row = (cb, t, req) => h("label", {}, cb, t, h("button", { class: "see linkbtn", type: "button", onclick: (e) => { e.preventDefault(); see(); } }, "보기"));
  const go = h("button", { class: "cta", type: "submit" }, "가입하기");
  const f = h("form", { onsubmit: async (e) => {
    e.preventDefault(); set(mAll, "", "bad");
    if (nick.value.trim() !== nickOk) { set(mAll, "닉네임 중복 확인을 해 주세요.", "bad"); return; }
    go.disabled = true;
    try { await api("/api/auth/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nick: nick.value.trim(), uid: uid.value.trim(), pw: pw.value, pw2: pw2.value, terms: boxes[0].checked, privacy: boxes[1].checked, marketing: boxes[2].checked }) }); await loadMe(); toast("가입을 환영해요"); goNext(); }
    catch (er) { set(mAll, er.message, "bad"); go.disabled = false; }
  } },
    h("h1", { style: "margin-bottom:0" }, "회원가입"),
    h("label", { class: "fl", for: "sn" }, "닉네임"), h("div", { class: "nickrow" }, nick, btn("중복 확인", "", check)), mNick,
    h("label", { class: "fl", for: "su", style: "margin-top:8px" }, "아이디"), uid, mUid, h("label", { class: "fl", for: "sp", style: "margin-top:8px" }, "비밀번호"), pw, mPw,
    h("label", { class: "fl", for: "sp2", style: "margin-top:8px" }, "비밀번호 확인"), pw2, mPw2,
    h("div", { class: "terms" }, h("label", { class: "all" }, all, "약관 전체 동의"), row(boxes[0], "[필수] 이용약관 동의"), row(boxes[1], "[필수] 개인정보 수집 · 이용 동의"), row(boxes[2], "[선택] 마케팅 정보 수신 동의")),
    mAll, go, h("p", { class: "foot-link" }, "이미 계정이 있나요? ", h("a", { href: "#/login" }, "로그인")));
  page(authLayout(f)); nick.focus();
}

/* ---------------------------------------------------------------- 라우터 */
let homeLoaded = false;
function showHome() { $("#page").hidden = true; $("#layout").hidden = false; if (!homeLoaded) { homeLoaded = true; reload(); } }
/* ---------------------------------------------------------------- 마이페이지 (프로필 · 팔로워/팔로잉 · 프로필 편집) */
const shortLink = (l) => l.replace(/^https?:\/\//i, "").replace(/\/$/, "");
const compact = (n) => (n >= 10000 ? (n / 1000).toFixed(0) + "k" : n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, "") + "k" : String(n));
async function toggleFollow(uid, on) { await api(`/api/users/${uid}/follow`, { method: on ? "DELETE" : "POST" }); }

function followsDialog(u, kind, after) {
  let cur = kind, list = [], q = "";
  const body = h("div", { class: "fl-body" });
  const tabs = h("div", { class: "fl-tabs", role: "tablist" });
  const m = h("div", { class: "modal", onmousedown: (e) => e.target === m && close() },
    h("div", { class: "dlg fol", role: "dialog", "aria-modal": "true", "aria-label": `${u.uid} 팔로워 / 팔로잉` },
      h("div", { class: "chd" }, h("h2", {}, u.uid), h("button", { class: "icon-btn", type: "button", "aria-label": "닫기", onclick: () => close() }, icon("close", 24))),
      tabs,
      h("label", { class: "fl-search" }, icon("search", 20), h("input", { type: "search", placeholder: "검색", "aria-label": "사용자 검색", oninput: (e) => { q = e.target.value.trim().toLowerCase(); drawList(); } })),
      body));
  const close = () => { m.remove(); after && after(); };
  const drawTabs = () => tabs.replaceChildren(...[["followers", `팔로워 ${compact(u.followers)}`], ["following", `팔로잉 ${compact(u.following)}`]].map(([k, l]) =>
    h("button", { type: "button", role: "tab", class: cur === k ? "on" : "", "aria-selected": String(cur === k), onclick: () => { cur = k; drawTabs(); load(); } }, l)));
  function drawList() {
    const rows = list.filter((x) => !q || x.uid.toLowerCase().includes(q) || x.nick.toLowerCase().includes(q));
    body.replaceChildren(...(rows.length ? rows.map((x) => {
      const isMine = u.me && cur === "following";
      const label = x.isFollowing ? "팔로잉" : (cur === "followers" && u.me ? "맞팔로우" : "팔로우");
      return h("div", { class: "fl-row" },
        h("a", { href: "#/u/" + x.uid, onclick: () => m.remove() }, avatarEl(x, 44)),
        h("a", { class: "fl-name", href: "#/u/" + x.uid, onclick: () => m.remove() }, h("b", {}, x.uid), h("span", {}, x.nick)),
        x.me ? null : h("button", { class: "btn" + (x.isFollowing ? "" : " primary"), type: "button", onclick: async () => {
          if (!ME) return needLogin();
          try { await toggleFollow(x.uid, x.isFollowing); x.isFollowing = !x.isFollowing; if (isMine && !x.isFollowing) { /* 목록에는 남겨 두고 버튼만 바꿈 */ } drawList(); } catch (e) { toast(e.message); }
        } }, label));
    }) : [h("p", { class: "nempty" }, q ? "검색 결과가 없어요" : cur === "followers" ? "아직 팔로워가 없어요" : "아직 팔로잉한 사용자가 없어요")]));
  }
  async function load() { body.replaceChildren(h("p", { class: "nempty" }, "불러오는 중…")); try { list = (await api(`/api/users/${u.uid}/follows?kind=${cur}`)).items; } catch (e) { list = []; toast(e.message); } drawList(); }
  drawTabs(); document.body.append(m); load();
}

async function profilePage(uid) {
  const root = h("div", { class: "pf" }); page(root);
  let u, tab = "posts", posts = [], books = [];
  async function loadAll() {
    u = await api("/api/users/" + uid);
    posts = (await api(`/api/users/${uid}/posts?limit=100`)).items;
    books = u.me ? (await api(`/api/users/${uid}/books`)).items : [];
  }
  function draw() {
    const links = h("div", { class: "pf-links" }, icon("link", 20), h("span", {}, ...u.links.flatMap((l, i) => [i ? " · " : "", h("a", { href: l, target: "_blank", rel: "noopener noreferrer nofollow" }, shortLink(l))])));
    const stat = (n, l, fn) => (fn ? h("button", { class: "pf-stat", type: "button", onclick: fn }, h("b", {}, compact(n)), h("span", {}, l)) : h("span", { class: "pf-stat" }, h("b", {}, compact(n)), h("span", {}, l)));
    const acts = u.me
      ? h("div", { class: "pf-acts" }, btn("프로필 편집", "l", () => (location.hash = "#/me/edit")), btn("+ 업로드", "primary l", () => openUpload()),
        h("button", { class: "icon-btn", type: "button", "aria-label": "설정", onclick: (e) => { e.stopPropagation(); popMenu(e.currentTarget, [["프로필 편집", () => (location.hash = "#/me/edit")], ["로그아웃", doLogout]]); } }, icon("settings", 24)))
      : h("div", { class: "pf-acts" }, btn(u.isFollowing ? "팔로잉" : "팔로우", (u.isFollowing ? "" : "primary ") + "l", async () => { if (!ME) return needLogin(); try { await toggleFollow(u.uid, u.isFollowing); await loadAll(); draw(); } catch (e) { toast(e.message); } }));
    const tabBtn = (k, l) => h("button", { class: "pf-tab" + (tab === k ? " on" : ""), type: "button", role: "tab", "aria-selected": String(tab === k), onclick: () => { tab = k; draw(); } }, l);
    const grid = tab === "posts"
      ? (posts.length ? h("div", { class: "pf-grid" }, posts.map((it) => h("button", { class: "pf-cell", type: "button", "aria-label": it.title || "레퍼런스 이미지", onclick: () => goPost(it.id) }, h("img", { src: it.thumb, alt: it.title || "", loading: "lazy" }))))
        : notice(u.me ? "아직 올린 게시물이 없어요" : "아직 올린 게시물이 없어요", u.me ? "첫 레퍼런스를 올리면 AI가 태그를 붙여 줘요." : "", u.me ? btn("+ 업로드", "primary", () => openUpload()) : null))
      : (books.length ? h("div", { class: "pf-grid" }, books.map((b) => h("button", { class: "pf-cell book", type: "button", "aria-label": `${b.name} 열기`, onclick: () => (location.hash = "#/drawer/book/" + b.id) },
        b.cover ? h("img", { src: b.cover, alt: "" }) : (b.covers[0] ? h("img", { src: `/img/${b.covers[0]}?s=thumb`, alt: "" }) : h("span", { class: "ph" })), h("span", { class: "bn" }, h("b", {}, b.name), h("span", {}, `${b.count}개`)))))
        : notice("아직 북이 없어요", "서랍에서 새 북을 만들어 보세요.", btn("서랍으로", "primary", () => (location.hash = "#/drawer"))));
    root.replaceChildren(
      h("div", { class: "pf-head" },
        h("div", { class: "pf-who" }, avatarEl(u, 120, "pf-av"),
          h("div", { class: "pf-txt" }, h("h1", {}, u.nick, h("small", {}, "@" + u.uid)), u.bio ? h("p", { class: "pf-bio" }, u.bio) : null, u.links.length ? links : null,
            h("div", { class: "pf-stats" }, stat(u.posts, "게시물"), stat(u.followers, "팔로워", () => followsDialog(u, "followers", refresh)), stat(u.following, "팔로잉", () => followsDialog(u, "following", refresh))))),
        acts),
      h("div", { class: "pf-tabs", role: "tablist" }, tabBtn("posts", `게시물 ${u.posts}`), u.me ? tabBtn("books", `북 ${u.books}`) : null),
      grid);
  }
  const refresh = async () => { try { await loadAll(); draw(); } catch { /* 유지 */ } };
  try { await loadAll(); draw(); } catch (e) { root.replaceChildren(notice("프로필을 찾을 수 없어요", e.message, btn("홈으로", "primary", () => (location.hash = "#/")))); }
}

async function profileEdit() {
  if (!needLogin()) return;
  const root = h("div", { class: "pe" }); page(root);
  let u; try { u = await api("/api/users/" + ME.uid); } catch (e) { root.replaceChildren(notice("불러오지 못했어요", e.message)); return; }
  let links = [...u.links], avatar = u.avatar;
  const avBox = h("div", { class: "pe-av" });
  const nick = h("input", { class: "inp", id: "peNick", value: u.nick, maxlength: "20", placeholder: "입력해 주세요", "aria-label": "닉네임" });
  const bio = h("textarea", { class: "inp ta", maxlength: "100", placeholder: "한 줄 소개를 입력하세요 (최대 100자)", "aria-label": "소개" }, u.bio);
  const file = h("input", { type: "file", accept: "image/jpeg,image/png", hidden: true, onchange: async (e) => {
    const f = e.target.files[0]; if (!f) return; if (f.size > 5 << 20) return toast("5MB 이하의 이미지만 올릴 수 있어요.");
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/api/me/avatar", { method: "POST", body: fd }); avatar = r.avatar; await loadMe(); drawAv(); toast("프로필 사진을 바꿨어요"); } catch (er) { toast(er.message); }
  } });
  const drawAv = () => avBox.replaceChildren(avatarEl({ nick: nick.value || u.nick, avatar }, 96, "pe-avt"),
    h("div", { class: "pe-avtx" }, h("div", { class: "pe-avbtns" }, btn("사진 변경", "", () => file.click()), avatar ? btn("삭제", "", async () => { try { await api("/api/me/avatar", { method: "DELETE" }); avatar = null; await loadMe(); drawAv(); } catch (er) { toast(er.message); } }) : null), h("span", {}, "JPG · PNG, 5MB 이하"), file));
  const linkBox = h("div", { class: "pe-links" });
  const drawLinks = () => linkBox.replaceChildren(...links.map((l, i) => h("div", { class: "pe-link" }, icon("link", 20),
      h("input", { value: l, "aria-label": `외부 링크 ${i + 1}`, placeholder: "https://", maxlength: "120", oninput: (e) => (links[i] = e.target.value) }),
      h("button", { type: "button", "aria-label": "링크 삭제", onclick: () => { links.splice(i, 1); drawLinks(); } }, icon("close", 20)))),
    links.length < 5 ? h("button", { class: "pe-add", type: "button", onclick: () => { links.push(""); drawLinks(); linkBox.querySelectorAll("input")[links.length - 1]?.focus(); } }, icon("plus", 20), "링크 추가") : null);
  drawAv(); drawLinks();
  const save = async (ev) => {
    const b = ev.currentTarget; b.disabled = true;
    try { await api("/api/me/profile", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ nick: nick.value, bio: bio.value, links: links.filter((x) => x.trim()) }) }); await loadMe(); toast("프로필을 저장했어요"); location.hash = "#/me"; }
    catch (er) { toast(er.message); b.disabled = false; }
  };
  root.replaceChildren(h("h1", {}, "프로필 편집"), avBox,
    h("div", { class: "pe-f" }, h("label", { for: "peNick" }, "닉네임"), nick),
    h("div", { class: "pe-f s" }, h("label", {}, "소개"), bio),
    h("div", { class: "pe-lh" }, h("h2", {}, "외부 링크"), h("span", {}, "최대 5개")), linkBox,
    h("div", { class: "pe-ft" }, btn("취소", "l", () => (location.hash = "#/me")), btn("저장", "primary l", save)));
}

function route() {
  const [, a = "", b = "", c = ""] = (location.hash.slice(1) || "/").split("/");
  document.body.classList.toggle("auth", a === "login" || a === "signup");
  document.querySelectorAll("#nav a").forEach((l) => { const on = l.dataset.r === (a === "post" ? "" : a); l.classList.toggle("on", on); on ? l.setAttribute("aria-current", "page") : l.removeAttribute("aria-current"); });
  $("#notif").hidden = true;
  if (ME && (a === "login" || a === "signup")) { location.hash = "#/"; return; }
  if (a === "login") loginPage();
  else if (a === "signup") signupPage();
  else if (a === "keep") keepPage();
  else if (a === "drawer") drawerPage(b, +c);
  else if (a === "me" && !ME) needLogin();
  else if (a === "me" && b === "edit") profileEdit();
  else if (a === "me") profilePage(ME.uid);
  else if (a === "u" && b) profilePage(decodeURIComponent(b));
  else if (a === "post" && +b) { showHome(); openDetail(+b); }
  else { showHome(); if (!$("#panel").hidden) closeDetail(); }
}
$("#home").onclick = (e) => { e.preventDefault(); if (location.hash && location.hash !== "#/") location.hash = "#/"; else { $("#reset").click(); closeDetail(); } };
window.addEventListener("hashchange", route);
setInterval(() => { if (ME) loadMe().catch(() => {}); }, 60000);
(async () => {
  try { await loadMe(); } catch { /* 서버에 연결되지 않음 */ }
  try { await loadVocab(); } catch (e) { $("#empty").hidden = false; $("#empty").replaceChildren(h("h2", {}, "서비스에 연결하지 못했어요"), h("p", {}, e.message)); }
  route();
})();
