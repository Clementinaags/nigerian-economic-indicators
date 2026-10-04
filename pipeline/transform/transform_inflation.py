# ============================================================
# INFLATION TRANSFORM — raw → staging
# Cleans, types and validates NBS inflation data
# Author: Clementina Chukwu | Datara.Insight
# ============================================================

import psycopg2
from datetime import datetime, date
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv()

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}


def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def clean_numeric(value):
    if value is None:
        return None
    try:
        return round(float(str(value).strip().replace(",", "")), 4)
    except (ValueError, TypeError):
        return None


def validate_inflation(headline, food, core, mom, year, month):
    notes = []

    if headline is None:
        notes.append("NULL HEADLINE INFLATION")
        return False, " | ".join(notes)

    if headline <= 0 or headline > 100:
        notes.append(f"HEADLINE OUT OF RANGE: {headline}")
        return False, " | ".join(notes)

    if food and food <= 0:
        notes.append(f"FOOD INFLATION NEGATIVE: {food}")

    if core and core <= 0:
        notes.append(f"CORE INFLATION NEGATIVE: {core}")

    if food and headline and food < headline - 20:
        notes.append(f"FOOD MUCH LOWER THAN HEADLINE: {food} vs {headline}")

    if mom and abs(mom) > 5:
        notes.append(f"LARGE MOM CHANGE: {mom}% — verify")

    if not notes:
        notes.append("ALL CHECKS PASSED")

    return True, " | ".join(notes)


def run():
    print("=" * 60)
    print("INFLATION TRANSFORM — raw → staging")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    # Clear staging
    cursor.execute("DELETE FROM staging.stg_inflation")
    conn.commit()
    print(f"\n[1/3] Staging table cleared")

    # Fetch raw inflation records
    cursor.execute("""
        SELECT id, report_year, report_month,
               headline_inflation, food_inflation, core_inflation,
               mom_change, yoy_change, extraction_notes
        FROM raw.raw_nbs_inflation
        ORDER BY report_year, report_month
    """)
    raw_records = cursor.fetchall()
    print(f"[2/3] Fetched {len(raw_records)} raw records")

    loaded = 0
    warnings = 0

    print(f"[3/3] Transforming and loading to staging...")

    for row in raw_records:
        _, year, month, headline_raw, food_raw, core_raw, \
            mom_raw, yoy_raw, extraction_notes = row

        # Clean and type
        headline = clean_numeric(headline_raw)
        food     = clean_numeric(food_raw)
        core     = clean_numeric(core_raw)
        mom      = clean_numeric(mom_raw)
        yoy      = clean_numeric(yoy_raw)

        # Build report date — first day of the month
        report_date = date(year, month, 1)
        month_name  = MONTH_NAMES.get(month, "Unknown")

        # Determine rebase period from extraction notes
        rebase = "pre_2024"
        if extraction_notes and "post_2024" in extraction_notes:
            rebase = "post_2024"

        # Validate
        is_valid, validation_notes = validate_inflation(
            headline, food, core, mom, year, month
        )

        if "verify" in validation_notes.lower():
            warnings += 1

        cursor.execute("""
            INSERT INTO staging.stg_inflation
                (report_date, report_year, report_month, report_month_name,
                 headline_inflation, food_inflation, core_inflation,
                 mom_change, yoy_change, rebase_period,
                 is_valid, validation_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            report_date, year, month, month_name,
            headline, food, core,
            mom, yoy, rebase,
            is_valid, validation_notes
        ))
        loaded += 1

    conn.commit()

    # Summary
    cursor.execute("""
        SELECT rebase_period, COUNT(*),
               MIN(report_date), MAX(report_date),
               ROUND(AVG(headline_inflation)::numeric, 2)
        FROM staging.stg_inflation
        GROUP BY rebase_period
        ORDER BY rebase_period
    """)
    by_rebase = cursor.fetchall()

    cursor.execute("""
        SELECT report_year, ROUND(AVG(headline_inflation)::numeric, 2)
        FROM staging.stg_inflation
        GROUP BY report_year
        ORDER BY report_year
    """)
    by_year = cursor.fetchall()

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✅ Inflation transform complete!")
    print(f"   Records loaded  : {loaded}")
    print(f"   Warnings        : {warnings}")
    print(f"\n   By rebase period:")
    for rebase, count, min_d, max_d, avg_h in by_rebase:
        print(f"   → {rebase:<12} {count:>3} months  {min_d} → {max_d}  avg: {avg_h}%")
    print(f"\n   Annual average headline inflation:")
    for yr, avg in by_year:
        bar = "█" * int(float(avg) / 2)
        print(f"   → {yr}: {avg:>6}%  {bar}")
    print("=" * 60)

    return loaded


if __name__ == "__main__":
    run()