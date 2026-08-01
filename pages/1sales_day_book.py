import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

# 🔥 util.py එකෙන් 'cached_get_all_records' ඉවත් කර ඇත (Cache පැටලීම වැළැක්වීමට)
from util import connect_to_sheets2, clear_sheet_cache

def show():
    st.title("Production Requirement")
    st.write("Welcome! This is your private area.")
    st.write("Here you can enter Daily Sales data.")

    # --- 1. SHEET CONNECTION ---
    sh2 = connect_to_sheets2()
    try:
        ws_daily_sales = sh2.worksheet("Sales_day_book")
    except gspread.exceptions.WorksheetNotFound:
        ws_daily_sales = sh2.add_worksheet(title="Sales_day_book", rows=3000, cols=15)

    # --- 2. UNIQUE LOCAL CACHE (Fixes the Data Bleed issue) ---
    # unique_key එකක් දීමෙන් මේ cache එක වෙනත් page එකක් එක්ක පැටලෙන්නේ නෑ
    @st.cache_data(ttl=600, show_spinner=False)
    def get_local_sales_data(unique_key):
        try:
            return ws_daily_sales.get_all_records(default_blank="")
        except Exception:
            return []

    # --- 3. HELPER FUNCTIONS ---
    def save_and_refresh(message, seconds=2):
        clear_sheet_cache()
        get_local_sales_data.clear() # මේ page එකේ local cache එකත් clear කරනවා
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_date_column(df):
        return "new_date" if "new_date" in df.columns else "Date"

    def get_rows_for_date(date_str):
        # Local cache එක හරහා දත්ත ලබාගැනීම
        records = get_local_sales_data("Sales_day_book_data")
        df = pd.DataFrame(records)
        if df.empty:
            return pd.DataFrame()
            
        date_col = get_date_column(df)
        if date_col not in df.columns:
            return pd.DataFrame()
            
        standardized_dates = pd.to_datetime(df[date_col], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df[date_col].astype(str).str.strip())
        
        return df[standardized_dates == date_str]

    def delete_rows_for_date(date_str):
        records = get_local_sales_data("Sales_day_book_data")
        df = pd.DataFrame(records)
        if df.empty:
            return
            
        date_col = get_date_column(df)
        if date_col not in df.columns:
            return
            
        standardized_dates = pd.to_datetime(df[date_col], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df[date_col].astype(str).str.strip())
            
        remaining = df[standardized_dates != date_str]
        ws_daily_sales.clear()
        set_with_dataframe(ws_daily_sales, remaining if not remaining.empty else pd.DataFrame(columns=df.columns))
        
        clear_sheet_cache() 
        get_local_sales_data.clear() # Data මකපු නිසා Cache එක අලුත් කරන්න

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

    # --- 4. MAIN UI LOGIC ---
    selected_date = st.date_input("Select Date:", value=datetime.date.today())
    selected_date_str = selected_date.strftime('%Y-%m-%d')
    st.divider()

    section_banner("📤 Upload Daily Sales CSV")

    existing_sales = get_rows_for_date(selected_date_str)
    
    if not existing_sales.empty:
        st.warning(f"⚠️ Sales data already exists for **{selected_date_str}** ({len(existing_sales)} rows).")
        st.dataframe(styled_table(existing_sales.head(10), gradient_cols=["Qty", "Amount"], cmap="Purples"), use_container_width=True)
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

    st.info("Upload Sales Day Book csv file")
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"], key="sales_upload")
    
    if uploaded_file is not None:
        try:
            df_csv = pd.read_csv(uploaded_file)
            if st.button("Submit to Google Sheets", type="primary", key="sales_submit"):
                with st.spinner("Processing and uploading..."):
                    
                    if "new_date" not in df_csv.columns:
                        df_csv.insert(0, "new_date", selected_date_str)
                        
                    df_csv["Qty"] = pd.to_numeric(df_csv.get("Qty", 0), errors="coerce").fillna(0)
                    df_csv["Amount"] = pd.to_numeric(df_csv.get("Amount", 0), errors="coerce").fillna(0)
                    df_csv = df_csv.fillna("")
                    
                    all_existing_data = ws_daily_sales.get_all_values()
                    if not all_existing_data:
                        ws_daily_sales.append_row(df_csv.columns.tolist())
                    
                    data_to_upload = df_csv.values.tolist()
                    ws_daily_sales.append_rows(data_to_upload)
                
                save_and_refresh("✅ Sales Day book successfully uploaded!")

        except Exception as e:
            st.error(f"Error processing file: {e}")