# util.py
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st
from google.oauth2.service_account import Credentials

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

USERS = {
    "user1": {"password_hash": hash_password("pass1"), "role": "user1"},
    "user2": {"password_hash": hash_password("pass2"), "role": "user2"},
    "user3": {"password_hash": hash_password("pass3"), "role": "user3"},
    "admin": {"password_hash": hash_password("adminpass"), "role": "admin"}
}

def authenticate(username, password):
    if username in USERS:
        if USERS[username]["password_hash"] == hash_password(password):
            return USERS[username]["role"]
    return None

def get_allowed_pages(role):
    if role == "admin":
        return ["Requrement", "dashboard","rep_target"]
    if role in ["user1"]:
        return ["1sales_by_product","1sales_day_book","2Inventory","3Monthly_Forecast","4Working_days","5Rep_Target"]
    if role in ["user2","user3"]:
        return [role]
    return []

# ---------- Google Sheets Connection ----------


# ========================================================
# Control API limit
# ========================================================
@st.cache_data(ttl=600, show_spinner=False)
def cached_get_all_records(_ws):
    return _ws.get_all_records()

@st.cache_data(ttl=600, show_spinner=False)
def cached_get_all_values(_ws):
    return _ws.get_all_values()

def clear_sheet_cache():
    """අලුත් Data Sheet එකට ලිව්වට පස්සේ පරණ මතකය (Cache) මකා දැමීම"""
    cached_get_all_records.clear()
    cached_get_all_values.clear()
# ========================================================

def get_credentials():
    """Centralized function to build credentials from Streamlit secrets."""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = dict(st.secrets["gcp_service_account"])
    return Credentials.from_service_account_info(service_account_info, scopes=scope)


def get_client():
    return gspread.authorize(get_credentials())


@st.cache_resource
def connect_to_sheets():
    gc = gspread.service_account(filename="service_account.json")
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1TWSwwcEElojBnoqY_hPllfb3l9xn1_9ed4Xy4FQdq98/edit")
    return sh

def connect_to_sheets2():
    gc = gspread.service_account(filename="service_account.json")
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1TWSwwcEElojBnoqY_hPllfb3l9xn1_9ed4Xy4FQdq98/edit")
    return sh

@st.cache_data
def fetch_database_records():
    sh = connect_to_sheets()
    main_records = sh.worksheet("Data_Entry").get_all_records()
    reps_records = sh.worksheet("Sales_Reps").get_all_records()
    try:
        banks_records = sh.worksheet("Banks").get_all_records()
    except:
        banks_records = []
    return main_records, reps_records, banks_records


def get_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scope)
    return gspread.authorize(credentials)

# ----- Master Data Load කරන්න -----
def load_master_data():
    """Master Data Load කරන්න - දැන් connect_to_sheets2() භාවිතා කරයි"""
    sh = connect_to_sheets2()  # <--- Use connect_to_sheets2() here
    try:
        ws = sh.worksheet("MasterData")
        records = ws.cached_get_all_records(ws)
        return records
    except gspread.exceptions.WorksheetNotFound:
        # If the worksheet doesn't exist, create it with headers
        ws = sh.add_worksheet(title="MasterData", rows=500, cols=20)
        ws.append_row(["No", "Manager", "Route", "Representative", "Status"])
        return []
    
def load_targets_for_month(month):
    """Load targets for a specific month from the "MonthlyTargets" worksheet."""
    sh = connect_to_sheets2()
    try:
        ws = sh.worksheet("MonthlyTargets")
        records = cached_get_all_records(ws)
        df_all = pd.DataFrame(records)
        if df_all.empty:
            return pd.DataFrame()
        df_month = df_all[df_all["Month"] == month]
        if not df_month.empty and "No" in df_month.columns:
            return df_month[["No", "Target"]]
        return pd.DataFrame()
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()
    

# ----- Update Master Data (via Settings) -----
def update_master_data(df):
    client = get_client()
    sheet = client.open("Sales data2").worksheet("MasterData")
    
    # Delete existing data (except the header).
    all_rows = sheet.get_all_values()
    if len(all_rows) > 1:
        sheet.delete_rows(2, len(all_rows))
    
    # Rewrite the header (using the DataFrame columns).
    headers = df.columns.tolist()
    if not sheet.get_all_values():  # If the sheet is empty, add headers
        sheet.append_row(headers)
    
    # Append new rows from the DataFrame.
    for _, row in df.iterrows():
        sheet.append_row(row.tolist())
    clear_sheet_cache()  # Clear cache after updating the sheet
    return True

# ----- Save Monthly Targets -----
def save_monthly_data(month, data_list):
    client = get_client()
    sheet = client.open("Sales data2").worksheet("MonthlyTargets")
    
    # 1. Find and delete the existing rows for that month only (without affecting data from other months).
    all_values = sheet.get_all_values()
    rows_to_delete = []
    if len(all_values) > 1:  # Header එක හැර
        for idx, row in enumerate(all_values, start=1):
            if idx == 1:
                continue  # Header එක පැත්තකින් තියන්න
            if len(row) > 0 and row[0] == month:
                rows_to_delete.append(idx)
    
    # Delete from bottom to top to avoid index shifting
    for idx in sorted(rows_to_delete, reverse=True):
        sheet.delete_rows(idx)
    
    # 2. Append new data for that month
    for row in data_list:
        new_row = [
            month,
            row.get("No", ""),
            row.get("Manager", ""),
            row.get("Route", ""),
            row.get("Representative", ""),
            row.get("Status", ""),
            row.get("Target", "")
        ]
        sheet.append_row(new_row)
    clear_sheet_cache()
    return True


@st.cache_resource
def connect_to_sheets2():
    gc = gspread.service_account(filename="service_account.json")
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1xO3xNDYkC-97BHksfiq9BRpJ9rDP9_snTzTLP-sJbMg/edit?usp=sharing")
    return sh

def save_monthly_data(month, data_list):
    """
    Save monthly targets to the same Google Sheet used by connect_to_sheets().
    """
    # Use connect_to_sheets() instead of get_client() here.
    sh = connect_to_sheets2()
    
    # Check if the "MonthlyTargets" worksheet exists; if not, create it with headers.
    try:
        ws = sh.worksheet("MonthlyTargets")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="MonthlyTargets", rows=1000, cols=20)
        ws.append_row(["Month", "No", "Manager", "Route", "Representative", "Status", "Target"])
    
    # Delete existing rows for the specified month (without affecting other months).
    all_values = ws.get_all_values()
    rows_to_delete = []
    if len(all_values) > 1:
        for idx, row in enumerate(all_values, start=1):
            if idx == 1:
                continue  # Skip the header row
            if len(row) > 0 and row[0] == month:
                rows_to_delete.append(idx)
    
    # Delete from bottom to top to avoid index shifting
    for idx in sorted(rows_to_delete, reverse=True):
        ws.delete_rows(idx)
    
    # Append new data for that month
    for row in data_list:
        new_row = [
            month,
            row.get("No", ""),
            row.get("Manager", ""),
            row.get("Route", ""),
            row.get("Representative", ""),
            row.get("Status", ""),
            row.get("Target", "")
        ]
        ws.append_row(new_row)
    
    return True 


# ----- Sales Day Book -----
def get_sales_daybook_ws():
    """Get (or create) the Sales_day_book worksheet."""
    sh = connect_to_sheets2()
    try:
        ws = sh.worksheet("Sales_day_book")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Sales_day_book", rows=2000, cols=20)
        ws.append_row(["new_date", "Date", "Agent", "Customer ID", "Customer",
                        "Group", "Invoice", "Item", "Qty", "Amount", "VAT"])
    return ws

def get_rows_for_date(ws, date_col_name, date_value):
    """Return all rows from ws where date_col_name matches date_value."""
    records = cached_get_all_records(ws)
    df = pd.DataFrame(records)
    if df.empty or date_col_name not in df.columns:
        return pd.DataFrame()
    return df[df[date_col_name].astype(str) == str(date_value)]

def delete_rows_for_date(ws, date_col_name, date_value):
    """Delete all rows from ws where date_col_name matches date_value.
    Uses a single batched API call instead of one call per row (avoids rate limits)."""
    all_values = ws.get_all_values()
    if len(all_values) < 2:
        return
    header = all_values[0]
    if date_col_name not in header:
        return
    col_idx = header.index(date_col_name)
    target = pd.to_datetime(date_value).normalize()

    rows_to_delete = []
    for idx, row in enumerate(all_values, start=1):
        if idx == 1:
            continue
        if len(row) > col_idx and row[col_idx].strip():
            cell_date = pd.to_datetime(row[col_idx].strip(), errors="coerce")
            if pd.notna(cell_date) and cell_date.normalize() == target:
                rows_to_delete.append(idx)

    if not rows_to_delete:
        return

    # --- Group consecutive row numbers into ranges, e.g. [5,6,7,10,11] -> [(5,7),(10,11)] ---
    rows_to_delete.sort()
    ranges = []
    start = prev = rows_to_delete[0]
    for r in rows_to_delete[1:]:
        if r == prev + 1:
            prev = r
        else:
            ranges.append((start, prev))
            start = prev = r
    ranges.append((start, prev))

    # --- Build one batch_update request with all delete ranges ---
    # Delete from bottom to top so earlier deletions don't shift later ranges
    sheet_id = ws.id
    requests = []
    for (start_row, end_row) in reversed(ranges):
        requests.append({
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_row - 1,   # 0-indexed, inclusive
                    "endIndex": end_row              # 0-indexed, exclusive
                }
            }
        })

    ws.spreadsheet.batch_update({"requests": requests})
    clear_sheet_cache()


    import calendar
from datetime import datetime

# ----- Working Days Sheet -----
def get_working_days_ws():
    sh = connect_to_sheets2()
    try:
        ws = sh.worksheet("Working_Days")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Working_Days", rows=200, cols=10)
        ws.append_row(["Year", "Month", "Working Days", "Working Days 2", "Day To Work"])
    return ws


def _parse_report_month(month_str):
    """'2026-Jul' -> (year, month_num, full_month_name e.g. 'July', days_in_month)"""
    year_str, mon_abbr = month_str.split("-")
    year = int(year_str)
    month_num = datetime.strptime(mon_abbr, "%b").month
    full_month_name = datetime(year, month_num, 1).strftime("%B")
    days_in_month = calendar.monthrange(year, month_num)[1]
    return year, month_num, full_month_name, days_in_month


def load_working_days(month_str):
    """Look up Working Days / Working Days 2 / Day To Work for the given month."""
    year, month_num, full_month_name, days_in_month = _parse_report_month(month_str)
    ws = get_working_days_ws()
    records = cached_get_all_records(ws)

    result = {
        "Year": year, "MonthNum": month_num, "MonthName": full_month_name,
        "DaysInMonth": days_in_month,
        "Working Days": 0, "Working Days 2": 0, "Day To Work": 0
    }
    for row in records:
        row_year = str(row.get("Year", "")).strip()
        row_month = str(row.get("Month", "")).strip().lower()
        if row_year == str(year) and row_month == full_month_name.lower():
            result["Working Days"] = pd.to_numeric(row.get("Working Days", 0), errors="coerce") or 0
            result["Working Days 2"] = pd.to_numeric(row.get("Working Days 2", 0), errors="coerce") or 0
            result["Day To Work"] = pd.to_numeric(row.get("Day To Work", 0), errors="coerce") or 0
            break
    return result


def _normalize_name(name):
    """Match Agent <-> Representative by first name, case-insensitive."""
    if not name or not isinstance(name, str):
        return ""
    parts = name.strip().split()
    return parts[0].lower() if parts else ""


# ----- Report Sheet -----
def get_report_ws():
    sh = connect_to_sheets2()
    try:
        ws = sh.worksheet("Report")
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title="Report", rows=1000, cols=60)
    return ws


def build_report(month_str):
    """Join MonthlyTargets + Working_Days + Sales_day_book into the full report DataFrame."""
    sh = connect_to_sheets2()
    wd = load_working_days(month_str)
    year, month_num, days_in_month = wd["Year"], wd["MonthNum"], wd["DaysInMonth"]
    working_days = wd["Working Days"] or 0
    working_days2 = wd["Working Days 2"] or 0
    day_to_work = wd["Day To Work"] or 0

    # --- Targets for selected month ---
    ws_targets = sh.worksheet("MonthlyTargets")
    df_targets = pd.DataFrame(ws_targets.get_all_records())
    if df_targets.empty or "Month" not in df_targets.columns:
        return pd.DataFrame()
    df_targets = df_targets[df_targets["Month"] == month_str].copy()
    if df_targets.empty:
        return pd.DataFrame()
    df_targets["Target"] = pd.to_numeric(df_targets["Target"], errors="coerce").fillna(0)

    # --- Sales day book, filtered to this month ---
    ws_sales = get_sales_daybook_ws()
    df_sales = pd.DataFrame(ws_sales.get_all_records())
    date_cols = [f"{year}-{month_num:02d}-{d:02d}" for d in range(1, days_in_month + 1)]

    if not df_sales.empty and "new_date" in df_sales.columns and "Agent" in df_sales.columns:
        df_sales["Qty"] = pd.to_numeric(df_sales.get("Qty", 0), errors="coerce").fillna(0)
        df_sales["new_date"] = df_sales["new_date"].astype(str)
        df_sales["rep_key"] = df_sales["Agent"].apply(_normalize_name)
        df_month_sales = df_sales[df_sales["new_date"].isin(date_cols)]
        pivot = df_month_sales.pivot_table(
            index="rep_key", columns="new_date", values="Qty", aggfunc="sum", fill_value=0
        )
    else:
        pivot = pd.DataFrame()

    # --- Build each report row ---
    report_rows = []
    for i, row in df_targets.reset_index(drop=True).iterrows():
        rep_key = _normalize_name(row.get("Representative", ""))
        if rep_key in pivot.index:
            daily_values = {c: float(pivot.loc[rep_key, c]) if c in pivot.columns else 0.0 for c in date_cols}
        else:
            daily_values = {c: 0.0 for c in date_cols}

        sales = sum(daily_values.values())
        target = row["Target"]
        day_target = (target / working_days) if working_days else 0
        balance = sales - target
        achievement = (sales / target) if target else 0
        day_target2 = day_target * working_days2
        day_achievement = (sales / day_target2) if day_target2 else 0
        average = (sales / days_in_month) if days_in_month else 0
        day_to_work_target = average * day_to_work
        forecast = day_to_work_target + sales
        forecast_achievement = (forecast / target) if target else 0

        report_row = {
            "No": i + 1,
            "Manager": row.get("Manager", ""),
            "Route": row.get("Route", ""),
            "Representative": row.get("Representative", ""),
            "Status": row.get("Status", ""),
            "Day Target": round(day_target, 2),
            "Sales": round(sales, 2),
            "Target": round(target, 2),
            "Balance": round(balance, 2),
            "Achievement": round(achievement, 4),
            "Day Target 2": round(day_target2, 2),
            "Day Achievement": round(day_achievement, 4),
            "Average": round(average, 2),
            "Day to work target": round(day_to_work_target, 2),
            "Forecast": round(forecast, 2),
            "Forecast Achievement %": round(forecast_achievement, 4),
        }
        report_row.update({c: round(daily_values[c], 2) for c in date_cols})
        report_rows.append(report_row)

    return pd.DataFrame(report_rows)


def save_report_to_sheet(df_report):
    """Overwrite the 'Report' worksheet with the freshly built report."""
    ws = get_report_ws()
    ws.clear()
    if df_report.empty:
        return
    headers = df_report.columns.tolist()
    values = df_report.fillna("").values.tolist()
    ws.update(range_name="A1", values=[headers] + values)
    clear_sheet_cache()