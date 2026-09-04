"""
This is the brain of the app,
connecting backend with frontend.
"""
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import logging
import os
import tempfile
from pipelines import run_chat_pipeline, run_video_pipeline
from vision import analyse_image, analyse_video
from retrieval import list_exercises, get_user_plan, cur, db_lock

app = FastAPI()

# these are the allowed addresses, if this is not done the app does not behave
# a.k.a. it just does not load
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    """defines the contents of the JSON body FastAPI expects when it receives a POST request"""
    content: str
    image_path: str | None = None
    file_type: str | None = None
    video_choice: str | None = None
    user_id: int = 1


logging.basicConfig(
    filename="refit.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(funcName)s -%(message)s"
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@app.post("/chat")
async def chat_endpoint(message: Message):
    """checks file type, if image it analyses it and sends a response to frontend,
        if video, creates a summary that will be fed to the pipeline
        else simply runs the pipeline."""
    if message.video_choice:
        # if a video choice is made, returns the chosen exercise
        return StreamingResponse(run_video_pipeline(message.content,
                                                    None, video_choice=message.video_choice), media_type="text/plain")

    if message.image_path:
        if message.file_type == "video":
            # returns a summary of the video to be fed to LLM
            video_summary = analyse_video(message.image_path)
            return StreamingResponse(run_video_pipeline(message.content, video_summary), media_type="text/plain")

        # if it is not a video, the image gets analysed and the response streamed
        return StreamingResponse(analyse_image(message.image_path, message.content), media_type="text/plain")

    # if no media is present, regular chat pipeline runs
    return StreamingResponse(run_chat_pipeline(message.content, message.user_id), media_type="text/plain")


@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    """uploads uploaded file to pipeline"""
    contents = await file.read()
    temp_path = os.path.join(tempfile.gettempdir(), f"temp_{file.filename}")
    with open(temp_path, "wb") as f:
        f.write(contents)

    return {"file_path": temp_path}


@app.get("/exercises")
def exercises_endpoint():
    """returns all exercises as JSON for the Exercises page"""
    return list_exercises()


@app.get("/plan")
def plan_endpoint(user_id: int = 1):
    """returns the given user's workout plan as JSON for the Plans page.
    null until that user has completed the plan flow in chat."""
    return get_user_plan(user_id)


@app.get("/users")
def users_endpoint():
    """returns all seeded test users as [{user_id, full_name}, ...], for the
    frontend's dev-only user switcher."""
    with db_lock:
        cur.execute('SELECT user_id, full_name FROM "user" ORDER BY user_id')
        return [{"user_id": uid, "full_name": name} for uid, name in cur.fetchall()]
