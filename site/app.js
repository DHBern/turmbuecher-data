/* Berner Turmbücher — viewer. No build step, no framework.
   Derived from the St. Gallen and Thun Missives viewers (DHBern/sg-missiven-data,
   DHBern/thun-missiven-data). The unit is a row of the index (data/index.json):
   a page while the entries are not segmented yet (index.by_page), an entry later.
   Every visible string comes from i18n/<lang>.json (t("key")); config.json names
   the languages and whether the page images are shown. */
(() => {
  "use strict";
  const app = document.getElementById("app");
  const state = { index: null, readers: null, chunks: new Map(), filter: "", osd: null, pagekeys: null, cfg: null };
  const store = {
    get(k, d) { try { const v = localStorage.getItem("tb:" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("tb:" + k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  state.reader = store.get("reader", "");
  state.mode = store.get("mode", "plain");

  /* ---------- language ---------- */
  let LANG = "de", STR = {}, BASE = {};
  /* t("key", {name: …}): the string in the current language, else the first
     language's, else the key. t("page", {}, n) picks key.one / key.other. */
  function t(key, vars, n) {
    if (n !== undefined) key += n === 1 ? ".one" : ".other";
    let s = STR[key] ?? BASE[key] ?? key;
    if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    return s;
  }
  const loc = (r, k) => r[k + "_" + LANG] || r[k] || "";
  const num = (n) => Number(n).toLocaleString(t("locale"));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => (x == null ? "–" : (x * 100).toLocaleString(t("locale"), { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %");
  const json = (p) => fetch(p).then((r) => { if (!r.ok) throw new Error(p + ": " + r.status); return r.json(); });

  async function loadLang(l) {
    STR = l === state.cfg.langs[0] ? BASE : await json(`i18n/${l}.json`);
    LANG = l;
  }
  function applyLang() {
    document.documentElement.lang = LANG;
    document.title = t("site.doctitle");
    document.querySelectorAll("[data-nav]").forEach((a) => { a.textContent = t("nav." + a.dataset.nav); });
    const brand = document.querySelector(".brand");
    if (brand) brand.innerHTML = `${esc(t("site.title"))} <span>· ${esc(t("site.sub"))}</span>`;
    const box = document.querySelector(".lang");
    if (box) {
      box.hidden = state.cfg.langs.length < 2;
      box.innerHTML = state.cfg.langs.map((l) => `<button type="button" data-lang="${esc(l)}" class="${l === LANG ? "on" : ""}" aria-pressed="${l === LANG}">${esc(l.toUpperCase())}</button>`).join("");
    }
  }
  async function setLang(l) {
    await loadLang(l);
    store.set("lang", l);
    const u = new URL(location.href);
    u.searchParams.set("lang", l);
    history.replaceState(null, "", u);
    applyLang();
    destroyOsd();
    route();
  }

  /* ---------- names ---------- */
  /* a unit is an entry, or (u.p) a page of a volume not yet cut into entries */
  const unitWord = (n) => t("unit", null, n);
  const titleOf = (u) => `${u.shelf}, ${t(u.p ? "page.abbr" : "entry.abbr")} ${u.nr}`;
  const readerLabel = (id) => { const r = (state.readers || []).find((x) => x.id === id); return r ? loc(r, "label") : (id || t("draft.areading")); };
  const thumb = (tk) => `${state.cfg.iiif}${encodeURIComponent(tk)}/full/120,/0/default.jpg`;
  const statusBadge = (st) => (st ? `<span class="badge st-${esc(st)}" title="${esc(t(`status.${st}.title`))}">${esc(t("status." + st))}</span>` : "");

  async function boot() {
    state.cfg = await json("config.json");
    BASE = await json(`i18n/${state.cfg.langs[0]}.json`);
    const urlLang = new URLSearchParams(location.search).get("lang");
    const want = state.cfg.langs.includes(urlLang) ? urlLang : store.get("lang", state.cfg.langs[0]);
    await loadLang(state.cfg.langs.includes(want) ? want : state.cfg.langs[0]);
    [state.index, state.readers] = await Promise.all([json("data/index.json"), json("data/readers.json")]);
    state.pos = new Map(state.index.units.map((u, i) => [u.id, i]));
    if (!state.readers.some((r) => r.id === state.reader)) state.reader = state.readers.length ? state.readers[0].id : "";
    window.addEventListener("hashchange", route);
    document.querySelector(".lang").addEventListener("click", (ev) => { const b = ev.target.closest("[data-lang]"); if (b) setLang(b.dataset.lang); });
    document.addEventListener("keydown", pageKeys);
    applyLang();
    route();
  }

  function setNav(which) {
    if (which !== "search") clearTimeout(searchTimer);
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === which));
  }

  function route() {
    hideTip();
    const [path, qs] = location.hash.replace(/^#\/?/, "").split("?");
    const parts = path.split("/").map(decodeURIComponent);
    if (parts[0] !== "e") { destroyOsd(); cur = null; }
    if (parts[0] !== "karte") window.TBMap.leave();
    if (parts[0] === "search") return showSearch(new URLSearchParams(qs || ""));
    if (parts[0] === "e" && parts[1]) return showUnit(parts[1], +(parts[2] || 1), parts[3]);
    if (parts[0] === "page" && parts[1]) return toPageKey(parts[1], parts[2]);
    if (parts[0] === "readers") return showReaders();
    if (parts[0] === "about") return showAbout();
    if (parts[0] === "pruefen") { setNav("about"); return window.TBCheck.show(app, { t, esc, num, json, store }, parts[1], parts[2]); }
    if (parts[0] === "register") { setNav("register"); return window.TBRegister.show(app, { t, esc, num, json, store }, parts[1]); }
    if (parts[0] === "karte") { setNav("map"); return window.TBMap.show(app, { t, esc, num, json, store }); }
    if (parts[0] === "auswertung") { setNav("analysis"); return window.TBAnalysis.show(app, { t, esc, num, json, store }); }
    return showList(parts[0] === "band" ? parts[1] : null);
  }

  async function toPageKey(key, reader) {
    if (!state.pagekeys) state.pagekeys = json("data/pagekeys.json");
    const hit = (await state.pagekeys)[key];
    if (!hit) { app.innerHTML = `<p>${esc(t("unit.none"))} ${esc(key)}. <a href="#/">${esc(t("all"))}</a></p>`; return; }
    location.replace(`#/e/${encodeURIComponent(hit[0])}/${hit[1]}${reader ? "/" + encodeURIComponent(reader) : ""}`);
  }

  /* ---------- list: volumes, their units shown on demand ---------- */
  const draftMark = () => `<span class="badge auto" title="${esc(t("draft.badge.title"))}">${esc(t("draft.badge"))}</span>`;

  function unitRow(u, extra = "", href = `#/e/${encodeURIComponent(u.id)}/1`) {
    return `<div class="row lrow">
      <span class="th">${state.cfg.images && u.tk ? `<img src="${thumb(u.tk)}" alt="" loading="lazy" width="44" height="60">` : ""}</span>
      <span class="num">${esc(t(u.p ? "page.abbr" : "entry.abbr"))} ${esc(u.nr)}</span>
      <span class="body"><a class="who" href="${href}">${esc(titleOf(u))}</a>
        <span class="small muted">${u.e ? esc(t("status.none")) : ""} ${statusBadge(u.st === "IN_PROGRESS" || u.e ? "" : u.st)}${!u.p ? ` ${num(u.n)} ${esc(t("page", null, u.n))}${u.y ? " · " + esc(u.y) : ""}` : ""}</span>
        ${u.h ? `<span class="reg">${esc(u.h)} ${draftMark()}</span>` : ""}${extra}</span>
    </div>`;
  }

  function showList(openVol) {
    setNav("units");
    const units = state.index.units, vols = state.index.volumes;
    const sum = (k) => vols.reduce((a, v) => a + v[k], 0);
    app.innerHTML = `
      <section class="intro">
        <h1>${esc(t("list.h1"))} <span class="badge proto">${esc(t("proto"))}</span></h1>
        <p>${esc(t("list.intro"))}</p>
        <p class="small muted">${esc(t("list.state", { volumes: num(vols.length), pages: num(state.index.pages), text: num(sum("text")), gt: num(sum("gt")), entries: num(units.filter((u) => !u.p).length) }))} ${esc(t("list.caveat"))}</p>
      </section>
      <div class="filters">
        <input id="q" type="search" placeholder="${esc(t("list.filter"))}" value="${esc(state.filter)}" aria-label="${esc(t("list.filter.aria"))}">
        <span id="count" class="muted small"></span>
        <a class="small" href="#/search">${esc(t("list.search"))}</a>
      </div>
      <div id="list"></div>`;
    const q = document.getElementById("q");
    const open = new Set(openVol ? [openVol] : store.get("open", []));
    const draw = () => {
      state.filter = q.value;
      const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
      const rows = words.length ? units.filter((u) => {
        const hay = [u.id, titleOf(u), u.h || "", u.y || ""].join(" ").toLowerCase();
        return words.every((w) => hay.includes(w));
      }) : units;
      document.getElementById("count").textContent = words.length ? `${num(rows.length)} ${unitWord(rows.length)}` : `${num(vols.length)} ${t("volume", null, vols.length)}`;
      document.getElementById("list").innerHTML = vols.map((v) => {
        const us = rows.filter((u) => u.shelf === v.v);
        if (!us.length) return "";
        const isOpen = open.has(v.v) || (words.length && rows.length <= 200);
        return `<details class="vol" data-vol="${esc(v.v)}" ${isOpen ? "open" : ""}>
          <summary><span class="shelf">${esc(v.doc)}</span> <span class="muted small">${esc(t("list.vol.meta", { pages: num(v.pages), text: num(v.text), gt: num(v.gt), entries: num(units.filter((u) => u.shelf === v.v && !u.p).length) }))}</span></summary>
          <div class="list">${isOpen ? us.map((u) => unitRow(u)).join("") : ""}</div></details>`;
      }).join("") || `<p class="empty">${esc(t("list.none"))}</p>`;
    };
    q.addEventListener("input", draw);
    document.getElementById("list").addEventListener("toggle", (ev) => {
      const d = ev.target.closest("details.vol");
      if (!d) return;
      d.open ? open.add(d.dataset.vol) : open.delete(d.dataset.vol);
      store.set("open", [...open]);
      const list = d.querySelector(".list");
      if (d.open && !list.children.length) {
        const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
        list.innerHTML = units.filter((u) => u.shelf === d.dataset.vol && (!words.length ||
          words.every((w) => [u.id, titleOf(u), u.h || "", u.y || ""].join(" ").toLowerCase().includes(w)))).map((u) => unitRow(u)).join("");
      }
    }, true);
    draw();
    if (openVol) { const d = app.querySelector(`details.vol[data-vol="${CSS.escape(openVol)}"]`); d && d.scrollIntoView(); }
  }

  /* ---------- readers ---------- */
  function showReaders() {
    setNav("readers");
    const rs = state.readers;
    const pairs = [];
    rs.forEach((a, i) => rs.slice(i + 1).forEach((b) => { const d = (a.disagreement || {})[b.id]; if (d) pairs.push([a, b, d]); }));
    app.innerHTML = `
      <section class="prose"><h1>${esc(t("readers.h1"))}</h1><p>${esc(t("readers.intro"))}</p></section>
      <div class="scroll"><table class="scores">
        <thead><tr><th>${esc(t("readers.col.reader"))}</th><th>${esc(t("readers.col.kind"))}</th><th>${esc(t("readers.col.pages"))}</th><th>${esc(t("readers.col.about"))}</th></tr></thead>
        <tbody>${rs.map((r) => `
          <tr><td><b>${esc(loc(r, "label"))}</b><div class="muted small"><code>${esc(r.id)}</code></div></td><td>${esc(loc(r, "kind"))}</td>
          <td class="n">${num(r.pages_read || 0)} / ${num(state.index.pages)}</td>
          <td class="small">${esc(loc(r, "about"))}${r.caveat ? `<div class="caveat">${esc(loc(r, "caveat"))}</div>` : ""}</td></tr>`).join("")}
        </tbody></table></div>
      <section class="prose">
        <h2>${esc(t("readers.dis.h2"))}</h2>
        <p class="muted small">${t("readers.dis.p")}</p>
        ${pairs.length ? `<div class="scroll"><table class="scores"><thead><tr><th>${esc(t("readers.col.reader"))}</th><th>${esc(t("readers.col.reader"))}</th><th>${esc(t("readers.dis.col"))}</th><th>${esc(t("readers.dis.both"))}</th></tr></thead>
          <tbody>${pairs.sort((x, y) => x[2].value - y[2].value).map(([a, b, d]) => `<tr><td>${esc(loc(a, "label"))}</td><td>${esc(loc(b, "label"))}</td><td class="n">${pct(d.value)}</td><td class="n">${num(d.pages)}</td></tr>`).join("")}</tbody></table></div>`
          : `<p class="empty">${esc(t("readers.dis.none"))}</p>`}
      </section>`;
  }

  function showAbout() {
    setNav("about");
    app.innerHTML = `<section class="prose">${t("about.html")}</section>`;
  }

  /* ---------- search ----------
     Full text over the units, in one reading. The text is sharded per reader
     (data/search/<reader>/text-N.json: unit id -> its page texts) and loaded,
     in parallel, only once a query is typed. Without a query the facets alone
     select. The whole search lives in the URL. */
  const FACETS = ["vol", "of", "dec", "st", "dr"];
  let TAXO = null;   // offence id -> label, from data/analysis.json
  const texts = new Map();   // reader -> Promise<{unit id: [page texts]}>
  const normed = new Map();  // reader|tol -> Map(unit id -> [normalised page texts])
  let searchTimer = null;

  function searchTexts(reader) {
    if (!texts.has(reader)) {
      const n = state.index.search[reader] || 0;
      texts.set(reader, Promise.all(Array.from({ length: n }, (_, i) => json(`data/search/${encodeURIComponent(reader)}/text-${i}.json`)))
        .then((shards) => Object.assign({}, ...shards)));
    }
    return texts.get(reader);
  }

  /* Normalise for matching, keeping for every output character the position it
     came from (for highlighting). Tolerant: the old spelling's variants count as
     one: u/v/w, i/y/j, ſ/s, doubled letters, ů = uo = u, ä = ae = a, and a word
     broken at the line end. */
  function normText(str, tol) {
    let out = "", map = [], last = " ";
    for (let i = 0; i < str.length; i++) {
      const c = str[i];
      if (tol && (c === "-" || c === "¬" || c === "=") && /^[ \t]*\n/.test(str.slice(i + 1, i + 4))) {
        while (i + 1 < str.length && str[i + 1] !== "\n") i++;
        i++; // the line break: the word continues on the next line
        continue;
      }
      let d = c.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace("ß", "ss").replace("ſ", "s");
      if (tol) d = d.replace(/[vw]/g, "u").replace(/[yj]/g, "i");
      for (let ch of d) {
        if (!/[a-z0-9]/.test(ch)) ch = " ";
        if (ch === " " && last === " ") continue;
        if (tol && ch !== " " && ch === last) continue;
        if (tol && ((ch === "e" && /[aou]/.test(last)) || (ch === "o" && last === "u"))) continue;
        out += ch; map.push(i); last = ch;
      }
    }
    return { s: out, map };
  }

  function parseQuery(q, tol) {
    const terms = [];
    q.replace(/"([^"]+)"|«([^»]+)»|(\S+)/g, (_, ph, ph2, w) => { const x = normText(ph || ph2 || w, tol).s.trim(); if (x) terms.push(x); });
    return terms;
  }

  function snippet(text, terms, tol) {
    const { s, map } = normText(text, tol);
    const spans = [];
    for (const x of terms) { let i = s.indexOf(x); while (i >= 0 && spans.length < 40) { spans.push([map[i], map[i + x.length - 1] + 1]); i = s.indexOf(x, i + x.length); } }
    spans.sort((a, b) => a[0] - b[0]);
    if (!spans.length) return "";
    const a = Math.max(0, spans[0][0] - 70), b = Math.min(text.length, spans[0][1] + 110);
    let out = "", at = a;
    for (const [x, y] of spans) { if (x < at || y > b) continue; out += esc(text.slice(at, x)) + `<mark>${esc(text.slice(x, y))}</mark>`; at = y; }
    out += esc(text.slice(at, b));
    return (a > 0 ? "…" : "") + out.replace(/\n/g, " / ") + (b < text.length ? "…" : "") + (spans.length > 1 ? ` <span class="muted">(${spans.length}×)</span>` : "");
  }

  function facetValue(u, k) {
    if (k === "vol") return u.shelf;
    if (k === "st") return u.e ? "none" : (u.st || "");
    if (k === "dec") return u.y ? String(Math.floor(u.y / 10) * 10) : "";
    if (k === "of") return u.o || [];
    if (k === "dr") return state.hasDrafts ? (u.h ? "yes" : "no") : "";
    return "";
  }
  function facetLabel(k, v) {
    if (k === "st") return t("status." + v);
    if (k === "dec") return t("facet.dec.label", { v });
    if (k === "dr") return t("facet.dr." + v);
    if (k === "of") return (TAXO && TAXO[v]) || v;
    return v;
  }

  async function showSearch(params) {
    setNav("search");
    state.hasDrafts = state.index.units.some((u) => u.h);
    if (!TAXO && state.index.analysis) { try { TAXO = Object.fromEntries((await json("data/analysis.json")).offences.map((o) => [o.id, o.label])); } catch { TAXO = {}; } }
    const readers = state.readers.filter((r) => state.index.search[r.id]);
    const ui = { q: params.get("q") || "", tol: params.get("tol") !== "0", shown: 50, ff: {},
                 reader: readers.some((r) => r.id === params.get("r")) ? params.get("r") : (readers.some((r) => r.id === state.reader) ? state.reader : (readers[0] || {}).id) };
    const sel = Object.fromEntries(FACETS.map((k) => [k, new Set(params.getAll(k))]));
    const volOrder = state.index.volumes.map((v) => v.v);
    app.innerHTML = `
      <section class="intro"><h1>${esc(t("search.h1"))}</h1><p>${esc(t("search.intro"))}</p></section>
      <div class="sbar">
        <input id="sq" type="search" value="${esc(ui.q)}" placeholder="${esc(t("search.placeholder"))}" aria-label="${esc(t("search.aria"))}">
        <label class="small"><input type="checkbox" id="stol" ${ui.tol ? "checked" : ""}> ${esc(t("search.tol"))}</label>
        <select id="sr" aria-label="${esc(t("search.reader.aria"))}">${readers.map((r) => `<option value="${esc(r.id)}" ${r.id === ui.reader ? "selected" : ""}>${esc(t("search.in", { name: loc(r, "label") }))}</option>`).join("")}</select>
        <button type="button" id="sreset" class="linkish">${esc(t("search.reset"))}</button>
      </div>
      <div class="search">
        <div class="facetwrap">
          <button type="button" id="ftoggle" class="ftoggle" aria-expanded="false" aria-controls="facets">${esc(t("search.facets"))} <span id="fsel"></span></button>
          <aside class="facets" id="facets" aria-label="${esc(t("search.facets"))}"></aside>
        </div>
        <section class="results"><p id="scount" class="muted small"></p><div id="sres" class="list"></div></section>
      </div>`;
    const $ = (id) => document.getElementById(id);
    const toUrl = () => {
      const u = new URLSearchParams();
      if (ui.q) u.set("q", ui.q);
      if (!ui.tol) u.set("tol", "0");
      if (ui.reader && ui.reader !== (readers[0] || {}).id) u.set("r", ui.reader);
      for (const k of FACETS) for (const v of sel[k]) u.append(k, v);
      const h = "#/search" + (u.toString() ? "?" + u : "");
      if (location.hash !== h) history.replaceState(null, "", location.pathname + location.search + h);
    };
    const sortVals = (k, counts) => [...counts.entries()].sort((a, b) => {
      if (k === "vol") return volOrder.indexOf(a[0]) - volOrder.indexOf(b[0]);
      if (k === "dec") return +a[0] - +b[0];
      return b[1] - a[1] || a[0].localeCompare(b[0], "de");
    });

    const run = async () => {
      toUrl();
      const terms = parseQuery(ui.q, ui.tol);
      const nSel = FACETS.reduce((n, k) => n + sel[k].size, 0);
      let base;
      if (terms.length && ui.reader) {
        $("scount").textContent = t("search.loading");
        const all = await searchTexts(ui.reader);
        const nk = ui.reader + "|" + ui.tol;
        if (!normed.has(nk)) normed.set(nk, new Map());
        const cache = normed.get(nk);
        base = [];
        for (const u of state.index.units) {
          const pages = all[u.id];
          if (!pages) continue;
          if (!cache.has(u.id)) cache.set(u.id, pages.map((x) => normText(x, ui.tol).s));
          const ns = cache.get(u.id);
          if (!terms.every((x) => ns.some((s) => s.includes(x)))) continue;
          const at = Math.max(0, ns.findIndex((s) => s.includes(terms[0])));
          base.push({ u, page: at + 1, text: pages[at] });
        }
      } else if (nSel) {
        base = state.index.units.map((u) => ({ u }));
      } else {
        $("facets").innerHTML = facetsHtml(state.index.units.map((u) => ({ u })), () => true);
        $("fsel").textContent = "";
        $("scount").textContent = "";
        $("sres").innerHTML = `<p class="empty">${esc(readers.length ? t("search.hint") : t("search.noreading"))}</p>`;
        return;
      }
      const vals = (u, k) => [].concat(facetValue(u, k)).filter(Boolean);
      const passes = (h, except) => FACETS.every((k) => k === except || !sel[k].size || vals(h.u, k).some((v) => sel[k].has(v)));
      const rows = base.filter((h) => passes(h, null));
      $("fsel").textContent = nSel ? `(${t("search.selected", { n: nSel })})` : "";
      $("facets").innerHTML = facetsHtml(base, passes);
      $("scount").innerHTML = `${num(rows.length)} ${esc(unitWord(rows.length))}` + (terms.length ? esc(t("search.with")) +
        (ui.q.match(/"[^"]+"|«[^»]+»|\S+/g) || []).map((x) => `<b>${esc(x)}</b>`).join(" + ") + ` · ${esc(readerLabel(ui.reader))}` : "");
      const draw = () => {
        const rest = rows.length - ui.shown;
        $("sres").innerHTML = rows.slice(0, ui.shown).map((h) => {
          if (!h.text) return unitRow(h.u);
          const href = `#/e/${encodeURIComponent(h.u.id)}/${h.page}/${encodeURIComponent(ui.reader)}`;
          return unitRow(h.u, `<a class="hit" href="${href}">${snippet(h.text, terms, ui.tol)}</a>`, href);
        }).join("") + (rest > 0 ? `<button type="button" class="linkish" id="smore">${esc(t("search.more", { n: Math.min(50, rest), rest }))}</button>` : "")
          + (!rows.length ? `<p class="empty">${esc(t("search.none"))}</p>` : "");
        const more = $("smore");
        more && more.addEventListener("click", () => { ui.shown += 50; draw(); });
      };
      draw();
    };

    function facetsHtml(base, passes) {
      return FACETS.map((k) => {
        const counts = new Map();
        for (const h of base) if (passes(h, k)) for (const v of [].concat(facetValue(h.u, k)).filter(Boolean)) counts.set(v, (counts.get(v) || 0) + 1);
        for (const v of sel[k]) if (!counts.has(v)) counts.set(v, 0);
        const vals = sortVals(k, counts);
        if (!vals.length) return "";
        const ff = (ui.ff[k] || "").toLowerCase();
        return `<details class="facet" open data-k="${k}"><summary>${esc(t("facet." + k))}${sel[k].size ? ` <span class="badge">${sel[k].size}</span>` : ""} <span class="muted small">${vals.length}</span></summary>
          ${vals.length > 12 ? `<input class="ffilter" type="search" data-ff="${k}" value="${esc(ui.ff[k] || "")}" placeholder="${esc(t("search.filter"))}" aria-label="${esc(t("search.filter"))} ${esc(t("facet." + k))}">` : ""}
          <ul>${vals.map(([v, n]) => `<li ${ff && !facetLabel(k, v).toLowerCase().includes(ff) ? "hidden" : ""}><label class="${n ? "" : "zero"}"><input type="checkbox" data-k="${k}" value="${esc(v)}" ${sel[k].has(v) ? "checked" : ""}>
            <span class="fl">${esc(facetLabel(k, v))}</span><span class="fc">${num(n)}</span></label></li>`).join("")}</ul></details>`;
      }).join("");
    }

    const later = (f, ms = 250) => { clearTimeout(searchTimer); searchTimer = setTimeout(f, ms); };
    $("sq").addEventListener("input", () => { ui.q = $("sq").value; ui.shown = 50; later(run); });
    $("stol").addEventListener("change", () => { ui.tol = $("stol").checked; run(); });
    $("sr").addEventListener("change", () => { ui.reader = $("sr").value; run(); });
    $("sreset").addEventListener("click", () => { location.hash = "#/search"; });
    $("ftoggle").addEventListener("click", () => {
      const open = $("facets").classList.toggle("shown");
      $("ftoggle").setAttribute("aria-expanded", String(open));
    });
    $("facets").addEventListener("change", (ev) => {
      const box = ev.target.closest("input[type=checkbox][data-k]");
      if (!box) return;
      box.checked ? sel[box.dataset.k].add(box.value) : sel[box.dataset.k].delete(box.value);
      ui.shown = 50;
      run();
    });
    $("facets").addEventListener("input", (ev) => {
      const inp = ev.target.closest("input[data-ff]");
      if (!inp) return;
      ui.ff[inp.dataset.ff] = inp.value;
      const w = inp.value.toLowerCase();
      inp.closest(".facet").querySelectorAll("li").forEach((li) => { li.hidden = !!w && !li.querySelector(".fl").textContent.toLowerCase().includes(w); });
    });
    await run();
  }

  /* ---------- unit (a page now, an entry later) ---------- */
  async function getUnit(id) {
    const pos = state.pos.get(id);
    if (pos == null) return null;
    const c = Math.floor(pos / state.index.chunk);
    if (!state.chunks.has(c)) state.chunks.set(c, json(`data/units/${c}.json`));
    return (await state.chunks.get(c)).find((u) => u.id === id) || null;
  }

  let cur = null;   // the page on screen, for the arrow keys
  function pageKeys(ev) {
    if (!cur || ev.target.closest("input, select, textarea") || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    const to = ev.key === "ArrowLeft" ? cur.prev : ev.key === "ArrowRight" ? cur.next : null;
    if (to) { location.hash = to; ev.preventDefault(); }
  }

  async function showUnit(id, pageNo, readerId) {
    setNav("units");
    cur = null;
    let unit = null;
    try { unit = await getUnit(id); } catch { unit = null; }
    if (!unit) { destroyOsd(); app.innerHTML = `<p>${esc(t("unit.none"))} ${esc(id)}. <a href="#/">${esc(t("all"))}</a></p>`; return; }
    const pages = unit.pages;
    pageNo = Math.min(Math.max(pageNo || 1, 1), pages.length);
    const page = pages[pageNo - 1];
    if (readerId && state.readers.some((r) => r.id === readerId)) { state.reader = readerId; store.set("reader", readerId); }
    let reader = state.reader;
    if (!page.readings[reader]) {
      const first = state.readers.find((x) => page.readings[x.id]);
      if (first) reader = first.id;
    }

    const pos = state.pos.get(id);
    const prevU = state.index.units[pos - 1], nextU = state.index.units[pos + 1];
    const href = (uid, n) => `#/e/${encodeURIComponent(uid)}/${n}`;
    const prev = pageNo > 1 ? href(id, pageNo - 1) : prevU ? href(prevU.id, 1) : null;
    const next = pageNo < pages.length ? href(id, pageNo + 1) : nextU ? href(nextU.id, 1) : null;
    cur = { prev, next };
    state.view = { page, reader };   // the lines on the image follow the page and reader on screen
    const showImg = state.cfg.images && store.get("image", true);
    const pgBtn = (p, i) => `<a class="pg ${i + 1 === pageNo ? "on" : ""}" href="${href(id, i + 1)}" ${i + 1 === pageNo ? 'aria-current="page"' : ""}>${esc(p.nr ?? i + 1)}</a>`;

    const keepImage = showImg && state.osd && app.querySelector("#osd") && app.dataset.tk === page.tk;
    const html = `
      <div class="letter ${showImg ? "" : "noimgpane"}">
        <section class="pane textpane">
          <div class="lnav">
            ${prevU ? `<a href="${href(prevU.id, 1)}">← ${esc(titleOf(prevU))}</a>` : "<span></span>"}
            <a href="#/band/${encodeURIComponent(unit.shelf)}">${esc(unit.shelf)}</a>
            ${nextU ? `<a href="${href(nextU.id, 1)}">${esc(titleOf(nextU))} →</a>` : "<span></span>"}
          </div>
          <div class="muted small">${esc(t("unit.tkpage"))} ${esc(page.key)} ${Object.keys(page.readings).length ? statusBadge(page.st) : `<span class="badge st-NEW">${esc(t("status.none"))}</span>`}</div>
          <h1>${esc((unit.draft && unit.draft.heading) || unit.title || titleOf(unit))}</h1>
          ${unit.draft && unit.draft.heading ? `<div class="muted small">${esc(titleOf(unit))} ${draftMark()}</div>` : ""}
          ${draftBlock(unit.draft)}
          ${unit.p ? "" : `<p class="small teilinks">TEI: <button type="button" class="linkish" id="tei-entry">${esc(t("tei.entry"))}</button> · <a href="data/tei/${encodeURIComponent(teiFile(unit.shelf))}" download>${esc(t("tei.volume", { vol: unit.shelf }))}</a> <span id="tei-msg" class="muted"></span></p>`}
          <div class="pages">${pages.length > 1 ? `<span class="lbl">${esc(t("unit.pages"))}</span>${pages.map(pgBtn).join("")}` : ""}
            ${state.cfg.images ? `<button type="button" class="linkish imgtoggle" id="imgtoggle" aria-pressed="${showImg}">${esc(t(showImg ? "img.hide" : "img.show"))}</button>` : ""}
          </div>
          <div class="readers" role="tablist" aria-label="${esc(t("readings.aria"))}">${readerButtons(page, reader)}</div>
          ${modeSelect(page, reader)}
          <div id="reading">${readingHtml(page, reader)}</div>
          ${state.cfg.images ? "" : `<p class="small muted">${esc(t("img.off"))}</p>`}
        </section>
        ${showImg ? `<section class="pane imgpane">
          <div id="osd" role="img" aria-label="${esc(t("img.aria"))} ${esc(titleOf(unit))}"></div>
          <div class="imgbar"><span><b>${esc(page.vol)}, ${esc(t("page.abbr"))} ${esc(page.nr)}</b></span><span id="imglink"></span></div>
          <p class="imgcredit small muted">${esc(t("img.credit"))}</p>
        </section>` : ""}
      </div>
      <footer class="foot">${esc(t("foot"))}</footer>`;

    if (keepImage) {
      app.querySelector(".textpane").outerHTML = new DOMParser().parseFromString(html, "text/html").querySelector(".textpane").outerHTML;
    } else {
      destroyOsd();
      app.innerHTML = html;
      if (showImg) { app.dataset.tk = page.tk; openImage(page); }
    }

    app.querySelectorAll(".rd").forEach((b) => b.addEventListener("click", () => {
      if (b.disabled) return;
      location.hash = `${href(id, pageNo)}/${encodeURIComponent(b.dataset.reader)}`;
    }));
    const teiBtn = document.getElementById("tei-entry");
    teiBtn && teiBtn.addEventListener("click", () => downloadEntryTei(unit));
    const tog = document.getElementById("imgtoggle");
    tog && tog.addEventListener("click", () => { store.set("image", !showImg); destroyOsd(); route(); });
    const m = document.getElementById("t-mode");
    m && m.addEventListener("change", () => { state.mode = m.value; store.set("mode", m.value); route(); });
    const det = app.querySelector("details.regest");
    det && det.addEventListener("toggle", () => store.set("regest", det.open));
    const rd = document.getElementById("reading");
    rd.addEventListener("mouseover", entTip);
    rd.addEventListener("click", entTip);
    rd.addEventListener("mouseover", onLineHover);
    rd.addEventListener("mouseleave", () => { if (!pinned) clearRows(); });
    rd.addEventListener("click", onLineClick);
    clearRows();
  }

  /* TEI: one file per volume (data/tei/<volume>.xml, scripts/tei_export.py). An
     entry's own TEI is cut from it here: the header, the surfaces of the entry's
     pages and its <div>, as a document of its own. */
  const teiFile = (vol) => vol.replace(/[^A-Za-z0-9]+/g, "_") + ".xml";
  const teiDocs = new Map();
  async function downloadEntryTei(unit) {
    const msg = document.getElementById("tei-msg");
    const say = (s) => { if (msg) msg.textContent = s; };
    try {
      say(t("tei.loading"));
      const file = teiFile(unit.shelf);
      if (!teiDocs.has(file)) teiDocs.set(file, fetch("data/tei/" + file).then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then((x) => new DOMParser().parseFromString(x, "application/xml")));
      const doc = await teiDocs.get(file);
      const NS = "http://www.tei-c.org/ns/1.0", XML = "http://www.w3.org/XML/1998/namespace";
      const byId = (id) => [...doc.getElementsByTagNameNS(NS, "*")].find((el) => el.getAttributeNS(XML, "id") === id);
      const div = byId(unit.id);
      if (!div) throw new Error(unit.id);
      const out = document.implementation.createDocument(NS, "TEI", null);
      out.documentElement.setAttributeNS(XML, "xml:id", unit.id + "_tei");
      out.documentElement.appendChild(out.importNode(doc.getElementsByTagNameNS(NS, "teiHeader")[0], true));
      const fac = out.createElementNS(NS, "facsimile");
      const pages = new Set([...div.getElementsByTagNameNS(NS, "pb")].map((pb) => (pb.getAttribute("facs") || "").slice(1)));
      for (const s of doc.getElementsByTagNameNS(NS, "surface")) if (pages.has(s.getAttributeNS(XML, "id"))) fac.appendChild(out.importNode(s, true));
      out.documentElement.appendChild(fac);
      const text = out.createElementNS(NS, "text"), body = out.createElementNS(NS, "body");
      body.appendChild(out.importNode(div, true));
      text.appendChild(body);
      out.documentElement.appendChild(text);
      const xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(out);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([xml], { type: "application/tei+xml" }));
      a.download = unit.id + ".xml";
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      say("");
      return xml;
    } catch (e) { say(t("tei.failed")); return null; }
  }
  window.TBTei = { entry: downloadEntryTei };

  /* A heading and regest drafted by a language model: always marked as such. */
  function draftBlock(d) {
    if (!d) return "";
    const when = [d.place, d.date_text].filter(Boolean).map(esc).join(", ");
    return `<details class="regest draft" ${store.get("regest", true) ? "open" : ""}>
      <summary>${esc(t("draft.summary"))}</summary>
      ${d.heading ? `<div class="meta"><span class="parties">${esc(d.heading)}</span></div>` : ""}
      ${when || d.year ? `<p class="small muted">${when}${d.year ? `${when ? " · " : ""}${esc(t("draft.year", { year: d.year, source: d.year_source || t("draft.year.read") }))}` : ""}</p>` : ""}
      <p lang="de">${esc(d.regest)}</p>
      <p class="small muted">${esc(t("draft.note", { model: d.model || t("draft.amodel"), reader: readerLabel(d.reader) }))}</p>
    </details>`;
  }

  function readerButtons(page, current) {
    return state.readers.map((r) => {
      const rd = page.readings[r.id];
      const lines = rd && rd.text ? rd.text.split("\n").length : 0;
      const badge = rd ? `<span class="cer">${rd.text ? `${lines} ${esc(t("line", null, lines))}` : esc(t("reading.emptybadge"))}</span>` : "";
      return `<button class="rd ${r.id === current ? "on" : ""}" role="tab" aria-selected="${r.id === current}" data-reader="${esc(r.id)}" ${rd ? "" : `disabled title="${esc(t("reading.notread.title"))}"`}>
        <span>${esc(loc(r, "label"))}<span class="k">${esc(loc(r, "kind"))}</span></span>${badge}</button>`;
    }).join("");
  }

  /* the ways a reading can be shown: the text, the tags (if there are any), or
     a comparison with each other reading of the page */
  function modes(page, reader) {
    const out = [["plain", t("mode.plain")]];
    if (hasEnts(page, reader)) out.push(["ents", t("mode.ents")]);
    for (const r of state.readers) if (r.id !== reader && page.readings[r.id] && page.readings[r.id].text) out.push(["cmp:" + r.id, t("mode.cmp", { name: loc(r, "label") })]);
    return out;
  }
  function modeFor(page, reader) {
    const ms = modes(page, reader);
    return ms.some(([id]) => id === state.mode) ? state.mode : "plain";
  }
  function modeSelect(page, reader) {
    const ms = modes(page, reader);
    if (ms.length < 2) return "";
    const c = modeFor(page, reader);
    return `<div class="viewmode"><label for="t-mode">${esc(t("view"))}</label>
      <select id="t-mode">${ms.map(([id, label]) => `<option value="${esc(id)}" ${id === c ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></div>`;
  }

  function disagreement(page, a, b) {
    const d = page.dis || {};
    return d[`${a}|${b}`] ?? d[`${b}|${a}`];
  }

  function readingHtml(page, readerId) {
    const r = state.readers.find((x) => x.id === readerId);
    if (!r) return `<p class="empty">${esc(t("reading.none"))}</p>`;
    const gt = ["GT", "DONE", "FINAL"].includes(page.st) && readerId === "transkribus-bestand";
    const head = `<details class="about-reader"><summary>${esc(loc(r, "label"))}: ${esc(loc(r, "kind"))}</summary>${r.about ? `<p>${esc(loc(r, "about"))}</p>` : ""}${r.caveat ? `<p class="caveat">${esc(loc(r, "caveat"))}</p>` : ""}</details>` +
      (gt ? `<p class="gtnote small">${esc(t("reading.gt"))}</p>` : "");
    const rd = page.readings[readerId];
    if (!rd) return head + `<p class="empty">${esc(t("reading.notread"))}</p>`;
    if (!rd.text) return head + `<p class="empty">${esc(t("reading.empty"))}</p>`;
    const trunc = rd.truncated ? `<p class="caveat">${esc(t("reading.truncated"))}</p>` : "";
    const mode = modeFor(page, readerId);
    let body, note = "";
    if (mode.startsWith("cmp:")) {
      const other = mode.slice(4);
      const x = disagreement(page, readerId, other);
      note = `<p class="cmp-note small">${t("cmp.note", { name: esc(readerLabel(other)) })} ${x != null ? esc(t("cmp.dis", { pct: pct(x) })) : ""}</p>`;
      body = diffHtml(page.readings[other].text, rd.text);
    } else if (mode === "ents") {
      body = entHtml(rd.text, page.ents[readerId]);
    } else body = esc(rd.text);
    const inside = spanLines(page, rd);
    return head + trunc + note + (mode === "ents" ? legend() : "") + lineNote(rd.ln, page) +
      (inside && inside.some((x) => !x) ? `<p class="small muted">${esc(t("span.note"))}</p>` : "") +
      `<div class="text ${mode === "ents" ? "ents" : ""}">${numberLines(body, rd.ln, page.rt, inside)}</div>`;
  }

  /* a line whose row lies in a heading region (Transkribus layout) is set off */
  /* Which lines of this reading belong to the entry on screen: page.span names
     the entry's first and last line in the reading it was cut on (the Transkribus
     text); other readings follow through the rows on the image both are linked
     to. null = everything (no span, or no way to tell). */
  function spanLines(page, rd) {
    if (!page.span) return null;
    const base = page.readings["transkribus-bestand"];
    const n = rd.text.split("\n").length;
    if (rd === base) return Array.from({ length: n }, (_, i) => i >= page.span[0] && i <= page.span[1]);
    if (!base || !base.ln || !rd.ln) return null;
    const rows = new Set();
    for (let i = page.span[0]; i <= page.span[1]; i++) (base.ln[i] || []).forEach((j) => rows.add(j));
    let last = false;
    return Array.from({ length: n }, (_, i) => { const r = rd.ln[i] || []; if (r.length) last = r.some((j) => rows.has(j)); return last; });
  }

  function numberLines(body, ln, rt, inside) {
    return body.split("\n").map((l, i) => {
      const kind = rt && ln && ln[i] && ln[i].length ? rt[ln[i][0]] : "";
      const cls = (kind === "heading" ? " hd" : kind === "page-number" ? " pn" : "") + (inside && !inside[i] ? " out" : "");
      return `<span class="line${cls}" data-i="${i}"${cls.includes(" hd") ? ` title="${esc(t("lines.heading"))}"` : ""}><span class="ln">${i + 1}</span>${l}</span>`;
    }).join("");
  }

  /* ---------- lines on the image ----------
     build_site.py gives a page with Transkribus lines `rows` (each TextLine's
     outline: x, y, x, y, … in ten-thousandths of the image width, the unit of
     OpenSeadragon's overlays) and every reading `ln`: per line the rows it is
     linked to (empty where no link was good enough). Pointing at a line shows
     its row on the image, pointing at the image shows the line; a click (a tap)
     on a line also brings the image to it, a click on the image brings the text
     to the line. */
  function lineNote(ln, page) {
    if (!ln || !page.rows || !state.cfg.images) return "";
    return `<p class="line-note small muted">${esc(t("lines.note", { linked: ln.filter((x) => x.length).length, lines: ln.length }))}</p>`;
  }
  function currentLn() {
    const v = state.view || {};
    if (!v.page || !v.page.rows) return null;
    const rd = v.page.readings[v.reader];
    return (rd && rd.ln) || null;
  }
  function rowBox(poly) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let k = 0; k + 1 < poly.length; k += 2) {
      x0 = Math.min(x0, poly[k]); x1 = Math.max(x1, poly[k]);
      y0 = Math.min(y0, poly[k + 1]); y1 = Math.max(y1, poly[k + 1]);
    }
    return [x0, y0, x1, y1];
  }
  const imageOpen = () => !!(state.osd && state.osd.world.getItemCount() && window.OpenSeadragon);
  let hlEls = [], pinned = false, pinUntil = 0;
  function clearRows() {
    hlEls.forEach((el) => state.osd && state.osd.removeOverlay(el));
    hlEls = [];
    pinned = false;
    app.querySelectorAll("#reading .line.hl").forEach((el) => el.classList.remove("hl"));
  }
  function showRows(rows) {
    const v = state.view || {};
    if (!imageOpen() || !v.page || !v.page.rows) return;
    for (const j of rows) {
      const poly = v.page.rows[j];
      if (!poly) continue;
      const [x0, y0, x1, y1] = rowBox(poly);
      const w = x1 - x0, h = y1 - y0;
      if (w <= 0 || h <= 0) continue;
      const el = document.createElement("div");
      el.className = "row-hl";
      const pts = [];
      for (let k = 0; k + 1 < poly.length; k += 2) pts.push(`${poly[k] - x0},${poly[k + 1] - y0}`);
      el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><polygon points="${pts.join(" ")}"/></svg>`;
      state.osd.addOverlay({ element: el, location: new OpenSeadragon.Rect(x0 / 1e4, y0 / 1e4, w / 1e4, h / 1e4) });
      hlEls.push(el);
    }
  }
  function lineRows(line) {
    const ln = currentLn();
    return (line && ln && ln[+line.dataset.i]) || [];
  }
  /* after a click the line stays shown until another line is pointed at */
  function onLineHover(ev) {
    const line = ev.target.closest(".line[data-i]");
    if (line && line.classList.contains("hl")) return;
    if (pinned && (!lineRows(line).length || performance.now() < pinUntil)) return;
    clearRows();
    const rows = lineRows(line);
    if (!rows.length) return;
    line.classList.add("hl");
    showRows(rows);
  }
  /* a click or a tap on a line: keep it shown and bring the image to it, gently */
  function onLineClick(ev) {
    if (ev.target.closest(".ent, a, button")) return;
    const line = ev.target.closest(".line[data-i]");
    const rows = lineRows(line);
    if (!rows.length) return;
    clearRows();
    line.classList.add("hl");
    showRows(rows);
    pinned = true;
    pinUntil = performance.now() + 1500;
    if (!imageOpen()) return;
    const v = state.view, bs = rows.map((j) => rowBox(v.page.rows[j]));
    const x0 = Math.min(...bs.map((b) => b[0])), y0 = Math.min(...bs.map((b) => b[1]));
    const x1 = Math.max(...bs.map((b) => b[2])), y1 = Math.max(...bs.map((b) => b[3]));
    const w = Math.max(x1 - x0, 2500), h = y1 - y0, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const vw = w * 1.25, vh = Math.max(h * 5, vw * 0.25);
    state.osd.viewport.fitBoundsWithConstraints(new OpenSeadragon.Rect((cx - vw / 2) / 1e4, (cy - vh / 2) / 1e4, vw / 1e4, vh / 1e4));
    const img = document.getElementById("osd");
    if (img && stacked()) img.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  /* the image below the text (narrow screens) */
  function stacked() {
    const a = app.querySelector(".textpane"), i = app.querySelector(".imgpane");
    return !!(a && i && i.getBoundingClientRect().top >= a.getBoundingClientRect().bottom - 1);
  }
  function inPoly(x, y, p) {
    let inside = false;
    for (let a = 0, b = p.length - 2; a < p.length; b = a, a += 2) {
      if ((p[a + 1] > y) !== (p[b + 1] > y) && x < (p[b] - p[a]) * (y - p[a + 1]) / (p[b + 1] - p[a + 1]) + p[a]) inside = !inside;
    }
    return inside;
  }
  function rowAt(pt) {
    const v = state.view || {};
    if (!v.page || !v.page.rows) return -1;
    const x = pt.x * 1e4, y = pt.y * 1e4;
    let hit = -1, area = Infinity;
    v.page.rows.forEach((poly, j) => {
      const b = rowBox(poly);
      if (x < b[0] || x > b[2] || y < b[1] || y > b[3] || !inPoly(x, y, poly)) return;
      const a = (b[2] - b[0]) * (b[3] - b[1]);
      if (a < area) { hit = j; area = a; }
    });
    return hit;
  }
  function linesOfRow(j) {
    const ln = currentLn();
    if (!ln || j < 0) return [];
    return [...app.querySelectorAll("#reading .line[data-i]")].filter((el) => (ln[+el.dataset.i] || []).includes(j));
  }
  function hlRow(j) {
    clearRows();
    const els = linesOfRow(j);
    if (!els.length) return [];
    els.forEach((el) => el.classList.add("hl"));
    showRows([j]);
    return els;
  }
  function trackImage(osd) {
    let last = -2;
    const tracker = new OpenSeadragon.MouseTracker({
      element: osd.canvas,
      moveHandler: (e) => {
        if (state.osd !== osd) return;
        const j = rowAt(osd.viewport.pointFromPixel(e.position));
        if (j === last) return;
        last = j;
        if (pinned && (performance.now() < pinUntil || !linesOfRow(j).length)) return;
        hlRow(j);
      },
      leaveHandler: () => { last = -2; if (!pinned) clearRows(); },
    });
    osd.addHandler("canvas-click", (e) => {
      if (!e.quick || state.osd !== osd) return;
      const j = rowAt(osd.viewport.pointFromPixel(e.position));
      last = j;
      const els = hlRow(j);
      pinned = els.length > 0;
      if (els.length && !stacked()) els[0].scrollIntoView({ block: "center", behavior: "smooth" });
    });
    osd.addHandler("destroy", () => tracker.destroy());
  }

  /* word diff: tokens of the reading against tokens of another reading (LCS) */
  function diffHtml(ref, hyp) {
    const tok = (s) => s.split(/(\s+)/).filter((x) => x !== "");
    const a = tok(ref).filter((x) => !/^\s+$/.test(x));
    const bAll = tok(hyp);
    const b = bAll.filter((x) => !/^\s+$/.test(x));
    const n = a.length, m = b.length;
    if (n * m > 4e6) return esc(hyp);
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const seps = []; { let k = -1; for (const x of bAll) { if (/^\s+$/.test(x)) { seps[k] = (seps[k] || "") + x; } else { k++; } } }
    let i = 0, j = 0, out = "", pendingDel = [];
    const flushDel = () => { if (pendingDel.length) { out += `<del>${esc(pendingDel.join(" "))}</del> `; pendingDel = []; } };
    while (i < n || j < m) {
      if (i < n && j < m && a[i] === b[j]) { flushDel(); out += esc(b[j]) + (seps[j] ?? ""); i++; j++; }
      else if (j < m && (i >= n || dp[i][j + 1] >= dp[i + 1][j])) { flushDel(); out += `<ins>${esc(b[j])}</ins>` + (seps[j] ?? ""); j++; }
      else { pendingDel.push(a[i]); i++; }
    }
    flushDel();
    return out.replace(/ \n/g, "\n");
  }

  /* ---------- image (IIIF on files.transkribus.eu) ---------- */
  function destroyOsd() { if (state.osd) { state.osd.destroy(); state.osd = null; } delete app.dataset.tk; }
  function noImage(msg) {
    const el = document.getElementById("osd");
    if (el) el.innerHTML = `<p class="noimg">${esc(msg)}</p>`;
  }
  /* Transkribus' info.json lists `sizes`; with `sizes` OpenSeadragon 4.1 stops
     at a thumbnail, so it is dropped. */
  async function openImage(page) {
    if (!page.tk) { noImage(t("img.none")); return; }
    if (!window.OpenSeadragon) { noImage(t("img.noviewer")); return; }
    const base = state.cfg.iiif + encodeURIComponent(page.tk);
    noImage(t("img.loading"));
    let info = null;
    try { info = await json(`${base}/info.json`); } catch { info = null; }
    if (app.dataset.tk !== page.tk || !document.getElementById("osd")) return;
    if (!info) { noImage(t("img.failed")); return; }
    info["@id"] = base;
    delete info.sizes;
    document.getElementById("osd").innerHTML = "";
    state.osd = OpenSeadragon({
      id: "osd",
      prefixUrl: "https://cdnjs.cloudflare.com/ajax/libs/openseadragon/4.1.0/images/",
      tileSources: info,
      showNavigator: true, navigatorPosition: "BOTTOM_RIGHT",
      gestureSettingsMouse: { clickToZoom: false },
      crossOriginPolicy: "Anonymous",
    });
    trackImage(state.osd);
    const el = document.getElementById("imglink");
    if (el) el.innerHTML = `<a href="${esc(base)}/full/max/0/default.jpg" target="_blank" rel="noopener">${esc(t("img.full"))} ↗</a>`;
  }

  /* ---------- tags (entities/<reader>.jsonl) ---------- */
  function hasEnts(page, reader) { return !!(page.ents && page.ents[reader] && page.ents[reader].length); }
  function legend() {
    return `<div class="legend">${["per", "org", "place", "date"].map((k) => `<span class="${k}"><i></i>${esc(t("ent." + k))}</span>`).join("")}</div>`;
  }
  function entHtml(text, ents) {
    const sorted = [...ents].sort((a, b) => a.start - b.start);
    let out = "", at = 0;
    for (const e of sorted) {
      if (e.start < at) continue;
      out += esc(text.slice(at, e.start));
      const attrs = `class="ent ${esc(e.type)}" data-ref="${esc(e.ref || e.when || "")}" data-role="${esc(e.role || "")}"`;
      out += `<span ${attrs}>${text.slice(e.start, e.end).split("\n").map(esc).join(`</span>\n<span ${attrs}>`)}</span>`;
      at = e.end;
    }
    return out + esc(text.slice(at));
  }
  let tipEl = null;
  function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } }
  document.addEventListener("click", (ev) => { if (tipEl && !tipEl.contains(ev.target) && !ev.target.closest(".ent")) hideTip(); });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hideTip(); });
  function entTip(ev) {
    const el = ev.target.closest(".ent");
    if (!el) return;
    const kind = [...el.classList].find((c) => ["per", "place", "org", "date"].includes(c));
    const ref = el.dataset.ref;
    let body = `<b>${esc(kind ? t("ent." + kind) : "")}</b><div class="muted">${esc(t("ent.source"))}</div>`;
    body += ref ? (/^https?:/.test(ref) ? `<a href="${esc(ref)}" target="_blank" rel="noopener">${esc(ref)}</a>` : esc(ref)) : `<span class="muted">${esc(t("ent.unlinked"))}</span>`;
    if (el.dataset.role) body += `<div class="muted">${esc(t("ent.role"))}: ${esc(el.dataset.role)}</div>`;
    hideTip();
    tipEl = document.createElement("div");
    tipEl.className = "tip";
    tipEl.innerHTML = body;
    document.body.appendChild(tipEl);
    const r = el.getBoundingClientRect();
    const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
    tipEl.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left)) + "px";
    tipEl.style.top = (r.bottom + 6 + h > window.innerHeight ? r.top - h - 6 : r.bottom + 6) + "px";
  }

  boot().catch((err) => { app.innerHTML = `<p>${esc(t("error.load"))}: ${esc(err.message)}</p>`; });
})();
