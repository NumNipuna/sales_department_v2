import streamlit as st
import pandas as pd
import datetime
import time
from gspread_dataframe import set_with_dataframe
import gspread

from util import connect_to_sheets, clear_sheet_cache

def show():
    # --- CSS Styling (Theme එකට ගැලපෙන ලෙස) ---
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
        /* Hide number input arrows (+ / -) */
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
    st.markdown("<p style='text-align: center; color: #0077B6; font-weight: 600;'>Manage collections, bank deposits, and cash in hand per route.</p>", unsafe_allow_html=True)
    st.write("")

    # --- 1. SHEET CONNECTION ---
    sh = connect_to_sheets()  # "Sales data" sheet
    
    # DSR Data Load කරගැනීම
    @st.cache_data(ttl=300, show_spinner=False)
    def get_dsr_data():
        try:
            ws_dsr = sh.worksheet("DSR")
            return pd.DataFrame(ws_dsr.get_all_records(default_blank=""))
        except:
            return pd.DataFrame()

    # අලුත් Headers සහිත Cash Collection Sheet එක සෑදීම හෝ Load කරගැනීම
    new_headers = ["Date", "Route", "Total Cash Collection", "Deposit Date", "Remark", "Status", "Amount", "Index", "Balance"]
    try:
        ws_cc = sh.worksheet("Cash_Collection")
        all_data = ws_cc.get_all_values()
        if not all_data:
            ws_cc.append_row(new_headers)
        elif all_data[0] != new_headers:
            # Header එක අලුත් එක නොවේ නම් ඉබේම අලුත් Header එක 1 වෙනි පේළියට දැමීම
            ws_cc.insert_row(new_headers, index=1)
    except gspread.exceptions.WorksheetNotFound:
        ws_cc = sh.add_worksheet(title="Cash_Collection", rows=3000, cols=9)
        ws_cc.append_row(new_headers)

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
    
    # අදාළ දිනයට ඇති Route ලැයිස්තුව ලබා ගැනීම
    available_routes = []
    if not df_dsr.empty and "Date" in df_dsr.columns and "Location" in df_dsr.columns:
        dsr_filtered = df_dsr[df_dsr["Date"].astype(str) == selected_date_str]
        available_routes = dsr_filtered["Location"].dropna().unique().tolist()
        available_routes = sorted([str(r) for r in available_routes if str(r).strip() != ""])

    with col2:
        if not available_routes:
            selected_route = st.selectbox("Select Route:", ["No data available for this date"], disabled=True)
        else:
            selected_route = st.selectbox("Select Route:", ["-- Select --"] + available_routes)

    # Route එක තේරූ පසු Total Cash එක සෙවීම
    total_cash = 0.0
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available for this date":
        route_data = dsr_filtered[dsr_filtered["Location"].astype(str) == selected_route]
        if "Cash Amount" in route_data.columns:
            # කොමා ඉවත් කර සංඛ්‍යාවක් බවට පත් කිරීම
            route_data["Cash Amount"] = pd.to_numeric(route_data["Cash Amount"].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            total_cash = route_data["Cash Amount"].sum()

    with col3:
        # Total Cash Collection එක පැහැදිලිව පෙන්වීම
        st.markdown(f"""
            <div style="background-color: #03045E; padding: 10px; border-radius: 8px; text-align: center; border: 2px solid #00B4D8;">
                <span style="color: #90E0EF; font-size: 13px; font-weight: bold;">TOTAL CASH COLLECTION</span><br>
                <span style="color: #FFFFFF; font-size: 20px; font-weight: 900;">Rs. {total_cash:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)

    st.divider()

    # --- 3. DATA ENTRY SECTION ---
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available for this date":
        
        # Fast entry සඳහා Form එකක් භාවිතා කිරීම
        with st.form("cash_collection_form", clear_on_submit=True):
            st.markdown("<h4 style='color: #0077B6; margin-bottom: 15px;'>📝 Enter Collection Details</h4>", unsafe_allow_html=True)
            
            f_col1, f_col2, f_col3 = st.columns(3)
            
            with f_col1:
                deposit_date = st.date_input("Deposit Date", value=datetime.date.today())
            with f_col2:
                remark_selected = st.selectbox("Remark", ["BOC", "COM", "Head office"])
            with f_col3:
                # step=None භාවිතයෙන් +/- ඊතල සම්පූර්ණයෙන්ම ඉවත් කර ඇත
                amount_entered = st.number_input("Amount", min_value=0.0, format="%.2f", value=None, placeholder="Enter Amount", step=None)

            # Form submit button
            submit_btn = st.form_submit_button("💾 Save Collection Data", type="primary", use_container_width=True)

            if submit_btn:
                amount = amount_entered if amount_entered is not None else 0.0
                
                # Validation: Amount එක අනිවාර්ය වීම
                if amount == 0:
                    st.error("⚠️ අනිවාර්යයෙන්ම 'Amount' අගයක් ඇතුළත් කළ යුතුයි.")
                else:
                    with st.spinner("Generating Index and Saving..."):
                        # Status තීරුව තීරණය කිරීම
                        status_val = "Cash" if remark_selected == "Head office" else "Bank"
                        
                        df_cc = get_cc_data()
                        
                        # Cumulative Balance එක ගණනය කිරීම
                        past_tot_col, past_tot_amt = 0, 0
                        has_past_records = False
                        
                        if not df_cc.empty and "Date" in df_cc.columns and "Route" in df_cc.columns:
                            mask_bal = (df_cc["Date"].astype(str) == selected_date_str) & (df_cc["Route"].astype(str) == selected_route)
                            past_records_bal = df_cc[mask_bal]
                            
                            if len(past_records_bal) > 0:
                                has_past_records = True
                                
                            if "Total Cash Collection" in df_cc.columns:
                                past_tot_col = pd.to_numeric(past_records_bal["Total Cash Collection"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                            if "Amount" in df_cc.columns:
                                past_tot_amt = pd.to_numeric(past_records_bal["Amount"].astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                            
                        # අදාළ දිනයට සහ Route එකට පළමු වාර්තාව නම් පමණක් Total Cash Collection අගය යොදන්න (නැත්නම් 0)
                        final_total_cash = 0.0 if has_past_records else total_cash
                            
                        balance = (past_tot_col + final_total_cash) - (past_tot_amt + amount)

                        # --- INDEX GENERATION LOGIC ---
                        next_num = 1
                        if not df_cc.empty and "Date" in df_cc.columns and "Route" in df_cc.columns and "Remark" in df_cc.columns:
                            # Index එක මාසෙන් මාසෙට Reset වීමට අදාළ මාසය සහ වර්ෂය වෙන් කරගැනීම
                            df_cc["ParsedDate"] = pd.to_datetime(df_cc["Date"], errors='coerce')
                            current_month = selected_date.month
                            current_year = selected_date.year
                            
                            # එම Route එකට, අදාළ Remark එකට සහ අදාළ මාසයට/වර්ෂයට අදාළ පෙර දත්ත සෙවීම
                            mask_idx = (
                                (df_cc["Route"].astype(str) == selected_route) & 
                                (df_cc["Remark"].astype(str) == remark_selected) & 
                                (df_cc["ParsedDate"].dt.month == current_month) & 
                                (df_cc["ParsedDate"].dt.year == current_year)
                            )
                            past_records_idx = df_cc[mask_idx]
                            next_num = len(past_records_idx) + 1
                        
                        # Index එක Format කිරීම (උදා: BOC 01, Head office 01)
                        entry_index = f"{remark_selected} {next_num:02d}"

                        # අලුත් පේළිය සැකසීම
                        new_row = [
                            selected_date_str,
                            selected_route,
                            final_total_cash,
                            deposit_date.strftime('%Y-%m-%d'),
                            remark_selected,
                            status_val,
                            amount,
                            entry_index,
                            balance
                        ]
                        
                        # Google Sheet එකට සේව් කිරීම
                        ws_cc.append_row(new_row)
                        
                        # Cache Clear කිරීම
                        clear_sheet_cache()
                        get_cc_data.clear()
                        
                    st.success(f"✅ Data Saved Successfully! Generated Index: **{entry_index}** | Balance: **{balance:,.2f}**")
                    time.sleep(2.0)
                    st.rerun()

    # --- 4. RECENT ENTRIES TABLE ---
    st.write("")
    if selected_route and selected_route != "-- Select --" and selected_route != "No data available for this date":
        st.markdown(f"<h4 style='color: #03045E;'>📋 Cash Collections for Route: {selected_route}</h4>", unsafe_allow_html=True)
        
        df_cc_show = get_cc_data()
        if not df_cc_show.empty and "Date" in df_cc_show.columns and "Route" in df_cc_show.columns:
            # Filter Only by Selected Date and Route (Entry order එකටම තබා ඇත)
            df_cc_show = df_cc_show[
                (df_cc_show["Date"].astype(str) == selected_date_str) & 
                (df_cc_show["Route"].astype(str) == selected_route)
            ].copy()
            
            if not df_cc_show.empty:
                # අවසාන Balance එක ගණනය කිරීම
                tot_col = pd.to_numeric(df_cc_show.get("Total Cash Collection", pd.Series([0])).astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                tot_amt = pd.to_numeric(df_cc_show.get("Amount", pd.Series([0])).astype(str).str.replace(',', ''), errors='coerce').fillna(0).sum()
                final_display_bal = tot_col - tot_amt
                
                # 0 අගයන් හිස් (Empty) බවට පත් කිරීමේ Function එක
                def fmt_currency(x):
                    try:
                        v = float(str(x).replace(',', ''))
                        if v == 0: return ""
                        return f"{v:,.2f}"
                    except:
                        return ""
                
                for col in ["Total Cash Collection", "Amount"]:
                    if col in df_cc_show.columns:
                        df_cc_show[col] = df_cc_show[col].apply(fmt_currency)
                
                # Balance තීරුවේ යටම පේළියට පමණක් අගය ලබා දීම, ඉතුරු ඒවා හිස් කිරීම
                if "Balance" in df_cc_show.columns:
                    balances = [""] * len(df_cc_show)
                    balances[-1] = fmt_currency(final_display_bal)
                    df_cc_show["Balance"] = balances
                
                # Table 100% පළලට සැකසීම
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