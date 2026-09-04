"""
Database WRITE operations for user-generated data.
"""

import json
from retrieval import (conn, cur, db_lock)


def save_user_profile(user_id, profile):
    """Upserts the whole profile object. The merge happens upstream in the extractor,
    which sees the existing profile — writing a partial object here would silently
    drop slots the user mentioned in earlier turns."""
    with db_lock:
        try:
            cur.execute("""
                        INSERT INTO user_profile (user_id, profile, updated_at)
                        VALUES (%s, %s, now())
                        ON CONFLICT (user_id)
                        DO UPDATE SET profile = EXCLUDED.profile,
                                      updated_at = now()
                        """, (user_id, json.dumps(profile)))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def save_plan(user_id, plan_name, exercises):
    """Persists a freshly-built plan for a user, replacing any existing one —
    plans.user_id is UNIQUE, so each user has exactly one active plan."""
    names = list({exercise["name"] for exercise in exercises})
    with db_lock:
        cur.execute(
            "SELECT exercise_name, exercise_id FROM exercises WHERE exercise_name = ANY(%s)",
            (names,))
        name_to_id = dict(cur.fetchall())

        cur.execute("""
                    INSERT INTO plans (plan_name, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET plan_name = EXCLUDED.plan_name
                    RETURNING plan_id
                    """, (plan_name, user_id))
        plan_id = cur.fetchone()[0]

        cur.execute("DELETE FROM plan_exercises WHERE plan_id = %s", (plan_id,))
        for order, exercise in enumerate(exercises):
            exercise_id = name_to_id.get(exercise["name"])
            if exercise_id is None:
                continue  # shouldn't happen — plan_schema constrains names to retrieved candidates
            cur.execute("""
                        INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps, "order")
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (plan_id, exercise_id, exercise["day"], exercise["sets"], exercise["reps"], order))
        conn.commit()


_EDITABLE_FIELDS = {"sets", "reps"}


def apply_plan_edits(user_id, edits):
    """Applies a batch of already-resolved plan edits (see pipelines.route_plan_edit)
    to a user's plan_exercises rows, as one transaction. Each edit dict, by op:
      - move_day:       {op, from_day, to_day}            — moves every exercise on from_day
      - move_exercise:  {op, plan_exercise_id, to_day}
      - relative_param: {op, plan_exercise_id, field, amount}  — amount is a signed delta
      - absolute_param: {op, plan_exercise_id, field, amount}  — amount is the target value
      - add_exercise:   {op, exercise_id, day, sets, reps}
      - remove_exercise:{op, plan_exercise_id}                 — deletes the row entirely
    Raises ValueError if the user has no plan to edit."""
    with db_lock:
        cur.execute('SELECT plan_id FROM plans WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError("No plan exists for this user")
        plan_id = row[0]

        for edit in edits:
            operation = edit["op"]
            if operation == "move_day":
                cur.execute("""
                            UPDATE plan_exercises SET day = %s
                            WHERE plan_id = %s AND day = %s
                            """, (edit["to_day"], plan_id, edit["from_day"]))
            elif operation == "move_exercise":
                cur.execute("""
                            UPDATE plan_exercises SET day = %s
                            WHERE plan_exercise_id = %s AND plan_id = %s
                            """, (edit["to_day"], edit["plan_exercise_id"], plan_id))
            elif operation in ("relative_param", "absolute_param"):
                field = edit["field"]
                if field not in _EDITABLE_FIELDS:
                    raise ValueError(
                        f"field must be one of {_EDITABLE_FIELDS}, got {field!r}")
                if operation == "relative_param":
                    cur.execute(f"""
                                UPDATE plan_exercises SET {field} = {field} + %s
                                WHERE plan_exercise_id = %s AND plan_id = %s
                                """, (edit["amount"], edit["plan_exercise_id"], plan_id))
                else:
                    cur.execute(f"""
                                UPDATE plan_exercises SET {field} = %s
                                WHERE plan_exercise_id = %s AND plan_id = %s
                                """, (edit["amount"], edit["plan_exercise_id"], plan_id))
            elif operation == "remove_exercise":
                cur.execute("""
                            DELETE FROM plan_exercises
                            WHERE plan_exercise_id = %s AND plan_id = %s
                            """, (edit["plan_exercise_id"], plan_id))
            elif operation == "add_exercise":
                cur.execute(
                    'SELECT COALESCE(MAX("order"), -1) + 1 FROM plan_exercises WHERE plan_id = %s',
                    (plan_id,))
                next_order = cur.fetchone()[0]
                cur.execute("""
                            INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps, "order")
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """, (plan_id, edit["exercise_id"], edit["day"],
                                  edit.get("sets", 3), edit.get("reps", 10), next_order))
        conn.commit()
