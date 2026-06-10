/* arch-map — shared chrome: theme + aesthetic-direction toggles */
(function () {
  "use strict";
  const { Prefs, subscribePrefs } = window.Arch;

  function apply(p) {
    document.documentElement.setAttribute("data-theme", p.theme);
    document.documentElement.setAttribute("data-dir", p.dir);
    document.querySelectorAll("[data-theme-btn]").forEach((b) =>
      b.setAttribute("aria-pressed", b.dataset.themeBtn === p.theme));
    document.querySelectorAll("[data-dir-btn]").forEach((b) =>
      b.setAttribute("aria-pressed", b.dataset.dirBtn === p.dir));
  }

  function init() {
    apply(Prefs.get());
    document.addEventListener("click", (e) => {
      const t = e.target.closest("[data-theme-btn]");
      const d = e.target.closest("[data-dir-btn]");
      if (t) apply(Prefs.set({ theme: t.dataset.themeBtn }));
      if (d) apply(Prefs.set({ dir: d.dataset.dirBtn }));
    });
    subscribePrefs(apply);
  }

  // build the toggle markup into a container
  window.renderChromeToggles = function (el) {
    el.innerHTML = `
      <div class="seg" role="group" aria-label="Aesthetic direction">
        <button data-dir-btn="a">Direction A</button>
        <button data-dir-btn="b">Direction B</button>
      </div>
      <div class="seg" role="group" aria-label="Theme">
        <button data-theme-btn="light" title="Light">${sun()}</button>
        <button data-theme-btn="dark" title="Dark">${moon()}</button>
      </div>`;
  };
  function sun() { return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></svg>`; }
  function moon() { return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>`; }

  window.applyPrefs = apply;
  init();
})();
