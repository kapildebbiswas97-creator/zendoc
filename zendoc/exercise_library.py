"""
Exercise Library — reusable exercise catalogue.

Seeded once at startup (idempotent).  Exercises are the authoritative source
used by WorkoutEngine when building personalised plans.

The `camera_ready` flag marks exercises whose form can be evaluated by a
pose-detection model — reserved for Milestone 6 Camera Coach.
"""

from .db import get_db


# ---------------------------------------------------------------------------
# Seed data — ~40 exercises across all categories
# ---------------------------------------------------------------------------

SEED_EXERCISES = [
    # ── Bodyweight / Strength ───────────────────────────────────────────────
    {
        "name": "Push-Up",
        "category": "strength",
        "muscle_group": "chest, triceps, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Start in a high plank: hands shoulder-width apart, body in a straight line. Lower your chest to just above the floor by bending your elbows. Press back up until arms are fully extended.",
        "common_mistakes": "Sagging hips; flaring elbows; not going to full depth.",
        "easier_variation": "Knee push-up",
        "harder_variation": "Decline push-up or archer push-up",
        "camera_ready": 1,
    },
    {
        "name": "Bodyweight Squat",
        "category": "strength",
        "muscle_group": "quadriceps, glutes, hamstrings",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Stand feet shoulder-width apart. Push hips back and bend knees, lowering until thighs are parallel to the floor. Drive through heels to stand.",
        "common_mistakes": "Knees caving inward; heels lifting; rounding the lower back.",
        "easier_variation": "Sit-to-stand from a chair",
        "harder_variation": "Jump squat or pistol squat",
        "camera_ready": 1,
    },
    {
        "name": "Plank",
        "category": "core",
        "muscle_group": "core, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Support yourself on forearms and toes. Keep body in a straight line from head to heels. Breathe steadily and hold.",
        "common_mistakes": "Hips too high or sagging; holding breath; neck tension.",
        "easier_variation": "Knee plank",
        "harder_variation": "Side plank or plank with shoulder tap",
        "camera_ready": 1,
    },
    {
        "name": "Lunge",
        "category": "strength",
        "muscle_group": "quadriceps, glutes, hamstrings",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Stand upright. Step one foot forward and lower the back knee toward the floor. Front knee stays over ankle. Push through front heel to return. Alternate legs.",
        "common_mistakes": "Knee passing far over toes; leaning forward excessively.",
        "easier_variation": "Stationary split squat",
        "harder_variation": "Reverse lunge or walking lunge with weight",
        "camera_ready": 1,
    },
    {
        "name": "Glute Bridge",
        "category": "strength",
        "muscle_group": "glutes, hamstrings",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Lie on back, knees bent, feet flat. Drive hips up by squeezing glutes until body forms a straight line from shoulders to knees. Lower slowly.",
        "common_mistakes": "Overextending the lower back; feet too far from hips.",
        "easier_variation": "Partial range bridge",
        "harder_variation": "Single-leg glute bridge",
        "camera_ready": 1,
    },
    {
        "name": "Mountain Climber",
        "category": "cardio",
        "muscle_group": "core, hip flexors, shoulders",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "Start in high plank. Drive one knee toward chest, then quickly switch legs in a running motion. Keep hips level.",
        "common_mistakes": "Hips rising; too slow to engage cardio.",
        "easier_variation": "Slow-tempo alternating knee drives",
        "harder_variation": "Cross-body mountain climber",
        "camera_ready": 0,
    },
    {
        "name": "Burpee",
        "category": "cardio",
        "muscle_group": "full body",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "From standing, squat and place hands on floor. Jump feet back to plank, perform a push-up, jump feet forward, then jump up with arms overhead.",
        "common_mistakes": "Skipping the push-up; landing heavily on joints.",
        "easier_variation": "Step-out burpee without jump",
        "harder_variation": "Burpee with tuck jump",
        "camera_ready": 0,
    },
    {
        "name": "Tricep Dip",
        "category": "strength",
        "muscle_group": "triceps, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Sit on the edge of a chair or bench. Hands beside hips. Lower your body by bending elbows to about 90 degrees. Push back up.",
        "common_mistakes": "Shoulders hunching; elbows flaring wide.",
        "easier_variation": "Bend knees to reduce load",
        "harder_variation": "Parallel bar dip",
        "camera_ready": 0,
    },
    {
        "name": "Superman Hold",
        "category": "strength",
        "muscle_group": "lower back, glutes",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Lie face down, arms extended. Simultaneously lift arms, chest, and legs off the floor. Hold briefly, lower, repeat.",
        "common_mistakes": "Straining the neck; holding breath.",
        "easier_variation": "Alternate arm-and-leg lift",
        "harder_variation": "Add a pause at top",
        "camera_ready": 0,
    },
    {
        "name": "Hollow Body Hold",
        "category": "core",
        "muscle_group": "core",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "Lie on back. Press lower back into floor. Lift shoulders and legs slightly. Arms reach overhead. Hold while breathing.",
        "common_mistakes": "Lower back lifting off floor; breath-holding.",
        "easier_variation": "Knees bent variation",
        "harder_variation": "Rock in hollow position",
        "camera_ready": 0,
    },
    # ── Dumbbell ────────────────────────────────────────────────────────────
    {
        "name": "Dumbbell Goblet Squat",
        "category": "strength",
        "muscle_group": "quadriceps, glutes",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Hold one dumbbell vertically at chest height. Squat deep, keeping chest tall. Drive through heels to stand.",
        "common_mistakes": "Letting elbows drop; heels rising.",
        "easier_variation": "Bodyweight squat",
        "harder_variation": "Dumbbell front squat",
        "camera_ready": 1,
    },
    {
        "name": "Dumbbell Romanian Deadlift",
        "category": "strength",
        "muscle_group": "hamstrings, glutes, lower back",
        "equipment": "dumbbell",
        "difficulty": "intermediate",
        "instructions": "Stand holding dumbbells in front of thighs. Hinge at hips, pushing them back, letting dumbbells slide down your legs. Keep back flat. Drive hips forward to return.",
        "common_mistakes": "Rounding the lower back; bending knees too much.",
        "easier_variation": "Single-leg variant with support",
        "harder_variation": "Single-leg Romanian deadlift",
        "camera_ready": 0,
    },
    {
        "name": "Dumbbell Row",
        "category": "strength",
        "muscle_group": "back, biceps",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Support one hand and knee on a bench. Hold dumbbell with other hand, arm extended. Pull elbow up toward ceiling, squeezing the back. Lower slowly.",
        "common_mistakes": "Rotating the torso; using momentum.",
        "easier_variation": "Two-arm incline dumbbell row",
        "harder_variation": "Kroc row with heavier weight",
        "camera_ready": 0,
    },
    {
        "name": "Dumbbell Shoulder Press",
        "category": "strength",
        "muscle_group": "shoulders, triceps",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Sit or stand. Hold dumbbells at shoulder height, elbows at 90 degrees. Press overhead until arms are extended. Lower slowly.",
        "common_mistakes": "Arching the lower back; not reaching full extension.",
        "easier_variation": "Seated Arnold press",
        "harder_variation": "Standing single-arm press",
        "camera_ready": 0,
    },
    {
        "name": "Dumbbell Bicep Curl",
        "category": "strength",
        "muscle_group": "biceps",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Stand with dumbbells at sides, palms forward. Curl weights toward shoulders, keeping elbows still. Lower with control.",
        "common_mistakes": "Swinging body; not lowering fully.",
        "easier_variation": "Hammer curl",
        "harder_variation": "Concentration curl or incline curl",
        "camera_ready": 0,
    },
    {
        "name": "Dumbbell Chest Press",
        "category": "strength",
        "muscle_group": "chest, triceps, shoulders",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Lie on bench or floor. Dumbbells at chest level, elbows bent. Press up until arms are straight. Lower slowly.",
        "common_mistakes": "Flaring elbows; bouncing from chest.",
        "easier_variation": "Floor press",
        "harder_variation": "Incline dumbbell press",
        "camera_ready": 0,
    },
    {
        "name": "Dumbbell Lateral Raise",
        "category": "strength",
        "muscle_group": "side deltoids",
        "equipment": "dumbbell",
        "difficulty": "beginner",
        "instructions": "Stand holding dumbbells at sides. Raise both arms out to sides to shoulder height. Lower slowly.",
        "common_mistakes": "Using momentum; shrugging shoulders.",
        "easier_variation": "Seated lateral raise",
        "harder_variation": "Cable lateral raise",
        "camera_ready": 0,
    },
    # ── Resistance Band ─────────────────────────────────────────────────────
    {
        "name": "Resistance Band Pull-Apart",
        "category": "strength",
        "muscle_group": "rear deltoids, upper back",
        "equipment": "resistance_band",
        "difficulty": "beginner",
        "instructions": "Hold band at shoulder height, arms extended. Pull hands apart until band touches chest. Slowly return.",
        "common_mistakes": "Rounding shoulders; not pulling to full width.",
        "easier_variation": "Lighter band",
        "harder_variation": "Heavier band or add pause",
        "camera_ready": 0,
    },
    {
        "name": "Resistance Band Squat",
        "category": "strength",
        "muscle_group": "quadriceps, glutes",
        "equipment": "resistance_band",
        "difficulty": "beginner",
        "instructions": "Stand on band with feet shoulder-width apart. Hold band handles at shoulders. Squat down, keeping chest tall. Return to standing.",
        "common_mistakes": "Knees caving; band slipping.",
        "easier_variation": "Squat with band around thighs only",
        "harder_variation": "Jump squat with band",
        "camera_ready": 0,
    },
    # ── Cardio ──────────────────────────────────────────────────────────────
    {
        "name": "High Knees",
        "category": "cardio",
        "muscle_group": "hip flexors, core",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Run in place, driving knees as high as possible with each step. Pump arms in opposition.",
        "common_mistakes": "Not driving knees high enough; leaning back.",
        "easier_variation": "Marching in place",
        "harder_variation": "Sprint intervals",
        "camera_ready": 0,
    },
    {
        "name": "Jumping Jack",
        "category": "cardio",
        "muscle_group": "full body",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Start standing. Jump feet wide while raising arms overhead. Jump feet together while lowering arms. Repeat rhythmically.",
        "common_mistakes": "Landing hard on heels; incomplete arm extension.",
        "easier_variation": "Step-out jack (no jump)",
        "harder_variation": "Speed jack or weighted jack",
        "camera_ready": 0,
    },
    {
        "name": "Jump Rope (Simulated)",
        "category": "cardio",
        "muscle_group": "calves, cardio",
        "equipment": "none",
        "difficulty": "beginner",
        "instructions": "Simulate jump-rope motion: small hops with both feet together, swinging arms in small circles. Maintain rhythm.",
        "common_mistakes": "Jumping too high; stiff ankles.",
        "easier_variation": "March with arm circles",
        "harder_variation": "Double-under simulation",
        "camera_ready": 0,
    },
    # ── Mobility & Flexibility ───────────────────────────────────────────────
    {
        "name": "World's Greatest Stretch",
        "category": "mobility",
        "muscle_group": "hip flexors, thoracic spine, hamstrings",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "From a lunge position, place same-side hand on floor. Rotate upper body, reaching opposite arm to ceiling. Return. Alternate sides.",
        "common_mistakes": "Collapsing the front knee; limited rotation.",
        "easier_variation": "Half-kneeling hip flexor stretch",
        "harder_variation": "Add ankle mobility by dorsiflexing the front foot",
        "camera_ready": 0,
    },
    {
        "name": "Hip Flexor Stretch",
        "category": "flexibility",
        "muscle_group": "hip flexors",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Kneel on one knee, other foot forward. Push hips forward gently. Keep torso upright. Hold 30–45 seconds each side.",
        "common_mistakes": "Arching the lower back; not keeping torso upright.",
        "easier_variation": "Standing hip flexor stretch",
        "harder_variation": "Add overhead reach for deeper stretch",
        "camera_ready": 0,
    },
    {
        "name": "Cat-Cow Stretch",
        "category": "mobility",
        "muscle_group": "spine, core",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "On all fours. Inhale: drop belly, lift head and tailbone (cow). Exhale: round spine toward ceiling, tuck chin and pelvis (cat). Flow smoothly.",
        "common_mistakes": "Moving too fast; not breathing with movement.",
        "easier_variation": "Seated spinal flexion and extension",
        "harder_variation": "Add thread-the-needle rotation",
        "camera_ready": 0,
    },
    {
        "name": "Pigeon Pose",
        "category": "flexibility",
        "muscle_group": "glutes, hip external rotators",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "From downward dog, bring one knee toward same-side wrist. Extend opposite leg back. Lower hips toward floor. Hold 30–60 seconds each side.",
        "common_mistakes": "Forcing hips down prematurely; hips uneven.",
        "easier_variation": "Supine figure-four stretch",
        "harder_variation": "King pigeon with back-foot hold",
        "camera_ready": 0,
    },
    {
        "name": "Hamstring Stretch (Standing)",
        "category": "flexibility",
        "muscle_group": "hamstrings",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Stand and place one heel on a low surface. Hinge forward at hips, keeping back flat, until you feel a stretch in the back of the thigh. Hold 30 seconds.",
        "common_mistakes": "Rounding the back; locking the knee too hard.",
        "easier_variation": "Seated hamstring stretch",
        "harder_variation": "Standing forward fold with feet together",
        "camera_ready": 0,
    },
    # ── Yoga ────────────────────────────────────────────────────────────────
    {
        "name": "Downward Dog",
        "category": "yoga",
        "muscle_group": "hamstrings, calves, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Start on all fours. Tuck toes and lift hips toward ceiling, forming an inverted V. Press palms flat and reach heels toward floor. Hold and breathe.",
        "common_mistakes": "Rounded back; elbows flaring; heels not working toward floor.",
        "easier_variation": "Downward dog with bent knees",
        "harder_variation": "Three-legged downward dog",
        "camera_ready": 0,
    },
    {
        "name": "Warrior I",
        "category": "yoga",
        "muscle_group": "hip flexors, quadriceps, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Step one foot forward into a deep lunge. Back foot angled ~45 degrees. Square hips forward. Arms raised overhead. Hold and breathe.",
        "common_mistakes": "Hips not squared; front knee collapsing inward.",
        "easier_variation": "Low lunge without arm raise",
        "harder_variation": "Warrior I to Warrior III transition",
        "camera_ready": 0,
    },
    {
        "name": "Child's Pose",
        "category": "yoga",
        "muscle_group": "back, hips, shoulders",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Kneel, sit back toward heels, extend arms forward on floor, rest forehead down. Breathe deeply. Hold as long as comfortable.",
        "common_mistakes": "Holding tension in shoulders; hips not reaching heels.",
        "easier_variation": "Blanket under knees for comfort",
        "harder_variation": "Wide-knee child's pose for deeper hip opening",
        "camera_ready": 0,
    },
    # ── Core ────────────────────────────────────────────────────────────────
    {
        "name": "Crunch",
        "category": "core",
        "muscle_group": "rectus abdominis",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Lie on back, knees bent, hands behind head. Exhale and curl shoulders off floor. Inhale and lower slowly. Avoid pulling on the neck.",
        "common_mistakes": "Pulling neck forward; using momentum.",
        "easier_variation": "Partial crunch",
        "harder_variation": "Bicycle crunch",
        "camera_ready": 0,
    },
    {
        "name": "Dead Bug",
        "category": "core",
        "muscle_group": "core, hip flexors",
        "equipment": "bodyweight",
        "difficulty": "beginner",
        "instructions": "Lie on back. Arms up toward ceiling, knees bent at 90 degrees. Lower opposite arm and leg toward floor while keeping lower back pressed down. Return. Alternate.",
        "common_mistakes": "Lower back arching; moving too fast.",
        "easier_variation": "Extend only one limb at a time",
        "harder_variation": "Add resistance band",
        "camera_ready": 0,
    },
    {
        "name": "Russian Twist",
        "category": "core",
        "muscle_group": "obliques",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "Sit with knees bent, feet slightly off floor. Lean back slightly. Rotate torso side to side, touching floor beside hips.",
        "common_mistakes": "Feet on floor removes oblique engagement; rotating only with arms.",
        "easier_variation": "Feet on floor",
        "harder_variation": "Hold a weight or medicine ball",
        "camera_ready": 0,
    },
    {
        "name": "Leg Raise",
        "category": "core",
        "muscle_group": "lower abdominals, hip flexors",
        "equipment": "bodyweight",
        "difficulty": "intermediate",
        "instructions": "Lie flat. Keep legs straight, raise to 90 degrees. Lower slowly without touching floor.",
        "common_mistakes": "Lower back arching; legs dropping fast.",
        "easier_variation": "Bent-knee raise",
        "harder_variation": "Hanging leg raise",
        "camera_ready": 0,
    },
    # ── Barbell ─────────────────────────────────────────────────────────────
    {
        "name": "Barbell Back Squat",
        "category": "strength",
        "muscle_group": "quadriceps, glutes, hamstrings, core",
        "equipment": "barbell",
        "difficulty": "intermediate",
        "instructions": "Bar on upper traps. Feet shoulder-width, toes slightly out. Break at hips and knees, descend until thighs are parallel. Drive through heels to stand.",
        "common_mistakes": "Heels rising; knees caving; forward lean.",
        "easier_variation": "Goblet squat",
        "harder_variation": "Front squat or pause squat",
        "camera_ready": 1,
    },
    {
        "name": "Barbell Deadlift",
        "category": "strength",
        "muscle_group": "hamstrings, glutes, lower back, core",
        "equipment": "barbell",
        "difficulty": "intermediate",
        "instructions": "Bar over mid-foot. Hip-width stance. Hinge and grip bar outside legs. Push floor away, keeping back flat, until standing. Lower with control.",
        "common_mistakes": "Rounded back; bar drifting from body; jerking the bar.",
        "easier_variation": "Trap bar deadlift or Romanian deadlift",
        "harder_variation": "Deficit deadlift",
        "camera_ready": 1,
    },
    {
        "name": "Barbell Bench Press",
        "category": "strength",
        "muscle_group": "chest, triceps, shoulders",
        "equipment": "barbell",
        "difficulty": "intermediate",
        "instructions": "Lie on bench. Grip bar slightly wider than shoulder-width. Lower to chest, elbows at ~75 degrees. Press back up explosively.",
        "common_mistakes": "Bouncing bar off chest; feet not flat; excessive arch.",
        "easier_variation": "Dumbbell chest press",
        "harder_variation": "Close-grip bench press",
        "camera_ready": 0,
    },
    # ── Pull-Up Bar ─────────────────────────────────────────────────────────
    {
        "name": "Pull-Up",
        "category": "strength",
        "muscle_group": "back (lats), biceps",
        "equipment": "pull_up_bar",
        "difficulty": "intermediate",
        "instructions": "Hang from bar, hands wider than shoulder-width, overhand grip. Pull until chin clears bar. Lower slowly to full hang.",
        "common_mistakes": "Kipping without intention; not achieving chin over bar; partial range.",
        "easier_variation": "Assisted pull-up or inverted row",
        "harder_variation": "Weighted pull-up or L-sit pull-up",
        "camera_ready": 1,
    },
    {
        "name": "Chin-Up",
        "category": "strength",
        "muscle_group": "back (lats), biceps",
        "equipment": "pull_up_bar",
        "difficulty": "intermediate",
        "instructions": "Hang from bar, hands shoulder-width, underhand grip. Pull chest toward bar. Lower slowly.",
        "common_mistakes": "Swinging; not reaching full extension at bottom.",
        "easier_variation": "Resistance band-assisted chin-up",
        "harder_variation": "Weighted chin-up",
        "camera_ready": 0,
    },
]


def seed_exercises():
    """Seed exercise library if not already populated. Safe to call repeatedly."""
    db = get_db()
    count = db.execute("SELECT COUNT(*) n FROM exercises").fetchone()["n"]
    if count > 0:
        return
    for ex in SEED_EXERCISES:
        db.execute(
            """INSERT OR IGNORE INTO exercises
            (name, category, muscle_group, equipment, difficulty,
             instructions, common_mistakes, easier_variation,
             harder_variation, camera_ready)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                ex["name"], ex["category"], ex["muscle_group"],
                ex["equipment"], ex["difficulty"], ex["instructions"],
                ex.get("common_mistakes"), ex.get("easier_variation"),
                ex.get("harder_variation"), ex.get("camera_ready", 0),
            ),
        )
    db.commit()


def list_exercises(category=None, equipment=None, difficulty=None, q=None, limit=100, offset=0):
    """Return filtered list of exercises."""
    conditions = []
    params = []
    if category:
        conditions.append("category=?")
        params.append(category.lower())
    if equipment:
        conditions.append("equipment=?")
        params.append(equipment.lower())
    if difficulty:
        conditions.append("difficulty=?")
        params.append(difficulty.lower())
    if q:
        text = f"%{str(q).strip().lower()[:100]}%"
        conditions.append("(LOWER(name) LIKE ? OR LOWER(muscle_group) LIKE ? OR LOWER(category) LIKE ?)")
        params.extend([text, text, text])
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) n FROM exercises{where}", params).fetchone()["n"]
    rows = db.execute(
        f"SELECT * FROM exercises{where} ORDER BY category, difficulty, name LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    return {"exercises": [dict(r) for r in rows], "total": total}


def get_exercise(exercise_id):
    """Return full exercise detail dict, or raise LookupError."""
    row = get_db().execute("SELECT * FROM exercises WHERE id=?", (exercise_id,)).fetchone()
    if not row:
        raise LookupError("Exercise not found.")
    return dict(row)


def get_exercises_for_plan(goal, location, equipment_list, difficulty, available_minutes):
    """
    Select a balanced exercise set for a generated plan.
    Returns a list of exercise dicts suitable for the given constraints.
    """
    # Determine categories by goal
    goal_categories = {
        "general_fitness": ["strength", "cardio", "core"],
        "fat_loss": ["cardio", "strength", "core"],
        "strength": ["strength", "core"],
        "muscle_building": ["strength", "core"],
        "mobility": ["mobility", "flexibility"],
        "flexibility": ["flexibility", "yoga"],
        "cardio": ["cardio"],
        "home_workout": ["strength", "cardio", "core", "mobility"],
        "gym_workout": ["strength", "core"],
    }
    categories = goal_categories.get(goal, ["strength", "cardio", "core"])

    # Build equipment filter: always include bodyweight + user's equipment
    allowed_equipment = {"bodyweight", "none"}
    if equipment_list:
        allowed_equipment.update(equipment_list)
    if location == "gym":
        allowed_equipment.update({"barbell", "cable", "machine", "pull_up_bar", "bench", "dumbbell", "kettlebell"})

    db = get_db()
    placeholders_eq = ",".join("?" for _ in allowed_equipment)
    placeholders_cat = ",".join("?" for _ in categories)
    rows = db.execute(
        f"""SELECT * FROM exercises
        WHERE category IN ({placeholders_cat})
        AND equipment IN ({placeholders_eq})
        AND difficulty=?
        ORDER BY category, RANDOM()""",
        list(categories) + list(allowed_equipment) + [difficulty],
    ).fetchall()
    if not rows:
        # fallback: relax difficulty constraint
        rows = db.execute(
            f"""SELECT * FROM exercises
            WHERE category IN ({placeholders_cat})
            AND equipment IN ({placeholders_eq})
            ORDER BY category, RANDOM()""",
            list(categories) + list(allowed_equipment),
        ).fetchall()

    # Bound by time: assume ~4 min per exercise block
    minutes_budget = max(available_minutes or 45, 10)
    max_exercises = max(3, min(int(minutes_budget / 4), 12))
    return [dict(r) for r in rows[:max_exercises]]
