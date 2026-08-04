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

    @st.cache_data(ttl=300, show_spinner=False)
    def _cached_records(_ws, sheet_key):
        return _ws.get_all_records()

    def get_records(ws_obj, sheet_key):
        return _cached_records(ws_obj, sheet_key)

    def invalidate_sheet_cache():
        _cached_records.clear()

    def save_and_refresh(message, seconds=2):
        invalidate_sheet_cache()
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    MONTH_OPTIONS = ["2026-Jan", "2026-Feb", "2026-Mar", "2026-Apr",
                     "2026-May", "2026-Jun", "2026-Jul", "2026-Aug",
                     "2026-Sep", "2026-Oct", "2026-Nov", "2026-Dec",
                     "2027-Jan", "2027-Feb", "2027-Mar", "2027-Apr",
                     "2027-May", "2027-Jun", "2027-Jul", "2027-Aug",
                     "2027-Sep", "2027-Oct", "2027-Nov", "2027-Dec"]

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

    section_banner("🎯 Set Rep Target")
    st.caption("Manage representative targets. Upload an Excel/CSV file or enter manually.")
    
    current_month_str = datetime.date.today().strftime("%Y-%b")
    default_month_index = (MONTH_OPTIONS.index(current_month_str)
                           if current_month_str in MONTH_OPTIONS else 0)
    
    col1, col2 = st.columns([1, 3], vertical_alignment="bottom")
    with col1:
        month = st.selectbox("Select Month", MONTH_OPTIONS, index=default_month_index, key="month_select")
        
    st.divider()

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

    st.write("")
    st.info("💡 Upload an Excel or CSV file to auto-fill the target. Ensure it has 'No' and 'Target' columns.")
    
    # අලුතින් එකතු කළ Template බාගත කිරීමේ බොත්තම
    template_df = df_editable[["No", "Manager", "Route", "Representative", "Status", "Target"]].copy()
    template_csv = template_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button("⬇️ Download Format Template (CSV)", data=template_csv, file_name=f"Rep_Target_Template_{month}.csv", mime="text/csv")

    uploaded_file = st.file_uploader("Upload Target File", type=["csv", "xlsx"], key="target_uploader")
    
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                uploaded_df = pd.read_csv(uploaded_file)
            else:
                uploaded_df = pd.read_excel(uploaded_file)
            
            if "No" in uploaded_df.columns and "Target" in uploaded_df.columns:
                uploaded_df["No"] = uploaded_df["No"].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                uploaded_df["Target"] = pd.to_numeric(uploaded_df["Target"], errors="coerce").fillna(0)
                
                df_editable["No"] = df_editable["No"].astype(str).str.strip()
                
                # Dtype mismatch errors වළක්වා ගැනීමට තීරුව Float බවට පත් කිරීම
                df_editable["Target"] = df_editable["Target"].astype(float)
                
                # .update() වෙනුවට වඩාත් ආරක්ෂිත Dictionary mapping ක්‍රමය භාවිතා කිරීම
                upload_dict = dict(zip(uploaded_df["No"], uploaded_df["Target"]))
                df_editable["Target"] = df_editable.apply(
                    lambda r: upload_dict.get(str(r["No"]), r["Target"]), 
                    axis=1
                )
                
                st.success("✅ File data loaded! Check the table below and click 'Save this month Target' to apply changes.")
            else:
                st.error("⚠️ Uploaded file must contain 'No' and 'Target' columns.")
        except Exception as e:
            st.error(f"Error processing file: {e}")

    # Table එකේ පිළිවෙළ අනිවාර්යයෙන්ම ඔයා ඉල්ලපු ආකාරයට සැකසීම
    df_editable = df_editable[["No", "Manager", "Route", "Representative", "Status", "Target"]]

    max_val = df_editable["Target"].max()
    vmax_val = max_val if pd.notna(max_val) and max_val > 0 else 100000

    styled_df = df_editable.style.background_gradient(
        subset=["Target"], 
        cmap="Blues",
        vmin=-100, 
        vmax=vmax_val
    )

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
        styled_df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=500,
        key=dynamic_editor_key,
    )

    st.write("")
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