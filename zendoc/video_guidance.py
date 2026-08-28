GUIDANCE_LABEL = "General ZENDOC guidance for this exercise - not extracted from the video."


def _clean(value, default):
    text = str(value or "").strip()
    return text if text else default


def build_video_guidance(query, category="fitness", video=None):
    exercise = _clean(query, "this exercise")
    category = _clean(category, "fitness").replace("_", " ")
    title = _clean(video.get("title") if isinstance(video, dict) else None, exercise)
    return {
        "label": GUIDANCE_LABEL,
        "title": title,
        "category": category,
        "before": [
            "Choose a clear area, wear stable footwear, and keep water nearby.",
            "Warm up gently for 3 to 5 minutes before attempting the movement.",
            "Use a pain-free range of motion and reduce intensity if form starts to break down.",
        ],
        "steps": [
            f"Set up for {exercise} with a balanced stance and relaxed breathing.",
            "Move slowly through the first repetition while checking alignment.",
            "Keep the target muscles engaged and avoid rushing the lowering phase.",
            "Pause if balance, breathing, or posture feels unstable.",
            "Complete the set with controlled repetitions rather than chasing speed.",
        ],
        "mistakes": [
            "Holding your breath during effort.",
            "Using momentum instead of controlled movement.",
            "Ignoring discomfort, dizziness, numbness, or sharp pain.",
        ],
        "watch_for": [
            "Steady breathing.",
            "Smooth joint movement without wobbling or collapsing posture.",
            "A pace that lets you stop safely at any point.",
        ],
        "stop_and_get_help": [
            "Stop immediately for chest pain, severe shortness of breath, fainting, new weakness, or sharp joint pain.",
            "Ask a clinician or trainer before continuing if you are recovering from injury, surgery, pregnancy, or a cardiac event.",
        ],
        "after_completion": [
            "Cool down, note difficulty, and save the session if you are tracking progress.",
            "If this is part of a ZENDOC workout, open Camera Coach for form-aware practice when available.",
        ],
    }
