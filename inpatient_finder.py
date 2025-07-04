import streamlit as st
import pandas as pd
from datetime import timedelta
from io import BytesIO
import matplotlib.pyplot as plt

st.title("🏥 Patient Admission Grouper & LA Patient Stats")

uploaded_file = st.file_uploader("Upload a CSV or XLSX file", type=["csv", "xlsx"])

def fill_missing_discharge_dates(df):
    missing_dd = df["Discharge Date"].isna()
    mask_o = missing_dd & (df["Patient Class"] == "O")
    df.loc[mask_o, "Discharge Date"] = df.loc[mask_o, "Admit Date"]
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

def correct_patient_state(state):
    if str(state).strip() != "CA":
        return state
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

def group_patient_records(patient_df, days_threshold):
    patient_df = patient_df.sort_values("Admit Date").reset_index(drop=True)
    group = 1
    group_ids = [group]  # First record always starts a group

    for i in range(1, len(patient_df)):
        prev_discharge = patient_df.loc[i - 1, "Discharge Date"]
        curr_admit = patient_df.loc[i, "Admit Date"]
        day_gap = (curr_admit - prev_discharge).days

        if day_gap >= days_threshold:
            group += 1  # Start a new group
        group_ids.append(group)

    patient_df["Group"] = group_ids
    return patient_df

def convert_df_to_csv(df):
    buffer = BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return buffer

if uploaded_file:
    df = load_data(uploaded_file)

    # Remove threshold UI and use fixed 20 days
    days_threshold = 20

    # Filter out telemedicine patients
    df = df[df["Patient Type"] != "Telemedicine"]

    # Correct patient states
    df["Patient State"] = df["Patient State"].apply(correct_patient_state)

    # Split into CA and non-CA
    ca_df = df[df["Patient State"] == "CA"]
    non_ca_df = df[df["Patient State"] != "CA"]

    ca_inpatients = ca_df[ca_df["Patient Type"] == "Inpatient"]
    ca_non_inpatients = ca_df[ca_df["Patient Type"] != "Inpatient"]

    grouped_inpatients = ca_inpatients.groupby("Medical Record #", group_keys=False).apply(
        lambda df: group_patient_records(df, days_threshold)
    )
    grouped_inpatients["Group Type"] = "CA Grouped (Inpatient)"

    ca_non_inpatients = ca_non_inpatients.copy()
    ca_non_inpatients["Group"] = range(1, len(ca_non_inpatients) + 1)
    ca_non_inpatients["Group Type"] = "CA Single Record (Non-Inpatient)"

    grouped_ca = pd.concat([grouped_inpatients, ca_non_inpatients], ignore_index=True)

    grouped_non_ca = non_ca_df.groupby("Medical Record #", group_keys=False).apply(
        lambda df: group_patient_records(df, days_threshold)
    )
    grouped_non_ca["Group Type"] = "Non-CA Grouped"

    combined_df = pd.concat([grouped_ca, grouped_non_ca], ignore_index=True)
    combined_df["Group Discharge Date"] = (
        combined_df.groupby(["Medical Record #", "Group"])["Discharge Date"]
        .transform("max")
    )

    grouped_only = (
        combined_df[combined_df["Group"].notna()]
        .sort_values(["Medical Record #", "Group", "Admit Date"])
        .groupby(["Medical Record #", "Group"], as_index=False)
        .first()
    )
    not_grouped = combined_df[combined_df["Group"].isna()]
    df_result = pd.concat([grouped_only, not_grouped], ignore_index=True)

    # ----------- FILTER BY SINGLE DATE -----------
    st.subheader("📅 Choose Date of Interest")
    chosen_date = st.date_input("Select Date")
    if chosen_date:
        chosen_date = pd.to_datetime(chosen_date)

        filtered_df = df_result[
            (df_result["Admit Date"] <= chosen_date) &
            (df_result["Group Discharge Date"] >= chosen_date)
        ]

        # Deduplicate by Medical Record #
        filtered_df = filtered_df.sort_values("Admit Date")
        filtered_df = filtered_df.drop_duplicates(subset=["Medical Record #"], keep="first")

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

        st.subheader("🔎 Filtered Patients")
        st.dataframe(filtered_df)

        csv_data = convert_df_to_csv(filtered_df)
        st.download_button(
            label="⬇️ Download Filtered CSV",
            data=csv_data,
            file_name="filtered_output.csv",
            mime="text/csv"
        )

        # ---- LA Patients Analytics ----
        st.subheader("📊 LA Patient Analytics (Past 30 Days)")

        date_range = pd.date_range(chosen_date - pd.Timedelta(days=29), chosen_date)
        daily_patient_counts = []
        
        for day in date_range:
            # Count unique patients present on this day
            count = df_result[
                (df_result["Admit Date"] <= day) &
                (df_result["Group Discharge Date"] >= day)
            ]["Medical Record #"].nunique()
            daily_patient_counts.append(count)
        
        # Bar Chart: Each bar is one day
        fig1, ax1 = plt.subplots(figsize=(10, 4))
        ax1.bar(
            [d.strftime("%b %d") for d in date_range],
            daily_patient_counts
        )
        ax1.set_title("Unique Patients per Day (Last 30 Days)")
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Unique Patients")
        fig1.autofmt_xdate()  # Rotate date labels for better readability
        st.pyplot(fig1)
        
        # Line Chart: Unique patients per day
        fig2, ax2 = plt.subplots()
        ax2.plot(date_range, daily_patient_counts, marker='o')
        ax2.set_title("Unique Patients per Day (Last 30 Days)")
        ax2.set_xlabel("Date")
        ax2.set_ylabel("Unique Patients")
        fig2.autofmt_xdate()
        st.pyplot(fig2)
