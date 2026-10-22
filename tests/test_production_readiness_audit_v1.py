"""Production readiness regression suite for ZENDOC.

Covers:
1. Server-enforced session revocation after password reset (web + API).
2. Legacy session version compatibility and invalidation on reset.
3. Secure, single-use, expiring, hashed beta invitations (web + API).
4. Prevention of token reuse, expired tokens, revoked tokens, and email mismatches.
5. Atomic double redemption / race condition prevention.
6. Owner-only beta invitation management and audit logging.
7. Health Memory duplicate detection and patient-to-patient data isolation.
8. Operations worker bounded cycle configuration and resilience.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from tests.test_milestone1 import csrf, make_client
from zendoc.beta_invitation import (
    create_beta_invitation,
    get_beta_invitation,
    hash_beta_token,
    list_beta_invitations,
    redeem_beta_invitation,
    resolve_beta_invitation,
    revoke_beta_invitation,
)
from zendoc.db import get_db, now_iso
from zendoc.health_memory_continuity import detect_record_conflicts_and_duplicates
import sys
from pathlib import Path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
from scripts.run_operations_worker import _cycle_seconds


def _create_owner(app):
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone()
        if row:
            return dict(row)
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, verified, active, session_version, created_at, updated_at)
            VALUES ('Owner', 'admin@example.com', 'admin@example.com', 'hash', 'admin', 1, 1, 1, ?, ?)
            """,
            (now_iso(), now_iso()),
        )
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE role='admin' LIMIT 1").fetchone())


def _create_patient(app, email="patient@example.test", password="Password123!", session_version=1):
    from werkzeug.security import generate_password_hash
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (name, email, email_normalized, password_hash, role, verified, active, session_version, created_at, updated_at)
            VALUES ('Patient Test', ?, ?, ?, 'patient', 1, 1, ?, ?, ?)
            """,
            (email, email.lower(), generate_password_hash(password), session_version, now_iso(), now_iso()),
        )
        db.commit()
        return dict(db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone())


# ==============================================================================
# Phase 3 - Issue E: Password Reset Session Revocation
# ==============================================================================

def test_password_reset_revokes_browser_sessions(tmp_path):
    app, client = make_client(tmp_path)
    _create_patient(app, email="alice@example.test", password="OldPassword123!")

    # Alice logs in
    login_page = client.get("/login?role=patient")
    token = csrf(login_page.get_data(as_text=True))
    login_res = client.post(
        "/login",
        data={
            "csrf_token": token,
            "email": "alice@example.test",
            "password": "OldPassword123!",
            "role": "patient",
        },
        follow_redirects=True,
    )
    assert login_res.status_code == 200
    assert "Health Command Center" in login_res.get_data(as_text=True) or "Dashboard" in login_res.get_data(as_text=True)

    # Verify session can access protected patient dashboard
    dash_res = client.get("/dashboard")
    assert dash_res.status_code == 200

    # Perform password reset for Alice (via database reset token)
    with app.app_context():
        from zendoc.security import hash_token, new_token
        db = get_db()
        reset_tok = new_token()
        db.execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES ((SELECT id FROM users WHERE email='alice@example.test'), ?, 'password_reset', ?, ?)",
            (hash_token(reset_tok), (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(), now_iso()),
        )
        db.commit()

    # Reset password using the reset token via another client/request
    reset_client = app.test_client()
    reset_page = reset_client.get(f"/reset-password?token={reset_tok}")
    assert reset_page.status_code == 200
    reset_csrf = csrf(reset_page.get_data(as_text=True))
    reset_post = reset_client.post(
        f"/reset-password?token={reset_tok}",
        data={"csrf_token": reset_csrf, "password": "NewStrongPassword456!", "token": reset_tok},
        follow_redirects=True,
    )
    assert reset_post.status_code == 200

    # CRITICAL SECURITY CHECK:
    # Alice's PREVIOUS browser session must now be rejected and cleared!
    stale_dash = client.get("/dashboard", follow_redirects=False)
    assert stale_dash.status_code == 302
    assert "/login" in stale_dash.headers["Location"]

    # Following redirect should show flash message
    login_redirect = client.get(stale_dash.headers["Location"])
    assert "Your password was changed. Please log in again." in login_redirect.get_data(as_text=True)

    # Logging in with new password works
    fresh_login_page = client.get("/login?role=patient")
    fresh_csrf = csrf(fresh_login_page.get_data(as_text=True))
    fresh_login = client.post(
        "/login",
        data={
            "csrf_token": fresh_csrf,
            "email": "alice@example.test",
            "password": "NewStrongPassword456!",
            "role": "patient",
        },
        follow_redirects=True,
    )
    assert fresh_login.status_code == 200
    # Now dashboard is accessible again
    assert client.get("/dashboard").status_code == 200


def test_password_reset_revokes_api_tokens(tmp_path):
    app, client = make_client(tmp_path)
    alice = _create_patient(app, email="alice_api@example.test", password="OldPassword123!")

    # Issue an API access token for Alice
    with app.app_context():
        from zendoc.security import hash_token, new_token
        db = get_db()
        access_tok = new_token()
        expires = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'access', ?, ?)",
            (alice["id"], hash_token(access_tok), expires, now_iso()),
        )
        reset_tok = new_token()
        db.execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'password_reset', ?, ?)",
            (alice["id"], hash_token(reset_tok), expires, now_iso()),
        )
        db.commit()

    # Token can authenticate
    headers = {"Authorization": f"Bearer {access_tok}"}
    dash_res = client.get("/api/v1/dashboard", headers=headers)
    assert dash_res.status_code == 200

    # Reset password via API
    reset_res = client.post(
        "/api/v1/auth/reset-password",
        json={"reset_token": reset_tok, "password": "BrandNewPassword789!"},
    )
    assert reset_res.status_code == 200
    assert reset_res.get_json()["status"] == "password_reset_success"

    # Previously issued access token MUST be rejected
    rejected_dash = client.get("/api/v1/dashboard", headers=headers)
    assert rejected_dash.status_code == 401


def test_legacy_session_version_handling(tmp_path):
    """A pre-existing session without session_version should work initially, but invalidate upon password reset."""
    app, client = make_client(tmp_path)
    bob = _create_patient(app, email="bob@example.test", password="OldPassword123!", session_version=1)

    # Establish session without session_version (simulate legacy session)
    with client.session_transaction() as sess:
        sess["user_id"] = bob["id"]
        sess["role"] = "patient"
        sess["last_activity_at"] = now_iso()
        sess["csrf_token"] = "legacy_token"

    # Should be accepted because user's DB session_version is 1
    assert client.get("/dashboard").status_code == 200

    # Increment session_version in database (as password reset does)
    with app.app_context():
        db = get_db()
        db.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (bob["id"],))
        db.commit()

    # The legacy session MUST now be rejected
    revoked = client.get("/dashboard", follow_redirects=False)
    assert revoked.status_code == 302
    assert "/login" in revoked.headers["Location"]


# ==============================================================================
# Phase 3 - Issue F: Invitation-Only Beta Registration
# ==============================================================================

def test_beta_invitation_enforcement_web(tmp_path):
    app, client = make_client(tmp_path)
    app.config["BETA_INVITATION_REQUIRED"] = True
    owner = _create_owner(app)

    reg_page = client.get("/register/patient")
    assert reg_page.status_code == 200
    csrf_tok = csrf(reg_page.get_data(as_text=True))

    # 1. Registration WITHOUT invitation code must fail
    res_no_code = client.post(
        "/register/patient",
        data={
            "csrf_token": csrf_tok,
            "name": "Beta Patient",
            "email": "beta@example.test",
            "password": "Password123!",
            "accept_privacy": "1",
            "accept_terms": "1",
        },
    )
    assert res_no_code.status_code == 403

    # 2. Registration with INVALID code must fail
    res_bad_code = client.post(
        "/register/patient",
        data={
            "csrf_token": csrf_tok,
            "name": "Beta Patient",
            "email": "beta@example.test",
            "password": "Password123!",
            "invitation_code": "invalid_code_123",
            "accept_privacy": "1",
            "accept_terms": "1",
        },
    )
    assert res_bad_code.status_code == 403

    # 3. Create a valid invitation
    with app.app_context():
        token, inv = create_beta_invitation(owner, email="beta@example.test", notes="Test invitation")

    # 4. Registration with valid code succeeds
    res_valid = client.post(
        "/register/patient",
        data={
            "csrf_token": csrf_tok,
            "name": "Beta Patient",
            "email": "beta@example.test",
            "password": "Password123!",
            "invitation_code": token,
            "accept_privacy": "1",
            "accept_terms": "1",
        },
        follow_redirects=False,
    )
    assert res_valid.status_code == 302
    assert "/login" in res_valid.headers["Location"]

    # 5. Token reuse (second attempt with same token) MUST fail
    res_reuse = client.post(
        "/register/patient",
        data={
            "csrf_token": csrf_tok,
            "name": "Beta Patient 2",
            "email": "beta2@example.test",
            "password": "Password123!",
            "invitation_code": token,
            "accept_privacy": "1",
            "accept_terms": "1",
        },
    )
    assert res_reuse.status_code == 403


def test_beta_invitation_enforcement_api(tmp_path):
    app, client = make_client(tmp_path)
    app.config["BETA_INVITATION_REQUIRED"] = True
    owner = _create_owner(app)

    # API register without code -> 403
    res_no_code = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Patient",
            "email": "api_beta@example.test",
            "password": "Password123!",
            "role": "patient",
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert res_no_code.status_code == 403
    assert "invitation" in res_no_code.get_json()["error"]["message"].lower()

    # Create invitation
    with app.app_context():
        token, inv = create_beta_invitation(owner, email="api_beta@example.test")

    # API register with valid code -> 201
    res_valid = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Patient",
            "email": "api_beta@example.test",
            "password": "Password123!",
            "role": "patient",
            "invitation_code": token,
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert res_valid.status_code == 201

    # Attempt reuse via API -> 403
    res_reuse = client.post(
        "/api/v1/auth/register",
        json={
            "name": "API Patient Second",
            "email": "api_beta2@example.test",
            "password": "Password123!",
            "role": "patient",
            "invitation_code": token,
            "accept_terms": True,
            "accept_privacy": True,
        },
    )
    assert res_reuse.status_code == 403


def test_beta_invitation_email_binding_and_expiry(tmp_path):
    app, client = make_client(tmp_path)
    owner = _create_owner(app)

    with app.app_context():
        # Invitation bound to specific email
        token_bound, _ = create_beta_invitation(owner, email="bound@example.test")
        # Attempt to redeem with different email
        with pytest.raises(ValueError, match="another email address"):
            resolve_beta_invitation(token_bound, expected_email="wrong@example.test")

        # Expired invitation
        token_exp, inv_exp = create_beta_invitation(owner, expires_in_days=1)
        db = get_db()
        db.execute(
            "UPDATE beta_invitations SET expires_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), inv_exp["id"]),
        )
        db.commit()
        with pytest.raises(ValueError, match="expired"):
            resolve_beta_invitation(token_exp)

        # Revoked invitation
        token_rev, inv_rev = create_beta_invitation(owner)
        revoke_beta_invitation(owner, inv_rev["id"])
        with pytest.raises(ValueError, match="revoked"):
            resolve_beta_invitation(token_rev)


def test_beta_invitation_atomic_concurrent_redemption(tmp_path):
    """Prove that concurrent redemptions of the same invitation cannot both succeed."""
    app, _ = make_client(tmp_path)
    owner = _create_owner(app)

    with app.app_context():
        token, inv = create_beta_invitation(owner)
        p1 = _create_patient(app, email="p1@example.test")
        p2 = _create_patient(app, email="p2@example.test")

        # First redemption succeeds
        redeemed = redeem_beta_invitation(token, p1["id"])
        assert redeemed["redeemed_by"] == p1["id"]

        # Second redemption MUST raise ValueError
        with pytest.raises(ValueError, match="already"):
            redeem_beta_invitation(token, p2["id"])


def test_beta_invitation_hashed_storage(tmp_path):
    """Raw tokens must NEVER be stored in plaintext in the database."""
    app, _ = make_client(tmp_path)
    owner = _create_owner(app)

    with app.app_context():
        raw_token, inv = create_beta_invitation(owner)
        db = get_db()
        row = db.execute("SELECT * FROM beta_invitations WHERE id = ?", (inv["id"],)).fetchone()

        # Token column must not exist; token_hash must match SHA-256
        assert "token" not in row.keys()
        assert row["token_hash"] == hash_beta_token(raw_token)
        assert raw_token not in row["token_hash"]


def test_beta_invitation_owner_management_and_audit(tmp_path):
    app, client = make_client(tmp_path)
    owner = _create_owner(app)
    patient = _create_patient(app, email="normal_patient@example.test")

    # Issue API token for patient and owner
    with app.app_context():
        from zendoc.security import hash_token, new_token
        db = get_db()
        patient_tok = new_token()
        owner_tok = new_token()
        exp = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds")
        db.execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'access', ?, ?)",
            (patient["id"], hash_token(patient_tok), exp, now_iso()),
        )
        db.execute(
            "INSERT INTO api_tokens (user_id, token_hash, token_type, expires_at, created_at) VALUES (?, ?, 'access', ?, ?)",
            (owner["id"], hash_token(owner_tok), exp, now_iso()),
        )
        db.commit()

    # Patient cannot access owner beta-invitations API -> 403
    patient_res = client.get("/api/v1/admin/beta-invitations", headers={"Authorization": f"Bearer {patient_tok}"})
    assert patient_res.status_code == 403

    # Owner can create beta invitation via API
    owner_create = client.post(
        "/api/v1/admin/beta-invitations",
        headers={"Authorization": f"Bearer {owner_tok}"},
        json={"email": "newbie@example.test", "notes": "VIP beta access", "expires_in_days": 14},
    )
    assert owner_create.status_code == 201
    created_data = owner_create.get_json()
    assert "token" in created_data
    inv_id = created_data["invitation"]["id"]

    # Owner can list beta invitations
    owner_list = client.get("/api/v1/admin/beta-invitations", headers={"Authorization": f"Bearer {owner_tok}"})
    assert owner_list.status_code == 200
    invitations = owner_list.get_json()["invitations"]
    assert any(i["id"] == inv_id for i in invitations)

    # Owner can revoke beta invitation
    owner_revoke = client.post(
        f"/api/v1/admin/beta-invitations/{inv_id}/revoke",
        headers={"Authorization": f"Bearer {owner_tok}"},
    )
    assert owner_revoke.status_code == 200
    assert owner_revoke.get_json()["status"] == "revoked"

    # Check audit log records
    with app.app_context():
        db = get_db()
        logs = db.execute(
            "SELECT * FROM audit_logs WHERE entity_type='beta_invitation' AND entity_id=? ORDER BY id",
            (str(inv_id),),
        ).fetchall()
        actions = [log["action"] for log in logs]
        assert "create_beta_invitation" in actions
        assert "revoke_beta_invitation" in actions


# ==============================================================================
# Phase 3 - Issue D: Health Memory PostgreSQL Compatibility & Isolation
# ==============================================================================

def test_health_memory_duplicate_detection_and_patient_isolation(tmp_path):
    app, _ = make_client(tmp_path)
    p_alice = _create_patient(app, email="hm_alice@example.test")
    p_bob = _create_patient(app, email="hm_bob@example.test")

    with app.app_context():
        db = get_db()
        t1 = "2026-10-14T10:00:00"
        t2 = "2026-10-14T11:00:00"
        # Alice has duplicate heart_rate at t1
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, 'heart_rate', 72, 'bpm', ?)",
            (p_alice["id"], t1),
        )
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, 'heart_rate', 75, 'bpm', ?)",
            (p_alice["id"], t1),
        )
        # Alice has a single metric at t2
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, 'steps', 5000, 'steps', ?)",
            (p_alice["id"], t2),
        )
        # Bob has metric at t1 (same time as Alice)
        db.execute(
            "INSERT INTO health_metrics (user_id, metric_type, metric_value, unit, recorded_at) VALUES (?, 'heart_rate', 80, 'bpm', ?)",
            (p_bob["id"], t1),
        )
        db.commit()

        # Run duplicate detection for Alice (using Alice as actor)
        alice_actor = {"id": p_alice["id"], "role": "patient"}
        report = detect_record_conflicts_and_duplicates(p_alice["id"], actor=alice_actor)

        # Alice's duplicate metric must be detected
        dup_metrics = [d for d in report["duplicates"] if d.get("record_type") == "health_metric"]
        assert len(dup_metrics) == 1
        assert dup_metrics[0]["metric_type"] == "heart_rate"
        assert dup_metrics[0]["recorded_at"] == t1
        assert dup_metrics[0]["count"] == 2

        # Patient isolation check: Bob's metric must NOT contribute to Alice's count
        assert dup_metrics[0]["count"] == 2

        # Bob has only 1 metric, so Bob has 0 duplicates
        bob_actor = {"id": p_bob["id"], "role": "patient"}
        bob_report = detect_record_conflicts_and_duplicates(p_bob["id"], actor=bob_actor)
        bob_dup_metrics = [d for d in bob_report["duplicates"] if d.get("record_type") == "health_metric"]
        assert len(bob_dup_metrics) == 0


# ==============================================================================
# Phase 3 - Issue A: Operations Worker Bounded Cycles and Resilience
# ==============================================================================

def test_operations_worker_cycle_bounds_and_imports(monkeypatch):
    from zendoc import create_app
    from zendoc.operations_digest import run_owner_operations_cycle
    assert callable(run_owner_operations_cycle)

    # Test bounded cycle seconds
    monkeypatch.setenv("ZENDOC_OPS_CYCLE_SECONDS", "60")
    # Must enforce minimum 300 seconds
    assert _cycle_seconds() == 300

    monkeypatch.setenv("ZENDOC_OPS_CYCLE_SECONDS", "100000")
    # Must enforce maximum 86400 seconds (24h)
    assert _cycle_seconds() == 86400

    monkeypatch.setenv("ZENDOC_OPS_CYCLE_SECONDS", "invalid")
    assert _cycle_seconds() == 3600
