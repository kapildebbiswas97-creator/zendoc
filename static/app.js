// Apply a saved theme before the page becomes interactive. Fail closed if
// storage is unavailable (for example, in a locked-down browser context).
(function initializeTheme() {
  let storedTheme = null;
  try {
    storedTheme = window.localStorage.getItem("zendoc-theme");
  } catch (_error) {
    // The default light theme remains usable without storage access.
  }
  const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = storedTheme === "dark" || storedTheme === "light" ? storedTheme : preferredTheme;
})();

const navToggle = document.querySelector(".nav-toggle");
const primaryNav = document.getElementById("primary-navigation");
const themeToggle = document.getElementById("theme-toggle-btn");
const topbar = document.getElementById("site-topbar");

const syncThemeToggle = () => {
  if (!themeToggle) return;
  const isDark = document.documentElement.dataset.theme === "dark";
  themeToggle.setAttribute("aria-pressed", String(isDark));
  themeToggle.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
};

syncThemeToggle();

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = nextTheme;
    try {
      window.localStorage.setItem("zendoc-theme", nextTheme);
    } catch (_error) {
      // Theme switching still works for the current page without persistence.
    }
    syncThemeToggle();
  });
}

if (topbar) {
  const updateTopbar = () => topbar.classList.toggle("topbar--scrolled", window.scrollY > 24);
  window.addEventListener("scroll", updateTopbar, { passive: true });
  updateTopbar();
}

if (navToggle && primaryNav) {
  const navToggleLabel = navToggle.querySelector(".sr-only");
  const closeNav = () => {
    navToggle.setAttribute("aria-expanded", "false");
    primaryNav.removeAttribute("data-open");
    if (navToggleLabel) navToggleLabel.textContent = "Open navigation";
  };

  navToggle.addEventListener("click", () => {
    const willOpen = navToggle.getAttribute("aria-expanded") !== "true";
    navToggle.setAttribute("aria-expanded", String(willOpen));
    primaryNav.toggleAttribute("data-open", willOpen);
    if (navToggleLabel) navToggleLabel.textContent = willOpen ? "Close navigation" : "Open navigation";
  });

  primaryNav.addEventListener("click", (event) => {
    if (event.target.closest("a") && window.matchMedia("(max-width: 960px)").matches) {
      closeNav();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeNav();
      document.querySelectorAll(".nav-menu[open]").forEach((menu) => menu.removeAttribute("open"));
      navToggle.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".nav-menu")) {
      document.querySelectorAll(".nav-menu[open]").forEach((menu) => menu.removeAttribute("open"));
    }
  });

  document.querySelectorAll(".nav-menu").forEach((menu) => {
    const summary = menu.querySelector("summary");
    if (!summary) return;
    const updateExpanded = () => summary.setAttribute("aria-expanded", String(menu.open));
    menu.addEventListener("toggle", () => {
      updateExpanded();
      if (menu.open) {
        document.querySelectorAll(".nav-menu[open]").forEach((other) => {
          if (other !== menu) other.removeAttribute("open");
        });
      }
    });
    updateExpanded();
  });
}

// Senior landing-page motion enhancement. It is visual only and does not
// change any healthcare workflow, safety state, or action confirmation rule.
const heroVideo = document.getElementById("hero-video");
if (heroVideo) {
  const applyHeroPlayback = () => {
    heroVideo.playbackRate = 0.6;
  };
  heroVideo.addEventListener("loadedmetadata", applyHeroPlayback);
  heroVideo.addEventListener("canplay", applyHeroPlayback);
  if (heroVideo.readyState >= 1) applyHeroPlayback();
}

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((control) => {
      control.disabled = true;
      if (control.tagName === "BUTTON") {
        control.dataset.originalLabel = control.textContent;
        control.textContent = control.dataset.submittingLabel || "Working…";
      }
    });
  });
});

const assistantInput = document.getElementById("assistant-message");
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    if (!assistantInput) return;
    assistantInput.value = button.dataset.prompt || "";
    assistantInput.focus();
  });
});

document.querySelectorAll("textarea[data-character-count]").forEach((textarea) => {
  const counter = document.getElementById(textarea.dataset.characterCount);
  const updateCount = () => {
    if (counter) counter.textContent = `${textarea.value.length} characters`;
  };
  textarea.addEventListener("input", updateCount);
  updateCount();
});

// Interactive Hero AI Scenario Switcher
document.querySelectorAll(".scenario-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    const scenarioKey = tab.dataset.scenario;
    if (!scenarioKey) return;

    document.querySelectorAll(".scenario-tab").forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");

    document.querySelectorAll(".scenario-panel").forEach((panel) => {
      panel.classList.remove("active");
    });
    const targetPanel = document.getElementById(`scenario-${scenarioKey}`);
    if (targetPanel) {
      targetPanel.classList.add("active");
    }
  });
});

// Bring the senior frontend's subtle reveal behavior into the existing app
// without making content inaccessible when motion is reduced or JS is absent.
if (
  "IntersectionObserver" in window &&
  !window.matchMedia("(prefers-reduced-motion: reduce)").matches
) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("reveal-active");
        revealObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.12 }
  );

  document
    .querySelectorAll(
      ".journey-card, .feature-card, .trust-pillar-card, .role-card, .care-path-node, .marketplace-preview-card"
    )
    .forEach((element) => {
      element.classList.add("reveal-on-scroll");
      revealObserver.observe(element);
    });
}
