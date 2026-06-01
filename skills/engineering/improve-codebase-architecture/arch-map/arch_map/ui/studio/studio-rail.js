/* arch-map studio — agent rail (proposals · inspector · modules) + boot */
window.Studio = window.Studio || {};
(function (S) {
  "use strict";
  const { Store, subscribe, tierOf, isOrphan, openSuggestions, STRENGTHS } = window.Arch;

  const els = {};
  let activeTab = "agent";   // agent | inspector | modules
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

  /* ============ agent: proposal queue ============ */
  function candidates() { return S.model.modules.filter((m) => m.suggestion); }

  function renderAgentPane() {
    const cands = candidates();
    const open = cands.filter((m) => !S.model.decisions[m.id]);
    const decided = cands.filter((m) => S.model.decisions[m.id]);
    const order = { strong: 0, worth: 1, speculative: 2 };
    open.sort((a, b) => order[a.suggestion.strength] - order[b.suggestion.strength]);

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

  function propCard(m) {
    const s = m.suggestion, st = STRENGTHS[s.strength], dec = S.model.decisions[m.id];
    const verdict = dec && VERDICT[dec.verdict] ? `
      <div class="aprop-verdict ${VERDICT[dec.verdict].cls}">
        <span class="vlabel">${VERDICT[dec.verdict].verb}</span>
        ${dec.reason ? `<span class="vreason">— ${esc(dec.reason)}</span>` : ""}
        <span class="spacer"></span><button class="undo" data-undo="${m.id}">undo</button>
      </div>` : "";
    const actions = dec ? "" : `
      <textarea class="reason-in" data-reason="${m.id}" rows="1" placeholder="reason (saved with the decision)"></textarea>
      <div class="actions">
        <button class="act accept" data-act="accept" data-id="${m.id}">Accept</button>
        <button class="act defer" data-act="defer" data-id="${m.id}">Defer</button>
        <button class="act reject" data-act="reject" data-id="${m.id}">Reject</button>
        <button class="act dismiss" data-act="dismiss" data-id="${m.id}">Dismiss</button>
      </div>`;
    return `
      <article class="aprop ${dec ? "decided" : ""}" data-prop="${m.id}">
        <div class="aprop-bar ${s.strength}"></div>
        <div class="aprop-main">
          <div class="aprop-top">
            <span class="strength-tag ${s.strength}">${st.label}</span>
            <a class="aprop-id" data-open="${m.id}" href="#">${m.id}</a>
            <span class="spacer"></span>
            <button class="aprop-locate" data-locate="${m.id}" title="Find in graph">⌖</button>
          </div>
          <h4>${s.title}</h4>
          <div class="body">
            <p><b>Problem.</b> ${s.problem}</p>
            <p><b>Solution.</b> ${s.solution}</p>
          </div>
          <ul class="wins">${s.wins.map((w) => `<li>${w}</li>`).join("")}</ul>
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
      const id = b.dataset.id, act = b.dataset.act;
      const r = root.querySelector(`[data-reason="${id}"]`), reason = r ? r.value.trim() : "";
      if (act === "dismiss") { S.model = Store.dismiss(id); S.toast("Dismissed " + id, "var(--text-faint)"); }
      else { S.model = Store.decide(id, act, reason); S.toast("Saved: " + VERDICT[act].badge, vcolor(act)); }
      S.onModelMutated(id);
    });
    root.querySelectorAll("[data-undo]").forEach((b) => b.onclick = () => {
      // undo = re-open the proposal (clears its server-side decision)
      const id = b.dataset.undo;
      S.model = Store.reopen(id); S.toast("Reopened " + id, "var(--accent)"); S.onModelMutated(id);
    });
    root.querySelectorAll(".reason-in").forEach(autosize);
  }
  function autosize(t) {
    const fit = () => { t.style.height = "auto"; t.style.height = Math.max(32, t.scrollHeight) + "px"; };
    fit(); t.addEventListener("input", fit);
  }

  /* ============ inspector ============ */
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
    const tier = tierOf(m.depth), orphan = isOrphan(S.model, m), open = m.suggestion && !S.model.decisions[m.id];
    const usedBy = S.model.modules.filter((x) => (x.dependsOn || []).includes(m.id));
    const tags = [`<span class="tag ${tier}"><span class="dot"></span>${tier}</span>`];
    if (open) tags.push(`<span class="tag seam">seam candidate</span>`);
    if (m.updated) tags.push(`<span class="tag updated">updated</span>`);
    if ((m.leaks || []).length) tags.push(`<span class="tag leak">${m.leaks.length} leak${m.leaks.length > 1 ? "s" : ""}</span>`);
    if (orphan) tags.push(`<span class="tag orphan">not connected</span>`);

    const depPills = (m.dependsOn || []).length
      ? `<div class="pill-list">${m.dependsOn.map((d) => `<button class="pill" data-nav="${d}">${d}</button>`).join("")}</div>`
      : `<div class="no-sug" style="padding:9px">no dependencies</div>`;
    const usedPills = usedBy.length
      ? `<div class="pill-list">${usedBy.map((u) => `<button class="pill" data-nav="${u.id}">${u.id}</button>`).join("")}</div>`
      : `<div class="no-sug" style="padding:9px">nothing depends on this</div>`;

    let sug;
    if (open) {
      const st = STRENGTHS[m.suggestion.strength];
      sug = `<div class="sug-block ${m.suggestion.strength}">
          <div class="sug-hd"><span class="strength-tag ${m.suggestion.strength}">${st.label}</span></div>
          <div class="sug-bd">
            <p class="sug-title">${m.suggestion.title}</p>
            <p><b>Problem.</b> ${m.suggestion.problem}</p>
            <p><b>Solution.</b> ${m.suggestion.solution}</p>
            <ul>${m.suggestion.wins.map((w) => `<li>${w}</li>`).join("")}</ul>
            <button class="btn primary grill" data-grill="${m.id}">Review in agent queue →</button>
          </div></div>`;
    } else {
      const d = S.model.decisions[m.id];
      sug = d ? `<div class="no-sug">Decided: <b style="color:var(--text)">${d.verdict}</b>${d.reason ? " — " + esc(d.reason) : ""}</div>`
              : `<div class="no-sug">No open proposal for this module.</div>`;
    }

    els.inspPane.innerHTML = `
      <div class="insp-head">
        <div class="it"><div><div class="insp-id">${m.id}</div><div class="insp-label">${m.label} · ${m.domain}</div></div></div>
        <div class="insp-tags">${tags.join("")}</div>
      </div>
      <div class="insp-body">
        <div class="dr-sec"><h5>Interface</h5><div class="iface">${m.interface || "—"}</div></div>
        <div class="dr-sec"><h5>Depth &amp; coverage</h5>
          <div class="metric-row">
            <div class="metric depth"><div class="ml"><span>depth</span>${stepper("depth")}</div><div class="mv">${m.depth}<span class="u">/100</span></div><div class="track"><i style="width:${m.depth}%"></i></div></div>
            <div class="metric cov"><div class="ml"><span>coverage</span>${stepper("cov")}</div><div class="mv">${m.coverage}<span class="u">%</span></div><div class="track"><i style="width:${m.coverage}%"></i></div></div>
          </div></div>
        <div class="dr-sec"><h5>Depends on</h5>${depPills}</div>
        <div class="dr-sec"><h5>Used by</h5>${usedPills}</div>
        <div class="dr-sec"><h5>Files</h5><div class="file-list">${(m.files || []).map((f) => `<code>${f}</code>`).join("") || "<span class='no-sug' style='padding:9px'>none</span>"}</div></div>
        <div class="dr-sec"><h5>Tests</h5><div class="test-list">${(m.tests || []).map((t) => `<code>${t}</code>`).join("") || "<span class='no-sug' style='padding:9px'>no tests</span>"}</div></div>
        <div class="dr-sec"><h5>Agent proposal</h5>${sug}</div>
        <div class="danger-zone" id="dz"></div>
      </div>`;

    els.inspPane.querySelectorAll("[data-nav]").forEach((b) => b.onclick = () => { S.selectNode(b.dataset.nav); S.centerOn(b.dataset.nav, true); });
    els.inspPane.querySelectorAll("[data-step]").forEach((b) => b.onclick = () => {
      const [kind, dir] = b.dataset.step.split(":"), delta = dir === "up" ? 5 : -5;
      S.model = kind === "depth" ? Store.setDepth(m.id, delta) : Store.setCoverage(m.id, delta);
      S.onModelMutated(m.id);
    });
    const grill = els.inspPane.querySelector("[data-grill]");
    if (grill) grill.onclick = () => { setTab("agent"); flashProp(m.id); };
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

  /* ============ tab counts ============ */
  function renderTabCounts() {
    const open = openSuggestions(S.model).length;
    const agentTab = els.tabs.querySelector('[data-tab="agent"]');
    agentTab.querySelector(".tcount").textContent = open;
    agentTab.classList.toggle("has-open", open > 0);
    els.tabs.querySelector('[data-tab="modules"] .tcount').textContent = S.model.modules.length;
  }

  /* ============ full rail render ============ */
  S.renderRail = function () {
    renderAgentHead();
    renderAgentPane();
    renderInspector();
    renderModules();
    renderTabCounts();
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

    // keyboard
    window.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== S._searchBox) { e.preventDefault(); S._searchBox.focus(); }
      if (e.key === "Escape") S.deselect();
      if (e.key === "1") setTab("agent");
      if (e.key === "2") setTab("inspector");
      if (e.key === "3") setTab("modules");
    });

    subscribe(onExternal);
  };
})(window.Studio);
