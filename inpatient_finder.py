import streamlit as st
import pandas as pd
from datetime import datetime

st.title("🏥 Inpatient Finder Tool")

# File uploader
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Ensure required columns exist
    required_cols = {"Medical Record #", "Admit Date", "Discharge Date"}
    if not required_cols.issubset(df.columns):
        st.error(f"The CSV must contain these columns: {', '.join(required_cols)}")
    else:
        # Convert dates
        df["Admit Date"] = pd.to_datetime(df["Admit Date"], errors='coerce')
        df["Discharge Date"] = pd.to_datetime(df["Discharge Date"], errors='coerce')

        st.write("📄 Preview of the data:")
        st.dataframe(df.head())

        # Date input
        st.subheader("📆 Select Timeframe")
        start_date = st.date_input("Start Date")
        end_date = st.date_input("End Date")

        if start_date and end_date:
            # Filter logic
            mask = (df["Admit Date"] <= pd.to_datetime(end_date)) & \
                   (df["Discharge Date"] >= pd.to_datetime(start_date))
            filtered_df = df[mask]

            st.subheader("🧾 Inpatients During This Timeframe")
            st.write(f"Patients admitted on or before **{end_date}** and discharged on or after **{start_date}**:")
            st.dataframe(filtered_df)

            # Download option
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Results as CSV", data=csv, file_name="inpatients_filtered.csv", mime="text/csv")