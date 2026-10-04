import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

def run_schema():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cursor = conn.cursor()

    with open("sql/schema.sql", "r") as f:
        sql = f.read()

    try:
        cursor.execute(sql)
        print("✅ Schema created successfully!")
        print("   Tables created:")
        cursor.execute("""
            SELECT schemaname, tablename 
            FROM pg_tables 
            WHERE schemaname IN ('raw', 'staging', 'marts', 'public')
            AND tablename NOT IN ('pipeline_runs', 'pipeline_assertions')
            OR tablename IN ('pipeline_runs', 'pipeline_assertions')
            ORDER BY schemaname, tablename
        """)
        for row in cursor.fetchall():
            print(f"   → {row[0]}.{row[1]}")
    except Exception as e:
        print(f"❌ Schema creation failed: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_schema()