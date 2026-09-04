"""
All Postgres database retrieval functions live here
"""

from datetime import date, timedelta
import getpass
import os
import threading

import ollama
import psycopg2

# to use the app, user must have Postgres installed on device and be logged in
# os module gets the authentication details below
conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()
db_lock = threading.RLock()


def retrieve_exercises(query, top_k=3, target_muscle_id=None, injured_muscle_id=None,
                       equipment=None):
    """Queries the database to retrieve the top_k most relevant exercises
    based on the user's input and the corresponding generated embedding.
    Optionally constrained to a target muscle, a set of allowed equipment,
    and/or excluding an injured muscle"""

    response = ollama.embed(model="nomic-embed-text", input=f"search_query: {query}")\

    embedding = response.embeddings[0]

    conditions, params = [], []

    if target_muscle_id:
        conditions.append("""exercise_id IN (
        SELECT exercise_id FROM muscles_exercised
        WHERE muscle_id = ANY(%s) AND role = 'Primary')""")
        params.append(target_muscle_id)

    if equipment:
        conditions.append("equipment = ANY(%s)")
        params.append(equipment)

    if injured_muscle_id:
        conditions.append("""exercise_id NOT IN (
            SELECT exercise_id FROM muscles_exercised WHERE muscle_id = ANY(%s))""")
        params.append(injured_muscle_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db_lock:
        cur.execute(f"""
        SELECT exercise_id, exercise_name, description, type, difficulty, equipment
        FROM exercises
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """, params + [embedding, top_k])

        rows = cur.fetchall()

    # if the target-muscle filter matched nothing, drop it but keep the equipment
    # constraint (the user still cares which kit they have) and search again
    if not rows and target_muscle_id:
        return retrieve_exercises(query, top_k=top_k, injured_muscle_id=injured_muscle_id,
                                  equipment=equipment)

    results = []
    for ex_id, name, description, type_, difficulty, equipment in rows:
        m = _muscles_for_exercise(ex_id)
        results.append(
            f"Exercise: {name}\n"
            f"Type: {type_}\n"
            f"Difficulty: {difficulty}\n"
            f"Equipment: {equipment}\n"
            f"Muscles — Primary: {m['Primary']} | Secondary: {m['Secondary']} | Stabilisers: {m['Stabiliser']}\n"
            f"Description: {description}")
    return "\n\n".join(results)


def _muscles_for_exercise(exercise_id):
    """Returns an exercise's worked muscles grouped by role (Primary, Secondary,
    Stabiliser) as display strings, for grounding the answerer and reviewer."""
    with db_lock:
        cur.execute("""
                    SELECT me.role, string_agg(m.muscle_name, ', ' ORDER BY m.muscle_name)
                    FROM muscles_exercised me
                    JOIN muscles m ON m.muscle_id = me.muscle_id
                    WHERE me.exercise_id = %s
                    GROUP BY me.role
                    """, (exercise_id,))

        grouped = {"Primary": "none listed",
                   "Secondary": "none listed", "Stabiliser": "none listed"}
        # default values as none listed until appended

        for role, names in cur.fetchall():
            grouped[role] = names
    return grouped


def retrieve_exercise_names(description, top_k=3):
    """Queries the database to retrieve the three most relevant exercises
    based on the provided description and the corresponding generated embedding.
    This function is only used for the video analysis."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {description}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT exercise_name
                    FROM exercises
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        rows = cur.fetchall()
    results = []
    for name in rows:
        results.append(name[0])
    return results


def retrieve_exercise_description(name):
    """Retrieves the description of the exercise that matches the given name.
    Used in the last step of the video analysis pipeline."""
    with db_lock:
        cur.execute("""
                    SELECT description
                    FROM exercises
                    WHERE exercise_name ILIKE %s
                    """, (name,))
        result = cur.fetchone()
    if result is None:
        return None
    return result[0]


def retrieve_foods(query, top_k=3):
    """Queries the database to retrieve the most relevant foods
    based on the user's input, returning their key macros per 100g of food.
    Used by the nutrition talk pipeline."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT food_name, kcal, protein_g, fat_g, carb_g, total_sugars_g, fibre_nsp_g
                    FROM foods
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        rows = cur.fetchall()

    def fmt(value, unit):
        # CoFID leaves some nutrients unmeasured (stored as NULL).
        return f"{value}{unit}" if value is not None else "N/A"

    results = []
    for name, kcal, protein, fat, carb, sugars, fibre in rows:
        results.append(
            f"Food: {name} (per 100g)\n"
            f"Energy: {fmt(kcal, ' kcal')} | Protein: {fmt(protein, 'g')} | "
            f"Fat: {fmt(fat, 'g')} | Carbohydrate: {fmt(carb, 'g')} | "
            f"Sugars: {fmt(sugars, 'g')} | Fibre: {fmt(fibre, 'g')}")
    return "\n\n".join(results)


# Cosine-distance cutoff above which an embedding match is treated as no match.

FOOD_MATCH_MAX_DISTANCE = 0.35


def resolve_food_name(query, top_k=1, max_distance=None):
    """Maps the lay food name (e.g. "chicken breast") to the nearest
    match in the database. This allows for nutrition RAG functions to
    retrieve data without returning None.
    Passing max_distance rejects matches further away than that cutoff, returning
    None instead of the closest row. Defaults to
    off, so the read-side callers keep their always-return-something behaviour."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT food_name, embedding <=> %s::vector AS distance
                    FROM foods
                    ORDER BY distance
                    LIMIT %s
                    """, (embedding, top_k))
        row = cur.fetchone()
    if row is None or (max_distance is not None and row[1] > max_distance):
        return None
    return row[0]


def retrieve_nutrient_targets(sex, age):
    """Returns the UK daily dietary guideline values (PHE 2016) for a user of
    the given sex ('M'/'F') and age, as a {nutrient: (value, limit_type)} dict.
    limit_type is 'target', 'min' (at least) or 'max' (less than)."""
    with db_lock:
        cur.execute("""
                    SELECT nutrient, value, limit_type
                    FROM nutrient_reference
                    WHERE sex = %s AND %s BETWEEN age_min AND age_max
                    """, (sex, age))
        return {nutrient: (value, limit_type) for nutrient, value, limit_type in cur.fetchall()}


def get_user_sex_age(user_id):
    """Returns (sex, age_in_years) for a user, age derived from date_of_birth.
    Returns None if the user or their date of birth is missing."""
    with db_lock:
        cur.execute(
            'SELECT gender, date_of_birth FROM "user" WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
    if row is None or row[1] is None:
        return None
    gender, dob = row
    today = date.today()
    age = today.year - dob.year - \
        ((today.month, today.day) < (dob.month, dob.day))
    return gender, age


# Shared by every per-food lookup so the column order
_MACRO_COLUMNS = """kcal, protein_g, fat_g, carb_g, total_sugars_g,
                    COALESCE(fibre_aoac_g, fibre_nsp_g)"""

# Nutrients the guideline covers but the food data cannot honestly be scored
# against, so they are excluded from targets and tracked as bare numbers instead:
UNTARGETED_NUTRIENTS = {"satfat_g", "free_sugars_g"}


def _scale_macros(row, grams):
    """Scales a _MACRO_COLUMNS row from per-100g to 'grams', keyed to match the
    nutrient_reference nutrients."""
    kcal, protein, fat, carb, sugars, fibre = row
    factor = grams / 100.0
    scaled = {"energy_kcal": kcal, "protein_g": protein, "fat_g": fat,
              "carb_g": carb, "total_sugars_g": sugars, "fibre_g": fibre}
    return {nutrient: round(value * factor, 1)
            for nutrient, value in scaled.items() if value is not None}


def get_food_macros(food_name, grams=100):
    """Returns a food's macros scaled to 'grams', keyed to match the
    nutrient_reference nutrients (looked up by name, case-insensitive)"""

    with db_lock:
        cur.execute(f"""
                    SELECT {_MACRO_COLUMNS}
                    FROM foods
                    WHERE food_name ILIKE %s
                    ORDER BY length(food_name)
                    LIMIT 1
                    """, (food_name,))
        row = cur.fetchone()
    return _scale_macros(row, grams) if row else None


def effective_targets(user_id):
    """The user's daily nutrient targets: the PHE population guideline for their
    sex/age with any per-user override layered on top, minus the nutrients in
    UNTARGETED_NUTRIENTS. Returns {nutrient: (value, limit_type)}, or None if the
    user has no record or date of birth on file."""
    context = get_user_sex_age(user_id)
    if context is None:
        return None
    sex, age = context
    targets = retrieve_nutrient_targets(sex, age)
    with db_lock:
        cur.execute("""
                    SELECT nutrient, value, limit_type
                    FROM user_nutrition_targets
                    WHERE user_id = %s
                    """, (user_id,))
        targets.update({nutrient: (value, limit_type)
                        for nutrient, value, limit_type in cur.fetchall()})
    return {nutrient: target for nutrient, target in targets.items()
            if nutrient not in UNTARGETED_NUTRIENTS}


def compute_macro_gaps(targets, consumed):
    """Compares a dict of consumed macros against the given daily targets (see
    effective_targets) and returns, per nutrient, the amount consumed, the target,
    its limit_type, and 'remaining' (target - consumed): for 'target'/'min' how
    much is left to go; for 'max' the headroom left, where a negative value means
    the limit is exceeded."""
    result = {}
    for nutrient, (target, limit_type) in targets.items():
        amount = consumed.get(nutrient)
        if amount is None:
            continue
        result[nutrient] = {
            "consumed": amount,
            "target": target,
            "limit_type": limit_type,
            "remaining": round(target - amount, 1),
        }
    return result


# translating DB column names to natural language
_NUTRIENT_LABELS = {"energy_kcal": "Energy (kcal)", "protein_g": "Protein (g)",
                    "fat_g": "Fat (g)", "carb_g": "Carbohydrate (g)",
                    "fibre_g": "Fibre (g)", "total_sugars_g": "Total sugars (g)"}


def _format_gaps(header, gaps):
    """Renders compute_macro_gaps output as the readable lines both the
    single-food and whole-day summaries hand to the LLM."""
    lines = [header]
    for nutrient, gap in gaps.items():
        if gap["limit_type"] == "max":
            note = (f"{abs(gap['remaining'])} over limit" if gap["remaining"] < 0
                    else f"{gap['remaining']} headroom left")
        else:
            note = (f"{gap['remaining']} to go" if gap["remaining"] > 0
                    else "target met")
        lines.append(f"  {_NUTRIENT_LABELS.get(nutrient, nutrient)}: {gap['consumed']} "
                     f"of {gap['target']} ({gap['limit_type']}) -> {note}")
    return "\n".join(lines)


def daily_gaps_for_food(user_id, food_name, grams=100):
    """End-to-end: how eating 'grams' of 'food_name' contributes toward a user's
    daily UK dietary guideline. Returns a readable summary, or a note if the
    user/date of birth or the food is missing."""
    targets = effective_targets(user_id)
    if targets is None:
        return "No user record or date of birth on file."
    consumed = get_food_macros(food_name, grams)
    if consumed is None:
        return f"No food matching '{food_name}' found."
    sex, age = get_user_sex_age(user_id)
    return _format_gaps(f"{grams}g of {food_name} vs daily guideline ({sex}, age {age}):",
                        compute_macro_gaps(targets, consumed))


def _muscle_roles_for_exercise(exercise_id):
    """Like _muscles_for_exercise but also returns the raw muscle_ids per role,
    for the frontend MuscleMap to key highlighting off of — a parallel field
    alongside the existing display-name strings, not a replacement. Used by
    list_exercises; kept separate from _muscles_for_exercise (which stays
    string-only for the RAG-context callers) to avoid a second query there."""
    with db_lock:
        cur.execute("""
                    SELECT me.role, m.muscle_id, m.muscle_name
                    FROM muscles_exercised me
                    JOIN muscles m ON m.muscle_id = me.muscle_id
                    WHERE me.exercise_id = %s
                    ORDER BY m.muscle_name
                    """, (exercise_id,))
        rows = cur.fetchall()

    names = {"Primary": [], "Secondary": [], "Stabiliser": []}
    ids = {"Primary": [], "Secondary": [], "Stabiliser": []}
    for role, muscle_id, muscle_name in rows:
        names[role].append(muscle_name)
        ids[role].append(muscle_id)

    display = {role: ", ".join(names[role]) or "none listed" for role in names}
    return display, ids


def list_exercises():
    """Returns a list of dictionaries of all exercises within the database
    for searching and browsing within the 'Exercises' tab"""
    with db_lock:
        cur.execute("""
        SELECT exercise_id, exercise_name, description, type, difficulty, equipment
        FROM exercises
        ORDER BY exercise_name
        """)

        rows = cur.fetchall()

        exercises = []

        for ex_id, name, description, type_, difficulty, equipment in rows:
            muscles, muscle_ids = _muscle_roles_for_exercise(ex_id)
            exercises.append({
                "id": ex_id,
                "name": name,
                "description": description,
                "type": type_,
                "difficulty": difficulty,
                "equipment": equipment,
                "muscles": muscles,
                "muscle_ids": muscle_ids,
            })
    return exercises


PROFILE_SLOTS = ("conditions", "medications", "injuries", "goals", "equipment",
                 "constraints", "other")


def get_user_plan(user_id):
    """Returns a user's current plan as {"exercises": [{name, day, sets, reps}, ...]},
    ordered the same way it was built, or None if they have no plan yet."""
    with db_lock:
        cur.execute("""
                    SELECT e.exercise_name, pe.day, pe.sets, pe.reps
                    FROM plans p
                    JOIN plan_exercises pe ON pe.plan_id = p.plan_id
                    JOIN exercises e ON e.exercise_id = pe.exercise_id
                    WHERE p.user_id = %s
                    ORDER BY pe."order"
                    """, (user_id,))
        rows = cur.fetchall()
    if not rows:
        return None
    return {"exercises": [
        {"name": name, "day": day, "sets": sets, "reps": reps}
        for name, day, sets, reps in rows
    ]}


def get_user_plan_rows(user_id):
    """Like get_user_plan, but includes plan_exercise_id/exercise_id — used by
    the plan-edit pipeline(pipelines.route_plan_edit) to target a specific row
    for a move/param edit. Plans.tsx doesn't need these ids, hence the separate
    function."""
    with db_lock:
        cur.execute("""
                    SELECT pe.plan_exercise_id, e.exercise_id, e.exercise_name, pe.day, pe.sets, pe.reps
                    FROM plans p
                    JOIN plan_exercises pe ON pe.plan_id = p.plan_id
                    JOIN exercises e ON e.exercise_id = pe.exercise_id
                    WHERE p.user_id = %s
                    ORDER BY pe."order"
                    """, (user_id,))
        rows = cur.fetchall()
    return [{"plan_exercise_id": plan_id, "exercise_id": exercise_id, "name": name,
             "day": day, "sets": sets, "reps": reps}
            for plan_id, exercise_id, name, day, sets, reps in rows]


def get_exercise_id(exercise_name):
    """Exact(case-insensitive) exercise_name -> exercise_id lookup. Used to
    resolve an add_exercise plan edit after resolve_exercise_name finds the
    canonical name."""
    with db_lock:
        cur.execute(
            "SELECT exercise_id FROM exercises WHERE exercise_name ILIKE %s LIMIT 1",
            (exercise_name,))
        row = cur.fetchone()
    return row[0] if row else None


def resolve_exercise_name(query, top_k=1):
    """Maps a free-text exercise name(e.g. "lunges") to the closest canonical
    exercise_name via embedding search. Used to resolve an add_exercise plan edit
    to a real exercise_id. Returns the best-matching exercise_name, or None if the table is empty."""

    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT exercise_name
                    FROM exercises
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        row = cur.fetchone()
    return row[0] if row else None


# =========================== Unused =============================================

def get_user_profile(user_id):
    """Returns the accumulated profile as a dict of slot -> list of strings.
    Missing slots come back empty, so a caller never has to guard for them."""
    with db_lock:
        cur.execute(
            "SELECT profile FROM user_profile WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
    stored = row[0] if row and row[0] else {}
    return {slot: list(stored.get(slot) or []) for slot in PROFILE_SLOTS}


def format_user_profile(profile):
    """Renders a profile for a prompt. Returns "" when nothing is known, so the
    caller can inject it unconditionally without emitting an empty heading."""
    lines = [f"- {slot.capitalize()}: {'; '.join(values)}"
             for slot, values in profile.items() if values]
    return "\n".join(lines)


def get_food_macros_by_id(food_id, grams=100):
    """Macros for a food looked up by primary key. Used once a food_id is already
    resolved, where get_food_macros' ILIKE-and-shortest-match could land on a
    different row than the one that id refers to."""
    with db_lock:
        cur.execute(
            f"SELECT {_MACRO_COLUMNS} FROM foods WHERE id = %s", (food_id,))
        row = cur.fetchone()
    return _scale_macros(row, grams) if row else None


def get_food_id(food_name):
    """Maps an exact (case-insensitive) food name to its primary key, preferring
    the shortest match the same way get_food_macros does."""
    with db_lock:
        cur.execute("""
                    SELECT id
                    FROM foods
                    WHERE food_name ILIKE %s
                    ORDER BY length(food_name)
                    LIMIT 1
                    """, (food_name,))
        row = cur.fetchone()
    return row[0] if row else None


def get_exercise_ratings(user_id, exercise_id=None):
    """Returns a user's self-reported exercise difficulty ratings as an
    {exercise_id: difficulty} dict. Pass exercise_id to fetch a single one
    (dict with 0 or 1 entry); omit it for all of the user's ratings."""
    with db_lock:
        if exercise_id is None:
            cur.execute("""
                        SELECT exercise_id, difficulty
                        FROM user_exercise_difficulty
                        WHERE user_id = %s
                        """, (user_id,))
        else:
            cur.execute("""
                        SELECT exercise_id, difficulty
                        FROM user_exercise_difficulty
                        WHERE user_id = %s AND exercise_id = %s
                        """, (user_id, exercise_id))
        return {ex_id: difficulty for ex_id, difficulty in cur.fetchall()}
