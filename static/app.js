const navToggle = document.querySelector(".nav-toggle");
const primaryNav = document.getElementById("primary-navigation");

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

  // Close any open dropdown when clicking outside navigation
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".nav-menu")) {
      document.querySelectorAll(".nav-menu[open]").forEach((menu) => menu.removeAttribute("open"));
    }
  });
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
