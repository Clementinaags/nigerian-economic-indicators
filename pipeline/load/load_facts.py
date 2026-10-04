# ============================================================
# FACT TABLE LOADER
# Loads staging → marts.fact_exchange_rates + fact_inflation
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

# ── FACT EXCHANGE RATES ──────────────────────────────────────

def load_fact_exchange_rates(cursor, conn):
    print("\n[FX] Loading fact_exchange_rates...")

    cursor.execute("DELETE FROM marts.fact_exchange_rates")

    # Only load valid records with a matching dim_date
    cursor.execute("""
        INSERT INTO marts.fact_exchange_rates
            (date_id, currency_id, buying_rate, central_rate,
             selling_rate, spread, source)
        SELECT
            d.date_id,
            c.currency_id,
            s.buying_rate,
            s.central_rate,
            s.selling_rate,
            s.spread,
            'CBN/FRED'
        FROM staging.stg_exchange_rates s
        JOIN marts.dim_date d
            ON d.full_date = s.rate_date
        JOIN marts.dim_currency c
            ON c.currency_code = s.currency_code
        WHERE s.is_valid = TRUE
        ON CONFLICT (date_id, currency_id) DO NOTHING
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM marts.fact_exchange_rates")
    count = cursor.fetchone()[0]

    # Show what loaded
    cursor.execute("""
        SELECT c.currency_code, COUNT(*),
               MIN(d.full_date), MAX(d.full_date),
               ROUND(MIN(f.central_rate)::numeric, 2),
               ROUND(MAX(f.central_rate)::numeric, 2)
        FROM marts.fact_exchange_rates f
        JOIN marts.dim_date d     ON d.date_id     = f.date_id
        JOIN marts.dim_currency c ON c.currency_id = f.currency_id
        GROUP BY c.currency_code
        ORDER BY c.currency_code
    """)
    by_curr = cursor.fetchall()

    print(f"   ✅ {count} records loaded to fact_exchange_rates")
    print(f"   By currency:")
    for code, n, min_d, max_d, min_r, max_r in by_curr:
        print(f"   → {code:<5} {n:>3} records  {min_d} → {max_d}"
              f"  range: ₦{min_r:,.2f} – ₦{max_r:,.2f}")
    return count

# ── FACT INFLATION ───────────────────────────────────────────

def load_fact_inflation(cursor, conn):
    print("\n[INF] Loading fact_inflation...")

    cursor.execute("DELETE FROM marts.fact_inflation")

    cursor.execute("""
        INSERT INTO marts.fact_inflation
            (date_id, headline_inflation, food_inflation,
             core_inflation, mom_change, yoy_change,
             rebase_period, source)
        SELECT
            d.date_id,
            s.headline_inflation,
            s.food_inflation,
            s.core_inflation,
            s.mom_change,
            s.yoy_change,
            s.rebase_period,
            'NBS'
        FROM staging.stg_inflation s
        JOIN marts.dim_date d
            ON d.full_date = s.report_date
        WHERE s.is_valid = TRUE
        ON CONFLICT (date_id) DO NOTHING
    """)
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM marts.fact_inflation")
    count = cursor.fetchone()[0]

    # Summary by year
    cursor.execute("""
        SELECT d.year,
               ROUND(AVG(f.headline_inflation)::numeric, 2),
               ROUND(MAX(f.headline_inflation)::numeric, 2),
               ROUND(MIN(f.headline_inflation)::numeric, 2)
        FROM marts.fact_inflation f
        JOIN marts.dim_date d ON d.date_id = f.date_id
        GROUP BY d.year
        ORDER BY d.year
    """)
    by_year = cursor.fetchall()

    print(f"   ✅ {count} records loaded to fact_inflation")
    print(f"   Annual headline inflation:")
    for yr, avg, hi, lo in by_year:
        print(f"   → {yr}: avg {avg:>6}%  "
              f"high {hi:>6}%  low {lo:>6}%")
    return count

# ── MAIN ─────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("FACT TABLE LOADER — staging → marts")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    start = datetime.now()
    conn   = get_connection()
    cursor = conn.cursor()

    fx_count  = load_fact_exchange_rates(cursor, conn)
    inf_count = load_fact_inflation(cursor, conn)

    duration = (datetime.now() - start).total_seconds()

    # Log the run
    cursor.execute("""
        INSERT INTO public.pipeline_runs
            (pipeline_name, status, rows_extracted,
             rows_loaded, duration_seconds)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, ("load_facts", "success",
          fx_count + inf_count,
          fx_count + inf_count,
          duration))
    run_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"✅ Fact load complete!")
    print(f"   fact_exchange_rates : {fx_count} records")
    print(f"   fact_inflation      : {inf_count} records")
    print(f"   Total               : {fx_count + inf_count}")
    print(f"   Duration            : {duration:.2f}s")
    print(f"   Run ID              : {run_id}")
    print("=" * 60)
    return fx_count, inf_count

if __name__ == "__main__":
    run()