"""Fail-closed Family Care scope checks across unrelated clinical contexts."""
from __future__ import annotations

import pytest

from zendoc.context_engine import (
    create_or_update_consent_grant,
    verify_context_authorization,
)
from zendoc.db import get_db
from zendoc.family_care import create_family_access_grant, revoke_family_access_grant
from tests.test_milestone1 import make_app, register_web


def _family(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    for email in ("subject@example.test", "caregiver@example.test", "outsider@example.test"):
        registered = register_web(client, "patient", email)
        assert registered.status_code == 200
    with app.app_context():
        db = get_db()
        users = []
        for email in ("subject@example.test", "caregiver@example.test", "outsider@example.test"):
            users.append(dict(db.execute(
                "SELECT * FROM users WHERE email_normalized=?", (email,)
            ).fetchone()))
    return app, users


def test_pharmacy_family_grant_only_authorizes_pharmacy_not_care_journey_or_referral(tmp_path):
    app, (subject, caregiver, outsider) = _family(tmp_path)
    with app.app_context():
        create_family_access_grant(
            subject, {"grantee_id": caregiver["id"], "scopes": ["pharmacy"]}
        )
        assert verify_context_authorization(caregiver, subject["id"], "pharmacy") == "DELEGATED_CONSENT"
        assert verify_context_authorization(caregiver, subject["id"], "prescriptions") == "DELEGATED_CONSENT"
        for purpose in ("care_journey", "referral", "care_graph", "unexpected-purpose"):
            with pytest.raises(PermissionError, match="Access denied"):
                verify_context_authorization(caregiver, subject["id"], purpose)
        with pytest.raises(PermissionError):
            verify_context_authorization(outsider, subject["id"], "pharmacy")


def test_care_journey_requires_explicit_purpose_and_timeline_scope(tmp_path):
    app, (subject, caregiver, _outsider) = _family(tmp_path)
    with app.app_context():
        create_family_access_grant(
            subject, {"grantee_id": caregiver["id"], "scopes": ["pharmacy"]}
        )
        with pytest.raises(ValueError, match="requires scopes"):
            create_or_update_consent_grant(
                subject_id=subject["id"],
                grantee_id=caregiver["id"],
                purpose="care_journey",
                scopes=["prescriptions"],
                actor=subject,
            )
        create_or_update_consent_grant(
            subject_id=subject["id"],
            grantee_id=caregiver["id"],
            purpose="care_journey",
            scopes=["timeline"],
            actor=subject,
        )
        assert verify_context_authorization(caregiver, subject["id"], "care_journey") == "DELEGATED_CONSENT"
        with pytest.raises(PermissionError):
            verify_context_authorization(caregiver, subject["id"], "referral")


def test_revocation_blocks_family_scoped_access(tmp_path):
    app, (subject, caregiver, _outsider) = _family(tmp_path)
    with app.app_context():
        grant = create_family_access_grant(
            subject, {"grantee_id": caregiver["id"], "scopes": ["pharmacy"]}
        )
        assert verify_context_authorization(caregiver, subject["id"], "pharmacy") == "DELEGATED_CONSENT"
        revoke_family_access_grant(subject, grant["id"])
        with pytest.raises(PermissionError):
            verify_context_authorization(caregiver, subject["id"], "pharmacy")
