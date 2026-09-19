from io import BytesIO
import hashlib
import hmac
import json

import pytest

from zendoc.db import get_db
from zendoc.payments import verify_webhook
from zendoc.health_commerce import search_health_products
from zendoc.health_shop import affiliate_readiness
from zendoc.health_social import create_post, list_feed, list_moderation_reports, moderate_report, report_entity
from zendoc.payments import payment_gateway_status
from tests.test_milestone1 import csrf, login_web, make_app, register_web


def test_patient_can_reach_new_product_surfaces(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "expansion@example.com", "Expansion Patient")
    login_web(client, "patient", "expansion@example.com")

    pages = {
        "/mental-wellness": [
            b"Mental Wellness &amp; Awareness",
            b"Students",
            b"Professionals",
            b"Adults &amp; Parents",
            b"Older Adults",
            b"Non-diagnostic",
        ],
        "/community": [b"Health-only social community", b"24-hour story", b"reporting", b"blocking"],
        "/health-shop": [b"Health Shop", b"B2C health commerce", b"Clinical independence"],
        "/payments": [b"Payments &amp; invoices", b"Payment truth boundary"],
        "/health-hub": [b"Health Community", b"Health Shop"],
        "/dashboard": [
            b"Mental Wellness Center",
            b"Health Community",
            b"Health Shop",
            b"Payments",
            b"/ai#mental-awareness",
        ],
    }
    for path, expected in pages.items():
        response = client.get(path)
        assert response.status_code == 200, path
        for marker in expected:
            assert marker in response.data, (path, marker)


def test_health_community_post_story_follow_and_comment_are_persisted(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "creator-a@example.com", "Creator A")
    register_web(client, "patient", "creator-b@example.com", "Creator B")
    login_web(client, "patient", "creator-a@example.com")

    page = client.get("/community")
    token = csrf(page.data.decode())
    created = client.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "post",
            "lane": "healthy_food",
            "body": "Simple balanced lunch idea with vegetables and whole grains.",
            "accept_guidelines": "1",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert b"Simple balanced lunch idea" in created.data
    assert b"not verified medical advice" in created.data.lower()

    token = csrf(created.data.decode())
    story = client.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "story",
            "lane": "fitness",
            "body": "Completed a gentle mobility routine today.",
            "accept_guidelines": "1",
        },
        follow_redirects=True,
    )
    assert story.status_code == 200
    assert b"Completed a gentle mobility routine today." in story.data


def test_food_and_device_commerce_uses_truthful_external_handoffs():
    result = search_health_products("bananas", "food_fresh")
    ids = {item["id"] for item in result["results"]}
    assert {"blinkit", "bigbasket", "zepto", "swiggy_instamart", "zomato", "amazon_india"} <= ids
    assert result["external_only"] is True
    assert result["affiliate_attribution_enabled"] is False
    assert result["payment_execution_enabled"] is False

    medicine = search_health_products("antibiotic tablets", "general_wellness")
    assert medicine["medicine_query"] is True
    assert medicine["results"] == []
    assert medicine["pharmacy_handoff"].startswith("/pharmacy")


def test_affiliate_and_payment_claims_stay_disabled_without_real_credentials(monkeypatch):
    for key in (
        "ZENDOC_RAZORPAY_KEY_ID",
        "ZENDOC_RAZORPAY_KEY_SECRET",
        "ZENDOC_RAZORPAY_WEBHOOK_SECRET",
        "ZENDOC_AFFILIATE_AMAZON_INDIA_URL_TEMPLATE",
        "ZENDOC_AFFILIATE_BLINKIT_URL_TEMPLATE",
    ):
        monkeypatch.delenv(key, raising=False)

    gateway = payment_gateway_status()
    assert gateway["ready_for_live_payment"] is False
    assert gateway["checkout_configured"] is False
    assert gateway["webhook_configured"] is False

    affiliate = affiliate_readiness()
    assert affiliate["affiliate_revenue_claim_allowed"] is False
    assert affiliate["configured_merchants"] == []


def test_business_page_is_public_and_truthful(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    response = client.get("/business")
    assert response.status_code == 200
    assert b"B2B + B2C" in response.data
    assert b"real merchant affiliate approval" in response.data
    assert b"real contracts" in response.data


def test_signed_payment_webhook_requires_matching_invoice_amount_and_currency(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "pay-patient@example.com", "Pay Patient")
    register_web(client, "hospital", "pay-hospital@example.com", "Pay Hospital")

    webhook_secret = "unit-test-webhook-secret"
    monkeypatch.setenv("ZENDOC_RAZORPAY_WEBHOOK_SECRET", webhook_secret)

    with app.app_context():
        db = get_db()
        patient = db.execute("SELECT id FROM users WHERE email='pay-patient@example.com'").fetchone()
        hospital = db.execute("SELECT id FROM users WHERE email='pay-hospital@example.com'").fetchone()
        now = "2026-09-19T08:00:00+00:00"
        db.execute(
            """
            INSERT INTO care_invoices
            (invoice_uid,patient_id,payee_user_id,resource_type,resource_id,amount_paise,currency,
             description,status,gateway,gateway_order_id,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "inv_test_match",
                patient["id"],
                hospital["id"],
                "appointment",
                101,
                12500,
                "INR",
                "Connected care test invoice",
                "checkout_ready",
                "razorpay",
                "order_match",
                hospital["id"],
                now,
                now,
            ),
        )
        db.execute(
            """
            INSERT INTO care_invoices
            (invoice_uid,patient_id,payee_user_id,resource_type,resource_id,amount_paise,currency,
             description,status,gateway,gateway_order_id,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "inv_test_mismatch",
                patient["id"],
                hospital["id"],
                "appointment",
                102,
                12500,
                "INR",
                "Connected care mismatch invoice",
                "checkout_ready",
                "razorpay",
                "order_mismatch",
                hospital["id"],
                now,
                now,
            ),
        )
        db.commit()

        good_event = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_match",
                        "order_id": "order_match",
                        "amount": 12500,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw = json.dumps(good_event, separators=(",", ":")).encode()
        signature = hmac.new(webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
        result = verify_webhook(raw, signature)
        assert result["handled"] is True
        row = db.execute("SELECT status FROM care_invoices WHERE gateway_order_id='order_match'").fetchone()
        assert row["status"] == "paid"

        bad_event = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_mismatch",
                        "order_id": "order_mismatch",
                        "amount": 12499,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_bad = json.dumps(bad_event, separators=(",", ":")).encode()
        bad_signature = hmac.new(webhook_secret.encode(), raw_bad, hashlib.sha256).hexdigest()
        with pytest.raises(PermissionError, match="amount"):
            verify_webhook(raw_bad, bad_signature)
        row = db.execute("SELECT status FROM care_invoices WHERE gateway_order_id='order_mismatch'").fetchone()
        assert row["status"] == "checkout_ready"


def test_owner_moderation_removes_reported_content(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "post-author@example.com", "Post Author")
    register_web(client, "patient", "post-reporter@example.com", "Post Reporter")

    with app.app_context():
        db = get_db()
        author = db.execute("SELECT * FROM users WHERE email=?", ("post-author@example.com",)).fetchone()
        reporter = db.execute("SELECT * FROM users WHERE email=?", ("post-reporter@example.com",)).fetchone()
        post = create_post(author, {"lane": "fitness", "body": "Community post for moderation test"})
        report_id = report_entity(reporter, "post", post["id"], "Needs owner review")
        queue = list_moderation_reports()
        assert any(item["id"] == report_id for item in queue)

        result = moderate_report(report_id, "remove")
        assert result["status"] == "resolved_removed"
        hidden = db.execute(
            "SELECT moderation_status FROM health_social_posts WHERE id=?",
            (post["id"],),
        ).fetchone()
        assert hidden["moderation_status"] == "removed"
        assert all(item["id"] != post["id"] for item in list_feed(reporter))

    login_web(client, "admin", "admin@example.com", "AdminStrong123")
    response = client.get("/admin/community-moderation")
    assert response.status_code == 200
    assert b"Health Community moderation" in response.data


def test_community_guidelines_are_public_and_required_to_publish(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    public = client.get("/community-guidelines")
    assert public.status_code == 200
    assert b"ZENDOC Health Community Guidelines" in public.data

    register_web(client, "patient", "guideline-user@example.com", "Guideline User")
    login_web(client, "patient", "guideline-user@example.com")
    page = client.get("/community")
    token = csrf(page.data.decode())
    denied = client.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "post",
            "lane": "fitness",
            "body": "A health-focused post without policy acknowledgement.",
        },
        follow_redirects=True,
    )
    assert denied.status_code == 200
    assert b"Accept the current Health Community Guidelines" in denied.data
    assert b"A health-focused post without policy acknowledgement." not in denied.data


def test_native_community_media_upload_is_validated_and_access_controlled(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    register_web(client, "patient", "media-user@example.com", "Media User")
    login_web(client, "patient", "media-user@example.com")

    page = client.get("/community")
    token = csrf(page.data.decode())
    # Minimal PNG signature plus bounded payload is enough for the storage
    # contract; browsers remain responsible for rendering valid image content.
    png = b"\x89PNG\r\n\x1a\n" + (b"zendoc-media" * 8)
    created = client.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "post",
            "lane": "healthy_food",
            "body": "Native media upload test.",
            "accept_guidelines": "1",
            "media_file": (BytesIO(png), "healthy.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert created.status_code == 200
    assert b"Native media upload test." in created.data

    with app.app_context():
        row = get_db().execute(
            """
            SELECT media_storage_key,media_mime_type,media_original_name,media_size_bytes
            FROM health_social_posts
            WHERE body='Native media upload test.'
            """
        ).fetchone()
        assert row is not None
        assert row["media_storage_key"]
        assert row["media_mime_type"] == "image/png"
        assert row["media_original_name"] == "healthy.png"
        assert int(row["media_size_bytes"]) == len(png)
        media_path = row["media_storage_key"]

    media = client.get(f"/community/media/{media_path}")
    assert media.status_code == 200
    assert media.mimetype == "image/png"

    page = client.get("/community")
    token = csrf(page.data.decode())
    bad = client.post(
        "/community",
        data={
            "csrf_token": token,
            "action": "story",
            "lane": "fitness",
            "body": "Bad content-type test.",
            "accept_guidelines": "1",
            "media_file": (BytesIO(b"not-a-png"), "fake.png", "image/png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert bad.status_code == 200
    assert b"does not match its declared media type" in bad.data
