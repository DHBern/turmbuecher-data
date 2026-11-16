/* Berner Turmbücher — Prüfen: a fixed sample of the machine's work, checked by hand.
   Loaded by app.js on #/pruefen[/grenzen|delikte|personen[/n]]. Data:
   data/pruefung.json (scripts/pruefung.py). Answers stay in this browser
   (localStorage) until they are exported as a file; scripts/pruefung_auswerten.py
   reads such files. Nothing is sent anywhere. */
window.TBCheck = (() => {
  "use strict";
  const TASKS = ["grenzen", "delikte", "personen"];
  const IIIF = "https://files.transkribus.eu/iiif/2/";
  let sample = null, analysis = null;

  async function show(app, ctx, task, n) {
    const { t, esc, num, json, store } = ctx;
    task = TASKS.includes(task) ? task : "grenzen";
    app.innerHTML = `<p class="loading">${esc(t("loading"))}</p>`;
    let S, A;
    try {
      if (!sample) sample = json("data/pruefung.json");
      if (!analysis) analysis = json("data/analysis.json");
      [S, A] = await Promise.all([sample, analysis]);
    } catch (e) { app.innerHTML = `<p>${esc(t("error.load"))}: ${esc(e.message)}</p>`; return; }
    const KEY = "pruefung:" + S.version;
    const load = () => store.get(KEY, { reviewer: "", grenzen: {}, delikte: {}, personen: {} });
    const save = (x) => store.set(KEY, x);
    let ans = load();
    const items = S[task];
    const idOf = (it) => (task === "grenzen" ? it.key : task === "delikte" ? it.id : it.key);
    n = Math.min(Math.max(+n || firstOpen(), 1), items.length);
    function firstOpen() { const i = items.findIndex((it) => !ans[task][idOf(it)]); return i < 0 ? 1 : i + 1; }
    const it = items[n - 1], id = idOf(it), mine = ans[task][id];
    const offLabel = Object.fromEntries(A.offences.map((o) => [o.id, o.label]));
    const sanLabel = Object.fromEntries(A.sanctions.map((o) => [o.id, o.label]));
    const done = (k) => Object.keys(ans[k]).length;
    const go = (m) => `#/pruefen/${task}/${m}`;

    const img = (p) => p.tk ? `<a href="${IIIF}${encodeURIComponent(p.tk)}/full/max/0/default.jpg" target="_blank" rel="noopener" title="${esc(t("pr.fullimg"))}">
      <img class="primg" src="${IIIF}${encodeURIComponent(p.tk)}/full/1400,/0/default.jpg" alt="${esc(p.vol)}, ${esc(t("page.abbr"))} ${p.nr}" loading="lazy"></a>` : "";
    const lines = (p, sel) => p.lines.map((l, i) => {
      const ln = p.first + i;
      return `<label class="prline ${sel && sel.has(ln) ? "start" : ""}" data-ln="${ln}">${sel ? `<input type="checkbox" ${sel.has(ln) ? "checked" : ""} aria-label="${esc(t("pr.g.start"))} ${ln + 1}">` : ""}<span class="ln">${ln + 1}</span>${esc(l)}</label>`;
    }).join("");
    const radios = (name, opts, cur) => `<span class="prradio">${opts.map(([v, l]) => `<label><input type="radio" name="${name}" value="${v}" ${cur === v ? "checked" : ""}> ${esc(l)}</label>`).join("")}</span>`;

    let body = "";
    if (task === "grenzen") {
      const sel = new Set(mine ? mine.starts : it.starts);
      body = `<p class="small">${esc(t("pr.g.how"))}</p>
        <div class="prgrid"><div>
          ${it.before.length ? `<div class="prbefore"><div class="small muted">${esc(t("pr.g.before"))}</div>${it.before.map((l) => `<div>${esc(l)}</div>`).join("")}</div>` : `<p class="small muted">${esc(t("pr.g.volstart"))}</p>`}
          <div class="prlines" id="pr-lines">${lines(it, sel)}</div>
          <p class="small muted">${esc(t("pr.g.model", { n: it.starts.length, lines: it.starts.map((s) => s + 1).join(", ") || "–" }))}</p>
        </div><div>${img(it)}</div></div>`;
    } else if (task === "delikte") {
      const cur = mine || {};
      const have = new Set(cur.delikte || it.delikte);
      body = `<div class="prgrid"><div>
          <h2 class="prtitle">${esc(it.title || id)}</h2>
          <p class="small muted">${esc(t("pr.d.date", { text: it.datum_text || "–", year: it.year || "–", src: it.year_source || "–" }))}</p>
          <p>${esc(it.regest)}</p>
          ${it.woertlich ? `<p class="small"><i>${esc(it.woertlich)}</i></p>` : ""}
          <details class="prtext" open><summary>${esc(t("pr.d.text"))}</summary>${it.pages.map((p) => `<div class="small muted">${esc(p.vol)}, ${esc(t("page.abbr"))} ${p.nr}</div><div class="prlines">${lines(p, null)}</div>`).join("")}</details>
          <fieldset class="prform" id="pr-form">
            <legend>${esc(t("pr.d.offences"))}</legend>
            <div class="prchecks">${[...new Set([...it.delikte, ...have])].map((o) => `<label><input type="checkbox" name="off" value="${esc(o)}" ${have.has(o) ? "checked" : ""}> ${esc(offLabel[o] || o)}${it.delikte.includes(o) ? "" : ` <span class="badge auto">${esc(t("pr.d.added"))}</span>`}</label>`).join("")}</div>
            <label class="small">${esc(t("pr.d.add"))} <select id="pr-add"><option value="">—</option>${A.offences.filter((o) => !have.has(o.id)).map((o) => `<option value="${esc(o.id)}">${esc(o.label)}</option>`).join("")}</select></label>
            <p class="small">${esc(t("pr.d.outcome"))}: ${esc(it.sanktionen.map((s) => sanLabel[s] || s).join(", ") || "–")} ${radios("san", [["ok", t("pr.ok")], ["no", t("pr.wrong")], ["?", t("pr.unclear")]], cur.san)}</p>
            <p class="small">${esc(t("pr.d.year", { year: it.year || "–" }))} ${radios("year", [["ok", t("pr.ok")], ["no", t("pr.wrong")], ["?", t("pr.unclear")]], cur.year)}
              <input type="number" id="pr-year" min="1500" max="1800" placeholder="${esc(t("pr.d.yearfix"))}" value="${esc(cur.yearfix || "")}"></p>
            <p class="small">${esc(t("pr.d.person", { names: it.accused.join(", ") || "–" }))} ${radios("person", [["ok", t("pr.ok")], ["no", t("pr.wrong")], ["?", t("pr.unclear")]], cur.person)}</p>
            <p class="small">${esc(t("pr.d.regest"))} ${radios("regest", [["ok", t("pr.ok")], ["part", t("pr.part")], ["no", t("pr.wrong")]], cur.regest)}</p>
            <p class="small">${esc(t("pr.d.boundary"))} ${radios("bound", [["ok", t("pr.ok")], ["short", t("pr.d.short")], ["long", t("pr.d.long")]], cur.bound)}</p>
          </fieldset>
        </div><div>${it.pages.map(img).join("")}</div></div>`;
    } else {
      const h = it.hls;
      body = `<div class="prform">
        <h2 class="prtitle">${esc(it.name)} <span class="badge ${it.grade === "wahrscheinlich" ? "st-GT" : "st-NEW"}">${esc(t("reg.grade." + (it.grade === "wahrscheinlich" ? "likely" : "possible")))}</span></h2>
        <p class="small">${esc(t("reg.p.forms"))}: ${it.forms.map(esc).join(" · ")} · ${it.years ? it.years.join("–") : ""}</p>
        <div class="prop likely"><b>${esc(h.name)}</b> <span class="muted">(${h.b ?? "?"}–${h.d ?? "?"})</span> <span class="small">${esc(h.desc || "")}</span>
          <span class="small"><a href="https://hls-dhs-dss.ch/de/articles/${encodeURIComponent(h.hls)}/" target="_blank" rel="noopener">HLS ${esc(h.hls)}</a> · <a href="https://www.wikidata.org/wiki/${encodeURIComponent(h.qid)}" target="_blank" rel="noopener">Wikidata</a></span></div>
        <p class="small muted">${esc(t("pr.p.entries", { n: it.n }))}</p>
        <ul class="prentries">${it.entries.map((e) => `<li><a href="#/e/${encodeURIComponent(e.id)}/1" target="_blank">${esc(e.title || e.id)}</a> <span class="muted small">${e.year || ""}${e.roles.length ? " · " + esc(e.roles.map((r) => t("reg.role." + r)).join(", ")) : ""}</span><div class="small">${esc(e.regest)}</div></li>`).join("")}</ul>
        <p>${esc(t("pr.p.q"))} ${radios("same", [["ok", t("pr.p.same")], ["no", t("pr.p.other")], ["?", t("pr.unclear")]], mine && mine.same)}</p>
      </div>`;
    }

    app.innerHTML = `
      <section class="intro">
        <h1>${esc(t("pr.h1"))} <span class="badge proto">${esc(t("proto"))}</span></h1>
        <p>${esc(t("pr.intro"))}</p>
        <div class="anbar">
          <label>${esc(t("pr.who"))} <input id="pr-who" type="text" maxlength="12" size="6" value="${esc(ans.reviewer)}" placeholder="${esc(t("pr.who.ph"))}"></label>
          <button type="button" class="linkish" id="pr-export">${esc(t("pr.export"))}</button>
          <span class="small muted">${esc(t("pr.store", { v: S.version }))}</span>
        </div>
        <nav class="regtabs">${TASKS.map((k) => `<a href="#/pruefen/${k}" class="${k === task ? "on" : ""}">${esc(t("pr.tab." + k))} <span class="small">${num(done(k))}/${num(S[k].length)}</span></a>`).join("")}</nav>
        <p class="small muted">${esc(t("pr.about." + task))}</p>
      </section>
      <div class="prnav">
        ${n > 1 ? `<a href="${go(n - 1)}">← ${esc(t("pr.prev"))}</a>` : "<span></span>"}
        <span><b>${num(n)}</b> / ${num(items.length)} · ${task === "personen" ? "" : `<a href="#/${task === "grenzen" ? "page/" + encodeURIComponent(it.key) : "e/" + encodeURIComponent(id) + "/1"}" target="_blank">${esc(task === "grenzen" ? it.vol + ", " + t("page.abbr") + " " + it.nr : id)}</a>`}
          ${mine ? `<span class="badge st-GT">${esc(t("pr.saved"))}</span>` : ""}</span>
        ${n < items.length ? `<a href="${go(n + 1)}">${esc(t("pr.next"))} →</a>` : "<span></span>"}
      </div>
      <div class="prbody">${body}</div>
      <div class="prsave">
        <label class="small">${esc(t("pr.note"))} <input type="text" id="pr-note" size="40" value="${esc((mine && mine.note) || "")}"></label>
        <button type="button" class="btn" id="pr-save">${esc(t(n < items.length ? "pr.savenext" : "pr.savelast"))}</button>
        ${mine ? `<button type="button" class="linkish" id="pr-reset">${esc(t("pr.reset"))}</button>` : ""}
        <span id="pr-msg" class="small muted"></span>
      </div>`;

    const $ = (x) => document.getElementById(x);
    $("pr-who").addEventListener("change", () => { ans = load(); ans.reviewer = $("pr-who").value.trim(); save(ans); });
    if (task === "grenzen") {
      $("pr-lines").addEventListener("change", (ev) => { const l = ev.target.closest(".prline"); if (l) l.classList.toggle("start", ev.target.checked); });
    }
    if (task === "delikte") {
      $("pr-add").addEventListener("change", () => {
        const v = $("pr-add").value;
        if (!v) return;
        const box = document.querySelector(".prchecks");
        box.insertAdjacentHTML("beforeend", `<label><input type="checkbox" name="off" value="${esc(v)}" checked> ${esc(offLabel[v])} <span class="badge auto">${esc(t("pr.d.added"))}</span></label>`);
        $("pr-add").querySelector(`option[value="${CSS.escape(v)}"]`).remove();
        $("pr-add").value = "";
      });
    }
    const val = (name) => (document.querySelector(`input[name="${name}"]:checked`) || {}).value || "";
    $("pr-save").addEventListener("click", () => {
      ans = load();
      ans.reviewer = $("pr-who").value.trim();
      const note = $("pr-note").value.trim();
      let a;
      if (task === "grenzen") a = { starts: [...document.querySelectorAll("#pr-lines input:checked")].map((x) => +x.closest(".prline").dataset.ln), model: it.starts };
      else if (task === "delikte") {
        a = { delikte: [...document.querySelectorAll('input[name="off"]:checked')].map((x) => x.value), model: it.delikte,
              san: val("san"), year: val("year"), yearfix: $("pr-year").value || "", year_source: it.year_source, person: val("person"), regest: val("regest"), bound: val("bound") };
        if (!a.year || !a.person || !a.regest) { $("pr-msg").textContent = t("pr.d.missing"); return; }
      } else {
        a = { same: val("same"), grade: it.grade, hls: it.hls.hls };
        if (!a.same) { $("pr-msg").textContent = t("pr.p.missing"); return; }
      }
      a.note = note;
      a.at = new Date().toISOString();
      ans[task][id] = a;
      save(ans);
      location.hash = n < items.length ? go(n + 1) : `#/pruefen/${task}/${n}`;
      if (n >= items.length) show(app, ctx, task, n);
    });
    const reset = $("pr-reset");
    reset && reset.addEventListener("click", () => { ans = load(); delete ans[task][id]; save(ans); show(app, ctx, task, n); });
    $("pr-export").addEventListener("click", () => {
      ans = load();
      ans.reviewer = $("pr-who").value.trim() || ans.reviewer;
      const out = { sample: S.version, seed: S.seed, reviewer: ans.reviewer, exported: new Date().toISOString(), answers: { grenzen: ans.grenzen, delikte: ans.delikte, personen: ans.personen } };
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: "application/json" }));
      a.download = `pruefung-${S.version}-${(ans.reviewer || "anonym").replace(/[^A-Za-z0-9]+/g, "")}.json`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      window.__tbLastExport = out;
    });
  }

  return { show };
})();
