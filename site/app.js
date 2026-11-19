/* Salmons FPL - single-file front end. Reads data.json built by scripts/build.py. */
(() => {
"use strict";

// ------------------------------------------------------------------ state
let D = null;
const S = {
  tab: "week", sub: "home",
  me: lsGet("me", "1") === "1",
  squad: null, totw: null, raceHl: null,
  wirePos: "all", wireMin: 270,
  dir: "",
};
const POS = { 1: "GK", 2: "DEF", 3: "MID", 4: "FWD" };
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

function lsGet(k, d) { try { const v = localStorage.getItem("sfpl:" + k); return v === null ? d : v; } catch { return d; } }
function lsSet(k, v) { try { localStorage.setItem("sfpl:" + k, v); } catch { /* private mode */ } }
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ------------------------------------------------------------------ nav model
const ICONS = {
  week: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M12 3l2.7 5.6 6.1.8-4.4 4.3 1 6.1L12 17l-5.4 2.8 1-6.1-4.4-4.3 6.1-.8z"/></svg>',
  table: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h11"/></svg>',
  squads: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="9" cy="8" r="3.2"/><circle cx="17" cy="9" r="2.4"/><path d="M3 19c.8-3.2 3.2-5 6-5s5.2 1.8 6 5M15 14.5c2.6-.6 5 .9 6 4"/></svg>',
  transfers: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8h14l-3.5-3.5M20 16H6l3.5 3.5"/></svg>',
  history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M7 4h10v5a5 5 0 01-10 0zM7 6H4v1a3 3 0 003 3M17 6h3v1a3 3 0 01-3 3M12 14v4M8 20h8"/></svg>',
};
const SHARE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3M7 8l5-5 5 5M5 13v6a2 2 0 002 2h10a2 2 0 002-2v-6"/></svg>';

function tabs() {
  const season = (D && D.meta.season) || "";
  const short = season.length >= 7 ? season.slice(2, 5) + season.slice(5) : season;
  return [
    { id: "week", label: "This week", subs: [["home", "Home"], ["totw", "TOTW"], ["midweek", "Midweek"], ["preview", "Preview"], ["waivers", "Waivers"]] },
    { id: "table", label: "Table", subs: [["standings", "Standings"], ["power", "Power"], ["race", "The race"]] },
    { id: "squads", label: "Squads", subs: [["squads", "Squads"], ["needs", "Needs"]] },
    { id: "transfers", label: "Transfers", subs: [["wire", "Waiver wire"], ["trades", "Trades"], ["swaps", "Swap Shop"]] },
    { id: "history", label: "History", subs: [["records", "Records"], ["past", "Past seasons"], ["draft", "Draft " + short]] },
  ];
}

// ------------------------------------------------------------------ data helpers
const M = (id) => D.managers.find((m) => m.id === +id) || { name: "?", ini: "?", team: "", col: "#888" };
const P = (pid) => D.players[pid] || { n: "?", p: 3, t: 0, gw: [], pr: [] };
const T = (tid) => (D.teams[tid] || { s: "?" }).s;
const isMe = (id) => +id === D.meta.me;
const meAttr = (id) => (isMe(id) ? ` data-me${S.me ? ' class="me"' : ""}` : "");
const fmt = (n, d = 0) => (n == null ? "–" : Number(n).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }));
const signed = (n, d = 1) => (n > 0 ? "+" : n < 0 ? "−" : "") + fmt(Math.abs(n), d);
const plural = (n, w, ws) => `${n} ${n === 1 ? w : ws || w + "s"}`;
const ordinal = (n) => n + (n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th"));
const names = (ids) => { const n = ids.map((i) => M(i).name); return n.length < 2 ? n.join("") : n.slice(0, -1).join(", ") + " and " + n.at(-1); };

function av(id, cls = "") {
  const m = M(id);
  return `<span class="av ${cls} ${isMe(id) && S.me ? "me" : ""}" title="${esc(m.full || m.name)}">${esc(m.ini)}</span>`;
}
function who(id, opts = {}) {
  const m = M(id);
  return `<span class="who">${av(id, opts.size || "")}<span style="min-width:0"><span class="nm">${esc(m.name)}</span>${opts.arrow || ""}${
    opts.team ? `<br><span class="tm">${esc(m.team)}</span>${m.champ ? ' <span class="champ">🏆 (c)</span>' : ""}` : ""}</span></span>`;
}
function arrow(move) {
  if (move > 0) return `<span class="arrow up"><span class="arrow-up">▲</span>${move}</span>`;
  if (move < 0) return `<span class="arrow down"><span class="arrow-down">▼</span>${-move}</span>`;
  return `<span class="arrow flat">–</span>`;
}
function pTag(pid, opts = {}) {
  const p = P(pid);
  return `<span class="nm">${esc(p.n)}</span> <span class="club">${opts.pos === false ? "" : POS[p.p] + " "}${T(p.t)}</span>`;
}
function flagFor(p) {
  if (p.s === "u" || p.s === "n") return '<span class="flag out">GONE</span>';
  if (p.s === "i") return '<span class="flag out">INJ</span>';
  if (p.s === "s") return '<span class="flag out">SUS</span>';
  if (p.s === "d" || (p.cop != null && p.cop < 100)) return `<span class="flag">${p.cop ?? 50}%</span>`;
  return "";
}
function fxChips(tid, n = 3) {
  const fx = (D.fx[tid] || []).slice(0, n);
  if (!fx.length) return '<span class="fx"><span>—</span></span>';
  return `<span class="fx">${fx.map((f) => `<span class="f${f.d}" title="GW${f.gw} · FDR ${f.d}">${f.h ? T(f.o) : T(f.o).toLowerCase()}</span>`).join("")}</span>`;
}
function spark(arr, w = 110, h = 26) {
  const max = Math.max(10, ...arr);
  const bw = w / Math.max(arr.length, 1);
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" data-spark='${JSON.stringify(arr)}'>${arr.map((v, i) => {
    const bh = Math.max(2, (Math.max(v, 0) / max) * (h - 2));
    return `<rect x="${(i * bw + 1).toFixed(1)}" y="${(h - bh).toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${bh.toFixed(1)}" rx="1" class="${v <= 0 ? "z" : v >= 10 ? "hit" : ""}"/>`;
  }).join("")}</svg>`;
}
const cu = (v, d = 0) => `<span class="cu" data-v="${v}" data-d="${d}">${fmt(v, d)}</span>`;
const lastGw = () => D.meta.after;
const gwData = (g) => D.gws[String(g)];
function when(iso, withDay = true) {
  if (!iso) return "–";
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "short", timeZone: "Europe/London" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" });
  return withDay ? `${day} at ${time}` : time;
}

// ------------------------------------------------------------------ views
const V = {};

V.home = () => {
  const st = D.standings;
  if (!st.length) return empty("The season hasn't started yet.");
  const lead = st[0], second = st[1];
  const gap = lead.total - (second ? second.total : 0);
  const g = gwData(lastGw());
  const aw = g ? g.awards : null;
  const moves = st.map((s) => ({ id: s.id, m: s.move }));
  const up = moves.reduce((a, b) => (b.m > a.m ? b : a), { m: 0 });
  const down = moves.reduce((a, b) => (b.m < a.m ? b : a), { m: 0 });
  const nx = D.meta.next;
  return `
  ${D.meta.live ? `<a class="banner" href="#/week/midweek" style="text-decoration:none"><span><span class="live-badge">LIVE</span>&nbsp; GW${D.live.gw} is on. Provisional scores in Midweek.</span><span>→</span></a>` : ""}
  <div class="hero">
    <div class="label">Top of the table</div>
    <div class="big">${av(lead.id, "lg")}${esc(M(lead.id).name.toUpperCase())}</div>
    <div class="meta"><b>${cu(lead.total)} pts</b> · ${second ? (gap ? `${gap} clear of ${esc(M(second.id).name)}` : `level with ${esc(M(second.id).name)}`) : ""}</div>
  </div>
  <div class="tiles">
    ${aw ? tile("Manager of the week", aw.motw.ids, cu(aw.motw.pts), "y") : ""}
    ${aw ? tile("Stinker of the week", aw.stinker.ids, cu(aw.stinker.pts), "bad") : ""}
    ${tile("Biggest climber", up.m > 0 ? [up.id] : [], up.m > 0 ? `▲${up.m}` : "–", "good")}
    ${tile("Biggest faller", down.m < 0 ? [down.id] : [], down.m < 0 ? `▼${-down.m}` : "–", "bad")}
  </div>
  ${nx && nx.gw ? `<div class="deadline">
    <div class="label">GW${nx.gw} deadline</div>
    <div class="when">${when(nx.deadline)}</div>
    <div class="note" style="margin:0">Waivers process ${when(nx.waivers)}. <a href="#/transfers/wire">Check the waiver wire</a>.</div>
  </div>` : ""}
  <div class="note" style="margin-top:18px">After gameweek ${lastGw()}. <a href="#/week/totw">Read the Team of the Week →</a></div>`;
};
function tile(label, ids, val, kind) {
  return `<div class="tile ${kind === "y" ? "y" : ""}"><div class="label">${label}</div>
    ${ids.length ? `<div class="who">${av(ids[0], "sm")}<span class="nm">${esc(names(ids))}</span></div>` : '<div class="who"><span class="tm">Nobody moved</span></div>'}
    <div class="val ${kind === "good" ? "good" : kind === "bad" ? "bad" : ""}">${val}</div></div>`;
}

V.totw = () => {
  const gws = Object.keys(D.gws).map(Number).sort((a, b) => b - a);
  if (!gws.length) return empty("No finished gameweeks yet.");
  const g = S.totw && D.gws[S.totw] ? S.totw : gws[0];
  const d = gwData(g), aw = d.awards, wu = d.writeup || {};
  const card = (key, cls, label, title, text, id) => `
    <div class="card award ${cls}" data-award="${key}" data-gw="${g}">
      <button class="share-btn" data-share="${key}" aria-label="Share ${label}">${SHARE_ICON}</button>
      <div class="label">${label}</div>
      <div class="head">${id != null ? av(id) : ""}<h4>${esc(title)}</h4></div>
      ${text ? `<p>${esc(text)}</p>` : ""}
    </div>`;
  const cards = [];
  cards.push(card("motw", "gold", "Manager of the week", `${names(aw.motw.ids).toUpperCase()} · ${aw.motw.pts}`, wu.motw, aw.motw.ids[0]));
  cards.push(card("stinker", "red", "Stinker of the week", `${names(aw.stinker.ids).toUpperCase()} · ${aw.stinker.pts}`, wu.stinker, aw.stinker.ids[0]));
  if (aw.bench.ids.length) cards.push(card("bench", "", "Bench of the week", `${names(aw.bench.ids).toUpperCase()} · ${aw.bench.pts}`, wu.bench, aw.bench.ids[0]));
  if (aw.bench_jam) cards.push(card("bench_jam", "", "Bench jam of the week", `${P(aw.bench_jam.pid).n.toUpperCase()} ${aw.bench_jam.pts}`, wu.bench_jam, aw.bench_jam.id));
  if (aw.red_card) cards.push(card("red_card", "", "Red card of the week", `${P(aw.red_card.pid).n.toUpperCase()} ${aw.red_card.pts < 0 ? "−" + -aw.red_card.pts : aw.red_card.pts}`, wu.red_card, aw.red_card.id));
  if (aw.gloves) cards.push(card("gloves", "", "Gloves of the week", `${P(aw.gloves.pid).n.toUpperCase()} ${aw.gloves.pts}`, wu.gloves, aw.gloves.id));

  const xi = d.xi.players;
  const top = Math.max(...xi.map((x) => x.pts));
  const rows = [1, 2, 3, 4].map((pos) => xi.filter((x) => P(x.pid).p === pos));
  const pitch = `<div class="pitch">${rows.map((r) => `<div class="prow">${r.map((x) => `
      <div class="pcard" style="--oc:${M(x.owner).col}">
        <span class="pp ${x.pts === top ? "top" : ""}">${x.pts}</span>
        <div class="pn">${esc(P(x.pid).n)}</div><div class="po">${esc(M(x.owner).name)}</div>
      </div>`).join("")}</div>`).join("")}</div>`;
  const writeup = xi.map((x) => {
    const p = P(x.pid);
    return `<div class="wh">${esc(p.n)}<small>${POS[p.p]} · ${T(p.t)} · ${esc(M(x.owner).name)} · ${x.pts} pts</small></div>
      <p>${esc((wu.xi || {})[x.pid] || "")}</p>`;
  }).join("");

  const sa = D.season_awards;
  const saRows = D.managers.slice().sort((a, b) => (sa[b.id].motw - sa[a.id].motw) || (sa[a.id].stinker - sa[b.id].stinker))
    .map((m) => { const s = sa[m.id]; return `<tr${meAttr(m.id)}><td>${who(m.id)}</td>
      <td class="r">${s.motw ? `<span class="chip y">${s.motw}</span>` : '<span class="num">0</span>'}</td>
      <td class="r">${s.stinker ? `<span class="chip bad">${s.stinker}</span>` : '<span class="num">0</span>'}</td>
      <td class="r num">${s.bench}</td></tr>`; }).join("");

  return `
  <div class="select-row"><span class="label">Showing</span>
    <select class="sel" id="totw-gw">${gws.map((x) => `<option value="${x}" ${x === g ? "selected" : ""}>Gameweek ${x}${x === gws[0] ? " · latest" : ""}</option>`).join("")}</select></div>
  <h2 class="title">Team of the week · GW${g}</h2>
  ${wu.intro ? `<p class="lede" style="color:var(--ink-2)">${esc(wu.intro)}</p>` : '<p class="lede">The write-up lands once bonus points are confirmed.</p>'}
  <div class="stack">${cards.join("")}</div>
  <h3 class="section">The XI <span class="mono" style="font-size:14px;color:var(--muted)">${d.xi.formation} · ${d.xi.total} pts</span></h3>
  <p class="note">The best valid XI from players owned in the league that week. The bar on each card is the owner.</p>
  ${pitch}
  <h3 class="section">The write-up</h3>
  <div class="writeup">${writeup}</div>
  <h3 class="section">Season awards</h3>
  <p class="note">Manager of the Week is the top score each gameweek, Stinker the lowest, Bench of the Week the most points left on the bench. Ties count for everyone.</p>
  <div class="card"><table class="t"><thead><tr><th>Manager</th><th class="r">MOTW</th><th class="r">Stinker</th><th class="r">Bench</th></tr></thead><tbody>${saRows}</tbody></table></div>
  ${wu.source === "template" ? '<p class="foot">Template write-up. Claude takes over once the API key is added.</p>' : ""}`;
};

V.midweek = () => {
  const L = D.live;
  if (!L) return empty("Nothing to show yet.");
  const state = D.meta.live ? '<span class="live-badge">LIVE</span>' : L.final ? (L.checked ? '<span class="chip n">FINAL</span>' : '<span class="chip y">PROVISIONAL</span>') : '<span class="chip n">NOT STARTED</span>';
  const fx = L.fixtures.map((f) => {
    const live = f.started && !f.done;
    const sc = f.started ? `${f.hs ?? 0}–${f.as ?? 0}` : when(f.ko, false);
    return `<div class="fxc ${live ? "live" : ""}">${T(f.h)} ${sc} ${T(f.a)}<div class="st">${live ? (f.min ? f.min + "'" : "LIVE") : f.done ? "FT" : new Date(f.ko).toLocaleDateString("en-GB", { weekday: "short", timeZone: "Europe/London" })}</div></div>`;
  }).join("");
  const rows = L.managers.map((r, i) => {
    const pl = r.players.map((x) => {
      const p = P(x.pid);
      const ev = [x.g ? "⚽".repeat(x.g) : "", x.a ? "🅰️".repeat(x.a) : "", x.yc ? "🟨" : "", x.rc ? "🟥" : ""].join("");
      const tag = x.role === "in" ? '<span class="tag in">AUTO-SUB IN</span>' : x.role === "out" ? '<span class="tag out">SUBBED OFF</span>' : "";
      const bonus = x.bp ? `<span class="tag prov">+${x.bp} BONUS</span>` : x.b ? `<span class="tag">+${x.b} BONUS</span>` : "";
      const st = x.state === "pre" ? "yet to play" : x.state === "live" ? `${x.min}' · live` : x.state === "none" ? "no game" : `${x.min}'`;
      return `<div class="lp ${x.role === "bench" || x.role === "out" ? "bench" : ""}"><span>${pTag(x.pid, { pos: false })} ${tag}${bonus}<br><span class="ev">${st} ${ev}</span></span><span></span><span class="p">${x.pts}</span></div>`;
    }).join("");
    return `<details class="mgr ${isMe(r.id) && S.me ? "me" : ""}"><summary><span class="mono" style="color:var(--muted)">${i + 1}</span>${who(r.id, { team: true })}<span class="gwp">${cu(r.pts)}</span><span class="tot">${fmt(r.total)}</span></summary>${pl}</details>`;
  }).join("");
  return `
  <div class="select-row" style="justify-content:space-between"><h2 class="title" style="margin:10px 0">Gameweek ${L.gw}</h2>${state}</div>
  <p class="lede">${D.meta.live ? "Live scores, including auto-subs and provisional bonus as they happen. Everything here is provisional until the gameweek is final." : L.final ? (L.checked ? "Final scores for the gameweek. Tap a manager to see their team." : "All games are done, but bonus points aren't confirmed yet, so treat these as provisional.") : "Scores appear here once the first game kicks off."}</p>
  <div class="fixtures-strip hscroll">${fx}</div>
  <div class="card">${rows}</div>`;
};

V.preview = () => {
  const pv = D.preview;
  if (!pv) return empty("No upcoming gameweek.");
  const rows = pv.managers.map((r, i) => {
    const chips = r.xi.map((pid) => { const p = P(pid); const f = (D.fx[p.t] || []).find((x) => x.gw === pv.gw);
      return `<span class="f${f ? f.d : 3}">${esc(p.n)}<b>${f ? (f.h ? T(f.o) : T(f.o).toLowerCase()) : "—"}</b></span>`; }).join("");
    const doubts = r.doubts.length ? "Doubts: " + r.doubts.map((d) => `<b>${esc(P(d.pid).n)}</b> ${d.cop != null ? d.cop + "%" : ""}${d.news ? " – " + esc(d.news) : ""}`).join("; ") : "No injury or suspension doubts.";
    return `<div ${isMe(r.id) && S.me ? 'style="background:var(--y-tint)"' : ""}>
      <div class="prow2" style="grid-template-columns:26px 1fr auto;border:0"><span class="mono" style="color:var(--muted)">${i + 1}</span>${who(r.id, { team: true })}<span style="text-align:right"><span class="big" style="font:400 30px/1 var(--display)">${cu(r.proj, 1)}</span><br><span class="pos">${r.formation}</span></span></div>
      <div class="xi-chips">${chips}</div><div class="doubts">${doubts}</div></div>`;
  }).join('<div style="border-top:1px solid var(--line)"></div>');
  return `<h2 class="title">GW${pv.gw} preview</h2>
  <p class="lede">Deadline ${when(pv.deadline)}. Each manager's likely XI is the best projected line-up from their current squad. Chips show the opponent (home in capitals), green for easy and red for hard.</p>
  <div class="card">${rows}</div>
  <p class="note">Projections use FPL's expected points, adjusted for fixture difficulty, recent minutes and fitness flags.</p>`;
};

V.waivers = () => {
  const w = D.waivers;
  const order = D.waiver_order.map((id, i) => `<tr${meAttr(id)}><td class="rank">${i + 1}</td><td>${who(id, { team: true })}</td></tr>`).join("");
  let round = empty("No waiver claims yet.");
  if (w) {
    const RES = { a: ["good", "WON"], di: ["bad", "DENIED"], do: ["bad", "DENIED"], r: ["bad", "DENIED"] };
    const byMgr = {};
    w.claims.forEach((c) => (byMgr[c.id] = byMgr[c.id] || []).push(c));
    round = `<div class="card">${Object.keys(byMgr).sort((a, b) => D.waiver_order.indexOf(+a) - D.waiver_order.indexOf(+b)).map((id) => `
      <div class="pad" style="border-bottom:1px solid var(--line)">${who(id)}
        ${byMgr[id].sort((a, b) => (a.pri || 0) - (b.pri || 0)).map((c) => { const [k, l] = RES[c.res] || ["n", c.res.toUpperCase()];
          return `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-top:8px;font-size:14px"><span>+ ${pTag(c.in)}<br><span class="club">drop ${esc(P(c.out).n)}</span></span><span class="chip ${k}">${l}</span></div>`; }).join("")}
      </div>`).join("")}</div>
      ${w.fa.length ? `<h3 class="section">Free agents since</h3><div class="card">${w.fa.map((f) => `<div class="pad" style="border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:10px">${who(f.id)}<span style="text-align:right;font-size:14px">+ ${esc(P(f.in).n)}<br><span class="club">drop ${esc(P(f.out).n)}</span></span></div>`).join("")}</div>` : ""}`;
  }
  return `<h2 class="title">Waivers${w ? " · GW" + w.gw : ""}</h2>
  <p class="lede">The latest waiver round: who claimed whom, which claims failed, and who was dropped. Next round: ${when(D.meta.next && D.meta.next.waivers)}.</p>
  ${round}
  <h3 class="section">Waiver order</h3><p class="note">First pick at the top.</p>
  <div class="card"><table class="t"><tbody>${order}</tbody></table></div>`;
};

V.standings = () => {
  if (!D.standings.length) return empty("No standings yet.");
  const rows = D.standings.map((s) => `<tr${meAttr(s.id)}>
    <td class="rank">${s.rank}</td>
    <td>${who(s.id, { team: true, arrow: arrow(s.move) })}</td>
    <td class="r num">${s.gw}</td>
    <td class="big">${cu(s.total)}</td>
    <td class="r num" style="color:var(--muted)">${s.gap ? s.gap : "–"}</td></tr>`).join("");
  return `<h2 class="title">League table</h2>
  <p class="lede">After gameweek ${lastGw()}. Arrows show movement since last week.</p>
  <div class="card"><table class="t compact"><thead><tr><th>#</th><th>Manager</th><th class="r">GW${lastGw()}</th><th class="r">Total</th><th class="r">Gap</th></tr></thead><tbody>${rows}</tbody></table></div>
  ${D.managers.some((m) => m.champ) ? '<p class="note">🏆 (c) marks last season\'s champion.</p>' : ""}`;
};

V.power = () => {
  const up = D.meta.upcoming;
  const avg = D.league_avg3;
  const rows = D.power.map((p) => {
    const vs = p.vs_table;
    const vsTxt = vs > 0 ? `<span class="good-t" style="font-size:13px;font-weight:600"> ${vs} above table</span>` : vs < 0 ? `<span class="bad-t" style="font-size:13px;font-weight:600"> ${-vs} below table</span>` : '<span style="font-size:13px;color:var(--muted)"> level with table</span>';
    const top = p.top.map((x) => P(x).n);
    const miss = p.missing.map((x) => P(x).n);
    const diff = p.last3 - avg;
    let blurb = `${top.join(" and ")} lead the way.`;
    if (miss.length) blurb += ` Missing ${miss.join(", ")}.`;
    blurb += ` ${fmt(p.last3, 1)} a week over the last 3, ${Math.abs(diff) < 1.5 ? "around" : diff > 0 ? (diff > 6 ? "well above" : "above") : (diff < -6 ? "well below" : "below")} the league average of ${fmt(avg, 1)}.`;
    return `<tr${meAttr(p.id)}><td class="rank">${p.rank}</td><td><span class="who">${av(p.id)}<span><span class="nm">${esc(M(p.id).name)}</span>${vsTxt}<br><span class="tm">${esc(blurb)}</span></span></span></td><td class="big">${cu(p.proj, 1)}</td></tr>`;
  }).join("");
  return `<h2 class="title">Power rankings</h2>
  <p class="lede">Ranked on what each squad's best XI is projected to score a week over gameweeks ${up.join("–")}, not on points already banked.</p>
  <div class="card"><table class="t"><thead><tr><th>#</th><th>Manager</th><th class="r">Proj / wk</th></tr></thead><tbody>${rows}</tbody></table></div>`;
};

V.race = () => {
  const n = lastGw();
  if (!n) return empty("No gameweeks yet.");
  const sc = D.scores;
  const hi = [], lo = [];
  for (let g = 0; g < n; g++) {
    const vals = D.managers.map((m) => sc[m.id][g]);
    hi.push(Math.max(...vals)); lo.push(Math.min(...vals));
  }
  const grid = D.managers.slice().sort((a, b) => D.cum[b.id][n - 1] - D.cum[a.id][n - 1]).map((m) => `<tr${meAttr(m.id)}><td style="position:sticky;left:0;background:var(--card);z-index:2">${who(m.id)}</td>${sc[m.id].map((v, g) =>
    `<td class="r">${v === hi[g] ? `<span class="chip good">${v}</span>` : v === lo[g] ? `<span class="chip bad">${v}</span>` : `<span class="num">${v}</span>`}</td>`).join("")}<td class="r num"><b>${D.cum[m.id][n - 1]}</b></td></tr>`).join("");
  return `<h2 class="title">The race</h2>
  <p class="lede">Total points after each gameweek. Tap a name to follow one line; tap the chart for the numbers.</p>
  <div class="card pad chart" id="race"></div>
  <div class="legend" id="race-legend">${D.managers.map((m) => `<button data-hl="${m.id}" aria-pressed="${S.raceHl === m.id}"><i style="background:${S.raceHl === m.id ? "#0A0A0A" : m.col}"></i>${esc(m.name)}</button>`).join("")}</div>
  <h3 class="section">Gameweek scores</h3>
  <p class="note">Green is the week's top score, red the lowest.</p>
  <div class="card hscroll"><table class="t"><thead><tr><th style="position:sticky;left:0;z-index:3">Manager</th>${Array.from({ length: n }, (_, g) => `<th class="r">GW${g + 1}</th>`).join("")}<th class="r">Total</th></tr></thead><tbody>${grid}</tbody></table></div>`;
};

function drawRace() {
  const el = $("#race");
  if (!el) return;
  const n = lastGw();
  const W = Math.max(300, Math.round(el.clientWidth - 36)), H = Math.round(Math.max(300, Math.min(440, W * 0.78))), L = 34, R = 96, Tp = 12, B = 24;
  const max = Math.ceil(Math.max(...D.managers.map((m) => D.cum[m.id][n - 1])) / 50) * 50 || 50;
  const x = (g) => L + (n === 1 ? 0 : (g / (n - 1)) * (W - L - R));
  const y = (v) => Tp + (1 - v / max) * (H - Tp - B);
  const step = max > 1200 ? 200 : max > 500 ? 100 : 50;
  let grid = "", axis = "";
  for (let v = 0; v <= max; v += step) { grid += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`; axis += `<text x="${L - 6}" y="${y(v) + 3.5}" text-anchor="end">${v}</text>`; }
  const every = n > 20 ? 5 : n > 10 ? 2 : 1;
  for (let g = 0; g < n; g++) if ((g + 1) % every === 0 || g === 0) axis += `<text x="${x(g)}" y="${H - 8}" text-anchor="middle">${g + 1}</text>`;
  const order = D.managers.slice().sort((a, b) => D.cum[b.id][n - 1] - D.cum[a.id][n - 1]);
  const hl = S.raceHl;
  const lines = order.slice().reverse().map((m) => {
    const pts = D.cum[m.id].map((v, g) => `${x(g).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    const c = m.col === "#0A0A0A" ? "var(--ink)" : m.col;
    return `<polyline class="ln-under ${hl === m.id ? "hl" : ""}" points="${pts}"/><polyline class="ln ${hl === m.id ? "hl" : ""}" points="${pts}" stroke="${c}"/>`;
  }).join("");
  // end labels, nudged apart
  const labs = order.map((m) => ({ m, y: y(D.cum[m.id][n - 1]) }));
  for (let i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 13) labs[i].y = labs[i - 1].y + 13;
  const ends = labs.map(({ m, y: ly }) => {
    const c = m.col === "#0A0A0A" ? "var(--ink)" : m.col;
    return `<g class="${hl === m.id ? "hl" : ""}"><circle cx="${x(n - 1)}" cy="${y(D.cum[m.id][n - 1])}" r="3.5" fill="${hl === m.id ? "var(--y)" : c}" stroke="var(--card)" stroke-width="1.5"/><text x="${x(n - 1) + 8}" y="${ly + 4}" fill="${c}">${esc(m.name)} ${D.cum[m.id][n - 1]}</text></g>`;
  }).join("");
  el.classList.toggle("has-hl", hl != null);
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative points by gameweek"><g class="grid">${grid}</g><g class="axis">${axis}</g>${lines}<line id="race-cursor" x1="0" x2="0" y1="${Tp}" y2="${H - B}" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0"/><g class="end">${ends}</g></svg>`;
  const svg = $("svg", el);
  const onPoint = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
    const g = Math.max(0, Math.min(n - 1, Math.round(((px - L) / (W - L - R)) * (n - 1))));
    const cur = $("#race-cursor", svg);
    cur.setAttribute("x1", x(g)); cur.setAttribute("x2", x(g)); cur.setAttribute("opacity", ".6");
    const rows = D.managers.slice().sort((a, b) => D.cum[b.id][g] - D.cum[a.id][g])
      .map((m) => `${m.id === hl ? "<b>" : ""}${esc(m.name)} ${D.cum[m.id][g]} <span style="opacity:.6">(+${D.scores[m.id][g]})</span>${m.id === hl ? "</b>" : ""}`).join("<br>");
    showTip(`<b>After GW${g + 1}</b><br>${rows}`, ev);
  };
  svg.addEventListener("click", onPoint);
  svg.addEventListener("mousemove", onPoint);
  svg.addEventListener("mouseleave", hideTip);
}

V.squads = () => {
  const id = S.squad || D.meta.me || D.managers[0].id;
  const sq = D.squads[id];
  const m = M(id);
  const picker = D.standings.map((s) => `<button data-squad="${s.id}" aria-pressed="${s.id === id}">${av(s.id)}<span>${esc(M(s.id).name)}</span></button>`).join("");
  const row = (pid, dash) => {
    const p = P(pid);
    return `<div class="prow2 ${dash ? "dash" : ""} ${p.dead ? "isdead" : ""}"><span class="pos">${POS[p.p]}</span>
      <span style="min-width:0"><span class="nm">${esc(p.n)}<span class="club">${T(p.t)}</span></span>${flagFor(p)}<br>${fxChips(p.t)}</span>
      ${spark(p.gw.slice(0, lastGw()))}<span class="pts">${p.pts}</span></div>`;
  };
  return `<h2 class="title">Squads</h2>
  <p class="lede">Pick a manager. The top eleven is the best-fit XI by season points, with the bench below the dashed line. Bars show points each gameweek (orange for 10+); the chips are the next three fixtures, green easy, red hard.</p>
  <div class="picker" id="picker">${picker}</div>
  <div class="card">
    <div class="pad sq-head">${who(id, { team: true })}<span class="dead-badge ${sq.dead ? "" : "ok"}">${sq.dead ? plural(sq.dead, "DEAD SLOT") : "NO DEAD SLOTS"}</span></div>
    <div class="statgrid">
      <div><div class="v">${cu(sq.xi_pts)}</div><div class="label">Best XI pts</div></div>
      <div><div class="v">${cu(sq.squad_pts)}</div><div class="label">Squad pts</div></div>
      <div><div class="v">${cu(sq.unavailable)}</div><div class="label">Unavailable</div></div>
      <div><div class="v">${cu(sq.bench_pts)}</div><div class="label">Bench pts</div></div>
    </div>
    ${sq.xi.map((p) => row(p)).join("")}${sq.bench.map((p, i) => row(p, i === 0)).join("")}
  </div>
  <p class="note">A dead slot is a player who is injured, suspended, gone from the league, or has played under 180 minutes all season. ${esc(m.name)}'s best XI is a ${sq.formation}.</p>`;
};

V.needs = () => {
  const cols = { 1: "var(--pos-gk)", 2: "var(--pos-def)", 3: "var(--pos-mid)", 4: "var(--pos-fwd)" };
  const share = {};
  D.managers.forEach((m) => {
    const pp = D.pos_points[m.id]; const tot = Object.values(pp).reduce((a, b) => a + b, 0) || 1;
    share[m.id] = { 1: pp[1] / tot, 2: pp[2] / tot, 3: pp[3] / tot, 4: pp[4] / tot, tot };
  });
  const sorted = D.managers.slice().sort((a, b) => share[b.id][2] - share[a.id][2]);
  const pct = (v) => Math.round(v * 100);
  const maxBy = (pos) => D.managers.reduce((a, b) => (share[b.id][pos] > share[a.id][pos] ? b : a));
  const minBy = (pos) => D.managers.reduce((a, b) => (share[b.id][pos] < share[a.id][pos] ? b : a));
  const d = maxBy(2), f = maxBy(4), fl = minBy(4), mi = maxBy(3);
  const summary = `${esc(d.name)} gets the biggest share from defence (${pct(share[d.id][2])}%). ${esc(f.name)} leans hardest on forwards (${pct(share[f.id][4])}%), ${esc(mi.name)} on midfield (${pct(share[mi.id][3])}%), and ${esc(fl.name)}'s forwards have provided just ${pct(share[fl.id][4])}%.`;
  const bars = sorted.map((m) => `<div class="nrow ${isMe(m.id) && S.me ? "me" : ""}">${who(m.id, { size: "sm" })}<div class="bar">${[1, 2, 3, 4].map((p) =>
    `<span class="${POS[p].toLowerCase()}" style="flex-basis:${(share[m.id][p] * 100).toFixed(1)}%;background:${cols[p]}" title="${POS[p]} ${pct(share[m.id][p])}%">${share[m.id][p] > 0.14 ? POS[p] + " " + pct(share[m.id][p]) + "%" : ""}</span>`).join("")}</div><span class="num r" style="text-align:right">${share[m.id].tot}</span></div>`).join("");
  const sh = { g: "good", a: "amber", r: "bad" };
  const needRows = D.managers.map((m) => `<tr${meAttr(m.id)}><td>${who(m.id)}</td>${[1, 2, 3, 4].map((p) => { const c = D.needs[m.id][p];
    return `<td class="r"><span class="chip ${sh[c.shade]}">${c.fit}/${c.held}</span></td>`; }).join("")}</tr>`).join("");
  return `<h3 class="section" style="margin-top:14px">Where the points come from</h3>
  <p class="note">Points scored by each manager's starting XI this season, split by position. ${summary}</p>
  <div class="legend-pos">${[1, 2, 3, 4].map((p) => `<span><span class="pos-dot" style="background:${cols[p]}"></span>${POS[p]}</span>`).join("")}</div>
  <div>${bars}</div>
  <h3 class="section">Who needs what</h3>
  <p class="note">Fit, regularly playing players out of the total held at each position. Green means enough to field a side (1 GK, 4 DEF, 4 MID, 2 FWD), amber one short, red two or more short. That's where trades are most likely to land. "Regularly playing" means appearing in at least 2 of the last 3 gameweeks.</p>
  <div class="card"><table class="t"><thead><tr><th>Manager</th><th class="r">GK</th><th class="r">DEF</th><th class="r">MID</th><th class="r">FWD</th></tr></thead><tbody>${needRows}</tbody></table></div>`;
};

V.wire = () => {
  const list = D.wire.filter((pid) => { const p = P(pid); return (S.wirePos === "all" || p.p === +S.wirePos) && p.min >= S.wireMin; }).slice(0, 80);
  const rows = list.map((pid) => { const p = P(pid); const nf = (D.fx[p.t] || [])[0];
    return `<tr><td><span class="nm" style="font-weight:600">${esc(p.n)}</span>${flagFor(p)}<br><span class="pos">${POS[p.p]}</span> <span class="club">${T(p.t)}</span></td>
      <td class="r num"><b>${fmt(p.pw, 1)}</b></td><td class="r num">${p.pts}</td>
      <td class="r">${p.p === 1 ? '<span class="num" style="color:var(--muted)">–</span>' : p.dch ? `<span class="chip good">${fmt(p.dc90, 1)}</span>` : `<span class="num">${fmt(p.dc90, 1)}</span>`}</td>
      <td class="r">${nf ? `<span class="fx"><span class="f${nf.d}">${nf.h ? T(nf.o) : T(nf.o).toLowerCase()}</span></span>` : "—"}</td></tr>`; }).join("");
  const mins = [0, 90, 180, 270, 450, 630, 900];
  return `<h2 class="title">Waiver wire</h2>
  <p class="lede">Everyone nobody owns, ranked by projected points a week over the next three gameweeks. A green DEFCON figure means he hits the defensive bonus in most games (10 actions for defenders, 12 for midfielders and forwards).</p>
  <div class="filters"><div class="seg" id="wire-pos">${[["all", "All"], ["1", "GK"], ["2", "DEF"], ["3", "MID"], ["4", "FWD"]].map(([v, l]) => `<button data-pos="${v}" aria-pressed="${String(S.wirePos) === v}">${l}</button>`).join("")}</div>
  <label>Min. minutes <select id="wire-min">${mins.map((v) => `<option ${v === S.wireMin ? "selected" : ""}>${v}</option>`).join("")}</select></label></div>
  <div class="card"><table class="t compact"><thead><tr><th>Player</th><th class="r">Proj<br>/wk ▾</th><th class="r">Pts</th><th class="r">DC<br>/90</th><th class="r">Next</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="empty">Nobody matches those filters.</td></tr>'}</tbody></table></div>`;
};

V.trades = () => {
  const table = D.trade_table.map((r) => `<tr${meAttr(r.id)}><td>${who(r.id)}</td><td class="r num">${r.won}</td><td class="r num">${r.lost}</td><td class="r num ${r.net > 0 ? "good-t" : r.net < 0 ? "bad-t" : ""}">${signed(r.net)}</td></tr>`).join("");
  const side = (id, gets, val, win) => `<div class="side ${win ? "win" : ""}"><div class="label">${esc(M(id).name)} gets</div>
    <div class="gets">${gets.map((g) => `<div>${g.chain.map((pid, i) => (i ? '<span class="chain"> → </span>' : "") + `<b>${esc(P(pid).n)}</b>`).join("")} <span class="club">${g.pts} pts${g.proj ? ` + ${fmt(g.proj, 1)} proj` : ""}</span></div>`).join("")}</div>
    <div class="val">${fmt(val, 1)}</div></div>`;
  const list = D.trades.map((t) => `<div class="card trade"><div class="top"><span class="label">GW${t.gw} · ${t.time ? new Date(t.time).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : ""}</span><span class="label">${t.winner ? esc(M(t.winner).name) + " wins" : "Too close to call"}</span></div>
    <div class="sides">${side(t.a, t.a_gets, t.va, t.winner === t.a)}${side(t.b, t.b_gets, t.vb, t.winner === t.b)}</div></div>`).join("");
  return `<h2 class="title">Trades</h2>
  <p class="lede">Every completed trade, newest first. Each player's squad spot is followed after the trade: if he's later swapped on waivers, his replacement's points count too (shown with an arrow).</p>
  <h3 class="section">Trade winners</h3>
  <p class="note">Each trade is judged on what the squad spots have scored since it went through, including any waiver replacements, plus projected points for the next three gameweeks. A trade counts as a win at 3 points or more. Net is the total margin across a manager's trades.</p>
  ${table ? `<div class="card"><table class="t"><thead><tr><th>Manager</th><th class="r">Won</th><th class="r">Lost</th><th class="r">Net pts</th></tr></thead><tbody>${table}</tbody></table></div>` : empty("No trades yet.")}
  <h3 class="section">All trades</h3><div class="stack">${list || empty("No trades yet.")}</div>`;
};

V.swaps = () => {
  const cards = D.swaps.map((s) => `<div class="card trade">
    <div class="sides">
      <div class="side"><div class="label">${esc(M(s.a).name)} gives</div><div class="gets">${s.a_gives.map((p) => `<div>${pTag(p)}</div>`).join("")}</div><div class="note" style="margin:8px 0 0">Best XI <b class="good-t">${signed(s.a_gain)}</b> a week</div></div>
      <div class="side"><div class="label">${esc(M(s.b).name)} gives</div><div class="gets">${s.b_gives.map((p) => `<div>${pTag(p)}</div>`).join("")}</div><div class="note" style="margin:8px 0 0">Best XI <b class="good-t">${signed(s.b_gain)}</b> a week</div></div>
    </div></div>`).join("");
  return `<h2 class="title">Swap Shop</h2>
  <p class="lede">Suggested trades where both sides' best projected XI improves over the next three gameweeks. They're like-for-like by position so both squads stay legal, and usually work by filling one side's dead slot or weak spot from the other's depth.</p>
  <div class="stack">${cards || empty("No trades improve both sides right now. Everyone's squad is either balanced or equally broken.")}</div>`;
};

V.records = () => {
  const r = D.records, at = D.alltime;
  const rc = (label, v, w, s) => `<div class="card pad rec"><div class="label">${label}</div><div class="v">${v}</div><div class="w">${esc(w)}</div><div class="s">${esc(s)}</div></div>`;
  const season = r.high ? [
    rc("Highest gameweek score", cu(r.high.v), M(r.high.id).name, `GW${r.high.gw}`),
    rc("Lowest gameweek score", cu(r.low.v), M(r.low.id).name, `GW${r.low.gw}`),
    rc("Biggest winning margin", cu(r.margin.v), M(r.margin.id).name, `clear of second in GW${r.margin.gw}`),
    rc("Most points on the bench", cu(r.bench.v), M(r.bench.id).name, `GW${r.bench.gw}`),
    r.trades ? rc("Most trades", cu(r.trades.v), names(r.trades.ids), "trades completed") : "",
    r.transfers ? rc("Most transfers", cu(r.transfers.v), names(r.transfers.ids), "waivers and free agents") : "",
  ].join("") : "";
  const ptable = (rows, col) => `<div class="card"><table class="t"><thead><tr><th>Pts</th><th>Player</th><th>${col}</th><th class="r">When</th></tr></thead><tbody>${rows.map((h) =>
    `<tr${meAttr(h.id)}><td class="num"><b>${h.pts}</b></td><td>${pTag(h.pid)}</td><td><b>${esc(M(h.id).name)}</b></td><td class="r num">GW${h.gw}</td></tr>`).join("")}</tbody></table></div>`;
  const all = [
    at.high ? rc("Highest season total", cu(at.high.v), at.high.name, at.high.season + (at.high.champ ? ", finished champion" : "")) : "",
    at.low ? rc("Lowest season total", cu(at.low.v), at.low.name, at.low.season) : "",
    at.margin ? rc("Biggest title margin", cu(at.margin.v), at.margin.name, `${at.margin.season}, ahead of ${at.margin.over}`) : "",
    at.closest ? rc("Closest title race", cu(at.closest.v), at.closest.name, `${at.closest.season}, over ${at.closest.over}`) : "",
    at.climb ? rc("Biggest climb", "+" + at.climb.v, at.climb.name, `${ordinal(at.climb.from)} to ${ordinal(at.climb.to)} in ${at.climb.season}`) : "",
  ].join("");
  const nearFinal = D.seasons.filter((s) => s.near_final).map((s) => s.season);
  const full = D.seasons.filter((s) => s.table && !s.near_final).length;
  return `<h2 class="title">Records</h2>
  <p class="lede">The best and worst of the season so far, and of the league's history on record. Season records update every week.</p>
  <h3 class="section">This season</h3><div class="recs">${season || empty("No gameweeks yet.")}</div>
  <h3 class="section">Biggest hauls</h3><p class="note">Highest single-week scores by a player in someone's starting XI.</p>${r.hauls ? ptable(r.hauls, "For") : ""}
  <h3 class="section">Bench disasters</h3><p class="note">Highest scores left on the bench.</p>${r.bench_disasters ? ptable(r.bench_disasters, "Benched by") : ""}
  <h3 class="section">All time</h3>
  ${all ? `<div class="recs">${all}</div>` : empty("Add past final tables to history.json to unlock these.")}
  ${full === 1 ? '<p class="note">Only one past season is on record so far, so the biggest and closest title margins are the same race. Send more tables and these get interesting.</p>' : ""}
  ${nearFinal.length ? `<p class="note">${nearFinal.join(", ")} ${nearFinal.length > 1 ? "are near-final snapshots" : "is a near-final snapshot"}, so ${nearFinal.length > 1 ? "they don't" : "it doesn't"} count for all-time records.</p>` : ""}`;
};

V.past = () => {
  const ss = D.seasons;
  const titles = D.alltime.titles || {};
  const multi = Object.entries(titles).filter(([, n]) => n > 1).sort((a, b) => b[1] - a[1]);
  const intro = multi.length === 1 ? `${multi[0][0]} is the only manager with more than one title, with ${multi[0][1]}.`
    : multi.length ? multi.map(([n, c]) => `${n} has ${c}`).join(", ") + "."
    : ss.length ? "Nobody has won it more than once yet." : "";
  const cards = ss.map((s) => {
    const t = s.table ? s.table.slice().sort((a, b) => b.total - a.total) : null;
    const meta = t && t.length > 1 ? `${t[0].total} pts · ${t[0].total - t[1].total} clear of ${esc(t[1].name)}` : "Final table not on record";
    return `<div class="card season champ-card"><details><summary>
      <div class="yr">${esc(s.season)}${s.near_final ? " · near-final" : ""}</div>
      <h4>${esc((s.champion || "?").toUpperCase())}</h4><div class="note" style="margin:0">${meta}${t ? " · tap for the table" : ""}</div></summary>
      ${t ? `<table class="t"><tbody>${t.map((r, i) => `<tr><td class="rank">${i + 1}</td><td><span class="nm" style="font-weight:600">${esc(r.name)}</span><br><span class="tm" style="color:var(--muted);font-size:13px">${esc(r.team || "")}</span></td><td class="big">${r.total}</td></tr>`).join("")}</tbody></table>` : ""}
    </details></div>`;
  }).join("");
  return `<h2 class="title">History</h2>
  <p class="lede">Final tables from past seasons. ${esc(intro)}</p>
  <div class="stack">${cards || empty("No past seasons on record yet. Send over the old tables and they'll appear here.")}</div>`;
};

V.draft = () => {
  const dr = D.draft;
  if (!dr.picks.length) return empty("The draft hasn't happened yet.");
  const order = dr.order;
  const byRound = {};
  dr.picks.forEach((p) => ((byRound[p.round] = byRound[p.round] || {})[p.id] = p));
  const head = `<div></div>${order.map((id) => `<div class="h ${isMe(id) && S.me ? "me" : ""}">${esc(M(id).name)}</div>`).join("")}`;
  const body = Object.keys(byRound).map(Number).sort((a, b) => a - b).map((r) => `<div class="rd">${r}</div>${order.map((id) => {
    const p = byRound[r][id]; if (!p) return "<div></div>";
    const pl = P(p.pid);
    const cls = [p.value >= 40 ? "good" : p.value <= -40 ? "bad" : "", p.kept ? "" : "gone"].join(" ");
    return `<div class="cell ${cls}" title="Pick ${p.pick} · ranks ${ordinal(p.rank)} by points"><div class="pn">${esc(pl.n)}</div><div class="pm">${POS[pl.p]} ${T(pl.t)} · ${pl.pts}</div></div>`;
  }).join("")}`).join("");
  const tbl = (rows) => `<div class="card"><table class="t"><thead><tr><th>Pick</th><th>Player</th><th>By</th><th class="r">Season</th><th class="r">For him</th></tr></thead><tbody>${rows.map((p) =>
    `<tr${meAttr(p.id)}><td class="num">${p.pick}</td><td>${pTag(p.pid)}</td><td><b>${esc(M(p.id).name)}</b></td><td class="r num">${P(p.pid).pts}</td><td class="r num">${p.for}</td></tr>`).join("")}</tbody></table></div>`;
  const date = dr.date ? new Date(dr.date).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/London" }) : "";
  return `<h2 class="title">The ${esc(D.meta.season)} draft</h2>
  <p class="lede">Drafted on ${date}, snake order, ${dr.rounds} rounds. Each pick shows the player's season points so far. Green picks rank at least 40 places better (by points) than where they were taken; red ones at least 40 places worse. Faded picks are no longer in that manager's squad.</p>
  <div class="card hscroll" style="padding:8px"><div class="board" style="grid-template-columns:30px repeat(${order.length}, 132px)">${head}${body}</div></div>
  <h3 class="section">Best value picks</h3><p class="note">"For him" is what the player scored while in that manager's squad.</p>${tbl(dr.best)}
  <h3 class="section">Early picks that missed</h3><p class="note">From the first ${Math.max(...dr.misses.map((m) => m.pick), 0) > 0 ? "six rounds" : "rounds"}, the picks furthest below where they were taken.</p>${tbl(dr.misses)}`;
};

function empty(msg) { return `<div class="card empty">${esc(msg)}</div>`; }

// ------------------------------------------------------------------ render
function render(animate = true) {
  const tb = tabs();
  const tab = tb.find((t) => t.id === S.tab) || tb[0];
  if (!tab.subs.some(([id]) => id === S.sub)) S.sub = tab.subs[0][0];
  $("#nav").innerHTML = tb.map((t) => `<button role="tab" data-tab="${t.id}" aria-selected="${t.id === tab.id}">${ICONS[t.id]}<span>${t.label}</span></button>`).join("");
  $("#pills").innerHTML = tab.subs.map(([id, l]) => `<button class="pill" role="tab" data-sub="${id}" aria-selected="${id === S.sub}">${l}</button>`).join("");
  const sel = $(`.pill[aria-selected="true"]`);
  if (sel) { const pills = $("#pills"); const l = sel.offsetLeft - 16, r = sel.offsetLeft + sel.offsetWidth - pills.clientWidth + 16;
    if (pills.scrollLeft > l) pills.scrollLeft = l; else if (pills.scrollLeft < r) pills.scrollLeft = r; }
  if (!D) return;
  const view = $("#view");
  let html;
  try { html = V[S.sub](); } catch (e) { console.error(e); html = empty("Something went wrong drawing this page."); }
  view.innerHTML = `<div class="${animate ? "view-in " + S.dir : ""}">${html}<p class="foot">${esc(D.meta.app)} · data from the FPL Draft API · updated ${when(D.meta.updated)}</p></div>`;
  S.dir = "";
  if (S.sub === "race") drawRace();
  countUp(view);
  document.title = `${tab.subs.find(([id]) => id === S.sub)[1]} · ${D.meta.app}`;
}

function countUp(root) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  $$(".cu", root).forEach((el) => {
    const end = +el.dataset.v, d = +el.dataset.d || 0;
    if (!isFinite(end) || Math.abs(end) < 2) return;
    const t0 = performance.now(), dur = 650;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(end * e, d);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });
}

function header() {
  const m = D.meta;
  $("#app-title").textContent = m.app;
  $("#app-sub").textContent = m.sub || "";
  $("#kicker").textContent = `FPL Draft · ${m.season} · ${m.after ? "After GW" + m.after : "Pre-season"}`;
  $("#updated").textContent = "Updated " + when(m.updated, false);
  $("#live-slot").innerHTML = m.live ? '<span class="live-badge">LIVE</span>' : "";
  $("#me-toggle").setAttribute("aria-pressed", S.me);
}

// ------------------------------------------------------------------ routing
function fromHash() {
  const [, tab, sub] = (location.hash || "").split("/");
  if (tab) S.tab = tab;
  if (sub) S.sub = sub;
}
function go(tab, sub, dir = "") {
  S.tab = tab; S.sub = sub; S.dir = dir;
  history.replaceState(null, "", `#/${tab}/${sub}`);
  render();
  window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
}
window.addEventListener("hashchange", () => { fromHash(); render(); });

// ------------------------------------------------------------------ events
document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-tab],[data-sub],[data-squad],[data-hl],[data-pos],[data-share],#me-toggle");
  if (!t) return;
  if (t.dataset.tab) { const tb = tabs().find((x) => x.id === t.dataset.tab); go(tb.id, tb.subs[0][0]); haptic(); }
  else if (t.dataset.sub) {
    const subs = tabs().find((x) => x.id === S.tab).subs.map(([id]) => id);
    go(S.tab, t.dataset.sub, subs.indexOf(t.dataset.sub) > subs.indexOf(S.sub) ? "from-right" : "from-left"); haptic();
  }
  else if (t.dataset.squad) { S.squad = +t.dataset.squad; render(false); }
  else if (t.dataset.hl) { const id = +t.dataset.hl; S.raceHl = S.raceHl === id ? null : id; render(false); }
  else if (t.dataset.pos) { S.wirePos = t.dataset.pos; render(false); }
  else if (t.dataset.share) shareAward(t.closest("[data-award]"));
  else if (t.id === "me-toggle") {
    S.me = !S.me; lsSet("me", S.me ? "1" : "0");
    if (S.me && S.raceHl == null) S.raceHl = D.meta.me;
    if (!S.me && S.raceHl === D.meta.me) S.raceHl = null;
    header(); render(false); haptic();
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "totw-gw") { S.totw = e.target.value; render(); }
  if (e.target.id === "wire-min") { S.wireMin = +e.target.value; lsSet("wireMin", S.wireMin); render(false); }
});
document.addEventListener("click", (e) => {
  const sp = e.target.closest(".spark");
  if (!sp) { if (!e.target.closest("#race svg")) hideTip(); return; }
  const arr = JSON.parse(sp.dataset.spark);
  const r = sp.getBoundingClientRect();
  const i = Math.max(0, Math.min(arr.length - 1, Math.floor(((e.clientX - r.left) / r.width) * arr.length)));
  showTip(`<b>GW${i + 1}</b> ${arr[i]} pts`, e);
});
function haptic() { try { navigator.vibrate && navigator.vibrate(8); } catch { /* not supported */ } }

const tip = () => $("#tip");
let tipTimer;
function showTip(html, ev) {
  const el = tip(); el.innerHTML = html; el.classList.add("on");
  const x = ev.touches ? ev.touches[0].clientX : ev.clientX, y = ev.touches ? ev.touches[0].clientY : ev.clientY;
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.left = Math.max(8, Math.min(innerWidth - w - 8, x - w / 2)) + "px";
  el.style.top = Math.max(8, y - h - 14) + "px";
  clearTimeout(tipTimer); tipTimer = setTimeout(hideTip, 4000);
}
function hideTip() { tip().classList.remove("on"); const c = $("#race-cursor"); if (c) c.setAttribute("opacity", "0"); }

// swipe between sub-tabs + pull to refresh
let sx = 0, sy = 0, pulling = false, pullDy = 0, swipeOk = true;
document.addEventListener("touchstart", (e) => {
  const t = e.touches[0]; sx = t.clientX; sy = t.clientY;
  swipeOk = !e.target.closest(".hscroll,.picker,.pills,.fixtures-strip,svg,select,.seg");
  pulling = window.scrollY <= 0; pullDy = 0;
}, { passive: true });
document.addEventListener("touchmove", (e) => {
  if (!pulling) return;
  pullDy = e.touches[0].clientY - sy;
  $("#ptr").classList.toggle("show", pullDy > 70 && Math.abs(e.touches[0].clientX - sx) < 40);
}, { passive: true });
document.addEventListener("touchend", (e) => {
  const t = e.changedTouches[0], dx = t.clientX - sx, dy = t.clientY - sy;
  if (pulling && pullDy > 70 && Math.abs(dx) < 40) { load(true); }
  $("#ptr").classList.remove("show"); pulling = false;
  if (!swipeOk || Math.abs(dx) < 70 || Math.abs(dy) > 45) return;
  const subs = tabs().find((x) => x.id === S.tab).subs.map(([id]) => id);
  const i = subs.indexOf(S.sub) + (dx < 0 ? 1 : -1);
  if (i >= 0 && i < subs.length) { go(S.tab, subs[i], dx < 0 ? "from-right" : "from-left"); haptic(); }
}, { passive: true });

// ------------------------------------------------------------------ share images
async function shareAward(card) {
  if (!card) return;
  const g = +card.dataset.gw, key = card.dataset.award;
  const d = gwData(g), aw = d.awards, wu = d.writeup || {};
  const label = $(".label", card).textContent;
  const title = $("h4", card).textContent;
  const text = wu[key] || "";
  const idMap = { motw: aw.motw.ids[0], stinker: aw.stinker.ids[0], bench: aw.bench.ids[0], bench_jam: aw.bench_jam && aw.bench_jam.id, red_card: aw.red_card && aw.red_card.id, gloves: aw.gloves && aw.gloves.id };
  const mgr = M(idMap[key]);
  try { await document.fonts.ready; } catch { /* fine */ }
  const W = 1080, H = 1350, c = document.createElement("canvas");
  c.width = W; c.height = H;
  const x = c.getContext("2d");
  const gold = key === "motw";
  x.fillStyle = gold ? "#EC4C24" : "#FFFFFF"; x.fillRect(0, 0, W, H);
  x.fillStyle = "#0A0A0A"; x.fillRect(0, 0, W, 230);
  x.fillStyle = "#EC4C24"; x.fillRect(0, 230, W, 12);
  const crest = await new Promise((res) => { const im = new Image(); im.onload = () => res(im); im.onerror = () => res(null); im.src = "icons/crest.png"; });
  if (crest) x.drawImage(crest, 60, 35, 160, 160);
  x.fillStyle = "#EC4C24"; x.font = '600 30px "JetBrains Mono", monospace';
  x.fillText(`FPL DRAFT · ${D.meta.season} · GW${g}`, 250, 92);
  x.fillStyle = "#FFFFFF"; x.font = '96px "Bebas Neue", Impact, sans-serif';
  x.fillText(D.meta.app.toUpperCase(), 250, 182);
  if (key === "stinker") { x.strokeStyle = "#A83A3A"; x.lineWidth = 10; x.strokeRect(40, 290, W - 80, H - 380); }
  x.fillStyle = gold ? "rgba(0,0,0,.65)" : "#6E6E6E"; x.font = '600 34px "JetBrains Mono", monospace';
  x.fillText(label.toUpperCase(), 90, 380);
  // avatar
  x.fillStyle = "#0A0A0A"; x.beginPath(); x.arc(140, 480, 54, 0, Math.PI * 2); x.fill();
  x.fillStyle = "#FFF"; x.font = '600 40px Inter, sans-serif'; x.textAlign = "center"; x.fillText(mgr.ini, 140, 494); x.textAlign = "left";
  x.fillStyle = "#0A0A0A"; x.font = '120px "Bebas Neue", Impact, sans-serif';
  fitText(x, title, 220, 520, W - 310, 120);
  x.font = '400 40px Inter, sans-serif'; x.fillStyle = gold ? "#0A0A0A" : "#2A2A2A";
  wrap(x, text, 90, 640, W - 180, 58, 10);
  x.fillStyle = gold ? "rgba(0,0,0,.6)" : "#8A8A8A"; x.font = '600 28px "JetBrains Mono", monospace';
  x.fillText(`${mgr.team || ""}`.toUpperCase(), 90, H - 60);
  const blob = await new Promise((r) => c.toBlob(r, "image/png"));
  const file = new File([blob], `salmons-gw${g}-${key}.png`, { type: "image/png" });
  try {
    if (navigator.canShare && navigator.canShare({ files: [file] })) { await navigator.share({ files: [file], title: `${label} · GW${g}` }); return; }
  } catch (err) { if (err && err.name === "AbortError") return; }
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = file.name; a.click();
  toast("Image saved");
}
function fitText(x, s, px, py, maxW, size) {
  let f = size;
  while (f > 50) { x.font = `${f}px "Bebas Neue", Impact, sans-serif`; if (x.measureText(s).width <= maxW) break; f -= 6; }
  x.fillText(s, px, py);
}
function wrap(x, s, px, py, maxW, lh, maxLines) {
  const words = s.split(/\s+/); let line = "", n = 0;
  for (const w of words) {
    const test = line ? line + " " + w : w;
    if (x.measureText(test).width > maxW && line) {
      if (++n >= maxLines) { x.fillText(line + " …", px, py); return; }
      x.fillText(line, px, py); py += lh; line = w;
    } else line = test;
  }
  if (line) x.fillText(line, px, py);
}
function toast(msg) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 1800); }

// ------------------------------------------------------------------ load
let refreshTimer;
async function load(manual = false) {
  try {
    const r = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    D = await r.json();
    D.managers.forEach((m) => { if (!D.squads[m.id]) D.squads[m.id] = { xi: [], bench: [], dead: 0 }; });
    if (S.raceHl == null && S.me) S.raceHl = D.meta.me;
    header(); render(!manual);
    if (manual) toast("Up to date");
  } catch (e) {
    console.error(e);
    if (!D) $("#view").innerHTML = empty("Couldn't load the data. Pull down to try again.");
    else if (manual) toast("Couldn't refresh");
  }
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => { if (document.visibilityState === "visible") load(); else refreshTimer = null; }, D && D.meta.live ? 60000 : 300000);
}
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && !refreshTimer) load(); });

S.wireMin = +lsGet("wireMin", "270");
fromHash();
render();
load();
if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("sw.js").catch(() => {});
})();
