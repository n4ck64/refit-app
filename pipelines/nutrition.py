from ollama import chat
from prompts_and_schemas import (NUTRITION_PROMPT, NUTRITION_REVIEW_PROMPT,
                                 NUTRITION_ROUTER_PROMPT, NUTRITION_ROUTER_SCHEMA)
from retrieval import retrieve_foods, get_food_macros, daily_gaps_for_food, resolve_food_name
from memory import Memory
from llm import structured_chat
from pipelines.reviewer_and_rewriter import review_and_rewrite
import json
import logging


def route_nutrition(user_input, user_id=1):
    """Tool that determines which nutrition function to run based on the user query.
    Once llama3.1 picks the tool, hard-coded python code extracts the needed information.
    This mitigates LLM hallucination risk, as the only risk remaining is choosing the wrong tool."""
    route = structured_chat("llama3.1", NUTRITION_ROUTER_PROMPT,
                            user_input, NUTRITION_ROUTER_SCHEMA)
    logging.debug(f"Nutrition router: {route}")

    tool = route["tool"]
    food_name = route["food_name"]
    # caller default when the user named no amount
    grams = route["grams"] or 100

    if tool == "food_macros":
        if not food_name:
            return tool, None
        macros = get_food_macros(food_name, grams)
        if macros is None:
            # the DB stores food names in a very verbose manner,
            # the extracted food name is resolved via nearest neighbour vector lookup
            resolved = resolve_food_name(food_name)

            if resolved:
                macros = get_food_macros(resolved, grams)
                food_name = resolved
        if macros is None:
            # if after the above resolution nothing is found, let the user know
            return tool, f"No nutrition data found for '{food_name}'."
            # nutrients returned are calories, protein, fat, carbohydrates, free sugars and fibre
        lines = "\n".join(
            f"  {nutrient}: {amount}" for nutrient, amount in macros.items())

        final = f"Macros for {grams}g of {food_name}:\n{lines}"

        logging.debug(f"Final Macros: {final}")
        return tool, final

    if tool == "daily_gaps":
        if not food_name:
            return tool, None
        # attempts retrieval with base name, else attempts to resolve
        if get_food_macros(food_name) is None:
            food_name = resolve_food_name(food_name) or food_name
        logging.debug(
            f"Found Gaps: {daily_gaps_for_food(user_id, food_name, grams)}")
        return tool, daily_gaps_for_food(user_id, food_name, grams)

    if tool == "food_search":
        # retrieves the three most relevant foods based on the user's query
        logging.debug(retrieve_foods(user_input))
        return tool, retrieve_foods(user_input)

    # if tool == "none": general nutrition talk, no retrieval needed
    return tool, None


def run_nutrition_pipeline(user_input, user_id=1):
    """when the intent is classified as NUTRITION or NUTRITION_PLAN,
    the LLM shifts to a nutritionist role, grounded by whichever food-database
    tool route_nutrition selects for the query"""
    yield "Hungry..."

    logging.debug(f"User's message: {user_input}")

    tool, context = route_nutrition(user_input, user_id)

    if context:
        user_message = (f"Reference data from the UK food database:\n{context}\n"
                        f"(the ONLY trustworthy source for this food's figures — use these "
                        f"exact numbers, do not estimate your own or assume a different food, "
                        f"variant, or preparation than the one named above)"
                        f"\n\nUser question: {user_input}")
    else:
        user_message = f"User question: {user_input}"

    initial_response = chat("llama3.1",
                            messages=[{"role": "system", "content": NUTRITION_PROMPT}] +
                            Memory.chat_history[-10:]
                            # the user query plus any retrieved food-database context
                            + [{"role": "user", "content": user_message}],
                            options={
                                "temperature": 0.7,
                                "num_predict": 8192,
                                "num_ctx": 8192
                            },
                            stream=False)

    initial_text = initial_response.message.content
    logging.debug(f"Nutrition first response: {initial_text}")

    # context label is changed to remove the word exercise, otherwise the LLM
    # starts suggesting workouts when it is not warranted
    yield from review_and_rewrite(user_input, initial_text, NUTRITION_REVIEW_PROMPT,
                                  context, context_label="Reference data")
