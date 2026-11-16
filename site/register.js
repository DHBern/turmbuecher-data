/* Berner Turmbücher — Register: persons, places, offences, with links to authority files.
   Loaded by app.js on #/register[/personen|orte|delikte]. Data:
   data/register_personen.json (scripts/register.py: name forms, HLS proposals),
   data/map.json (places with their links), data/analysis.json (offences, entry titles).
   A person entry is a name form, not an identified person; every link is a proposal. */
window.TBRegister = (() => {
  "use strict";
  let persons = null, base = null;
  const HLS = (id) => `https://hls-dhs-dss.ch/de/articles/${encodeURIComponent(id)}/`;
  const WD = (q) => `https://www.wikidata.org/wiki/${encodeURIComponent(q)}`;
  const GND = (id) => `https://d-nb.info/gnd/${encodeURIComponent(id)}`;
  const GEON = (id) => `https://www.geonames.org/${encodeURIComponent(id)}`;
  const ext = (href, label) => `<a href="${href}" target="_blank" rel="noopener">${label}</a>`;

  async function show(app, ctx, tab) {
    const { t, esc, num, json, store } = ctx;
    tab = ["personen", "orte", "delikte"].includes(tab) ? tab : "personen";
    app.innerHTML = `<p class="loading">${esc(t("loading"))}</p>`;
    let A, M, P;
    try {
      if (!base) base = Promise.all([json("data/analysis.json"), json("data/map.json")]);
      [A, M] = await base;
      if (tab === "personen") { if (!persons) persons = json("data/register_personen.json"); P = (await persons).persons; }
    } catch (e) { app.innerHTML = `<p>${esc(t("error.load"))}: ${esc(e.message)}</p>`; return; }
    const entry = new Map(A.entries.map((e) => [e[0], e]));
    const entryLink = (id) => { const e = entry.get(id); return `<li><a href="#/e/${encodeURIComponent(id)}/1">${esc((e && e[6]) || id)}</a>${e ? ` <span class="muted small">${e[1] || ""} · ${esc(A.volumes[e[5]])}</span>` : ""}</li>`; };

    app.innerHTML = `
      <section class="intro">
        <h1>${esc(t("reg.h1"))} <span class="badge proto">${esc(t("proto"))}</span></h1>
        <nav class="regtabs" aria-label="${esc(t("reg.h1"))}">${["personen", "orte", "delikte"].map((k) => `<a href="#/register/${k}" class="${k === tab ? "on" : ""}" ${k === tab ? 'aria-current="page"' : ""}>${esc(t("reg.tab." + k))}</a>`).join("")}</nav>
        <p>${esc(t("reg.intro." + tab))}</p>
        <p class="caveat">${esc(t("reg.caveat." + tab))}</p>
      </section>
      <div id="rg"></div>`;
    const box = document.getElementById("rg");

    if (tab === "personen") {
      const ui = { q: "", linked: store.get("reg.linked", false), multi: store.get("reg.multi", true), shown: 100 };
      const linkedN = P.filter((r) => r.hls).length;
      box.innerHTML = `
        <div class="anbar">
          <input id="rg-q" type="search" placeholder="${esc(t("reg.p.filter"))}" aria-label="${esc(t("reg.p.filter"))}">
          <label><input type="checkbox" id="rg-multi" ${ui.multi ? "checked" : ""}> ${esc(t("reg.p.multi"))}</label>
          <label><input type="checkbox" id="rg-linked" ${ui.linked ? "checked" : ""}> ${esc(t("reg.p.linked", { n: num(linkedN) }))}</label>
          <span id="rg-n" class="muted small"></span>
        </div>
        <div id="rg-list" class="reglist"></div>`;
      const plain = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
      const hay = new Map();
      const roleText = (roles) => Object.entries(roles).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${esc(t("reg.role." + k))} ${num(v)}`).join(", ");
      const proposal = (h) => `<div class="prop ${h.grade === "wahrscheinlich" ? "likely" : ""}">
          <span class="badge ${h.grade === "wahrscheinlich" ? "st-GT" : "st-NEW"}">${esc(t("reg.grade." + (h.grade === "wahrscheinlich" ? "likely" : "possible")))}</span>
          <b>${esc(h.name)}</b> <span class="muted">(${h.b ?? "?"}–${h.d ?? "?"})</span> ${h.desc ? `<span class="small muted">${esc(h.desc.slice(0, 110))}</span>` : ""}
          <span class="small">${ext(HLS(h.hls), "HLS")} · ${ext(WD(h.qid), "Wikidata")}${h.gnd ? " · " + ext(GND(h.gnd), "GND") : ""}${h.ssrq ? ` · SSRQ ${esc(h.ssrq.id)}` : ""}${h.kf ? ` · ${esc(t("reg.kf"))} ${esc(h.kf.id)}` : ""}</span>
          <span class="small muted">${esc(t("reg.p.inentries", { n: num(h.entries.length) }))}</span></div>`;
      const row = (r, i) => `<details class="regrow" data-i="${i}">
          <summary><span class="rn">${esc(r.name)}</span> <span class="muted small">${num(r.n)} ${esc(t("entry", null, r.n))}${r.years ? ` · ${r.years[0] === r.years[1] ? r.years[0] : r.years[0] + "–" + r.years[1]}` : ""}${r.from.length ? " · " + esc(r.from.join(", ")) : ""}</span>
            ${r.hls ? `<span class="badge ${r.hls.some((h) => h.grade === "wahrscheinlich") ? "st-GT" : "st-NEW"}">HLS?</span>` : ""}</summary>
          <div class="regbody"></div></details>`;
      let rows = [];
      const draw = () => {
        const words = plain(ui.q).split(/\s+/).filter(Boolean);
        rows = P.filter((r) => {
          if (ui.linked && !r.hls) return false;
          if (ui.multi && r.n < 2 && !words.length && !ui.linked) return false;
          if (!words.length) return true;
          if (!hay.has(r)) hay.set(r, plain([r.name, ...r.forms, ...r.from].join(" ")));
          return words.every((w) => hay.get(r).includes(w));
        });
        document.getElementById("rg-n").textContent = t("reg.p.n", { n: num(rows.length), all: num(P.length) });
        document.getElementById("rg-list").innerHTML = rows.slice(0, ui.shown).map(row).join("") +
          (rows.length > ui.shown ? `<button type="button" class="linkish" id="rg-more">${esc(t("search.more", { n: Math.min(100, rows.length - ui.shown), rest: rows.length - ui.shown }))}</button>` : "") +
          (!rows.length ? `<p class="empty">${esc(t("list.none"))}</p>` : "");
        const more = document.getElementById("rg-more");
        more && more.addEventListener("click", () => { ui.shown += 100; draw(); });
      };
      document.getElementById("rg-list").addEventListener("toggle", (ev) => {
        const d = ev.target.closest("details.regrow");
        if (!d || !d.open) return;
        const body = d.querySelector(".regbody");
        if (body.children.length) return;
        const r = rows[+d.dataset.i];
        body.innerHTML = `
          <p class="small">${esc(t("reg.p.forms"))}: ${r.forms.map(esc).join(" · ")}</p>
          <p class="small">${esc(t("reg.p.roles"))}: ${roleText(r.roles)}</p>
          ${r.hls ? `<div class="props"><p class="small muted">${esc(t("reg.p.props"))}</p>${r.hls.map(proposal).join("")}</div>` : ""}
          <ul>${r.entries.slice(0, 60).map(entryLink).join("")}</ul>
          ${r.n > 60 ? `<p class="small muted">${esc(t("an.more", { n: num(r.n - 60) }))}</p>` : ""}`;
      }, true);
      let timer = null;
      document.getElementById("rg-q").addEventListener("input", (ev) => { ui.q = ev.target.value; ui.shown = 100; clearTimeout(timer); timer = setTimeout(draw, 200); });
      document.getElementById("rg-multi").addEventListener("change", (ev) => { ui.multi = ev.target.checked; store.set("reg.multi", ui.multi); ui.shown = 100; draw(); });
      document.getElementById("rg-linked").addEventListener("change", (ev) => { ui.linked = ev.target.checked; store.set("reg.linked", ui.linked); ui.shown = 100; draw(); });
      draw();
      return;
    }

    if (tab === "orte") {
      const count = M.places.map(() => [0, 0]);
      for (const [, named, origin] of M.entries) { for (const i of named) count[i][0] += 1; for (const i of origin) count[i][1] += 1; }
      const list = M.places.map((p, i) => ({ p, named: count[i][0], origin: count[i][1] })).sort((a, b) => a.p.name.localeCompare(b.p.name, "de"));
      const linked = list.filter((x) => x.p.links).length;
      box.innerHTML = `
        <div class="anbar"><input id="rg-q" type="search" placeholder="${esc(t("reg.o.filter"))}" aria-label="${esc(t("reg.o.filter"))}">
          <span class="muted small">${esc(t("reg.o.n", { n: num(list.length), linked: num(linked) }))}</span> <a class="small" href="#/karte">${esc(t("reg.o.map"))}</a></div>
        <div class="scroll"><table class="scores"><thead><tr><th>${esc(t("map.col.place"))}</th><th>${esc(t("reg.o.named"))}</th><th>${esc(t("reg.o.origin"))}</th><th>${esc(t("reg.o.links"))}</th><th>${esc(t("map.col.rule"))}</th><th>${esc(t("map.col.names"))}</th></tr></thead>
        <tbody id="rg-body"></tbody></table></div>`;
      const draw = (q) => {
        const w = q.toLowerCase();
        document.getElementById("rg-body").innerHTML = list.filter((x) => !w || (x.p.name + " " + Object.keys(x.p.names).join(" ")).toLowerCase().includes(w)).map(({ p, named, origin }) => {
          const l = p.links || {};
          const links = [l.hls && ext(HLS(l.hls), "HLS"), l.qid && ext(WD(l.qid), "Wikidata"), l.gnd && ext(GND(l.gnd), "GND"), l.geonames && ext(GEON(l.geonames), "GeoNames")].filter(Boolean).join(" · ");
          return `<tr><td><b>${esc(p.name)}</b>${p.canton ? ` (${esc(p.canton)})` : ""}</td><td class="n">${num(named)}</td><td class="n">${num(origin)}</td><td class="small">${links || `<span class="muted">${esc(t("reg.o.nolink"))}</span>`}</td>
            <td class="small">${esc(p.rule)}${p.alias ? " · " + esc(t("map.alias")) : ""}</td><td class="small muted">${esc(Object.keys(p.names).slice(0, 6).join(", "))}</td></tr>`;
        }).join("");
      };
      document.getElementById("rg-q").addEventListener("input", (ev) => draw(ev.target.value));
      draw("");
      return;
    }

    /* offences */
    const counts = A.offences.map(() => 0);
    for (const e of A.entries) for (const o of e[2]) counts[o] += 1;
    const colour = Object.fromEntries(A.groups.map((g) => [g.id, g.farbe || "#898781"]));
    box.innerHTML = `<p class="small"><a href="#/auswertung">${esc(t("reg.d.analysis"))}</a></p>` + A.groups.map((g) => {
      const os = A.offences.map((o, i) => ({ o, i, n: counts[i] })).filter((x) => x.o.group === g.id).sort((a, b) => b.n - a.n);
      if (!os.length) return "";
      return `<section class="an-card"><h2><i class="sw" style="background:${colour[g.id]}"></i>${esc(g.id)} <span class="muted small">${num(os.reduce((a, x) => a + x.n, 0))} ${esc(t("an.mentions"))}</span></h2>
        <table class="scores"><tbody>${os.map(({ o, n }) => `<tr><td><a href="#/search?of=${encodeURIComponent(o.id)}"><b>${esc(o.label)}</b></a></td><td class="n">${num(n)}</td><td class="small muted">${esc(o.hint || "")}</td></tr>`).join("")}</tbody></table></section>`;
    }).join("");
  }

  return { show };
})();
