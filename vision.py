"""
This module is responsible for the image/vision
recognition aspect of the app.
It gives feedback on physiques, form analysis,
and advice based on local LLMs.
"""
from ollama import chat
import mediapipe as mp
import cv2
import os
from memory import Memory
from prompts_and_schemas import VISION_PROMPT
import logging

MAX_EDGE = 1024  # ~1,300 vision tokens worst case for qwen2.5vl


def _load_downscaled(image_path):
    """Re-encodes the image with its long edge capped, so the
    vision token count stays bounded regardless of upload size."""
    img = cv2.imread(image_path)
    if img is None:  # format cv2 can't decode — send the original bytes
        with open(image_path, "rb") as f:
            return f.read()

    h, w = img.shape[:2]
    scale = MAX_EDGE / max(h, w)
    if scale >= 1:  # already small enough
        with open(image_path, "rb") as f:
            return f.read()

    img = cv2.resize(img, (int(w * scale), int(h * scale)),
                     interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def analyse_image(image_path, user_input):
    """Takes uploaded images and gives feedback based on user query"""

    image_data = _load_downscaled(image_path)

    logging.debug("=" * 100)
    logging.debug(f"User's message: {user_input}")

    response_content = ""
    yield "Analysing..."
    response = chat("qwen2.5vl:7b", messages=[
        {"role": "system", "content": VISION_PROMPT},
        {"role": "user",
         "content": user_input,
         "images": [image_data]}
    ], options={
        "temperature": 0.5,
        "num_predict": 4096,
        "num_ctx": 8192
    }, stream=True)

    for chunk in response:
        token = chunk.message.content
        response_content += token
        yield token

    logging.debug(f"Image analysis response: {response_content}")

    os.remove(image_path)  # deletes the temp file

    Memory.chat_history += [
        {"role": "user", "content": user_input},
        # adds the user query and subsequent LLM response to the chat history
        {"role": "assistant", "content": response_content}
    ]


def analyse_video(video):
    """Takes video input, extracts every 30th frame,
    feeds it into mediapipe for joint position analysis,
    returns the final coordinates as a string to be fed
    to the local LLMs."""
    cap = cv2.VideoCapture(video)
    frame_count = 0
    frames = []  # list of total frames to be analysed from video

    while cap.isOpened():
        ret, frame = cap.read()  # ret is True if frame was read successfully
        if not ret:
            break

        if frame_count % 30 == 0:
            frames.append(frame)

        frame_count += 1

    cap.release()  # discards video from memory once extraction is finished

    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose()

    all_frames = []

    for frame in frames:
        # cv2 is BGR, mp only accepts RGB, so frames need to be converted
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame)
        if results.pose_landmarks:
            # each landmark has x, y, z coordinates which will be saved
            landmarks = results.pose_landmarks.landmark
            # the position for each bodypart will be saved against each frame in the dict below
            frame_data = {
                "left_shoulder": landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER],
                "right_shoulder": landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER],
                "left_elbow": landmarks[mp_pose.PoseLandmark.LEFT_ELBOW],
                "right_elbow": landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW],
                "left_wrist": landmarks[mp_pose.PoseLandmark.LEFT_WRIST],
                "right_wrist": landmarks[mp_pose.PoseLandmark.RIGHT_WRIST],
                "left_hip": landmarks[mp_pose.PoseLandmark.LEFT_HIP],
                "right_hip": landmarks[mp_pose.PoseLandmark.RIGHT_HIP],
                "left_knee": landmarks[mp_pose.PoseLandmark.LEFT_KNEE],
                "right_knee": landmarks[mp_pose.PoseLandmark.RIGHT_KNEE],
                "left_ankle": landmarks[mp_pose.PoseLandmark.LEFT_ANKLE],
                "right_ankle": landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE],
                "left_heel": landmarks[mp_pose.PoseLandmark.LEFT_HEEL],
                "right_heel": landmarks[mp_pose.PoseLandmark.RIGHT_HEEL],
                "left_foot_index": landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX],
                "right_foot_index": landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX]
            }
            # saves a dictionary for each frame extracted with all of the above coordinates
            all_frames.append(frame_data)

    summary = ""
    for i, frame in enumerate(all_frames):
        summary += f"Frame {i}:\n"
        for joint, landmark in frame.items():
            summary += f" {joint}: x={landmark.x:.2f}, y={landmark.y:.2f}, visibility = {landmark.visibility:.2f}\n"

    os.remove(video)

    logging.debug(f"Coordinates gathered: {summary}")

    return summary
