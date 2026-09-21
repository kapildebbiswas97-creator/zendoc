(() => {
  "use strict";

  const root = document.querySelector("[data-zendoc-copilot]");
  if (!root) return;

  const toggle = root.querySelector("[data-copilot-toggle]");
  const close = root.querySelector("[data-copilot-close]");
  const panel = root.querySelector(".zendoc-copilot__panel");
  if (!toggle || !panel) return;

  let lastFocused = null;

  function openCopilot() {
    if (!panel.hidden) return;
    lastFocused = document.activeElement;
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("copilot-open");

    const focusTarget = panel.querySelector(
      "a, button:not([disabled]), textarea, input, select"
    );
    if (focusTarget) {
      window.requestAnimationFrame(() => focusTarget.focus({ preventScroll: true }));
    }
  }

  function closeCopilot(options) {
    if (panel.hidden) return;
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("copilot-open");

    if (!options || options.restoreFocus !== false) {
      const target =
        lastFocused && typeof lastFocused.focus === "function"
          ? lastFocused
          : toggle;
      target.focus({ preventScroll: true });
    }
  }

  toggle.addEventListener("click", () => {
    if (panel.hidden) openCopilot();
    else closeCopilot();
  });

  if (close) {
    close.addEventListener("click", () => closeCopilot());
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault();
      closeCopilot();
      return;
    }

    // Alt+Z is an explicit user shortcut. Copilot never opens on its own.
    if (
      event.altKey &&
      !event.ctrlKey &&
      !event.metaKey &&
      String(event.key || "").toLowerCase() === "z"
    ) {
      event.preventDefault();
      if (panel.hidden) openCopilot();
      else closeCopilot();
    }
  });

  document.addEventListener("pointerdown", (event) => {
    if (panel.hidden) return;
    if (root.contains(event.target)) return;
    closeCopilot({ restoreFocus: false });
  });

  panel.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (link) closeCopilot({ restoreFocus: false });
  });
})();