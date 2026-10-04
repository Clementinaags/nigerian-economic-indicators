import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# CBN exchange rate page
CBN_URL = "https://www.cbn.gov.ng/rates/ExchRateByCurrency.asp"

# NBS CPI reports page  
NBS_URL = "https://www.nigerianstat.gov.ng/elibrary/read/1241"

# Date range
START_YEAR = 2019
END_YEAR = 2026

# Currencies we care about
TARGET_CURRENCIES = ["US DOLLAR", "POUNDS STERLING", "EURO", "YUAN/RENMINBI"]

# Data quality thresholds
MAX_BUSINESS_DAY_GAP = 5
FX_CROSS_VALIDATION_TOLERANCE = 0.05