(() => {
  const root = document.querySelector("[data-zendoc-call]");
  if (!root) return;

  const statusEl = document.getElementById("call-status");
  const detailEl = document.getElementById("call-detail");
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
  let remoteDescriptionApplied = false;

  let iceServers = [];
  try { iceServers = JSON.parse(root.dataset.iceServers || "[]"); } catch (_) {}

  const setStatus = (label, detail = "") => {
    if (statusEl) statusEl.textContent = label;
    if (detailEl && detail) detailEl.textContent = detail;
  };

  async function postForm(url, values) {
    const body = new FormData();
    body.set("csrf_token", csrfToken);
    Object.entries(values || {}).forEach(([key, value]) => body.set(key, String(value)));
    const response = await fetch(url, { method: "POST", body, credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data && data.error && data.error.message ? data.error.message : "Call request failed.");
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

  async function ensurePeer() {
    if (pc) return pc;
    pc = new RTCPeerConnection({ iceServers: iceServers });
    const stream = await ensureMedia();
    stream.getTracks().forEach(track => pc.addTrack(track, stream));
    pc.ontrack = event => {
      const streamValue = event.streams[0];
      if (callType === "video" && remoteVideo) remoteVideo.srcObject = streamValue;
      if (callType === "voice" && remoteAudio) remoteAudio.srcObject = streamValue;
      if (waiting) waiting.hidden = true;
    };
    pc.onicecandidate = async event => {
      if (!event.candidate || !callId) return;
      try {
        await postForm("/calls/" + callId + "/ice", {
          candidate_json: JSON.stringify(event.candidate.toJSON())
        });
      } catch (_) {}
    };
    pc.onconnectionstatechange = () => {
      if (!pc) return;
      const state = pc.connectionState;
      if (state === "connected") setStatus("Connected", "Peer-to-peer media connection established.");
      if (state === "failed" || state === "disconnected") {
        setStatus("Connection issue", "The peer connection was interrupted. TURN may be required on this network.");
      }
    };
    return pc;
  }

  async function startCall() {
    try {
      setStatus("Requesting permission…", "Allow microphone/camera access to start the call.");
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
      setStatus("Ringing", "Waiting for the other participant to answer.");
      beginPolling();
    } catch (error) {
      setStatus("Could not start call", error.message);
    }
  }

  async function acceptCall() {
    try {
      setStatus("Connecting…", "Preparing your browser media connection.");
      const peer = await ensurePeer();
      const response = await fetch("/calls/" + callId + "/state", { credentials: "same-origin", cache: "no-store" });
      const state = await response.json();
      if (!response.ok) throw new Error(state && state.error ? state.error.message : "Call state unavailable.");
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
      setStatus("Accepted", "Connecting peer-to-peer media…");
      beginPolling();
    } catch (error) {
      setStatus("Could not answer call", error.message);
    }
  }

  async function rejectCall() {
    try {
      await postForm("/calls/" + callId + "/answer", { accept: "0", answer_json: "" });
      setStatus("Rejected", "The call was rejected.");
      if (acceptBtn) acceptBtn.disabled = true;
      if (rejectBtn) rejectBtn.disabled = true;
    } catch (error) {
      setStatus("Could not reject call", error.message);
    }
  }

  async function applyState(call) {
    if (!call) return;
    const label = String(call.status || "unknown").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
    setStatus(label);
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
      } catch (_) {}
    }
    if (call.status === "ended" || call.status === "rejected") {
      stopPolling();
      closePeer();
    }
  }

  async function poll() {
    if (!callId) return;
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
    if (pc) pc.close();
    pc = null;
    if (localStream) localStream.getTracks().forEach(track => track.stop());
    localStream = null;
  }

  async function endCall() {
    try {
      if (callId) await postForm("/calls/" + callId + "/end", {});
    } catch (_) {}
    stopPolling();
    closePeer();
    setStatus("Ended", "Call ended.");
    if (endBtn) endBtn.disabled = true;
  }

  if (startBtn) startBtn.addEventListener("click", startCall);
  if (acceptBtn) acceptBtn.addEventListener("click", acceptCall);
  if (rejectBtn) rejectBtn.addEventListener("click", rejectCall);
  if (endBtn) endBtn.addEventListener("click", endCall);
  if (muteBtn) muteBtn.addEventListener("click", () => {
    if (!localStream) return;
    const tracks = localStream.getAudioTracks();
    const nextEnabled = tracks.some(track => !track.enabled);
    tracks.forEach(track => { track.enabled = nextEnabled; });
    muteBtn.textContent = nextEnabled ? "Mute" : "Unmute";
  });
  if (cameraBtn) cameraBtn.addEventListener("click", () => {
    if (!localStream) return;
    const tracks = localStream.getVideoTracks();
    const nextEnabled = tracks.some(track => !track.enabled);
    tracks.forEach(track => { track.enabled = nextEnabled; });
    cameraBtn.textContent = nextEnabled ? "Camera off" : "Camera on";
  });

  window.addEventListener("beforeunload", stopPolling);
  if (callId) beginPolling();
})();
