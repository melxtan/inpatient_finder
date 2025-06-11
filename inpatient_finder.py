import streamlit as st
import pandas as pd
from datetime import timedelta
from io import BytesIO

st.title("🏥 Patient Admission Grouper & Filter")

uploaded_file = st.file_uploader("Upload a CSV or XLSX file", type=["csv", "xlsx"])

def fill_missing_discharge_dates(df):
    # Fill only rows where Discharge Date is NA
    missing_dd = df["Discharge Date"].isna()
    
    # If Patient Class == "O", set Discharge Date = Admit Date
    mask_o = missing_dd & (df["Patient Class"] == "O")
    df.loc[mask_o, "Discharge Date"] = df.loc[mask_o, "Admit Date"]

    # If Patient Class == "I", set Discharge Date = 2050/1/1
    mask_i = missing_dd & (df["Patient Class"] == "I")
    df.loc[mask_i, "Discharge Date"] = pd.to_datetime("2050-01-01")

    return df

@st.cache_data
def load_data(file):
    if file.name.endswith(".xlsx"):
        df = pd.read_excel(file, sheet_name=0, parse_dates=["Admit Date", "Discharge Date"])
    else:
        df = pd.read_csv(file, parse_dates=["Admit Date", "Discharge Date"])
    df = df.dropna(subset=["Admit Date"])
    df = fill_missing_discharge_dates(df)
    return df

# Normalize invalid patient states
def correct_patient_state(state):
    if str(state).strip() != "CA":
        return state  # Leave non-"CA" states untouched

    known_invalids_for_CA = {
        "Zug": "International",
        "Sao Paulo": "International",
        "Paris": "International",
        "Dededo": "GU",
        "Agat": "GU",
        "Yigo": "GU",
        "Hagatna": "GU",
        "Lio Lio": "AS",
        "Saipan": "MP"
    }

    return known_invalids_for_CA.get(str(state).strip(), "CA")

# Grouping logic (applies 20-day threshold)
def group_patient_records(patient_df, days_threshold):
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
            if next_admit <= group_end + timedelta(days=days_threshold):
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

# CSV export
def convert_df_to_csv(df):
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer

if uploaded_file:
    df = load_data(uploaded_file)

    # Grouping threshold slider
    st.subheader("⚙️ Grouping Threshold")
    days_threshold = st.slider("Days between admissions to group records", min_value=1, max_value=90, value=20)

    # Filter out telemedicine patients
    df = df[df["Patient Type"] != "Telemedicine"]

    # Correct patient states
    df["Patient State"] = df["Patient State"].apply(correct_patient_state)

    # Split into CA and non-CA
    ca_df = df[df["Patient State"] == "CA"]
    non_ca_df = df[df["Patient State"] != "CA"]

    # --- CA logic ---
    ca_inpatients = ca_df[ca_df["Patient Type"] == "Inpatient"]
    ca_non_inpatients = ca_df[ca_df["Patient Type"] != "Inpatient"]

    # Group CA inpatients
    grouped_inpatients = ca_inpatients.groupby("Medical Record #", group_keys=False).apply(
        lambda df: group_patient_records(df, days_threshold)
    )
    grouped_inpatients["Group Type"] = "CA Grouped (Inpatient)"

    # Each CA non-inpatient gets its own group
    ca_non_inpatients = ca_non_inpatients.copy()
    ca_non_inpatients["Group"] = range(1, len(ca_non_inpatients) + 1)
    ca_non_inpatients["Group Type"] = "CA Single Record (Non-Inpatient)"

    # Combine CA patients
    grouped_ca = pd.concat([grouped_inpatients, ca_non_inpatients], ignore_index=True)

    # Group Non-CA patients using standard logic
    grouped_non_ca = non_ca_df.groupby("Medical Record #", group_keys=False).apply(
        lambda df: group_patient_records(df, days_threshold)
    )
    grouped_non_ca["Group Type"] = "Non-CA Grouped"

    # Combine all
    combined_df = pd.concat([grouped_ca, grouped_non_ca], ignore_index=True)

    # Calculate Group Discharge Date
    combined_df["Group Discharge Date"] = (
        combined_df.groupby(["Medical Record #", "Group"])["Discharge Date"]
        .transform("max")
    )

    # Keep only first row per group for deduplication
    grouped_only = (
        combined_df[combined_df["Group"].notna()]
        .sort_values(["Medical Record #", "Group", "Admit Date"])
        .groupby(["Medical Record #", "Group"], as_index=False)
        .first()
    )

    not_grouped = combined_df[combined_df["Group"].isna()]
    df_result = pd.concat([grouped_only, not_grouped], ignore_index=True)

    st.subheader("📋 Grouped Data Preview")
    st.dataframe(df_result)

    # Date filter
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

        # Deduplicate by Medical Record #, keeping only overlapping records
        filtered_df = filtered_df.sort_values("Admit Date")
        filtered_df = filtered_df.drop_duplicates(subset=["Medical Record #"], keep="first")

        # Keep only specified columns
        columns_to_keep = [
            "Medical Record #",
            "First Name",
            "Last Name",
            "Med Service",
            "Patient Address",
            "Patient Address (ln2)",
            "Patient City",
            "Patient State",
            "Patient Email Address"
        ]
        
        filtered_df = filtered_df[columns_to_keep]

        st.subheader("🔎 Filtered Result")
        st.dataframe(filtered_df)

        csv_data = convert_df_to_csv(filtered_df)
        st.download_button(
            label="⬇️ Download Filtered CSV",
            data=csv_data,
            file_name="filtered_output.csv",
            mime="text/csv"
        )
