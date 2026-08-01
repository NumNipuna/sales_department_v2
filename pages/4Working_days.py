import streamlit as st
from util import fetch_database_records, connect_to_sheets, connect_to_sheets2
import pandas as pd
import numpy as np
from gspread_dataframe import set_with_dataframe
import gspread
import datetime
import time
import plotly.express as px
import plotly.graph_objects as go
import io
import base64
import streamlit.components.v1 as components

def show():
    st.title("Production Requirement")
    st.write("Welcome, Pradeep...! This is your private area.")
    st.write("Here you can enter data.")
    CACHE_TTL_SECONDS = 600  # 10 minutes - how long data is reused before a fresh Google Sheets call is made
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🔄 Refresh All Data", key="home_refresh_btn"):
        fetch_database_records.clear()
        try:
            _cached_records.clear()
        except NameError:
            pass
        try:
            get_connection.clear()
        except NameError:
            pass
        try:
            get_or_create_ws.clear()
        except NameError:
            pass
        st.rerun()

    # --- CONNECTION (cached as a resource, not re-created on every rerun) ---
    @st.cache_resource(show_spinner=False)
    def get_connection():
        sh = connect_to_sheets()
        sh2 = connect_to_sheets2()
        ws_main = sh.worksheet("Data_Entry")
        ws_working_days = sh.worksheet("Working_Days")
        try:
            ws_daily_sales = sh2.worksheet("Sales_day_book")
        except gspread.exceptions.WorksheetNotFound:
            ws_daily_sales = sh2.add_worksheet(title="Sales_day_book", rows=3000, cols=15)
        ws_inventory = sh.worksheet("Inventory")
        return sh, ws_main, ws_working_days, ws_daily_sales, ws_inventory

    try:
        Working_Days, Daily_Sales, Inventory = fetch_database_records()
        sh, ws_main, ws_working_days, ws_daily_sales, ws_inventory = get_connection()
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        st.stop()

    # --- AUTO-CREATE NEW WORKSHEETS IF THEY DON'T EXIST (also cached as a resource) ---
    @st.cache_resource(show_spinner=False)
    def get_or_create_ws(title, rows=3000, cols=15):
        try:
            return sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            return sh.add_worksheet(title=title, rows=rows, cols=cols)

    ws_items = get_or_create_ws("Items_Master")
    ws_forecast = get_or_create_ws("Forecast")
    ws_report = get_or_create_ws("Report")

    # --- CACHED READS ---
    @st.cache_data(ttl=660, show_spinner=False)
    def _cached_records(_ws, sheet_key):
        return _ws.get_all_records()

    def get_records(ws_obj, sheet_key):
        return _cached_records(ws_obj, sheet_key)

    def invalidate_sheet_cache():
        _cached_records.clear()

    def save_and_refresh(message, seconds=3):
        """Call after any write: invalidates the cache, shows a success message
        right at this point in the page (so it appears near the button that
        triggered it), holds it for `seconds`, then refreshes the page."""
        invalidate_sheet_cache()
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_items_master_lists():
        try:
            df_items = pd.DataFrame(get_records(ws_items, "items"))
            if df_items.empty:
                return [], []
            codes_list = df_items["Product Code"].astype(str).tolist()
            names_list = df_items["Item Name"].astype(str).tolist()
            return codes_list, names_list
        except Exception as e:
            st.error(f"⚠️ Error fetching Items Master data: {e}")
            return [], []

    DEFAULT_CODES, DEFAULT_NAMES = get_items_master_lists()

    def init_items_master():
        existing = ws_items.get_all_values()
        if not existing or existing[0][:2] != ["Product Code", "Item Name"]:
            df = pd.DataFrame({"Product Code": DEFAULT_CODES, "Item Name": DEFAULT_NAMES})
            ws_items.clear()
            set_with_dataframe(ws_items, df)

    if not st.session_state.get("_items_master_checked"):
        init_items_master()
        st.session_state["_items_master_checked"] = True

    # Shared dropdown option lists
    year_options = [str(y) for y in range(2026, 2035)]
    month_options = ["January", "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December"]
    day_options = [str(d) for d in range(0, 32)]

    def section_banner(text):
        st.markdown(f'<div class="section-banner">{text}</div>', unsafe_allow_html=True)


    section_banner("📅 Manage Monthly Working Days")

    # 1. Fetch existing Working Days data
    try:
        working_days_data = get_records(ws_working_days, "working_days")
        df_working = pd.DataFrame(working_days_data)
        if not df_working.empty:
            df_working["Year"] = df_working["Year"].astype(str)
            df_working["Working Days"] = pd.to_numeric(df_working["Working Days"], errors="coerce").fillna(0).astype(int)
        else:
            df_working = pd.DataFrame(columns=["Year", "Month", "Working Days"])
    except Exception:
        df_working = pd.DataFrame(columns=["Year", "Month", "Working Days"])

    # 2. Calculate Worked Days based on unique 'New_date' column from Sales_day_book
    sales_records = get_records(ws_daily_sales, "daily_sales")
    df_sales = pd.DataFrame(sales_records)

    worked_days_dict = {}
    if not df_sales.empty:
        # Standardize column search for 'New_date' regardless of case sensitivity
        target_col = None
        for col in df_sales.columns:
            if col.strip().lower() == "new_date":
                target_col = col
                break
        
        if target_col:
            # Convert 'New_date' column to datetime objects
            df_sales['Date_obj'] = pd.to_datetime(df_sales[target_col], errors='coerce')
            valid_sales = df_sales.dropna(subset=['Date_obj']).copy()

            if not valid_sales.empty:
                # Format to standard date string (YYYY-MM-DD), Year string, and Month name
                valid_sales['Just_Date'] = valid_sales['Date_obj'].dt.strftime('%Y-%m-%d')
                valid_sales['Y_str'] = valid_sales['Date_obj'].dt.year.astype(str)
                valid_sales['M_str'] = valid_sales['Date_obj'].dt.month_name()

                # Calculate unique dates count per Year and Month based on 'New_date'
                grouped = valid_sales.groupby(['Y_str', 'M_str'])['Just_Date'].nunique()
                worked_days_dict = grouped.to_dict()

    # 3. Map Worked Days and calculate remaining Days to Work
    worked_days_list = []
    days_to_work_list = []

    for idx, row in df_working.iterrows():
        y = str(row.get("Year", ""))
        m = str(row.get("Month", ""))
        wd = int(row.get("Working Days", 0))

        wkd = worked_days_dict.get((y, m), 0)
        worked_days_list.append(wkd)
        days_to_work_list.append(max(0, wd - wkd))
        
    df_working["Worked Days"] = worked_days_list
    df_working["Days to Work"] = days_to_work_list
    df_working["Working Days"] = df_working["Working Days"].astype(str)

    # 4. Render Data Editor
    edited_working_days = st.data_editor(
        df_working,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        disabled=["Worked Days", "Days to Work"],
        column_config={
            "Year": st.column_config.SelectboxColumn("Year", options=year_options, required=True),
            "Month": st.column_config.SelectboxColumn("Month", options=month_options, required=True),
            "Working Days": st.column_config.SelectboxColumn("Working Days", options=day_options, required=True),
            "Worked Days": st.column_config.NumberColumn("Worked Days (Auto)"),
            "Days to Work": st.column_config.NumberColumn("Days to Work (Auto)"),
        },
        key="working_days_editor",
    )

    # 5. Save all 5 columns back to Google Sheets
    if st.button("Save Working Days", type="primary", key="save_wd_btn"):
        with st.spinner("Saving changes..."):
            save_cols = ["Year", "Month", "Working Days", "Worked Days", "Days to Work"]
            save_df = edited_working_days[save_cols].copy()

            ws_working_days.clear()
            set_with_dataframe(ws_working_days, save_df)
        save_and_refresh("✅ Working days successfully updated!")