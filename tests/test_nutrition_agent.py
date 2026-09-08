from zendoc.nutrition_agent import compare_products, hydration_guidance
from tests.test_milestone1 import api_token, make_app


def sample_products():
    return [
        {
            "name": "Sponsored Drink",
            "price_inr": 60,
            "quantity": 500,
            "quantity_unit": "ml",
            "calories_kcal": 180,
            "protein_g": 0,
            "carbohydrate_g": 45,
            "fat_g": 0,
            "fibre_g": 0,
            "sugar_g": 42,
            "sodium_mg": 260,
            "ingredients": "water, sugar, flavour",
            "sponsored": True,
        },
        {
            "name": "Simple Drink",
            "price_inr": 25,
            "quantity": 500,
            "quantity_unit": "ml",
            "calories_kcal": 20,
            "protein_g": 0,
            "carbohydrate_g": 5,
            "fat_g": 0,
            "fibre_g": 0,
            "sugar_g": 3,
            "sodium_mg": 40,
            "ingredients": "water, lime",
            "sponsored": False,
        },
    ]


def test_sponsorship_never_changes_health_ranking():
    result = compare_products(sample_products(), goal="general_wellness")
    assert result["best_general_fit"] == "Simple Drink"
    assert result["sponsored_products"] == ["Sponsored Drink"]
    assert all(item["sponsorship_affects_health_rank"] is False for item in result["products"])


def test_nutrition_comparison_flags_user_allergen():
    products = sample_products()
    products[1]["ingredients"] = "water, lime, peanut extract"
    result = compare_products(products, allergens=["peanut"])
    row = next(item for item in result["products"] if item["name"] == "Simple Drink")
    assert row["allergy_matches"] == ["peanut"]
    assert row["eligible_for_health_ranking"] is False
    assert result["allergy_warning"] is True


def test_medical_diet_is_escalated_not_autonomously_created():
    result = compare_products(sample_products(), goal="kidney medical diet")
    assert result["medical_diet_required"] is True
    assert "clinician/dietitian" in result["next_step"]


def test_hydration_guidance_escalates_medical_condition():
    result = hydration_guidance(activity_minutes=30, medical_condition=True)
    assert result["status"] == "CLINICAL_REVIEW_RECOMMENDED"


def test_nutrition_api_is_authenticated_and_truthful(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()
    denied = client.post("/api/v1/nutrition/compare", json={"products": sample_products()})
    assert denied.status_code == 401

    token = api_token(client, "nutrition-user@example.com")
    response = client.post(
        "/api/v1/nutrition/compare",
        json={"products": sample_products(), "goal": "general_wellness"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["patient_specific_clinical_advice"] is False
    assert payload["best_general_fit"] == "Simple Drink"
