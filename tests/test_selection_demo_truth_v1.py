from pathlib import Path


def test_selection_demo_runbook_uses_truthful_current_workflow():
    text = Path("docs/SELECTION_DEMO_RUNBOOK.md").read_text(encoding="utf-8")
    lower = text.lower()

    assert "/showcase" in text
    assert "/agent-os" in text
    assert "/admin/edgecare" in text
    assert "/admin/startup" in text
    assert "DEMO ONLY" in text
    assert "waiting for provider confirmation" in lower
    assert "model cannot directly execute tools" in lower
    assert "missing traction remains missing" in lower

    # Old demo claims must not return without real evidence.
    assert "Dr. Clara Smith" not in text
    assert "instant confirmation" not in lower
    assert "real-time appointment availability" not in lower
    assert "HIPAA/GDPR-aligned" not in text
    assert "Omron BP Monitor" not in text
    assert "Apple Watch" not in text
    assert "100% of core patient" not in lower

    # Hardware claims remain evidence-gated.
    assert "runs on Snapdragon NPU" in text
    assert "without Qualcomm/physical-device evidence" in text
    assert "fabricated latency" in lower
