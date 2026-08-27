import json
import sqlite3
from datetime import datetime, timedelta, timezone
from io import BytesIO

from zendoc import create_app
from zendoc.db import get_db

from tests.test_milestone1 import api_token, csrf, login_web, make_client, register_web
from tests.test_milestone3 import register_api


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def user_id(app, email):
    with app.app_context():
        return get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]


# ---------------------------------------------------------------------------
# 1. Fitness Profile Tests
# ---------------------------------------------------------------------------

def test_fitness_profile_create_update_and_isolation(tmp_path):
    app, client = make_client(tmp_path)
    token_one = api_token(client, "fit1@example.com")
    token_two = api_token(client, "fit2@example.com")

    # Read initial empty profile
    res = client.get("/api/v1/fitness-profile", headers=headers(token_one))
    assert res.status_code == 200
    assert res.json["fitness_profile"]["fitness_goal"] is None

    # Upsert profile
    update_payload = {
        "fitness_goal": "fat_loss",
        "experience_level": "beginner",
        "preferred_workout_type": "mixed",
        "workout_location": "home",
        "equipment": ["dumbbell", "resistance_band"],
        "available_minutes": 30,
        "preferred_days": ["Monday", "Wednesday", "Friday"],
        "height_cm": 170,
        "weight_kg": 75.5,
        "limitations": "Slight lower back sensitivity",
        "target_weight_kg": 68.0,
    }
    res = client.put("/api/v1/fitness-profile", json=update_payload, headers=headers(token_one))
    assert res.status_code == 200
    profile = res.json["fitness_profile"]
    assert profile["fitness_goal"] == "fat_loss"
    assert profile["available_minutes"] == 30
    assert "dumbbell" in profile["equipment"]

    # Check isolation: User Two cannot see User One's profile
    res_two = client.get("/api/v1/fitness-profile", headers=headers(token_two))
    assert res_two.status_code == 200
    assert res_two.json["fitness_profile"]["fitness_goal"] is None
    assert res_two.json["fitness_profile"]["user_id"] != profile["user_id"]


def test_fitness_profile_validation(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "val_fit@example.com")

    # Invalid goal
    res = client.put("/api/v1/fitness-profile", json={"fitness_goal": "become_superman"}, headers=headers(token))
    assert res.status_code == 400
    assert "fitness_goal must be one of" in res.json["error"]["message"]

    # Invalid available_minutes (too small)
    res = client.put("/api/v1/fitness-profile", json={"available_minutes": 1}, headers=headers(token))
    assert res.status_code == 400

    # Invalid height (out of range)
    res = client.put("/api/v1/fitness-profile", json={"height_cm": 400}, headers=headers(token))
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# 2. Exercise Library Tests
# ---------------------------------------------------------------------------

def test_exercise_library_list_and_filters(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "ex_user@example.com")

    # List all exercises (seeded)
    res = client.get("/api/v1/fitness/exercises", headers=headers(token))
    assert res.status_code == 200
    assert res.json["total"] >= 30

    # Filter by category = strength
    res_cat = client.get("/api/v1/fitness/exercises?category=strength", headers=headers(token))
    assert res_cat.status_code == 200
    for ex in res_cat.json["exercises"]:
        assert ex["category"] == "strength"

    # Filter by equipment = dumbbell
    res_eq = client.get("/api/v1/fitness/exercises?equipment=dumbbell", headers=headers(token))
    assert res_eq.status_code == 200
    for ex in res_eq.json["exercises"]:
        assert ex["equipment"] == "dumbbell"

    # Search query = squat
    res_q = client.get("/api/v1/fitness/exercises?q=squat", headers=headers(token))
    assert res_q.status_code == 200
    assert any("squat" in ex["name"].lower() for ex in res_q.json["exercises"])


def test_exercise_detail_lookup(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "ex_detail@example.com")

    # Get Push-Up (id=1 usually)
    res = client.get("/api/v1/fitness/exercises/1", headers=headers(token))
    assert res.status_code == 200
    ex = res.json["exercise"]
    assert ex["name"] == "Push-Up"
    assert "instructions" in ex
    assert "common_mistakes" in ex

    # Lookup non-existent exercise ID
    res_404 = client.get("/api/v1/fitness/exercises/99999", headers=headers(token))
    assert res_404.status_code == 404


# ---------------------------------------------------------------------------
# 3. Workout Engine Tests
# ---------------------------------------------------------------------------

def test_workout_plan_generation_and_constraints(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "planner@example.com")

    # Setup profile first
    client.put("/api/v1/fitness-profile", json={
        "fitness_goal": "fat_loss",
        "experience_level": "beginner",
        "workout_location": "home",
        "equipment": ["resistance_band"],
        "available_minutes": 20,
    }, headers=headers(token))

    # Generate plan
    res = client.post("/api/v1/fitness/plans", json={"name": "Fat Loss Home Plan"}, headers=headers(token))
    assert res.status_code == 201
    plan = res.json["workout_plan"]
    assert plan["goal"] == "fat_loss"
    assert len(plan["items"]) > 0

    # Ensure equipment constraints were respected: no barbell or cable exercises
    for item in plan["items"]:
        assert item["category"] in ["cardio", "strength", "core", "mobility"]


# ---------------------------------------------------------------------------
# 4. Workout Session & Timeline Integration Tests
# ---------------------------------------------------------------------------

def test_workout_session_lifecycle_and_timeline(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "session_user@example.com")

    # 1. Start session
    res_start = client.post("/api/v1/fitness/sessions", json={"name": "Morning Cardio"}, headers=headers(token))
    assert res_start.status_code == 201
    sess = res_start.json["workout_session"]
    sess_id = sess["id"]
    assert sess["status"] == "active"

    # 2. Log a set
    res_set = client.post(f"/api/v1/fitness/sessions/{sess_id}/sets", json={
        "exercise_id": 1,
        "completed_reps": 15,
        "notes": "Good pace",
    }, headers=headers(token))
    assert res_set.status_code == 200

    # 3. Finish session
    res_finish = client.post(f"/api/v1/fitness/sessions/{sess_id}/complete", json={"notes": "Felt energized"}, headers=headers(token))
    assert res_finish.status_code == 200
    assert res_finish.json["status"] == "completed"

    # 4. Verify Timeline Event written automatically
    res_timeline = client.get("/api/v1/health-timeline", headers=headers(token))
    assert res_timeline.status_code == 200
    events = res_timeline.json["events"]
    fitness_events = [e for e in events if e["event_type"] == "fitness"]
    assert len(fitness_events) >= 1
    assert "Morning Cardio" in fitness_events[0]["title"]


def test_workout_session_cross_user_isolation(tmp_path):
    app, client = make_client(tmp_path)
    token_one = api_token(client, "sess_one@example.com")
    token_two = api_token(client, "sess_two@example.com")

    # User One starts session
    res_start = client.post("/api/v1/fitness/sessions", json={"name": "User One Session"}, headers=headers(token_one))
    sess_id = res_start.json["workout_session"]["id"]

    # User Two attempts to view User One's session -> 403 / 404
    res_view = client.get(f"/api/v1/fitness/sessions/{sess_id}", headers=headers(token_two))
    assert res_view.status_code == 403

    # User Two attempts to complete User One's session -> 403 / 404
    res_comp = client.post(f"/api/v1/fitness/sessions/{sess_id}/complete", json={}, headers=headers(token_two))
    assert res_comp.status_code == 403


# ---------------------------------------------------------------------------
# 5. Fitness Progress Tests
# ---------------------------------------------------------------------------

def test_fitness_progress_empty_and_populated(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "prog_user@example.com")

    # Initial empty progress
    res_empty = client.get("/api/v1/fitness/progress?period=30d", headers=headers(token))
    assert res_empty.status_code == 200
    prog = res_empty.json["progress"]
    assert prog["workouts_completed"] == 0
    assert prog["current_streak_days"] == 0

    # Start and finish a session
    sess_res = client.post("/api/v1/fitness/sessions", json={"name": "Quick Workout"}, headers=headers(token))
    sess_id = sess_res.json["workout_session"]["id"]
    client.post(f"/api/v1/fitness/sessions/{sess_id}/complete", json={}, headers=headers(token))

    # Check progress updated
    res_pop = client.get("/api/v1/fitness/progress?period=30d", headers=headers(token))
    assert res_pop.status_code == 200
    assert res_pop.json["progress"]["workouts_completed"] == 1


# ---------------------------------------------------------------------------
# 6. Video Provider Tests
# ---------------------------------------------------------------------------

def test_video_search_fallback_when_no_provider_configured(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "vid_user@example.com")

    # Default env has ZENDOC_VIDEO_PROVIDER=none -> available: False, no fabricated results
    res = client.get("/api/v1/fitness/videos?q=squat", headers=headers(token))
    assert res.status_code == 200
    data = res.json
    assert data["available"] is False
    assert "Video discovery requires a video provider API key" in data["reason"]
    assert len(data["results"]) == 0


# ---------------------------------------------------------------------------
# 7. Nutrition & Hydration Tests
# ---------------------------------------------------------------------------

def test_nutrition_logging_and_nullable_calories(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "nutr_user@example.com")

    # Log food without calories/macros
    res_log1 = client.post("/api/v1/nutrition/logs", json={
        "food_name": "Apple",
        "meal_type": "morning_snack",
    }, headers=headers(token))
    assert res_log1.status_code == 201

    # Log food with calories/macros
    res_log2 = client.post("/api/v1/nutrition/logs", json={
        "food_name": "Grilled Chicken Salad",
        "meal_type": "lunch",
        "calories_kcal": 350.0,
        "protein_g": 40.0,
    }, headers=headers(token))
    assert res_log2.status_code == 201

    # Check daily summary
    res_sum = client.get("/api/v1/nutrition/summary", headers=headers(token))
    assert res_sum.status_code == 200
    summary = res_sum.json["nutrition_summary"]
    assert summary["entries"] == 2
    assert summary["total_calories_kcal"] == 350.0  # Only sums non-null values
    assert summary["total_protein_g"] == 40.0


def test_hydration_logging_and_summary(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "hydro_user@example.com")

    # Log water
    res_w1 = client.post("/api/v1/hydration/logs", json={"ml": 500}, headers=headers(token))
    assert res_w1.status_code == 201
    res_w2 = client.post("/api/v1/hydration/logs", json={"ml": 750}, headers=headers(token))
    assert res_w2.status_code == 201

    # Check summary
    res_sum = client.get("/api/v1/hydration/summary", headers=headers(token))
    assert res_sum.status_code == 200
    summary = res_sum.json["hydration_summary"]
    assert summary["total_ml"] == 1250
    assert summary["total_litres"] == 1.25
    assert summary["percentage_of_suggestion"] == 62


# ---------------------------------------------------------------------------
# 8. Central AI Routing & Safety Precedence Tests
# ---------------------------------------------------------------------------

def test_ai_fitness_intents_routing(tmp_path):
    app, client = make_client(tmp_path)
    token = api_token(client, "ai_fit@example.com")

    # 1. Goal intent
    res_goal = client.post("/api/v1/ai/message", json={"message": "I want to lose weight"}, headers=headers(token))
    assert res_goal.status_code == 200
    assert res_goal.json["intent"] == "fitness_coach"

    # 2. Workout plan intent
    res_plan = client.post("/api/v1/ai/message", json={"message": "Create a beginner home workout plan"}, headers=headers(token))
    assert res_plan.status_code == 200
    assert res_plan.json["intent"] == "workout_plan"

    # 3. Exercise instruction intent
    res_ex = client.post("/api/v1/ai/message", json={"message": "Show me how to squat"}, headers=headers(token))
    assert res_ex.status_code == 200
    assert res_ex.json["intent"] == "exercise_instruction"
    assert "Squat" in res_ex.json["message"]

    # 4. Nutrition intent
    res_nutr = client.post("/api/v1/ai/message", json={"message": "What should I eat after workout?"}, headers=headers(token))
    assert res_nutr.status_code == 200
    assert res_nutr.json["intent"] == "nutrition_general"

    # 5. Emergency Precedence: Chest pain during workout discussion MUST trigger emergency
    res_emg = client.post("/api/v1/ai/message", json={"message": "I had severe chest pain during my squat workout"}, headers=headers(token))
    assert res_emg.status_code == 200
    assert res_emg.json["intent"] == "emergency"
    assert res_emg.json["emergency"] is True


# ---------------------------------------------------------------------------
# 9. API Authentication Requirement Tests
# ---------------------------------------------------------------------------

def test_api_auth_required_for_all_m5_endpoints(tmp_path):
    app, client = make_client(tmp_path)

    endpoints = [
        ("GET", "/api/v1/fitness-profile"),
        ("PUT", "/api/v1/fitness-profile"),
        ("GET", "/api/v1/fitness/exercises"),
        ("GET", "/api/v1/fitness/plans"),
        ("POST", "/api/v1/fitness/plans"),
        ("GET", "/api/v1/fitness/sessions"),
        ("POST", "/api/v1/fitness/sessions"),
        ("GET", "/api/v1/fitness/progress"),
        ("GET", "/api/v1/fitness/videos"),
        ("GET", "/api/v1/nutrition/logs"),
        ("POST", "/api/v1/nutrition/logs"),
        ("GET", "/api/v1/nutrition/summary"),
        ("GET", "/api/v1/hydration/logs"),
        ("POST", "/api/v1/hydration/logs"),
        ("GET", "/api/v1/hydration/summary"),
    ]

    for method, path in endpoints:
        if method == "GET":
            res = client.get(path)
        else:
            res = client.post(path) if method == "POST" else client.put(path)
        assert res.status_code == 401
