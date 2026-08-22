import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL_PATH = os.path.join(BASE_DIR, "data", "AROL_Q2_synthetic_fleet_dataset.xlsx")
DB_PATH = os.path.join(BASE_DIR, "data", "arol_fleet.db")

def create_sqlite_db():
    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR, Dataset not found in {EXCEL_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    excel_file = pd.ExcelFile(EXCEL_PATH)

    for sheet_name in excel_file.sheet_names:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
        df.to_sql(sheet_name, conn, if_exists="replace", index=False)

    conn.close()

if __name__ == "__main__":
    create_sqlite_db()