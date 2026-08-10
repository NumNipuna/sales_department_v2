import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

# 'util' එකෙන් අවශ්‍ය Functions Import කරගැනීම
from util import connect_to_sheets, clear_sheet_cache

def show():
    st.markdown("<h2 style='text-align: center; color: #03045E; font-weight: 800;'>📥 Daily Sales Report (DSR)</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #0077B6; font-weight: 600;'>Upload and manage daily cash collections based on location.</p>", unsafe_allow_html=True)
    st.write("")

    # --- 1. SHEET CONNECTION ---
    sh = connect_to_sheets()  # "Sales data" sheet එකට Connect වීම
    try:
        ws_dsr = sh.worksheet("DSR")
    except gspread.exceptions.WorksheetNotFound:
        # DSR Tab එක නැත්නම් අලුතින් සෑදීම
        ws_dsr = sh.add_worksheet(title="DSR", rows=3000, cols=10)

    # --- 2. UNIQUE LOCAL CACHE ---
    @st.cache_data(ttl=600, show_spinner=False)
    def get_local_dsr_data(unique_key):
        try:
            return ws_dsr.get_all_records(default_blank="")
        except Exception:
            return []

    # --- 3. HELPER FUNCTIONS ---
    def save_and_refresh(message, seconds=2):
        clear_sheet_cache()
        get_local_dsr_data.clear() 
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    def get_rows_for_date(date_str):
        records = get_local_dsr_data("DSR_data_cache")
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return pd.DataFrame()
            
        standardized_dates = pd.to_datetime(df["Date"], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df["Date"].astype(str).str.strip())
        
        return df[standardized_dates == date_str]

    def delete_rows_for_date(date_str):
        records = get_local_dsr_data("DSR_data_cache")
        df = pd.DataFrame(records)
        if df.empty or "Date" not in df.columns:
            return
            
        standardized_dates = pd.to_datetime(df["Date"], errors="coerce").dt.strftime('%Y-%m-%d')
        standardized_dates = standardized_dates.fillna(df["Date"].astype(str).str.strip())
            
        remaining = df[standardized_dates != date_str]
        ws_dsr.clear()
        set_with_dataframe(ws_dsr, remaining if not remaining.empty else pd.DataFrame(columns=df.columns))
        
        clear_sheet_cache() 
        get_local_dsr_data.clear()

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
            # 🚀 table-layout: fixed යෙදීමෙන් දකුණු පස ඇති හිස් ඉඩ මකා දමා තීරු සමබරව විහිදුවයි.
            {'selector': 'table', 'props': [('width', '100%'), ('border-collapse', 'collapse'), ('table-layout', 'fixed')]},
            # 🚀 position: sticky යෙදීමෙන් Scroll කිරීමේදී Header එක නොපෙනී යාම වළක්වයි.
            {'selector': 'th', 'props': [('background-color', '#03045E'), ('color', 'white'), ('font-weight', 'bold'), ('text-align', 'center'), ('border', '1px solid #ADE8F4'), ('padding', '10px'), ('position', 'sticky'), ('top', '0'), ('z-index', '2')]},
            {'selector': 'td', 'props': [('border', '1px solid #ADE8F4'), ('padding', '8px'), ('text-align', 'center')]},
            {'selector': 'tr:nth-child(even)', 'props': [('background-color', '#F8FDFF')]},
            {'selector': 'tr:nth-child(odd)', 'props': [('background-color', '#FFFFFF')]}
        ])
        
        styler = styler.hide(axis="index")
        if "Cash Amount" in df.columns:
            styler = styler.format({"Cash Amount": "{:,.2f}"})
        return styler

    # --- 4. STYLING (CSS) ---
    st.markdown("""
        <style>
        /* 🚀 Dashboard එකේ වගේම Page spacing එක හැදීම */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
            min-height: 85vh !important;
        }
        [data-testid="stHeader"] {
            background: transparent !important;
        }
        div[data-testid="stDateInput"] label p { font-family: 'Arial', sans-serif !important; font-weight: 800 !important; font-size: 16px !important; color: #03045E !important; }
        div[data-testid="stDateInput"] div[data-baseweb="input"] { border: 2px solid #0096C7 !important; border-radius: 8px !important; background-color: #F8FDFF !important; transition: all 0.3s ease-in-out; padding-left: 5px; }
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within { border: 2px solid #03045E !important; box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important; }
        div[data-testid="stFileUploader"] label p { font-family: 'Arial', sans-serif !important; font-weight: 800 !important; font-size: 16px !important; color: #03045E !important; }
        div[data-testid="stFileUploaderDropzone"] { border: 2px dashed #0096C7 !important; border-radius: 8px !important; background-color: #F8FDFF !important; transition: all 0.3s ease-in-out; }
        div[data-testid="stFileUploaderDropzone"]:hover { border: 2px dashed #03045E !important; background-color: #EAF8FF !important; }
        div.element-container:has(.delete-target), div.element-container:has(.cancel-target) { display: none; }
        div.element-container:has(.delete-target) + div.element-container button { background-color: #D90429 !important; color: white !important; border: 1px solid #D90429 !important; }
        div.element-container:has(.delete-target) + div.element-container button:hover { background-color: #B20322 !important; border: 1px solid #B20322 !important; color: white !important; }
        div.element-container:has(.cancel-target) + div.element-container button { background-color: #28a745 !important; color: white !important; border: 1px solid #28a745 !important; }
        div.element-container:has(.cancel-target) + div.element-container button:hover { background-color: #218838 !important; border: 1px solid #218838 !important; color: white !important; }
        
        /* Custom Scrollbar for the table */
        .table-wrapper::-webkit-scrollbar { width: 8px; height: 8px; }
        .table-wrapper::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
        .table-wrapper::-webkit-scrollbar-thumb { background: #0096C7; border-radius: 4px; }
        .table-wrapper::-webkit-scrollbar-thumb:hover { background: #03045E; }
        
        /* 🚀 අලුතින් එක් කළ කොටස: Table එක 100% ක් පළලට විහිදීමට */
        .table-wrapper table { width: 100% !important; table-layout: fixed !important; margin: 0 !important; }
        </style>
    """, unsafe_allow_html=True)
    
    # --- 5. MAIN UI ---
    col1, col2, col3 = st.columns([1.8, 1, 3],vertical_alignment="bottom")
    with col1:
        selected_date = st.date_input("Select Date:", value=datetime.date.today())
        selected_date_str = selected_date.strftime('%Y-%m-%d')
    st.divider()

    section_banner("📥 Upload Customer DSR")

    existing_dsr = get_rows_for_date(selected_date_str)
    
    if not existing_dsr.empty:
        # 🚀 "99" කියන Location එක පෙන්වන අවස්ථාවේදීත් ඉවත් කිරීම
        if "Location" in existing_dsr.columns:
            existing_dsr = existing_dsr[existing_dsr["Location"].astype(str).str.strip() != "99"]
            
        st.warning(f"⚠️ DSR data already exists for **{selected_date_str}**.")
        
        my_styled_table = styled_table(existing_dsr, gradient_cols=["Cash Amount"], cmap="Blues")
        
        # 🚀 max-height සහ overflow-y යෙදීමෙන් Scrollable බවට පත් කිරීම
        # 🚀 String එක තනි පේළියකට ගෙන ඒමෙන් Markdown වලදී යටින් එන අනවශ්‍ය </div> අකුරු මැකී යයි.
        table_html = '<div class="table-wrapper" style="max-height: 400px; overflow-y: auto; border-radius: 8px; border: 2px solid #0096C7; background-color: white;">' + my_styled_table.to_html() + '</div>'
        st.markdown(table_html, unsafe_allow_html=True)
        st.write("") 

        if st.button("🗑️ Delete DSR data for this date", key="delete_dsr_btn"):
            st.session_state["confirm_delete_dsr"] = True

        if st.session_state.get("confirm_delete_dsr"):
            st.error(f"Permanently delete DSR records for {selected_date_str}?")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('<span class="delete-target"></span>', unsafe_allow_html=True)
                if st.button("✅ Yes, delete it", key="confirm_delete_dsr_yes"):
                    delete_rows_for_date(selected_date_str)
                    st.session_state["confirm_delete_dsr"] = False
                    save_and_refresh(f"🗑️ DSR data for {selected_date_str} deleted.")
            with c2:
                st.markdown('<span class="cancel-target"></span>', unsafe_allow_html=True)
                if st.button("Cancel", key="confirm_delete_dsr_no"):
                    st.session_state["confirm_delete_dsr"] = False
                    st.rerun()

    else:
        st.info("Upload DSR CSV File. The system will automatically extract Location and Cash Amount.")
        
        if "dsr_uploader_key" not in st.session_state:
            st.session_state["dsr_uploader_key"] = 0
            
        uploaded_file = st.file_uploader(
            "Upload CSV File", 
            type=["csv"], 
            key=f"dsr_uploader_{st.session_state['dsr_uploader_key']}"
        )
        
        if uploaded_file is not None:
            try:
                df_csv = pd.read_csv(uploaded_file)
                
                if len(df_csv.columns) < 10:
                    st.error("⚠️ Uploaded CSV does not have the required columns. It must have at least 10 columns.")
                else:
                    if st.button("Processing and Submit", type="primary", key="dsr_submit"):
                        with st.spinner("Processing Data..."):
                            df_filtered = df_csv.iloc[:, [3, 9]].copy()
                            df_filtered.columns = ["Location", "Cash Amount"]
                            
                            # 🚀 Location එක "99" වන දත්ත මුළුමනින්ම ඉවත් කිරීම
                            df_filtered = df_filtered[df_filtered["Location"].astype(str).str.strip() != "99"]
                            
                            df_filtered["Cash Amount"] = pd.to_numeric(df_filtered["Cash Amount"], errors='coerce').fillna(0)
                            
                            df_grouped = df_filtered.groupby("Location", as_index=False)["Cash Amount"].sum()
                            
                            df_grouped.insert(0, "Date", selected_date_str)
                            
                            all_existing_data = ws_dsr.get_all_values()
                            if not all_existing_data:
                                ws_dsr.append_row(df_grouped.columns.tolist())
                            
                            data_to_upload = df_grouped.values.tolist()
                            ws_dsr.append_rows(data_to_upload)
                        
                        st.session_state["dsr_uploader_key"] += 1
                        save_and_refresh("✅ DSR successfully processed and uploaded!")

            except Exception as e:
                st.error(f"Error processing file: {e}")