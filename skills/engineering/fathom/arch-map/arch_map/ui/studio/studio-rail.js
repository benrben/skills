/* arch-map studio — agent rail (proposals · inspector · modules) + boot */
window.Studio = window.Studio || {};
(function (S) {
  "use strict";
  const { Store, subscribe, tierOf, isOrphan, openSuggestions, isOpen, STRENGTHS } = window.Arch;

  const els = {};
  let activeTab = "agent";   // agent | inspector | modules | plans
  let modSearch = "";

  const VERDICT = {
    accept: { badge: "accepted", cls: "accepted", verb: "Accepted" },
    defer: { badge: "deferred", cls: "deferred", verb: "Deferred" },
    reject: { badge: "rejected", cls: "rejected", verb: "Rejected" },
  };
  function vcolor(a) { return a === "accept" ? "var(--strong)" : a === "defer" ? "var(--worth)" : a === "reject" ? "var(--leak)" : "var(--text-faint)"; }
  function esc(s) { return (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

  /* ============ tabs ============ */
  function setTab(t) {
    activeTab = t;
    els.tabs.querySelectorAll(".rtab").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === t));
    els.panes.forEach((p) => p.classList.toggle("active", p.dataset.pane === t));
  }
  S.setTab = setTab;

  /* ============ agent: status header ============ */
  function renderAgentHead() {
    const s = S.model;
    const open = openSuggestions(s).length;
    const leaks = s.modules.reduce((a, m) => a + (m.leaks || []).length, 0);
    const decided = Object.keys(s.decisions).length;
    els.agentSub.innerHTML = open
      ? `I scanned <b>${s.modules.length}</b> modules and found <b>${open}</b> ${open === 1 ? "place" : "places"} worth deepening. Review each against the graph, then decide.`
      : `All ${decided} proposal${decided === 1 ? "" : "s"} triaged. I'll keep watching the graph for new seams.`;
    els.agentStats.innerHTML = `
      <div class="astat acc"><div class="n">${open}</div><div class="l">proposals</div></div>
      <div class="astat leak"><div class="n">${leaks}</div><div class="l">leaks</div></div>
      <div class="astat"><div class="n">${decided}</div><div class="l">decided</div></div>`;
  }

  /* ============ agent: proposal queue (per-suggestion) ============ */
  function decidedSuggestions() {
    const out = [];
    S.model.modules.forEach((m) => (m.suggestions || []).forEach((s) => {
      if (S.model.decisions[s.sid] || s.decision) out.push(s);
    }));
    return out;
  }

  function renderAgentPane() {
    const open = openSuggestions(S.model).slice();
    const decided = decidedSuggestions();
    const order = { strong: 0, worth: 1, speculative: 2 };
    open.sort((a, b) => order[a.strength] - order[b.strength]);

    let html = `<p class="queue-intro">These are the agent's <b>deepening proposals</b> — modules it thinks should be hardened or split. Hover one to spotlight it in the graph.</p>`;

    if (!open.length) {
      html += `<div class="queue-clear"><div class="check">✓</div><div class="big">Inbox zero</div><div class="sm">No open proposals. Everything the agent flagged has a decision.</div></div>`;
    } else {
      html += open.map(propCard).join("");
    }
    if (decided.length) {
      html += `<div class="decided-head">decided · ${decided.length}</div>`;
      html += decided.map(propCard).join("");
    }
    els.agentPane.innerHTML = html;
    wireProps(els.agentPane);
  }

  function propCard(s) {
    const st = STRENGTHS[s.strength], dec = S.model.decisions[s.sid];
    const statusPill = s.status && s.status !== "open" ? `<span class="cand-status ${s.status}">${s.status}</span>` : "";
    const catTag = s.category ? `<span class="cat-tag">${esc(s.category)}</span>` : "";
    const adr = s.adrRef ? `<a class="adr-link" href="#">${esc(s.adrRef)}</a>` : "";
    const verdict = dec && VERDICT[dec.verdict] ? `
      <div class="aprop-verdict ${VERDICT[dec.verdict].cls}">
        <span class="vlabel">${VERDICT[dec.verdict].verb}</span>
        ${dec.reason ? `<span class="vreason">— ${esc(dec.reason)}</span>` : ""}
        ${adr}
        <span class="spacer"></span><button class="undo" data-undo="${s.sid}">undo</button>
      </div>` : "";
    const actions = dec ? "" : `
      <textarea class="reason-in" data-reason="${s.sid}" rows="1" placeholder="reason (saved with the decision)"></textarea>
      <div class="actions">
        <button class="act accept" data-act="accept" data-id="${s.sid}" data-module="${s.module}">Accept</button>
        <button class="act defer" data-act="defer" data-id="${s.sid}" data-module="${s.module}">Defer</button>
        <button class="act reject" data-act="reject" data-id="${s.sid}" data-module="${s.module}">Reject</button>
        <button class="act dismiss" data-act="dismiss" data-id="${s.sid}" data-module="${s.module}">Dismiss</button>
        <button class="act grill" data-act="grill" data-id="${s.sid}" data-module="${s.module}">Grill</button>
      </div>`;
    return `
      <article class="aprop ${dec ? "decided" : ""}" data-prop="${s.module}">
        <div class="aprop-bar ${s.strength}"></div>
        <div class="aprop-main">
          <div class="aprop-top">
            <span class="strength-tag ${s.strength}">${st.label}</span>
            ${catTag}
            <a class="aprop-id" data-open="${s.module}" data-locate="${s.module}" href="#">${s.module}</a>
            ${statusPill}
            <span class="spacer"></span>
            <button class="aprop-locate" data-locate="${s.module}" title="Find in graph">⌖</button>
          </div>
          <h4>${s.title}</h4>
          <div class="body">
            <p><b>Problem.</b> ${s.problem}</p>
            <p><b>Solution.</b> ${s.solution}</p>
          </div>
          <ul class="wins">${(s.wins || []).map((w) => `<li>${w}</li>`).join("")}</ul>
          ${actions}
        </div>
        ${verdict}
      </article>`;
  }

  function wireProps(root) {
    root.querySelectorAll(".aprop").forEach((card) => {
      const id = card.dataset.prop;
      card.addEventListener("mouseenter", () => { S.setRailHot(id); card.classList.add("hot"); });
      card.addEventListener("mouseleave", () => { S.setRailHot(null); card.classList.remove("hot"); });
    });
    root.querySelectorAll("[data-locate]").forEach((b) => b.onclick = (e) => { e.preventDefault(); S.centerOn(b.dataset.locate, true); });
    root.querySelectorAll("[data-open]").forEach((b) => b.onclick = (e) => { e.preventDefault(); S.selectNode(b.dataset.open); S.centerOn(b.dataset.open, true); });
    root.querySelectorAll("[data-act]").forEach((b) => b.onclick = () => {
      const sid = b.dataset.id, mod = b.dataset.module, act = b.dataset.act;
      if (act === "grill") { Store.grill(mod); S.toast("Grilling " + mod, "var(--accent)"); S.onModelMutated(mod); return; }
      const r = root.querySelector(`[data-reason="${sid}"]`), reason = r ? r.value.trim() : "";
      if (act === "dismiss") { S.model = Store.dismiss(sid); S.toast("Dismissed " + sid, "var(--text-faint)"); }
      else { S.model = Store.decide(sid, act, reason); S.toast("Saved: " + VERDICT[act].badge, vcolor(act)); }
      S.onModelMutated(mod);
    });
    root.querySelectorAll("[data-undo]").forEach((b) => b.onclick = () => {
      // undo = re-open the proposal (clears its server-side decision)
      const sid = b.dataset.undo;
      S.model = Store.reopen(sid); S.toast("Reopened " + sid, "var(--accent)"); S.onModelMutated(sid);
    });
    root.querySelectorAll(".reason-in").forEach(autosize);
  }
  function autosize(t) {
    const fit = () => { t.style.height = "auto"; t.style.height = Math.max(32, t.scrollHeight) + "px"; };
    fit(); t.addEventListener("input", fit);
  }

  /* ============ inspector ============ */
  const SIGNALS = [
    {
      id: "danger-zone",
      sev: "bad",
      label: "Danger zone",
      icon: "⚠",
      check: (m, mx) => mx.churn >= 40 && m.coverage < 40,
      why: "Changes constantly but has almost no tests.",
      how: "Freeze new features. Write tests for the interface first, then refactor internals. This is your highest-risk module.",
    },
    {
      id: "critical-path-untested",
      sev: "bad",
      label: "Critical path untested",
      icon: "⚠",
      check: (m, mx) => mx.blastRadius >= 5 && m.coverage < 60,
      why: "Many modules depend on this one but it lacks test coverage — a bug here breaks a lot.",
      how: "Add interface-level tests before touching anything else. Even 60% coverage dramatically reduces blast risk.",
    },
    {
      id: "circular",
      sev: "bad",
      label: "Circular dependency",
      icon: "↺",
      check: (m, mx) => mx.inCycle,
      why: "This module is part of a dependency cycle. Cycles make code impossible to test in isolation and cause unpredictable load-order bugs.",
      how: "Extract the shared logic into a third module that neither depends on the other. Or invert the dependency with an interface.",
    },
    {
      id: "needs-refactor",
      sev: "warn",
      label: "Needs refactor",
      icon: "↻",
      check: (m, mx) => mx.fanOut >= 6 && m.depth < 50,
      why: "Depends on too many things while hiding very little — it's doing too much and too visibly.",
      how: "Identify which responsibilities can move down into a deeper helper. Aim to cut fan-out by half and raise depth above 60.",
    },
    {
      id: "god-module",
      sev: "warn",
      label: "God module",
      icon: "✦",
      check: (m, mx) => mx.fanIn >= 5 && mx.fanOut >= 4,
      why: "Everything depends on it AND it depends on everything. The hardest kind of module to change safely.",
      how: "Split along responsibility lines. One cluster of callers usually wants a narrower interface — extract that first.",
    },
    {
      id: "bottleneck",
      sev: "warn",
      label: "Bottleneck",
      icon: "⬡",
      check: (m, mx) => mx.fanIn >= 5 && m.depth < 40,
      why: "Lots of modules depend on this but it's shallow — it's a wide, fragile load-bearing surface.",
      how: "Deepen it: push implementation details in and shrink the interface. Each caller should need to know less.",
    },
    {
      id: "test-first",
      sev: "warn",
      label: "Test this first",
      icon: "⬟",
      check: (m, mx) => mx.blastRadius >= 3 && m.coverage < 40,
      why: "Changes here affect at least " + "N" + " other modules, but it's barely tested.",
      how: "Before refactoring anything in this module, get coverage above 60% at the interface. Tests act as a safety net for the downstream blast.",
      dynamic: (m, mx) => `Changes here affect at least ${mx.blastRadius} other modules, but it's barely tested.`,
    },
    {
      id: "unstable-api",
      sev: "warn",
      label: "Unstable API",
      icon: "≋",
      check: (m, mx) => mx.instability > 0.7 && mx.fanIn >= 2,
      why: "High instability (depends on many things) but other modules depend on it — any change inside ripples out.",
      how: "Introduce a stable interface layer. The volatile implementation should hide behind a thin, unchanging contract.",
    },
    {
      id: "split-me",
      sev: "info",
      label: "Split candidate",
      icon: "⊕",
      check: (m, mx) => mx.fanOut >= 4 && mx.coupling >= 2,
      why: "Reaches into too many different domains — a sign it's doing multiple jobs.",
      how: "Group the dependencies by domain. Each group is probably a separate responsibility that deserves its own module.",
    },
    {
      id: "leaky-seam",
      sev: "warn",
      label: "Leaky seam",
      icon: "⤼",
      check: (m, mx) => (m.leaks || []).length > 0,
      why: "Imports modules it shouldn't — a seam violation that creates hidden coupling.",
      how: "Invert the dependency or route through an interface. The module being leaked into should not be aware of its caller.",
      dynamic: (m) => `Imports ${(m.leaks || []).length} module(s) it shouldn't — a seam violation that creates hidden coupling.`,
    },
  ];

  function computeSignals(m) {
    if (!m || !m.metrics) return [];
    const mx = m.metrics;
    try {
      return SIGNALS.filter(s => { try { return s.check(m, mx); } catch(e) { return false; } })
        .map(s => ({ ...s, why: s.dynamic ? s.dynamic(m, mx) : s.why }));
    } catch(e) { return []; }
  }

  function signalsSection(m) {
    const sigs = computeSignals(m);
    if (!sigs.length) return `<div class="dr-sec"><h5>Recommendations</h5><div class="sig-clean">✓ No structural issues detected</div></div>`;
    return `<div class="dr-sec">
      <h5>Recommendations</h5>
      <div class="sig-list">
        ${sigs.map(s => `
          <div class="sig-card sig-${s.sev}">
            <div class="sig-hd">
              <span class="sig-icon">${s.icon}</span>
              <span class="sig-label">${s.label}</span>
            </div>
            <div class="sig-why">${s.why}</div>
            <details class="sig-how-wrap">
              <summary>How to fix</summary>
              <div class="sig-how">${s.how}</div>
            </details>
          </div>`).join("")}
      </div>
    </div>`;
  }

  function healthClass(h) { return h >= 70 ? "good" : h >= 40 ? "warn" : "bad"; }
  function instClass(i)   { return i <= 0.33 ? "good" : i <= 0.66 ? "warn" : "bad"; }
  function metricBadge(label, value, cls, title) {
    return `<div class="mx-stat ${cls}" title="${title}"><div class="mx-val">${value}</div><div class="mx-lbl">${label}</div></div>`;
  }
  function metricsSection(m) {
    const mx = m.metrics;
    if (!mx) return "";
    const instPct = Math.round(mx.instability * 100);
    return `<div class="dr-sec dr-sec-metrics">
      <h5>Graph metrics</h5>
      <div class="mx-grid">
        ${metricBadge("health", mx.health, healthClass(mx.health), "Composite score: depth + coverage − leaks − churn. Higher = healthier.")}
        ${metricBadge("fan-in", mx.fanIn, mx.fanIn >= 10 ? "warn" : "good", "How many modules depend on this one. High = critical, changes are risky.")}
        ${metricBadge("fan-out", mx.fanOut, mx.fanOut >= 8 ? "warn" : "good", "How many modules this one depends on. High = knows too much.")}
        ${metricBadge("instability", instPct + "%", instClass(mx.instability), "fan-out ÷ (fan-in + fan-out). 0% = rock-stable, 100% = fragile — depends on everything, nothing depends on it.")}
        ${metricBadge("blast radius", mx.blastRadius, mx.blastRadius >= 15 ? "bad" : mx.blastRadius >= 5 ? "warn" : "good", "If this module changes, how many modules are transitively affected.")}
        ${metricBadge("coupling", mx.coupling, mx.coupling >= 3 ? "bad" : mx.coupling >= 1 ? "warn" : "good", "Cross-domain dependencies — how many domains this module reaches into.")}
        ${mx.inCycle ? metricBadge("cycle", "⚠ yes", "bad", "This module is part of a circular dependency. Cycles make code hard to test and change.") : ""}
        ${mx.churn ? metricBadge("churn", mx.churn + "%", mx.churn >= 70 ? "bad" : mx.churn >= 40 ? "warn" : "good", "How frequently this module changes (from git history). High churn + low coverage = danger zone.") : ""}
      </div>
    </div>`;
  }

  function renderInspector() {
    const m = S.model.modules.find((x) => x.id === S.selectedId);
    if (!m) {
      els.inspPane.innerHTML = `<div class="insp-empty">
        <div class="ic"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><path d="M17.5 14v7M14 17.5h7"/></svg></div>
        <div class="t">No module selected</div>
        <div class="s">Click any card on the graph to inspect its interface, dependencies, tests and coverage.</div>
      </div>`;
      return;
    }
    const tier = tierOf(m.depth), orphan = isOrphan(S.model, m), open = !!m.suggestion;
    const usedBy = S.model.modules.filter((x) => (x.dependsOn || []).includes(m.id));
    const tags = [`<span class="tag ${tier}"><span class="dot"></span>${tier}</span>`];
    if (open) tags.push(`<span class="tag seam">seam candidate</span>`);
    if (m.plane === "intended") tags.push(`<span class="planned-tag">planned</span>`);
    if (m.lifecycle) tags.push(`<span class="tag lifecycle ${m.lifecycle}">${m.lifecycle}</span>`);
    if (m.updated) tags.push(`<span class="tag updated">updated</span>`);
    if ((m.leaks || []).length) tags.push(`<span class="tag leak">${m.leaks.length} leak${m.leaks.length > 1 ? "s" : ""}</span>`);
    if (orphan) tags.push(`<span class="tag orphan">not connected</span>`);

    const depPills = (m.dependsOn || []).length
      ? `<div class="pill-list">${m.dependsOn.map((d) => `<button class="pill" data-nav="${d}">${d}</button>`).join("")}</div>`
      : `<div class="no-sug" style="padding:9px">no dependencies</div>`;
    const usedPills = usedBy.length
      ? `<div class="pill-list">${usedBy.map((u) => `<button class="pill" data-nav="${u.id}">${u.id}</button>`).join("")}</div>`
      : `<div class="no-sug" style="padding:9px">nothing depends on this</div>`;
    const navPills = (ids) => `<div class="pill-list">${ids.map((d) => `<button class="pill" data-nav="${d}">${d}</button>`).join("")}</div>`;

    const queue = m.suggestions || [];
    let sug;
    if (queue.length) {
      sug = queue.map((s) => {
        const st = STRENGTHS[s.strength] || { label: s.strength };
        const dec = S.model.decisions[s.sid];
        const catTag = s.category ? `<span class="cat-tag">${esc(s.category)}</span>` : "";
        const statusPill = s.status && s.status !== "open" ? `<span class="cand-status ${s.status}">${s.status}</span>` : "";
        if (dec) {
          const adr = s.adrRef ? `<a class="adr-link" href="#">${esc(s.adrRef)}</a>` : "";
          return `<div class="sug-block decided ${s.strength}">
            <div class="sug-hd"><span class="strength-tag ${s.strength}">${st.label}</span>${catTag}${statusPill}</div>
            <div class="sug-bd"><p class="sug-title">${s.title}</p>
              <p class="no-sug" style="padding:0">Decided: <b style="color:var(--text)">${dec.verdict}</b>${dec.reason ? " — " + esc(dec.reason) : ""} ${adr}</p>
            </div></div>`;
        }
        return `<div class="sug-block ${s.strength}">
          <div class="sug-hd"><span class="strength-tag ${s.strength}">${st.label}</span>${catTag}${statusPill}</div>
          <div class="sug-bd">
            <p class="sug-title">${s.title}</p>
            <p><b>Problem.</b> ${s.problem}</p>
            <p><b>Solution.</b> ${s.solution}</p>
            <ul>${(s.wins || []).map((w) => `<li>${w}</li>`).join("")}</ul>
            <button class="btn primary grill" data-grill="${m.id}">Grill this candidate →</button>
          </div></div>`;
      }).join("");
    } else {
      sug = `<div class="no-sug">No proposals for this module.</div>`;
    }

    const supersedesSec = (m.supersedes || []).length ? `<div class="dr-sec"><h5>Supersedes</h5>${navPills(m.supersedes)}</div>` : "";
    const supersededBySec = (m.supersededBy || []).length ? `<div class="dr-sec"><h5>Superseded by</h5>${navPills(m.supersededBy)}</div>` : "";
    const intendsSec = (m.intendsToDependOn || []).length ? `<div class="dr-sec"><h5>Intends to depend on</h5>${navPills(m.intendsToDependOn)}</div>` : "";

    els.inspPane.innerHTML = `
      <div class="insp-head">
        <div class="it"><div><div class="insp-id">${m.id}</div><div class="insp-label">${m.label} · ${m.domain}${m.plane === "intended" ? ' · <span class="planned-tag">planned</span>' : ""}</div></div></div>
        <div class="insp-tags">${tags.join("")}</div>
      </div>
      <div class="insp-body">
        <div class="dr-sec"><h5>Interface</h5><div class="iface">${m.interface || "—"}</div></div>
        <div class="dr-sec"><h5>Depth &amp; coverage</h5>
          <div class="metric-row">
            <div class="metric depth"><div class="ml"><span>depth</span>${stepper("depth")}</div><div class="mv">${m.depth}<span class="u">/100</span></div><div class="track"><i style="width:${m.depth}%"></i></div></div>
            <div class="metric cov"><div class="ml"><span>coverage</span>${stepper("cov")}</div><div class="mv">${m.coverage}<span class="u">%</span></div><div class="track"><i style="width:${m.coverage}%"></i></div></div>
          </div></div>
        ${signalsSection(m)}
        ${metricsSection(m)}
        <div class="dr-sec"><h5>Depends on</h5>${depPills}</div>
        ${intendsSec}
        <div class="dr-sec"><h5>Used by</h5>${usedPills}</div>
        ${supersedesSec}${supersededBySec}
        <div class="dr-sec"><h5>Files</h5><div class="file-list">${(m.files || []).map((f) => `<code>${f}</code>`).join("") || "<span class='no-sug' style='padding:9px'>none</span>"}</div></div>
        <div class="dr-sec"><h5>Tests</h5><div class="test-list">${(m.tests || []).map((t) => `<code>${t}</code>`).join("") || "<span class='no-sug' style='padding:9px'>no tests</span>"}</div></div>
        <div class="dr-sec"><h5>Agent proposals</h5>${sug}</div>
        <div class="danger-zone" id="dz"></div>
      </div>`;

    els.inspPane.querySelectorAll("[data-nav]").forEach((b) => b.onclick = () => { S.selectNode(b.dataset.nav); S.centerOn(b.dataset.nav, true); });
    els.inspPane.querySelectorAll("[data-step]").forEach((b) => b.onclick = () => {
      const [kind, dir] = b.dataset.step.split(":"), delta = dir === "up" ? 5 : -5;
      S.model = kind === "depth" ? Store.setDepth(m.id, delta) : Store.setCoverage(m.id, delta);
      S.onModelMutated(m.id);
    });
    els.inspPane.querySelectorAll("[data-grill]").forEach((grill) => grill.onclick = () => { Store.grill(m.id); setTab("agent"); flashProp(m.id); });
    renderDanger(m.id);
  }
  function stepper(kind) {
    const k = kind === "cov" ? "cov" : "depth";
    return `<span class="stepper"><button data-step="${k}:down">−</button><button data-step="${k}:up">+</button></span>`;
  }
  function renderDanger(id) {
    const dz = els.inspPane.querySelector("#dz"); if (!dz) return;
    dz.innerHTML = `<button class="btn danger" id="delBtn">Delete module</button>`;
    dz.querySelector("#delBtn").onclick = () => {
      dz.innerHTML = `<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px">Delete <b style="font-family:var(--font-mono)">${id}</b> and its edges?</div>
        <div class="confirm-row"><button class="btn" id="cancel">Cancel</button><button class="btn danger-solid" id="yes">Delete</button></div>`;
      dz.querySelector("#cancel").onclick = () => renderDanger(id);
      dz.querySelector("#yes").onclick = () => { S.model = Store.deleteModule(id); S.selectedId = null; S.rebuildGraph(); S.renderRail(); S.toast("Deleted " + id, "var(--leak)"); };
    };
  }
  function flashProp(id) {
    setTimeout(() => {
      const card = els.agentPane.querySelector(`[data-prop="${id}"]`);
      if (card) { els.railBody.scrollTop = card.offsetTop - 12; card.classList.add("hot"); setTimeout(() => card.classList.remove("hot"), 1400); }
    }, 60);
  }

  /* ============ modules pane ============ */
  function renderModules() {
    const rows = S.model.modules
      .filter((m) => !modSearch || m.id.toLowerCase().includes(modSearch) || m.label.toLowerCase().includes(modSearch) || m.domain.toLowerCase().includes(modSearch))
      .sort((a, b) => a.domain.localeCompare(b.domain) || a.id.localeCompare(b.id));

    const list = rows.length ? rows.map((m) => `
      <div class="mrow" data-row="${m.id}">
        <div class="mr-main" data-open="${m.id}">
          <div class="mr-id">${m.id}</div>
          <div class="mr-meta"><span class="dom">${m.domain}</span><span>${m.label}</span></div>
        </div>
        <div class="mr-metrics">
          <div class="mr-metric depth"><div class="mm-v">${m.depth}</div><div class="mm-bar"><i style="width:${m.depth}%"></i></div></div>
          <div class="mr-metric cov"><div class="mm-v">${m.coverage}%</div><div class="mm-bar"><i style="width:${m.coverage}%"></i></div></div>
        </div>
        <button class="mr-del" data-del="${m.id}" title="delete">✕</button>
      </div>`).join("") : `<div class="no-sug" style="padding:18px;border:0">no matches</div>`;

    els.modsPane.innerHTML = `
      <div class="mods-search"><label class="search"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg><input id="modSearch" placeholder="Filter modules…" value="${esc(modSearch)}" autocomplete="off"></label></div>
      <div class="mlist">${list}</div>
      <div class="mods-add">
        <h5>Add module</h5>
        <div class="grid3">
          <div class="field full"><label>id</label><input id="mAddId" placeholder="rate-limiter" autocomplete="off"></div>
          <div class="field"><label>label</label><input id="mAddLabel" placeholder="Rate Limiter" autocomplete="off"></div>
          <div class="field"><label>domain</label><input id="mAddDomain" placeholder="infra" autocomplete="off"></div>
          <div class="field full"><button class="btn primary" id="mAddSave" style="width:100%;justify-content:center">+ Add module</button></div>
        </div>
      </div>`;

    const sb = els.modsPane.querySelector("#modSearch");
    sb.oninput = () => { modSearch = sb.value.trim().toLowerCase(); const pos = sb.selectionStart; renderModules(); const nb = els.modsPane.querySelector("#modSearch"); nb.focus(); nb.setSelectionRange(pos, pos); };

    els.modsPane.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => { S.selectNode(b.dataset.open); S.centerOn(b.dataset.open, true); });
    els.modsPane.querySelectorAll(".mrow").forEach((r) => {
      const id = r.dataset.row;
      r.addEventListener("mouseenter", () => S.setRailHot(id));
      r.addEventListener("mouseleave", () => S.setRailHot(null));
    });
    els.modsPane.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => {
      const id = b.dataset.del;
      if (b.dataset.confirm) { S.model = Store.deleteModule(id); if (S.selectedId === id) S.selectedId = null; S.rebuildGraph(); S.renderRail(); S.toast("Deleted " + id, "var(--leak)"); }
      else { b.dataset.confirm = "1"; b.textContent = "?"; b.style.color = "var(--leak)"; b.style.borderColor = "var(--leak)"; setTimeout(() => { if (b.isConnected) { b.dataset.confirm = ""; b.textContent = "✕"; b.style.color = ""; b.style.borderColor = ""; } }, 2000); }
    });
    els.modsPane.querySelector("#mAddSave").onclick = () => {
      const id = els.modsPane.querySelector("#mAddId").value.trim();
      const label = els.modsPane.querySelector("#mAddLabel").value.trim();
      const domain = els.modsPane.querySelector("#mAddDomain").value.trim();
      if (!id) return;
      S.model = Store.addModule({ id, label, domain });
      S.rebuildGraph(); S.renderRail(); S.toast("Added " + id, "var(--accent)");
    };
  }

  /* ============ plans pane ============ */
  const PSTEP_STATUSES = ["todo", "in-progress", "done", "blocked"];
  function renderPlans() {
    const plans = S.model.plans || [];
    if (!plans.length) {
      els.plansPane.innerHTML = `<div class="no-sug" style="padding:18px;border:0">No plans yet — fathom:plan creates intended structure here.</div>`;
      return;
    }
    els.plansPane.innerHTML = plans.map((p) => {
      const mods = (p.moduleIds || []).length
        ? `<div class="plan-modules">${p.moduleIds.map((id) => `<button class="pill" data-nav="${id}">${id}</button>`).join("")}</div>` : "";
      const adrs = (p.adrRefs || []).length
        ? `<div class="plan-adrs">${p.adrRefs.map((a) => `<a class="adr-link" href="#">${esc(a)}</a>`).join("")}</div>` : "";
      const steps = (p.steps || []).map((st) => `
        <div class="pstep">
          <div class="ps-top"><span class="ps-title">${esc(st.title)}</span><span class="ps-status ${st.status}">${st.status}</span></div>
          ${st.interface ? `<div class="ps-iface"><code>${esc(st.interface)}</code></div>` : ""}
          ${st.note ? `<div class="ps-note">${esc(st.note)}</div>` : ""}
          <div class="ps-controls">${PSTEP_STATUSES.map((s) => `<button class="ps-set ${s === st.status ? "on" : ""}" data-plan="${p.id}" data-step="${st.id}" data-pstatus="${s}">${s}</button>`).join("")}</div>
        </div>`).join("");
      return `<article class="plan-card" data-plan="${p.id}">
        <div class="plan-hd"><span class="plan-title">${esc(p.title)}</span><span class="plan-status ${p.status}">${p.status}</span></div>
        <div class="plan-intent">${esc(p.intent || "")}</div>
        ${mods}${adrs}
        <div class="plan-steps">${steps || `<div class="no-sug" style="padding:9px;border:0">no steps</div>`}</div>
      </article>`;
    }).join("");

    els.plansPane.querySelectorAll("[data-nav]").forEach((b) => b.onclick = () => { S.selectNode(b.dataset.nav); S.centerOn(b.dataset.nav, true); });
    els.plansPane.querySelectorAll(".ps-set").forEach((b) => b.onclick = () => {
      S.model = Store.setStepStatus(b.dataset.plan, b.dataset.step, b.dataset.pstatus);
      S.toast("Step → " + b.dataset.pstatus, "var(--accent)");
      S.onModelMutated(b.dataset.plan);
    });
  }

  /* ============ issues panel ============ */
  let ipOpen = false;
  let ipFilter = "all";   // "all" | "bad" | "warn" | "info"
  let ipSearch = "";

  const SEV_ORDER = { bad: 0, warn: 1, info: 2 };
  const SEV_LABEL = { bad: "🔴 Critical", warn: "🟠 Warn", info: "🟡 Info" };

  function allSignals() {
    return S.model.modules.flatMap((m) => {
      const sigs = computeSignals(m);
      return sigs.length ? [{ m, sigs }] : [];
    }).sort((a, b) => {
      const ah = a.m.metrics ? a.m.metrics.health : 50;
      const bh = b.m.metrics ? b.m.metrics.health : 50;
      return ah - bh;
    });
  }

  function renderIssuesPanel() {
    const ipPanel = document.getElementById("issuesPanel");
    const ipListEl = document.getElementById("ipList");
    const ipFiltersEl = document.getElementById("ipFilters");
    const ipCountsEl = document.getElementById("ipCounts");
    const ipTabCount = document.getElementById("ipTabCount");
    if (!ipPanel) return;

    const all = allSignals();
    const counts = { bad: 0, warn: 0, info: 0 };
    all.forEach(({ sigs }) => sigs.forEach((s) => { if (counts[s.sev] !== undefined) counts[s.sev]++; }));
    const total = all.length;

    // tab badge
    if (ipTabCount) ipTabCount.textContent = total;
    document.getElementById("ipTab").classList.toggle("has-issues", total > 0);

    // counts line
    if (ipCountsEl) {
      ipCountsEl.innerHTML = [
        counts.bad  ? `<span class="ip-ct bad">${counts.bad}</span>`   : "",
        counts.warn ? `<span class="ip-ct warn">${counts.warn}</span>` : "",
        counts.info ? `<span class="ip-ct info">${counts.info}</span>` : "",
      ].join("") || `<span class="ip-ct ok">✓ clean</span>`;
    }

    // filter chips
    if (ipFiltersEl) {
      const chips = [["all","All"], ["bad","🔴 Critical"], ["warn","🟠 Warn"], ["info","🟡 Info"]];
      ipFiltersEl.innerHTML = chips.map(([k, label]) =>
        `<button class="ip-chip${ipFilter === k ? " active" : ""}" data-ipf="${k}">${label}</button>`
      ).join("");
      ipFiltersEl.querySelectorAll("[data-ipf]").forEach((b) => b.onclick = () => {
        ipFilter = b.dataset.ipf;
        renderIssuesPanel();
      });
    }

    // list
    const q = ipSearch.toLowerCase();
    const filtered = all.filter(({ m, sigs }) => {
      if (ipFilter !== "all" && !sigs.some((s) => s.sev === ipFilter)) return false;
      if (q && !m.id.toLowerCase().includes(q) && !m.label.toLowerCase().includes(q) && !m.domain.toLowerCase().includes(q)) return false;
      return true;
    });

    if (!ipListEl) return;
    if (!filtered.length) {
      ipListEl.innerHTML = `<div class="ip-empty">${q || ipFilter !== "all" ? "No matches" : "✓ No issues found"}</div>`;
      return;
    }

    ipListEl.innerHTML = filtered.map(({ m, sigs }) => {
      const health = m.metrics ? m.metrics.health : 50;
      const hcls = health >= 70 ? "good" : health >= 40 ? "warn" : "bad";
      const badges = sigs.map((s) => `<span class="ip-badge ip-badge-${s.sev}" title="${s.why}">${s.icon} ${s.label}</span>`).join("");
      return `<div class="ip-row" data-ipnav="${m.id}">
        <div class="ip-row-main">
          <div class="ip-row-top">
            <span class="ip-health health-${hcls}">${health}</span>
            <span class="ip-id">${esc(m.id)}</span>
            <span class="ip-dom">${esc(m.domain)}</span>
          </div>
          <div class="ip-badges">${badges}</div>
        </div>
        <button class="ip-goto" data-ipnav="${m.id}" title="Find in graph">⌖</button>
      </div>`;
    }).join("");

    ipListEl.querySelectorAll("[data-ipnav]").forEach((el) => el.onclick = () => {
      const id = el.dataset.ipnav;
      S.selectNode(id);
      S.centerOn && S.centerOn(id, true);
    });
  }

  S.toggleIssuesPanel = function (open) {
    const panel = document.getElementById("issuesPanel");
    if (!panel) return;
    ipOpen = open === undefined ? !ipOpen : !!open;
    panel.classList.toggle("open", ipOpen);
    renderIssuesPanel();
  };

  /* ============ tab counts ============ */
  function renderTabCounts() {
    const open = openSuggestions(S.model).length;
    const agentTab = els.tabs.querySelector('[data-tab="agent"]');
    agentTab.querySelector(".tcount").textContent = open;
    agentTab.classList.toggle("has-open", open > 0);
    els.tabs.querySelector('[data-tab="modules"] .tcount').textContent = S.model.modules.length;
    const plansTab = els.tabs.querySelector('[data-tab="plans"] .tcount');
    if (plansTab) plansTab.textContent = (S.model.plans || []).length;
  }

  /* ============ full rail render ============ */
  S.renderRail = function () {
    renderAgentHead();
    renderAgentPane();
    renderInspector();
    renderModules();
    renderPlans();
    renderTabCounts();
    renderIssuesPanel();
  };

  /* ============ select / deselect ============ */
  S.selectNode = function (id) {
    S.selectedId = id;
    setTab("inspector");
    renderInspector();
    S.refreshVisualState();
    if (S.railCollapsed) S.toggleRail(true);
  };
  S.deselect = function () { S.selectedId = null; renderInspector(); S.refreshVisualState(); };

  /* ============ rail collapse ============ */
  S.railCollapsed = false;
  S.toggleRail = function (open) {
    S.railCollapsed = open === undefined ? !S.railCollapsed : !open;
    els.rail.classList.toggle("collapsed", S.railCollapsed);
    els.railToggle.querySelector(".lbl").textContent = S.railCollapsed ? "Agent" : "Hide";
    setTimeout(() => S.fit && S.fit(true), 290);
  };

  /* ============ toast ============ */
  let toastT;
  S.toast = function (msg, color) {
    els.toast.innerHTML = `<div class="toast"><span class="tk" style="background:${color || "var(--strong)"}"></span>${msg}</div>`;
    clearTimeout(toastT); toastT = setTimeout(() => (els.toast.innerHTML = ""), 2200);
  };

  /* ============ counts in header ============ */
  function renderHeaderCounts() {
    document.getElementById("openCount").querySelector(".n").textContent = openSuggestions(S.model).length;
  }

  /* ============ mutation handling ============ */
  S.onModelMutated = function (touchedId) {
    const sig = S.sigOf(S.model);
    if (sig !== S._structSig) { S.rebuildGraph(); S._structSig = sig; }
    else S.softUpdateGraph();
    S.renderRail(); renderHeaderCounts();
    if (touchedId && activeTab !== "inspector") { /* keep tab */ }
  };

  /* ============ external model updates (poll / other tab) ============ */
  function onExternal(s) {
    S.model = s;
    const sig = S.sigOf(s);
    if (sig !== S._structSig) { S.rebuildGraph(); S._structSig = sig; }
    else S.softUpdateGraph();
    S.renderRail(); renderHeaderCounts();
  }

  /* ============ boot ============ */
  S.bootRail = function () {
    els.tabs = document.getElementById("railTabs");
    els.railBody = document.getElementById("railBody");
    els.agentSub = document.getElementById("agentSub");
    els.agentStats = document.getElementById("agentStats");
    els.agentPane = document.getElementById("agentPane");
    els.inspPane = document.getElementById("inspPane");
    els.modsPane = document.getElementById("modsPane");
    els.plansPane = document.getElementById("plansPane");
    els.rail = document.getElementById("rail");
    els.railToggle = document.getElementById("railToggle");
    els.toast = document.getElementById("toast");
    els.panes = Array.from(document.querySelectorAll(".rail-pane"));

    els.tabs.querySelectorAll(".rtab").forEach((b) => b.onclick = () => setTab(b.dataset.tab));
    els.railToggle.onclick = () => S.toggleRail();

    S._structSig = S.sigOf(S.model);
    S.renderRail(); renderHeaderCounts(); setTab("agent");

    // deep links
    const q = new URLSearchParams(location.search);
    if (q.get("q")) { S._searchBox.value = q.get("q"); S._searchBox.dispatchEvent(new Event("input")); }
    if (q.get("sel")) S.selectNode(q.get("sel"));

    // issues panel wiring
    const ipTab = document.getElementById("ipTab");
    const ipClose = document.getElementById("ipClose");
    const ipSearchEl = document.getElementById("ipSearch");
    if (ipTab) ipTab.onclick = () => S.toggleIssuesPanel();
    if (ipClose) ipClose.onclick = () => S.toggleIssuesPanel(false);
    if (ipSearchEl) ipSearchEl.oninput = () => { ipSearch = ipSearchEl.value.trim(); renderIssuesPanel(); };

    // keyboard
    window.addEventListener("keydown", (e) => {
      if (document.activeElement === ipSearchEl) return;
      if (e.key === "/" && document.activeElement !== S._searchBox) { e.preventDefault(); S._searchBox.focus(); }
      if (e.key === "Escape") { S.deselect(); S.toggleIssuesPanel(false); }
      if (e.key === "p" || e.key === "P") S.toggleIssuesPanel();
      if (e.key === "1") setTab("agent");
      if (e.key === "2") setTab("inspector");
      if (e.key === "3") setTab("modules");
      if (e.key === "4") setTab("plans");
    });

    subscribe(onExternal);
  };
})(window.Studio);
