import streamlit as st
import pandas as pd
import altair as alt  # <--- Added Altair for better charts
from bs4 import BeautifulSoup

# --- 1. PROCESSING ENGINE (Same as before) ---
def parse_csrs_file(uploaded_file):
    soup = BeautifulSoup(uploaded_file, 'lxml')
    student_info = {}
    info_table = soup.find('table', class_='form')
    if info_table:
        for row in info_table.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) == 2:
                key = cols[0].get_text(strip=True).replace(':', '')
                val = cols[1].get_text(strip=True)
                student_info[key] = val

    all_grades = []
    grade_tables = soup.find_all('table', class_='list')
    for table in grade_tables:
        headers = [th.get_text(strip=True) for th in table.find_all('th')]
        for row in table.find_all('tr'):
            if row.find('th'): continue
            cols = row.find_all('td')
            if not cols: continue
            row_data = {headers[i]: col.get_text(strip=True) for i, col in enumerate(cols) if i < len(headers)}
            all_grades.append(row_data)

    return student_info, pd.DataFrame(all_grades)

def calculate_gwa(df):
    df['Units_Calc'] = pd.to_numeric(df['Units'], errors='coerce')
    df['Grade_Calc'] = pd.to_numeric(df['Grade'], errors='coerce')
    df['Is_Included'] = ~df['Course'].str.contains(r'^(PE|NSTP)', case=False, regex=True) & df['Grade_Calc'].notna()
    df['Weighted_Grade'] = df['Grade_Calc'] * df['Units_Calc']

    sem_groups = df.groupby(['Year', 'Semester'], sort=False)
    sem_data = []
    for (year, sem), group in sem_groups:
        valid = group[group['Is_Included']]
        total_units = valid['Units_Calc'].sum()
        weighted_sum = valid['Weighted_Grade'].sum()
        gwa = weighted_sum / total_units if total_units > 0 else 0.0
        
        # Shorten semester names for cleaner graphs (Optional)
        short_sem = "1st Sem" if "FIRST" in sem else "2nd Sem" if "SECOND" in sem else "Midsem"
        term_label = f"{year} {short_sem}" 

        sem_data.append({
            'Year': year, 
            'Semester': sem, 
            'Term': term_label, # Cleaner label for X-axis
            'Units': total_units, 
            'GWA': gwa
        })
    
    df_sem = pd.DataFrame(sem_data)
    valid_all = df[df['Is_Included']]
    total_units_cum = valid_all['Units_Calc'].sum()
    weighted_sum_cum = valid_all['Weighted_Grade'].sum()
    overall_gwa = weighted_sum_cum / total_units_cum if total_units_cum > 0 else 0.0

    return df, df_sem, overall_gwa

# --- 2. THE USER INTERFACE ---
st.set_page_config(page_title="UPMin Grade Calculator", layout="wide")

st.title("🎓 CSRS Grade Visualizer")
st.markdown("Upload your **CSRS Student.html** file to generate your academic dashboard.")

# --- NEW: Help Tooltip / Expander ---
with st.expander("ℹ️ How to save and upload your CSRS.html?"):
    st.markdown("""
    **Step-by-step guide:**
    1. Log in to your UPMin CSRS portal.
    2. Navigate to your **Grades** or **Student Profile** page.
    3. Right-click anywhere on the page and select **Save As...** (or press `Ctrl+S` / `Cmd+S`).
    4. Make sure the "Save as type" is set to **Webpage, HTML Only** or **Webpage, Complete**.
    5. Upload that saved `.html` file below!
    """)
    
    spacer1, center_col, spacer2 = st.columns([1, 2, 1])
        
        with center_col:
            # Putting use_container_width=True makes it fill the center column perfectly
            st.image("tutorial.gif", caption="Visual Guide", use_column_width=True)

uploaded_file = st.file_uploader("Choose your HTML file", type="html")

if uploaded_file is not None:
    try:
        info, raw_df = parse_csrs_file(uploaded_file)
        
        if raw_df.empty:
            st.error("Could not find any grades in the file.")
        else:
            processed_df, sem_df, overall_gwa = calculate_gwa(raw_df)

            # Sidebar
            with st.sidebar:
                st.header("Student Profile")
                if info:
                    st.text(f"Name: {info.get('Name', 'N/A')}")
                    st.text(f"Student #: {info.get('Student Number', 'N/A')}")
                    st.text(f"Program: {info.get('Program', 'N/A')}")
                st.divider()
                st.write("Developed with Streamlit")

            # Metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(label="Cumulative GWA", value=f"{overall_gwa:.4f}")
            with col2:
                total_units = processed_df[processed_df['Is_Included']]['Units_Calc'].sum()
                st.metric(label="Total Academic Units", value=f"{total_units}")
            with col3:
                if overall_gwa <= 1.20: status = "Summa Cum Laude Standing"
                elif overall_gwa <= 1.45: status = "Magna Cum Laude Standing"
                elif overall_gwa <= 1.75: status = "Cum Laude Standing"
                else: status = "Good Standing"
                
                # Added the 'help' parameter (supports clean Markdown!)
                st.metric(
                    label="Status", 
                    value=status,
                    help=(
                        "**UP System Honor Cutoffs:**\n\n"
                        "🥇 **Summa Cum Laude:** 1.00 – 1.20\n\n"
                        "🥈 **Magna Cum Laude:** 1.20 – 1.45\n\n"
                        "🥉 **Cum Laude:** 1.45 – 1.75\n\n"
                    )
                )

            st.divider()

            # --- IMPROVED CHART SECTION ---
            st.subheader("📈 GWA Trajectory")
            
            # We use Altair here for full control over axes
            # 1. We inverse the Y axis (scale domain) so 1.0 is at the 'top' conceptually? 
            #    Actually, standard math plots have 1.0 at bottom. 
            #    Let's stick to your request: "lowest y axis value be flat one".
            #    This means we set the domain to start specifically at 1.0.
            
            chart = alt.Chart(sem_df).mark_line(point=True, strokeWidth=3).encode(
                x=alt.X('Term',sort=None, axis=alt.Axis(labelAngle=0, title="Semester")), # labelAngle=0 forces horizontal
                y=alt.Y('GWA', scale=alt.Scale(domain=[1.0, 3.0]), axis=alt.Axis(title="GWA")), # Lock axis 1.0 to 3.0
                tooltip=['Term', 'GWA', 'Units']
            ).properties(
                height=350
            ).interactive() # Allows zooming/panning

            st.altair_chart(chart, use_container_width=True)
            # ------------------------------

            # Detailed Tables
            col_left, col_right = st.columns([1, 2])
            
            with col_left:
                st.subheader("Semestral Summary")
                st.dataframe(sem_df[['Term', 'GWA', 'Units']].style.format({"GWA": "{:.4f}"}), hide_index=True)

            with col_right:
                st.subheader("Full Grade History")
                display_cols = ['Course', 'Grade', 'Units', 'Year', 'Semester']
                st.dataframe(processed_df[display_cols], hide_index=True, use_container_width=True)

            st.divider()
            st.subheader("📅 Course Breakdown by Term")
            st.markdown("Expand each semester to see the specific subjects and your term GWA.")

            # We use groupby to loop through every unique Year + Semester combo
            # sort=False ensures it keeps the chronological order from the original HTML
            for (year, sem), group in processed_df.groupby(['Year', 'Semester'], sort=False):
                
                # Calculate the exact GWA for just this specific semester
                valid = group[group['Is_Included']]
                term_units = valid['Units_Calc'].sum()
                term_weighted = valid['Weighted_Grade'].sum()
                term_gwa = term_weighted / term_units if term_units > 0 else 0.0
                
                # Create a clean title for the collapsible box
                expander_title = f"{year} — {sem} | Term GWA: {term_gwa:.4f}"
                
                # Create the expander
                with st.expander(expander_title):
                    # We only show the relevant columns so it fits nicely
                    display_cols = ['Course', 'Grade', 'Units']
                    
                    # Display the dataframe inside the expander
                    st.dataframe(
                        group[display_cols], 
                        hide_index=True, 
                        use_container_width=True
                    )

    except Exception as e:

        st.error(f"An error occurred: {e}")
