import getpass
import os
import psycopg2
import ollama

conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

# Fetch all exercises without embeddings
cur.execute(
    "SELECT exercise_id, exercise_name, description FROM exercises WHERE embedding IS NULL")
exercises = cur.fetchall()

for exercise_id, exercise_name, description in exercises:
    # nomic-embed-text is asymmetric: documents need the search_document: prefix
    # (queries use search_query:), otherwise retrieval quality drops noticeably.
    text = f"search_document: {exercise_name}. {description}"
    response = ollama.embed(model="nomic-embed-text", input=text)
    embedding = response.embeddings[0]

    cur.execute(
        "UPDATE exercises SET embedding = %s WHERE exercise_id = %s",
        (embedding, exercise_id)
    )
    print(f"Embedded: {exercise_name}")

conn.commit()
cur.close()
conn.close()
print("Done.")
