import streamlit as st
from util import fetch_database_records, connect_to_sheets, connect_to_sheets2
import pandas as pd
from gspread_dataframe import set_with_dataframe
import gspread
import datetime
import time

def show():
    st.title("Production Requirement")
    st.write("Welcome! This is your private area.")
    st.write("Here you can manage Working Days.")
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🔄 Refresh All Data", key="home_refresh_btn_wd"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    @st.cache_resource(show_spinner=False)
    def get_connection():
        sh = connect_to_sheets()
        sh2 = connect_to_sheets2()
        
        try:
            ws_working_days = sh.worksheet("Working_Days")
        except gspread.exceptions.WorksheetNotFound:
            ws_working_days = sh.add_worksheet(title="Working_Days", rows=3000, cols=15)
            
        try:
            ws_daily_sales = sh2.worksheet("Sales_day_book")
        except gspread.exceptions.WorksheetNotFound:
            ws_daily_sales = sh2.add_worksheet(title="Sales_day_book", rows=3000, cols=15)
            
        return ws_working_days, ws_daily_sales

    try:
        ws_working_days, ws_daily_sales = get_connection()
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        st.stop()

    st.markdown("""
        <style>
        div[data-testid="stSelectbox"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #03045E !important;
        }
        
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            border: 2px solid #0096C7 !important; 
            border-radius: 8px !important;        
            background-color: #F8FDFF !important; 
            transition: all 0.3s ease-in-out;     
        }
        
        div[data-testid="stSelectbox"] div[data-baseweb="select"]:focus-within {
            border: 2px solid #03045E !important; 
            box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }
        
        [data-testid="stDataFrame"] {
            border: 2px solid #0096C7 !important;
            border-radius: 8px !important;
            overflow: hidden !important;
        }
        </style>
    """, unsafe_allow_html=True)

    def section_banner(text):
        st.markdown(f'<div class="section-banner" style="background-color:#052b6c;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

    year_options = [str(y) for y in range(2024, 2035)]
    month_options = ["January", "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December"]
    day_options = [str(d) for d in range(0, 32)]

    section_banner("📅 Manage Monthly Working Days")
    st.write("")

    with st.spinner("Syncing data..."):
        raw_working_days = ws_working_days.get_all_records(default_blank="")
        df_working = pd.DataFrame(raw_working_days)
        
        if not df_working.empty:
            df_working["Year"] = df_working["Year"].astype(str)
            df_working["Month"] = df_working["Month"].astype(str)
            df_working["Working Days"] = pd.to_numeric(df_working["Working Days"], errors="coerce").fillna(0).astype(int)
        else:
            df_working = pd.DataFrame(columns=["Year", "Month", "Working Days", "Worked Days", "Days to Work"])

        raw_sales = ws_daily_sales.get_all_records(default_blank="")
        df_sales = pd.DataFrame(raw_sales)

        worked_days_dict = {}
        if not df_sales.empty:
            target_col = next((col for col in df_sales.columns if col.strip().lower() in ["new_date", "date"]), None)
            
            if target_col:
                df_sales['Date_obj'] = pd.to_datetime(df_sales[target_col], errors='coerce')
                valid_sales = df_sales.dropna(subset=['Date_obj']).copy()

                if not valid_sales.empty:
                    valid_sales['Just_Date'] = valid_sales['Date_obj'].dt.strftime('%Y-%m-%d')
                    valid_sales['Y_str'] = valid_sales['Date_obj'].dt.year.astype(str)
                    valid_sales['M_str'] = valid_sales['Date_obj'].dt.month_name()

                    grouped = valid_sales.groupby(['Y_str', 'M_str'])['Just_Date'].nunique()
                    worked_days_dict = grouped.to_dict()

        worked_days_list = []
        days_to_work_list = []

        for idx, row in df_working.iterrows():
            y = str(row.get("Year", ""))
            m = str(row.get("Month", ""))
            wd = int(row.get("Working Days", 0))

            wkd = worked_days_dict.get((y, m), 0)
            worked_days_list.append(wkd)
            days_to_work_list.append(max(0, wd - wkd))
            
        updated_df_working = df_working.copy()
        if not updated_df_working.empty:
            updated_df_working["Worked Days"] = worked_days_list
            updated_df_working["Days to Work"] = days_to_work_list
            updated_df_working["Working Days"] = updated_df_working["Working Days"].astype(str)

        needs_auto_save = False
        if not updated_df_working.empty and not df_working.empty:
            orig_records = df_working.fillna("").astype(str).to_dict('records')
            new_records = updated_df_working.fillna("").astype(str).to_dict('records')
            
            if orig_records != new_records:
                needs_auto_save = True

        if needs_auto_save:
            save_cols = ["Year", "Month", "Working Days", "Worked Days", "Days to Work"]
            save_df = updated_df_working[save_cols].copy()
            ws_working_days.clear()
            set_with_dataframe(ws_working_days, save_df)
            st.toast("✅ Working Days auto-synced with recent sales data!", icon="🔄")

    edited_working_days = st.data_editor(
        updated_df_working,
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

    st.write("")
    if st.button("Save Manual Changes", type="primary", key="save_wd_btn"):
        with st.spinner("Saving changes..."):
            save_cols = ["Year", "Month", "Working Days", "Worked Days", "Days to Work"]
            save_df = edited_working_days[save_cols].copy()
            
            save_df["Working Days"] = pd.to_numeric(save_df["Working Days"], errors="coerce").fillna(0).astype(int)
            
            manual_worked_list = []
            manual_to_work_list = []
            
            for idx, row in save_df.iterrows():
                y = str(row.get("Year", ""))
                m = str(row.get("Month", ""))
                wd = int(row.get("Working Days", 0))
                
                wkd = worked_days_dict.get((y, m), 0)
                manual_worked_list.append(wkd)
                manual_to_work_list.append(max(0, wd - wkd))
                
            save_df["Worked Days"] = manual_worked_list
            save_df["Days to Work"] = manual_to_work_list
            save_df["Working Days"] = save_df["Working Days"].astype(str)

            ws_working_days.clear()
            set_with_dataframe(ws_working_days, save_df)
            
        msg_placeholder = st.empty()
        msg_placeholder.success("✅ Working days successfully saved!")
        time.sleep(2)
        msg_placeholder.empty()
        st.rerun()