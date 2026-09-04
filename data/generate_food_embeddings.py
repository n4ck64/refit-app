"""
Generates embeddings for every food in the 'foods' table using the same
Ollama model as the exercises (nomic-embed-text, 768 dims).
"""

import getpass
import os

import ollama
import psycopg2

conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

cur.execute(
    "SELECT id, food_name, description FROM foods WHERE embedding IS NULL")
foods = cur.fetchall()

for food_id, food_name, description in foods:

    text = f"search_document: {food_name}. {description}"
    response = ollama.embed(model="nomic-embed-text", input=text)
    embedding = response.embeddings[0]

    cur.execute(
        "UPDATE foods SET embedding = %s WHERE id = %s",
        (embedding, food_id)
    )

conn.commit()
cur.close()
conn.close()
print("Done.")
