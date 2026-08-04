import streamlit as st
from util import fetch_database_records, connect_to_sheets
import pandas as pd
import numpy as np
from gspread_dataframe import set_with_dataframe
import gspread
import datetime
import time

def show():
    st.title("Production Requirement")
    st.write("Welcome, Pradeep...! This is your private area.")
    st.write("Here you can enter data.")
    
    st.sidebar.markdown("---")

    @st.cache_resource(show_spinner=False)
    def get_connection():
        sh = connect_to_sheets()
        return sh
        
    try:
        sh = get_connection()
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        st.stop()

    @st.cache_resource(show_spinner=False)
    def get_or_create_ws(title, rows=3000, cols=15):
        try:
            return sh.worksheet(title)
        except gspread.exceptions.WorksheetNotFound:
            return sh.add_worksheet(title=title, rows=rows, cols=cols)
            
    ws_items = get_or_create_ws("Items_Master")
    ws_forecast = get_or_create_ws("Forecast")

    @st.cache_data(ttl=660, show_spinner=False)
    def _cached_records(_ws, sheet_key):
        return _ws.get_all_records()
        
    def get_records(ws_obj, sheet_key):
        return _cached_records(ws_obj, sheet_key)
        
    def invalidate_sheet_cache():
        _cached_records.clear()
        
    def save_and_refresh(message, seconds=3):
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
            st.error(f"Error fetching Items Master: {e}")
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

    def section_banner(text):
        st.markdown(f'<div class="section-banner" style="background-color:#052b6c;color:white;padding:10px;border-radius:5px;font-weight:bold;">{text}</div>', unsafe_allow_html=True)

    year_options = [str(y) for y in range(2024, 2035)]
    month_options = ["January", "February", "March", "April", "May", "June", "July",
                    "August", "September", "October", "November", "December"]

    section_banner("🎯 Set Monthly Forecast")
    st.caption("Enter the forecast quantity/amount for each item for a given month. "
               "Saving only updates the selected month — other months are kept untouched.")
               
    fc_col1, fc_col2, fc_col3 = st.columns([1, 1, 2], vertical_alignment="bottom")
    with fc_col1:
        forecast_year = st.selectbox("Forecast Year", year_options,
                                    index=year_options.index(str(datetime.date.today().year))
                                    if str(datetime.date.today().year) in year_options else 0,
                                    key="forecast_year_select")
    with fc_col2:
        forecast_month = st.selectbox("Forecast Month", month_options,
                                    index=datetime.date.today().month - 1,
                                    key="forecast_month_select")
                                    
    st.divider()

    items_records = get_records(ws_items, "items")
    df_items_now = pd.DataFrame(items_records) if items_records else pd.DataFrame(columns=["Product Code", "Item Name"])
    
    forecast_records = get_records(ws_forecast, "forecast")
    df_forecast_all = pd.DataFrame(forecast_records) if forecast_records else pd.DataFrame(
        columns=["Year", "Month", "Product Code", "Item Name", "Forecast Qty"])
        
    if not df_forecast_all.empty:
        df_forecast_month = df_forecast_all[
            (df_forecast_all["Year"].astype(str) == str(forecast_year)) &
            (df_forecast_all["Month"].astype(str) == str(forecast_month))
        ][["Product Code", "Forecast Qty"]]
    else:
        df_forecast_month = pd.DataFrame(columns=["Product Code", "Forecast Qty"])
        
    merged_forecast = df_items_now.merge(df_forecast_month, on="Product Code", how="left")
    merged_forecast["Forecast Qty"] = pd.to_numeric(merged_forecast.get("Forecast Qty"), errors="coerce").fillna(0)
    
    st.write("")
    st.info("💡 Upload a CSV or Excel file to auto-fill the forecast. Required columns: 'Product Code', 'Item Name', 'Forecast Qty'.")
    
    # අලුතින් එකතු කළ Template බාගත කිරීමේ බොත්තම (පහසුවෙන් දත්ත පිරවීම සඳහා)
    template_df = merged_forecast[["Product Code", "Item Name", "Forecast Qty"]].copy()
    template_csv = template_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("⬇️ Download Format Template (CSV)", data=template_csv, file_name=f"Forecast_Template_{forecast_year}_{forecast_month}.csv", mime="text/csv")
    
    uploaded_file = st.file_uploader("Upload Forecast File", type=["csv", "xlsx"], key="forecast_uploader")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                uploaded_df = pd.read_csv(uploaded_file)
            else:
                uploaded_df = pd.read_excel(uploaded_file)
            
            if "Product Code" in uploaded_df.columns and "Forecast Qty" in uploaded_df.columns:
                uploaded_df["Product Code"] = uploaded_df["Product Code"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                uploaded_df["Forecast Qty"] = pd.to_numeric(uploaded_df["Forecast Qty"], errors="coerce").fillna(0)
                
                # Dtype mismatch errors වළක්වා ගැනීමට තීරුව Float බවට පත් කිරීම
                merged_forecast["Forecast Qty"] = merged_forecast["Forecast Qty"].astype(float)
                
                # .update() වෙනුවට වඩාත් ආරක්ෂිත Dictionary mapping ක්‍රමය භාවිතා කිරීම
                upload_dict = dict(zip(uploaded_df["Product Code"], uploaded_df["Forecast Qty"]))
                merged_forecast["Forecast Qty"] = merged_forecast.apply(
                    lambda r: upload_dict.get(str(r["Product Code"]), r["Forecast Qty"]), 
                    axis=1
                )
                
                st.success("✅ File data loaded! Check the table below and click 'Save Forecast' to apply changes.")
            else:
                st.error("⚠️ Uploaded file must contain 'Product Code' and 'Forecast Qty' columns.")
        except Exception as e:
            st.error(f"Error processing file: {e}")
            
    dynamic_editor_key = f"forecast_editor_{forecast_year}_{forecast_month}"
    
    # Table එකේ පිළිවෙළ අනිවාර්යයෙන්ම "Product Code", "Item Name", "Forecast Qty" ලෙස සැකසීම
    merged_forecast = merged_forecast[["Product Code", "Item Name", "Forecast Qty"]]
    
    max_val = merged_forecast["Forecast Qty"].max()
    vmax_val = max_val if pd.notna(max_val) and max_val > 0 else 1000

    styled_forecast = merged_forecast.style.background_gradient(
        subset=["Forecast Qty"], 
        cmap="Blues",
        vmin=-100, 
        vmax=vmax_val
    )
    
    edited_forecast = st.data_editor(
        styled_forecast,
        use_container_width=True,
        hide_index=True,
        disabled=["Product Code", "Item Name"],
        key=dynamic_editor_key,
    )

    st.write("")
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