from zendoc.health_commerce import search_health_products
from zendoc.health_shop import affiliate_readiness
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
