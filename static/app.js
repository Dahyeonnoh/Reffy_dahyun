"use strict";
/* REFFY 프런트엔드 — 의존성 없음. 사용자 입력은 모두 textContent 로만 넣습니다. */
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const svg = (d) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("class", "ic"); s.setAttribute("aria-hidden", "true"); const p = document.createElementNS(s.namespaceURI, "path"); p.setAttribute("d", d); s.append(p); return s; };
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* 저장소를 못 쓰는 환경 */ } },
};
async function api(path, opt) {
  const r = await fetch(path, opt);
  let d = null; try { d = await r.json(); } catch { /* 본문 없음 */ }
  if (!r.ok) throw new Error((d && (d.detail || d.error)) || "요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.");
  return d;
}
function toast(msg, link) { const t = $("#toast"); t.replaceChildren(msg, link ? h("a", { href: link[1], onclick: () => t.classList.remove("show") }, link[0]) : ""); t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), link ? 5000 : 2600); }

const S = { q: "", picked: new Set(), applied: [], sort: "", items: [], total: 0, loading: false, done: false, vocab: null, labels: {}, open: null, req: 0, colors: [], pickColors: [], hist: [] };

/* ---------------------------------------------------------------- 사용자(서버 계정) */
let ME = null, UNREAD = 0;
async function loadMe() { const r = await api("/api/auth/me"); ME = r.user; UNREAD = r.unread; drawMe(); }
function drawMe() {
  $("#me").replaceChildren(ME ? (ME.avatar ? h("img", { src: ME.avatar, alt: "" }) : ME.nick.slice(0, 1).toUpperCase()) : "");
  $("#me").title = ME ? `${ME.nick} · 메뉴` : "로그인";
  $("#bell").classList.toggle("has", UNREAD > 0);
}
function needLogin() { if (ME) return true; sessionStorage.setItem("reffy.next", location.hash || "#/"); location.hash = "#/login"; return false; }
const goPost = (id) => { location.hash = "#/post/" + id; };

/* ---------------------------------------------------------------- 필터 패널 */
async function loadVocab() {
  S.vocab = await api("/api/vocab");
  S.vocab.groups.forEach((g) => g.axes.forEach((a) => a.tags.forEach((t) => (S.labels[t.ikey] = { label: t.kw, axis: a.name, group: g.name }))));
  drawGroups();
}
const openState = store.get("reffy.open", {});
function drawGroups() {
  const root = $("#groups"); root.replaceChildren();
  S.vocab.groups.forEach((g, gi) => {
    const open = openState[g.name] ?? gi === 0;
    const box = h("div", { class: "fgroup", "data-open": String(open) });
    const btn = h("button", { type: "button", "aria-expanded": String(open), onclick: () => { const o = box.dataset.open !== "true"; box.dataset.open = String(o); btn.setAttribute("aria-expanded", String(o)); openState[g.name] = o; store.set("reffy.open", openState); } }, g.name, icon("chevronDown"));
    const body = h("div", { class: "fbody" });
    g.axes.forEach((a) => body.append(h("div", { class: "axis" },
      h("h4", {}, a.name, a.mode === "단일" ? h("span", { class: "mode" }, "하나만") : null),
      a.tags.map((t) => h("label", { class: "chk" + (t.n ? "" : " zero") },
        h("input", { type: "checkbox", checked: S.picked.has(t.ikey), onchange: (e) => { e.target.checked ? S.picked.add(t.ikey) : S.picked.delete(t.ikey); } }),
        t.label, h("span", { class: "n" }, String(t.n)))))));
    box.append(btn, body); root.append(box);
  });
}
$("#apply").onclick = () => {
  if (CP.dirty && !$("#cpanel").hidden) { const c = hsv2hex(CP.h, CP.s, CP.v); if (!S.pickColors.includes(c)) S.pickColors = [...S.pickColors, c].slice(-5); CP.dirty = false; }   // 저장하지 않아도 지금 고른 색으로 적용
  S.applied = [...S.picked]; S.colors = [...S.pickColors]; if (!$("#cpanel").hidden) drawColorPanel(); reload();
};
$("#reset").onclick = () => { S.picked.clear(); S.applied = []; S.colors = []; S.pickColors = []; drawColorPanel(); S.q = ""; $("#q").value = ""; drawGroups(); reload(); };
$("#filterBtn").onclick = () => { const o = $("#layout").classList.toggle("f-open"); $("#filterBtn").setAttribute("aria-expanded", String(o)); };
$("#home").onclick = (e) => { e.preventDefault(); $("#reset").click(); closeDetail(); };

/* ---------------------------------------------------------------- 색상 필터 (컬러 팔레트) */
const hsv2hex = (h, s, v) => { const f = (n) => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); }; return "#" + [f(5), f(3), f(1)].map((x) => Math.round(x * 255).toString(16).padStart(2, "0")).join(""); };
const hex2hsv = (hex) => { const r = parseInt(hex.slice(1, 3), 16) / 255, g = parseInt(hex.slice(3, 5), 16) / 255, b = parseInt(hex.slice(5, 7), 16) / 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn; let hh = 0; if (d) hh = mx === r ? ((g - b) / d + 6) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; return { h: hh * 60, s: mx ? d / mx : 0, v: mx }; };
const CP = { h: 0, s: 0.75, v: 0.9, dirty: false };
const pastPal = () => store.get("reffy.pal", []);
function drawColorPanel() {
  const root = $("#cpanel"); root.replaceChildren();
  const cur = () => hsv2hex(CP.h, CP.s, CP.v);
  const add = (c) => { c = c.toLowerCase(); if (!S.pickColors.includes(c)) S.pickColors = [...S.pickColors, c].slice(-5); CP.dirty = false; drawColorPanel(); };
  const saveColor = (c) => { c = c.toLowerCase(); store.set("reffy.pal", [c, ...pastPal().filter((x) => x !== c)].slice(0, 15)); add(c); toast("지난 팔레트에 저장했어요"); };
  const box = h("div", { class: "cbox", role: "slider", "aria-label": "채도와 명도", tabindex: "0" }, h("span", { class: "cdot" }));
  const hue = h("input", { type: "range", min: "0", max: "360", step: "1", class: "chue", "aria-label": "색상(Hue)", value: String(Math.round(CP.h)) });
  const hex = h("input", { class: "chex", maxlength: "7", "aria-label": "색상 코드", value: cur().toUpperCase() });
  const sw = h("i", { class: "sw" });
  const paint = () => { box.style.background = `linear-gradient(to top,#000,transparent),linear-gradient(to right,#fff,hsl(${CP.h},100%,50%))`; box.firstChild.style.left = CP.s * 100 + "%"; box.firstChild.style.top = (1 - CP.v) * 100 + "%"; sw.style.background = cur(); hex.value = cur().toUpperCase(); hue.value = String(Math.round(CP.h)); };
  const pick = (e) => { CP.dirty = true; const r = box.getBoundingClientRect(); CP.s = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)); CP.v = 1 - Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)); paint(); };
  box.addEventListener("pointerdown", (e) => { box.setPointerCapture(e.pointerId); pick(e); box.onpointermove = pick; });
  box.addEventListener("pointerup", () => { box.onpointermove = null; });
  box.addEventListener("keydown", (e) => { const d = e.shiftKey ? 0.1 : 0.02; CP.dirty = true; if (e.key === "ArrowLeft") CP.s = Math.max(0, CP.s - d); else if (e.key === "ArrowRight") CP.s = Math.min(1, CP.s + d); else if (e.key === "ArrowUp") CP.v = Math.min(1, CP.v + d); else if (e.key === "ArrowDown") CP.v = Math.max(0, CP.v - d); else return; e.preventDefault(); paint(); });
  hue.oninput = () => { CP.h = +hue.value; CP.dirty = true; paint(); };
  const setHex = () => { let v = hex.value.trim(); if (/^#?[0-9a-fA-F]{6}$/.test(v)) { Object.assign(CP, hex2hsv("#" + v.replace("#", "")), { dirty: true }); paint(); } else { toast("#RRGGBB 형식으로 입력해 주세요"); paint(); } };
  hex.onchange = setHex; hex.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); setHex(); } };
  const eye = h("button", { class: "ceye", type: "button", "aria-label": "스포이트", title: "화면에서 색 고르기", onclick: async () => {
    if (!window.EyeDropper) return toast("이 브라우저는 스포이트를 지원하지 않아요. 크롬·엣지에서 써 보세요.");
    try { const r = await new EyeDropper().open(); Object.assign(CP, hex2hsv(r.sRGBHex), { dirty: true }); paint(); } catch { /* 취소 */ }
  } }, icon("eyedropper", 20));
  const circle = (c, fn, label) => h("button", { type: "button", class: "ccirc", style: `background:${c}`, title: label, "aria-label": `${c.toUpperCase()} ${label}`, onclick: fn });
  root.append(box, h("div", { class: "chrow" }, eye, hue),
    h("div", { class: "ccode" }, h("span", {}, "Color Code"), h("div", { class: "cfield" }, hex, sw), h("button", { class: "btn", type: "button", onclick: () => saveColor(cur()) }, "저장")),
    h("hr", { class: "cdiv" }),
    h("h3", { class: "ctit" }, "현재 팔레트"),
    h("div", { class: "cpal" }, h("button", { type: "button", class: "ccirc plus", "aria-label": "현재 색 추가", title: "현재 색 추가", onclick: () => add(cur()) }, icon("plus", 20)), S.pickColors.map((c) => circle(c, () => { S.pickColors = S.pickColors.filter((x) => x !== c); drawColorPanel(); }, "삭제"))),
    h("h3", { class: "ctit" }, "지난 팔레트"),
    h("div", { class: "cpal" }, pastPal().length ? pastPal().map((c) => h("span", { class: "pc-wrap" }, circle(c, () => add(c), "현재 팔레트에 추가"), h("button", { type: "button", class: "pc-x", "aria-label": `${c.toUpperCase()} 지난 팔레트에서 삭제`, onclick: () => { store.set("reffy.pal", pastPal().filter((x) => x !== c)); drawColorPanel(); } }, "×"))) : h("p", { class: "hint", style: "margin:0" }, "‘저장’을 누른 색이 여기에 남아 나중에 다시 쓸 수 있어요.")));
  paint();
}
async function pullPalette(id) {
  if (!(await confirmDialog("해당 이미지의 컬러를 ‘현재 팔레트’에 얹어 씌우겠습니까?", "이미지 대표 색 5개를 현재 팔레트로 불러와요.", { remember: "reffy.palAsk" }))) return;
  try {
    const r = await api(`/api/images/${id}/colors`);
    if (!r.colors.length) return toast("이 이미지에서 색을 찾지 못했어요.");
    S.pickColors = r.colors.map((c) => c[0]); CP.dirty = false;
    $("#layout").classList.add("f-open"); $("#filterBtn").setAttribute("aria-expanded", "true");
    showTab(true); toast("현재 팔레트에 색을 불러왔어요. ‘색상 적용하기’를 눌러 같은 색을 찾아보세요.");
  } catch (e) { toast(e.message); }
}
function showTab(color) {
  $("#groups").hidden = color; $("#cpanel").hidden = !color;
  $("#tabTag").classList.toggle("on", !color); $("#tabColor").classList.toggle("on", color);
  $("#tabTag").setAttribute("aria-selected", String(!color)); $("#tabColor").setAttribute("aria-selected", String(color));
  $("#apply").textContent = color ? "색상 적용하기" : "필터 적용하기";
  if (color) drawColorPanel();
}
$("#tabTag").onclick = () => showTab(false);
$("#tabColor").onclick = () => showTab(true);

/* ---------------------------------------------------------------- 검색창 */
const recent = () => store.get("reffy.recent", []);
function pushRecent(q) { const l = [q, ...recent().filter((x) => x !== q)].slice(0, 8); store.set("reffy.recent", l); }
async function drawSuggest() {
  const box = $("#suggest"); box.replaceChildren();
  const rc = recent();
  if (rc.length) box.append(h("h3", {}, "최근 검색어", h("button", { type: "button", onmousedown: (e) => { e.preventDefault(); store.set("reffy.recent", []); drawSuggest(); } }, "전체 삭제")),
    h("div", { class: "recent" }, rc.map((x) => h("span", { class: "chip" }, h("button", { type: "button", onmousedown: (e) => { e.preventDefault(); runQuery(x); } }, x), h("button", { type: "button", "aria-label": `${x} 삭제`, onmousedown: (e) => { e.preventDefault(); store.set("reffy.recent", recent().filter((y) => y !== x)); drawSuggest(); } }, "✕")))));
  let pop = [];
  try { pop = await api("/api/popular"); } catch { /* 인기 태그 없이 표시 */ }
  box.append(h("h3", {}, "인기 태그"));
  box.append(pop.length ? h("ol", { class: "pop" }, pop.map((p, i) => h("li", {}, h("button", { type: "button", onmousedown: (e) => { e.preventDefault(); runQuery(p.label); } }, h("b", {}, String(i + 1)), p.label)))) : h("p", { class: "none" }, "아직 태그가 붙은 이미지가 없어요. 이미지를 올려 보세요."));
}
const qEl = $("#q");
qEl.addEventListener("focus", () => { $("#suggest").hidden = false; drawSuggest(); });
qEl.addEventListener("blur", () => setTimeout(() => ($("#suggest").hidden = true), 120));
function runQuery(q) { S.q = q.trim(); qEl.value = S.q; if (S.q) pushRecent(S.q); $("#suggest").hidden = true; qEl.blur(); S.sort = ""; reload(); }
$("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); runQuery(qEl.value); });
const SORTS = [["recent", "최근 순"], ["popular", "인기 순"], ["relevance", "관련도 순"]];
let curSort = "recent";
function drawSort() {
  $("#sortLabel").textContent = SORTS.find((x) => x[0] === curSort)[1];
  const m = $("#sortMenu"); m.replaceChildren(...SORTS.map(([k, l]) => h("button", { type: "button", role: "option", "aria-selected": String(k === curSort), onclick: () => { S.sort = k; curSort = k; m.hidden = true; $("#sortBtn").setAttribute("aria-expanded", "false"); drawSort(); reload(); } }, l, k === curSort ? icon("check") : null)));
}
$("#sortBtn").onclick = (e) => { e.stopPropagation(); const m = $("#sortMenu"); m.hidden = !m.hidden; $("#sortBtn").setAttribute("aria-expanded", String(!m.hidden)); };
document.addEventListener("click", () => { $("#sortMenu").hidden = true; });
drawSort();

/* ---------------------------------------------------------------- 피드(무한 스크롤) */
function card(it) {
  const img = h("img", { src: it.thumb, alt: it.title || "레퍼런스 이미지", loading: "lazy", width: it.w || null, height: it.h || null });
  return h("button", { class: "card" + (S.open === it.id ? " sel" : ""), type: "button", "data-id": it.id, onclick: () => openDetail(it.id) },
    h("span", { class: "im" }, img, h("span", { class: "palbtn", role: "button", tabindex: "0", "aria-label": "이 이미지의 색상으로 팔레트 만들기", title: "이 이미지의 색상을 팔레트로",
      onclick: (e) => { e.stopPropagation(); pullPalette(it.id); }, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); pullPalette(it.id); } } }, icon("palette", 20))),
    h("span", { class: "meta" }, h("span", { class: "av" }, (it.author || "?").slice(0, 1)), h("span", { class: "tx" }, h("b", {}, it.title || "제목 없음"), h("span", {}, it.author)), moreIc()));
}
const moreIc = () => icon("more", 24);
function skeleton() { const g = $("#grid"); for (let i = 0; i < 10; i++) g.append(h("div", { class: "card skel" }, h("span", { class: "im", style: `aspect-ratio:3/${3 + (i % 3)}` }))); }
async function reload() {
  S.items = []; S.total = 0; S.done = false; $("#grid").replaceChildren(); $("#empty").hidden = true;
  await more(true);
}
async function more(first) {
  if (S.loading || S.done) return;
  S.loading = true; const my = ++S.req;
  if (first) skeleton();
  const p = new URLSearchParams({ q: S.q, tags: S.applied.join(","), offset: S.items.length });
  if (S.sort) p.set("sort", S.sort);
  if (S.colors.length) p.set("color", S.colors.join(","));
  try {
    const d = await api("/api/images?" + p);
    if (my !== S.req) return;
    if (first) $("#grid").replaceChildren();
    S.items.push(...d.items); S.total = d.total;
    $("#grid").append(...d.items.map(card));
    S.done = d.items.length === 0 || S.items.length >= d.total;
    drawBar(d);
  } catch (e) {
    if (first) $("#grid").replaceChildren();
    $("#empty").hidden = false; $("#empty").replaceChildren(h("h2", {}, "불러오지 못했어요"), h("p", {}, e.message), h("button", { class: "btn", onclick: () => reload() }, "다시 시도"));
  } finally { S.loading = false; }
}
function drawBar(d) {
  const hasQ = !!S.q;
  const t = $("#resultTitle"); t.textContent = hasQ ? `“${S.q}”` : (S.applied.length || S.colors.length ? "검색 결과" : "레퍼런스"); t.className = hasQ ? "q" : "";
  $("#count").textContent = `${S.total.toLocaleString()}개`;
  curSort = d.sort; drawSort();
  const chips = $("#chips"); chips.replaceChildren();
  const seen = new Set();
  [...d.matched.map((m) => ({ ...m, dark: true })), ...S.applied.map((k) => ({ ikey: k, label: S.labels[k]?.label || k }))].forEach((m) => {
    if (seen.has(m.ikey)) return; seen.add(m.ikey);
    chips.append(h("span", { class: "chip dark" }, "#" + m.label, S.applied.includes(m.ikey) ? h("button", { type: "button", "aria-label": `${m.label} 필터 해제`, onclick: () => { S.picked.delete(m.ikey); S.applied = S.applied.filter((x) => x !== m.ikey); drawGroups(); reload(); } }, "✕") : null));
  });
  S.colors.forEach((c) => chips.append(h("span", { class: "chip dark" }, h("i", { class: "sw", style: `background:${c}` }), c.toUpperCase(),
    h("button", { type: "button", "aria-label": `${c} 색상 해제`, onclick: () => { S.colors = S.colors.filter((x) => x !== c); S.pickColors = [...S.colors]; drawColorPanel(); reload(); } }, "✕"))));
  const e = $("#empty");
  if (!S.total) {
    e.hidden = false;
    const any = hasQ || S.applied.length || S.colors.length;
    e.replaceChildren(h("h2", {}, any ? "조건에 맞는 레퍼런스가 없어요" : "아직 레퍼런스가 없어요"),
      h("p", {}, any ? "검색어를 줄이거나 필터를 하나씩 풀어 보세요." : "첫 이미지를 올리면 AI가 태그를 붙여 줘요."),
      any ? h("button", { class: "btn", onclick: () => $("#reset").click() }, "조건 초기화") : h("button", { class: "btn primary", onclick: openUpload }, "이미지 올리기"));
  } else e.hidden = true;
}
new IntersectionObserver((en) => { if (en[0].isIntersecting && S.items.length) more(false); }, { rootMargin: "600px" }).observe($("#more"));

/* ---------------------------------------------------------------- 태그 추가 선택기 */
let vocabFlat = null;
function flat() { return vocabFlat || (vocabFlat = S.vocab.groups.flatMap((g) => g.axes.flatMap((a) => a.tags.map((t) => ({ ikey: t.ikey, label: t.label, axis: a.name }))))); }
function picker(onPick, exclude) {
  const box = h("div", { class: "box" });
  const input = h("input", { type: "search", placeholder: "태그 이름 검색", "aria-label": "태그 검색" });
  const list = h("div", {});
  const draw = () => {
    const q = input.value.trim().toLowerCase(); list.replaceChildren();
    flat().filter((t) => !exclude().has(t.ikey) && (!q || t.label.toLowerCase().includes(q) || t.axis.toLowerCase().includes(q))).slice(0, 30)
      .forEach((t) => list.append(h("button", { class: "opt", type: "button", onclick: () => { onPick(t); draw(); } }, t.label, h("small", {}, t.axis))));
    if (!list.children.length) list.append(h("p", { class: "hint" }, "맞는 태그가 없어요."));
  };
  input.oninput = draw; box.append(input, list); draw(); setTimeout(() => input.focus(), 0);
  return box;
}

/* ---------------------------------------------------------------- 상세 패널 */
async function openDetail(id, back = false) {
  if (!back && S.open && S.open !== id) S.hist.push(S.open);   // back 버튼용: 직전에 본 이미지 기록
  S.open = id; document.querySelectorAll(".card").forEach((c) => c.classList.toggle("sel", +c.dataset.id === id));
  const panel = $("#panel"); panel.hidden = false; $("#layout").classList.add("has-panel");
  panel.replaceChildren(h("div", { class: "pbody" }, "불러오는 중…"));
  try { const [d, so] = await Promise.all([api("/api/images/" + id), api("/api/images/" + id + "/social")]); d.so = so; drawDetail(d); }
  catch (e) { panel.replaceChildren(h("div", { class: "pbody" }, h("p", {}, e.message))); }
}
function goBack() { const p = S.hist.pop(); if (p != null) openDetail(p, true); }
function closeDetail() {
  S.hist = []; S.open = null; $("#panel").hidden = true; $("#layout").classList.remove("has-panel");
  document.querySelectorAll(".card.sel").forEach((c) => c.classList.remove("sel"));
  if (location.hash.startsWith("#/post/")) location.hash = "#/";
}
async function refreshSocial(d, edit = false) { try { d.so = await api(`/api/images/${d.id}/social`); drawDetail(d, edit); } catch (e) { toast(e.message); } }
async function act(d, method, url, body, edit) {
  if (!needLogin()) return;
  try { await api(url, { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined }); await refreshSocial(d, edit); if (method === "POST" && url.endsWith("/keep")) toast("킵 스페이스에 담았어요. 나중에 골라서 북에 정리하세요.", ["킵 스페이스 보기", "#/keep"]); } catch (e) { toast(e.message); }
}
function drawDetail(d, edit = false) {
  const panel = $("#panel"); const so = d.so || { likes: 0, comments: [], owner: null, editable: false };
  const act_ = d.tags.filter((t) => t.active), off = d.tags.filter((t) => !t.active);
  const pct = (t) => (t.prob != null && t.user !== "add" ? Math.round(t.prob * 100) + "%" : "");
  const tagEl = (t) => edit
    ? h("button", { class: "tag " + (t.user === "add" ? "user" : "ai"), type: "button", title: "눌러서 삭제", "aria-label": `${t.label} 태그 삭제`, onclick: () => save(d, { remove: [t.ikey] }, t) }, "#" + t.label, h("span", { class: "pr" }, pct(t)), h("x", {}, "×"))
    : h("button", { class: "tag" + (t.user === "add" ? " user" : ""), type: "button", title: t.prob != null && t.user !== "add" ? `AI 예측 ${pct(t)}` : "직접 추가한 태그", onclick: () => { S.picked = new Set([t.ikey]); S.applied = [t.ikey]; S.q = ""; qEl.value = ""; drawGroups(); reload(); } }, "#" + t.label);
  const box = h("div", { class: "pick" });
  const o = so.owner;
  const comment = h("input", { class: "cin", maxlength: "500", placeholder: ME ? "댓글을 남겨 보세요" : "로그인하고 댓글을 남겨 보세요", "aria-label": "댓글 입력" });
  const send = () => { const v = comment.value.trim(); if (!ME) return needLogin(); if (v) act(d, "POST", `/api/images/${d.id}/comments`, { body: v }, edit); };
  comment.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); send(); } };
  const palBtn = h("button", { type: "button", class: "palbtn", "aria-label": "이 이미지의 색상으로 팔레트 만들기", title: "이 이미지의 색상을 팔레트로", onclick: () => pullPalette(d.id) }, icon("palette", 20));
  panel.replaceChildren(
    h("div", { class: "pimg" }, h("img", { src: d.full, alt: d.title || "레퍼런스 이미지" }),
      h("button", { class: "back", type: "button", "aria-label": "이전에 본 이미지", title: "이전에 본 이미지", disabled: !S.hist.length, onclick: goBack }, icon("arrowLeft", 24)),
      h("button", { class: "close", type: "button", "aria-label": "창 닫기", title: "닫기", onclick: closeDetail }, icon("close", 24)),
      h("div", { class: "imgact" }, palBtn)),
    h("div", { class: "pbody" },
      h("div", { class: "who" }, o ? avatarEl(o, 36, "av") : h("span", { class: "av" }, (d.author || "?").slice(0, 1)),
        h("div", {}, o ? h("a", { class: "pname", href: "#/u/" + o.uid }, d.author) : h("b", {}, d.author), h("span", {}, o ? `@${o.uid} · 조회 ${d.views.toLocaleString()}` : `조회 ${d.views.toLocaleString()} · ${d.w}×${d.h}`)),
        o && !o.me ? h("button", { class: "btn" + (o.following ? "" : " primary"), type: "button", onclick: () => act(d, o.following ? "DELETE" : "POST", `/api/users/${o.uid}/follow`, null, edit) }, o.following ? "Following" : "Follow") : null),
      h("h2", { class: "ptitle" }, d.title || "제목 없음"),
      h("div", { class: "prow" },
        h("button", { class: "stat" + (so.liked ? " on" : ""), type: "button", "aria-pressed": String(!!so.liked), "aria-label": "하트", onclick: () => act(d, so.liked ? "DELETE" : "POST", `/api/images/${d.id}/like`, null, edit) }, icon("heart", 20), String(so.likes)),
        h("button", { class: "stat", type: "button", "aria-label": "댓글", onclick: () => comment.focus() }, icon("comment", 20), String(so.comments.length)),
        h("span", { class: "sp" }),
        h("button", { class: "btn", type: "button", onclick: () => act(d, so.kept ? "DELETE" : "POST", `/api/images/${d.id}/keep`, null, edit) }, so.kept ? "킵 해제" : "킵에 담기"),
        h("button", { class: "btn primary", type: "button", onclick: () => needLogin() && saveToBook([d.id], { after: () => refreshSocial(d, edit) }) }, "북에 저장")),
      h("div", { class: "sec" },
        h("div", { class: "sec-h" }, h("h3", {}, "태그"), so.editable ? h("button", { class: "btn sm", type: "button", onclick: () => drawDetail(d, !edit) }, edit ? "수정 완료" : "태그 수정") : null),
        h("div", { class: "tags" }, act_.length ? act_.map(tagEl) : h("span", { class: "hint" }, "아직 태그가 없어요.")),
        edit ? h("div", { class: "tags", style: "margin-top:10px" }, pickButton(box, (t) => save(d, { add: [t.ikey] }, t), () => new Set(d.tags.filter((x) => x.active).map((x) => x.ikey))),
          off.map((t) => h("button", { class: "tag off", type: "button", title: "눌러서 되돌리기", onclick: () => save(d, { restore: [t.ikey] }, t) }, "#" + t.label))) : null,
        edit ? h("p", { class: "hint" }, "AI가 붙인 태그를 눌러 지우거나, 흐린 태그를 눌러 되살릴 수 있어요. 같은 축의 ‘하나만’ 항목은 하나만 남겨 주세요.") : h("p", { class: "hint" }, "태그를 누르면 같은 태그의 레퍼런스를 모아 볼 수 있어요."),
        edit ? h("button", { class: "linkbtn danger", type: "button", onclick: () => removePost(d) }, "게시물 삭제") : null),
      h("div", { class: "sec" },
        h("div", { class: "sec-h" }, h("h3", {}, `댓글 ${so.comments.length}`)),
        h("div", { class: "cform" }, comment, h("button", { class: "btn primary", type: "button", onclick: send }, "등록")),
        h("ul", { class: "clist" }, so.comments.map((c) => h("li", {}, h("span", { class: "av lg" }, c.nick.slice(0, 1)),
          h("div", { class: "ct" }, h("b", {}, c.nick, h("small", {}, ago(c.created))), h("span", {}, c.body)),
          c.mine ? h("button", { class: "linkbtn", type: "button", "aria-label": "댓글 삭제", onclick: () => act(d, "DELETE", `/api/comments/${c.id}`, null, edit) }, "삭제") : null))))));
}
async function removePost(d) {
  if (!(await confirmDialog("이 게시물을 삭제할까요?", "되돌릴 수 없어요."))) return;
  try { await api("/api/images/" + d.id, { method: "DELETE" }); closeDetail(); toast("게시물을 삭제했어요"); reload(); loadVocab().catch(() => {}); } catch (e) { toast(e.message); }
}
async function save(d, body, tag, keepPicker) {
  // 단일 축에 이미 활성 태그가 있으면 새로 추가하는 태그와 바꿔 줍니다
  const full = { add: [], remove: [], restore: [], ...body };
  if (full.add.length && S.vocab) {
    const ax = S.labels[full.add[0]]?.axis; const one = S.vocab.groups.flatMap((g) => g.axes).find((a) => a.name === ax && a.mode === "단일");
    if (one) d.tags.filter((t) => t.active && S.labels[t.ikey]?.axis === ax).forEach((t) => full.remove.push(t.ikey));
  }
  try {
    const r = await api(`/api/images/${d.id}/tags`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(full) });
    d.tags = r.tags; drawDetail(d, true);
    loadVocab().catch(() => {});
  } catch (e) { toast(e.message); }
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if ($(".modal")) $(".modal").remove(); else if (!$("#panel").hidden) closeDetail(); } });

/* ---------------------------------------------------------------- 업로드: 분석 -> 태그 확인 -> 게시 */
let up = null;
function closeUpload() { $(".modal")?.remove(); up = null; }
function openUpload() {
  if (!needLogin()) return;
  up = { token: null, tags: new Map(), file: null, kind: "illust" };
  const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp,image/gif", hidden: true, onchange: (e) => e.target.files[0] && analyze(e.target.files[0]) });
  const drop = h("div", { class: "drop", tabindex: "0", role: "button", "aria-label": "이미지 선택", onclick: () => input.click(), onkeydown: (e) => (e.key === "Enter" || e.key === " ") && input.click(),
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); }, ondragleave: () => drop.classList.remove("over"), ondrop: (e) => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && analyze(e.dataTransfer.files[0]); } },
    h("b", {}, "이미지를 끌어다 놓거나 눌러서 선택하세요"), h("p", {}, "JPG · PNG · WEBP · GIF, 15MB 이하. 올리면 AI가 태그를 붙여 줘요."), input);
  const m = h("div", { class: "modal upl" },
    h("div", { class: "dlg", role: "dialog", "aria-modal": "true", "aria-label": "새 게시물" }, h("header", {}, h("h2", {}, "새 게시물"), h("button", { class: "icon-btn", type: "button", "aria-label": "닫기", onclick: closeUpload }, icon("close"))), h("div", { id: "upBody" }, drop)));
  document.body.append(m);
}
async function analyze(file) {
  const body = $("#upBody"); const url = URL.createObjectURL(file);
  body.replaceChildren(h("div", { class: "up" }, h("div", { class: "pv" }, h("img", { src: url, alt: "올린 이미지" })), h("div", {}, h("p", {}, h("span", { class: "busy" }), "AI가 태그를 붙이는 중이에요…"))));
  const fd = new FormData(); fd.append("file", file);
  try {
    const r = await api("/api/analyze", { method: "POST", body: fd });
    up.token = r.token; up.tags = new Map(r.tags.map((t) => [t.ikey, t])); up.url = url; up.msg = r.message; up.sec = r.seconds;
    drawUpload();
  } catch (e) { body.replaceChildren(h("div", { class: "up", style: "grid-template-columns:1fr" }, h("div", {}, h("div", { class: "note warn" }, e.message), h("button", { class: "btn", onclick: () => { closeUpload(); openUpload(); } }, "다른 이미지 고르기")))); }
}
function pickButton(box, onPick, exclude) {
  box.append(h("button", { class: "btn sm", type: "button", onclick: () => {
    const open = box.querySelector(".box"); if (open) { open.remove(); return; }
    box.append(picker(onPick, exclude));
  } }, "+ 태그 추가"));
  return box;
}
function singleAxis(ax) { return S.vocab.groups.flatMap((g) => g.axes).find((a) => a.name === ax && a.mode === "단일"); }
function drawUpload() {
  const body = $("#upBody"); const tags = [...up.tags.values()];
  const byAxis = new Map(); tags.forEach((t) => { const k = (S.labels[t.ikey]?.axis) || t.group; if (!byAxis.has(k)) byAxis.set(k, []); byAxis.get(k).push(t); });
  const title = h("input", { id: "upTitle", maxlength: "120", placeholder: "예) 앉아서 뒤돌아보는 포즈", value: up.title || "", oninput: (e) => (up.title = e.target.value) });
  const tagBtn = (t) => h("button", { type: "button", class: "tag " + (t.manual ? "user" : "ai"), title: "눌러서 삭제", "aria-label": `${t.label} 태그 삭제`, onclick: () => { up.tags.delete(t.ikey); drawUpload(); } },
    "#" + t.label, t.prob != null && !t.manual ? h("span", { class: "pr" }, Math.round(t.prob * 100) + "%") : null, h("x", {}, "×"));
  const onPick = (t) => {
    if (singleAxis(t.axis)) [...up.tags.values()].filter((x) => S.labels[x.ikey]?.axis === t.axis).forEach((x) => up.tags.delete(x.ikey));
    up.tags.set(t.ikey, { ikey: t.ikey, label: t.label, manual: true, group: "" }); drawUpload();
  };
  const right = h("div", {},
    up.msg ? h("div", { class: "note warn" }, up.msg) : h("div", { class: "note" }, `AI가 ${tags.length}개의 태그를 붙였어요 (${up.sec}초). 틀린 태그는 지우고, 빠진 태그는 추가하세요.`),
    h("div", { class: "field" }, h("label", { for: "upTitle" }, "제목"), title),
    h("div", { class: "field" }, h("label", {}, "종류"), h("div", { class: "seg", role: "radiogroup" }, [["illust", "일러스트"], ["photo", "사진"]].map(([k, l]) => h("button", { type: "button", role: "radio", "aria-checked": String(up.kind === k), class: up.kind === k ? "on" : "", onclick: () => { up.kind = k; drawUpload(); } }, l)))),
    h("div", { class: "field" }, h("label", {}, "태그"),
      tags.length ? [...byAxis].map(([ax, ts]) => h("div", { class: "axisgrp" }, h("h4", {}, ax), h("div", { class: "tags" }, ts.map(tagBtn)))) : h("p", { class: "hint" }, "붙은 태그가 없어요. 아래에서 직접 추가하세요."),
      pickButton(h("div", { class: "pick" }), onPick, () => new Set(up.tags.keys()))));
  body.replaceChildren(h("div", { class: "up" }, h("div", { class: "pv" }, h("img", { src: up.url, alt: "올린 이미지" })), right),
    h("div", { class: "foot" }, h("button", { class: "btn", type: "button", onclick: closeUpload }, "취소"), h("button", { class: "btn primary", id: "pub", type: "button", onclick: publish }, "게시하기")));
}
async function publish() {
  const b = $("#pub"); b.disabled = true; b.textContent = "게시하는 중…";
  try {
    const r = await api("/api/images", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: up.token, title: up.title || "", kind: up.kind || "illust", tags: [...up.tags.keys()] }) });
    closeUpload(); toast("게시했어요"); if (location.hash !== "#/") location.hash = "#/"; await reload(); loadVocab().catch(() => {}); openDetail(r.id);
  } catch (e) { b.disabled = false; b.textContent = "게시하기"; toast(e.message); }
}
$("#uploadBtn").onclick = openUpload;

