(() => {
  "use strict";

  const banner = document.getElementById("zendoc-incoming-call");
  if (!banner || document.querySelector("[data-zendoc-call]")) return;

  const incomingUrl = banner.dataset.incomingCallsUrl;
  const csrfToken = banner.dataset.csrfToken;
  const nameEl = document.getElementById("zendoc-incoming-call-name");
  const kindEl = document.getElementById("zendoc-incoming-call-kind");
  const timeEl = document.getElementById("zendoc-incoming-call-time");
  const avatarEl = document.getElementById("zendoc-incoming-call-avatar");
  const openLink = document.getElementById("zendoc-incoming-call-open");
  const rejectBtn = document.getElementById("zendoc-incoming-call-reject");
  const dismissBtn = document.getElementById("zendoc-incoming-call-dismiss");

  let active = true;
  let inFlight = false;
  let currentCall = null;
  let dismissedCallId = 0;
  let announcedCallId = 0;
  let pollTimer = null;

  function labelCallType(value) {
    return String(value || "voice").toLowerCase() === "video" ? "Incoming video call" : "Incoming voice call";
  }

  function hideBanner() {
    banner.hidden = true;
    banner.removeAttribute("data-call-id");
  }

  function showCall(call) {
    currentCall = call;
    const id = Number(call.id || 0);
    if (!id || id === dismissedCallId) {
      hideBanner();
      return;
    }

    const person = String(call.initiator_name || "ZENDOC contact").trim();
    nameEl.textContent = person;
    kindEl.textContent = labelCallType(call.call_type);
    timeEl.textContent = "Waiting for your response";
    avatarEl.textContent = (person[0] || "Z").toUpperCase();
    openLink.href = "/calls/" + id;
    banner.dataset.callId = String(id);
    banner.hidden = false;

    if (announcedCallId !== id) {
      announcedCallId = id;
      if (navigator.vibrate) {
        try { navigator.vibrate([180, 100, 180]); } catch (_error) {}
      }
    }
  }

  async function loadIncoming() {
    if (!active || inFlight || document.hidden) return;
    inFlight = true;
    try {
      const response = await fetch(incomingUrl, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { "X-Requested-With": "XMLHttpRequest" }
      });

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          active = false;
          hideBanner();
        }
        return;
      }

      const data = await response.json();
      const calls = Array.isArray(data.calls) ? data.calls : [];
      const first = calls[0] || null;

      if (!first) {
        currentCall = null;
        dismissedCallId = 0;
        hideBanner();
        return;
      }

      showCall(first);
    } catch (_error) {
      // Transient failure must not fabricate a call or interrupt the page.
    } finally {
      inFlight = false;
    }
  }

  async function rejectCurrentCall() {
    if (!currentCall) return;
    const id = Number(currentCall.id || 0);
    if (!id) return;

    rejectBtn.disabled = true;
    timeEl.textContent = "Rejecting…";

    const body = new FormData();
    body.set("csrf_token", csrfToken);
    body.set("accept", "0");
    body.set("answer_json", "");

    try {
      const response = await fetch("/calls/" + id + "/answer", {
        method: "POST",
        body,
        credentials: "same-origin"
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data && data.error && data.error.message ? data.error.message : "Call could not be rejected.");
      }

      dismissedCallId = id;
      currentCall = null;
      hideBanner();
      window.setTimeout(loadIncoming, 350);
    } catch (error) {
      timeEl.textContent = error.message || "Could not reject this call.";
    } finally {
      rejectBtn.disabled = false;
    }
  }

  dismissBtn.addEventListener("click", () => {
    if (currentCall) dismissedCallId = Number(currentCall.id || 0);
    hideBanner();
  });

  rejectBtn.addEventListener("click", rejectCurrentCall);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) loadIncoming();
  });

  window.addEventListener("beforeunload", () => {
    active = false;
    if (pollTimer) window.clearInterval(pollTimer);
  });

  loadIncoming();
  pollTimer = window.setInterval(loadIncoming, 4000);
})();