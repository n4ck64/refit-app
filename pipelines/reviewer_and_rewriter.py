from ollama import chat
from prompts_and_schemas import FINAL_PROMPT, REVIEW_SCHEMA
from llm import structured_chat
import logging


def review_and_rewrite(user_input, response, review_prompt, rag_context=None,
                       context_label="Approved exercises"):
    """takes the LLM's initial response, reviews it against a list of criteria,
    and rewrites it to have a conversational and lay register"""

    yield "Reviewing..."

    if rag_context:
        review_input = (f"{context_label}:\n{rag_context}\n\n"
                        f"Original Question: {user_input}\n\nAI Response: {response}")
    else:
        review_input = f"Original Question: {user_input}\n\nAI Response: {response}"

    audit = structured_chat("qwen2.5:7b", review_prompt,
                            review_input, REVIEW_SCHEMA)
    corrected = response if audit["verdict"] == "Safe" else audit["corrected_response"]

    logging.debug(f"Reviewer response: {audit}")

    final_response = chat("llama3.1",
                          messages=[
                              {"role": "system", "content": FINAL_PROMPT},
                              {"role": "user", "content": (
                                  f"Verified Advice:\n{corrected}")}
                          ],
                          options={
                              "temperature": 0.1,
                              "num_predict": 4096,
                              "num_ctx": 8192
                          },
                          stream=True)  # final response will stream as it is being generated

    for chunk in final_response:
        token = chunk.message.content
        yield token
