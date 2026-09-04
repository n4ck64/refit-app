"""
The functions here classify information from text using Llama3.1
"""

from memory import Memory
from prompts_and_schemas import (INTENT_PROMPT, TARGET_MUSCLE_PROMPT,
                                 INJURED_MUSCLE_PROMPT, CONDENSE_PROMPT, MUSCLE_SCHEMA, QUERY_SCHEMA,
                                 INTENT_SCHEMA, CONTINUATION_PROMPT, CONTINUATION_SCHEMA,
                                 CONFIRM_PROMPT, CONFIRM_SCHEMA)
from llm import structured_chat


def classify_intent(user_input):
    """Takes the user's query and classifies it into one of eight
    intent labels (EXERCISE_GENERAL, EXERCISE_INJURY, PLAN_GENERAL,
    PLAN_INJURY, PLAN_EDIT, NUTRITION, NUTRITION_PLAN, CHITCHAT)"""
    history = "\n".join(
        f'{memory["role"]}: {memory["content"]}' for memory in Memory.chat_history[-4:])
    return structured_chat(
        "llama3.1", INTENT_PROMPT,
        f"Previous conversation:\n{history}\n\nMessage to classify: {user_input}",
        INTENT_SCHEMA)["intent"]


def answers_pending_question(question, reply):
    """Gate for the plan-edit clarification loop: True if 'reply' answers the
    outstanding 'question', False if the user moved on to a new request."""
    return structured_chat(
        "llama3.1", CONTINUATION_PROMPT,
        f"Question: {question!r}\nReply: {reply!r}",
        CONTINUATION_SCHEMA)["is_answer"]


def classify_confirmation(question, reply):
    """Gate for actions that WRITE to the user's data: returns 'yes', 'no' or
    'unrelated' for a reply to a confirmation question. Distinct from
    answers_pending_question, which asks whether a reply supplies missing
    information rather than whether it grants permission."""
    return structured_chat(
        "llama3.1", CONFIRM_PROMPT,
        f"Question: {question!r}\nReply: {reply!r}",
        CONFIRM_SCHEMA)["decision"]


def classify_injured_muscle(user_input):
    """Takes user input and if an injury is mentioned, returns the list of injured
    muscle_ids (empty list if none) so it can be passed straight to 
    retrieve_exercises' ANY(%s) filter."""
    return structured_chat("llama3.1", INJURED_MUSCLE_PROMPT, user_input, MUSCLE_SCHEMA)["muscle_ids"]


def classify_target_muscle(query):
    """Returns the muscle_id the user wants to train, 0 if no muscle is mentioned"""
    return structured_chat("llama3.1", TARGET_MUSCLE_PROMPT, query, MUSCLE_SCHEMA)["muscle_ids"]


def condense_query(user_input):
    """Rewrites a follow-up into a standalone query using recent history, so the
    RAG embeds the user's actual intent instead of the previous reply. Returns
    self-contained queries unchanged, and skips the LLM call on the first turn."""
    if not Memory.chat_history:
        return user_input

    history = "\n".join(
        f'{memory["role"]}: {memory["content"]}' for memory in Memory.chat_history[-4:])
    result = structured_chat(
        "llama3.1", CONDENSE_PROMPT,
        f"Conversation:\n{history}\n\nLatest message: {user_input}",
        QUERY_SCHEMA)

    return result["query"].strip() or user_input
