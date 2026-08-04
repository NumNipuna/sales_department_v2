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

    sh = connect_to_sheets()
    try:
        ws_inventory = sh.worksheet("Inventory")
    except gspread.exceptions.WorksheetNotFound:
        ws_inventory = sh.add_worksheet(title="Inventory", rows=3000, cols=15)

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
        st.markdown(f'<div class="section-banner" style="background-color:#052b6c;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

    def styled_table(df, gradient_cols=None, cmap="Blues"):
        if df.empty:
            return df
        
        styler = df.style
        
        if gradient_cols:
            gradient_cols = [c for c in gradient_cols if c in df.columns]
            if gradient_cols:
                styler = styler.background_gradient(subset=gradient_cols, cmap=cmap)
        
        styler = styler.set_table_styles([
            {'selector': 'table', 'props': [
                ('width', '100%'),
                ('border-collapse', 'collapse')
            ]},
            {'selector': 'th', 'props': [
                ('background-color', '#00245e'), 
                ('color', 'white'),              
                ('font-weight', 'bold'),
                ('text-align', 'center'),
                ('border', '1px solid #ADE8F4'),
                ('padding', '10px')
            ]},
            {'selector': 'td', 'props': [
                ('border', '1px solid #ADE8F4'),
                ('padding', '8px'),
                ('text-align', 'center')
            ]},
            {'selector': 'tr:nth-child(even)', 'props': [
                ('background-color', '#F8FDFF')  
            ]},
            {'selector': 'tr:nth-child(odd)', 'props': [
                ('background-color', '#FFFFFF')  
            ]}
        ])
        
        styler = styler.hide(axis="index")
        return styler

    st.markdown("""
        <style>
        div[data-testid="stDateInput"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #03045E !important;
        }
        
        div[data-testid="stDateInput"] div[data-baseweb="input"] {
            border: 2px solid #0096C7 !important; 
            border-radius: 8px !important;        
            background-color: #F8FDFF !important; 
            transition: all 0.3s ease-in-out;     
            padding-left: 5px;
        }
        
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
            border: 2px solid #03045E !important; 
            box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }
        
        div[data-testid="stFileUploader"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 600 !important;
            font-size: 16px !important;
            color: #03045E !important;
        }
        
        div[data-testid="stFileUploaderDropzone"] {
            border: 2px dashed #0096C7 !important; 
            border-radius: 8px !important;
            background-color: #F8FDFF !important; 
            transition: all 0.3s ease-in-out;
        }
        
        div[data-testid="stFileUploaderDropzone"]:hover {
            border: 2px dashed #03045E !important;
            background-color: #EAF8FF !important;
        }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1, 1, 1, 2, 1], vertical_alignment="bottom")
    with col1:
        selected_date = st.date_input("Select Date:", value=datetime.date.today())
        selected_date_str = selected_date.strftime('%Y-%m-%d')
    st.divider()

    col1, col2, col3, col4, col6 = st.columns([1.8, 1, 1, 2, 1], vertical_alignment="bottom")
    with col1:
        section_banner("📦 Update Inventory")

    existing_inventory = get_rows_for_date(selected_date_str)
    
    if not existing_inventory.empty:
        col1, col2 = st.columns([9.3, 1], vertical_alignment="bottom")
        with col1:
            st.warning(f"⚠️ Inventory data already exists for **{selected_date_str}** ({len(existing_inventory)} rows).")
        
        my_styled_table = styled_table(existing_inventory.head(10), gradient_cols=["Available Qty"], cmap="Blues")
        
        st.markdown(my_styled_table.to_html(), unsafe_allow_html=True)
        st.write("") 
        
        if len(existing_inventory) > 10:
            st.caption(f"Showing 10 of {len(existing_inventory)} rows.")

        if st.button("🗑️ Delete inventory data for this date", key="delete_inv_btn"):
            st.session_state["confirm_delete_inv"] = True

        if st.session_state.get("confirm_delete_inv"):
            st.error(f"Permanently delete all {len(existing_inventory)} inventory rows for {selected_date_str}? This cannot be undone.")
            st.markdown("""
                <style>
                div.element-container:has(.delete-target), 
                div.element-container:has(.cancel-target) {
                    display: none;
                }
                
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
                if st.button("✅ Yes, delete it", key="confirm_delete_inv_yes", type="primary"):
                    delete_rows_for_date(selected_date_str)
                    st.session_state["confirm_delete_inv"] = False
                    save_and_refresh(f"🗑️ Inventory data for {selected_date_str} deleted.")
            with c2:
                st.markdown('<span class="cancel-target"></span>', unsafe_allow_html=True)
                if st.button("Cancel", key="confirm_delete_inv_no"):
                    st.session_state["confirm_delete_inv"] = False
                    st.rerun()

    col1, col2, col3, col4, col6 = st.columns([1.8, 1, 1, 2, 1], vertical_alignment="bottom")
    with col1:
        st.info("Upload an updated inventory CSV")
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