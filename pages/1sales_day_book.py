import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

# import util functions
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
    @st.cache_data(ttl=600, show_spinner=False)
    def get_local_sales_data(unique_key):
        try:
            return ws_daily_sales.get_all_records(default_blank="")
        except Exception:
            return []

    # --- 3. HELPER FUNCTIONS ---
    def save_and_refresh(message, seconds=2):
        clear_sheet_cache()
        get_local_sales_data.clear() 
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_date_column(df):
        return "new_date" if "new_date" in df.columns else "Date"

    def get_rows_for_date(date_str):
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
        get_local_sales_data.clear()

    def section_banner(text):
        st.markdown(f'<div class="section-banner" style="background-color:#052b6c;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

    def styled_table(df, gradient_cols=None, cmap="Blues"):
        if df.empty:
            return df
        
        styler = df.style
        
        # apply gradient only to specified columns if they exist in the DataFrame
        if gradient_cols:
            gradient_cols = [c for c in gradient_cols if c in df.columns]
            if gradient_cols:
                styler = styler.background_gradient(subset=gradient_cols, cmap=cmap)
        
        # custom CSS for the table
        styler = styler.set_table_styles([
            # 100% width and border collapse for the table
            {'selector': 'table', 'props': [
                ('width', '100%'),
                ('border-collapse', 'collapse')
            ]},
            # table header cells
            {'selector': 'th', 'props': [
                ('background-color', '#00245e'), 
                ('color', 'white'),              
                ('font-weight', 'bold'),
                ('text-align', 'center'),
                ('border', '1px solid #ADE8F4'),
                ('padding', '10px')
            ]},
            # Table Data Cells
            {'selector': 'td', 'props': [
                ('border', '1px solid #ADE8F4'),
                ('padding', '8px'),
                ('text-align', 'center')
            ]},
            # Even rows background color (light blue)
            {'selector': 'tr:nth-child(even)', 'props': [
                ('background-color', '#F8FDFF')  
            ]},
            # Odd rows background color (white)
            {'selector': 'tr:nth-child(odd)', 'props': [
                ('background-color', '#FFFFFF')  
            ]}
        ])
        
        # Hide the index column for a cleaner look
        styler = styler.hide(axis="index")

        return styler

    # --- 4. MAIN UI LOGIC ---
    # --- Custom CSS for Date Input Box ---
    st.markdown("""
        <style>
        /* Select date font and style */
        div[data-testid="stDateInput"] label p {
            font-family: 'Arial', sans-serif !important; /* Select font */
            font-weight: 600 !important; /* Bold */
            font-size: 16px !important; /* font size */
            color: #03045E !important; /* font color */
        }
        
        /* Date Input Box border and background */
        div[data-testid="stDateInput"] div[data-baseweb="input"] {
            border: 2px solid #0096C7 !important; 
            border-radius: 8px !important;        
            background-color: #F8FDFF !important; 
            transition: all 0.3s ease-in-out;     
            padding-left: 5px;
        }
        
        /* Box Clicked color */
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
            border: 2px solid #03045E !important; 
            box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }
        
        /* 'Upload CSV File' */
        div[data-testid="stFileUploader"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #03045E !important;
        }
        
        /* dropzone */
        div[data-testid="stFileUploaderDropzone"] {
            border: 2px dashed #0096C7 !important; 
            border-radius: 8px !important;
            background-color: #F8FDFF !important; 
            transition: all 0.3s ease-in-out;
        }
        
        /* dark color when hovered */
        div[data-testid="stFileUploaderDropzone"]:hover {
            border: 2px dashed #03045E !important;
            background-color: #EAF8FF !important;
        }
        /* 👆 ----------------------------------- 👆 */
        </style>
    """, unsafe_allow_html=True)
    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1, 1, 1, 2,1], vertical_alignment="bottom")
    with col1:
        selected_date = st.date_input("Select Date:", value=datetime.date.today())
        selected_date_str = selected_date.strftime('%Y-%m-%d')
    st.divider()

    col1, col2, col3, col4, col6 = st.columns([1.8, 1, 1,2,1], vertical_alignment="bottom")
    with col1:
        section_banner("📤 Upload Daily Sales CSV")

    existing_sales = get_rows_for_date(selected_date_str)
    
    if not existing_sales.empty:
        col1, col2 = st.columns([9.3,1], vertical_alignment="bottom")
        with col1:
            st.warning(f"⚠️ Sales data already exists for **{selected_date_str}** ({len(existing_sales)} rows).")
        
        # Render the styled table with gradient for "Qty" and "Amount" columns
        my_styled_table = styled_table(existing_sales.head(10), gradient_cols=["Qty", "Amount"], cmap="Blues")
        
        st.markdown(my_styled_table.to_html(), unsafe_allow_html=True)
        st.write("") # Add a small space after the table for better visual separation
        
        if len(existing_sales) > 10:
            st.caption(f"Showing 10 of {len(existing_sales)} rows.")

        if st.button("🗑️ Delete sales data for this date", key="delete_sales_btn"):
            st.session_state["confirm_delete_sales"] = True

        if st.session_state.get("confirm_delete_sales"):
            st.error(f"Permanently delete all {len(existing_sales)} sales rows for {selected_date_str}? This cannot be undone.")
            st.markdown("""
                <style>
                /* Hide the delete and cancel buttons */
                div.element-container:has(.delete-target), 
                div.element-container:has(.cancel-target) {
                    display: none;
                }
                
                /* Delete button styling */
                div.element-container:has(.delete-target) + div.element-container button {
                    background-color: #D90429 !important;
                    color: white !important;
                    border: 1px solid #D90429 !important;
                }
                div.element-container:has(.delete-target) + div.element-container button:hover {
                    background-color: #B20322 !important;
                    border: 1px solid #B20322 !important;
                    color: white !important;
                }
                
                /* Cancel button styling */
                div.element-container:has(.cancel-target) + div.element-container button {
                    background-color: #28a745 !important;
                    color: white !important;
                    border: 1px solid #28a745 !important;
                }
                div.element-container:has(.cancel-target) + div.element-container button:hover {
                    background-color: #218838 !important;
                    border: 1px solid #218838 !important;
                    color: white !important;
                }
                </style>
            """, unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 1, 7], vertical_alignment="bottom")
            with c1:
                st.markdown('<span class="delete-target"></span>', unsafe_allow_html=True)
                if st.button("✅ Yes, delete it", key="confirm_delete_sales_yes", type="primary"):
                    delete_rows_for_date(selected_date_str)
                    st.session_state["confirm_delete_sales"] = False
                    save_and_refresh(f"🗑️ Sales data for {selected_date_str} deleted.")
            with c2:
                st.markdown('<span class="cancel-target"></span>', unsafe_allow_html=True)
                if st.button("Cancel", key="confirm_delete_sales_no"):
                    st.session_state["confirm_delete_sales"] = False
                    st.rerun()

    col1, col2, col3, col4, col6 = st.columns([1.8, 1, 1,2,1], vertical_alignment="bottom")
    with col1:
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