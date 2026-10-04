# ============================================================
# DIM DATE LOADER
# Populates marts.dim_date for 2019-01-01 to 2026-12-31
# Author: Clementina Chukwu | Datara.Insight
# ============================================================

import psycopg2
from datetime import datetime, date, timedelta
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv()

MONTH_NAMES = {
    1:"January",2:"February",3:"March",4:"April",
    5:"May",6:"June",7:"July",8:"August",
    9:"September",10:"October",11:"November",12:"December"
}
DAY_NAMES = {
    0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",
    4:"Friday",5:"Saturday",6:"Sunday"
}

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def run():
    print("=" * 60)
    print("DIM DATE LOADER")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    # Must clear fact tables first — they reference dim_date via foreign key
    print("\n[1/2] Clearing fact tables and dim_date...")
    cursor.execute("DELETE FROM marts.fact_exchange_rates")
    cursor.execute("DELETE FROM marts.fact_inflation")
    cursor.execute("DELETE FROM marts.dim_date")
    conn.commit()
    print("      ✅ Tables cleared")

    start   = date(2019, 1, 1)
    end     = date(2026, 12, 31)
    current = start
    loaded  = 0

    print(f"[2/2] Loading dates: {start} → {end}")

    while current <= end:
        dow         = current.weekday()
        is_weekend  = dow >= 5
        is_business = not is_weekend
        quarter     = (current.month - 1) // 3 + 1
        quarter_lbl = f"Q{quarter} {current.year}"

        cursor.execute("""
            INSERT INTO marts.dim_date
                (full_date, year, month, month_name, quarter,
                 quarter_label, day_of_week, day_name,
                 is_business_day, is_weekend)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (full_date) DO NOTHING
        """, (
            current, current.year, current.month,
            MONTH_NAMES[current.month], quarter, quarter_lbl,
            dow, DAY_NAMES[dow], is_business, is_weekend
        ))
        loaded += 1
        current += timedelta(days=1)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM marts.dim_date")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.dim_date WHERE is_business_day")
    biz = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✅ dim_date loaded!")
    print(f"   Total days    : {total}")
    print(f"   Business days : {biz}")
    print(f"   Weekend days  : {total - biz}")
    print("=" * 60)
    return loaded

if __name__ == "__main__":
    run()