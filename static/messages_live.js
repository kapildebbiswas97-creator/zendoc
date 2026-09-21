(function () {
  "use strict";

  const stack = document.getElementById("zendoc-live-message-stack");
  if (!stack || !stack.dataset.liveUrl) return;

  let active = true;
  let inFlight = false;
  let lastHtml = stack.innerHTML;
  let timer = null;

  const unreadBadge = document.getElementById("zendoc-unread-total");

  function nearBottom() {
    return stack.scrollHeight - stack.scrollTop - stack.clientHeight <= 140;
  }

  function followLatest(behavior) {
    stack.scrollTo({ top: stack.scrollHeight, behavior: behavior || "auto" });
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
      const unread = response.headers.get("X-ZENDOC-Unread-Count");
      if (unreadBadge && unread !== null) {
        unreadBadge.textContent = String(unread) + " Unread";
      }
      if (html !== lastHtml) {
        stack.innerHTML = html;
        lastHtml = html;
        if (shouldFollow) {
          followLatest("smooth");
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

  // Open a selected conversation at the newest available message without
  // forcing later jumps when the user intentionally scrolls upward.
  followLatest("auto");
  schedule();
})();
