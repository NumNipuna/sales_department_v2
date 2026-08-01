# pages/rep_target.py
import streamlit as st
from util import connect_to_sheets2
import pandas as pd
import gspread
import datetime
import time
from gspread_dataframe import set_with_dataframe


def show():
    st.title("Rep Target")
    st.write("Welcome, Pradeep...! This is your private area.")
    st.write("Here you can enter data.")

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Refresh All Data", key="rep_target_refresh_btn"):
        try:
            _cached_records.clear()
        except NameError:
            pass
        try:
            get_connection.clear()
        except NameError:
            pass
        st.rerun()

    # --- CONNECTION (cached as a resource, not re-created on every rerun) ---
    @st.cache_resource(show_spinner=False)
    def get_connection():
        sh = connect_to_sheets2()
        ws_master = sh.worksheet("MasterData")
        ws_targets = sh.worksheet("MonthlyTargets")
        ws_sales_day = sh.worksheet("Sales_day_book")
        return sh, ws_master, ws_targets, ws_sales_day

    try:
        sh, ws_master, ws_targets, ws_sales_day = get_connection()
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        st.stop()

    # --- CACHED READS ---
    # Same pattern as the other pages: reads are cached for 5 minutes and the
    # cache is cleared right after any save, so you always see fresh data
    # immediately after saving something.
    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_records(_ws, sheet_key):
        return _ws.get_all_records()

    def get_records(ws_obj, sheet_key):
        return _cached_records(ws_obj, sheet_key)

    def invalidate_sheet_cache():
        _cached_records.clear()

    def save_and_refresh(message, seconds=1):
        """Call after any write: invalidates the cache, shows a success message,
        holds it for `seconds`, then refreshes the page."""
        invalidate_sheet_cache()
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_rows_for_column(ws_obj, sheet_key, column, value_str):
        """Return existing rows in a sheet that match a given value in `column`."""
        records = get_records(ws_obj, sheet_key)
        df = pd.DataFrame(records)
        if df.empty or column not in df.columns:
            return pd.DataFrame()
        return df[df[column].astype(str) == value_str]

    def delete_rows_for_column(ws_obj, sheet_key, column, value_str):
        """Permanently remove all rows matching a given value in `column`, keeping everything else."""
        records = get_records(ws_obj, sheet_key)
        df = pd.DataFrame(records)
        if df.empty or column not in df.columns:
            return
        remaining = df[df[column].astype(str) != value_str]
        ws_obj.clear()
        set_with_dataframe(ws_obj, remaining if not remaining.empty else pd.DataFrame(columns=df.columns))

    MONTH_OPTIONS = ["2026-Jan", "2026-Feb", "2026-Mar", "2026-Apr",
                     "2026-May", "2026-Jun", "2026-Jul", "2026-Aug",
                     "2026-Sep", "2026-Oct", "2026-Nov", "2026-Dec",
                     "2027-Jan", "2027-Feb", "2027-Mar", "2027-Apr",
                     "2027-May", "2027-Jun", "2027-Jul", "2027-Aug",
                     "2027-Sep", "2027-Oct", "2027-Nov", "2027-Dec"]

    st.subheader("Update Rep Targets & Sales Day Book")
    st.caption("Manage representative targets and sales day book information from this page.")
    st.divider()

    current_month_str = datetime.date.today().strftime("%Y-%b")
    default_month_index = (MONTH_OPTIONS.index(current_month_str)
                            if current_month_str in MONTH_OPTIONS else 0)
    col1, col2 = st.columns([1, 3])
    with col1:
        month = st.selectbox("Select Month", MONTH_OPTIONS, index=default_month_index, key="month_select")
    st.subheader(f"📍 Enter the target for {month}")

    master_records = get_records(ws_master, "master")
    df_master = pd.DataFrame(master_records) if master_records else pd.DataFrame(
        columns=["No", "Manager", "Route", "Representative", "Status"])

    targets_records = get_records(ws_targets, "targets")
    df_targets_all = pd.DataFrame(targets_records) if targets_records else pd.DataFrame(
        columns=["Month", "No", "Manager", "Route", "Representative", "Status", "Target"])

    if not df_targets_all.empty and "Month" in df_targets_all.columns:
        df_existing = df_targets_all[df_targets_all["Month"].astype(str) == str(month)]
    else:
        df_existing = pd.DataFrame()

    df_editable = df_master.copy()
    if "Target" not in df_editable.columns:
        df_editable["Target"] = 0
    if not df_existing.empty and "No" in df_existing.columns:
        df_editable = df_editable.merge(
            df_existing[["No", "Target"]], on="No", how="left", suffixes=("", "_existing"))
        if "Target_existing" in df_editable.columns:
            df_editable["Target"] = df_editable["Target_existing"].fillna(0)
            df_editable = df_editable.drop(columns=["Target_existing"])
    df_editable["Target"] = pd.to_numeric(df_editable["Target"], errors="coerce").fillna(0)

    column_config = {
        "No": st.column_config.TextColumn("No", disabled=True, width="small"),
        "Manager": st.column_config.TextColumn("Manager", disabled=True),
        "Route": st.column_config.TextColumn("Route", disabled=True),
        "Representative": st.column_config.TextColumn("Representative", disabled=True),
        "Status": st.column_config.TextColumn("Status", disabled=True, width="small"),
        "Target": st.column_config.NumberColumn("🎯 Target", help="Enter Target here", min_value=0, step=1),
    }

    dynamic_editor_key = f"target_editor_{month}"
    edited_df = st.data_editor(
        df_editable,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=500,
        key=dynamic_editor_key,
    )

    if st.button("💾 Save this month Target", type="primary", key=f"save_target_btn_{month}"):
        with st.spinner("Saving..."):
            save_df = edited_df.copy()
            save_df["Month"] = month
            save_cols = ["Month"] + [c for c in df_editable.columns]
            save_df = save_df[save_cols]

            if not df_targets_all.empty and "Month" in df_targets_all.columns:
                remainder = df_targets_all[df_targets_all["Month"].astype(str) != str(month)]
            else:
                remainder = pd.DataFrame(columns=save_cols)

            final_targets = pd.concat([remainder, save_df], ignore_index=True)
            ws_targets.clear()
            set_with_dataframe(ws_targets, final_targets)
        save_and_refresh(f"✅ Data successfully saved for {month}!")

