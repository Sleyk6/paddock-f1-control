"use strict";
/* PADDOCK F1 CONTROL front end. No external libraries; charts are plain SVG. */

const $ = (sel) => document.querySelector(sel);
const state = { season: 2024, round: 1, tab: "calendar", results: null, calendar: null };

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`/api/${path}${qs ? "?" + qs : ""}`);
  const body = await res.json().catch(() => ({ error: "bad response from server" }));
  if (!res.ok) throw new Error(body.source ? `${body.source}: ${body.error}` : body.error);
  return body;
}

function fmtTime(s) {
  if (s == null) return "–";
  const m = Math.floor(s / 60), r = (s - m * 60).toFixed(3).padStart(6, "0");
  return m ? `${m}:${r}` : (+s).toFixed(3);
}

function renderStatus(meta) {
  const el = $("#status");
  if (!meta) { el.innerHTML = ""; return; }
  const kindText = { historical: "HISTORICAL", recent: "RECENT · may change", fixture: "TEST FIXTURE · synthetic" }[meta.data_kind] || meta.data_kind;
  const chips = [`<span class="badge kind-${esc(meta.data_kind)}">${esc(kindText)}</span>`];
  const seen = new Set();
  for (const s of meta.sources || []) {
    const key = `${s.source}|${s.cache}|${s.fetched_at}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const cache = { hit: "cached", miss: "fresh", stale: "STALE cache", fixture: "fixture" }[s.cache] || s.cache;
    chips.push(`<span class="badge cache-${esc(s.cache)}">${esc(s.source)} · ${esc(cache)} · fetched ${esc(s.fetched_at)}</span>`);
    if (s.warning) chips.push(`<span class="badge cache-stale">${esc(s.warning)}</span>`);
  }
  if (meta.server_ms != null) chips.push(`<span class="badge">server ${esc(meta.server_ms)} ms</span>`);
  el.innerHTML = chips.join("");
}

function notes(meta) {
  return (meta?.notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join("");
}

/* ---------- SVG charts ---------- */
function lineChart(series, { height = 260, yLabel = "", zero = false, step = false, yMin, yMax } = {}) {
  const W = 800, H = height, L = 52, R = 12, T = 26, B = 28;
  const pts = series.flatMap((s) => s.points).filter((p) => p[1] != null);
  if (!pts.length) return `<p class="loading">No data to chart.</p>`;
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = yMin ?? Math.min(...ys), y1 = yMax ?? Math.max(...ys);
  if (zero) { y0 = Math.min(y0, 0); y1 = Math.max(y1, 0); }
  if (x1 === x0) x1 = x0 + 1;
  if (y1 === y0) { y1 += 1; y0 -= 1; }
  const pad = (y1 - y0) * 0.06; y0 -= yMin == null ? pad : 0; y1 += yMax == null ? pad : 0;
  const sx = (x) => L + ((x - x0) / (x1 - x0)) * (W - L - R);
  const sy = (y) => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
  let out = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yLabel)} chart">`;
  for (let i = 0; i <= 4; i++) {
    const v = y0 + ((y1 - y0) * i) / 4, y = sy(v);
    out += `<line class="axis" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/><text class="tick" x="${L - 6}" y="${y + 4}" text-anchor="end">${esc(+v.toFixed(Math.abs(y1 - y0) < 10 ? 1 : 0))}</text>`;
  }
  for (let i = 0; i <= 5; i++) {
    const v = x0 + ((x1 - x0) * i) / 5;
    out += `<text class="tick" x="${sx(v)}" y="${H - 8}" text-anchor="middle">${esc(+v.toFixed(0))}</text>`;
  }
  if (zero) out += `<line class="zero" x1="${L}" x2="${W - R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
  for (const s of series) {
    const p = s.points.filter((q) => q[1] != null);
    let d = "";
    p.forEach((q, i) => {
      if (i === 0) d += `M${sx(q[0]).toFixed(1)},${sy(q[1]).toFixed(1)}`;
      else if (step) d += `H${sx(q[0]).toFixed(1)}V${sy(q[1]).toFixed(1)}`;
      else d += `L${sx(q[0]).toFixed(1)},${sy(q[1]).toFixed(1)}`;
    });
    out += `<path class="${esc(s.cls)}" d="${d}"/>`;
  }
  out += `<text class="tick" x="4" y="12">${esc(yLabel)}</text></svg>`;
  return out;
}

function stintChart(stints, order) {
  const drivers = order.filter((c) => stints.some((s) => s.code === c));
  if (!drivers.length) return `<p class="loading">No tyre stint data.</p>`;
  const maxLap = Math.max(...stints.map((s) => s.lap_end || 0), 1);
  const W = 800, L = 52, R = 12, rowH = 18, H = drivers.length * rowH + 30;
  const sx = (l) => L + (l / maxLap) * (W - L - R);
  let out = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Tyre stints">`;
  drivers.forEach((code, i) => {
    const y = 6 + i * rowH;
    out += `<text class="tick" x="${L - 6}" y="${y + 12}" text-anchor="end">${esc(code)}</text>`;
    for (const s of stints.filter((q) => q.code === code)) {
      const x = sx((s.lap_start || 1) - 1), w = Math.max(2, sx(s.lap_end || s.lap_start || 1) - x - 1);
      const comp = String(s.compound || "UNKNOWN").toUpperCase();
      out += `<rect class="c-${esc(comp)}" x="${x.toFixed(1)}" y="${y}" width="${w.toFixed(1)}" height="${rowH - 5}" rx="3"><title>${esc(code)} stint ${esc(s.stint)}: ${esc(comp)} laps ${esc(s.lap_start)}–${esc(s.lap_end)}</title></rect>`;
    }
  });
  for (let i = 0; i <= 5; i++) {
    const lap = Math.round((maxLap * i) / 5);
    out += `<text class="tick" x="${sx(lap)}" y="${H - 6}" text-anchor="middle">${lap}</text>`;
  }
  return out + `</svg>`;
}

/* ---------- views ---------- */
async function ensureResults() {
  if (!state.results || state.results.key !== `${state.season}/${state.round}`) {
    const r = await api("results", { season: state.season, round: state.round });
    state.results = { key: `${state.season}/${state.round}`, body: r };
  }
  return state.results.body;
}

const views = {
  async calendar() {
    const r = await api("calendar", { season: state.season });
    const today = new Date().toISOString().slice(0, 10);
    const rows = r.data.races.map((x) => `<tr class="${x.date < today ? "past" : ""}"><td class="num">${x.round}</td><td>${esc(x.name)}</td><td>${esc(x.circuit)}</td><td>${esc(x.locality)}, ${esc(x.country)}</td><td>${esc(x.date)}</td><td>${esc(x.time || "")}</td></tr>`).join("");
    return [r.meta, `<div class="card"><h2>${esc(r.data.season)} calendar · ${r.data.races.length} races</h2><div class="tablewrap"><table><thead><tr><th class="num">Rd</th><th>Race</th><th>Circuit</th><th>Location</th><th>Date</th><th>Time (UTC)</th></tr></thead><tbody>${rows}</tbody></table></div></div>`];
  },
  async standings() {
    const r = await api("standings", { season: state.season });
    const d = r.data.drivers.map((x) => `<tr class="pos${x.position}"><td class="num">${x.position}</td><td>${esc(x.name)} <span class="sub">${esc(x.code || "")}</span></td><td>${esc(x.team)}</td><td class="num">${x.wins}</td><td class="num">${x.points}</td></tr>`).join("");
    const c = r.data.constructors.map((x) => `<tr class="pos${x.position}"><td class="num">${x.position}</td><td>${esc(x.team)}</td><td class="num">${x.wins}</td><td class="num">${x.points}</td></tr>`).join("");
    return [r.meta, `<div class="grid2"><div class="card"><h2>Drivers · after round ${esc(r.data.after_round)}</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Wins</th><th class="num">Pts</th></tr></thead><tbody>${d}</tbody></table></div></div><div class="card"><h2>Constructors</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Team</th><th class="num">Wins</th><th class="num">Pts</th></tr></thead><tbody>${c}</tbody></table></div></div></div>`];
  },
  async results() {
    const r = await ensureResults();
    const rows = r.data.results.map((x) => `<tr class="pos${esc(x.position)}"><td class="num">${esc(x.position)}</td><td>${esc(x.name)} <span class="sub">#${esc(x.number)}</span></td><td>${esc(x.team)}</td><td class="num">${x.grid}</td><td class="num">${x.laps}</td><td>${esc(x.time || x.status)}</td><td>${esc(x.fastest_lap || "–")}</td><td class="num">${x.points}</td></tr>`).join("");
    return [r.meta, `<div class="card"><h2>${esc(r.data.race)} · ${esc(r.data.circuit)} · ${esc(r.data.date)}</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Grid</th><th class="num">Laps</th><th>Time / status</th><th>Fastest lap</th><th class="num">Pts</th></tr></thead><tbody>${rows}</tbody></table></div></div>`];
  },
  async compare() {
    const res = await ensureResults();
    const list = res.data.results;
    const a = state.cmpA || list[0]?.driver_id, b = state.cmpB || list[1]?.driver_id;
    const opts = (sel) => list.map((x) => `<option value="${esc(x.driver_id)}" ${x.driver_id === sel ? "selected" : ""}>${esc(x.code || x.driver_id)} · ${esc(x.name)}</option>`).join("");
    const r = await api("compare", { season: state.season, round: state.round, a, b });
    const A = r.data.drivers[a], B = r.data.drivers[b];
    const kpi = (cls, name, s) => `<div class="kpi ${cls}"><div class="v">${fmtTime(s.best)}</div><div class="l">${esc(name)} best (lap ${esc(s.best_lap ?? "–")}) · median ${fmtTime(s.median)}</div></div>`;
    const html = `<div class="card"><h2>Driver comparison · ${esc(res.data.race)}</h2>
      <div class="pickers"><label>Driver A <select id="cmpA">${opts(a)}</select></label><label>Driver B <select id="cmpB">${opts(b)}</select></label></div>
      <div class="kpis">${kpi("a", a, A.summary)}${kpi("b", b, B.summary)}</div>${notes(r.meta)}</div>
      <div class="card"><h2>Lap times (seconds)</h2>${lineChart([{ cls: "line-a", points: A.laps.map((x) => [x.lap, x.time]) }, { cls: "line-b", points: B.laps.map((x) => [x.lap, x.time]) }], { yLabel: "lap time s" })}
      <div class="legend"><span><i class="sw a"></i>${esc(a)}</span><span><i class="sw b"></i>${esc(b)}</span><span>x axis: lap number. Spikes are usually pit stops or safety cars.</span></div></div>
      <div class="card"><h2>Gap per lap: A minus B (negative = A faster)</h2>${lineChart([{ cls: "line-a", points: r.data.delta_a_minus_b.map((x) => [x.lap, x.delta]) }], { yLabel: "delta s", zero: true })}</div>`;
    return [r.meta, html, () => {
      $("#cmpA").onchange = (e) => { state.cmpA = e.target.value; show(); };
      $("#cmpB").onchange = (e) => { state.cmpB = e.target.value; show(); };
    }];
  },
  async strategy() {
    const r = await api("strategy", { season: state.season, round: state.round });
    const stops = r.data.pit_stops.map((x) => `<tr><td>${esc(x.code || x.driver_id)}</td><td class="num">${x.stop}</td><td class="num">${x.lap}</td><td class="num">${esc(x.duration ?? "–")}</td></tr>`).join("");
    return [r.meta, `<div class="card"><h2>Tyre stints · ${esc(r.data.race)}</h2>${notes(r.meta)}${stintChart(r.data.stints, r.data.finish_order)}
      <div class="legend"><span>Bars are coloured by compound: soft, medium, hard, intermediate, wet. Rows follow finishing order.</span></div></div>
      <div class="card"><h2>Pit stops (${r.data.pit_stops.length})</h2><div class="tablewrap"><table><thead><tr><th>Driver</th><th class="num">Stop</th><th class="num">Lap</th><th class="num">Time in pit lane (s)</th></tr></thead><tbody>${stops || '<tr><td colspan="4">No pit stop data.</td></tr>'}</tbody></table></div></div>`];
  },
  async telemetry() {
    const res = await ensureResults();
    const list = res.data.results;
    const drv = state.telDriver || list[0]?.number, lap = state.telLap || 5;
    const opts = list.map((x) => `<option value="${esc(x.number)}" ${String(x.number) === String(drv) ? "selected" : ""}>#${esc(x.number)} ${esc(x.code || "")} · ${esc(x.name)}</option>`).join("");
    const pick = `<div class="pickers"><label>Driver <select id="telD">${opts}</select></label><label>Lap <input id="telL" type="number" min="1" max="100" value="${esc(lap)}"></label><button id="telGo">Show lap</button></div>`;
    let r;
    try {
      r = await api("telemetry", { season: state.season, round: state.round, driver: drv, lap });
    } catch (e) {
      return [null, `<div class="card"><h2>Telemetry</h2>${pick}<div class="error">${esc(e.message)}</div></div>`, bindTel];
    }
    const pts = r.data.points;
    const chart = (key, label, opt = {}) => `<div class="card"><h2>${label}</h2>${lineChart([{ cls: "line-a", points: pts.map((p) => [p.t, p[key]]) }], { height: 170, yLabel: label, ...opt })}</div>`;
    return [r.meta, `<div class="card"><h2>Telemetry · car #${esc(r.data.driver_number)} · lap ${esc(r.data.lap)} · ${fmtTime(r.data.lap_time)} · ${esc(r.data.samples)} samples</h2>${pick}<p class="sub">x axis: seconds into the lap. Car data from OpenF1 (about 3.7 samples per second).</p></div>
      ${chart("speed", "Speed km/h")}${chart("throttle", "Throttle %", { yMin: 0, yMax: 100 })}${chart("brake", "Brake", { yMin: 0, yMax: 100, step: true })}${chart("gear", "Gear", { yMin: 0, yMax: 8, step: true })}`, bindTel];
  },
};

function bindTel() {
  $("#telGo").onclick = () => { state.telDriver = $("#telD").value; state.telLap = $("#telL").value; show(); };
}

async function show() {
  const view = $("#view");
  view.innerHTML = `<p class="loading">Loading ${esc(state.tab)}…</p>`;
  try {
    const [meta, html, after] = await views[state.tab]();
    renderStatus(meta);
    view.innerHTML = html;
    if (after) after();
  } catch (e) {
    renderStatus(null);
    view.innerHTML = `<div class="error"><strong>Could not load ${esc(state.tab)}.</strong><br>${esc(e.message)}<br><span class="sub">Check your internet connection, or try another season/race. Data sources can rate-limit; wait a minute and retry.</span></div>`;
  }
}

async function loadRounds() {
  const sel = $("#round");
  try {
    const r = await api("calendar", { season: state.season });
    sel.innerHTML = r.data.races.map((x) => `<option value="${x.round}" ${x.round === state.round ? "selected" : ""}>${x.round}. ${esc(x.name)}</option>`).join("");
    if (!r.data.races.some((x) => x.round === state.round)) state.round = r.data.races[0]?.round || 1;
  } catch {
    sel.innerHTML = `<option value="${state.round}">Round ${state.round}</option>`;
  }
}

async function init() {
  try {
    const h = await api("health");
    if (h.mode === "fixture") $("#fixture-banner").classList.remove("hidden");
    $("#health").textContent = ` · server v${h.version} (${h.mode} mode)`;
  } catch { $("#health").textContent = " · server not reachable"; }
  document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("active", x === b));
    state.tab = b.dataset.tab; show();
  }));
  $("#season").addEventListener("change", async (e) => { state.season = +e.target.value; state.results = null; await loadRounds(); });
  $("#round").addEventListener("change", (e) => { state.round = +e.target.value; state.results = null; state.cmpA = state.cmpB = state.telDriver = null; });
  $("#controls").addEventListener("submit", (e) => { e.preventDefault(); state.season = +$("#season").value; state.round = +$("#round").value; state.results = null; show(); });
  await loadRounds();
  show();
}

init();
