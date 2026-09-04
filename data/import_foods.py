"""
Imports the CoFID 2021 nutrition dataset  from the source Excel file into the 'foods' table.
"""

import getpass
import os

import numpy as np
import pandas as pd
import psycopg2

PATH = os.environ.get("COFID_XLSX",
                "data/McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021.xlsx")

# Column positions in the '1.3 Proximates' sheet (0-indexed).
POS = {
    "food_code": 0, "food_name": 1, "description": 2, "food_group": 3,
    "kcal": 12, "protein_g": 9, "fat_g": 10, "carb_g": 11,
    "total_sugars_g": 16, "fibre_nsp_g": 24, "fibre_aoac_g": 25,
}
NUMERIC = ["kcal", "protein_g", "fat_g", "carb_g",
           "total_sugars_g", "fibre_nsp_g", "fibre_aoac_g"]


def to_num(series):
    """Resolve CoFID sentinels then coerce to numbers: Tr -> 0, N/blank -> NaN."""
    return pd.to_numeric(series.replace({"Tr": 0, "N": np.nan}), errors="coerce")


if not os.path.exists(PATH):
    raise SystemExit(
        f"CoFID spreadsheet not found at {PATH}.\n"
        "Download it from https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid\n"
        "and set COFID_XLSX to its path.")

# Read the proximates sheet (3-row header -> skiprows=3).
raw = pd.read_excel(PATH, sheet_name="1.3 Proximates", skiprows=3, header=None)

out = pd.DataFrame({
    "food_code": raw[POS["food_code"]].astype(str).str.strip(),
    "food_name": raw[POS["food_name"]].astype(str).str.strip(),
    "description": raw[POS["description"]].astype(str).str.strip(),
    "food_group": raw[POS["food_group"]].astype(str).str.strip(),
})
for col in NUMERIC:
    out[col] = to_num(raw[POS[col]])

# Drop any rows without a food code.
out = out[out["food_code"].str.len() > 0]


def nan_to_none(v):
    # NaN must become SQL NULL; a 'real' column would otherwise store IEEE NaN.
    # (Converting per-column via the DataFrame re-coerces None back to NaN, so
    # this has to happen at tuple-build time.)
    return None if (isinstance(v, float) and pd.isna(v)) else v


conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

# Reset the table so re-running is idempotent. The surrogate `id` PK means
# CoFID's duplicate food_code (13-669) no longer drops a row on import.
cur.execute("TRUNCATE foods RESTART IDENTITY")

records = [tuple(nan_to_none(v) for v in row)
           for row in out.itertuples(index=False, name=None)]
cur.executemany(
    """
    INSERT INTO foods (food_code, food_name, description, food_group,
                       kcal, protein_g, fat_g, carb_g,
                       total_sugars_g, fibre_nsp_g, fibre_aoac_g)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """,
    records,
)

conn.commit()
print(f"Foods imported: {cur.rowcount} rows affected ({len(records)} read).")
cur.close()
conn.close()
print("Done.")
