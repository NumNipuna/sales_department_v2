import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

from util import connect_to_sheets, cached_get_all_records, clear_sheet_cache

def show():
    st.title("Production Requirement")
    st.write("Welcome, Pradeep...! This is your private area.")
    st.write("Here you can enter Inventory data.")

    # --- 1. SHEET CONNECTION ---
    sh = connect_to_sheets()
    try:
        ws_inventory = sh.worksheet("Inventory")
    except gspread.exceptions.WorksheetNotFound:
        ws_inventory = sh.add_worksheet(title="Inventory", rows=3000, cols=15)

    # --- 2. HELPER FUNCTIONS ---
    def save_and_refresh(message, seconds=2):
        clear_sheet_cache()  
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_rows_for_date(date_str):
        records = cached_get_all_records(ws_inventory)
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()
        
        standardized_dates = pd.to_datetime(df["Date"], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df["Date"].astype(str).str.strip())
        
        return df[standardized_dates == date_str]

    def delete_rows_for_date(date_str):
        records = cached_get_all_records(ws_inventory)
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return
        
        standardized_dates = pd.to_datetime(df["Date"], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df["Date"].astype(str).str.strip())

        remaining = df[standardized_dates != date_str]
        ws_inventory.clear()
        set_with_dataframe(ws_inventory, remaining if not remaining.empty else pd.DataFrame(columns=df.columns))
        clear_sheet_cache() 

    def section_banner(text):
        st.markdown(f'<div class="section-banner" style="background-color:#10B981;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

    def styled_table(df, gradient_cols=None, cmap="Blues"):
        if df.empty:
            return df
        styler = df.style
        if gradient_cols:
            gradient_cols = [c for c in gradient_cols if c in df.columns]
            if gradient_cols:
                styler = styler.background_gradient(subset=gradient_cols, cmap=cmap)
        return styler

    # --- 3. MAIN UI LOGIC ---
    selected_date = st.date_input("Select Date:", value=datetime.date.today())
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    st.divider()

    section_banner("📦 Update Inventory")

    existing_inventory = get_rows_for_date(selected_date_str)
    
    if not existing_inventory.empty:
        st.warning(f"⚠️ Inventory data already exists for **{selected_date_str}** ({len(existing_inventory)} rows).")
        st.dataframe(styled_table(existing_inventory.head(10), gradient_cols=["Available Qty"], cmap="Greens"),
                     use_container_width=True)
        if len(existing_inventory) > 10:
            st.caption(f"Showing 10 of {len(existing_inventory)} rows.")

        if st.button("🗑️ Delete inventory data for this date", key="delete_inv_btn"):
            st.session_state["confirm_delete_inv"] = True

        if st.session_state.get("confirm_delete_inv"):
            st.error(f"Permanently delete all {len(existing_inventory)} inventory rows for {selected_date_str}? This cannot be undone.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Yes, delete it", key="confirm_delete_inv_yes", type="primary"):
                    delete_rows_for_date(selected_date_str)
                    st.session_state["confirm_delete_inv"] = False
                    save_and_refresh(f"🗑️ Inventory data for {selected_date_str} deleted.")
            with c2:
                if st.button("Cancel", key="confirm_delete_inv_no"):
                    st.session_state["confirm_delete_inv"] = False
                    st.rerun()

    st.info("Upload an updated inventory CSV with columns: Product Name, Item Code, Available Qty")
    inv_file = st.file_uploader("Upload Inventory CSV", type=["csv"], key="inv_upload")
    
    if inv_file is not None:
        try:
            df_inv = pd.read_csv(inv_file)

            if st.button("Add to Inventory in Google Sheets", type="primary", key="inv_submit"):
                with st.spinner("Appending inventory..."):
                    if "Date" not in df_inv.columns:
                        df_inv.insert(0, "Date", selected_date_str)
                    df_inv = df_inv.fillna("")
                    
                    all_existing_data = ws_inventory.get_all_values()
                    if not all_existing_data:
                        ws_inventory.append_row(df_inv.columns.tolist())
                        
                    inv_data_to_upload = df_inv.values.tolist()
                    ws_inventory.append_rows(inv_data_to_upload)
                
                save_and_refresh("✅ Inventory successfully added!")

        except Exception as e:
            st.error(f"Error processing inventory file: {e}")