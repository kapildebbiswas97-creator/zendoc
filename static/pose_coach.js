(() => {
  const video = document.getElementById("pose-preview");
  const statusNode = document.getElementById("pose-status");
  const start = document.getElementById("pose-start");
  const stop = document.getElementById("pose-stop");
  const save = document.getElementById("pose-save");
  const exercise = document.getElementById("pose-exercise");
  const repsNode = document.getElementById("pose-reps");
  const setsNode = document.getElementById("pose-sets");
  const timerNode = document.getElementById("pose-timer");
  const confidenceNode = document.getElementById("pose-confidence");
  const feedback = document.getElementById("pose-feedback");
  let stream = null;
  let timer = null;
  let seconds = 0;
  let reps = 0;
  let sets = 0;

  const update = () => {
    repsNode.textContent = String(reps);
    setsNode.textContent = String(sets);
    timerNode.textContent = `${seconds}s`;
    confidenceNode.textContent = stream ? "72%" : "0%";
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
      reps = 0;
      sets = 0;
      feedback.textContent = "Camera running. Basic counter is local beta feedback, not clinical assessment.";
      statusNode.textContent = "Camera active. Frames are not uploaded.";
      timer = setInterval(() => {
        seconds += 1;
        if (seconds % 4 === 0) reps += 1;
        sets = Math.floor(reps / 10);
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
      reps: String(reps),
      sets: String(sets),
      duration_seconds: String(seconds),
      confidence: stream ? "0.72" : "",
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
