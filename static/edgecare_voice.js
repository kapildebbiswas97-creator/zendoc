(() => {
  const button = document.getElementById("edgecare-voice-input-toggle");
  const status = document.getElementById("edgecare-voice-input-status");
  const input = document.getElementById("assistant-message");
  if (!button || !status || !input) return;

  const form = input.closest("form");
  const csrfInput = form && form.querySelector("input[name='csrf_token']");
  const endpoint = "/edgecare/asr/transcribe";
  const BrowserSpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;

  const ensureHidden = (name, value = "") => {
    if (!form) return null;
    let field = form.querySelector(`input[name='${name}']`);
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = name;
      form.appendChild(field);
    }
    if (value !== undefined) field.value = String(value ?? "");
    return field;
  };

  const inputChannel = ensureHidden("input_channel", "typed");
  const asrAuditLogId = ensureHidden("asr_audit_log_id", "");
  const maxClientBytes = 8 * 1024 * 1024;
  const maxRecordingMs = 30 * 1000;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    button.disabled = true;
    status.textContent = "Local voice capture is not available in this browser. Type your request below.";
    return;
  }

  let recorder = null;
  let stream = null;
  let chunks = [];
  let stopTimer = null;
  let busy = false;
  let browserFallbackMode = false;
  let browserRecognition = null;

  const setButtonState = (recording, processing = false) => {
    button.setAttribute("aria-pressed", String(recording));
    button.setAttribute("aria-busy", String(processing));
    button.disabled = processing;
    button.textContent = processing
      ? "Transcribing locally…"
      : recording
        ? "Stop recording"
        : browserFallbackMode
          ? "Use browser dictation"
          : "Use voice input";
  };

  const stopTracks = () => {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  };

  const clearStopTimer = () => {
    if (stopTimer) {
      window.clearTimeout(stopTimer);
      stopTimer = null;
    }
  };

  const preferredMimeType = () => {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ];
    return candidates.find((value) => MediaRecorder.isTypeSupported(value)) || "";
  };

  const extensionFor = (mimeType) => {
    const value = String(mimeType || "").toLowerCase();
    if (value.includes("ogg")) return "ogg";
    if (value.includes("mp4")) return "mp4";
    if (value.includes("mpeg")) return "mp3";
    if (value.includes("wav")) return "wav";
    return "webm";
  };

  const appendTranscript = (text) => {
    const transcript = String(text || "").trim();
    if (!transcript) return;
    const existing = input.value.trim();
    const combined = `${existing}${existing ? " " : ""}${transcript}`;
    const limit = Number(input.maxLength) > 0 ? Number(input.maxLength) : 1500;
    input.value = combined.slice(0, limit);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  };

  const startBrowserDictation = () => {
    if (!BrowserSpeechRecognition || busy) {
      status.textContent = "Browser dictation is not available here. Type your request below.";
      return;
    }

    try {
      browserRecognition = new BrowserSpeechRecognition();
      browserRecognition.lang = document.documentElement.lang || navigator.language || "en-IN";
      browserRecognition.interimResults = false;
      browserRecognition.continuous = false;
      browserRecognition.maxAlternatives = 1;

      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      status.textContent = "Listening with your browser speech service… Review the transcript before pressing Send.";

      browserRecognition.onresult = (event) => {
        const transcript = event.results && event.results[0] && event.results[0][0]
          ? event.results[0][0].transcript
          : "";
        appendTranscript(transcript);
        if (inputChannel) inputChannel.value = "browser_speech_transcript";
        if (asrAuditLogId) asrAuditLogId.value = "";
        status.textContent = "Browser transcript added. Review it, then press Send when ready.";
      };
      browserRecognition.onerror = () => {
        status.textContent = "Browser dictation could not complete. You can try again or type your request.";
      };
      browserRecognition.onend = () => {
        browserRecognition = null;
        button.disabled = false;
        button.removeAttribute("aria-busy");
        setButtonState(false, false);
      };
      browserRecognition.start();
    } catch (_error) {
      browserRecognition = null;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      status.textContent = "Browser dictation could not start. Type your request below.";
      setButtonState(false, false);
    }
  };

  const transcribe = async (blob) => {
    if (!csrfInput || !csrfInput.value) {
      status.textContent = "Your session token is unavailable. Refresh the page, then try again.";
      return;
    }
    if (!blob || !blob.size) {
      status.textContent = "No usable audio was captured. Try again or type your request.";
      return;
    }
    if (blob.size > maxClientBytes) {
      status.textContent = "That recording is too large. Record a shorter message or type your request.";
      return;
    }

    busy = true;
    setButtonState(false, true);
    status.textContent = "Sending this clip only to the configured ZENDOC local speech runtime…";

    const formData = new FormData();
    formData.append("csrf_token", csrfInput.value);
    formData.append("audio", blob, `voice.${extensionFor(blob.type)}`);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });

      let payload = null;
      try {
        payload = await response.json();
      } catch (_error) {
        payload = null;
      }

      const result = payload && payload.result;
      if (!response.ok || !result || !result.success) {
        const category = result && result.error_category;
        if (response.status === 503 || category === "disabled" || category === "model_not_configured") {
          if (BrowserSpeechRecognition) {
            browserFallbackMode = true;
            status.textContent = "Local speech is not ready. Press “Use browser dictation” if you want to use your browser’s speech service instead; review the transcript before Send.";
          } else {
            status.textContent = "Local speech recognition is not ready and this browser has no dictation fallback. Type your request below.";
          }
        } else if (response.status === 401 || response.status === 403) {
          status.textContent = "Your session needs to be refreshed before local voice input can be used.";
        } else {
          status.textContent = "Local transcription could not complete. Type your request or try a shorter recording.";
        }
        return;
      }

      appendTranscript(result.text);
      if (inputChannel) inputChannel.value = "local_asr_transcript";
      if (asrAuditLogId) asrAuditLogId.value = String(result.audit_log_id || "");
      status.textContent = `Local transcript added${result.model ? ` using ${result.model}` : ""}. Review it, then press Send when ready.`;
    } catch (_error) {
      status.textContent = "The local speech runtime could not be reached. Type your request below.";
    } finally {
      busy = false;
      setButtonState(false, false);
    }
  };

  const finishRecording = () => {
    clearStopTimer();
    if (recorder && recorder.state !== "inactive") recorder.stop();
  };

  const startRecording = async () => {
    if (busy) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
        video: false,
      });
      chunks = [];
      const mimeType = preferredMimeType();
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      });

      recorder.addEventListener("error", () => {
        clearStopTimer();
        stopTracks();
        setButtonState(false, false);
        status.textContent = "Audio recording failed. Type your request or try again.";
      });

      recorder.addEventListener("stop", async () => {
        clearStopTimer();
        stopTracks();
        const type = recorder && recorder.mimeType ? recorder.mimeType.split(";", 1)[0] : "audio/webm";
        const blob = new Blob(chunks, { type });
        chunks = [];
        recorder = null;
        await transcribe(blob);
      });

      recorder.start(500);
      setButtonState(true, false);
      status.textContent = "Recording locally. Press Stop when finished; nothing is sent until recording stops.";
      stopTimer = window.setTimeout(() => {
        if (recorder && recorder.state !== "inactive") {
          status.textContent = "30-second recording limit reached. Transcribing locally…";
          finishRecording();
        }
      }, maxRecordingMs);
    } catch (error) {
      stopTracks();
      setButtonState(false, false);
      const denied = error && (error.name === "NotAllowedError" || error.name === "SecurityError");
      status.textContent = denied
        ? "Microphone permission was denied. Type your request below."
        : "Microphone capture could not start. Type your request below.";
    }
  };

  button.addEventListener("click", () => {
    if (browserFallbackMode) {
      startBrowserDictation();
      return;
    }
    if (recorder && recorder.state !== "inactive") {
      status.textContent = "Recording stopped. Transcribing locally…";
      finishRecording();
      return;
    }
    startRecording();
  });

  window.addEventListener("pagehide", () => {
    clearStopTimer();
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch (_error) {
        // Page is closing; no further action is required.
      }
    }
    stopTracks();
  });

  setButtonState(false, false);
  status.textContent = "Voice input tries the configured ZENDOC local speech runtime first. If it is unavailable, an explicit browser-dictation fallback may be offered. Nothing auto-sends; review the transcript, then press Send.";
})();
