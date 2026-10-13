import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_milestone1 import make_client, register_web, login_web
from tests.test_milestone3 import next_weekday_date
from zendoc.db import get_db

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUTPUT_DIR = Path(r"C:\Users\SAMSUNG USER\.gemini\antigravity\brain\d54a5515-775c-4e54-8d9f-28ad1a221ed2\screenshots")

def setup_client():
    temp_dir = Path(tempfile.mkdtemp())
    app, client = make_client(temp_dir)
    
    # Seed patient
    patient_email = "rahul.banerjee@example.test"
    register_web(client, "patient", patient_email)
    
    # Seed doctor & profile
    now = datetime.now(timezone.utc).isoformat()
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO users (name, email, email_normalized, password_hash, role, active, created_at, updated_at)
            VALUES ('Dr. Aisha Sharma', 'dr.aisha@example.test', 'dr.aisha@example.test', 'hash', 'doctor', 1, ?, ?)""",
            (now, now)
        )
        doctor_id = db.execute("SELECT id FROM users WHERE email='dr.aisha@example.test'").fetchone()["id"]
        db.execute(
            """INSERT INTO provider_profiles (user_id, provider_type, specialty, organization, address, city, state, postal_code, public_phone, verification_status, created_at, updated_at)
            VALUES (?, 'doctor', 'Cardiology & Internal Medicine', 'Apollo Clinic Salt Lake', 'Sector 5, Salt Lake', 'Kolkata', 'West Bengal', '700091', '+91 98300 12345', 'verified', ?, ?)""",
            (doctor_id, now, now)
        )
        profile_id = db.execute("SELECT id FROM provider_profiles WHERE user_id=?", (doctor_id,)).fetchone()["id"]
        
        # Schedule
        db.execute(
            """INSERT INTO provider_schedules (provider_profile_id, weekday, start_time, end_time, slot_minutes, active, created_at, updated_at)
            VALUES (?, 0, '09:00', '13:00', 30, 1, ?, ?)""",
            (profile_id, now, now)
        )
        
        # Patient user id
        patient_id = db.execute("SELECT id FROM users WHERE email=?", (patient_email,)).fetchone()["id"]
        
        # Appointment
        appt_date = next_weekday_date(0).isoformat() + "T10:00:00"
        db.execute(
            """INSERT INTO appointments (patient_id, provider_profile_id, provider_name, scheduled_for, reason, status, created_at, updated_at)
            VALUES (?, ?, 'Dr. Aisha Sharma', ?, 'Cardiology wellness checkup & ECG review', 'confirmed', ?, ?)""",
            (patient_id, profile_id, appt_date, now, now)
        )
        
        # Medical record
        db.execute(
            """INSERT INTO medical_records (owner_id, uploaded_by, title, category, original_filename, stored_filename, mime_type, file_size, created_at)
            VALUES (?, ?, 'Annual Lipid Profile & ECG', 'Medical report', 'lipid_ecg_2026.pdf', 'stored_dummy.pdf', 'application/pdf', 1024, ?)""",
            (patient_id, patient_id, now)
        )
        db.commit()
        
    return app, client, patient_email

def capture_page_screenshot(html_content, out_path, width, height):
    preview_file = ROOT / f"_preview_tmp_{width}x{height}.html"
    # rewrite static paths to relative
    prepared_html = html_content.replace('href="/static/', 'href="static/').replace('src="/static/', 'src="static/')
    preview_file.write_text(prepared_html, encoding="utf-8")
    
    profile = tempfile.mkdtemp(prefix="chrome_shot_")
    shot_tmp = os.path.join(profile, "shot.png")
    
    cmd = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={profile}",
        f"--screenshot={shot_tmp}",
        f"--window-size={width},{height}",
        "--hide-scrollbars",
        preview_file.as_uri(),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    success = False
    if os.path.exists(shot_tmp) and os.path.getsize(shot_tmp) > 0:
        shutil.copyfile(shot_tmp, out_path)
        success = True
    else:
        print(f"FAILED {out_path}: {res.stderr[:100]}")
        
    shutil.rmtree(profile, ignore_errors=True)
    if preview_file.exists():
        preview_file.unlink()
        
    return success

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    app, client, patient_email = setup_client()
    
    viewports = [
        ("desktop", 1440, 900),
        ("tablet", 768, 1024),
        ("mobile", 375, 812),
    ]
    
    # 1. Public Landing page
    landing_html = client.get("/").get_data(as_text=True)
    
    # 2. Public Login
    login_html = client.get("/login").get_data(as_text=True)
    
    # 3. Public Register
    register_html = client.get("/register", follow_redirects=True).get_data(as_text=True)
    
    # Now login as patient
    login_web(client, "patient", patient_email)
    
    # 4. Patient Dashboard
    dashboard_html = client.get("/dashboard").get_data(as_text=True)
    
    # 5. Find Care
    finder_html = client.get("/finder").get_data(as_text=True)
    
    # 6. Provider Showcase
    provider_html = client.get("/providers/1").get_data(as_text=True)
    
    # 7. Appointments
    appts_html = client.get("/appointments").get_data(as_text=True)
    
    # 8. Records
    records_html = client.get("/records").get_data(as_text=True)
    
    # 9. Pharmacy
    pharm_html = client.get("/pharmacy").get_data(as_text=True)
    
    # 10. Agent OS
    agent_html = client.get("/agent-os").get_data(as_text=True)
    
    screens = [
        ("landing", landing_html),
        ("login", login_html),
        ("register", register_html),
        ("dashboard", dashboard_html),
        ("finder", finder_html),
        ("provider_showcase", provider_html),
        ("appointments", appts_html),
        ("records", records_html),
        ("pharmacy", pharm_html),
        ("agent_os", agent_html),
    ]
    
    results = []
    for screen_name, html in screens:
        for vp_name, w, h in viewports:
            out_name = f"{screen_name}_{vp_name}_{w}x{h}.png"
            out_path = OUTPUT_DIR / out_name
            ok = capture_page_screenshot(html, str(out_path), w, h)
            size = out_path.stat().st_size if ok else 0
            results.append((out_name, ok, size, f"{w}x{h}"))
            print(f"[{'PASS' if ok else 'FAIL'}] {out_name} ({size} bytes, {w}x{h})")
            
    print("\n================ Screenshot Suite Complete ================")
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f"Total: {len(results)}, Passed: {passed}, Failed: {len(results) - passed}")

if __name__ == "__main__":
    main()
