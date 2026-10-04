# ============================================================
# FX TRANSFORM — raw → staging
# Cleans, types and validates exchange rate data
# Author: Clementina Chukwu | Datara.Insight
# ============================================================

import psycopg2
from datetime import datetime, date
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv()

CURRENCY_CODE_MAP = {
    "US DOLLAR":         "USD",
    "POUNDS STERLING":   "GBP",
    "EURO":              "EUR",
    "YUAN/RENMINBI":     "CNY",
    "YEN":               "JPY",
    "SWISS FRANC":       "CHF",
    "RIYAL":             "SAR",
    "SOUTH AFRICAN RAND":"ZAR",
    "DANISH KRONA":      "DKK",
    "CFA":               "CFA",
}


def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def clean_rate(value):
    if value is None:
        return None
    try:
        return round(float(str(value).strip().replace(",", "")), 4)
    except (ValueError, TypeError):
        return None


def parse_date(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()
    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%m/%d/%Y"]:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def validate_record(rate_date, buying, central, selling):
    """
    Run validation rules on a single rate record.
    Returns (is_valid, notes)
    """
    notes = []
    is_valid = True

    if not rate_date:
        notes.append("INVALID DATE")
        return False, " | ".join(notes)

    if rate_date.year < 2019 or rate_date.year > 2026:
        notes.append(f"DATE OUT OF RANGE: {rate_date}")
        is_valid = False

    if buying is None or central is None or selling is None:
        notes.append("NULL RATE VALUE")
        is_valid = False
        return is_valid, " | ".join(notes)

    if buying <= 0 or central <= 0 or selling <= 0:
        notes.append("NON-POSITIVE RATE")
        is_valid = False

    if buying > selling:
        notes.append(f"BUYING > SELLING: {buying} > {selling}")
        is_valid = False

    if not (buying <= central <= selling):
        notes.append(f"CENTRAL NOT BETWEEN BUYING/SELLING: {buying}/{central}/{selling}")
        # Warn but keep — FRED annual averages may not have exact spread
        notes.append("WARNING ONLY — kept")

    spread = selling - buying
    if spread > 50:
        notes.append(f"LARGE SPREAD: {spread}")

    if not notes:
        notes.append("ALL CHECKS PASSED")

    return is_valid, " | ".join(notes)


def run():
    print("=" * 60)
    print("FX TRANSFORM — raw → staging")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    # Clear staging first
    cursor.execute("DELETE FROM staging.stg_exchange_rates")
    conn.commit()
    print(f"\n[1/3] Staging table cleared")

    # Fetch all raw FX records
    cursor.execute("""
        SELECT id, rate_date, currency, buying_rate,
               central_rate, selling_rate, source_url
        FROM raw.raw_cbn_exchange_rates
        ORDER BY rate_date, currency
    """)
    raw_records = cursor.fetchall()
    print(f"[2/3] Fetched {len(raw_records)} raw records")

    loaded = 0
    skipped = 0
    warnings = 0

    print(f"[3/3] Transforming and loading to staging...")

    for row in raw_records:
        _, rate_date_raw, currency_raw, buying_raw, \
            central_raw, selling_raw, source_url = row

        # Parse and clean
        rate_date = parse_date(rate_date_raw)
        buying    = clean_rate(buying_raw)
        central   = clean_rate(central_raw)
        selling   = clean_rate(selling_raw)

        # Map currency name to code
        currency_name = currency_raw.upper().strip()
        currency_code = CURRENCY_CODE_MAP.get(currency_name, "UNK")

        if currency_code == "UNK":
            skipped += 1
            continue

        # Calculate spread
        spread = round(selling - buying, 4) if selling and buying else None

        # Validate
        is_valid, validation_notes = validate_record(
            rate_date, buying, central, selling
        )

        if "WARNING" in validation_notes:
            warnings += 1

        # Insert into staging
        cursor.execute("""
            INSERT INTO staging.stg_exchange_rates
                (rate_date, currency_code, currency_name,
                 buying_rate, central_rate, selling_rate,
                 spread, is_valid, validation_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            rate_date, currency_code, currency_name,
            buying, central, selling,
            spread, is_valid, validation_notes
        ))
        loaded += 1

    conn.commit()

    # Summary
    cursor.execute("SELECT COUNT(*) FROM staging.stg_exchange_rates")
    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM staging.stg_exchange_rates
        WHERE is_valid = TRUE
    """)
    valid_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT currency_code, COUNT(*), MIN(rate_date), MAX(rate_date)
        FROM staging.stg_exchange_rates
        GROUP BY currency_code
        ORDER BY currency_code
    """)
    by_currency = cursor.fetchall()

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✅ FX transform complete!")
    print(f"   Raw records processed : {len(raw_records)}")
    print(f"   Loaded to staging     : {loaded}")
    print(f"   Skipped (unknown curr): {skipped}")
    print(f"   Valid records         : {valid_count}")
    print(f"   Warnings              : {warnings}")
    print(f"\n   By currency:")
    for code, count, min_date, max_date in by_currency:
        print(f"   → {code:<6} {count:>4} records  {min_date} → {max_date}")
    print("=" * 60)

    return loaded


if __name__ == "__main__":
    run()