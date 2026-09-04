from ollama import chat
from prompts_and_schemas import SYSTEM_PROMPT, EXERCISE_REVIEW_PROMPT
from retrieval import retrieve_exercises
from memory import Memory
from classification import (classify_intent, classify_injured_muscle, condense_query,
                            classify_target_muscle, answers_pending_question)
from pipelines.reviewer_and_rewriter import review_and_rewrite
from pipelines.plan import run_plan_pipeline, _edit_and_record, MAX_EDIT_CLARIFICATIONS
from pipelines.nutrition import run_nutrition_pipeline
import json
import logging


def run_chat_pipeline(user_input, user_id=1):
    """The main driver behind the chatting part of the app.
    Takes user input, clarifies intent, retrieves
    relevant exercises, reviews initial answer,
    and returns final response."""

    if user_input.strip().lower() == "/clear":
        # wipe the history for debugging
        Memory.clear()
        yield "Chat History Cleared."
        return

    # Debugging function for changing users without authentication
    # when user is changed, chat and plan history get wiped
    if Memory.current_user_id is not None and Memory.current_user_id != user_id:
        Memory.clear()
    Memory.current_user_id = user_id

    # when a plan is in the middle of being made, does not run the
    # classification step on the user's replies
    if Memory.plan_slots is not None:
        yield from run_plan_pipeline(user_input, user_id)
        return

    if Memory.pending_edit is not None:
        pending = Memory.pending_edit
        if pending["turns"] >= MAX_EDIT_CLARIFICATIONS:
            Memory.pending_edit = None
            yield "Let's start that over — what would you like to change?"
            return
        if answers_pending_question(pending["question"], user_input):
            yield from _edit_and_record(user_input, user_id, prior=pending["context"])
            return
        Memory.pending_edit = None

    logging.debug("=" * 100)
    logging.debug(f"User's message: {user_input}")

    response_content = ""

    # follow-up queries get condensed into one, for better context retention
    yield "Commencing..."
    rewritten_query = condense_query(user_input)
    logging.debug(f"User input rewritten as: {rewritten_query}")

    # determines user intent before proceeding
    intent = classify_intent(rewritten_query)

    yield "Classifying User Query..."

    Memory.last_intent = intent
    logging.debug(f"Intent classified as: {intent}")

    if intent in ("EXERCISE_INJURY"):
        injured_muscle_ids = classify_injured_muscle(rewritten_query)
        logging.debug(f"Injured muscle: {injured_muscle_ids}")

        retrieved = retrieve_exercises(
            rewritten_query, injured_muscle_id=injured_muscle_ids)

    elif intent in ("EXERCISE_GENERAL"):
        target_muscle_ids = classify_target_muscle(rewritten_query)
        logging.debug(f"Target Muscle: {target_muscle_ids}")
        retrieved = retrieve_exercises(
            rewritten_query, target_muscle_id=target_muscle_ids)

    elif intent in ("PLAN_GENERAL", "PLAN_INJURY"):
        # reads the raw user query, not the condensed version
        # this avoids loss of intent due to LLM rewrite
        yield from run_plan_pipeline(user_input, user_id)
        return

    elif intent == "PLAN_EDIT":
        yield from _edit_and_record(user_input, user_id)
        return

    elif intent in ("NUTRITION", "NUTRITION_PLAN"):
        retrieved = None  # nutrition talk requires no RAG
        for token in run_nutrition_pipeline(rewritten_query, user_id):
            response_content += token
            yield token

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]

        logging.debug(f"Final response: {response_content}")

        return

    else:
        retrieved = None

        response = chat("llama3.1", messages=[
            {"role": "system",
                "content": "You are a helpful fitness assistant. Be conversational and brief."}] + Memory.chat_history[-10:]
            + [{"role": "user", "content": user_input}
               ], stream=True)

        for chunk in response:
            token = chunk.message.content
            response_content += token
            yield token

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]

        return

    if Memory.plan_slots:
        pass
    else:
        logging.info(f"RAG retrieved: {retrieved}")
        # below is the result of the SQL queries
        rag_context = f"Relevant exercises:\n\n{retrieved}"

    # highlights the retrieved exercises used in chat, so they can be clickable in chat
    Memory.last_exercises = [
        line.replace("Exercise: ", "")
        for line in (retrieved or "").split("\n")
        if line.startswith("Exercise: ")
    ]

    yield "Thinking..."
    initial_response = chat("llama3.1",
                            # the system prompt
                            messages=[{"role": "system", "content": SYSTEM_PROMPT}] +
                            # context from the last 5 messages
                            Memory.chat_history[-10:]
                            # the user query plus the SQL results, with a rule to
                            # only use retrieved context when relevant,
                            # e.g. if user asks how long to rest between sets,
                            # it should not not recommend exercises
                            + [{"role": "user", "content":
                                f"""{rag_context}\n(background grounding only — do not name a 
                                specific exercise unless the user is choosing what to do; 
                                describe by category otherwise)
                                \n\nUser question: {user_input}"""}],
                            options={
                                # how creative the model can get -> 0.0 is static, 1.0 is unpredictable
                                "temperature": 0.7,
                                # maximum number of tokens the model can generate in one response
                                "num_predict": 8192,
                                # context window size, exceeding this causes the model to forget prior info
                                "num_ctx": 8192
                            },
                            stream=False)

    initial_text = initial_response.message.content
    logging.debug(f"LLM initial response: {initial_text}")

    for token in review_and_rewrite(user_input, initial_text, EXERCISE_REVIEW_PROMPT, retrieved):
        response_content += token
        yield token

    logging.debug(f"Final response: {response_content}")
    Memory.chat_history += [
        {"role": "user", "content": user_input},
        # adds the user query and subsequent LLM response to the chat history
        {"role": "assistant", "content": response_content}
    ]

    if Memory.last_exercises:
        yield f"EXERCISES:{','.join(Memory.last_exercises)}"
