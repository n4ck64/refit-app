import pandas as pd

df = pd.read_csv(
    '/Users/nikolaytinev/MSC_FINAL_PROJECT/data/Exercises-Exercises.csv')
df['description'] = df['description'].str.replace(
    '\n', ' ').str.replace('\r', ' ').str.strip()
df.to_csv(
    '/Users/nikolaytinev/MSC_FINAL_PROJECT/data/Exercises-Exercises.csv', index=False)
