# pages/report.py
import streamlit as st

def show():
    st.title("📊 Reports")

    # Drop down arrow eka sahitha select box ekak
    report_option = st.selectbox(
        "Choose Report",
        ("📄 Report 1 - Sales", "📄 Report 2 - Users")
    )

    st.markdown("---")

    if report_option == "📄 Report 1 - Sales":
        st.subheader("📈 Sales Report")
        st.write("Monthly sales data:")
        data = {"Jan": 100, "Feb": 150, "Mar": 200, "Apr": 180, "May": 220}
        st.bar_chart(data)
        st.success("This is Report 1")

    else:
        st.subheader("👥 User Analytics Report")
        st.write("User engagement metrics:")
        data = {"Active": 850, "New": 120, "Returning": 730}
        st.bar_chart(data)
        st.success("This is Report 2")