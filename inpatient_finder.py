import streamlit as st
import pandas as pd
from datetime import timedelta
from io import BytesIO

st.title("🏥 Patient Admission Grouper & Filter")

# Load file
uploaded_file = st.file_uploader("Upload a CSV or XLSX file", type=["csv", "xlsx"])

@st.cache_data
def load_data(file):
    if file.name.endswith(".xlsx"):
        df = pd.read_excel(file, sheet_name=0, parse_dates=["Admit Date", "Discharge Date"])
    else:
        df = pd.read_csv(file, parse_dates=["Admit Date", "Discharge Date"])
    df = df.dropna(subset=["Admit Date", "Discharge Date"])
    return df

# Grouping function
def group_patient_records(patient_df):
    patient_df = patient_df.sort_values("Admit Date").reset_index(drop=True)
    group = 1
    group_ids = [None] * len(patient_df)
    i = 0

    while i < len(patient_df):
        group_start_idx = i
        group_end = patient_df.loc[i, "Discharge Date"]

        j = i + 1
        while j < len(patient_df):
            next_admit = patient_df.loc[j, "Admit Date"]
            if next_admit <= group_end + timedelta(days=20):
                group_end = max(group_end, patient_df.loc[j, "Discharge Date"])
                j += 1
            else:
                break

        for k in range(group_start_idx, j):
            group_ids[k] = group
        group += 1
        i = j

    patient_df["Group"] = group_ids
    return patient_df

# CSV conversion helper
def convert_df_to_csv(df):
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer

if uploaded_file:
    df = load_data(uploaded_file)

    # Apply grouping
    df_grouped = df.groupby("Medical Record #", group_keys=False).apply(group_patient_records)

    # Calculate Group Discharge Date
    df_grouped["Group Discharge Date"] = (
        df_grouped.groupby(["Medical Record #", "Group"])["Discharge Date"]
        .transform("max")
    )

    # Keep only first row per group
    df_result = (
        df_grouped.sort_values(["Medical Record #", "Group", "Admit Date"])
        .groupby(["Medical Record #", "Group"], as_index=False)
        .first()
    )

    st.subheader("📋 Grouped Data Preview")
    st.dataframe(df_result)

    # Date filter UI
    st.subheader("📅 Filter by Date Range")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")

    if start_date and end_date:
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)

        filtered_df = df_result[
            (df_result["Admit Date"] <= end_date) &
            (df_result["Group Discharge Date"] >= start_date)
        ]

        st.subheader("🔎 Filtered Result")
        st.dataframe(filtered_df)

        csv_data = convert_df_to_csv(filtered_df)
        st.download_button(
            label="⬇️ Download Filtered CSV",
            data=csv_data,
            file_name="filtered_output.csv",
            mime="text/csv"
        )
