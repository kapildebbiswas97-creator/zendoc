(() => {
  "use strict";

  const root = document.querySelector("[data-zendoc-call]");
  if (!root) return;

  const statusEl = document.getElementById("call-status");
  const detailEl = document.getElementById("call-detail");
  const sessionStateEl = document.getElementById("call-session-state");
  const mediaPathEl = document.getElementById("call-media-path");
  const rttEl = document.getElementById("call-rtt");
  const durationEl = document.getElementById("call-duration");
  const startBtn = document.getElementById("start-call");
  const acceptBtn = document.getElementById("accept-call");
  const rejectBtn = document.getElementById("reject-call");
  const endBtn = document.getElementById("end-call");
  const muteBtn = document.getElementById("mute-call");
  const cameraBtn = document.getElementById("camera-call");
  const localVideo = document.getElementById("local-video");
  const remoteVideo = document.getElementById("remote-video");
  const remoteAudio = document.getElementById("remote-audio");
  const waiting = document.getElementById("remote-waiting");

  const conversationId = Number(root.dataset.conversationId);
  const callType = root.dataset.callType;
  const actorId = Number(root.dataset.actorId);
  const csrfToken = root.dataset.csrfToken;
  let callId = Number(root.dataset.callId || 0);
  let initiator = root.dataset.initiator === "1";
  let pc = null;
  let localStream = null;
  let afterCandidateId = 0;
  let pollTimer = null;
  let statsTimer = null;
  let durationTimer = null;
  let connectedAt = 0;
  let remoteDescriptionApplied = false;
  let terminal = false;

  let iceServers = [];
  try {
    iceServers = JSON.parse(root.dataset.iceServers || "[]");
  } catch (_error) {
    iceServers = [];
  }

  function setStatus(label, detail) {
    root.dataset.callState = String(label || "").toLowerCase().replaceAll(" ", "-");
    if (statusEl) statusEl.textContent = label;
    if (sessionStateEl) sessionStateEl.textContent = label;
    if (detailEl && detail) detailEl.textContent = detail;
  }

  function formatDuration(seconds) {
    const value = Math.max(0, Math.floor(seconds));
    const hours = Math.floor(value / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const secs = value % 60;
    if (hours) {
      return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
    }
    return [minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
  }

  function startDurationClock() {
    if (!connectedAt) connectedAt = Date.now();
    if (durationTimer) return;
    const update = () => {
      if (durationEl) durationEl.textContent = formatDuration((Date.now() - connectedAt) / 1000);
    };
    update();
    durationTimer = window.setInterval(update, 1000);
  }

  function stopDurationClock() {
    if (durationTimer) window.clearInterval(durationTimer);
    durationTimer = null;
  }

  async function postForm(url, values, options) {
    const body = new FormData();
    body.set("csrf_token", csrfToken);
    Object.entries(values || {}).forEach(([key, value]) => body.set(key, String(value)));
    const response = await fetch(url, {
      method: "POST",
      body,
      credentials: "same-origin",
      keepalive: Boolean(options && options.keepalive)
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data && data.error && data.error.message ? data.error.message : "Call request failed.");
    }
    return data;
  }

  async function ensureMedia() {
    if (localStream) return localStream;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("This browser does not provide camera/microphone access.");
    }

    localStream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: callType === "video"
    });

    if (localVideo && callType === "video") localVideo.srcObject = localStream;
    if (muteBtn) muteBtn.disabled = false;
    if (cameraBtn) cameraBtn.disabled = false;
    return localStream;
  }

  async function updateConnectionDiagnostics() {
    if (!pc || pc.connectionState !== "connected" || typeof pc.getStats !== "function") return;
    try {
      const reports = await pc.getStats();
      let selectedPair = null;
      reports.forEach((report) => {
        if (
          report.type === "candidate-pair" &&
          report.state === "succeeded" &&
          (report.nominated || report.selected)
        ) {
          selectedPair = report;
        }
      });

      if (!selectedPair) return;
      const local = reports.get(selectedPair.localCandidateId);
      const remote = reports.get(selectedPair.remoteCandidateId);
      const usesRelay = Boolean(
        (local && local.candidateType === "relay") ||
        (remote && remote.candidateType === "relay")
      );

      if (mediaPathEl) {
        mediaPathEl.textContent = usesRelay ? "TURN relay" : "Direct / STUN path";
      }

      if (rttEl && typeof selectedPair.currentRoundTripTime === "number") {
        rttEl.textContent = Math.round(selectedPair.currentRoundTripTime * 1000) + " ms";
      }
    } catch (_error) {
      // Diagnostics are optional and must never interfere with the call.
    }
  }

  function beginStats() {
    if (statsTimer) return;
    updateConnectionDiagnostics();
    statsTimer = window.setInterval(updateConnectionDiagnostics, 2500);
  }

  function stopStats() {
    if (statsTimer) window.clearInterval(statsTimer);
    statsTimer = null;
  }

  async function ensurePeer() {
    if (pc) return pc;

    pc = new RTCPeerConnection({ iceServers });
    const stream = await ensureMedia();
    stream.getTracks().forEach((track) => pc.addTrack(track, stream));

    pc.ontrack = (event) => {
      const streamValue = event.streams[0];
      if (callType === "video" && remoteVideo) {
        remoteVideo.srcObject = streamValue;
        remoteVideo.hidden = false;
      }
      if (callType === "voice" && remoteAudio) remoteAudio.srcObject = streamValue;
      if (waiting) waiting.hidden = true;
    };

    pc.onicecandidate = async (event) => {
      if (!event.candidate || !callId) return;
      try {
        await postForm("/calls/" + callId + "/ice", {
          candidate_json: JSON.stringify(event.candidate.toJSON())
        });
      } catch (_error) {
        // Polling may recover another candidate. Do not fabricate success.
      }
    };

    pc.onconnectionstatechange = () => {
      if (!pc) return;
      const state = pc.connectionState;

      if (state === "new") {
        setStatus("Preparing", "Preparing the authenticated browser media connection.");
      } else if (state === "connecting") {
        setStatus("Connecting", "Negotiating the browser-to-browser media path.");
      } else if (state === "connected") {
        setStatus("Connected", "Browser peer connection established.");
        startDurationClock();
        beginStats();
      } else if (state === "disconnected") {
        setStatus("Reconnecting", "The media path was interrupted. The browser is attempting to recover it.");
        stopStats();
      } else if (state === "failed") {
        setStatus("Connection failed", "The browser could not establish or recover the media path. A working TURN relay may be required on this network.");
        stopStats();
      } else if (state === "closed") {
        if (!terminal) setStatus("Ended", "The browser peer connection is closed.");
      }
    };

    pc.oniceconnectionstatechange = () => {
      if (!pc) return;
      if (pc.iceConnectionState === "checking" && pc.connectionState !== "connected") {
        setStatus("Connecting", "Checking available network paths…");
      }
    };

    return pc;
  }

  async function startCall() {
    try {
      setStatus("Requesting permission", "Allow microphone" + (callType === "video" ? " and camera" : "") + " access to start the call.");
      const peer = await ensurePeer();
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const response = await postForm("/calls/create", {
        conversation_id: conversationId,
        call_type: callType,
        offer_json: JSON.stringify(peer.localDescription)
      });

      callId = Number(response.call.id);
      initiator = true;
      history.replaceState({}, "", "/calls/" + callId);
      if (endBtn) endBtn.disabled = false;
      if (startBtn) startBtn.disabled = true;
      setStatus("Ringing", "Waiting for " + (response.call.callee_name || "the other participant") + " to answer.");
      beginPolling();
    } catch (error) {
      setStatus("Could not start call", error.message);
    }
  }

  async function acceptCall() {
    try {
      setStatus("Requesting permission", "Allow browser media access to answer this call.");
      const peer = await ensurePeer();
      const response = await fetch("/calls/" + callId + "/state", {
        credentials: "same-origin",
        cache: "no-store"
      });
      const state = await response.json();
      if (!response.ok) throw new Error(state && state.error ? state.error.message : "Call state unavailable.");
      if (!state.call.offer) throw new Error("The caller's media offer is no longer available.");

      await peer.setRemoteDescription(state.call.offer);
      remoteDescriptionApplied = true;
      const answer = await peer.createAnswer();
      await peer.setLocalDescription(answer);
      await postForm("/calls/" + callId + "/answer", {
        accept: "1",
        answer_json: JSON.stringify(peer.localDescription)
      });

      if (acceptBtn) acceptBtn.disabled = true;
      if (rejectBtn) rejectBtn.disabled = true;
      if (endBtn) endBtn.disabled = false;
      setStatus("Connecting", "Call accepted. Negotiating the media path…");
      beginPolling();
    } catch (error) {
      setStatus("Could not answer call", error.message);
    }
  }

  async function rejectCall() {
    try {
      await postForm("/calls/" + callId + "/answer", { accept: "0", answer_json: "" });
      terminal = true;
      setStatus("Rejected", "The call was rejected.");
      if (acceptBtn) acceptBtn.disabled = true;
      if (rejectBtn) rejectBtn.disabled = true;
      if (endBtn) endBtn.disabled = true;
      stopPolling();
      closePeer();
    } catch (error) {
      setStatus("Could not reject call", error.message);
    }
  }

  async function applyState(call) {
    if (!call) return;

    if (call.status === "ringing" && (!pc || pc.connectionState !== "connected")) {
      setStatus("Ringing", initiator ? "Waiting for the other participant to answer." : "Incoming call waiting for your response.");
    } else if (call.status === "accepted" && (!pc || pc.connectionState !== "connected")) {
      setStatus("Connecting", "Call accepted. Negotiating the media path…");
    }

    if (initiator && call.answer && !remoteDescriptionApplied) {
      const peer = await ensurePeer();
      await peer.setRemoteDescription(call.answer);
      remoteDescriptionApplied = true;
    }

    for (const item of call.candidates || []) {
      afterCandidateId = Math.max(afterCandidateId, Number(item.id || 0));
      if (Number(item.user_id) === actorId) continue;
      try {
        const peer = await ensurePeer();
        await peer.addIceCandidate(item.candidate);
      } catch (_error) {
        // Invalid/stale remote candidates are ignored by the browser.
      }
    }

    if (["ended", "rejected", "missed"].includes(call.status)) {
      terminal = true;
      const labels = {
        ended: ["Ended", "Call ended."],
        rejected: ["Rejected", "The other participant rejected the call."],
        missed: ["Missed", "The call was not answered before it expired."]
      };
      setStatus(labels[call.status][0], labels[call.status][1]);
      if (endBtn) endBtn.disabled = true;
      stopPolling();
      closePeer();
    }
  }

  async function poll() {
    if (!callId || terminal) return;
    try {
      const response = await fetch("/calls/" + callId + "/state?after_candidate_id=" + afterCandidateId, {
        credentials: "same-origin",
        cache: "no-store"
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data && data.error ? data.error.message : "Call state unavailable.");
      await applyState(data.call);
    } catch (error) {
      setStatus("Call state unavailable", error.message);
    }
  }

  function beginPolling() {
    stopPolling();
    poll();
    pollTimer = window.setInterval(poll, 1000);
  }

  function stopPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  function closePeer() {
    stopStats();
    stopDurationClock();

    if (pc) pc.close();
    pc = null;

    if (localStream) localStream.getTracks().forEach((track) => track.stop());
    localStream = null;

    if (localVideo) localVideo.srcObject = null;
    if (remoteVideo) remoteVideo.srcObject = null;
    if (remoteAudio) remoteAudio.srcObject = null;
  }

  async function endCall() {
    try {
      if (callId && !terminal) await postForm("/calls/" + callId + "/end", {});
    } catch (_error) {
      // The local media path is still closed even if the final server update fails.
    }
    terminal = true;
    stopPolling();
    closePeer();
    setStatus("Ended", "Call ended.");
    if (endBtn) endBtn.disabled = true;
  }

  if (startBtn) startBtn.addEventListener("click", startCall);
  if (acceptBtn) acceptBtn.addEventListener("click", acceptCall);
  if (rejectBtn) rejectBtn.addEventListener("click", rejectCall);
  if (endBtn) endBtn.addEventListener("click", endCall);

  if (muteBtn) {
    muteBtn.addEventListener("click", () => {
      if (!localStream) return;
      const tracks = localStream.getAudioTracks();
      const willEnable = tracks.some((track) => !track.enabled);
      tracks.forEach((track) => { track.enabled = willEnable; });
      muteBtn.textContent = willEnable ? "Mute" : "Unmute";
      muteBtn.setAttribute("aria-pressed", String(!willEnable));
    });
  }

  if (cameraBtn) {
    cameraBtn.addEventListener("click", () => {
      if (!localStream) return;
      const tracks = localStream.getVideoTracks();
      const willEnable = tracks.some((track) => !track.enabled);
      tracks.forEach((track) => { track.enabled = willEnable; });
      cameraBtn.textContent = willEnable ? "Camera off" : "Camera on";
      cameraBtn.setAttribute("aria-pressed", String(!willEnable));
    });
  }

  window.addEventListener("pagehide", (event) => {
    stopPolling();
    if (event.persisted || terminal || !callId) {
      closePeer();
      return;
    }

    // Best effort only. The server also expires stale sessions, so navigation
    // never justifies claiming an end update succeeded when it may not have.
    try {
      const body = new FormData();
      body.set("csrf_token", csrfToken);
      fetch("/calls/" + callId + "/end", {
        method: "POST",
        body,
        credentials: "same-origin",
        keepalive: true
      });
    } catch (_error) {}
    closePeer();
  });

  if (callId) beginPolling();
})();