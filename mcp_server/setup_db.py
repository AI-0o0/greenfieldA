import sqlite3
import os

# create the data base file into db directory
db_path = os.path.join("../db", "farm.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# read and execute the schema
with open("../db/schema.sql", "r") as f:
    cursor.executescript(f.read())

# fill the database with the data
with open("../db/seed.sql", "r") as f:
    cursor.executescript(f.read())

conn.commit()
conn.close()
print("Database built successfully: db/farm.db")