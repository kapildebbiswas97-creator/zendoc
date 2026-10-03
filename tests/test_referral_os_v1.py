from zendoc.care_journey_store import create_persisted_journey
from zendoc.context_engine import create_or_update_consent_grant
from zendoc.db import get_db, now_iso
from zendoc.personal_agents import route_personal_agent
from zendoc.referral_service import create_referral, transition_referral
from tests.test_milestone1 import make_client, register_web


def _verified_provider(db, email, *, specialty, organization):
    user = db.execute("SELECT * FROM users WHERE email_normalized=?", (email,)).fetchone()
    assert user is not None
    stamp = now_iso()
    db.execute(
        """
        INSERT INTO provider_profiles
        (user_id,provider_type,specialty,organization,verification_status,created_at,updated_at)
        VALUES (?,'doctor',?,?, 'verified',?,?)
        """,
        (int(user["id"]), specialty, organization, stamp, stamp),
    )
    db.commit()
    return db.execute("SELECT * FROM users WHERE id=?", (int(user["id"]),)).fetchone()


def test_referral_lifecycle_is_consent_and_provider_authority_bound(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "ref-patient@example.com", "Referral Patient")
    client.get("/logout")
    register_web(client, "doctor", "ref-gp@example.com", "Referral GP")
    client.get("/logout")
    register_web(client, "doctor", "ref-specialist@example.com", "Referral Specialist")

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT * FROM users WHERE email_normalized='ref-patient@example.com'").fetchone()
        referrer = _verified_provider(db, "ref-gp@example.com", specialty="General Medicine", organization="Referral GP Clinic")
        destination = _verified_provider(db, "ref-specialist@example.com", specialty="Cardiology", organization="Referral Heart Centre")

        journey = create_persisted_journey(dict(patient), provenance={"source": "referral_test"})
        create_or_update_consent_grant(
            int(patient["id"]),
            int(referrer["id"]),
            "referral",
            ["timeline"],
            actor=dict(patient),
        )

        referral = create_referral(
            dict(referrer),
            patient_id=int(patient["id"]),
            destination_provider_id=int(destination["id"]),
            journey_id=int(journey["id"]),
            reason="Persistent symptoms need specialist review",
            specialty="Cardiology",
            priority="urgent",
            packet_summary="Referral summary prepared from the current care relationship.",
        )
        referral_id = int(referral["id"])
        assert referral["status"] == "CREATED"
        assert referral["external_exchange_confirmed"] is False

        referral = transition_referral(dict(referrer), referral_id, "PACKET_PREPARED")
        assert referral["packet"]["prepared"] is True

        blocked = False
        try:
            transition_referral(dict(referrer), referral_id, "CONSENTED")
        except PermissionError:
            blocked = True
        assert blocked is True

        referral = transition_referral(dict(patient), referral_id, "CONSENTED")
        assert referral["packet"]["patient_consented"] is True

        referral = transition_referral(dict(referrer), referral_id, "SENT")
        referral = transition_referral(dict(destination), referral_id, "RECEIVED")
        referral = transition_referral(dict(destination), referral_id, "TRIAGED", note="Specialist triage completed.")
        referral = transition_referral(dict(destination), referral_id, "ACCEPTED")
        referral = transition_referral(dict(destination), referral_id, "WAITING_LIST")
        assert referral["waiting_since"]
        referral = transition_referral(dict(destination), referral_id, "SCHEDULED", scheduled_for="2026-10-20T10:00:00+05:30")
        referral = transition_referral(dict(destination), referral_id, "CONSULTATION")
        referral = transition_referral(
            dict(destination),
            referral_id,
            "REPORT_RECEIVED",
            specialist_opinion="Specialist assessment recorded for the referring clinician.",
        )
        referral = transition_referral(dict(destination), referral_id, "FOLLOW_UP")
        referral = transition_referral(
            dict(destination),
            referral_id,
            "RETURNED_TO_PRIMARY",
            outcome="Specialist episode completed; continue follow-up with the referring provider.",
        )

        assert referral["status"] == "RETURNED_TO_PRIMARY"
        assert referral["terminal"] is True
        assert len(referral["history"]) == 13
        action = db.execute(
            "SELECT status FROM care_actions WHERE service_ref=?",
            (f"zendoc_referral:{referral_id}",),
        ).fetchone()
        assert action is not None
        assert action["status"] == "COMPLETED"


def test_referral_packet_record_refs_require_reports_scope(tmp_path):
    app, client = make_client(tmp_path)
    register_web(client, "patient", "record-ref-patient@example.com", "Patient")
    client.get("/logout")
    register_web(client, "doctor", "record-ref-gp@example.com", "GP")
    client.get("/logout")
    register_web(client, "doctor", "record-ref-specialist@example.com", "Specialist")

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT * FROM users WHERE email_normalized='record-ref-patient@example.com'").fetchone()
        referrer = _verified_provider(db, "record-ref-gp@example.com", specialty="General Medicine", organization="GP Clinic")
        destination = _verified_provider(db, "record-ref-specialist@example.com", specialty="Neurology", organization="Neuro Centre")
        journey = create_persisted_journey(dict(patient), provenance={"source": "referral_attachment_test"})
        stamp = now_iso()
        record_id = db.execute(
            """
            INSERT INTO medical_records
            (owner_id,uploaded_by,title,category,original_filename,stored_filename,mime_type,file_size,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (int(patient["id"]), int(patient["id"]), "Referral report", "Lab", "r.txt", "ref-test-r.txt", "text/plain", 10, stamp),
        ).lastrowid
        db.commit()

        create_or_update_consent_grant(
            int(patient["id"]), int(referrer["id"]), "referral", ["timeline"], actor=dict(patient)
        )
        blocked = False
        try:
            create_referral(
                dict(referrer),
                patient_id=int(patient["id"]),
                destination_provider_id=int(destination["id"]),
                journey_id=int(journey["id"]),
                reason="Needs specialist review",
                record_ids=[int(record_id)],
            )
        except PermissionError:
            blocked = True
        assert blocked is True

        create_or_update_consent_grant(
            int(patient["id"]), int(referrer["id"]), "referral", ["timeline", "reports"], actor=dict(patient)
        )
        referral = create_referral(
            dict(referrer),
            patient_id=int(patient["id"]),
            destination_provider_id=int(destination["id"]),
            journey_id=int(journey["id"]),
            reason="Needs specialist review",
            record_ids=[int(record_id)],
        )
        assert referral["packet"]["record_ids"] == [int(record_id)]
        assert referral["packet"]["attachment_count"] == 1


def test_personal_agent_routes_referral_read_to_referral_agent():
    route = route_personal_agent({"id": 42, "role": "patient", "active": 1}, "referral")
    assert route["delegated_agent"] == "ReferralAgent"
    assert route["candidate_tools"] == ["get_referral_summary"]
    assert route["permission_expansion"] is False
