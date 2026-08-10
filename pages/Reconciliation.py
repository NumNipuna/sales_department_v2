import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

from util import connect_to_sheets, clear_sheet_cache

def show():
    # --- CSS Styling ---
    st.markdown("""
        <style>
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
            min-height: 85vh !important;
        }
        [data-testid="stHeader"] { background: transparent !important; }
        
        div[data-testid="stDateInput"] label p, div[data-testid="stSelectbox"] label p, div[data-testid="stNumberInput"] label p {
            font-family: 'Arial', sans-serif !important;
            font-weight: 800 !important;
            font-size: 15px !important;
            color: #03045E !important;
        }
        div[data-baseweb="input"], div[data-baseweb="select"] {
            border: 2px solid #0096C7 !important; 
            border-radius: 8px !important;        
            background-color: #F8FDFF !important; 
        }
        div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within {
            border: 2px solid #03045E !important; 
            box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }
        
        /* 🚀 Hide number input arrows (+ / -) */
        input[type="number"]::-webkit-inner-spin-button, 
        input[type="number"]::-webkit-outer-spin-button { 
            -webkit-appearance: none; 
            margin: 0; 
        }
        input[type="number"] {
            -moz-appearance: textfield;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 style='text-align: center; color: #03045E; font-weight: 800;'>💰 Daily Cash Collection</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #0077B6; font-weight: 600;'>Manage bank deposits and cash balances per route.</p>", unsafe_allow_html=True)
    st.write("")

    # --- 1. SHEET CONNECTION ---
    sh = connect_to_sheets()
    
    @st.cache_data(ttl=300, show_spinner=False)
    def get_dsr_data():
        try:
            ws_dsr = sh.worksheet("DSR")
            return pd.DataFrame(ws_dsr.get_all_records(default_blank=""))
        except:
            return pd.DataFrame()

    headers = ["Date", "Route", "Total Cash Collection", "Cash Deposit", "Deposit Date", "Bank", "Bank Index", "Cash in Hand", "Balance"]
    try:
        ws_cc = sh.worksheet("Cash_Collection")
        all_data = ws_cc.get_all_values()
        if not all_data:
            ws_cc.append_row(headers)
        elif all_data[0] != headers:
            ws_cc.insert_row(headers, index=1)
    except gspread.exceptions.WorksheetNotFound:
        ws_cc = sh.add_worksheet(title="Cash_Collection", rows=3000, cols=10)
        ws_cc.append_row(headers)

    @st.cache_data(ttl=10, show_spinner=False)
    def get_cc_data():
        try:
            return pd.DataFrame(ws_cc.get_all_records(default_blank=""))
        except:
            return pd.DataFrame()

    # --- 2. MAIN UI: FILTERING ---
    df_dsr = get_dsr_data()
    
    col1, col2, col3 = st.columns([1.5, 2, 2], vertical_alignment="bottom")
    with col1:
        selected_date = st.date_input("Filter Date:", value=datetime.date.today())
        selected_date_str = selected_date.strftime('%Y-%m-%d')
    
    available_routes = []
    if not df_dsr.empty and "Date" in df_dsr.columns and "Location" in df_dsr.columns:
        dsr_filtered = df_dsr[df_dsr["Date"].astype(str) == selected_date_str]
        available_routes = dsr_filtered["Location"].dropna().unique().tolist()
        available_routes = sorted([str(r) for r in available_routes if str(r).strip() != ""])

    with col2:
        if not available_routes:
            selected_route = st.selectbox("Select Route:", ["No data available"], disabled=True)
        else:
            selected_route = st.selectbox("Select Route:", ["-- Select --"] + available_routes)

    total_cash = 0.0
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available":
        route_data = dsr_filtered[dsr_filtered["Location"].astype(str) == selected_route]
        if "Cash Amount" in route_data.columns:
            route_data["Cash Amount"] = pd.to_numeric(route_data["Cash Amount"].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            total_cash = route_data["Cash Amount"].sum()

    with col3:
        st.markdown(f"""
            <div style="background-color: #03045E; padding: 10px; border-radius: 8px; text-align: center; border: 2px solid #00B4D8;">
                <span style="color: #90E0EF; font-size: 13px; font-weight: bold;">TOTAL CASH COLLECTION</span><br>
                <span style="color: #FFFFFF; font-size: 20px; font-weight: 900;">Rs. {total_cash:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- 3. DATA ENTRY SECTION ---
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available":
        
        with st.form("cash_collection_form", clear_on_submit=True):
            st.markdown("<h4 style='color: #0077B6; margin-bottom: 15px;'>📝 Enter Deposit Details</h4>", unsafe_allow_html=True)
            
            f_col1, f_col2, f_col3, f_col4 = st.columns(4)
            
            with f_col1:
                # step=None භාවිතයෙන් +/- ඊතල ඉවත් කිරීම
                cash_deposit = st.number_input("Cash Deposit", min_value=0.0, format="%.2f", value=None, placeholder="Amount", step=None)
            with f_col2:
                deposit_date = st.date_input("Deposit Date", value=datetime.date.today())
            with f_col3:
                bank_selected = st.selectbox("Bank", ["BOC", "COM"])
            with f_col4:
                cash_in_hand = st.number_input("Cash in Hand", min_value=0.0, format="%.2f", value=None, placeholder="Amount", step=None)

            submit_btn = st.form_submit_button("💾 Save Collection Data", type="primary", use_container_width=True)

            if submit_btn:
                deposit_date_str = deposit_date.strftime('%Y-%m-%d')
                actual_deposit = cash_deposit if cash_deposit is not None else 0.0
                actual_in_hand = cash_in_hand if cash_in_hand is not None else 0.0
                
                # 🚀 Validation: Cash Deposit හෝ Cash in hand දෙකෙන් එකක් අනිවාර්ය වීම
                if actual_deposit == 0 and actual_in_hand == 0:
                    st.error("⚠️ අනිවාර්යයෙන්ම 'Cash Deposit' හෝ 'Cash in Hand' අගයක් ඇතුළත් කළ යුතුයි.")
                else:
                    if selected_date_str == deposit_date_str:
                        final_total_cash = total_cash
                    else:
                        final_total_cash = 0.0
                    
                    with st.spinner("Generating Index and Saving..."):
                        df_cc = get_cc_data()
                        
                        # 🚀 Cumulative Balance එක ගණනය කිරීම
                        past_tot_col, past_tot_dep, past_tot_hand = 0, 0, 0
                        if not df_cc.empty:
                            mask_bal = (df_cc["Date"].astype(str) == selected_date_str) & (df_cc["Route"].astype(str) == selected_route)
                            past_records_bal = df_cc[mask_bal]
                            past_tot_col = pd.to_numeric(past_records_bal["Total Cash Collection"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                            past_tot_dep = pd.to_numeric(past_records_bal["Cash Deposit"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                            past_tot_hand = pd.to_numeric(past_records_bal["Cash in Hand"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                            
                        balance = (past_tot_col + final_total_cash) - (past_tot_dep + actual_deposit) - (past_tot_hand + actual_in_hand)

                        # 🚀 Index එක ගණනය කිරීම
                        next_num = 1
                        if not df_cc.empty and "Date" in df_cc.columns and "Route" in df_cc.columns and "Bank" in df_cc.columns:
                            df_cc["ParsedDate"] = pd.to_datetime(df_cc["Date"], errors='coerce')
                            current_month = selected_date.month
                            current_year = selected_date.year
                            
                            mask_idx = (
                                (df_cc["Route"].astype(str) == selected_route) & 
                                (df_cc["Bank"].astype(str) == bank_selected) & 
                                (df_cc["ParsedDate"].dt.month == current_month) & 
                                (df_cc["ParsedDate"].dt.year == current_year)
                            )
                            past_records_idx = df_cc[mask_idx]
                            next_num = len(past_records_idx) + 1
                        
                        bank_index = f"{bank_selected} {next_num:02d}"

                        new_row = [
                            selected_date_str,
                            selected_route,
                            final_total_cash, 
                            actual_deposit,
                            deposit_date_str,
                            bank_selected,
                            bank_index,
                            actual_in_hand,
                            balance
                        ]
                        
                        ws_cc.append_row(new_row)
                        
                        clear_sheet_cache()
                        get_cc_data.clear()
                        
                    st.success(f"✅ Data Saved! Index: **{bank_index}**")
                    time.sleep(2.0)
                    st.rerun()

    # --- 4. RECENT ENTRIES TABLE ---
    st.write("")
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available":
        st.markdown(f"<h4 style='color: #03045E;'>📋 Cash Collections for Route: {selected_route}</h4>", unsafe_allow_html=True)
        
        df_cc_show = get_cc_data()
        if not df_cc_show.empty:
            # 🚀 Filter Only by Selected Date and Route (Entry order එකටම තබා ඇත)
            df_cc_show = df_cc_show[
                (df_cc_show["Date"].astype(str) == selected_date_str) & 
                (df_cc_show["Route"].astype(str) == selected_route)
            ].copy()
            
            if not df_cc_show.empty:
                # 🚀 අවසාන Balance එක ගණනය කිරීම
                tot_col = pd.to_numeric(df_cc_show["Total Cash Collection"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                tot_dep = pd.to_numeric(df_cc_show["Cash Deposit"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                tot_hand = pd.to_numeric(df_cc_show["Cash in Hand"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                final_display_bal = tot_col - tot_dep - tot_hand
                
                # 🚀 0 අගයන් හිස් (Empty) බවට පත් කිරීමේ Function එක
                def fmt_currency(x):
                    try:
                        v = float(str(x).replace(',', ''))
                        if v == 0: return ""
                        return f"{v:,.2f}"
                    except:
                        return ""
                
                for col in ["Total Cash Collection", "Cash Deposit", "Cash in Hand"]:
                    if col in df_cc_show.columns:
                        df_cc_show[col] = df_cc_show[col].apply(fmt_currency)
                
                # 🚀 Balance තීරුවේ යටම පේළියට පමණක් අගය ලබා දීම, ඉතුරු ඒවා හිස් කිරීම
                balances = [""] * len(df_cc_show)
                balances[-1] = fmt_currency(final_display_bal)
                df_cc_show["Balance"] = balances
                
                # 🚀 Table 100% පළලට සැකසීම
                styler = df_cc_show.style.set_table_styles([
                    {'selector': 'table', 'props': [('width', '100%'), ('border-collapse', 'collapse')]},
                    {'selector': 'th', 'props': [('background-color', '#0077B6'), ('color', 'white'), ('text-align', 'center'), ('padding', '8px')]},
                    {'selector': 'td', 'props': [('border', '1px solid #ADE8F4'), ('padding', '6px'), ('text-align', 'center')]},
                ]).hide(axis="index")
                
                st.markdown(f'<div style="border: 2px solid #0096C7; border-radius: 8px; overflow: hidden; width: 100%;">{styler.to_html()}</div>', unsafe_allow_html=True)
            else:
                st.info("No cash collection records found for the selected Date and Route.")
        else:
            st.info("No cash collection records found.")
    else:
        st.info("Please select a Route to view records.")

if __name__ == "__main__":
    show()