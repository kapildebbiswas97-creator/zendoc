(() => {
  const video = document.getElementById("telehealth-preview");
  const statusNode = document.getElementById("telehealth-status");
  const join = document.getElementById("telehealth-join");
  const leave = document.getElementById("telehealth-leave");
  const mute = document.getElementById("telehealth-mute");
  const camera = document.getElementById("telehealth-camera");
  let stream = null;

  const setStatus = (text) => {
    if (statusNode) statusNode.textContent = text;
  };
  const stopStream = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    if (video) video.srcObject = null;
  };

  if (join) join.addEventListener("click", async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      video.srcObject = stream;
      setStatus("Connected locally. Signaling provider integration required for production calls.");
    } catch (error) {
      setStatus("Camera or microphone permission was denied or unavailable.");
    }
  });
  if (leave) leave.addEventListener("click", () => {
    stopStream();
    setStatus("Left room. Camera and microphone stopped.");
  });
  if (mute) mute.addEventListener("click", () => {
    if (!stream) return;
    stream.getAudioTracks().forEach((track) => { track.enabled = !track.enabled; });
    mute.textContent = stream.getAudioTracks().some((track) => track.enabled) ? "Mute" : "Unmute";
  });
  if (camera) camera.addEventListener("click", () => {
    if (!stream) return;
    stream.getVideoTracks().forEach((track) => { track.enabled = !track.enabled; });
    camera.textContent = stream.getVideoTracks().some((track) => track.enabled) ? "Camera Off" : "Camera On";
  });
  window.addEventListener("beforeunload", stopStream);
})();
