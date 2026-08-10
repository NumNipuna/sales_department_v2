import streamlit as st
import calendar
import re
import time
import base64
import datetime
import gspread
import numpy as np
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

def show():
    # ============================================================
    # 1. CONNECTION
    # ============================================================
    SCOPE = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    @st.cache_resource
    def get_client():
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "service_account.json", SCOPE
        )
        return gspread.authorize(creds)

    @st.cache_resource
    def get_sheets():
        client = get_client()
        sheet1 = client.open("Sales data")
        sheet2 = client.open("Sales data2")
        return sheet1, sheet2

    # ============================================================
    # 2. LOAD RAW DATA (cached, refreshed based on ttl)
    # ============================================================
    @st.cache_data(ttl=600, show_spinner=False)
    def load_raw_data():
        sheet1, sheet2 = get_sheets()

        working_days_ws = sheet1.worksheet("Working_Days")
        sales_day_book_ws = sheet2.worksheet("Sales_day_book") 
        inventory_ws = sheet1.worksheet("Inventory")
        items_master_ws = sheet1.worksheet("Items_Master")
        forecast_ws = sheet1.worksheet("Forecast")

        working_days_df = pd.DataFrame(working_days_ws.get_all_records())
        sales_day_book_df = pd.DataFrame(sales_day_book_ws.get_all_records())
        inventory_df = pd.DataFrame(inventory_ws.get_all_records())
        items_master_df = pd.DataFrame(items_master_ws.get_all_records())
        forecast_df = pd.DataFrame(forecast_ws.get_all_records())

        return working_days_df, sales_day_book_df, inventory_df, items_master_df, forecast_df

    def clear_raw_cache():
        st.cache_data.clear()

    def save_and_refresh(message, seconds=2):
        clear_raw_cache()
        msg_placeholder = st.empty()
        msg_placeholder.success(message)
        time.sleep(seconds)
        msg_placeholder.empty()
        st.rerun()

    # ============================================================
    # 3. CALCULATION
    # ============================================================
    def safe_float(val):
        if pd.isna(val) or val is None: 
            return 0.0
        if isinstance(val, (int, float)): 
            return float(val)
        
        val_str = str(val).strip()
        if val_str == "-" or val_str == "":
            return 0.0
            
        cleaned = re.sub(r'[^\d.-]', '', val_str)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def build_master_table(selected_date_str: str):
        working_days, sales_day_book, inventory, items_master, forecast = load_raw_data()

        select_date_obj = pd.to_datetime(selected_date_str)
        selected_year = select_date_obj.year
        selected_month = select_date_obj.strftime("%B")

        working_days_filtered = working_days[
            (working_days["Year"].astype(str) == str(selected_year))
            & (working_days["Month"].astype(str) == str(selected_month))
        ]
        
        working_days_value = 1.0
        if not working_days_filtered.empty:
            working_days_value = safe_float(working_days_filtered["Working Days"].iloc[0])
            if working_days_value == 0: working_days_value = 1.0

        date_col = "New_date" if "New_date" in sales_day_book.columns else "new_date" if "new_date" in sales_day_book.columns else "Date"
        if date_col in sales_day_book.columns:
            sales_day_book["Parsed_Date_Obj"] = pd.to_datetime(sales_day_book[date_col], errors="coerce")
            daily_sale_filtered = sales_day_book[
                (sales_day_book["Parsed_Date_Obj"].dt.year == selected_year) &
                (sales_day_book["Parsed_Date_Obj"].dt.month == select_date_obj.month) &
                (sales_day_book["Parsed_Date_Obj"] <= select_date_obj)
            ].copy()
        else:
            daily_sale_filtered = pd.DataFrame()

        inventory_filtered = inventory[inventory["Date"].astype(str) == selected_date_str].copy()
        if "Available Qty" in inventory_filtered.columns:
            inventory_filtered["Available Qty"] = inventory_filtered["Available Qty"].apply(safe_float)

        forecast_filtered = forecast[
            (forecast["Year"].astype(str) == str(selected_year)) & (forecast["Month"].astype(str) == str(selected_month))
        ].copy()
        if "Forecast Qty" in forecast_filtered.columns:
            forecast_filtered["Forecast Qty"] = forecast_filtered["Forecast Qty"].apply(safe_float)

        if not daily_sale_filtered.empty and "Item" in daily_sale_filtered.columns:
            if "Qty" not in daily_sale_filtered.columns:
                daily_sale_filtered["Qty"] = 0.0
            daily_sale_filtered["Qty"] = daily_sale_filtered["Qty"].apply(safe_float)
            sale_qty_grouped = daily_sale_filtered.groupby("Item")["Qty"].sum().reset_index()
            sale_qty = pd.merge(items_master, sale_qty_grouped, left_on="Item Name", right_on="Item", how="left")
            sale_qty["Qty"] = sale_qty["Qty"].fillna(0)
            sale_qty = sale_qty.drop(columns=["Item"], errors="ignore")
        else:
            sale_qty = items_master.copy()
            sale_qty["Qty"] = 0.0

        forecast_achievement = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        forecast_achievement["forecast_achivement %"] = np.where(
            forecast_achievement["Forecast Qty"] > 0,
            (forecast_achievement["Qty"] / forecast_achievement["Forecast Qty"]) * 100, 0
        )
        forecast_achievement = forecast_achievement.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        balance = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        balance["Balance"] = balance["Qty"] - balance["Forecast Qty"]
        balance = balance.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        dates_up_to_selected = select_date_obj.day
        denom = (dates_up_to_selected - 1) if dates_up_to_selected > 1 else 1

        avg_sale_per_week = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        avg_sale_per_week["avg sale per week"] = (avg_sale_per_week["Qty"] / denom) * 6
        avg_sale_per_week = avg_sale_per_week.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        availabel_balance = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        inv_avail = inventory_filtered.set_index("Item Code")["Available Qty"] if not inventory_filtered.empty else pd.Series(dtype=float)
        avg_week_series = avg_sale_per_week.set_index("Product Code")["avg sale per week"]

        availabel_balance = availabel_balance.set_index("Product Code")
        availabel_balance["avilable balance"] = (
            inv_avail.reindex(availabel_balance.index).fillna(0) - avg_week_series.reindex(availabel_balance.index).fillna(0)
        )
        availabel_balance = availabel_balance.reset_index().drop(columns=["Item Name", "Qty", "Forecast Qty"])

        day_target = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        day_target["Day Target"] = day_target["Forecast Qty"] / working_days_value
        day_target = day_target.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        days_in_month = calendar.monthrange(select_date_obj.year, select_date_obj.month)[1]
        average_sales = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        average_sales["Average Sales"] = average_sales["Qty"] / days_in_month
        average_sales = average_sales.drop(columns=["Item Name", "Qty", "Forecast Qty"])

        avg_daily_target = sale_qty.copy().merge(
            forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left"
        )
        avg_sales_series = average_sales.set_index("Product Code")["Average Sales"]
        day_target_series = day_target.set_index("Product Code")["Day Target"]
        avg_daily_target = avg_daily_target.set_index("Product Code")
        
        avg_daily_target["Average Daily Target"] = np.where(
            day_target_series.reindex(avg_daily_target.index).fillna(0) > 0,
            (avg_sales_series.reindex(avg_daily_target.index).fillna(0) / day_target_series.reindex(avg_daily_target.index).fillna(1.0)) * 100, 0
        )
        avg_daily_target = avg_daily_target.reset_index().drop(columns=["Item Name", "Qty", "Forecast Qty"])

        inventory_filtered_clean = inventory_filtered.drop(
            columns=[c for c in ["Date", "Product Name"] if c in inventory_filtered.columns]
        )

        master_table = (
            sale_qty
            .merge(forecast_filtered[["Product Code", "Forecast Qty"]], on="Product Code", how="left")
            .merge(forecast_achievement, on="Product Code", how="left")
            .merge(balance, on="Product Code", how="left")
            .merge(
                inventory_filtered_clean[["Item Code", "Available Qty"]] if not inventory_filtered_clean.empty else pd.DataFrame(columns=["Item Code", "Available Qty"]),
                left_on="Product Code", right_on="Item Code", how="left",
            )
            .drop(columns=["Item Code"], errors="ignore")
            .merge(avg_sale_per_week, on="Product Code", how="left")
            .merge(availabel_balance, on="Product Code", how="left")
            .merge(day_target, on="Product Code", how="left")
            .merge(average_sales, on="Product Code", how="left")
            .merge(avg_daily_target, on="Product Code", how="left")
            .fillna(0)
        )

        master_table = master_table.replace([np.inf, -np.inf], 0)
        return master_table

    def build_weekly_breakdown(selected_date_str: str, items_master: pd.DataFrame) -> pd.DataFrame:
        _, sales_day_book, _, _, _ = load_raw_data()

        select_date_obj = pd.to_datetime(selected_date_str)
        year, month = select_date_obj.year, select_date_obj.month
        
        days_in_month = calendar.monthrange(year, month)[1]
        first_weekday = pd.Timestamp(year, month, 1).weekday() 
        total_weeks = ((days_in_month - 1 + first_weekday) // 7) + 1
        week_cols = [f"Week {i}" for i in range(1, total_weeks + 1)]

        items_master = items_master.loc[:, ~items_master.columns.duplicated(keep="first")].copy()

        df = sales_day_book.copy()
        date_col = "New_date" if "New_date" in df.columns else "new_date" if "new_date" in df.columns else "Date"

        if not df.empty and date_col in df.columns:
            df["Date_parsed"] = pd.to_datetime(df[date_col], errors="coerce")
            df = df[
                (df["Date_parsed"].dt.year == year) & 
                (df["Date_parsed"].dt.month == month) &
                (df["Date_parsed"] <= select_date_obj)
            ].copy()

        if df.empty or "Item" not in df.columns:
            weekly_pivot = pd.DataFrame(columns=["Item Name"] + week_cols)
        else:
            if "Qty" not in df.columns:
                df["Qty"] = 0.0
            df["Qty"] = df["Qty"].apply(safe_float)
            df["day"] = df["Date_parsed"].dt.day
            df["week_num"] = ((df["day"] - 1 + first_weekday) // 7) + 1
            df["week_label"] = "Week " + df["week_num"].astype(int).astype(str)

            weekly_pivot = (
                df.groupby(["Item", "week_label"])["Qty"]
                .sum()
                .reset_index()
                .pivot(index="Item", columns="week_label", values="Qty")
                .reset_index()
            )
            weekly_pivot = weekly_pivot.rename(columns={"Item": "Item Name"})

        id_cols = [c for c in ["Product Code", "Item Name"] if c in items_master.columns]
        weekly_table = items_master[id_cols].merge(weekly_pivot, on="Item Name", how="left")

        for c in week_cols:
            if c not in weekly_table.columns:
                weekly_table[c] = 0
        weekly_table[week_cols] = weekly_table[week_cols].fillna(0)

        weekly_table["Total"] = weekly_table[week_cols].sum(axis=1)
        weekly_table = weekly_table[id_cols + week_cols + ["Total"]]
        return weekly_table

    def style_dataframe(df: pd.DataFrame, is_weekly=False):
        df_display = df.copy()
        
        def safe_formatter(val, is_pct):
            if pd.isna(val) or val == "": return "-"
            try:
                num = float(val)
                return f"{num:,.2f}%" if is_pct else f"{num:,.2f}"
            except:
                return str(val)
                
        format_dict = {}
        for c in df_display.columns:
            if c not in ["Product Code", "Item Code", "Item Name", "Category", "Brand", "Item", "No"]:
                is_pct_col = "%" in c or ("Target" in c and "Daily" in c)
                format_dict[c] = lambda x, p=is_pct_col: safe_formatter(x, p)
                
        styler = df_display.style.format(format_dict)
        
        def safe_get_float(val):
            try:
                if pd.isna(val) or val == "": return None
                if isinstance(val, str):
                    val = val.replace(',', '').replace('%', '').strip()
                return float(val)
            except: return None

        if not is_weekly:
            def highlight_rows(row):
                styles = [''] * len(row)
                if 'forecast_achivement %' in row.index:
                    ach_idx = row.index.get_loc('forecast_achivement %')
                    ach_val = safe_get_float(row['forecast_achivement %'])
                    if ach_val is not None:
                        if ach_val >= 100: styles[ach_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif ach_val >= 75: styles[ach_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif ach_val >= 50: styles[ach_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif ach_val >= 0: styles[ach_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[ach_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                
                if 'Average Daily Target' in row.index:
                    adt_idx = row.index.get_loc('Average Daily Target')
                    adt_val = safe_get_float(row['Average Daily Target'])
                    if adt_val is not None:
                        if adt_val >= 100: styles[adt_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif adt_val >= 75: styles[adt_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif adt_val >= 50: styles[adt_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif adt_val >= 0: styles[adt_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[adt_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                
                if 'Balance' in row.index:
                    bal_idx = row.index.get_loc('Balance')
                    bal_val = safe_get_float(row['Balance'])
                    if bal_val is not None:
                        if bal_val >= 0: styles[bal_idx] = 'background-color: #E2F0CB; color: #2D5A27; font-weight: bold;'
                        else: styles[bal_idx] = 'background-color: #FFD1D1; color: #900000; font-weight: bold;'
                
                if 'Qty' in row.index and 'Forecast Qty' in row.index:
                    qty_idx = row.index.get_loc('Qty')
                    qty_val = safe_get_float(row['Qty'])
                    fq_val = safe_get_float(row['Forecast Qty'])
                    if qty_val is not None and fq_val is not None and fq_val > 0:
                        pct = (qty_val / fq_val) * 100
                        if pct >= 100: styles[qty_idx] = 'background-color: #D4EDDA; color: #155724; font-weight: bold;'
                        elif pct >= 75: styles[qty_idx] = 'background-color: #FFF3CD; color: #856404; font-weight: bold;'
                        elif pct >= 50: styles[qty_idx] = 'background-color: #FFE8CC; color: #A04000; font-weight: bold;'
                        elif pct >= 0: styles[qty_idx] = 'background-color: #F8D7DA; color: #721C24; font-weight: bold;'
                        else: styles[qty_idx] = 'background-color: #F5C6CB; color: #721C24; font-weight: bold;'
                return styles
            styler = styler.apply(highlight_rows, axis=1)

        styler = styler.set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#03045E'), ('color', 'white'), ('text-align', 'center'), ('padding', '10px'), ('border', '1px solid #ADE8F4'), ('white-space', 'nowrap')]},
            {'selector': 'td', 'props': [('border', '1px solid #ADE8F4'), ('padding', '8px'), ('text-align', 'right'), ('white-space', 'nowrap')]},
            {'selector': 'tr:nth-child(even)', 'props': [('background-color', '#F8FDFF')]}
        ])
        
        try: styler = styler.hide(axis="index")
        except: pass
            
        return styler

    def generate_pdf_or_html(styler, title, date_str):
        try: import pdfkit
        except ImportError: pdfkit = None
            
        try:
            with open("logo.png", "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode()
            img_tag = f'<img src="data:image/png;base64,{logo_base64}" style="height: 55px;" />'
        except: img_tag = ''

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <style>
                @page {{ size: A4 landscape; margin: 10mm; }}
                body {{ font-family: 'Helvetica', 'Arial', sans-serif; color: #03045E; margin: 0; background-color: #ffffff; }}
                table.header-table {{ width: 100%; background-color: #00245E; color: white; border-bottom: 5px solid #DE9C40; border-radius: 8px 8px 0 0; margin-bottom: 15px; border-collapse: collapse; }}
                table.header-table td {{ border: none; padding: 15px; background-color: #00245E; text-align: left; vertical-align: middle; }}
                .info-section {{ background-color: #CAF0F8; padding: 12px 20px; border-left: 6px solid #0096C7; margin-bottom: 15px; border-radius: 4px; }}
                .info-section h3 {{ margin: 0; color: #023E8A; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; font-size: 11px !important; table-layout: auto; }}
                th, td {{ border: 1px solid #ADE8F4; padding: 6px 8px; text-align: right; white-space: nowrap; }}
                th {{ background-color: #03045E !important; color: white !important; text-align: center; font-weight: bold; }}
            </style>
        </head>
        <body>
            <table class="header-table">
                <tr>
                    <td style="width: 70px;">{img_tag}</td>
                    <td><h1 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: 1px; color: white;">Imo Chicken & Agro (Pvt) Ltd</h1></td>
                </tr>
            </table>
            <div class="info-section">
                <table style="width: 100%; border: none;">
                    <tr>
                        <td style="text-align: left; border: none; padding: 0;"><h3>Department: Sales & Marketing</h3></td>
                        <td style="text-align: center; border: none; padding: 0;"><h3>Report: {title}</h3></td>
                        <td style="text-align: right; border: none; padding: 0;"><h3>Date: {date_str}</h3></td>
                    </tr>
                </table>
            </div>
            <div style="display: flex; gap: 15px; margin-bottom: 10px; font-size: 11px; font-weight: bold; justify-content: flex-end; color: #03045E;">
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #D4EDDA; border: 1px solid #155724;"></div> Target &ge; 100%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFF3CD; border: 1px solid #856404;"></div> 75% - 99%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFE8CC; border: 1px solid #A04000;"></div> 50% - 74%</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #F8D7DA; border: 1px solid #721C24;"></div> &lt; 50%</div>
                <div style="display: flex; align-items: center; gap: 5px; margin-left:10px;"><div style="width: 12px; height: 12px; background-color: #E2F0CB; border: 1px solid #2D5A27;"></div> Balance &ge; 0</div>
                <div style="display: flex; align-items: center; gap: 5px;"><div style="width: 12px; height: 12px; background-color: #FFD1D1; border: 1px solid #900000;"></div> Balance &lt; 0</div>
            </div>
            {styler.to_html()}
        </body>
        </html>
        """
        
        options = {
            'page-size': 'A4', 'orientation': 'Landscape', 'margin-top': '0.3in', 'margin-right': '0.3in',
            'margin-bottom': '0.3in', 'margin-left': '0.3in', 'encoding': "UTF-8", 'enable-local-file-access': None,
            'zoom': 1.0, 'dpi': 300, 'no-outline': None
        }
        
        if pdfkit:
            try:
                pdf_bytes = pdfkit.from_string(html_content, False, options=options)
                return pdf_bytes, "pdf", "application/pdf"
            except Exception: pass 
        
        return html_content.encode('utf-8'), "html", "text/html"

    # ============================================================
    # 4. SAVE / LOAD / DELETE helpers
    # ============================================================
    def _get_or_create_ws(sheet, tab_name, headers=None, rows=2000, cols=30):
        try:
            ws = sheet.worksheet(tab_name)
            if headers:
                existing_header = ws.row_values(1)
                if existing_header != headers:
                    ws.update("A1", [headers])
        except gspread.exceptions.WorksheetNotFound:
            ws = sheet.add_worksheet(title=tab_name, rows=rows, cols=cols)
            if headers:
                ws.append_row(headers)
        return ws

    def _delete_records(sheet, tab_name, key_col_name, key_value):
        try:
            ws = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            return
            
        all_values = ws.get_all_values()
        if not all_values or len(all_values) < 2:
            return
            
        header = all_values[0]
        if key_col_name not in header:
            return
            
        key_col_idx = header.index(key_col_name)
        match_val = str(key_value).strip()
        rows_to_delete = []
        
        for idx, row in enumerate(all_values, start=1):
            if len(row) > key_col_idx:
                sheet_val = str(row[key_col_idx]).strip()
                if key_col_name == "Date":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m-%d")
                    except: pass
                elif key_col_name == "Month":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m")
                    except: pass
                if sheet_val == match_val:
                    rows_to_delete.append(idx)
                    
        if rows_to_delete:
            rows_to_delete.sort()
            ranges = []
            start = prev = rows_to_delete[0]
            for r in rows_to_delete[1:]:
                if r == prev + 1: prev = r
                else:
                    ranges.append((start, prev))
                    start = prev = r
            ranges.append((start, prev))
            sheet_id = ws.id
            requests = []
            for (start_row, end_row) in reversed(ranges):
                requests.append({
                    "deleteDimension": {
                        "range": { "sheetId": sheet_id, "dimension": "ROWS", "startIndex": start_row - 1, "endIndex": end_row }
                    }
                })
            ws.spreadsheet.batch_update({"requests": requests})

    def _save_df_to_tab(sheet, tab_name: str, df: pd.DataFrame, key_col_name: str, key_value: str):
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        df = df.loc[:, ~df.columns.duplicated(keep="first")].copy()
        df = df.replace([np.inf, -np.inf], 0).fillna(0)
        df.insert(0, key_col_name, key_value)

        headers = df.columns.tolist()
        ws = _get_or_create_ws(sheet, tab_name, headers=headers)
        
        _delete_records(sheet, tab_name, key_col_name, key_value)

        values = df.astype(str).values.tolist()
        ws.append_rows(values, value_input_option="USER_ENTERED")
        return True

    def _load_df_from_tab(sheet, tab_name: str, key_col_name: str, key_value: str):
        try: ws = sheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound: return None
        all_values = ws.get_all_values()
        if len(all_values) < 2: return None

        header = all_values[0]
        if key_col_name not in header: return None

        key_col_idx = header.index(key_col_name)
        match_val = str(key_value).strip()
        rows = []
        
        for row in all_values[1:]:
            if len(row) > key_col_idx:
                sheet_val = str(row[key_col_idx]).strip()
                if key_col_name == "Date":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m-%d")
                    except: pass
                elif key_col_name == "Month":
                    try: sheet_val = pd.to_datetime(sheet_val).strftime("%Y-%m")
                    except: pass
                if sheet_val == match_val: rows.append(row)
                    
        if not rows: return None
        fixed_rows = [row + [""] * (len(header) - len(row)) for row in rows]
        return pd.DataFrame(fixed_rows, columns=header)

    def save_report_to_sheet(sheet, df_report: pd.DataFrame, selected_date_str: str):
        return _save_df_to_tab(sheet, "Req_Report", df_report, "Date", selected_date_str)

    def load_report_for_date(sheet, selected_date_str: str):
        return _load_df_from_tab(sheet, "Req_Report", "Date", selected_date_str)

    def save_weekly_report_to_sheet(sheet, df_weekly: pd.DataFrame, month_str: str):
        return _save_df_to_tab(sheet, "Req_Weekly", df_weekly, "Month", month_str)

    def load_weekly_report_for_month(sheet, month_str: str):
        return _load_df_from_tab(sheet, "Req_Weekly", "Month", month_str)

    def enforce_numeric_types(df: pd.DataFrame) -> pd.DataFrame:
        """Normalize report values and safely remove duplicate spreadsheet headers."""
        df = df.copy()
        df.columns = [str(col).strip() for col in df.columns]
        df = df.loc[:, ~df.columns.duplicated(keep="first")].copy()

        text_cols = [
            "Date", "Month", "Product Code", "Item Code",
            "Item Name", "Item", "No", "Category", "Brand"
        ]

        for col in df.columns:
            if col not in text_cols:
                cleaned = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("%", "", regex=False)
                    .str.strip()
                )
                df[col] = pd.to_numeric(cleaned, errors="coerce").fillna(0.0)

        return df

    # ============================================================
    # 5. STREAMLIT UI
    # ============================================================
    st.set_page_config(page_title="Requirement Report", layout="wide")
    
    st.markdown("""
        <style>
        :root {
            --c-900: #03045E; --c-800: #023E8A; --c-700: #0077B6;
            --c-600: #0096C7; --c-500: #00B4D8; --c-400: #48CAE4;
            --c-300: #90E0EF; --c-200: #ADE8F4; --c-100: #CAF0F8;
            --accent: #DE9C40;
        }
        .stApp { background: linear-gradient(135deg, var(--c-100) 0%, #FFFFFF 100%); color: var(--c-900); }
        [data-testid="stHeader"] { background: transparent !important; }
        .block-container { 
            padding-top: 1rem !important; 
            padding-bottom: 2rem !important; 
            max-width: 98% !important; 
            overflow-x: hidden !important; 
            min-height: 85vh !important; 
        }
        h1, h2, h3 { color: var(--c-900) !important; }
        [data-testid="stDataFrame"] {
            border: 1px solid #D1E5EB; border-radius: 8px; box-shadow: 0 4px 15px rgba(3, 4, 94, 0.08); background-color: white; padding: 5px;
        }
        button[kind="primary"] { background-color: #03045E !important; color: white !important; border-radius: 6px !important; font-weight: 600 !important; }
        button[kind="primary"]:hover { background-color: #0077B6 !important; }
        button[kind="secondary"] { background-color: #0096C7 !important; color: white !important; border-color: #0096C7 !important; border-radius: 6px !important; }
        button[kind="secondary"]:hover { background-color: #023E8A !important; border-color: #023E8A !important; }
        
        div[data-testid="stDateInput"] label p {
            font-family: 'Arial', sans-serif !important; font-weight: 600 !important; font-size: 16px !important; color: #03045E !important;
        }
        div[data-testid="stDateInput"] div[data-baseweb="input"] {
            border: 2px solid #0096C7 !important; border-radius: 8px !important; background-color: #F8FDFF !important; transition: all 0.3s ease-in-out; padding-left: 5px;
        }
        div[data-testid="stDateInput"] div[data-baseweb="input"]:focus-within {
            border: 2px solid #03045E !important; box-shadow: 0 0 8px rgba(3, 4, 94, 0.4) !important;
        }
        
        div.element-container:has(.delete-target), div.element-container:has(.cancel-target) { display: none; }
        div.element-container:has(.delete-target) + div.element-container button {
            background-color: #D90429 !important; color: white !important; border: 1px solid #D90429 !important;
        }
        div.element-container:has(.delete-target) + div.element-container button:hover {
            background-color: #B20322 !important; border: 1px solid #B20322 !important; color: white !important;
        }
        div.element-container:has(.cancel-target) + div.element-container button {
            background-color: #28a745 !important; color: white !important; border: 1px solid #28a745 !important;
        }
        div.element-container:has(.cancel-target) + div.element-container button:hover {
            background-color: #218838 !important; border: 1px solid #218838 !important; color: white !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Production Requirement Report")
    
    col1, col2 = st.columns([2, 5], vertical_alignment="bottom")
    with col1:
        selected_date = st.date_input("Select Date:", value=datetime.date.today())
        
    selected_date_str = selected_date.strftime("%Y-%m-%d")
    selected_month_str = pd.to_datetime(selected_date_str).strftime("%Y-%m")
    
    st.divider()

    @st.cache_data(ttl=60, show_spinner=False)
    def fetch_existing_reports(date_str, month_str):
        sheet1, _ = get_sheets()
        df = load_report_for_date(sheet1, date_str)
        wk = load_weekly_report_for_month(sheet1, month_str)
        return df, wk
        
    existing_df, existing_weekly = fetch_existing_reports(selected_date_str, selected_month_str)

    if existing_df is not None and not existing_df.empty:
        st.info(f"✅ A previously generated report already exists for **{selected_date_str}**.")
        
        existing_df = enforce_numeric_types(existing_df)
        
        st.markdown("""
        <div style="display: flex; gap: 20px; flex-wrap: wrap; margin-bottom: 12px; font-size: 14px; font-weight: 600; color: #03045E; background: white; padding: 10px; border-radius: 6px; border: 1px solid #D1E5EB;">
            <span style="color: #666;">Targets:</span>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #D4EDDA; border: 1px solid #155724; border-radius: 4px;"></div> &ge; 100%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFF3CD; border: 1px solid #856404; border-radius: 4px;"></div> 75% - 99%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFE8CC; border: 1px solid #A04000; border-radius: 4px;"></div> 50% - 74%</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #F8D7DA; border: 1px solid #721C24; border-radius: 4px;"></div> &lt; 50%</div>
            <span style="color: #ccc; margin: 0 10px;">|</span>
            <span style="color: #666;">Balance:</span>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #E2F0CB; border: 1px solid #2D5A27; border-radius: 4px;"></div> &ge; 0 (Good)</div>
            <div style="display: flex; align-items: center; gap: 6px;"><div style="width: 16px; height: 16px; background-color: #FFD1D1; border: 1px solid #900000; border-radius: 4px;"></div> &lt; 0 (Short)</div>
        </div>
        """, unsafe_allow_html=True)
        
        styled_master = style_dataframe(existing_df, is_weekly=False)
        st.dataframe(styled_master, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            csv_bytes = existing_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇ Download Report CSV", data=csv_bytes, file_name=f"requirement_report_{selected_date_str}.csv", mime="text/csv", use_container_width=True)
        with c2:
            export_data, ext, mime = generate_pdf_or_html(styled_master, "Production Requirement", selected_date_str)
            st.download_button(f"🖨️ Download as PDF/HTML", data=export_data, file_name=f"requirement_report_{selected_date_str}.{ext}", mime=mime, use_container_width=True)

        if existing_weekly is not None and not existing_weekly.empty:
            st.divider()
            st.subheader(f"Weekly Breakdown — {pd.to_datetime(selected_date_str).strftime('%B %Y')}")
            existing_weekly = enforce_numeric_types(existing_weekly)
            styled_weekly = style_dataframe(existing_weekly, is_weekly=True)
            st.dataframe(styled_weekly, use_container_width=True)

            wc1, wc2 = st.columns(2)
            with wc1:
                weekly_csv_bytes = existing_weekly.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇ Download Weekly Breakdown CSV", data=weekly_csv_bytes, file_name=f"req_weekly_breakdown_{selected_month_str}.csv", mime="text/csv", use_container_width=True)
            with wc2:
                w_export_data, w_ext, w_mime = generate_pdf_or_html(styled_weekly, "Weekly Breakdown Report", selected_month_str)
                st.download_button(f"🖨️ Download Weekly as PDF/HTML", data=w_export_data, file_name=f"req_weekly_breakdown_{selected_month_str}.{w_ext}", mime=w_mime, use_container_width=True)

        st.divider()
        if st.button("🗑️ Delete this Report", key="delete_report_btn"):
            st.session_state["confirm_delete_report"] = True
            
        if st.session_state.get("confirm_delete_report"):
            st.error(f"Are you sure you want to permanently delete the report for {selected_date_str}?")
            dc1, dc2 = st.columns([1, 6], vertical_alignment="bottom")
            with dc1:
                st.markdown('<span class="delete-target"></span>', unsafe_allow_html=True)
                if st.button("✅ Yes, delete it"):
                    with st.spinner("Deleting..."):
                        sheet1, _ = get_sheets()
                        _delete_records(sheet1, "Req_Report", "Date", selected_date_str)
                        _delete_records(sheet1, "Req_Weekly", "Month", selected_month_str)
                        st.session_state["confirm_delete_report"] = False
                        save_and_refresh(f"🗑️ Report for {selected_date_str} successfully deleted!")
            with dc2:
                st.markdown('<span class="cancel-target"></span>', unsafe_allow_html=True)
                if st.button("Cancel"):
                    st.session_state["confirm_delete_report"] = False
                    st.rerun()

    else:
        st.info("No report exists for the selected date. Click the button below to generate and save one.")
        if st.button("▶ Calculate & Save Report", type="primary"):
            with st.spinner("Calculating and Saving to Database..."):
                try:
                    _, sales_day_book, _, _, _ = load_raw_data()
                    date_col = (
                        "New_date" if "New_date" in sales_day_book.columns
                        else "new_date" if "new_date" in sales_day_book.columns
                        else "Date"
                    )
                    has_sales_for_selected_date = False

                    if date_col in sales_day_book.columns:
                        sales_dates = pd.to_datetime(sales_day_book[date_col], errors="coerce")
                        has_sales_for_selected_date = sales_dates.dt.normalize().eq(
                            pd.Timestamp(selected_date_str)
                        ).any()

                    if not has_sales_for_selected_date:
                        st.warning(
                            f"No data has been entered in the Sales Day Book for {selected_date_str}. "
                            "Please enter the required data in the Sales Day Book and try generating the report again."
                        )
                        return

                    master_table = build_master_table(selected_date_str)
                    _, _, _, items_master_raw, _ = load_raw_data()
                    weekly_table = build_weekly_breakdown(selected_date_str, items_master_raw)
                    
                    sheet1, _ = get_sheets()
                    save_report_to_sheet(sheet1, master_table, selected_date_str)
                    save_weekly_report_to_sheet(sheet1, weekly_table, selected_month_str)
                    
                    save_and_refresh(f"✅ Report for '{selected_date_str}' successfully calculated and saved!")
                except Exception as e:
                    st.error(f"Error occurred during calculation/saving: {e}")
