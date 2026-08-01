# pages/user1.py
import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread


from util import connect_to_sheets, cached_get_all_records, clear_sheet_cache

def show():
    st.title("Production Requirement")
    st.write("Welcome! This is your private area.")
    st.write("Here you can enter Daily Sales data.")

    # --- 1. SHEET CONNECTION ---
    sh = connect_to_sheets()
    try:
        ws_daily_sales = sh.worksheet("Daily_Sales")
    except gspread.exceptions.WorksheetNotFound:
        ws_daily_sales = sh.add_worksheet(title="Daily_Sales", rows=3000, cols=15)

    # --- 2. HELPER FUNCTIONS (මේ Page එකට විතරක් අදාළ ඒවා) ---
    def save_and_refresh(message, seconds=2):
        """අලුත් Data ලිව්වට පස්සේ Cache එක clear කරලා Page එක Refresh කිරීම"""
        clear_sheet_cache()  # util.py එකෙන් එන Cache clear එක
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_rows_for_date(date_str):
        # util.py හි ඇති Cache function එක පාවිච්චි කිරීම
        records = cached_get_all_records(ws_daily_sales)
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()
        return df[df["Date"].astype(str) == date_str]

    def delete_rows_for_date(date_str):
        records = cached_get_all_records(ws_daily_sales)
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return
        remaining = df[df["Date"].astype(str) != date_str]
        ws_daily_sales.clear()
        set_with_dataframe(ws_daily_sales, remaining if not remaining.empty else pd.DataFrame(columns=df.columns))
        clear_sheet_cache() # Data මකපු නිසා Cache එක අලුත් කරන්න

    def section_banner(text):
        st.markdown(f'<div class="section-banner" style="background-color:#4F46E5;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

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

    section_banner("📤 Upload Daily Sales CSV")

    # පරණ දත්ත තියෙනවාද බැලීම
    existing_sales = get_rows_for_date(selected_date_str)
    
    if not existing_sales.empty:
        st.warning(f"⚠️ Sales data already exists for **{selected_date_str}** ({len(existing_sales)} rows).")
        st.dataframe(styled_table(existing_sales.head(10), gradient_cols=["Qty", "Total Amount"], cmap="Purples"), use_container_width=True)
        if len(existing_sales) > 10:
            st.caption(f"Showing 10 of {len(existing_sales)} rows.")

        if st.button("🗑️ Delete sales data for this date", key="delete_sales_btn"):
            st.session_state["confirm_delete_sales"] = True

        if st.session_state.get("confirm_delete_sales"):
            st.error(f"Permanently delete all {len(existing_sales)} sales rows for {selected_date_str}? This cannot be undone.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Yes, delete it", key="confirm_delete_sales_yes", type="primary"):
                    delete_rows_for_date(selected_date_str)
                    st.session_state["confirm_delete_sales"] = False
                    save_and_refresh(f"🗑️ Sales data for {selected_date_str} deleted.")
            with c2:
                if st.button("Cancel", key="confirm_delete_sales_no"):
                    st.session_state["confirm_delete_sales"] = False
                    st.rerun()

    # CSV Upload කිරීම
    st.info("CSV must contain 5 columns: Product Code, Product Name, Category, Qty, Total Amount")
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"], key="sales_upload")
    
    if uploaded_file is not None:
        try:
            df_csv = pd.read_csv(uploaded_file)
            if st.button("Submit to Google Sheets", type="primary", key="sales_submit"):
                with st.spinner("Processing and uploading..."):
                    df_csv.insert(0, "Date", selected_date_str)
                    df_csv["Qty"] = pd.to_numeric(df_csv["Qty"], errors="coerce").fillna(0)
                    df_csv["Total Amount"] = pd.to_numeric(df_csv["Total Amount"], errors="coerce").fillna(0)
                    df_csv = df_csv.fillna("")
                    
                    data_to_upload = df_csv.values.tolist()
                    ws_daily_sales.append_rows(data_to_upload)
                
                save_and_refresh("✅ Daily sales successfully uploaded!")

        except Exception as e:
            st.error(f"Error processing file: {e}")