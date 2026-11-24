(() => {
  const video = document.getElementById("pose-preview");
  const statusNode = document.getElementById("pose-status");
  const start = document.getElementById("pose-start");
  const stop = document.getElementById("pose-stop");
  const save = document.getElementById("pose-save");
  const exercise = document.getElementById("pose-exercise");
  const timerNode = document.getElementById("pose-timer");
  const feedback = document.getElementById("pose-feedback");
  let stream = null;
  let timer = null;
  let seconds = 0;

  const update = () => {
    timerNode.textContent = `${seconds}s`;
  };
  const stopStream = () => {
    if (timer) clearInterval(timer);
    timer = null;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    if (video) video.srcObject = null;
    statusNode.textContent = "Camera off. Media tracks released.";
    update();
  };

  if (start) start.addEventListener("click", async () => {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      video.srcObject = stream;
      seconds = 0;
      feedback.textContent = "Camera preview is active. Automatic pose analysis and rep counting are not connected in this prototype.";
      statusNode.textContent = "Camera active. Frames are not uploaded.";
      timer = setInterval(() => {
        seconds += 1;
        update();
      }, 1000);
      update();
    } catch (error) {
      statusNode.textContent = "Camera permission was denied or unavailable.";
    }
  });
  if (stop) stop.addEventListener("click", stopStream);
  if (save) save.addEventListener("click", async () => {
    const payload = new URLSearchParams({
      csrf_token: window.ZENDOC_CSRF || "",
      exercise: exercise.value,
      reps: "0",
      sets: "0",
      duration_seconds: String(seconds),
      confidence: "",
      feedback: feedback.textContent
    });
    const response = await fetch("/fitness/pose-coach", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: payload
    });
    statusNode.textContent = response.ok ? "Session saved." : "Could not save this session.";
  });
  window.addEventListener("beforeunload", stopStream);
  update();
})();
