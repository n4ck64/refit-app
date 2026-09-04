import csv
import getpass
import os
import psycopg2

conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

# Muscles should be imported first, as they are referenced in other tables, such as muscles_exercised
with open('data/Muscles-Muscles.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cur.execute(
            "INSERT INTO muscles (muscle_id, muscle_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (int(row['muscle_id']), row['muscle_name'].strip())
        )
print("Muscles imported.")

# Import exercises
with open('data/Exercises-Exercises.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row['exercise_name'].strip():  # skip blank rows
            continue
        cur.execute(
            # re-running updates the text, so an edited CSV actually reaches the DB
            """INSERT INTO exercises (exercise_id, exercise_name, description, type, difficulty, equipment)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (exercise_id) DO UPDATE SET
                 exercise_name = EXCLUDED.exercise_name,
                 description   = EXCLUDED.description,
                 type          = EXCLUDED.type,
                 difficulty    = EXCLUDED.difficulty,
                 equipment     = EXCLUDED.equipment""",
            (
                int(row['exercise_id']),
                row['exercise_name'].strip(),
                row['description'].strip(),
                row['type'].strip(),
                row['difficulty'].strip(),
                row['equipment'].strip()
            )
        )
print("Exercises imported.")

# Import muscles_exercised last, as it references both muscles and exercises.
# Mappings for exercises that were cut from the corpus are skipped.
cur.execute("SELECT exercise_id FROM exercises")
known_exercises = {row[0] for row in cur.fetchall()}

with open('data/Muscles exercised-Muscles exercised.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if int(row['exercise_id']) not in known_exercises:
            continue
        cur.execute(
            "INSERT INTO muscles_exercised (exercise_id, muscle_id, role) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (
                int(row['exercise_id']),
                int(row['muscle_id']),
                row['role'].strip()
            )
        )
print("Muscles exercised imported.")

conn.commit()
cur.close()
conn.close()
print("Done.")
