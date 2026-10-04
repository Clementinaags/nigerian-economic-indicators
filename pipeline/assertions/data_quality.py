# ============================================================
# DATA QUALITY ASSERTIONS
# 11 checks across raw → staging → marts
# Author: Clementina Chukwu | Datara.Insight
# ============================================================

import psycopg2
from datetime import datetime
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from dotenv import load_dotenv
load_dotenv()

def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

def log_assertion(cursor, run_id, name, layer,
                  scope, rows_checked, rows_failed, status, message):
    cursor.execute("""
        INSERT INTO public.pipeline_assertions
            (run_id, assertion_name, layer, scope,
             rows_checked, rows_failed, status, message)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (run_id, name, layer, scope,
          rows_checked, rows_failed, status, message))


def run_assertions(run_id):
    print("=" * 60)
    print("DATA QUALITY ASSERTIONS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    conn   = get_connection()
    cursor = conn.cursor()

    results = []

    # ── ASSERTION 1 ─────────────────────────────────────────
    # No null values in headline inflation
    name = "No null headline inflation"
    cursor.execute("""
        SELECT COUNT(*) FROM staging.stg_inflation
        WHERE headline_inflation IS NULL
    """)
    nulls = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM staging.stg_inflation")
    total = cursor.fetchone()[0]
    status  = "PASS" if nulls == 0 else "FAIL"
    message = (f"All {total} records have headline inflation"
               if nulls == 0
               else f"{nulls} records missing headline inflation")
    log_assertion(cursor, run_id, name, "staging", "stg_inflation",
                  total, nulls, status, message)
    results.append((name, status, message))

    # ── ASSERTION 2 ─────────────────────────────────────────
    # Buying rate always less than or equal to selling rate
    name = "Buying rate ≤ selling rate"
    cursor.execute("""
        SELECT COUNT(*) FROM staging.stg_exchange_rates
        WHERE buying_rate > selling_rate
    """)
    fails = cursor.fetchone()[0]
    cursor.execute("""
        SELECT COUNT(*) FROM staging.stg_exchange_rates
        WHERE buying_rate IS NOT NULL
    """)
    total = cursor.fetchone()[0]
    status  = "PASS" if fails == 0 else "FAIL"
    message = (f"All {total} records have buying ≤ selling"
               if fails == 0
               else f"{fails} records where buying > selling")
    log_assertion(cursor, run_id, name, "staging", "stg_exchange_rates",
                  total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 3 ─────────────────────────────────────────
    # All exchange rates are positive
    name = "All exchange rates positive"
    cursor.execute("""
        SELECT COUNT(*) FROM staging.stg_exchange_rates
        WHERE buying_rate <= 0
           OR central_rate <= 0
           OR selling_rate <= 0
    """)
    fails = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM staging.stg_exchange_rates")
    total = cursor.fetchone()[0]
    status  = "PASS" if fails == 0 else "FAIL"
    message = (f"All {total} rate records are positive"
               if fails == 0
               else f"{fails} non-positive rate records found")
    log_assertion(cursor, run_id, name, "staging", "stg_exchange_rates",
                  total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 4 ─────────────────────────────────────────
    # No duplicate date + currency in fact_exchange_rates
    name = "No duplicate date+currency in fact_exchange_rates"
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT date_id, currency_id, COUNT(*)
            FROM marts.fact_exchange_rates
            GROUP BY date_id, currency_id
            HAVING COUNT(*) > 1
        ) dupes
    """)
    dupes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.fact_exchange_rates")
    total = cursor.fetchone()[0]
    status  = "PASS" if dupes == 0 else "FAIL"
    message = (f"No duplicates across {total} FX records"
               if dupes == 0
               else f"{dupes} duplicate date+currency combinations")
    log_assertion(cursor, run_id, name, "marts",
                  "fact_exchange_rates", total, dupes, status, message)
    results.append((name, status, message))

    # ── ASSERTION 5 ─────────────────────────────────────────
    # No duplicate months in fact_inflation
    name = "No duplicate months in fact_inflation"
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT date_id, COUNT(*)
            FROM marts.fact_inflation
            GROUP BY date_id
            HAVING COUNT(*) > 1
        ) dupes
    """)
    dupes = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.fact_inflation")
    total = cursor.fetchone()[0]
    status  = "PASS" if dupes == 0 else "FAIL"
    message = (f"No duplicate months across {total} inflation records"
               if dupes == 0
               else f"{dupes} duplicate month records found")
    log_assertion(cursor, run_id, name, "marts",
                  "fact_inflation", total, dupes, status, message)
    results.append((name, status, message))

    # ── ASSERTION 6 ─────────────────────────────────────────
    # Inflation values in realistic range (5% to 80%)
    name = "Headline inflation in realistic range (5-80%)"
    cursor.execute("""
        SELECT COUNT(*) FROM marts.fact_inflation
        WHERE headline_inflation < 5
           OR headline_inflation > 80
    """)
    fails = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.fact_inflation")
    total = cursor.fetchone()[0]
    status  = "PASS" if fails == 0 else "FAIL"
    message = (f"All {total} inflation records within 5-80% range"
               if fails == 0
               else f"{fails} records outside realistic range")
    log_assertion(cursor, run_id, name, "marts", "fact_inflation",
                  total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 7 ─────────────────────────────────────────
    # USD rate devaluation trend — 2019 rate < 2024 rate
    name = "USD/NGN devaluation confirmed (2019 < 2024)"
    cursor.execute("""
        SELECT
            MIN(CASE WHEN d.year = 2019 THEN f.central_rate END),
            MAX(CASE WHEN d.year = 2024 THEN f.central_rate END)
        FROM marts.fact_exchange_rates f
        JOIN marts.dim_date d     ON d.date_id     = f.date_id
        JOIN marts.dim_currency c ON c.currency_id = f.currency_id
        WHERE c.currency_code = 'USD'
    """)
    row = cursor.fetchone()
    rate_2019, rate_2024 = row if row else (None, None)
    total = 1
    if rate_2019 and rate_2024 and rate_2019 < rate_2024:
        status  = "PASS"
        devaluation = round(
            ((rate_2024 - rate_2019) / rate_2019) * 100, 1)
        message = (f"Confirmed: ₦{rate_2019:.2f} (2019) → "
                   f"₦{rate_2024:.2f} (2024) "
                   f"= {devaluation}% devaluation")
        fails = 0
    else:
        status  = "FAIL"
        message = f"Unexpected: 2019={rate_2019}, 2024={rate_2024}"
        fails = 1
    log_assertion(cursor, run_id, name, "marts",
                  "fact_exchange_rates", total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 8 ─────────────────────────────────────────
    # Inflation trend — 2024 peak higher than 2019
    name = "2024 inflation higher than 2019 (trend confirmed)"
    cursor.execute("""
        SELECT
            AVG(CASE WHEN d.year = 2019 THEN f.headline_inflation END),
            AVG(CASE WHEN d.year = 2024 THEN f.headline_inflation END)
        FROM marts.fact_inflation f
        JOIN marts.dim_date d ON d.date_id = f.date_id
    """)
    row = cursor.fetchone()
    avg_2019, avg_2024 = row if row else (None, None)
    total = 1
    if avg_2019 and avg_2024 and avg_2024 > avg_2019:
        status  = "PASS"
        message = (f"Confirmed: {avg_2019:.2f}% avg (2019) → "
                   f"{avg_2024:.2f}% avg (2024)")
        fails = 0
    else:
        status  = "FAIL"
        message = f"Unexpected: 2019={avg_2019}, 2024={avg_2024}"
        fails = 1
    log_assertion(cursor, run_id, name, "marts",
                  "fact_inflation", total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 9 ─────────────────────────────────────────
    # Row count — raw inflation must equal staging
    name = "Raw inflation row count = staging row count"
    cursor.execute("SELECT COUNT(*) FROM raw.raw_nbs_inflation")
    raw_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM staging.stg_inflation")
    stg_count = cursor.fetchone()[0]
    total  = raw_count
    fails  = abs(raw_count - stg_count)
    status = "PASS" if fails == 0 else "FAIL"
    message = (f"Raw ({raw_count}) = Staging ({stg_count})"
               if fails == 0
               else f"Mismatch: raw={raw_count}, staging={stg_count}")
    log_assertion(cursor, run_id, name, "staging",
                  "stg_inflation vs raw", total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 10 ─────────────────────────────────────────
    # All fact records have a valid dim_date join
    name = "All fact_exchange_rates have valid dim_date"
    cursor.execute("""
        SELECT COUNT(*) FROM marts.fact_exchange_rates f
        LEFT JOIN marts.dim_date d ON d.date_id = f.date_id
        WHERE d.date_id IS NULL
    """)
    fails = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.fact_exchange_rates")
    total = cursor.fetchone()[0]
    status  = "PASS" if fails == 0 else "FAIL"
    message = (f"All {total} FX records have valid date dimension"
               if fails == 0
               else f"{fails} FX records missing date dimension")
    log_assertion(cursor, run_id, name, "marts",
                  "fact_exchange_rates", total, fails, status, message)
    results.append((name, status, message))

    # ── ASSERTION 11 ─────────────────────────────────────────
    # Rebase flag present on all inflation records
    name = "All inflation records have rebase flag"
    cursor.execute("""
        SELECT COUNT(*) FROM marts.fact_inflation
        WHERE rebase_period IS NULL
           OR rebase_period NOT IN ('pre_2024', 'post_2024')
    """)
    fails = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM marts.fact_inflation")
    total = cursor.fetchone()[0]
    status  = "PASS" if fails == 0 else "FAIL"
    message = (f"All {total} records correctly flagged pre/post rebase"
               if fails == 0
               else f"{fails} records missing or invalid rebase flag")
    log_assertion(cursor, run_id, name, "marts",
                  "fact_inflation", total, fails, status, message)
    results.append((name, status, message))

    conn.commit()

    # ── RESULTS SUMMARY ──────────────────────────────────────
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")

    print(f"\n{'─' * 60}")
    for i, (name, status, message) in enumerate(results, 1):
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} [{i:02d}] {name}")
        print(f"        {message}")
    print(f"{'─' * 60}")
    print(f"\n  {passed}/{len(results)} assertions passed")

    if failed == 0:
        print(f"\n  ✅ ALL {passed} ASSERTIONS PASSED")
    else:
        print(f"\n  ❌ {failed} ASSERTION(S) FAILED — review above")

    cursor.close()
    conn.close()

    print("=" * 60)
    return passed, failed


def run():
    start = datetime.now()
    conn  = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO public.pipeline_runs
            (pipeline_name, status, rows_extracted,
             rows_loaded, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, ("data_quality_assertions", "running", 0, 0, 0))
    run_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    passed, failed = run_assertions(run_id)

    duration = (datetime.now() - start).total_seconds()
    status   = "success" if failed == 0 else "failed"

    conn   = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE public.pipeline_runs
        SET status = %s, duration_seconds = %s
        WHERE id = %s
    """, (status, duration, run_id))
    conn.commit()
    cursor.close()
    conn.close()

    return passed, failed


if __name__ == "__main__":
    run()