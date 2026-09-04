from ollama import chat
from prompts_and_schemas import (INTAKE_PROMPT, INTAKE_SCHEMA, PLAN_PROMPT, plan_schema,
                                 PLAN_EDIT_PROMPT, PLAN_EDIT_SCHEMA)
from retrieval import retrieve_exercises, get_user_plan_rows, resolve_exercise_name, get_exercise_id
from memory import Memory
from llm import structured_chat
from user_data import save_plan, apply_plan_edits
from classification import classify_injured_muscle, classify_target_muscle
import json
import logging

WEEK = ["monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"]

# how many clarifying questions a single plan edit may ask before it gives up and
# resets, so an edit that never resolves can't trap the user in the loop forever
# which happened once during development...
MAX_EDIT_CLARIFICATIONS = 3


def _spread_days(number_of_days):
    """Picks weekdays spread across the week when the user gives a number but 
    does not name specific days (3 -> mon/wed/fri)."""
    if number_of_days >= 7:
        return WEEK
    step = 7 / number_of_days
    return [WEEK[int(i * step)] for i in range(number_of_days)]


# minimum number of exercises per day
_MIN_PER_DAY = 3
# exercises containing these keywords may appear twice in a week
# else exercises are limited to appearing only once per week
_COMPOUND_KEYWORDS = ("squat", "bench", "deadlift")


def _goal_set_reps(goal):
    """Representative (sets, reps) per goal. Used to fill topped-up rows."""
    return {"strength": (5, 5), "hypertrophy": (4, 10)}.get(goal, (3, 12))


def _exercise_cap(name):
    """Hard-coded cap on the max times one exercise may appear 
    across the week: major compounds twice, everything else once """
    exercise_name = name.lower()
    return 2 if any(keyword in exercise_name for keyword in _COMPOUND_KEYWORDS) else 1


def _topup_days(exercises, names, days, goal):
    """Ensure every training day has at least _MIN_PER_DAY exercises by appending
    the most-relevant unused candidate exercises. Only fills sparse days and never trims full ones. 
    Mutates and returns 'exercises'."""
    # the amount of times an exercise is seen in a plan
    usage = {}
    for exercise in exercises:
        usage[exercise["name"].lower()] = usage.get(
            exercise["name"].lower(), 0) + 1

    sets, reps = _goal_set_reps(goal)

    for day in days:
        exercise_names_this_day = {exercise["name"].lower(
        ) for exercise in exercises if exercise["day"] == day}
        for candidate_exercise in names:
            if len(exercise_names_this_day) >= _MIN_PER_DAY:
                break
            key = candidate_exercise.lower()
            if key in exercise_names_this_day:
                # already on this day
                continue
            if usage.get(key, 0) >= _exercise_cap(candidate_exercise):
                # weekly cap reached
                continue
            exercises.append(
                {"name": candidate_exercise, "day": day, "sets": sets, "reps": reps})
            usage[key] = usage.get(key, 0) + 1
            exercise_names_this_day.add(key)
    return exercises


def run_plan_pipeline(user_input, user_id=1):
    """Multi-turn plan builder. Accumulates INTAKE slots in Memory across turns,
    asks one combined clarifying question until goal + days are known, then builds
    the plan JSON by constrained decoding and persists it for the Plans page."""

    yield "Making Plan..."
    new_plan = structured_chat(
        "llama3.1", INTAKE_PROMPT, user_input, INTAKE_SCHEMA)

    # merge this turn's non-null answers into the running slots
    slots = Memory.plan_slots or {"which_days": None, "number_of_days": None,
                                  "goal": None, "injury": None,
                                  "focus": None, "equipment": None}
    for field, value in new_plan.items():
        if value is not None:
            slots[field] = value
    Memory.plan_slots = slots

    if slots["which_days"] and not slots["number_of_days"]:
        # e.g. if user states monday, tuesday and wednesday, it resolves it to 3 days
        slots["number_of_days"] = len(slots["which_days"])

    logging.debug(f"Plan intake slots: {slots}")

    # if it is still missing what it needs to build, it asks one combined question and waits
    missing = []
    if not slots["goal"]:
        missing.append("your goal (bigger, stronger, or general wellbeing)")
    if not slots["which_days"] and not slots["number_of_days"]:
        missing.append("how many days a week (or which days) you can train")
    if missing:
        yield "Before I build your plan, tell me " + " and ".join(missing) + "."
        return

    # enough info — retrieve candidate exercises (injury-aware) and build the plan
    days = slots["which_days"] or _spread_days(slots["number_of_days"])
    injured_ids = None
    if slots["injury"] and slots["injury"] != "none":
        injured_ids = classify_injured_muscle(slots["injury"])

    # if user indicates a body-part to focus, it gets turned into target muscle ids
    target_ids = classify_target_muscle(
        slots["focus"]) if slots["focus"] else None

    # equipment is filtered if specified, else exercises with all equipments are retrieved
    equipment = slots["equipment"] or None

    # scale candidate exexrices with the week: more days need more exercises to fill
    top_k = max(15, len(days) * 4)
    query = f"{slots['focus'] or ''} {slots['goal']} training exercises".strip()
    context = retrieve_exercises(query, top_k=top_k, target_muscle_id=target_ids,
                                 injured_muscle_id=injured_ids, equipment=equipment)
    names = [line.replace("Exercise: ", "")
             for line in context.split("\n") if line.startswith("Exercise: ")]
    logging.debug(f"Plan filters: injured={injured_ids} target={target_ids} "
                  f"equipment={equipment} query={query!r}")
    logging.debug(f"Plan candidates: {names}")

    plan = structured_chat(
        "llama3.1",
        PLAN_PROMPT + f"\n\nGoal: {slots['goal']}\nDays: {', '.join(days)}",
        context, plan_schema(names, days))

    logging.debug(f"Plan JSON (model): {plan}")

    # the model tends to return too few exercises, the below function ensures each day
    # has at least 3 exercises
    _topup_days(plan["exercises"], names, days, slots["goal"])

    logging.debug(f"Plan JSON (after topup): {plan}")

    plan_name = f"{slots['goal'].capitalize()} plan" if slots["goal"] else "Weekly plan"
    save_plan(user_id, plan_name, plan["exercises"])
    # plan-making is finished, closes the loop
    Memory.plan_slots = None
    yield _plan_to_markdown(plan)
    yield "\n\n*Open the [Plans](#plans) tab to track it.*"


def _normalize_exercise_name(name):
    """Lowercases and strips a trailing plural 's' (but not 'ss') so "squats"
    matches a plan row named "Squat" — the router paraphrases names loosely."""
    name = name.lower().strip()
    return name[:-1] if name.endswith("s") and not name.endswith("ss") else name


def _match_plan_exercise(name, plan_rows):
    """Finds plan rows whose name matches the name the router extracted: 
    exact match first, then plural/substring-tolerant."""
    name_lower = name.lower().strip()
    exact = [row for row in plan_rows if row["name"].lower() == name_lower]
    if exact:
        return exact
    name_normalised = _normalize_exercise_name(name)
    return [row for row in plan_rows if _normalize_exercise_name(row["name"]) == name_normalised
            or name_normalised in row["name"].lower() or row["name"].lower() in name_normalised]


def _narrow_by_day(matches, text, exclude=None):
    """When an exercise sits on more than one day, a clarifying answer like
    "the monday one" names the day. Keep only rows whose day is mentioned in
    'text', ignoring 'exclude' (the destination day of a move, which would
    otherwise be mistaken for the source)."""
    text_lower = text.lower()
    return [match for match in matches if match["day"] in text_lower and match["day"] != exclude]


def _resolve_edit(edit, plan_rows, text):
    """Resolves one router-extracted edit against the current plan. Returns
    (resolved_op, None) on success, or (None, question) when a clarification is
    needed — the caller then stashes context and asks, applying nothing."""
    operation = edit["op"]

    if operation == "move_day":
        if not edit["from_day"] or not edit["to_day"]:
            return None, "Which day should I move, and to which day?"
        return {"op": operation, "from_day": edit["from_day"], "to_day": edit["to_day"]}, None

    name = edit["exercise_name"]
    if not name:
        return None, "Which exercise did you mean?"

    if operation == "add_exercise":
        if not edit["to_day"]:
            return None, f"Which day should I add {name} on?"
        canonical = resolve_exercise_name(name)
        exercise_id = get_exercise_id(canonical) if canonical else None
        if exercise_id is None:
            return None, f"I couldn't find an exercise matching '{name}'."
        return {"op": operation, "exercise_id": exercise_id, "day": edit["to_day"]}, None

    matches = _match_plan_exercise(name, plan_rows)

    if not matches:
        return None, f"I don't see '{name}' in your current plan — did you mean something else?"
    # move_exercise has only one meaningful day (the destination); the router
    # sometimes drops a bare day into from_day instead of to_day,
    # so treat whichever it filled as the destination.
    destination_day = edit["to_day"] or (
        edit["from_day"] if operation == "move_exercise" else None)

    if len(matches) > 1:
        # a compound lift can appear on two days. If the (possibly
        # continued) text names one of those days, it is used, otherwise it asks.
        narrowed = _narrow_by_day(matches, text, exclude=destination_day)
        if len(narrowed) == 1:
            matches = narrowed
        else:
            days = ", ".join(match["day"].capitalize() for match in matches)
            return None, f"You have {name} on multiple days ({days}) — which day's should I change?"

    # if the above filtering somehow fails, pulls the first match
    target = matches[0]

    if operation == "remove_exercise":
        return {"op": operation, "plan_exercise_id": target["plan_exercise_id"]}, None

    if operation == "move_exercise":
        if not destination_day:
            return None, f"Which day should I move {name} to?"
        return {"op": operation, "plan_exercise_id": target["plan_exercise_id"],
                "to_day": destination_day}, None

    if operation in ("relative_param", "absolute_param"):
        # relative_param -> increase the squat reps by 5
        # absolute_param -> set squat reps to 12

        field, amount = edit["field"], edit["amount"]
        if field not in ("sets", "reps") or amount is None:
            return None, f"How many {field or 'sets/reps'} for {name}?"

        # maximum allowed sets are 6, maximum allowed reps are 20
        bound = 6 if field == "sets" else 20
        target_value = (
            target[field] + amount) if operation == "relative_param" else amount
        if not (1 <= target_value <= bound):
            return None, f"{target_value} {field} for {name} is outside a sane range (1-{bound})."
        return {"op": operation, "plan_exercise_id": target["plan_exercise_id"],
                "field": field, "amount": amount}, None

    # if all else fails
    return None, "I couldn't tell what you'd like to change — could you rephrase?"


def _edit_and_record(user_input, user_id, prior=None):
    """Runs route_plan_edit and appends the exchange to chat history. Shared by
    the PLAN_EDIT intent branch and the pending-edit continuation short-circuit."""
    response_content = ""
    for token in route_plan_edit(user_input, user_id, prior):
        response_content += token
        yield token
    Memory.chat_history += [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": response_content},
    ]


def route_plan_edit(user_input, user_id, prior=None):
    """Handles PLAN_EDIT intent: extracts one or more edit operations, 
    resolves exercise_name/day/field in Python against the user's current plan,
    (or the full exercise catalogue for add_exercise), and applies the whole batch 
    via apply_plan_edits. If any operation is unresolved, ambiguous or out of range, 
    Memory.pending_edit gets filled and it asks one clarifying question. The user's response 
    is stored as the prior parameter and handled without triggering the intent stage."""
    plan_rows = get_user_plan_rows(user_id)
    if not plan_rows:
        Memory.pending_edit = None
        yield "You don't have a plan yet — want me to build one?"
        return

    # If this goes over _MAX_EDIT_CLARIFICATIONS, reset; None on a fresh edit means this is attempt zero.
    prev_turns = Memory.pending_edit["turns"] if Memory.pending_edit else 0

    # a continued turn answers a prior question; give the router the full context
    combined = f"{prior}\n{user_input}" if prior else user_input

    Memory.pending_edit = None  # consumed — re-set below only if we must ask again

    raw = structured_chat("llama3.1", PLAN_EDIT_PROMPT,
                          combined, PLAN_EDIT_SCHEMA)
    logging.debug(f"Plan edit router (prior={prior!r}): {raw}")

    if not raw["edits"]:
        yield "I couldn't tell what you'd like to change — could you rephrase?"
        return

    resolved = []
    for edit in raw["edits"]:
        operation, question = _resolve_edit(edit, plan_rows, combined)
        if question:
            # carries context + the question, and bumps the attempt counter
            Memory.pending_edit = {"context": combined, "question": question,
                                   "turns": prev_turns + 1}
            yield question
            return
        resolved.append(operation)

    apply_plan_edits(user_id, resolved)
    yield "Updated your plan.\n\n*Open the [Plans](#plans) tab to see it.*"


def _plan_to_markdown(plan):
    """Render the built plan as markdown (headings + bullet lists) for the chat.
    Days in Mon->Sun order; rendered in plain react-markdown without additional plugins."""
    lines = ["**Your weekly plan**\n"]
    for day in WEEK:
        day_exercises = [
            exercise for exercise in plan["exercises"] if exercise["day"] == day]
        if not day_exercises:
            continue
        lines.append(f"**{day.capitalize()}**")
        for exercise in day_exercises:
            lines.append(
                f"- {exercise['name']} — {exercise['sets']}×{exercise['reps']}")
        lines.append("")
    return "\n".join(lines)
