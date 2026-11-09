"use strict";
/* PADDOCK F1 CONTROL front end. No external libraries; charts are plain SVG. */

const $ = (sel) => document.querySelector(sel);
const state = { season: new Date().getUTCFullYear(), round: 1, tab: "calendar", results: null, calendar: null };

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  let res;
  try {
    res = await fetch(`/api/${path}${qs ? "?" + qs : ""}`);
  } catch {
    throw new Error("F1 CONTROL server is not running. Start it in PowerShell: py -m f1control.server (keep that window open).");
  }
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
    out += `<path class="${esc(s.cls || "line-x")}" d="${d}"${s.color ? ` stroke="${esc(s.color)}"` : ""}${s.dash ? ` stroke-dasharray="7 5"` : ""}/>`;
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
    const d = r.data.drivers.map((x) => `<tr class="pos${x.position}" data-team="${esc(x.team_colour || "")}"><td class="num">${x.position}</td><td class="drv">${plate(x, 24)}<span>${esc(x.name)} <span class="sub">${esc(x.code || "")}</span></span></td><td><span class="teamchip" data-team="${esc(x.team_colour || "")}"></span>${esc(x.team)}</td><td class="num">${x.wins}</td><td class="num">${x.points}</td></tr>`).join("");
    const c = r.data.constructors.map((x) => `<tr class="pos${x.position}" data-team="${esc(x.team_colour || "")}"><td class="num">${x.position}</td><td><span class="teamchip" data-team="${esc(x.team_colour || "")}"></span>${esc(x.team)}</td><td class="num">${x.wins}</td><td class="num">${x.points}</td></tr>`).join("");
    return [r.meta, `<div class="grid2"><div class="card"><h2>Drivers · after round ${esc(r.data.after_round)}</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Wins</th><th class="num">Pts</th></tr></thead><tbody>${d}</tbody></table></div></div><div class="card"><h2>Constructors</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Team</th><th class="num">Wins</th><th class="num">Pts</th></tr></thead><tbody>${c}</tbody></table></div></div></div>${notes(r.meta)}`, paintTeams];
  },
  async points() {
    const r = await api("points", { season: state.season });
    const d = r.data;
    const series = d.series.map((s) => ({ color: s.team_colour || "#8a96ad", dash: s.second_driver, points: s.points }));
    const rows = d.table.map((x) => `<tr class="pos${x.position}" data-team="${esc(x.team_colour || "")}"><td class="num">${x.position}</td><td class="drv">${plate(x, 22)}<span>${esc(x.name)} <span class="sub">${esc(x.code || "")}</span></span></td><td><span class="teamchip" data-team="${esc(x.team_colour || "")}"></span>${esc(x.team)}</td><td class="num">${x.points}</td><td class="num">${x.position === 1 ? "leader" : "-" + x.gap}</td><td>${x.can_still_win ? '<span class="ok">in contention</span>' : '<span class="sub">out of reach</span>'}</td></tr>`).join("");
    return [r.meta, `<div class="kpis bigkpi"><div class="kpi a"><div class="v">${esc(d.table[0]?.code || "–")} ${esc(d.table[0]?.points ?? "")}</div><div class="l">Championship leader</div></div>
        <div class="kpi"><div class="v">${d.rounds_done}/${d.rounds_total}</div><div class="l">Rounds complete</div></div>
        <div class="kpi b"><div class="v">${d.max_points_left}</div><div class="l">Max points still available</div></div></div>
      <div class="card"><h2>Points progression · top ${d.series.length}</h2>${lineChart(series, { yLabel: "points", yMin: 0 })}
        <div class="legend">${d.series.map((s) => `<span><i class="sw${s.second_driver ? " dash" : ""}" data-team="${esc(s.team_colour || "")}"></i>${esc(s.code || s.driver_id)}</span>`).join("")}<span class="sub">dashed = second driver of the same team</span></div></div>
      <div class="card"><h2>Title fight</h2>${notes(r.meta)}<div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Pts</th><th class="num">Gap</th><th>Mathematically</th></tr></thead><tbody>${rows}</tbody></table></div></div>`, paintTeams];
  },
  async live() {
    const sessName = state.simSession || "Qualifying";
    const r = await api("replay", { season: state.season, round: state.round, session: sessName });
    state.simData = r.data;
    state.simT = 0;
    state.pos = { windows: {}, pending: {} };
    const opts = ["Qualifying", "Sprint Qualifying", "Race", "Sprint", "Practice 1", "Practice 2", "Practice 3"].map((n) => `<option ${n === sessName ? "selected" : ""}>${n}</option>`).join("");
    const html = `<div class="simbanner">SIMULATION · replay of ${esc(r.data.session)} (${esc(r.data.session_start.slice(0, 16).replace("T", " "))}Z) as if it were live · not real-time data</div>
      <div class="card"><h2>Live drill · ${esc(r.data.race)}</h2>
        <div class="pickers"><label>Session <select id="simS">${opts}</select></label>
          <label>Speed <select id="simX"><option value="10">10×</option><option value="30" selected>30×</option><option value="60">60×</option><option value="120">120×</option></select></label>
          <button id="simGo" type="button">Start</button><button id="simPause" type="button">Pause</button><button id="simReset" type="button">Reset</button></div>
        <div class="simclock"><span id="simClock">00:00</span><span class="sub"> / ${fmtClock(r.data.length_s)} session time</span><span id="simState" class="simstate">READY</span></div>
        <div class="simbar"><i id="simProg"></i></div></div>
      <div class="grid2"><div class="card"><h2>Timing tower</h2><div class="tablewrap"><table><thead><tr><th class="num">P</th><th>Driver</th><th class="num">Best</th><th class="num">Gap</th><th class="num">Last</th><th class="num">Laps</th></tr></thead><tbody id="tower"><tr><td colspan="6" class="sub">Press Start.</td></tr></tbody></table></div></div>
      <div class="card"><h2>Race control</h2><ul class="plain feed" id="feed"><li class="sub">Waiting for session start…</li></ul></div></div>`;
    return [r.meta, html, bindSim];
  },
  async weekend() {
    const [wk, wx] = await Promise.all([
      api("weekend", { season: state.season, round: state.round }),
      api("weather", { season: state.season, round: state.round }).catch((e) => ({ error: e.message })),
    ]);
    const d = wk.data;
    const t = (v) => (v == null ? "–" : fmtTime(v));
    const sess = d.sessions.map((x) => `<span class="pill ${x.best.length ? "done" : ""}">${esc(x.name)} · ${esc((x.start || "").slice(5, 16).replace("T", " "))}Z</span>`).join(" ");
    const prac = d.sessions.filter((x) => x.best.length).map((x) => `<div class="card"><h2>${esc(x.name)} · best laps</h2><div class="tablewrap"><table><thead><tr><th class="num">#</th><th>Driver</th><th>Team</th><th class="num">Best</th><th class="num">Gap</th></tr></thead><tbody>${x.best.slice(0, 20).map((b, i) => `<tr class="pos${i + 1}" data-team="${esc(b.team_colour || "")}"><td class="num">${i + 1}</td><td class="drv">${plate({ number: b.number, team_colour: b.team_colour }, 24)}<span>${esc(b.code || b.number)}</span></td><td>${esc(b.team || "")}</td><td class="num">${t(b.time)}</td><td class="num">${i ? "+" + b.gap.toFixed(3) : "–"}</td></tr>`).join("")}</tbody></table></div></div>`).join("");
    const q = d.qualifying.length ? `<div class="card"><h2>Qualifying</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Q1</th><th class="num">Q2</th><th class="num">Q3</th></tr></thead><tbody>${d.qualifying.map((x) => `<tr class="pos${x.position}${x.q3 ? "" : x.q2 ? " q2out" : " q1out"}"><td class="num">${x.position}</td><td>${esc(x.name)} <span class="sub">${esc(x.code || "")}</span></td><td>${esc(x.team)}</td><td class="num">${esc(x.q1 || "–")}</td><td class="num">${esc(x.q2 || "–")}</td><td class="num">${esc(x.q3 || "–")}</td></tr>`).join("")}</tbody></table></div><div class="legend"><span>Dimmed rows were knocked out in Q1 / Q2</span></div></div>` : "";
    let w = "";
    if (wx.error) w = `<div class="card"><h2>Weather</h2><div class="error">${esc(wx.error)}</div></div>`;
    else {
      const f = wx.data.forecast, m = wx.data.measured;
      const idx = (arr) => arr.map((v, i) => [i, v]);
      if (f) {
        const maxRain = Math.max(0, ...f.rain_pct.filter((v) => v != null));
        const raceHour = f.time.findIndex((x) => x.startsWith(wx.data.date + "T" + String(wx.data.time || "13:00").slice(0, 2)));
        w += `<div class="kpis bigkpi"><div class="kpi a"><div class="v">${esc(Math.max(...f.temp_c.filter((v) => v != null)))}°C</div><div class="l">Forecast high · race weekend</div></div>
          <div class="kpi b"><div class="v">${esc(maxRain)}%</div><div class="l">Highest chance of rain</div></div>
          ${raceHour >= 0 ? `<div class="kpi"><div class="v">${esc(f.temp_c[raceHour])}°C · ${esc(f.rain_pct[raceHour])}%</div><div class="l">At race start (${esc(f.time[raceHour].slice(11))} UTC)</div></div>` : ""}</div>
          <div class="card"><h2>Forecast · temperature °C (hourly, UTC, Fri–Sun)</h2>${lineChart([{ cls: "line-a", points: idx(f.temp_c) }], { height: 180, yLabel: "°C" })}
          <h2>Chance of rain %</h2>${lineChart([{ cls: "line-b", points: idx(f.rain_pct) }], { height: 150, yLabel: "%", yMin: 0, yMax: 100, step: true })}
          <div class="legend"><span>x axis: hours from Friday 00:00 UTC</span><span>${esc(f.credit)}</span></div></div>`;
      }
      if (m) {
        w += `<div class="card"><h2>Measured at the track during the race · ${m.rain ? '<span class="warn">rain recorded</span>' : "dry"}</h2>${lineChart([{ cls: "line-a", points: idx(m.track_c) }, { cls: "line-b", points: idx(m.air_c) }], { height: 180, yLabel: "°C" })}
          <div class="legend"><span><i class="sw a"></i>track</span><span><i class="sw b"></i>air</span><span>OpenF1 track weather station, about one reading per minute</span></div></div>`;
      }
      w += notes(wx.meta);
    }
    return [wk.meta, `<div class="card"><h2>${esc(d.race)} weekend · race ${esc(d.date)}</h2><p>${sess || '<span class="sub">Session list appears once OpenF1 publishes it.</span>'}</p>${notes(wk.meta)}
      <p class="sub">Free data appears after each session ends. Live timing needs undercut-f1 (pending approval).</p></div>${w}${q}${prac}`, paintTeams];
  },
  async results() {
    const r = await ensureResults();
    const res = r.data.results;
    let stints = {};
    try {
      const st = await api("strategy", { season: state.season, round: state.round });
      for (const x of st.data.stints) (stints[x.code] = stints[x.code] || []).push(x);
    } catch { stints = {}; }
    const maxLap = Math.max(1, ...res.map((x) => x.laps));
    const tyres = (code) => {
      const list = (stints[code] || []).sort((a, b) => a.stint - b.stint);
      if (!list.length) return '<span class="sub">–</span>';
      const icons = list.map((s) => `<span class="tstint">${tyreIcon(s.compound, 26)}<span class="tl">${esc((s.lap_end || 0) - (s.lap_start || 0) + 1)}</span></span>`).join("");
      return `<div class="tyrewrap"><div class="tyreicons">${icons}</div><svg class="minityres" viewBox="0 0 100 10" role="img" aria-label="${esc(list.map((s) => s.compound).join(", "))}">${list.map((s) => `<rect class="c-${esc(String(s.compound || "UNKNOWN").toUpperCase())}" x="${(((s.lap_start || 1) - 1) / maxLap) * 100}" y="1" width="${Math.max(1.5, (((s.lap_end || s.lap_start || 1) - (s.lap_start || 1) + 1) / maxLap) * 100 - 1)}" height="8" rx="1.5"><title>${esc(s.compound)} L${esc(s.lap_start)}–${esc(s.lap_end)}</title></rect>`).join("")}</svg></div>`;
    };
    const moved = (x) => {
      const fin = parseInt(x.position, 10);
      if (!x.grid || isNaN(fin)) return '<span class="sub">pit lane</span>';
      const d = x.grid - fin;
      return d > 0 ? `<span class="up">▲${d}</span>` : d < 0 ? `<span class="down">▼${-d}</span>` : '<span class="sub">=</span>';
    };
    const fl = (x) => x.fastest_lap_rank === "1" ? `<span class="purple" title="Fastest lap">${esc(x.fastest_lap)}</span>` : esc(x.fastest_lap || "–");
    const podium = res.slice(0, 3).map((x, i) => `<div class="dcard p${i + 1}" data-team="${esc(x.team_colour || "")}">${plate(x, 64)}<div><div class="dpos">P${esc(x.position)} ${flagForNationality(x.nationality, 22)}</div><div class="dname">${esc(x.name)}</div><div class="sub">${esc(x.team)} · ${esc(x.time || x.status)}</div>${tyres(x.code)}</div></div>`).join("");
    const rows = res.map((x) => `<tr class="pos${esc(x.position)}" data-team="${esc(x.team_colour || "")}"><td class="num">${esc(x.position)}</td><td class="drv">${plate(x, 26)}${flagForNationality(x.nationality, 20)}<span>${esc(x.name)}</span></td><td><span class="teamchip" data-team="${esc(x.team_colour || "")}"></span>${esc(x.team)}</td><td class="num">${x.grid || "PL"}</td><td class="num">${moved(x)}</td><td>${tyres(x.code)}</td><td>${esc(x.time || x.status)}</td><td>${fl(x)}</td><td class="num">${x.points}</td></tr>`).join("");
    return [r.meta, `<div class="podium">${podium}</div><div class="card"><h2>Classification · ${esc(r.data.circuit)} · ${esc(r.data.date)}</h2><div class="tablewrap"><table><thead><tr><th class="num">Pos</th><th>Driver</th><th>Team</th><th class="num">Grid</th><th class="num">+/-</th><th>Tyres</th><th>Time / status</th><th>Fastest lap</th><th class="num">Pts</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="legend"><span><i class="purple">■</i> fastest lap</span><span>▲▼ places gained/lost from grid</span><span>Tyres: soft · medium · hard · inter · wet</span></div></div>`, paintTeams];
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
  async planner() {
    const a = state.alloc || { soft: 2, medium: 2, hard: 2, pit_loss: "" };
    const form = `<div class="pickers">
      <label>Soft sets <input id="aS" type="number" min="0" max="8" value="${esc(a.soft)}"></label>
      <label>Medium sets <input id="aM" type="number" min="0" max="8" value="${esc(a.medium)}"></label>
      <label>Hard sets <input id="aH" type="number" min="0" max="8" value="${esc(a.hard)}"></label>
      <label>Pit loss s (blank = measured) <input id="aP" type="number" min="10" max="60" value="${esc(a.pit_loss)}" placeholder="auto"></label>
      <button id="runPlan" type="button">Run projection</button></div>
      <p class="sub">Sets left for the race. A standard weekend allocation is 13 dry sets (8 soft, 3 medium, 2 hard); most are used before Sunday. Dry races must use two different compounds.</p>`;
    let r;
    try {
      const params = { season: state.season, round: state.round, soft: a.soft, medium: a.medium, hard: a.hard };
      if (a.pit_loss) params.pit_loss = a.pit_loss;
      r = await api("projection", params);
    } catch (e) {
      return [null, `<div class="card"><h2>Strategy planner</h2>${form}<div class="error">${esc(e.message)}</div></div>`, bindPlan];
    }
    const d = r.data, best = d.plans[0];
    const comps = Object.entries(d.compounds).sort((x, y) => x[1].offset - y[1].offset);
    const compRows = comps.map(([c, m]) => `<tr><td>${tyreIcon(c, 22)} ${esc(c)}</td><td class="num">+${m.offset.toFixed(3)}</td><td class="num">${m.deg.toFixed(3)}</td><td class="num">${m.max_life_seen}</td><td class="num">${m.stints} / ${m.laps}</td></tr>`).join("");
    const planRows = d.plans.map((p, i) => `<tr class="${i === 0 ? "pos1" : ""}"><td class="num">${i + 1}</td><td>${planBar(p, d.race_laps)}</td><td>${p.stops}-stop</td><td>${p.pit_laps.map((l) => "L" + l).join(", ")}</td><td class="num">${i === 0 ? "fastest" : "+" + p.delta.toFixed(1) + " s"}</td></tr>`).join("");
    const v = d.validation;
    const used = Object.entries(d.used_top10).map(([k, v2]) => `<li><b>${esc(k)}</b> · ${esc(v2.join(", "))}</li>`).join("");
    const html = `<div class="card model"><h2>Strategy planner · ${esc(d.race)} · ${esc(d.race_laps)} laps</h2>${form}
        <div class="modeltag">${esc(d.label)}</div>${notes(r.meta)}</div>
      ${best ? `<div class="kpis bigkpi"><div class="kpi a"><div class="v">${esc(best.sequence.map((c) => c[0]).join(" → "))}</div><div class="l">Projected fastest · pit lap ${esc(best.pit_laps.join(" & "))}</div></div>
        <div class="kpi"><div class="v">${esc(d.pit_loss.toFixed(1))} s</div><div class="l">Pit loss per stop${d.measured_pit_loss ? " · measured" : ""}</div></div>
        ${v ? `<div class="kpi b"><div class="v">${v.error_pct > 0 ? "+" : ""}${esc(v.error_pct)}%</div><div class="l">Model vs ${esc(v.driver)}'s real race time</div></div>` : ""}</div>` : ""}
      <div class="card"><h2>Ranked plans (best pit laps found for each)</h2><div class="tablewrap"><table><thead><tr><th class="num">#</th><th>Stints</th><th>Type</th><th>Pit</th><th class="num">vs best</th></tr></thead><tbody>${planRows || '<tr><td colspan="5">No legal plan with this allocation.</td></tr>'}</tbody></table></div></div>
      <div class="card"><h2>Projected lap times · top 3 plans</h2>${lineChart(d.plans.slice(0, 3).map((p, i) => ({ cls: ["line-a", "line-b", "line-c"][i], points: p.trace.map((t, j) => [j + 1, t]) })), { yLabel: "lap s (no pit loss)" })}
        <div class="legend">${d.plans.slice(0, 3).map((p, i) => `<span><i class="sw ${["a", "b", "c"][i]}"></i>${esc(p.sequence.join("-"))}</span>`).join("")}</div></div>
      <div class="grid2"><div class="card"><h2>Tyre model fitted from this race</h2><div class="tablewrap"><table><thead><tr><th>Compound</th><th class="num">Pace gap s</th><th class="num">Wear s/lap</th><th class="num">Longest stint seen</th><th class="num">Stints / laps</th></tr></thead><tbody>${compRows}</tbody></table></div></div>
      <div class="card"><h2>Reality check</h2>${v ? `<p>${esc(v.driver)} ran <b>${esc(v.sequence.join(" → "))}</b>, pitting lap ${esc(v.pit_laps.join(" & "))}. Model: ${fmtTime(v.predicted)} · real: ${fmtTime(v.actual)}.</p>` : "<p class=\"sub\">Winner's strategy could not be checked.</p>"}
        <h2>What the top 10 actually ran</h2><ul class="plain">${used}</ul>
        <h2>Assumptions</h2><ul class="plain">${d.assumptions.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`;
    return [r.meta, html, bindPlan];
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
    return [r.meta, `<div class="card"><h2>Telemetry · car #${esc(r.data.driver_number)} · lap ${esc(r.data.lap)} · ${fmtTime(r.data.lap_time)} · ${esc(r.data.samples)} samples</h2>${pick}<p class="sub">x axis: seconds into the lap. Car data from OpenF1 (about 3.7 samples per second).</p><div class="flaglabel">Track status by lap (race control, replay)</div><div id="flagstrip" class="flagstrip"></div></div>
      ${chart("speed", "Speed km/h")}${chart("throttle", "Throttle %", { yMin: 0, yMax: 100 })}${chart("brake", "Brake", { yMin: 0, yMax: 100, step: true })}${chart("gear", "Gear", { yMin: 0, yMax: 8, step: true })}`, bindTel];
  },
};


// Original tyre graphic: black tyre, coloured compound ring, letter. Not a reproduction of any brand's design.
function tyreIcon(compound, size = 20) {
  const c = String(compound || "UNKNOWN").toUpperCase();
  const letter = { SOFT: "S", MEDIUM: "M", HARD: "H", INTERMEDIATE: "I", WET: "W" }[c] || "?";
  return `<svg class="tyre" width="${size}" height="${size}" viewBox="0 0 24 24" role="img" aria-label="${esc(c.toLowerCase())} tyre"><circle cx="12" cy="12" r="11" fill="#0b0d12" stroke="#2a2f3a" stroke-width="1"/><circle class="c-${esc(c)} ring" cx="12" cy="12" r="7.6" fill="none" stroke-width="2.6"/><circle cx="12" cy="12" r="5.6" fill="#161a22"/><text x="12" y="15.4" text-anchor="middle" class="tletter">${letter}</text></svg>`;
}

function plate(x, size) {
  const col = /^#[0-9A-Fa-f]{6}$/.test(x.team_colour || "") ? x.team_colour : "#3a4660";
  return `<svg class="plate" width="${size}" height="${size}" viewBox="0 0 40 40" role="img" aria-label="Car ${esc(x.number)}"><polygon points="6,2 40,2 34,38 0,38" fill="${col}"/><text x="20" y="26" text-anchor="middle" class="plate-n">${esc(x.number)}</text></svg>`;
}

function planBar(p, laps) {
  const W = 300, H = 16;
  return `<svg class="planbar" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(p.sequence.join(" then "))}">${p.stints.map((s) => `<rect class="c-${esc(s.compound)}" x="${((s.from - 1) / laps) * W + 1}" y="1" width="${Math.max(2, (s.laps / laps) * W - 2)}" height="${H - 2}" rx="2"><title>${esc(s.compound)} laps ${s.from}–${s.to}</title></rect><text x="${((s.from - 1) / laps) * W + 6}" y="12" class="planlbl">${esc(s.compound[0])}${s.laps}</text>`).join("")}</svg>`;
}

function bindPlan() {
  $("#runPlan").onclick = () => {
    state.alloc = { soft: $("#aS").value || 0, medium: $("#aM").value || 0, hard: $("#aH").value || 0, pit_loss: $("#aP").value };
    show();
  };
}

function paintTeams() {
  document.querySelectorAll("[data-team]").forEach((el) => {
    const c = el.dataset.team;
    if (!/^#[0-9A-Fa-f]{6}$/.test(c)) return;
    if (el.classList.contains("teamchip") || el.classList.contains("sw")) el.style.background = c;
    else if (el.tagName === "TR") el.style.boxShadow = `inset 3px 0 0 ${c}`;
    else el.style.borderLeft = `4px solid ${c}`;
  });
}

function paintSwatches() {
  const pal = ["#ff2a3d", "#39d5ff", "#ffc24a", "#3ff0a8", "#b98cff", "#ff8a3d", "#f2f5fa", "#5b9bd5", "#ff6fb5", "#9be15d"];
  document.querySelectorAll(".sw[data-c]").forEach((el) => { el.style.background = pal[+el.dataset.c % pal.length]; });
}

async function updateStatusForLap(lap) {
  try {
    const key = `${state.season}/${state.round}`;
    if (!state.rc || state.rc.key !== key) state.rc = { key, body: await api("racecontrol", { season: state.season, round: state.round }) };
    const by = state.rc.body.data.by_lap;
    state.status = { lap, status: by[Math.min(lap, by.length) - 1] || "GREEN", by };
  } catch { state.status = null; }
  setBeacon(state.status);
  const strip = $("#flagstrip");
  if (strip && state.status) strip.innerHTML = state.status.by.map((s, i) => `<i class="fs st-${s}${i + 1 === +lap ? " cur" : ""}" title="Lap ${i + 1}: ${STATUS[s] || s}"></i>`).join("");
}

function fmtClock(sec) {
  sec = Math.max(0, Math.floor(sec));
  return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
}

function stopSim() {
  if (state.simTimer) clearInterval(state.simTimer);
  state.simTimer = null;
  const g = document.querySelector("#trackmap #cars");
  if (g && state.tab !== "live") g.innerHTML = "";
}

const POS_WIN = 120;
async function loadPosWindow(w) {
  const P = state.pos;
  if (!P || P.windows[w] || P.pending[w] || !state.simData) return;
  P.pending[w] = true;
  try {
    const r = await api("positions", { season: state.season, round: state.round, session: state.simData.session, from: w, to: w + POS_WIN });
    P.windows[w] = r.data.cars;
  } catch (e) {
    P.windows[w] = {};
    P.error = e.message;
  } finally { delete P.pending[w]; }
}

function drawCars(t) {
  const svg = $("#trackmap svg");
  if (!svg || !state.pos) return;
  const w = Math.floor(t / POS_WIN) * POS_WIN;
  loadPosWindow(w);
  if (t - w > POS_WIN * 0.7) loadPosWindow(w + POS_WIN);  // prefetch the next two minutes
  const cars = state.pos.windows[w] || {};
  const drivers = Object.fromEntries(state.simData.drivers.map((x) => [String(x.number), x]));
  let g = svg.querySelector("#cars");
  if (!g) { g = document.createElementNS("http://www.w3.org/2000/svg", "g"); g.id = "cars"; svg.appendChild(g); }
  let out = "";
  for (const [num, pts] of Object.entries(cars)) {
    let i = pts.length - 1;
    while (i >= 0 && pts[i][0] > t) i--;
    if (i < 0 || t - pts[i][0] > 4) continue;  // no recent fix: car in garage / not running
    let [, x, y] = pts[i];
    const nxt = pts[i + 1];
    if (nxt && nxt[0] - pts[i][0] <= 2) {  // smooth between seconds
      const f = Math.min(1, (t - pts[i][0]) / (nxt[0] - pts[i][0]));
      x += (nxt[1] - x) * f; y += (nxt[2] - y) * f;
    }
    const dr = drivers[num] || {};
    const col = /^#[0-9A-Fa-f]{6}$/.test(dr.team_colour || "") ? dr.team_colour : "#e9eef7";
    out += `<g class="car"><circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.6" fill="${col}"/><text x="${(x + 3.2).toFixed(1)}" y="${(y - 2.2).toFixed(1)}" class="carlbl">${esc(dr.code || num)}</text></g>`;
  }
  g.innerHTML = out;
  const n = (out.match(/class="car"/g) || []).length;
  $("#map-note").textContent = state.pos.error ? "Car tracker: " + state.pos.error : `Car tracker · ${n} car${n === 1 ? "" : "s"} on track · OpenF1 positions (replay)`;
}

function simFrame() {
  const d = state.simData;
  if (!d) return;
  const t = state.simT;
  drawCars(t);
  const drivers = Object.fromEntries(d.drivers.map((x) => [x.number, x]));
  const per = {};
  let newest = null;
  for (const lap of d.laps) {
    if (lap.t > t) break;
    const p = per[lap.driver] || (per[lap.driver] = { best: Infinity, last: null, laps: 0, bestAt: 0 });
    p.last = lap.time; p.laps += 1;
    if (lap.time < p.best) { p.best = lap.time; p.bestAt = lap.t; }
    newest = lap;
  }
  const rows = Object.entries(per).sort((a, b) => a[1].best - b[1].best);
  const top = rows.length ? rows[0][1].best : 0;
  $("#tower").innerHTML = rows.map(([num, p], i) => {
    const dr = drivers[num] || { number: num };
    const fresh = t - p.bestAt < 12 * (state.simSpeed || 30) / 30;
    return `<tr class="${i === 0 ? "pos1" : ""} ${fresh ? "flash" : ""}" data-team="${esc(dr.team_colour || "")}"><td class="num">${i + 1}</td><td class="drv">${plate(dr, 22)}<span>${esc(dr.code || num)}</span></td><td class="num">${fmtTime(p.best)}</td><td class="num">${i ? "+" + (p.best - top).toFixed(3) : "–"}</td><td class="num">${fmtTime(p.last)}</td><td class="num">${p.laps}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="sub">No timed laps yet.</td></tr>`;
  paintTeams();
  const events = d.status.filter((e) => e.t <= t);
  const cur = events.length ? events[events.length - 1] : { status: "GREEN" };
  state.status = { lap: fmtClock(t), status: cur.status, by: [] };
  setBeacon(state.status);
  $("#beacon-text").textContent = `SIM ${fmtClock(t)} · ${STATUS[cur.status] || cur.status}`;
  $("#feed").innerHTML = events.slice(-8).reverse().map((e) => `<li><b class="st-txt-${esc(e.status)}">${fmtClock(e.t)}</b> ${esc(e.message || e.status)}</li>`).join("");
  $("#simClock").textContent = fmtClock(t);
  $("#simProg").style.width = `${Math.min(100, (t / d.length_s) * 100)}%`;
  if (t >= d.length_s) { stopSim(); $("#simState").textContent = "FINISHED"; }
}

function bindSim() {
  state.simSpeed = 30;
  $("#simS").onchange = (e) => { stopSim(); state.simSession = e.target.value; show(); };
  $("#simX").onchange = (e) => { state.simSpeed = +e.target.value; };
  $("#simGo").onclick = () => {
    if (state.simTimer) return;
    $("#simState").textContent = "SIMULATED LIVE";
    state.simTimer = setInterval(() => { state.simT += 0.25 * state.simSpeed; simFrame(); }, 250);
  };
  $("#simPause").onclick = () => { stopSim(); $("#simState").textContent = "PAUSED"; };
  $("#simReset").onclick = () => { stopSim(); state.simT = 0; $("#simState").textContent = "READY"; simFrame(); };
}

function bindTel() {
  updateStatusForLap(+(state.telLap || 5));
  $("#telGo").onclick = () => { state.telDriver = $("#telD").value; state.telLap = $("#telL").value; show(); };
}

async function show() {
  const view = $("#view");
  stopSim();
  view.innerHTML = `<p class="loading">Acquiring ${esc(state.tab)} data</p>`;
  setHero();
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

function setHero() {
  const opt = $("#round").selectedOptions[0];
  const race = state.calendar?.races?.find((r) => r.round === state.round);
  $("#hero-kicker").textContent = `Season ${state.season} · Round ${state.round}${race?.sprint ? " · Sprint weekend" : ""}`;
  $("#hero-title").textContent = race ? race.name : (opt ? opt.textContent.replace(/^\d+\.\s*/, "") : `Season ${state.season}`);
  $("#hero-flag").innerHTML = race ? flagSvg(race.country, 44) : "";
  $("#hero-meta").textContent = race ? `${race.circuit} · ${race.locality}, ${race.country} · ${race.date}` : "";
  const key = `${state.season}/${state.round}`;
  if (state.mapKey !== key) { state.mapKey = key; state.status = null; loadMap(key); }
  setBeacon(state.status);
}

async function loadMap(key) {
  $("#trackmap").innerHTML = `<p class="loading">Tracing circuit</p>`;
  $("#map-note").textContent = "";
  try {
    const m = await api("trackmap", { season: state.season, round: state.round });
    if (state.mapKey !== key) return;
    const pts = m.data.points.map((p) => p.join(",")).join(" ");
    $("#trackmap").innerHTML = `<svg viewBox="-8 -8 ${m.data.width + 22} ${m.data.height + 16}" role="img" aria-label="Track map of ${esc(m.data.circuit)}"><polygon class="track-glow" points="${pts}"/><polygon class="track" points="${pts}"/><circle class="sf" cx="${m.data.points[0][0]}" cy="${m.data.points[0][1]}" r="2.2"/></svg>`;
    $("#map-note").textContent = (m.meta.notes[0] || `Traced from car position data, ${m.data.traced_from.date}`) + " · OpenF1";
  } catch (e) {
    if (state.mapKey === key) { $("#trackmap").innerHTML = ""; $("#map-note").textContent = "No track map: " + e.message; }
  }
}

const STATUS = { GREEN: "Green flag", YELLOW: "Yellow flag", VSC: "Virtual safety car", SC: "Safety car", RED: "Red flag", CHEQUERED: "Chequered flag" };
function setBeacon(st) {
  const b = $("#beacon");
  b.className = "beacon" + (st ? " st-" + st.status : "");
  $("#beacon-text").textContent = st ? `LAP ${st.lap} · ${STATUS[st.status] || st.status} · replay` : "TRACK STATUS · pick a lap in Telemetry";
}

function tickClocks() {
  const now = new Date();
  const f = (tz) => now.toLocaleTimeString("en-GB", { timeZone: tz, hour12: false });
  $("#clkZ").textContent = f("UTC") + "Z";
  $("#clkL").textContent = now.toLocaleTimeString("en-GB", { hour12: false }) + " " + (Intl.DateTimeFormat("en-US", { timeZoneName: "short" }).formatToParts(now).find((p) => p.type === "timeZoneName")?.value || "");
  $("#clkD").textContent = f("America/New_York") + " " + (Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", timeZoneName: "short" }).formatToParts(now).find((p) => p.type === "timeZoneName")?.value || "ET");
}

/* ---------- v0.6: countdown to the next session (always the real upcoming weekend, not the selected race) ---------- */
const LIVE_WINDOW_S = { "Race": 2.5 * 3600, "Sprint": 3600, "Qualifying": 3600, "Sprint Qualifying": 2700 };
function sessionStart(x) { return x.time ? Date.parse(`${x.date}T${x.time}`) : Date.parse(`${x.date}T00:00:00Z`); }
async function loadCountdown() {
  const y = new Date().getUTCFullYear();
  state.cd = [];
  for (const season of [y, y + 1]) {
    try {
      const r = await api("calendar", { season });
      for (const race of r.data.races) {
        const list = race.sessions?.length ? race.sessions : [{ name: "Race", date: race.date, time: race.time }];
        for (const x of list) state.cd.push({ race, name: x.name, start: sessionStart(x), timed: !!x.time });
      }
      if (state.cd.some((x) => x.start > Date.now())) break;
    } catch { /* next season may not be published yet */ }
  }
  state.cd.sort((a, b) => a.start - b.start);
  tickCountdown();
}
function dhms(ms) {
  const t = Math.max(0, Math.floor(ms / 1000)), d = Math.floor(t / 86400), h = Math.floor(t / 3600) % 24, m = Math.floor(t / 60) % 60, s = t % 60;
  const p = (n) => String(n).padStart(2, "0");
  return `${d ? `${d}<small>D</small>` : ""}${p(h)}<small>H</small>${p(m)}<small>M</small>${p(s)}<small>S</small>`;
}
function tickCountdown() {
  if (!state.cd) return;
  const now = Date.now(), bar = $("#countdown");
  const live = state.cd.find((x) => x.timed && x.start <= now && now < x.start + (LIVE_WINDOW_S[x.name] || 3600) * 1000);
  const next = state.cd.find((x) => x.start > now);
  const cur = live || next;
  if (!cur) { $("#cd-name").textContent = "No upcoming sessions published yet"; return; }
  bar.classList.toggle("live", !!live);
  $("#cd-tag").textContent = live ? "LIVE" : "NEXT";
  if (state.cdKey !== cur.race.season + "/" + cur.race.round + cur.name) {
    state.cdKey = cur.race.season + "/" + cur.race.round + cur.name;
    $("#cd-flag").innerHTML = flagSvg(cur.race.country, 26);
    $("#cd-name").textContent = cur.race.name;
    const when = new Date(cur.start);
    $("#cd-sess").textContent = `${cur.name.toUpperCase()} · ${when.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}${cur.timed ? "" : " (time TBC)"}`;
    const race = state.cd.find((x) => x.race === cur.race && x.name === "Race");
    $("#cd-race").textContent = race && cur.name !== "Race" ? `LIGHTS OUT ${new Date(race.start).toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}` : "";
  }
  $("#cd-time").innerHTML = live ? "SESSION LIVE" : dhms(cur.start - now);
}

async function loadRounds() {
  const sel = $("#round");
  try {
    const r = await api("calendar", { season: state.season });
    state.calendar = r.data;
    sel.innerHTML = r.data.races.map((x) => `<option value="${x.round}" ${x.round === state.round ? "selected" : ""}>${x.round}. ${esc(x.name)}</option>`).join("");
    if (!r.data.races.some((x) => x.round === state.round)) state.round = r.data.races[0]?.round || 1;
  } catch {
    sel.innerHTML = `<option value="${state.round}">Round ${state.round}</option>`;
  }
}

async function init() {
  $("#season").value = state.season;
  tickClocks();
  setInterval(() => { tickClocks(); tickCountdown(); }, 1000);
  loadCountdown();
  setInterval(loadCountdown, 6 * 3600 * 1000);
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
  $("#round").addEventListener("change", (e) => { state.round = +e.target.value; state.results = null; state.cmpA = state.cmpB = state.telDriver = null; setHero(); });
  $("#controls").addEventListener("submit", (e) => { e.preventDefault(); state.season = +$("#season").value; state.round = +$("#round").value; state.results = null; show(); });
  await loadRounds();
  show();
}

init();
