# pages/user1.py
import streamlit as st
from util import fetch_database_records, connect_to_sheets
import pandas as pd
import numpy as np
from gspread_dataframe import set_with_dataframe
import gspread
import datetime
import time
def show():
    st.title("Production Requrement")
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
        return sh
    try:
        sh = get_connection()
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
    # --- CACHED READS ---
    # Every widget interaction re-runs this whole script. Without caching, that meant
    # live Google Sheets calls on every single click/keystroke. Data is now cached for
    # CACHE_TTL_SECONDS (10 minutes) and gets invalidated immediately after any save,
    # so you still always see fresh data right after you save something - the 10 minute
    # window only applies to changes made directly in the Google Sheet itself, outside
    # this app (use the "Refresh All Data" button in the sidebar to pull those in early).
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
    # විනාඩි 10ක් (තත්පර 600) දත්ත මතකයේ තබා ගැනීමට Cache කිරීම
    # NOTE (fixed): this used to open a brand-new connect_to_sheets() connection and do
    # an uncached ws_items.get_all_records() call on every single rerun/click, which
    # defeated the whole caching setup above. It now reuses the already-connected
    # ws_items + the cached get_records(), so it no longer hits Google Sheets on
    # every interaction. The returned lists are identical either way.
    def get_items_master_lists():
        try:
            df_items = pd.DataFrame(get_records(ws_items, "items"))

            if df_items.empty:
                return [], []

            codes_list = df_items["Product Code"].astype(str).tolist()
            names_list = df_items["Item Name"].astype(str).tolist()

            return codes_list, names_list

        except Exception as e:
            st.error(f"⚠️ Items Master දත්ත ලබාගැනීමේ දෝෂයක්: {e}")
            return [], []
    # Hardcoded lists වෙනුවට මෙලෙස ලබාගන්න
    DEFAULT_CODES, DEFAULT_NAMES = get_items_master_lists()
    # --- DEFAULT 53-ITEM MASTER LIST (now managed from Settings — kept here only
    # as the seed used the very first time the Items_Master sheet is created) ---
    def init_items_master():
        existing = ws_items.get_all_values()
        if not existing or existing[0][:2] != ["Product Code", "Item Name"]:
            df = pd.DataFrame({"Product Code": DEFAULT_CODES, "Item Name": DEFAULT_NAMES})
            ws_items.clear()
            set_with_dataframe(ws_items, df)
    # Only do this check once per browser session, not on every rerun/click
    if not st.session_state.get("_items_master_checked"):
        init_items_master()
        st.session_state["_items_master_checked"] = True
    # Shared dropdown option lists
    year_options = [str(y) for y in range(2024, 2035)]
    month_options = ["January", "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December"]

    def section_banner(text):
        st.markdown(f'<div class="section-banner">{text}</div>', unsafe_allow_html=True)


    section_banner("🎯 Set Monthly Forecast")
    st.caption("Enter the forecast quantity/amount for each item for a given month. "
            "Saving only updates the selected month — other months are kept untouched.")
    fc_col1, fc_col2 = st.columns(2)
    with fc_col1:
        forecast_year = st.selectbox("Forecast Year", year_options,
                                    index=year_options.index(str(datetime.date.today().year))
                                    if str(datetime.date.today().year) in year_options else 0,
                                    key="forecast_year_select")
    with fc_col2:
        forecast_month = st.selectbox("Forecast Month", month_options,
                                    index=datetime.date.today().month - 1,
                                    key="forecast_month_select")
    items_records = get_records(ws_items, "items")
    df_items_now = pd.DataFrame(items_records) if items_records else pd.DataFrame(columns=["Product Code", "Item Name"])
    forecast_records = get_records(ws_forecast, "forecast")
    df_forecast_all = pd.DataFrame(forecast_records) if forecast_records else pd.DataFrame(
        columns=["Year", "Month", "Product Code", "Item Name", "Forecast Qty"])
    # 🔥 Type Safety එකතු කර ඇත: .astype(str) සහ str() පාවිච්චි කර ඇත
    if not df_forecast_all.empty:
        df_forecast_month = df_forecast_all[
            (df_forecast_all["Year"].astype(str) == str(forecast_year)) &
            (df_forecast_all["Month"].astype(str) == str(forecast_month))
        ][["Product Code", "Forecast Qty"]]
    else:
        df_forecast_month = pd.DataFrame(columns=["Product Code", "Forecast Qty"])
    merged_forecast = df_items_now.merge(df_forecast_month, on="Product Code", how="left")
    merged_forecast["Forecast Qty"] = pd.to_numeric(merged_forecast.get("Forecast Qty"), errors="coerce").fillna(0)
    # 🔥 වෙනස 1: Key එක Dynamic කිරීම (Year + Month එකතුවෙන් අලුත් Key එකක් හැදේ)
    dynamic_editor_key = f"forecast_editor_{forecast_year}_{forecast_month}"
    edited_forecast = st.data_editor(
        merged_forecast,
        use_container_width=True,
        hide_index=True,
        disabled=["Product Code", "Item Name"],
        key=dynamic_editor_key, # <--- වෙනස් කළ ස්ථානය
    )
    # 🔥 වෙනස 2: Button Key එකත් Dynamic කිරීම වඩාත් ආරක්ෂිතයි
    save_btn_key = f"save_forecast_btn_{forecast_year}_{forecast_month}"
    if st.button("Save Forecast", type="primary", key=save_btn_key):
        with st.spinner("Saving forecast..."):
            edited_forecast = edited_forecast.copy()
            edited_forecast["Year"] = forecast_year
            edited_forecast["Month"] = forecast_month
            save_cols = ["Year", "Month", "Product Code", "Item Name", "Forecast Qty"]
            save_df = edited_forecast[save_cols]
            if not df_forecast_all.empty:
                remainder = df_forecast_all[~(
                    (df_forecast_all["Year"].astype(str) == str(forecast_year)) &
                    (df_forecast_all["Month"].astype(str) == str(forecast_month))
                )]
            else:
                remainder = pd.DataFrame(columns=save_cols)
            final_forecast = pd.concat([remainder, save_df], ignore_index=True)
            ws_forecast.clear()
            set_with_dataframe(ws_forecast, final_forecast)
        save_and_refresh(f"✅ Forecast for {forecast_month} {forecast_year} saved!")