"""
Loads UK dietary guideline values into the `nutrient_reference` table.

Source: Public Health England, "Government Dietary Recommendations:
Government recommendations for energy and nutrients for males and females aged
1-18 years and 19+ years" (August 2016), Tables 1 and 2 (macronutrients).
https://www.gov.uk/government/publications/the-eatwell-guide
"""

import getpass
import os

import psycopg2

# Age bands as (age_min, age_max); 200 stands in for the open-ended 75+ band.
BANDS = [(1, 1), (2, 3), (4, 6), (7, 10), (11, 14), (15, 18),
         (19, 64), (65, 74), (75, 200)]

# nutrient -> (limit_type, [(male, female) per band, or None for "no recommendation"])
DATA = {
    "energy_kcal":   ("target", [(765, 717), (1088, 1004), (1482, 1378), (1817, 1703),
                                 (2500, 2000), (2500, 2000), (2500, 2000), (2342, 1912), (2294, 1840)]),
    "protein_g":     ("min",    [(14.5, 14.5), (14.5, 14.5), (19.7, 19.7), (28.3, 28.3),
                                 (42.1, 41.2), (55.2, 45.0), (55.5, 45.0), (53.3, 46.5), (53.3, 46.5)]),
    "fat_g":         ("max",    [None, None, (58, 54), (71, 66),
                                 (97, 78), (97, 78), (97, 78), (91, 74), (89, 72)]),
    "satfat_g":      ("max",    [None, None, (18, 17), (22, 21),
                                 (31, 24), (31, 24), (31, 24), (29, 23), (28, 23)]),
    "carb_g":        ("min",    [None, (145, 134), (198, 184), (242, 227),
                                 (333, 267), (333, 267), (333, 267), (312, 255), (306, 245)]),
    "free_sugars_g": ("max",    [None, (15, 13), (20, 18), (24, 23),
                                 (33, 27), (33, 27), (33, 27), (31, 26), (31, 25)]),
    "fibre_g":       ("target", [None, (15, 15), (20, 20), (20, 20),
                                 (25, 25), (30, 30), (30, 30), (30, 30), (30, 30)]),
}

rows = []
for nutrient, (limit_type, per_band) in DATA.items():
    for (age_min, age_max), mf in zip(BANDS, per_band):
        if mf is None:  # dash in the source: no recommendation for this age
            continue
        male, female = mf
        rows.append(("M", age_min, age_max, nutrient, float(male), limit_type))
        rows.append(("F", age_min, age_max, nutrient,
                    float(female), limit_type))

conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

cur.execute("TRUNCATE nutrient_reference RESTART IDENTITY")
cur.executemany(
    """
    INSERT INTO nutrient_reference (sex, age_min, age_max, nutrient, value, limit_type)
    VALUES (%s, %s, %s, %s, %s, %s)
    """,
    rows,
)

conn.commit()
print(f"Nutrient reference loaded: {cur.rowcount} rows.")
cur.close()
conn.close()
print("Done.")
