(function () {
  "use strict";

  const stack = document.getElementById("zendoc-live-message-stack");
  if (!stack || !stack.dataset.liveUrl) return;

  let active = true;
  let inFlight = false;
  let lastHtml = stack.innerHTML;
  let timer = null;

  function nearBottom() {
    const doc = document.documentElement;
    return window.innerHeight + window.scrollY >= doc.scrollHeight - 180;
  }

  async function refreshThread() {
    if (!active || inFlight || document.hidden) return;
    inFlight = true;
    const shouldFollow = nearBottom();
    try {
      const response = await fetch(stack.dataset.liveUrl, {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store",
        headers: {"X-Requested-With": "XMLHttpRequest"}
      });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403 || response.status === 404) active = false;
        return;
      }
      const html = await response.text();
      if (html !== lastHtml) {
        stack.innerHTML = html;
        lastHtml = html;
        if (shouldFollow) {
          window.scrollTo({top: document.documentElement.scrollHeight, behavior: "smooth"});
        }
      }
    } catch (_error) {
      // A transient network failure must not erase or fake message state.
    } finally {
      inFlight = false;
    }
  }

  function schedule() {
    clearInterval(timer);
    timer = setInterval(refreshThread, 4000);
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refreshThread();
  });
  window.addEventListener("beforeunload", function () {
    active = false;
    clearInterval(timer);
  });

  schedule();
})();
