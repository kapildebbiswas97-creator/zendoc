(() => {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // PWA installation is optional; the web app continues without it.
    });
  });

  let installPrompt = null;
  const installButtons = () => document.querySelectorAll("[data-install-zendoc]");

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons().forEach((button) => {
      button.hidden = false;
      button.disabled = false;
    });
  });

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-install-zendoc]");
    if (!button || !installPrompt) return;
    button.disabled = true;
    installPrompt.prompt();
    try {
      await installPrompt.userChoice;
    } finally {
      installPrompt = null;
      button.hidden = true;
    }
  });

  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    installButtons().forEach((button) => {
      button.hidden = true;
    });
  });
})();
