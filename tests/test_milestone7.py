"""Milestone 7 regression suite with current messaging-policy overrides.

The original suite is preserved in ``tests.legacy_milestone7`` so downstream
tests can keep importing helpers such as ``headers`` from this module while the
two messaging expectations changed by the current product policy are tested
against their new contract.
"""

from tests.legacy_milestone7 import *  # noqa: F401,F403


def test_pharmacy_and_staff_task_communication_contexts(tmp_path):
    app, client = make_client(tmp_path)
    patient_tok = api_token(client, "pharm-patient@example.com")
    pharm_tok = api_token(client, "pharm-store@example.com", role="pharmacy")
    pharm_id = user_id(app, "pharm-store@example.com")

    # Current policy: a patient may open a direct text conversation with a
    # pharmacy without first creating a medicine order.
    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": pharm_id},
        headers=headers(patient_tok),
    )
    assert started.status_code == 201
    conv_id = started.json["conversation"]["id"]

    # The pharmacy may reply inside the patient-opened conversation. This does
    # not grant voice, video, record-sharing, order or payment permissions.
    reply = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"body": "We received your message."},
        headers=headers(pharm_tok),
    )
    assert reply.status_code == 201


def test_family_messaging_with_access_grant(tmp_path):
    app, client = make_client(tmp_path)
    patient1_tok = api_token(client, "fam1@example.com", role="patient")
    patient2_tok = api_token(client, "fam2@example.com", role="patient")
    patient2_id = user_id(app, "fam2@example.com")

    # Current policy: same-role users may start direct text chat without a
    # family-care grant. Family consent remains required for protected family
    # data/actions and other separately gated channels.
    started = client.post(
        "/api/v1/conversations",
        json={"target_user_id": patient2_id},
        headers=headers(patient1_tok),
    )
    assert started.status_code == 201
    conv_id = started.json["conversation"]["id"]

    reply = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"body": "Hello back."},
        headers=headers(patient2_tok),
    )
    assert reply.status_code == 201
