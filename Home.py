# Home.py (Complete updated version)
import streamlit as st
from util import authenticate, get_allowed_pages
import importlib
import re
import time
import base64
import os
import json


# ---------- Page configuration ----------
st.set_page_config(page_title="My App", layout="wide", initial_sidebar_state="expanded")

# ---------- Session state initialization ----------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.session_state.current_page = "Home"


# ---------- CSS to hide sidebar and default navigation ----------
def apply_css(hide_sidebar=True):
    if hide_sidebar:
        st.markdown(
            """
            <style>
                [data-testid="stSidebar"] { display: none; }
                [data-testid="stSidebarCollapsedControl"] { display: none; }
                [data-testid="stSidebarNav"] { display: none !important; }
                .main > div { padding-left: 2rem; padding-right: 2rem; }
            </style>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <style>
                [data-testid="stSidebar"] { display: block; }
                [data-testid="stSidebarCollapsedControl"] { display: block; }
                [data-testid="stSidebarNav"] { display: none !important; }
                section[data-testid="stSidebar"] > div:first-child { padding-top: 1rem; }
            </style>
            """,
            unsafe_allow_html=True
        )

if not os.path.exists("service_account.json"):
    try:
        # If the google_sheets are in credentials name, then write it to a file
        if "google_sheets_credentials" in st.secrets:
            with open("service_account.json", "w") as f:
                f.write(st.secrets["google_sheets_credentials"])
        
        # Method 2: If the credentials are directly pasted as a JSON in Secrets
        elif "type" in st.secrets and st.secrets["type"] == "service_account":
            with open("service_account.json", "w") as f:
                json.dump(dict(st.secrets), f)
                
        else:
            st.error("⚠️ Google Sheets credentials not found in Streamlit secrets. Please add them to the secrets.toml file.")
            st.stop() # Stop the app if the credentials are not found
            
    except Exception as e:
        st.error(f"⚠️ Error reading secrets: {e}")
        st.stop()
# ---------- Login form (main screen) ----------
def show_login_form():
    def get_base64_file(file_path):
        try:
            with open(file_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            return ""

    # Load logo and video files as base64
    logo_path = "logo.png"
    logo_base64 = get_base64_file(logo_path)

    video_path = "Sales_meeting_video_with_graphs_202608011540.mp4" 
    video_base64 = get_base64_file(video_path)

    # ==========================================
    # 🎨 CSS FOR MINIMAL LOGIN & ANIMATIONS
    # ==========================================
    css_code = """
        <style>
        /* 1. Hide the Sidebar completely on Login Page */
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stSidebarCollapsedControl"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        
        /* 2. Video Background Settings */
        [data-testid="stAppViewContainer"] {
            background-color: transparent !important;
        }
        .stApp {
            /* Video Background */
            background: linear-gradient(rgba(110,127,128,0.3), rgba(110,127,128,0.3)) !important;
        }
        
        /* send the video to the background */
        #bg-video {
            position: fixed;
            right: 0;
            bottom: 0;
            min-width: 100vw;
            min-height: 100vh;
            z-index: -1;
            object-fit: cover;
        }

        /* 3. Minimal Glassmorphism Form Styling */
        [data-testid="stForm"] {
            background: rgba(255, 255, 255, 0.6) !important;
            backdrop-filter: blur(10px) !important;
            border-radius: 3% !important;
            border: 1px solid rgba(255, 255, 255, 0.3) !important;
            width: 500px;
            margin-left: 75px;
            padding: 40px 40px !important;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.85) !important;
        }
        
        /* Form Text Styles */
        [data-testid="stForm"] h2 {
            color: #052b6c !important;
            text-align: center;
            font-weight: 800;
            padding-bottom: 5px;
        }
        
        /* Input Box Styling */
        div[data-baseweb="input"] {
            border-radius: 8px !important;
            border: 1px solid #ADE8F4 !important;
            background-color: white !important;
        }
        div[data-baseweb="input"]:focus-within {
            border-color: #0077B6 !important;
            box-shadow: 0 0 0 2px rgba(0, 119, 182, 0.2) !important;
        }
        
        /* Normal Clean Login Button */
        [data-testid="stFormSubmitButton"] button {
            background-color: #052b6c !important;
            color: white !important;
            border-radius: 8px !important;
            font-weight: bold !important;
            border: none !important;
            padding: 10px !important;
            transition: all 0.3s ease !important;
        }
        [data-testid="stFormSubmitButton"] button:hover {
            background-color: #03045E !important;
            box-shadow: 0 4px 12px rgba(3, 4, 94, 0.3) !important;
        }

        /* ==========================================
           4. "ACCESS GRANTED" ANIMATION CSS
           ========================================== */
        .success-box {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .checkmark {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: block;
            stroke-width: 4;
            stroke: #0077B6;
            stroke-miterlimit: 10;
            box-shadow: inset 0px 0px 0px #0077B6;
            animation: scale .3s ease-in-out .9s both;
            margin: 0 auto;
        }
        .checkmark__circle {
            stroke-dasharray: 166;
            stroke-dashoffset: 166;
            stroke-width: 4;
            stroke-miterlimit: 10;
            stroke: #0077B6;
            fill: none;
            animation: stroke 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
        }
        .checkmark__check {
            transform-origin: 50% 50%;
            stroke-dasharray: 48;
            stroke-dashoffset: 48;
            stroke: #0077B6;
            stroke-width: 4;
            animation: stroke 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.6s forwards;
        }

        /* ==========================================
           5. "ACCESS DENIED" (ERROR) ANIMATION CSS
           ========================================== */
        .error-box {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 16px;
            padding: 40px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .crossmark {
            width: 80px;
            height: 80px;
            border-radius: 50%;
            display: block;
            stroke-width: 4;
            stroke: #D90429;
            stroke-miterlimit: 10;
            box-shadow: inset 0px 0px 0px #D90429;
            animation: scale .3s ease-in-out .9s both;
            margin: 0 auto;
        }
        .crossmark__circle {
            stroke-dasharray: 166;
            stroke-dashoffset: 166;
            stroke-width: 4;
            stroke-miterlimit: 10;
            stroke: #D90429;
            fill: none;
            animation: stroke 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
        }
        .crossmark__cross {
            transform-origin: 50% 50%;
            stroke-dasharray: 48;
            stroke-dashoffset: 48;
            stroke: #D90429;
            stroke-width: 4;
            animation: stroke 0.3s cubic-bezier(0.65, 0, 0.45, 1) 0.6s forwards;
        }

        @keyframes stroke {
            100% { stroke-dashoffset: 0; }
        }
        @keyframes scale {
            0%, 100% { transform: none; }
            50% { transform: scale3d(1.1, 1.1, 1); }
        }
        </style>
    """
    
    video_html = f"""
        <video autoplay muted loop playsinline id="bg-video">
            <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
        </video>
    """
    
    st.markdown(css_code + video_html, unsafe_allow_html=True)

    st.markdown(css_code + video_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 15vh;'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown(f"""
            <div style='text-align: center; margin-bottom: 40px;'>
                <img src="data:image/png;base64,{logo_base64}" style="width: 180px;">
            <div style='margin-top: 35px;'>
                    <span style='background-color: #052b6c; 
                                color: white; 
                                padding: 8px 20px; 
                                border-radius: 8px; 
                                font-weight: 800; 
                                font-size: 30px;
                                display: inline-block;
                                box-shadow: 0 4px 12px rgba(3, 4, 94, 0.4);'>
                        Imo Chicken & Agro (Pvt) Ltd
                    </span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            st.markdown("<h2>Login</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #666; margin-top: -10px; margin-bottom: 20px;'>Enter your credentials to access the portal</p>", unsafe_allow_html=True)

            username = st.text_input("Username", placeholder="Enter Username")
            password = st.text_input("Password", type="password", placeholder="Enter Password")

            st.markdown("<br>", unsafe_allow_html=True)
            login_btn = st.form_submit_button("Log in", use_container_width=True)

        if login_btn:
            role = authenticate(username, password)
            if role:
                st.session_state.pending_username = username
                st.session_state.pending_role = role
                st.session_state.login_status = "granted"
            else:
                st.session_state.login_status = "denied"
            st.rerun()
# ---------- Logout ----------
def logout():
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.logging_out = True
        # no need to rerun here, the overlay will handle the logout process in the main function

# ---------- Main ----------
def main():
    if st.session_state.get("login_status") == "granted":
        st.markdown("""
            <style>
            .logout-overlay {
                position: fixed; top:0; left:0; width:100vw; height:100vh;
                background: rgba(255,255,255,0.4); backdrop-filter: blur(8px);
                z-index: 999999; display:flex; justify-content:center; align-items:center;
            }
            .success-box {
                background: rgba(255,255,255,0.95); backdrop-filter: blur(10px);
                border-radius: 16px; padding: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                text-align:center; display:flex; flex-direction:column; align-items:center; justify-content:center;
            }
            .checkmark { width:80px; height:80px; border-radius:50%; display:block; stroke-width:4; stroke:#0077B6; stroke-miterlimit:10; box-shadow:inset 0px 0px 0px #0077B6; animation: scale .3s ease-in-out .9s both; margin:0 auto; }
            .checkmark__circle { stroke-dasharray:166; stroke-dashoffset:166; stroke-width:4; stroke-miterlimit:10; stroke:#0077B6; fill:none; animation: stroke 0.6s cubic-bezier(0.65,0,0.45,1) forwards; }
            .checkmark__check { transform-origin:50% 50%; stroke-dasharray:48; stroke-dashoffset:48; stroke:#0077B6; stroke-width:4; animation: stroke 0.3s cubic-bezier(0.65,0,0.45,1) 0.6s forwards; }
            @keyframes stroke { 100% { stroke-dashoffset:0; } }
            @keyframes scale { 0%,100% { transform:none; } 50% { transform:scale3d(1.1,1.1,1); } }
            </style>
            <div class="logout-overlay">
                <div class="success-box">
                    <svg class="checkmark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                        <circle class="checkmark__circle" cx="26" cy="26" r="25" fill="none"/>
                        <path class="checkmark__check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                    </svg>
                    <h2 style="color:#03045e;margin-top:20px;font-weight:800;">Access Granted!</h2>
                    <p style="color:#666;font-size:15px;font-weight:500;">Welcome back...</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        time.sleep(1.8)

        st.session_state.logged_in = True
        st.session_state.username = st.session_state.pending_username
        st.session_state.role = st.session_state.pending_role
        allowed_pages = get_allowed_pages(st.session_state.role)
        st.session_state.current_page = "Home" if st.session_state.role == "admin" else (allowed_pages[0] if allowed_pages else "Home")

        st.session_state.login_status = ""
        st.rerun()

    if st.session_state.get("login_status") == "denied":
        st.markdown("""
            <style>
            .logout-overlay {
                position: fixed; top:0; left:0; width:100vw; height:100vh;
                background: rgba(255,255,255,0.4); backdrop-filter: blur(8px);
                z-index: 999999; display:flex; justify-content:center; align-items:center;
            }
            .error-box {
                background: rgba(255,255,255,0.95); backdrop-filter: blur(10px);
                border-radius: 16px; padding: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                text-align:center; display:flex; flex-direction:column; align-items:center; justify-content:center;
            }
            .crossmark { width:80px; height:80px; border-radius:50%; display:block; stroke-width:4; stroke:#D90429; stroke-miterlimit:10; box-shadow:inset 0px 0px 0px #D90429; animation: scale .3s ease-in-out .9s both; margin:0 auto; }
            .crossmark__circle { stroke-dasharray:166; stroke-dashoffset:166; stroke-width:4; stroke-miterlimit:10; stroke:#D90429; fill:none; animation: stroke 0.6s cubic-bezier(0.65,0,0.45,1) forwards; }
            .crossmark__cross { transform-origin:50% 50%; stroke-dasharray:48; stroke-dashoffset:48; stroke:#D90429; stroke-width:4; animation: stroke 0.3s cubic-bezier(0.65,0,0.45,1) 0.6s forwards; }
            @keyframes stroke { 100% { stroke-dashoffset:0; } }
            @keyframes scale { 0%,100% { transform:none; } 50% { transform:scale3d(1.1,1.1,1); } }
            </style>
            <div class="logout-overlay">
                <div class="error-box">
                    <svg class="crossmark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                        <circle class="crossmark__circle" cx="26" cy="26" r="25" fill="none"/>
                        <path class="crossmark__cross" fill="none" d="M16 16 36 36 M36 16 16 36"/>
                    </svg>
                    <h2 style="color:#D90429;margin-top:20px;font-weight:800;">Access Denied</h2>
                    <p style="color:#666;font-size:15px;font-weight:500;">Invalid username or password.</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        time.sleep(2)
        st.session_state.login_status = ""
        st.rerun()

    if not st.session_state.get("logged_in", False):
        show_login_form()
        return
    if not st.session_state.get("logged_in", False):
        show_login_form()
        return

    # LOGGED IN
    apply_css(hide_sidebar=False)

    st.markdown("""
        <style>
        /* 🚀 1. Keep the Sidebar Header visible for the toggle button, but remove extra space */
        [data-testid="stSidebarHeader"] {
            padding-top: 1rem !important;
            padding-bottom: 0 !important;
            background: transparent !important;
        }

        /* Make the toggle button clearly visible with our theme color */
        [data-testid="stSidebarCollapseButton"] {
            color: #03045E !important;
        }

        /* 🚀 2. Force pull the entire sidebar content upwards */
        [data-testid="stSidebarUserContent"] {
            padding-top: 0rem !important;
            margin-top: -30px !important; 
        }
        
        /* 🚀 Hide default Streamlit sidebar navigation to save space */
        [data-testid="stSidebarNav"] {
            display: none !important;
            height: 0px !important;
        }

        /* Sidebar Background */
        [data-testid="stSidebar"] {
            background-color: #00245E;
        }

        /* 🚀 Logo Shape Glow (No Box Shape) */
        [data-testid="stSidebar"] [data-testid="stImage"] {
            background: transparent !important;
            box-shadow: none !important;
            padding: 10px !important;
            margin-top: 10px;
            margin-bottom: 20px;
        }
        
        [data-testid="stSidebar"] [data-testid="stImage"] img {
            filter: drop-shadow(0px 0px 3px rgba(255, 255, 255, 0.4)) 
                    drop-shadow(0px 0px 3px rgba(255, 255, 255, 0.4))
                    drop-shadow(0px 0px 3px rgba(255, 255, 255, 0.4));
        }
        
        /* Sidebar Headers Styling (KPI, Data Entry, etc.) */
        [data-testid="stSidebar"] h3 {
            color: #FFFFFF !important;
            font-size: 1.05rem !important;
            font-weight: 800 !important;
            letter-spacing: 0.5px;
            border-bottom: 2px solid #0096C7;
            padding-bottom: 5px;
            margin-bottom: 10px;
            margin-top: 15px;
        }
        
        /* Radio Button Text Styling */
        .stRadio p {
            color: #eef4ed !important;
            font-weight: 600 !important;
            font-size: 0.95rem !important;
        }
        
        /* Sidebar Divider */
        hr {
            border-top: 2px dashed #90E0EF !important;
        }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.sidebar.columns([1, 2.5, 1])
    with col2:
        try:
            # If the logo.png file exists, display it in the sidebar
            st.image("logo.png", use_container_width=True)
        except Exception:
            pass

# ---------- Sidebar Content ----------
    st.sidebar.markdown("<h3 style='text-align: center; color: #052b6c; font-weight: 900; margin-top: -10px; margin-bottom: 0px; border-bottom: none;'>IMO Chicken & Agro (Pvt) Ltd</h3>", unsafe_allow_html=True)
    st.sidebar.markdown("<hr style='margin-top: 15px; margin-bottom: 15px; border-top: 2px solid #0096C7 !important;'>", unsafe_allow_html=True)

    st.sidebar.markdown(f"<h3 style='color: #FFFFFF; font-size: 22px; font-weight: 700; margin-bottom: 0;'>👋 Welcome, {st.session_state.username}!</h3>", unsafe_allow_html=True)
    
    st.sidebar.markdown(f"<p style='color: #FFFFFF; font-size: 16px; font-weight: 600; margin-top: 5px;'>Role: {st.session_state.role}</p>", unsafe_allow_html=True)
    
    st.sidebar.markdown("---")

    allowed = get_allowed_pages(st.session_state.role)
    
    # Only admin can access to Home
    if st.session_state.role == "admin":
        page_options = ["Home"] + allowed
    else:
        page_options = allowed
    
    if st.session_state.current_page not in page_options:
        st.session_state.current_page = page_options[0] if page_options else "Home"
        st.rerun()

    # Format the page name
    def format_page_name(name):
        if name == "Home":
            return "KPI" # For Home page, display as "KPI"
        # clear the unusefull 
        clean_name = re.sub(r'^[\d_]+', '', name)
        return clean_name.replace("_", " ").title()
    
    kpi_pages = [p for p in page_options if p in ["Home"]]
    data_entry_pages = [p for p in page_options if p in ["1sales_day_book" , "2Inventory", "3Monthly_Forecast", "4Working_days", "5Rep_Target"]]
    report_pages = [p for p in page_options if p in ["Requrement", "rep_target"]]
    dashboard_pages = [p for p in page_options if p in ["dashboard"]]

    def nav_callback(radio_key):
        if st.session_state[radio_key] is not None:
            st.session_state.current_page = st.session_state[radio_key]

    st.session_state["kpi_radio"] = st.session_state.current_page if st.session_state.current_page in kpi_pages else None
    st.session_state["data_entry_radio"] = st.session_state.current_page if st.session_state.current_page in data_entry_pages else None
    st.session_state["report_radio"] = st.session_state.current_page if st.session_state.current_page in report_pages else None
    st.session_state["dashboard_radio"] = st.session_state.current_page if st.session_state.current_page in dashboard_pages else None


    if kpi_pages:
        st.sidebar.markdown("### 🎯 KPI")
        st.sidebar.radio(
            "KPI Navigation",
            kpi_pages,
            index=kpi_pages.index(st.session_state.current_page) if st.session_state.current_page in kpi_pages else None,
            format_func=format_page_name,
            key="kpi_radio",
            on_change=nav_callback,
            args=("kpi_radio",),
            label_visibility="collapsed"
        )
        st.sidebar.write("")

    if data_entry_pages:
        st.sidebar.markdown("### 📝 Data Entry")
        st.sidebar.radio(
            "Data Entry Navigation",
            data_entry_pages,
            index=data_entry_pages.index(st.session_state.current_page) if st.session_state.current_page in data_entry_pages else None,
            format_func=format_page_name,
            key="data_entry_radio",
            on_change=nav_callback,
            args=("data_entry_radio",),
            label_visibility="collapsed"
        )
        st.sidebar.write("")

    if report_pages:
        st.sidebar.markdown("### 📁 Report")
        st.sidebar.radio(
            "Report Navigation",
            report_pages,
            index=report_pages.index(st.session_state.current_page) if st.session_state.current_page in report_pages else None,
            format_func=format_page_name,
            key="report_radio",
            on_change=nav_callback,
            args=("report_radio",),
            label_visibility="collapsed"
        )
        st.sidebar.write("")

    if dashboard_pages:
        st.sidebar.markdown("### 📊 Dashboard")
        st.sidebar.radio(
            "Dashboard Navigation",
            dashboard_pages,
            index=dashboard_pages.index(st.session_state.current_page) if st.session_state.current_page in dashboard_pages else None,
            format_func=format_page_name,
            key="dashboard_radio",
            on_change=nav_callback,
            args=("dashboard_radio",),
            label_visibility="collapsed"
        )

    st.sidebar.markdown("---")
    logout()

    selected = st.session_state.current_page

    # Render page
    if selected == "Home":
        st.title("KPI Dashboard Coming Soon")
        st.write(f"Hello Admin **{st.session_state.username}**!")
        st.write("Performance metrics and key insights will be available in an upcoming update.")
    else:
        try:
            module = importlib.import_module(f"pages.{selected}")
        except ImportError as e:
            st.error(f"Error loading page '{selected}': {e}")
        else:
            page_show = getattr(module, "show", None)

            if not callable(page_show):
                st.error(f"Page '{selected}' does not have a show() function.")
            else:
                try:
                    page_show()
                except Exception as e:
                    st.exception(e)

    # ==========================================
    # 🌟 OVERLAY LOGOUT ANIMATION 
    # (Rendered on top of the existing page content)
    # ==========================================
    if st.session_state.get("logging_out", False):
        st.markdown("""
            <style>
            .logout-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                background: rgba(255, 255, 255, 0.4);
                backdrop-filter: blur(8px);
                z-index: 999999;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .spinner-box {
                background: rgba(255, 255, 255, 0.95);
                border-radius: 16px;
                padding: 40px;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
                text-align: center;
                display: flex;
                flex-direction: column;
                align-items: center;
                animation: scaleIn 0.3s ease-out;
            }
            @keyframes scaleIn {
                from { transform: scale(0.9); opacity: 0; }
                to { transform: scale(1); opacity: 1; }
            }
            .loader {
                border: 6px solid #e2e8f0;
                border-top: 6px solid #0077B6;
                border-radius: 50%;
                width: 60px;
                height: 60px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            </style>
            <div class="logout-overlay">
                <div class="spinner-box">
                    <div class="loader"></div>
                    <h2 style="color: #03045E; font-weight: 800; margin:0;">Logging Out...</h2>
                    <p style="color: #666; font-size: 15px; margin-top: 5px;">Securely ending your session.</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # තත්පර 1.5ක් මේ Animation එක පෙන්වා ඉඳීම
        time.sleep(1.5)
        
        # ඉන්පසුව Session State සියල්ල මකා දැමීම (සම්පූර්ණ Logout වීම)
        for key in ["logged_in", "username", "role", "current_page", "logging_out"]:
            if key in st.session_state:
                del st.session_state[key]
                
        st.session_state.logged_in = False
        st.rerun()

if __name__ == "__main__":
    main()


###########################################################################
############################## KPI ########################################
###########################################################################

def apply_custom_css():
    st.markdown("""
        <style>
        /* Color Palette Variables */
        :root {
            --c-900: #03045E;
            --c-800: #023E8A;
            --c-700: #0077B6;
            --c-600: #0096C7;
            --c-500: #00B4D8;
            --c-400: #48CAE4;
            --c-300: #90E0EF;
            --c-200: #ADE8F4;
            --c-100: #CAF0F8;
        }

        /* App Background */
        .stApp {
            background: linear-gradient(135deg, var(--c-100) 0%, #FFFFFF 100%);
            color: var(--c-900);
        }

        /* Hide Header background */
        [data-testid="stHeader"] {
            background: transparent !important;
        }

        /* Hide Top Padding & Overflow fixes */
        .block-container {
            padding-top: 0rem !important;
            margin-top: -30px !important;
            padding-bottom: 1rem !important;
            max-width: 98% !important;
            overflow-x: hidden !important;
        }

        [data-testid="stPlotlyChart"] > div, 
        [data-testid="stPlotlyChart"] iframe {
            overflow: hidden !important;
            box-sizing: border-box !important;
        }

        }
        [data-testid="stPlotlyChart"] * {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }

        </style>
    """, unsafe_allow_html=True)

apply_custom_css()