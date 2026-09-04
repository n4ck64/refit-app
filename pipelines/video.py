from ollama import chat
from retrieval import retrieve_exercise_names, retrieve_exercise_description
from memory import Memory
import logging


def run_video_pipeline(user_input, video_summary=None, video_choice=None):
    """runs only when video is present, it is responsible for
    the back and forth interactions - extracts joint coordinates from video, generates
    a natural language interpretation of them, clarifies with the user what
    exercise is shown, and then runs pipeline based on that."""

    logging.debug("=" * 100)
    logging.debug(f"User's message: {user_input}")

    if video_summary:
        yield "Processing..."
        first_step = chat("llama3.1", messages=[{"role": "system", "content":
                                                 """You are an exercise analyst. 
        Based on the given joint position coordinates and user context
        identify the exercise being performed and describe it in natural language, focusing on:
        - Which muscle groups are being used
        - The movement pattern
        - The body position
        Keep it concise, 2-3 sentences max."""}, {"role": "user", "content":
                                                  f"Coordinates: {video_summary}\nUser context: {user_input}"}],
                          options={
            # low temperature, as higher values are ineffective
            "temperature": 0.0,
            "num_predict": 8192,
            "num_ctx": 8192
        },
            stream=False)
        # saves the extracted summary for future use
        Memory.video_summary = first_step.message.content
        logging.debug(f"Video summary: {Memory.video_summary}")
        # based on the summary, retrieves three exercises
        probable_exercises = retrieve_exercise_names(
            first_step.message.content)
        # these three exercises get stored to memory
        Memory.video_probable_exercises = probable_exercises
        # yields to frontend, "CHOICES:" is a signalling token that lets the frontend
        # know to format the variables as interactive buttons
        # it should not get rendered to the user
        yield f"CHOICES:To confirm, which exercise is shown in the video?|{probable_exercises[0]},{probable_exercises[1]},{probable_exercises[2]}"

    if video_choice:
        # if user indicates that none of the three exercises are correct
        # they can state the exercise in the video manually
        if video_choice == "manual":
            yield "Please type the name of the exercise shown in the video."
            return

        exercise_description = retrieve_exercise_description(user_input)

        if exercise_description is None:
            # if what they type is not in the database, reruns the question
            probable_exercises = Memory.video_probable_exercises
            yield f"CHOICES:That was not recognised, please choose from the list again:|{probable_exercises[0]},{probable_exercises[1]},{probable_exercises[2]}"
            return

        response_content = ""
        yield "Thinking..."
        # based on the user query, the indicated exercise description, and the
        # saved video summary, the model responds
        response = chat("llama3.1", messages=[
            {"role": "system", "content":
             "You are a fitness coach analysing my exercise form. Be specific and direct."},
            {"role": "user", "content": f"""I am performing: {user_input}\n
            Correct form reference: {exercise_description}\n
            What was observed: {Memory.video_summary}\n
            Rate my form and give specific corrections."""}
        ], stream=True)
        for chunk in response:
            token = chunk.message.content
            response_content += token
            yield token

        # once response is generated, video summary gets wiped from memory
        Memory.reset_video()

        logging.debug(f"Video response: {response_content}")

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]
