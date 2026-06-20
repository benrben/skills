/* arch-map studio — the TASK BOARD (skill-cycle Kanban).
 *
 * A full-width surface that SWAPS with the graph (header Graph|Board toggle, `b`).
 * Columns are the Fathom skill cycle — todo · understand · plan · in-progress ·
 * review · done — each owned by a skill (understand→understand, plan→design,
 * in-progress→code, review→review). Rows are agents (swimlanes), so every agent's
 * tasks are trackable; cards are WorkSteps carrying their per-task git worktree.
 *
 * The projection is computed server-side (model.board) and arrives in S.model.board,
 * so this file RENDERS it rather than recomputing lanes/columns. Dragging a card to a
 * cell moves it across the cycle (status) and assigns it to that lane's agent in one
 * write; worktree + dispatch buttons run the real git / headless agent through Store.
 */
window.Studio = window.Studio || {};
(function (S) {
  "use strict";
  const Store = window.Arch.Store;
  const Focus = window.Arch.Focus;
  const esc = (s) => (s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const COL_LABEL = {
    "todo": "Todo", "understand": "Understand", "plan": "Plan",
    "in-progress": "In progress", "review": "Review", "done": "Done",
  };
  const COL_SKILL = {                       // which Fathom skill owns each column
    "understand": "understand", "plan": "design", "in-progress": "code", "review": "review",
  };
  const PRIOS = ["low", "normal", "high", "urgent"];

  const els = {};
  let planFilter = "all";                   // "all" | a plan id
  let dragging = null;                      // { plan, step } while a card is dragged

  /* ============ view toggle: graph <-> board ============ */
  S.view = "graph";
  S.setView = function (view) {
    S.view = view === "board" ? "board" : "graph";
    const onBoard = S.view === "board";
    const ws = document.querySelector(".workspace");
    const tb = document.querySelector(".toolbar");
    if (ws) ws.style.display = onBoard ? "none" : "";
    if (tb) tb.style.display = onBoard ? "none" : "";
    if (els.surface) els.surface.style.display = onBoard ? "flex" : "none";
    document.querySelectorAll("[data-view-btn]").forEach((b) =>
      b.setAttribute("aria-pressed", b.dataset.viewBtn === S.view));
    if (onBoard) S.renderBoard();
    else setTimeout(() => S.fit && S.fit(true), 60);
  };

  /* ============ the cards / lanes ============ */
  function cardHtml(c) {
    const wt = c.worktree;
    const targets = (c.targets || []).slice(0, 4).map((t) =>
      `<button class="bcard-target" data-nav="${esc(t)}" title="Find ${esc(t)} in the graph">${esc(t)}</button>`).join("");
    const wtBadge = wt
      ? `<span class="bcard-wt ${esc(wt.status)}" title="worktree ${esc(wt.path || "")}">⎇ ${esc(wt.branch)}${wt.status !== "active" ? " · " + esc(wt.status) : ""}</span>`
      : "";
    const runBtn = `<button class="bcard-btn run" data-run title="Dispatch an agent to build this task${wt ? " in its worktree" : ""}">▶ run</button>`;
    const wtBtn = wt
      ? `<button class="bcard-btn" data-wtrm title="Remove this worktree">✕ wt</button>`
      : `<button class="bcard-btn" data-wtnew title="Create a git worktree (isolated branch) for this task">＋ worktree</button>`;
    return `
      <article class="bcard prio-${esc(c.priority)}${c.blocked ? " blocked" : ""}${c.running ? " running" : ""}"
               draggable="true" data-plan="${esc(c.planId)}" data-step="${esc(c.stepId)}">
        <div class="bcard-head">
          <button class="bcard-prio prio-${esc(c.priority)}" data-prio title="Cycle priority">${esc(c.priority)}</button>
          <span class="bcard-plan" title="${esc(c.planTitle)}">${esc(c.planTitle)}</span>
          <span class="bcard-flags">
            ${c.running ? `<span class="bcard-run" title="An agent is building this now">⚙</span>` : ""}
            ${c.blocked ? `<span class="bcard-blocked" title="Blocked">⚠</span>` : ""}
          </span>
        </div>
        <div class="bcard-title">${esc(c.title)}</div>
        ${targets ? `<div class="bcard-targets">${targets}</div>` : ""}
        ${wtBadge}
        <div class="bcard-foot">
          <button class="bcard-btn" data-assign title="Assign to an agent (swimlane)">@</button>
          <button class="bcard-btn" data-block title="${c.blocked ? "Unblock" : "Block"}">${c.blocked ? "▣" : "▢"}</button>
          ${wtBtn}
          ${runBtn}
        </div>
      </article>`;
  }

  function laneLabel(agent) {
    if (agent === "unassigned") return `<span class="lane-name unassigned">unassigned</span>`;
    return `<span class="lane-name" title="agent">${esc(agent)}</span>`;
  }

  S.renderBoard = function () {
    if (!els.grid) return;
    const board = (S.model && S.model.board) || { columns: [], lanes: [], counts: {}, cards: [] };
    const columns = board.columns && board.columns.length ? board.columns
      : ["todo", "understand", "plan", "in-progress", "review", "done"];

    // plan filter options
    const plans = (S.model.plans || []);
    els.filter.innerHTML = `<option value="all">all plans</option>` +
      plans.map((p) => `<option value="${esc(p.id)}"${planFilter === p.id ? " selected" : ""}>${esc(p.title || p.id)}</option>`).join("");

    const keep = (c) => planFilter === "all" || c.planId === planFilter;
    const cards = (board.cards || []).filter(keep);

    if (!cards.length) {
      els.grid.style.display = "none";
      els.empty.style.display = "block";
      els.empty.innerHTML = plans.length
        ? `<div class="board-empty-in"><b>No tasks${planFilter !== "all" ? " in this plan" : ""}.</b><p>fathom:design sequences a plan's work steps into board tasks. Each task can get its own worktree, walk the cycle, and be built by an agent.</p></div>`
        : `<div class="board-empty-in"><b>No plans yet.</b><p>Run <code>/design</code> to sequence intended structure into a plan — its steps become tasks here, one column per skill in the cycle.</p></div>`;
      renderWipCounts(columns, {});
      return;
    }
    els.empty.style.display = "none";
    els.grid.style.display = "grid";

    // lanes (rows), each with its cards bucketed by column; respect the plan filter
    const laneOrder = (board.lanes || []).map((l) => l.agent);
    const byLane = {};
    cards.forEach((c) => { (byLane[c.agent] = byLane[c.agent] || []).push(c); });
    const lanes = laneOrder.filter((a) => byLane[a]);   // only lanes with visible cards, server order

    const counts = {};
    columns.forEach((col) => (counts[col] = 0));
    cards.forEach((c) => { if (counts[c.column] != null) counts[c.column]++; });

    els.grid.style.gridTemplateColumns = `var(--lane-w,148px) repeat(${columns.length}, minmax(150px, 1fr))`;
    let html = `<div class="bg-corner">agent · stage</div>`;
    html += columns.map((col) =>
      `<div class="bg-colhead" data-col="${esc(col)}">
         <span class="ch-name">${esc(COL_LABEL[col] || col)}</span>
         ${COL_SKILL[col] ? `<span class="ch-skill" title="owned by fathom:${COL_SKILL[col]}">/${COL_SKILL[col]}</span>` : ""}
         <span class="ch-wip">${counts[col] || 0}</span>
       </div>`).join("");
    lanes.forEach((agent) => {
      html += `<div class="bg-lanelabel" data-lane="${esc(agent)}">${laneLabel(agent)}</div>`;
      html += columns.map((col) => {
        const inCell = byLane[agent].filter((c) => c.column === col);
        return `<div class="bg-cell" data-lane="${esc(agent)}" data-col="${esc(col)}">${inCell.map(cardHtml).join("")}</div>`;
      }).join("");
    });
    els.grid.innerHTML = html;
    renderWipCounts(columns, counts);
    wireBoard();
  };

  function renderWipCounts(columns, counts) {
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const done = counts["done"] || 0;
    els.summary.textContent = total ? `${total} task${total === 1 ? "" : "s"} · ${done} done` : "";
  }

  /* ============ wiring: drag/drop + card actions ============ */
  function cardOf(el) {
    const a = el.closest(".bcard");
    return a ? { plan: a.dataset.plan, step: a.dataset.step } : null;
  }
  function find(plan, step) {
    const p = (S.model.plans || []).find((x) => x.id === plan);
    return p ? (p.steps || []).find((s) => s.id === step) : null;
  }

  function wireBoard() {
    // drag a card across cells -> move column + assign to that lane's agent in one write
    els.grid.querySelectorAll(".bcard").forEach((card) => {
      card.addEventListener("dragstart", (e) => {
        dragging = cardOf(card);
        card.classList.add("dragging");
        try { e.dataTransfer.setData("text/plain", dragging.step); e.dataTransfer.effectAllowed = "move"; } catch (x) {}
      });
      card.addEventListener("dragend", () => { card.classList.remove("dragging"); dragging = null; els.grid.querySelectorAll(".drop-hot").forEach((c) => c.classList.remove("drop-hot")); });
    });
    els.grid.querySelectorAll(".bg-cell").forEach((cell) => {
      cell.addEventListener("dragover", (e) => { e.preventDefault(); cell.classList.add("drop-hot"); });
      cell.addEventListener("dragleave", () => cell.classList.remove("drop-hot"));
      cell.addEventListener("drop", (e) => {
        e.preventDefault(); cell.classList.remove("drop-hot");
        if (!dragging) return;
        const col = cell.dataset.col, lane = cell.dataset.lane;
        const cur = find(dragging.plan, dragging.step);
        if (!cur) return;
        const fields = {};
        if (cur.status !== col) fields.status = col;
        const targetAgent = lane === "unassigned" ? "" : lane;
        if ((cur.agent || "") !== targetAgent) fields.agent = targetAgent;
        if (!Object.keys(fields).length) return;
        S.model = Store.setStepFields(dragging.plan, dragging.step, fields);
        S.toast("Moved → " + (COL_LABEL[col] || col), "var(--accent)");
        S.renderBoard();
      });
    });

    // jump from a target pill to the graph
    els.grid.querySelectorAll("[data-nav]").forEach((b) => b.onclick = (e) => {
      e.preventDefault();
      S.setView("graph");
      Focus.select(b.dataset.nav); S.reveal(b.dataset.nav, {});
    });

    // priority cycle
    els.grid.querySelectorAll("[data-prio]").forEach((b) => b.onclick = (e) => {
      const { plan, step } = cardOf(b); const cur = find(plan, step); if (!cur) return;
      const next = PRIOS[(PRIOS.indexOf(cur.priority || "normal") + 1) % PRIOS.length];
      S.model = Store.setStepFields(plan, step, { priority: next }); S.renderBoard();
    });
    // block toggle
    els.grid.querySelectorAll("[data-block]").forEach((b) => b.onclick = () => {
      const { plan, step } = cardOf(b); const cur = find(plan, step); if (!cur) return;
      S.model = Store.setStepFields(plan, step, { blocked: !cur.blocked });
      S.toast(cur.blocked ? "Unblocked" : "Blocked", "var(--accent)"); S.renderBoard();
    });
    // assign to an agent (swimlane)
    els.grid.querySelectorAll("[data-assign]").forEach((b) => b.onclick = () => {
      const { plan, step } = cardOf(b); const cur = find(plan, step); if (!cur) return;
      const who = window.prompt("Assign this task to which agent? (blank = unassigned)\ne.g. fathom:code, Explore, workflow:build", cur.agent || "");
      if (who === null) return;
      S.model = Store.assignStep(plan, step, who.trim()); S.renderBoard();
    });
    // create a worktree for the task (isolated branch)
    els.grid.querySelectorAll("[data-wtnew]").forEach((b) => b.onclick = () => {
      const { plan, step } = cardOf(b); const cur = find(plan, step); if (!cur) return;
      const def = "feat/" + step.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const branch = window.prompt("Branch name for this task's worktree:", def);
      if (!branch) return;
      S.model = Store.createWorktree({ branch: branch.trim(), plan_id: plan, step_id: step, agent: cur.agent || "" });
      S.toast("Creating worktree " + branch, "var(--accent)");
    });
    // remove a worktree
    els.grid.querySelectorAll("[data-wtrm]").forEach((b) => b.onclick = () => {
      const { plan, step } = cardOf(b); const cur = find(plan, step); if (!cur || !cur.worktree) return;
      if (!window.confirm("Remove the worktree for this task? (the branch is kept)")) return;
      S.model = Store.removeWorktree(cur.worktree, true); S.toast("Removing worktree", "var(--leak)");
    });
    // dispatch an agent to build the task (runs inside its worktree when present)
    els.grid.querySelectorAll("[data-run]").forEach((b) => b.onclick = () => {
      const { plan, step } = cardOf(b);
      S.dispatch({ kind: "task", plan, step });
    });
  }

  /* ============ boot ============ */
  S.bootBoard = function () {
    els.surface = document.getElementById("boardSurface");
    if (!els.surface) return;
    els.grid = document.getElementById("boardGrid");
    els.empty = document.getElementById("boardEmpty");
    els.filter = document.getElementById("boardFilter");
    els.summary = document.getElementById("boardSummary");
    const sync = document.getElementById("boardSync");

    els.filter.onchange = () => { planFilter = els.filter.value; S.renderBoard(); };
    if (sync) sync.onclick = () => { Store.syncWorktrees(); S.toast("Syncing worktrees…", "var(--accent)"); };

    // header Graph|Board toggle + keyboard `b`
    document.querySelectorAll("[data-view-btn]").forEach((b) => b.onclick = () => S.setView(b.dataset.viewBtn));
    window.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target.tagName || "")) || e.target.isContentEditable;
      if (typing) return;
      if (e.key === "b" || e.key === "B") S.setView(S.view === "board" ? "graph" : "board");
      if (e.key === "Escape" && S.view === "board") S.setView("graph");
    });

    // re-render on any model change while the board is showing
    window.Arch.subscribe(() => { if (S.view === "board") S.renderBoard(); });
  };
})(window.Studio);
