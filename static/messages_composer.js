(function () {
  "use strict";

  const form = document.querySelector("[data-zendoc-message-composer]");
  if (!form) return;

  const fileInput = document.getElementById("message-media-file");
  const voiceButton = document.getElementById("message-voice-note");
  const preview = document.getElementById("message-attachment-preview");
  const previewName = document.getElementById("message-attachment-name");
  const previewNote = document.getElementById("message-attachment-note");
  const audioPreview = document.getElementById("message-audio-preview");
  const clearButton = document.getElementById("message-attachment-clear");
  const status = document.getElementById("message-composer-status");

  let recorder = null;
  let stream = null;
  let chunks = [];
  let previewUrl = null;
  let recordedFile = null;

  function revokePreviewUrl() {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }
  }

  function stopTracks() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
  }

  function setPreview(file, note) {
    revokePreviewUrl();
    if (!file) {
      preview.hidden = true;
      audioPreview.hidden = true;
      audioPreview.removeAttribute("src");
      previewName.textContent = "Attachment ready";
      previewNote.textContent = "Private to conversation participants.";
      return;
    }

    preview.hidden = false;
    previewName.textContent = file.name || "Private attachment";
    previewNote.textContent = note || ((file.size / 1024 / 1024).toFixed(2) + " MiB · private conversation media");

    if (file.type && file.type.startsWith("audio/")) {
      previewUrl = URL.createObjectURL(file);
      audioPreview.src = previewUrl;
      audioPreview.hidden = false;
    } else {
      audioPreview.hidden = true;
      audioPreview.removeAttribute("src");
    }
  }

  function assignRecordedFile(file) {
    recordedFile = file;
    if (!fileInput) return false;
    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      return fileInput.files && fileInput.files.length === 1;
    } catch (_error) {
      return false;
    }
  }

  function clearAttachment() {
    recordedFile = null;
    if (fileInput) fileInput.value = "";
    setPreview(null);
    status.textContent = "Text, image, video and recorded voice notes remain private to conversation participants. Media limit: 25 MiB.";
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      recordedFile = null;
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        setPreview(null);
        return;
      }
      setPreview(file);
      status.textContent = "Attachment ready. Add an optional caption, then press Send.";
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", clearAttachment);
  }

  function supportedAudioType() {
    if (!window.MediaRecorder || typeof MediaRecorder.isTypeSupported !== "function") return "";
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/mp4"
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  async function beginRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      status.textContent = "Voice-note recording is not supported by this browser. You can still attach a supported audio file.";
      return;
    }

    try {
      const mimeType = supportedAudioType();
      stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      chunks = [];
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

      recorder.addEventListener("dataavailable", (event) => {
        if (event.data && event.data.size) chunks.push(event.data);
      });

      recorder.addEventListener("stop", () => {
        const recordedType = String(recorder && recorder.mimeType || mimeType || "audio/webm");
        const baseType = recordedType.split(";")[0].toLowerCase();
        const extension = baseType === "audio/ogg" ? "ogg" : baseType === "audio/mp4" ? "m4a" : "webm";
        const blob = new Blob(chunks, { type: baseType });
        chunks = [];
        stopTracks();

        if (!blob.size) {
          status.textContent = "The recording was empty. Try again.";
          voiceButton.setAttribute("aria-pressed", "false");
          voiceButton.classList.remove("recording");
          return;
        }

        const file = new File([blob], "zendoc-voice-note-" + Date.now() + "." + extension, { type: baseType });
        if (!assignRecordedFile(file)) {
          status.textContent = "This browser recorded the note but cannot attach it automatically. Use the Media button to attach an audio file instead.";
          setPreview(null);
          recordedFile = null;
        } else {
          setPreview(file, (blob.size / 1024).toFixed(0) + " KiB · recorded voice note · review before Send");
          status.textContent = "Voice note ready. Play it back if you want, then press Send. Nothing is sent automatically.";
        }
        voiceButton.setAttribute("aria-pressed", "false");
        voiceButton.classList.remove("recording");
        voiceButton.querySelector("span:last-child").textContent = "Voice note";
      });

      recorder.start();
      voiceButton.setAttribute("aria-pressed", "true");
      voiceButton.classList.add("recording");
      voiceButton.querySelector("span:last-child").textContent = "Stop recording";
      status.textContent = "Recording voice note… Press Stop recording when finished. Maximum upload size remains 25 MiB.";
    } catch (error) {
      stopTracks();
      recorder = null;
      status.textContent = error && error.name === "NotAllowedError"
        ? "Microphone permission was denied. Allow microphone access or send a text/media message instead."
        : "Voice-note recording could not start. You can still attach a supported audio file.";
      voiceButton.setAttribute("aria-pressed", "false");
      voiceButton.classList.remove("recording");
    }
  }

  if (voiceButton) {
    voiceButton.addEventListener("click", () => {
      if (recorder && recorder.state === "recording") {
        recorder.stop();
        return;
      }
      beginRecording();
    });
  }

  form.addEventListener("submit", (event) => {
    if (recorder && recorder.state === "recording") {
      event.preventDefault();
      status.textContent = "Stop the voice recording before sending.";
      return;
    }

    const file = fileInput && fileInput.files && fileInput.files[0];
    const body = form.querySelector("textarea[name='body']");
    if (!file && (!body || !body.value.trim())) {
      event.preventDefault();
      status.textContent = "Write a message or attach media before sending.";
    }
  });

  window.addEventListener("beforeunload", () => {
    if (recorder && recorder.state === "recording") recorder.stop();
    stopTracks();
    revokePreviewUrl();
  });
})();