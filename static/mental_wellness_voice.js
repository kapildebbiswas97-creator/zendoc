(() => {
  "use strict";

  const button = document.getElementById("wellness-voice-input-toggle");
  const status = document.getElementById("wellness-voice-input-status");
  const input = document.getElementById("wellness-guidance-context");
  if (!button || !status || !input) return;

  const form = input.closest("form");
  const csrfInput = form && form.querySelector("input[name='csrf_token']");
  const endpoint = "/edgecare/asr/transcribe";
  const BrowserSpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition || null;

  const maxClientBytes = 8 * 1024 * 1024;
  const maxRecordingMs = 30 * 1000;
  let recorder = null;
  let stream = null;
  let chunks = [];
  let stopTimer = null;
  let busy = false;
  let browserFallback = false;

  const setButtonState = (recording = false, processing = false) => {
    button.disabled = processing;
    button.setAttribute("aria-pressed", String(recording));
    button.setAttribute("aria-busy", String(processing));
    button.textContent = processing
      ? "Transcribing…"
      : recording
        ? "Stop recording"
        : browserFallback
          ? "Use browser dictation"
          : "Use voice input";
  };

  const stopTracks = () => {
    if (!stream) return;
    stream.getTracks().forEach((track) => track.stop());
    stream = null;
  };

  const clearTimer = () => {
    if (!stopTimer) return;
    window.clearTimeout(stopTimer);
    stopTimer = null;
  };

  const appendTranscript = (value) => {
    const transcript = String(value || "").trim();
    if (!transcript) return;
    const existing = input.value.trim();
    const combined = `${existing}${existing ? " " : ""}${transcript}`;
    const limit = Number(input.maxLength) > 0 ? Number(input.maxLength) : 1000;
    input.value = combined.slice(0, limit);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.focus();
  };

  const preferredMimeType = () => {
    if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== "function") {
      return "";
    }
    return [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ].find((candidate) => MediaRecorder.isTypeSupported(candidate)) || "";
  };

  const extensionFor = (mimeType) => {
    const value = String(mimeType || "").toLowerCase();
    if (value.includes("ogg")) return "ogg";
    if (value.includes("mp4")) return "mp4";
    if (value.includes("mpeg")) return "mp3";
    if (value.includes("wav")) return "wav";
    return "webm";
  };

  const startBrowserDictation = () => {
    if (!BrowserSpeechRecognition || busy) {
      status.textContent =
        "Browser dictation is unavailable here. You can continue typing instead.";
      return;
    }

    const recognition = new BrowserSpeechRecognition();
    recognition.lang = document.documentElement.lang || navigator.language || "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;

    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    status.textContent =
      "Listening with your browser speech service. Review the transcript before requesting guidance.";

    recognition.onresult = (event) => {
      const transcript =
        event.results && event.results[0] && event.results[0][0]
          ? event.results[0][0].transcript
          : "";
      appendTranscript(transcript);
      status.textContent =
        "Browser transcript added. Review or edit it, then press Review safe next steps.";
    };
    recognition.onerror = () => {
      status.textContent =
        "Browser dictation could not complete. You can try again or type instead.";
    };
    recognition.onend = () => {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      setButtonState(false, false);
    };

    try {
      recognition.start();
    } catch (_error) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      status.textContent =
        "Browser dictation could not start. You can continue typing instead.";
    }
  };

  const transcribe = async (blob) => {
    if (!csrfInput || !csrfInput.value) {
      status.textContent =
        "Your session token is unavailable. Refresh the page before using voice input.";
      return;
    }
    if (!blob || !blob.size) {
      status.textContent = "No usable audio was captured. Try again or type instead.";
      return;
    }
    if (blob.size > maxClientBytes) {
      status.textContent = "That recording is too large. Record a shorter message.";
      return;
    }

    busy = true;
    setButtonState(false, true);
    status.textContent =
      "Transcribing through the configured ZENDOC speech runtime…";

    const data = new FormData();
    data.append("csrf_token", csrfInput.value);
    data.append("audio", blob, `wellness.${extensionFor(blob.type)}`);

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body: data,
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
        if (
          response.status === 503 ||
          ["disabled", "integration_required", "model_not_configured", "model_missing", "provider_unavailable"].includes(category)
        ) {
          if (BrowserSpeechRecognition) {
            browserFallback = true;
            status.textContent =
              "Local speech recognition is not ready. Press Use browser dictation to use your browser speech service instead.";
          } else {
            status.textContent =
              "Local speech recognition is not ready. You can continue typing instead.";
          }
        } else if (response.status === 401 || response.status === 403) {
          status.textContent =
            "Your session must be refreshed before voice input can be used.";
        } else {
          status.textContent =
            "Voice transcription could not complete. Try a shorter recording or type instead.";
        }
        return;
      }

      appendTranscript(result.text);
      status.textContent =
        "Transcript added. Review or edit it before pressing Review safe next steps.";
    } catch (_error) {
      status.textContent =
        "The speech runtime could not be reached. You can continue typing instead.";
    } finally {
      busy = false;
      setButtonState(false, false);
    }
  };

  const finishRecording = () => {
    clearTimer();
    if (recorder && recorder.state !== "inactive") recorder.stop();
  };

  const startRecording = async () => {
    if (busy) return;

    if (
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia ||
      !window.MediaRecorder
    ) {
      if (BrowserSpeechRecognition) {
        browserFallback = true;
        setButtonState(false, false);
        startBrowserDictation();
      } else {
        status.textContent =
          "Voice input is not supported by this browser. You can continue typing instead.";
      }
      return;
    }

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
      recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("error", () => {
        clearTimer();
        stopTracks();
        recorder = null;
        setButtonState(false, false);
        status.textContent =
          "Audio recording failed. Try again or type your situation instead.";
      });
      recorder.addEventListener("stop", async () => {
        clearTimer();
        stopTracks();
        const type =
          recorder && recorder.mimeType
            ? recorder.mimeType.split(";", 1)[0]
            : "audio/webm";
        const blob = new Blob(chunks, { type });
        chunks = [];
        recorder = null;
        await transcribe(blob);
      });

      recorder.start(500);
      setButtonState(true, false);
      status.textContent =
        "Recording. Press Stop when finished. Nothing is submitted automatically.";
      stopTimer = window.setTimeout(() => {
        if (recorder && recorder.state !== "inactive") {
          status.textContent =
            "30-second recording limit reached. Transcribing now…";
          finishRecording();
        }
      }, maxRecordingMs);
    } catch (error) {
      stopTracks();
      setButtonState(false, false);
      const denied =
        error &&
        (error.name === "NotAllowedError" || error.name === "SecurityError");
      status.textContent = denied
        ? "Microphone permission was denied. You can continue typing instead."
        : "Microphone capture could not start. You can continue typing instead.";
    }
  };

  button.addEventListener("click", () => {
    if (browserFallback) {
      startBrowserDictation();
      return;
    }
    if (recorder && recorder.state !== "inactive") {
      status.textContent = "Recording stopped. Transcribing…";
      finishRecording();
      return;
    }
    startRecording();
  });

  window.addEventListener("pagehide", () => {
    clearTimer();
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.stop();
      } catch (_error) {
        // Page is closing.
      }
    }
    stopTracks();
  });

  setButtonState(false, false);
})();
