/* Berner Turmbücher — Karte: where the accused came from, and the places the entries name.
   Loaded by app.js on #/karte. Data: data/map.json (places with coordinates from
   swisstopo, and per entry the places it names / its accused are from) joined with
   data/analysis.json (year, offences, title). Leaflet on swisstopo's grey map.
   Names were read and linked by machines; only places in Switzerland are found. */
window.TBMap = (() => {
  "use strict";
  const CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";
  const JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
  const TILES = "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-grau/default/current/3857/{z}/{x}/{y}.jpeg";
  const MARK = "#2a78d6";
  let libs = null, data = null, map = null;

  function loadLibs() {
    if (!libs) libs = new Promise((ok, no) => {
      const l = document.createElement("link"); l.rel = "stylesheet"; l.href = CSS; document.head.appendChild(l);
      const s = document.createElement("script"); s.src = JS; s.onload = ok; s.onerror = () => no(new Error(JS)); document.head.appendChild(s);
    });
    return libs;
  }

  async function show(app, ctx) {
    const { t, esc, num, json, store } = ctx;
    if (map) { map.remove(); map = null; }
    app.innerHTML = `<p class="loading">${esc(t("loading"))}</p>`;
    let A, M;
    try {
      if (!data) data = Promise.all([json("data/analysis.json"), json("data/map.json")]);
      [A, M] = await data;
      await loadLibs();
    } catch (e) { app.innerHTML = `<p>${esc(t("error.load"))}: ${esc(e.message)}</p>`; return; }
    const entry = new Map(A.entries.map((e) => [e[0], e]));
    const rows = M.entries.map(([id, named, origin]) => ({ e: entry.get(id), named, origin })).filter((r) => r.e);
    const years = rows.map((r) => r.e[1]).filter(Boolean);
    const yMin = Math.min(...years), yMax = Math.max(...years);
    const ui = { which: store.get("map.which", "origin"), from: yMin, to: yMax, off: "" };

    app.innerHTML = `
      <section class="intro">
        <h1>${esc(t("map.h1"))} <span class="badge proto">${esc(t("proto"))}</span></h1>
        <p>${esc(t("map.intro", { places: num(M.places.length), entries: num(rows.length) }))}</p>
        <p class="caveat">${esc(t("map.caveat"))}</p>
      </section>
      <div class="anbar" role="group" aria-label="${esc(t("an.filters"))}">
        <label>${esc(t("map.which"))} <select id="mp-which">
          <option value="origin" ${ui.which === "origin" ? "selected" : ""}>${esc(t("map.which.origin"))}</option>
          <option value="named" ${ui.which === "named" ? "selected" : ""}>${esc(t("map.which.named"))}</option></select></label>
        <label>${esc(t("an.from"))} <input type="number" id="mp-from" min="${yMin}" max="${yMax}" value="${yMin}"></label>
        <label>${esc(t("an.to"))} <input type="number" id="mp-to" min="${yMin}" max="${yMax}" value="${yMax}"></label>
        <label>${esc(t("an.col.off"))} <select id="mp-off"><option value="">${esc(t("map.alloff"))}</option>${A.offences.map((o, i) => `<option value="${i}">${esc(o.label)}</option>`).join("")}</select></label>
        <span id="mp-n" class="muted small"></span>
      </div>
      <div id="mp-map" class="tbmap" role="application" aria-label="${esc(t("map.h1"))}"></div>
      <p class="small muted">${esc(t("map.size"))}</p>
      <div id="mp-pick"></div>
      <details class="tableview" open><summary>${esc(t("map.table"))}</summary><div class="scroll" id="mp-table"></div></details>
      <details class="tableview"><summary>${esc(t("map.unlinked", { n: num(M.unlinked.length) }))}</summary>
        <p class="small muted">${esc(t("map.unlinked.note"))}</p>
        <p class="small">${M.unlinked.map(([k, v]) => `${esc(k)} <span class="muted">${num(v)}</span>`).join(" · ")}</p></details>`;

    const $ = (id) => document.getElementById(id);
    map = L.map("mp-map", { scrollWheelZoom: false, minZoom: 7, maxZoom: 14 }).setView([46.95, 7.55], 9);
    L.tileLayer(TILES, { attribution: '© <a href="https://www.swisstopo.admin.ch/" target="_blank" rel="noopener">swisstopo</a>', maxZoom: 14 }).addTo(map);
    map.on("click", () => map.scrollWheelZoom.enable());
    const layer = L.layerGroup().addTo(map);

    function pick(p, es) {
      const shown = es.slice(0, 80);
      $("mp-pick").innerHTML = `<div class="an-picked"><h3>${esc(p.name)}${p.canton ? ` (${esc(p.canton)})` : ""} <span class="muted small">${num(es.length)} ${esc(t("entry", null, es.length))}</span>
        <button type="button" class="linkish" id="mp-unpick">${esc(t("an.close"))}</button></h3>
        <p class="small muted">${esc(t("map.place.meta", { rule: p.rule, names: Object.keys(p.names).slice(0, 8).join(", ") }))}</p>
        <ul>${shown.map((e) => `<li><a href="#/e/${encodeURIComponent(e[0])}/1">${esc(e[6] || e[0])}</a> <span class="muted small">${e[1] || ""} · ${esc(A.volumes[e[5]])}</span></li>`).join("")}</ul>
        ${es.length > shown.length ? `<p class="small muted">${esc(t("an.more", { n: num(es.length - shown.length) }))}</p>` : ""}</div>`;
      $("mp-unpick").addEventListener("click", () => { $("mp-pick").innerHTML = ""; });
      $("mp-pick").scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function draw() {
      layer.clearLayers();
      $("mp-pick").innerHTML = "";
      const at = new Map();   // place index -> entries
      let n = 0;
      for (const r of rows) {
        const e = r.e;
        if (!e[1] || e[1] < ui.from || e[1] > ui.to) continue;
        if (ui.off !== "" && !e[2].includes(+ui.off)) continue;
        const ps = r[ui.which];
        if (!ps.length) continue;
        n += 1;
        for (const i of ps) { if (!at.has(i)) at.set(i, []); at.get(i).push(e); }
      }
      const list = [...at.entries()].map(([i, es]) => ({ p: M.places[i], es })).sort((a, b) => b.es.length - a.es.length);
      const max = list.length ? list[0].es.length : 1;
      const radius = (v) => 4 + 24 * Math.sqrt(v / max);
      // large circles first, so that small ones stay on top and can be pointed at
      for (const { p, es } of list) {
        const m = L.circleMarker([p.lat, p.lon], { radius: radius(es.length), color: "#fcfcfb", weight: 2, fillColor: MARK, fillOpacity: 0.55 });
        m.bindTooltip(`<b>${esc(p.name)}</b>${p.canton ? ` (${esc(p.canton)})` : ""}<br>${num(es.length)} ${esc(t("entry", null, es.length))}`, { direction: "top" });
        m.on("click", (ev) => { L.DomEvent.stopPropagation(ev); pick(p, es); });
        m.addTo(layer);
      }
      $("mp-n").textContent = t("map.n", { n: num(n), places: num(list.length) });
      $("mp-table").innerHTML = list.length ? `<table class="scores"><thead><tr><th>${esc(t("map.col.place"))}</th><th>${esc(t("entry.other"))}</th><th>${esc(t("map.col.rule"))}</th><th>${esc(t("map.col.names"))}</th></tr></thead>
        <tbody>${list.slice(0, 40).map(({ p, es }, k) => `<tr><td><button type="button" class="linkish" data-k="${k}">${esc(p.name)}${p.canton ? ` (${esc(p.canton)})` : ""}</button></td><td class="n">${num(es.length)}</td><td class="small">${esc(p.rule)}${p.alias ? " · " + esc(t("map.alias")) : ""}</td><td class="small muted">${esc(Object.keys(p.names).slice(0, 6).join(", "))}</td></tr>`).join("")}</tbody></table>
        ${list.length > 40 ? `<p class="small muted">${esc(t("an.more", { n: num(list.length - 40) }))}</p>` : ""}` : `<p class="empty">${esc(t("an.none"))}</p>`;
      $("mp-table").querySelectorAll("button[data-k]").forEach((b) => b.addEventListener("click", () => {
        const { p, es } = list[+b.dataset.k];
        map.setView([p.lat, p.lon], Math.max(map.getZoom(), 11));
        pick(p, es);
      }));
    }
    const clamp = (v, d) => (Number.isFinite(+v) && v !== "" ? Math.min(yMax, Math.max(yMin, +v)) : d);
    $("mp-which").addEventListener("change", () => { ui.which = $("mp-which").value; store.set("map.which", ui.which); draw(); });
    $("mp-from").addEventListener("change", () => { ui.from = clamp($("mp-from").value, yMin); if (ui.from > ui.to) ui.to = ui.from; $("mp-from").value = ui.from; $("mp-to").value = ui.to; draw(); });
    $("mp-to").addEventListener("change", () => { ui.to = clamp($("mp-to").value, yMax); if (ui.to < ui.from) ui.from = ui.to; $("mp-from").value = ui.from; $("mp-to").value = ui.to; draw(); });
    $("mp-off").addEventListener("change", () => { ui.off = $("mp-off").value; draw(); });
    draw();
  }

  function leave() { if (map) { map.remove(); map = null; } }
  return { show, leave };
})();
