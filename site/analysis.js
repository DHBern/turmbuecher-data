/* Berner Turmbücher — Auswertung: which offences are recorded, when, and together.
   Loaded by app.js on #/auswertung. Data: data/analysis.json (scripts/build_site.py),
   one row per described entry: [id, year, [offences], [sanctions], continuation,
   volume, title]. Charts with d3 and d3-sankey (loaded on demand).
   Everything counted here was labelled by a language model on a machine reading. */
window.TBAnalysis = (() => {
  "use strict";
  const LIBS = ["https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js",
                "https://cdnjs.cloudflare.com/ajax/libs/d3-sankey/0.12.3/d3-sankey.min.js"];
  /* one fixed hue per offence group (identity): groups and colours come from the
     vocabulary (taxonomy/delikte.json → data/analysis.json), so a new group or
     category needs no change here */
  let GROUPS = [], HUES = [];
  const NEUTRAL = "#898781";
  let data = null, libs = null;

  const load = (src) => new Promise((ok, no) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = () => no(new Error(src)); document.head.appendChild(s); });
  async function ready(json) {
    if (!libs) libs = (async () => { for (const l of LIBS) await load(l); })();
    if (!data) data = json("data/analysis.json");
    await libs;
    return data;
  }

  async function show(app, ctx) {
    const { t, esc, num, json, store } = ctx;
    app.innerHTML = `<p class="loading">${esc(t("loading"))}</p>`;
    let D;
    try { D = await ready(json); } catch (e) { app.innerHTML = `<p>${esc(t("error.load"))}: ${esc(e.message)}</p>`; return; }
    GROUPS = D.groups.map((g) => g.id);
    HUES = D.groups.map((g) => g.farbe || NEUTRAL);
    const gi = (name) => { const i = GROUPS.indexOf(name); return i < 0 ? GROUPS.length - 1 : i; };
    const hue = (o) => HUES[gi(D.offences[o].group)];
    const dated = D.entries.filter((e) => e[1]);
    const yMin = d3.min(dated, (e) => e[1]), yMax = d3.max(dated, (e) => e[1]);
    const ui = { from: yMin, to: yMax, cont: store.get("an.cont", true), right: store.get("an.right", "co"), vol: "" };

    app.innerHTML = `
      <section class="intro">
        <h1>${esc(t("an.h1"))} <span class="badge proto">${esc(t("proto"))}</span></h1>
        <p>${esc(t("an.intro", { n: num(D.entries.length), vols: D.volumes.join(", ") }))}</p>
        <p class="caveat">${esc(t("an.caveat", { model: D.model.join(", ") || "–" }))}</p>
      </section>
      <div class="anbar" role="group" aria-label="${esc(t("an.filters"))}">
        <label>${esc(t("an.from"))} <input type="number" id="an-from" min="${yMin}" max="${yMax}" value="${yMin}"></label>
        <label>${esc(t("an.to"))} <input type="number" id="an-to" min="${yMin}" max="${yMax}" value="${yMax}"></label>
        <label>${esc(t("facet.vol"))} <select id="an-vol"><option value="">${esc(t("an.allvols"))}</option>${D.volumes.map((v, i) => `<option value="${i}">${esc(v)}</option>`).join("")}</select></label>
        <label><input type="checkbox" id="an-cont" ${ui.cont ? "checked" : ""}> ${esc(t("an.cont"))}</label>
        <span id="an-n" class="muted small"></span>
      </div>
      <div class="legend an-legend">${GROUPS.map((g, i) => `<span><i style="background:${HUES[i]}"></i>${esc(g)}</span>`).join("")}</div>

      <section class="an-card">
        <h2>${esc(t("an.sankey.h2"))}</h2>
        <div class="anbar"><label>${esc(t("an.right"))} <select id="an-right">
          <option value="co" ${ui.right === "co" ? "selected" : ""}>${esc(t("an.right.co"))}</option>
          <option value="san" ${ui.right === "san" ? "selected" : ""}>${esc(t("an.right.san"))}</option></select></label></div>
        <p class="small muted" id="an-sankey-note"></p>
        <div class="scroll"><div id="an-sankey" class="chart"></div></div>
        <div id="an-pick"></div>
      </section>

      <section class="an-card">
        <h2>${esc(t("an.time.h2"))}</h2>
        <p class="small muted">${esc(t("an.time.note"))}</p>
        <div class="scroll"><div id="an-time" class="chart"></div></div>
        <details class="tableview"><summary>${esc(t("an.table"))}</summary><div class="scroll" id="an-time-table"></div></details>
      </section>

      <section class="an-card">
        <h2>${esc(t("an.count.h2"))}</h2>
        <p class="small muted">${esc(t("an.count.note"))}</p>
        <div id="an-count" class="chart"></div>
        <details class="tableview"><summary>${esc(t("an.table"))}</summary><div class="scroll" id="an-count-table"></div></details>
      </section>
      <div class="tip an-tip" id="an-tip" hidden></div>`;

    const $ = (id) => document.getElementById(id);
    const tip = $("an-tip");
    const showTip = (ev, html) => {
      tip.innerHTML = html; tip.hidden = false;
      const w = tip.offsetWidth, h = tip.offsetHeight;
      tip.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, ev.clientX + 12)) + "px";
      tip.style.top = (ev.clientY + 16 + h > window.innerHeight ? ev.clientY - h - 10 : ev.clientY + 16) + "px";
    };
    const hideTip = () => { tip.hidden = true; };

    const rows = () => D.entries.filter((e) => e[1] && e[1] >= ui.from && e[1] <= ui.to && (ui.cont || !e[4]) && (ui.vol === "" || e[5] === +ui.vol) && e[2].length);
    /* time bins: single years for a short range, else 5 or 10 years */
    const binSize = () => { const r = ui.to - ui.from + 1; return r <= 12 ? 1 : r <= 60 ? 5 : 10; };
    const binOf = (y, b) => Math.floor(y / b) * b;
    const binLabel = (s, b) => (b === 1 ? String(s) : `${s}–${s + b - 1}`);
    const nEntries = (n) => `${num(n)} ${t("entry", null, n)}`;

    function pick(title, list) {
      const shown = list.slice(0, 60);
      $("an-pick").innerHTML = `<div class="an-picked"><h3>${esc(title)} <span class="muted small">${nEntries(list.length)}</span>
        <button type="button" class="linkish" id="an-unpick">${esc(t("an.close"))}</button></h3>
        <ul>${shown.map((e) => `<li><a href="#/e/${encodeURIComponent(e[0])}/1">${esc(e[6] || e[0])}</a> <span class="muted small">${e[1] || ""} · ${esc(D.volumes[e[5]])}</span></li>`).join("")}</ul>
        ${list.length > shown.length ? `<p class="small muted">${esc(t("an.more", { n: num(list.length - shown.length) }))}</p>` : ""}</div>`;
      $("an-unpick").addEventListener("click", () => { $("an-pick").innerHTML = ""; });
      $("an-pick").scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    /* ---------- Sankey: period -> offence -> (offence named with it | sanction) ---------- */
    function sankey(es) {
      const el = $("an-sankey");
      el.innerHTML = "";
      $("an-pick").innerHTML = "";
      const b = binSize();
      $("an-sankey-note").textContent = t(ui.right === "co" ? "an.sankey.note.co" : "an.sankey.note.san");
      if (!es.length) { el.innerHTML = `<p class="empty">${esc(t("an.none"))}</p>`; return; }
      const nodes = [], idx = new Map(), links = new Map();
      const node = (key, label, color, col) => { if (!idx.has(key)) { idx.set(key, nodes.length); nodes.push({ key, label, color, col, es: new Set() }); } return idx.get(key); };
      const link = (a, bb, e, color) => { const k = a + ">" + bb; if (!links.has(k)) links.set(k, { source: a, target: bb, value: 0, color, es: [] }); const l = links.get(k); l.value += 1; l.es.push(e); };
      for (const e of es) {
        const s = binOf(e[1], b);
        const tn = node("t" + s, binLabel(s, b), NEUTRAL, 0);
        nodes[tn].es.add(e);
        for (const o of e[2]) {
          const on = node("o" + o, D.offences[o].label, hue(o), 1);
          nodes[on].es.add(e);
          link(tn, on, e, NEUTRAL);
          const targets = ui.right === "co"
            ? (e[2].length > 1 ? e[2].filter((x) => x !== o).map((x) => ["c" + x, D.offences[x].label, hue(x)]) : [["c-", t("an.alone"), NEUTRAL]])
            : (e[3].length ? e[3].map((x) => ["s" + x, D.sanctions[x].label, NEUTRAL]) : [["s-", t("an.nosanction"), NEUTRAL]]);
          for (const [k, label, color] of targets) {
            const rn = node(k, label, color, 2);
            nodes[rn].es.add(e);
            link(on, rn, e, hue(o));
          }
        }
      }
      const W = Math.max(760, el.clientWidth || 900);
      const rowsMax = Math.max(...[0, 1, 2].map((c) => nodes.filter((n) => n.col === c).length));
      const H = Math.max(360, Math.min(1400, rowsMax * 26 + 40));
      const layout = d3.sankey().nodeId((d) => d.index).nodeAlign((n) => n.col).nodeSort((a, bb) => (a.col === 0 ? d3.ascending(a.key, bb.key) : d3.descending(a.value, bb.value)))
        .nodeWidth(12).nodePadding(10).extent([[150, 24], [W - 220, H - 8]]);
      const g = layout({ nodes: nodes.map((n, i) => ({ ...n, index: i })), links: [...links.values()].map((l) => ({ ...l })) });
      const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H).attr("role", "img").attr("aria-label", t("an.sankey.h2"));
      const heads = [t("an.col.time"), t("an.col.off"), t(ui.right === "co" ? "an.col.co" : "an.col.san")];
      [150, null, W - 220].forEach((x, i) => {
        const nx = i === 1 ? (g.nodes.find((n) => n.col === 1) || { x0: W / 2 }).x0 : x;
        svg.append("text").attr("class", "colhead").attr("x", i === 2 ? nx : nx + (i === 0 ? 12 : 0)).attr("y", 14).attr("text-anchor", i === 0 ? "end" : "start").text(heads[i]);
      });
      const lk = svg.append("g").attr("fill", "none").selectAll("path").data(g.links).join("path")
        .attr("class", "slink").attr("d", d3.sankeyLinkHorizontal()).attr("stroke", (d) => d.color).attr("stroke-width", (d) => Math.max(1, d.width))
        .on("mousemove", (ev, d) => showTip(ev, `<b>${esc(d.source.label)} → ${esc(d.target.label)}</b><div>${nEntries(d.value)}</div>`))
        .on("mouseleave", () => { hideTip(); lk.classed("dim", false); })
        .on("mouseenter", (ev, d) => lk.classed("dim", (x) => x !== d))
        .on("click", (ev, d) => pick(`${d.source.label} → ${d.target.label}`, d.es));
      const nd = svg.append("g").selectAll("g").data(g.nodes).join("g").attr("class", "snode");
      nd.append("rect").attr("x", (d) => d.x0).attr("y", (d) => d.y0).attr("width", (d) => d.x1 - d.x0).attr("height", (d) => Math.max(1, d.y1 - d.y0)).attr("rx", 2).attr("fill", (d) => d.color)
        .on("mousemove", (ev, d) => showTip(ev, `<b>${esc(d.label)}</b><div>${nEntries(d.es.size)}</div>`))
        .on("mouseenter", (ev, d) => lk.classed("dim", (x) => x.source !== d && x.target !== d))
        .on("mouseleave", () => { hideTip(); lk.classed("dim", false); })
        .on("click", (ev, d) => pick(d.label, [...d.es]));
      nd.append("text").attr("x", (d) => (d.col === 0 ? d.x0 - 6 : d.x1 + 6)).attr("y", (d) => (d.y0 + d.y1) / 2).attr("dy", "0.35em")
        .attr("text-anchor", (d) => (d.col === 0 ? "end" : "start")).text((d) => `${d.label} · ${num(d.es.size)}`);
    }

    /* ---------- offences over time: stacked by group ---------- */
    function timeChart(es) {
      const el = $("an-time");
      el.innerHTML = "";
      if (!es.length) { el.innerHTML = `<p class="empty">${esc(t("an.none"))}</p>`; $("an-time-table").innerHTML = ""; return; }
      const b = binSize();
      const bins = d3.range(binOf(ui.from, b), ui.to + 1, b);
      const table = bins.map((s) => ({ s, tot: 0, n: 0, g: GROUPS.map(() => 0) }));
      const at = new Map(table.map((r) => [r.s, r]));
      for (const e of es) {
        const r = at.get(binOf(e[1], b));
        if (!r) continue;
        r.n += 1;
        for (const o of e[2]) { r.g[gi(D.offences[o].group)] += 1; r.tot += 1; }
      }
      const W = Math.max(760, el.clientWidth || 900), H = 300, m = { l: 44, r: 12, t: 10, b: 40 };
      const x = d3.scaleBand().domain(bins).range([m.l, W - m.r]).paddingInner(0.25).paddingOuter(0.1);
      const y = d3.scaleLinear().domain([0, d3.max(table, (r) => r.tot) || 1]).nice().range([H - m.b, m.t]);
      const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H).attr("role", "img").attr("aria-label", t("an.time.h2"));
      svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(5)).join("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", (d) => y(d)).attr("y2", (d) => y(d));
      svg.append("g").attr("class", "axis").selectAll("text").data(y.ticks(5)).join("text").attr("x", m.l - 6).attr("y", (d) => y(d)).attr("dy", "0.32em").attr("text-anchor", "end").text((d) => num(d));
      const every = Math.ceil(bins.length / Math.max(1, Math.floor((W - m.l - m.r) / (b === 1 ? 44 : 78))));
      svg.append("g").attr("class", "axis").selectAll("text").data(bins.filter((_, i) => i % every === 0)).join("text")
        .attr("x", (d) => x(d) + x.bandwidth() / 2).attr("y", H - m.b + 16).attr("text-anchor", "middle").text((d) => binLabel(d, b));
      svg.append("line").attr("class", "base").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(0)).attr("y2", y(0));
      const col = svg.append("g").selectAll("g").data(table).join("g");
      col.each(function (r) {
        let acc = 0;
        const gsel = d3.select(this);
        r.g.forEach((v, i) => {
          if (!v) return;
          const y1 = y(acc + v), y0 = y(acc);
          gsel.append("rect").attr("x", x(r.s)).attr("width", x.bandwidth()).attr("y", y1 + 1).attr("height", Math.max(0, y0 - y1 - 2)).attr("fill", HUES[i]).attr("rx", 2);
          acc += v;
        });
        gsel.append("rect").attr("class", "hit").attr("x", x(r.s) - 2).attr("width", x.bandwidth() + 4).attr("y", m.t).attr("height", H - m.b - m.t)
          .on("mousemove", (ev) => showTip(ev, `<b>${esc(binLabel(r.s, b))}</b><div>${nEntries(r.n)} · ${num(r.tot)} ${esc(t("an.mentions"))}</div>` +
            r.g.map((v, i) => (v ? `<div><i class="sw" style="background:${HUES[i]}"></i>${esc(GROUPS[i])}: ${num(v)}</div>` : "")).join("")))
          .on("mouseleave", hideTip)
          .on("click", () => pick(binLabel(r.s, b), es.filter((e) => binOf(e[1], b) === r.s)));
      });
      $("an-time-table").innerHTML = `<table class="scores"><thead><tr><th>${esc(t("an.col.time"))}</th><th>${esc(t("entry.other"))}</th>${GROUPS.map((g) => `<th>${esc(g)}</th>`).join("")}</tr></thead>
        <tbody>${table.map((r) => `<tr><td>${esc(binLabel(r.s, b))}</td><td class="n">${num(r.n)}</td>${r.g.map((v) => `<td class="n">${num(v)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }

    /* ---------- how often each offence is recorded ---------- */
    function countChart(es) {
      const el = $("an-count");
      el.innerHTML = "";
      const counts = D.offences.map((o, i) => ({ i, label: o.label, group: o.group, n: 0, es: [] }));
      for (const e of es) for (const o of e[2]) { counts[o].n += 1; counts[o].es.push(e); }
      const list = counts.filter((c) => c.n).sort((a, b) => b.n - a.n);
      if (!list.length) { el.innerHTML = `<p class="empty">${esc(t("an.none"))}</p>`; $("an-count-table").innerHTML = ""; return; }
      const W = Math.max(520, Math.min(900, el.clientWidth || 800)), rh = 24, m = { l: 230, r: 56, t: 4, b: 4 };
      const H = list.length * rh + m.t + m.b;
      const x = d3.scaleLinear().domain([0, list[0].n]).range([m.l, W - m.r]);
      const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("width", W).attr("height", H).attr("role", "img").attr("aria-label", t("an.count.h2"));
      const row = svg.selectAll("g").data(list).join("g").attr("transform", (d, i) => `translate(0,${m.t + i * rh})`);
      row.append("text").attr("class", "blabel").attr("x", m.l - 8).attr("y", rh / 2).attr("dy", "0.35em").attr("text-anchor", "end").text((d) => d.label);
      row.append("rect").attr("x", m.l).attr("y", 5).attr("height", rh - 10).attr("width", (d) => Math.max(2, x(d.n) - m.l)).attr("rx", 3).attr("fill", (d) => HUES[gi(d.group)]);
      row.append("text").attr("class", "bval").attr("x", (d) => x(d.n) + 6).attr("y", rh / 2).attr("dy", "0.35em").text((d) => num(d.n));
      row.append("rect").attr("class", "hit").attr("x", 0).attr("y", 0).attr("width", W).attr("height", rh)
        .on("mousemove", (ev, d) => showTip(ev, `<b>${esc(d.label)}</b><div>${esc(d.group)}</div><div>${nEntries(d.n)} (${(100 * d.n / es.length).toLocaleString(t("locale"), { maximumFractionDigits: 1 })} %)</div>`))
        .on("mouseleave", hideTip)
        .on("click", (ev, d) => pick(d.label, d.es));
      $("an-count-table").innerHTML = `<table class="scores"><thead><tr><th>${esc(t("an.col.off"))}</th><th>${esc(t("an.group"))}</th><th>${esc(t("entry.other"))}</th></tr></thead>
        <tbody>${list.map((d) => `<tr><td>${esc(d.label)}</td><td>${esc(d.group)}</td><td class="n">${num(d.n)}</td></tr>`).join("")}</tbody></table>`;
    }

    function draw() {
      const es = rows();
      const undated = D.entries.filter((e) => !e[1]).length;
      $("an-n").textContent = t("an.n", { n: num(es.length), undated: num(undated) });
      sankey(es); timeChart(es); countChart(es);
    }
    const clamp = (v, d) => (Number.isFinite(+v) && v !== "" ? Math.min(yMax, Math.max(yMin, +v)) : d);
    $("an-from").addEventListener("change", () => { ui.from = clamp($("an-from").value, yMin); if (ui.from > ui.to) ui.to = ui.from; $("an-from").value = ui.from; $("an-to").value = ui.to; draw(); });
    $("an-to").addEventListener("change", () => { ui.to = clamp($("an-to").value, yMax); if (ui.to < ui.from) ui.from = ui.to; $("an-from").value = ui.from; $("an-to").value = ui.to; draw(); });
    $("an-vol").addEventListener("change", () => { ui.vol = $("an-vol").value; draw(); });
    $("an-cont").addEventListener("change", () => { ui.cont = $("an-cont").checked; store.set("an.cont", ui.cont); draw(); });
    $("an-right").addEventListener("change", () => { ui.right = $("an-right").value; store.set("an.right", ui.right); draw(); });
    draw();
  }

  return { show };
})();
