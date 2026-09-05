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


// M12: keep the latest AI answer in view after a server-rendered send.
// This fixes the previous full-page reload behavior where users had to search
// for the answer after submitting a message.
const latestAIResponse = document.querySelector(".ai-response-inline");
if (latestAIResponse) {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.requestAnimationFrame(() => {
    latestAIResponse.scrollIntoView({
      behavior: reducedMotion ? "auto" : "smooth",
      block: "center",
    });
  });
}

// M12 Voice Access Beta.
// Browser speech APIs are an accessibility enhancement, not a replacement for
// screen readers, keyboard navigation, consent, or consequential-action gates.
(() => {
  const panel = document.getElementById("voice-access-panel");
  const toggle = document.getElementById("voice-access-toggle");
  const helpToggle = document.getElementById("voice-access-help-toggle");
  const status = document.getElementById("voice-access-status");
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const routeMap = document.getElementById("voice-route-map");

  if (!panel || !toggle || !status) return;

  let active = false;
  let recognition = null;
  let pendingAction = null;
  let awaitingDictation = false;
  let suppressRestart = false;

  const setStatus = (message) => {
    status.textContent = message;
  };

  const stopRecognition = () => {
    if (!recognition) return;
    suppressRestart = true;
    try {
      recognition.abort();
    } catch (_error) {
      // Ignore browser-specific abort races.
    }
    panel.dataset.listening = "false";
  };

  const speak = (message, restartAfter = true) => {
    setStatus(message);
    if (!("speechSynthesis" in window)) {
      if (restartAfter && active) window.setTimeout(startListening, 350);
      return;
    }
    stopRecognition();
    const utterance = new SpeechSynthesisUtterance(message);
    utterance.rate = 1;
    utterance.onend = () => {
      suppressRestart = false;
      if (restartAfter && active) window.setTimeout(startListening, 250);
    };
    utterance.onerror = () => {
      suppressRestart = false;
      if (restartAfter && active) window.setTimeout(startListening, 250);
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utterance);
  };

  const normalizeVoiceText = (value) =>
    String(value || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");

  const currentAIInput = () => document.getElementById("assistant-message");
  const currentAIForm = () => document.getElementById("ai-composer");

  const route = (key, fallback) => routeMap?.dataset?.[key] || fallback;
  const navigationTargets = [
    { phrases: ["doctor ai", "clinical ai"], url: route("doctorAi", "/ai?mode=doctor"), label: "Doctor AI" },
    { phrases: ["mental wellness ai", "mental ai", "wellness ai"], url: route("mentalAi", "/ai?mode=mental"), label: "Mental Wellness AI" },
    { phrases: ["general assistant", "assistant ai"], url: route("generalAi", "/ai?mode=assistant"), label: "General Assistant" },
    { phrases: ["zendoc ai", "boss ai", "ai assistant"], url: route("zendocAi", "/ai?mode=zendoc"), label: "ZENDOC AI" },
    { phrases: ["appointments", "appointment"], url: route("appointments", "/appointments"), label: "Appointments" },
    { phrases: ["find care", "find doctor"], url: route("findCare", "/finder"), label: "Find Care" },
    { phrases: ["health memory", "health timeline"], url: route("healthMemory", "/health-memory"), label: "Health Memory" },
    { phrases: ["medical records", "records"], url: route("records", "/records"), label: "Medical Records" },
    { phrases: ["messages", "zendoc connect"], url: route("messages", "/messages"), label: "Messages" },
    { phrases: ["family care", "family"], url: route("family", "/family"), label: "Family Care" },
    { phrases: ["fitness", "fitness coach"], url: route("fitness", "/fitness"), label: "Fitness" },
    { phrases: ["pharmacy"], url: route("pharmacy", "/pharmacy"), label: "Pharmacy" },
    { phrases: ["telehealth", "video consultation", "real doctor"], url: route("telehealth", "/telehealth"), label: "Telehealth" },
    { phrases: ["home healthcare", "home health"], url: route("homeHealth", "/home-health"), label: "Home Healthcare" },
    { phrases: ["medical transport", "transport"], url: route("transport", "/ambulance"), label: "Medical Transport" },
    { phrases: ["dashboard", "home"], url: route("dashboard", "/dashboard"), label: "Dashboard" },
  ];

  const findNavigationTarget = (spoken) => {
    const text = normalizeVoiceText(spoken)
      .replace(/^please\s+/, "")
      .replace(/^(open|go to|navigate to|show me)\s+/, "");
    return navigationTargets.find((target) =>
      target.phrases.some((phrase) => text === phrase || text.includes(phrase))
    );
  };

  const readPage = () => {
    const answer = document.querySelector(".ai-response-inline .ai-inline-answer");
    if (answer && answer.textContent.trim()) {
      speak(`Latest answer. ${answer.textContent.trim().slice(0, 1400)}`);
      return;
    }
    const heading = document.querySelector("main h1");
    const summary = document.querySelector("main .section-copy");
    const message = [
      heading ? heading.textContent.trim() : document.title,
      summary ? summary.textContent.trim() : "",
    ].filter(Boolean).join(". ");
    speak(message.slice(0, 1400) || "There is no readable page summary available.");
  };

  const stageAIDictation = (text) => {
    const input = currentAIInput();
    const form = currentAIForm();
    if (!input || !form) {
      speak("Voice dictation for sending messages is available inside a ZENDOC AI workspace.");
      return;
    }
    const clean = String(text || "").trim();
    if (!clean) {
      awaitingDictation = true;
      pendingAction = null;
      speak("Tell me the message you want to send.");
      return;
    }
    input.value = clean.slice(0, Number(input.maxLength || 4000));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
    pendingAction = { kind: "send_ai", label: "send this AI message" };
    speak("I filled your AI message. Say confirm to send it, or cancel to change it.");
  };

  const confirmPendingAction = () => {
    if (!pendingAction) {
      speak("There is nothing waiting for confirmation.");
      return;
    }
    const action = pendingAction;
    pendingAction = null;
    if (action.kind === "navigate") {
      speak(`Confirmed. Opening ${action.label}.`, false);
      window.setTimeout(() => {
        window.location.href = action.url;
      }, 250);
      return;
    }
    if (action.kind === "send_ai") {
      const form = currentAIForm();
      const input = currentAIInput();
      if (!form || !input || !input.value.trim()) {
        speak("The AI message is empty, so nothing was sent.");
        return;
      }
      speak("Confirmed. Sending your AI message.", false);
      window.setTimeout(() => form.requestSubmit(), 200);
    }
  };

  const handleVoiceCommand = (rawText) => {
    const text = normalizeVoiceText(rawText);
    if (!text) {
      speak("I did not hear a command. Please try again.");
      return;
    }

    if (awaitingDictation) {
      awaitingDictation = false;
      stageAIDictation(rawText);
      return;
    }

    if (["confirm", "yes confirm", "proceed", "continue"].includes(text)) {
      confirmPendingAction();
      return;
    }
    if (["cancel", "no", "stop that", "do not proceed"].includes(text)) {
      pendingAction = null;
      awaitingDictation = false;
      speak("Cancelled. No action was taken.");
      return;
    }
    if (["stop voice", "turn off voice", "voice off"].includes(text)) {
      active = false;
      toggle.setAttribute("aria-pressed", "false");
      toggle.textContent = "🎙 Voice Access Beta";
      pendingAction = null;
      awaitingDictation = false;
      stopRecognition();
      setStatus("Voice Access is off.");
      return;
    }
    if (text === "help" || text === "voice help" || text === "what can i say") {
      speak("You can say open Doctor AI, open appointments, open Health Memory, open messages, read page, dictate, or stop voice. Navigation and AI sending always ask for confirmation.");
      return;
    }
    if (text === "read page" || text === "read answer" || text === "read this page") {
      readPage();
      return;
    }
    if (text === "dictate" || text === "dictate message" || text === "new message") {
      stageAIDictation("");
      return;
    }
    if (text.startsWith("dictate ")) {
      stageAIDictation(rawText.replace(/^dictate\s+/i, ""));
      return;
    }
    if (text.startsWith("ask ")) {
      stageAIDictation(rawText.replace(/^ask\s+/i, ""));
      return;
    }

    const target = findNavigationTarget(text);
    if (target) {
      pendingAction = { kind: "navigate", url: target.url, label: target.label };
      speak(`You asked to open ${target.label}. Say confirm to continue, or cancel.`);
      return;
    }

    speak("I did not match that command. Say voice help to hear the supported commands.");
  };

  function startListening() {
    if (!active || !Recognition || recognition) return;
    suppressRestart = false;
    recognition = new Recognition();
    recognition.lang = document.documentElement.lang || "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      panel.dataset.listening = "true";
      setStatus("Listening for a voice command…");
    };
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      panel.dataset.listening = "false";
      setStatus(`Heard: “${transcript}”`);
      handleVoiceCommand(transcript);
    };
    recognition.onerror = (event) => {
      panel.dataset.listening = "false";
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        active = false;
        toggle.setAttribute("aria-pressed", "false");
        toggle.textContent = "🎙 Voice Access Beta";
        setStatus("Microphone permission is blocked. Enable microphone access in your browser to use Voice Access.");
      } else if (event.error !== "aborted") {
        setStatus(`Voice recognition error: ${event.error}. You can try again.`);
      }
    };
    recognition.onend = () => {
      recognition = null;
      panel.dataset.listening = "false";
      if (active && !suppressRestart && !window.speechSynthesis?.speaking) {
        window.setTimeout(startListening, 450);
      }
    };

    try {
      recognition.start();
    } catch (_error) {
      recognition = null;
    }
  }

  if (!Recognition) {
    toggle.disabled = true;
    setStatus("Voice Access Beta is unavailable in this browser. Keyboard and screen-reader navigation remain available.");
  }

  toggle.addEventListener("click", () => {
    if (!Recognition) return;
    active = !active;
    toggle.setAttribute("aria-pressed", String(active));
    toggle.textContent = active ? "■ Stop Voice Access" : "🎙 Voice Access Beta";
    if (active) {
      speak(
        "Voice Access Beta is on. Say voice help for commands. I will ask for confirmation before navigation or sending an AI message."
      );
    } else {
      pendingAction = null;
      awaitingDictation = false;
      stopRecognition();
      setStatus("Voice Access is off.");
    }
  });

  if (helpToggle) {
    helpToggle.addEventListener("click", () => {
      const next = panel.dataset.helpOpen !== "true";
      panel.dataset.helpOpen = String(next);
      helpToggle.setAttribute("aria-expanded", String(next));
    });
  }

  document.querySelectorAll("[data-voice-dictate-target]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!Recognition) {
        setStatus("Voice dictation is unavailable in this browser.");
        return;
      }
      const targetId = button.dataset.voiceDictateTarget;
      const target = document.getElementById(targetId);
      if (!target) return;

      const dictationRecognition = new Recognition();
      dictationRecognition.lang = document.documentElement.lang || "en-IN";
      dictationRecognition.interimResults = false;
      button.classList.add("listening");
      button.textContent = "Listening…";
      dictationRecognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript || "";
        target.value = transcript.slice(0, Number(target.maxLength || 4000));
        target.dispatchEvent(new Event("input", { bubbles: true }));
        target.focus();
        setStatus("Dictation added. Review the message, then send when ready.");
      };
      dictationRecognition.onerror = () => {
        setStatus("Dictation did not complete. Check microphone permission and try again.");
      };
      dictationRecognition.onend = () => {
        button.classList.remove("listening");
        button.textContent = "🎙 Dictate";
      };
      dictationRecognition.start();
    });
  });
})();
