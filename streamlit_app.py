import streamlit as st
import csv
import io
from fpdf import FPDF

# --- Constants ---
MILK_DENSITY_KG_L = 1.0285

def convert_kg_to_litres(kg_value):
    """
    Converts Mass (KG) to Volume (L) using standard milk density.
    Formula: L = KG / 1.0285
    Rounds strictly to 2 decimal places.
    """
    try:
        if kg_value < 0:
            return 0.0
        return round(kg_value / MILK_DENSITY_KG_L, 2)
    except (TypeError, ValueError):
        return 0.0

st.title("Milk DIP Converter & Table Generator")

# Initialize session state for records
if 'records' not in st.session_state:
    st.session_state['records'] = []

# --- Manual entry form ---
with st.form("add_record_form"):
    col1, col2 = st.columns(2)
    with col1:
        milk_kg_str = st.text_input("Milk (KG)", value="", key="manual_milk_kg")
    with col2:
        dip_str = st.text_input("DIP", value="", key="manual_dip")
    submitted = st.form_submit_button("Add Record")
    if submitted:
        try:
            milk_kg = float(milk_kg_str)
        except (ValueError, TypeError):
            milk_kg = 0.0
        try:
            dip = float(dip_str)
        except (ValueError, TypeError):
            dip = 0.0
            
        dip_mm = round(dip * 10, 2)
        st.session_state['records'].append({
            'Milk (KG)': round(milk_kg, 2),
            'DIP': round(dip, 2),
            'DIP(MM)': dip_mm
        })
        st.success(f"Added: Milk (KG)={milk_kg}, DIP={dip}, DIP(MM)={dip_mm}")

if st.session_state['records']:
    st.subheader("Current Records")
    
    # Callback function to auto-update DIP(MM) when DIP changes
    def update_dip_mm():
        """Automatically update DIP(MM) based on DIP column values"""
        for i, record in enumerate(st.session_state['records']):
            dip_value = record.get('DIP', 0)
            st.session_state['records'][i]['DIP(MM)'] = round(dip_value * 10, 1)
    
    # Use data_editor to allow editing and deletion of records
    st.session_state['records'] = st.data_editor(
        st.session_state['records'], 
        num_rows="dynamic",
        width="stretch",
        key="records_editor",
        on_change=update_dip_mm
    )
else:
    st.info("No records added yet.")

# --- DIP Table Logic (Continuous Interpolation) ---

# --- Helper Functions for Smart Interpolation ---

def find_consistent_step(dip1, dip2, milk1, milk2):
    """Calculates milk vol change per 0.1 DIP step."""
    milk_diff = milk2 - milk1
    dip_diff = dip2 - dip1
    if dip_diff == 0: return 0
    return milk_diff / (dip_diff * 10)

def calculate_smart_slope(target_dip, sorted_dips, value_map):
    """
    Calculates a 'smart' slope (per 1.0 DIP) based on the average of all slopes,
    clamping local variations to prevent wild extrapolation outliers.
    """
    if len(sorted_dips) < 2:
        return 25.0 # Default 2.5 per 0.1 -> 25.0 per 1.0
    
    slopes = []
    # Calculate all interval slopes (per 0.1 DIP)
    for i in range(len(sorted_dips) - 1):
        d1, d2 = sorted_dips[i], sorted_dips[i+1]
        v1, v2 = value_map[d1], value_map[d2]
        if d2 > d1:
            slopes.append(find_consistent_step(d1, d2, v1, v2))
    
    if not slopes:
        return 25.0
        
    avg_slope = sum(slopes) / len(slopes)
    
    # Determine local slope based on proximity
    if target_dip < sorted_dips[0]:
        local_slope = slopes[0]
    elif target_dip > sorted_dips[-1]:
        local_slope = slopes[-1]
    else:
        # Find closest interval
        closest_idx = 0
        min_dist = float('inf')
        for i in range(len(sorted_dips) - 1):
            midpoint = (sorted_dips[i] + sorted_dips[i+1]) / 2
            dist = abs(target_dip - midpoint)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i
        local_slope = slopes[closest_idx]
        
    # Clamp the slope to be within 50% - 150% of the average slope
    lower_limit = avg_slope * 0.5
    upper_limit = avg_slope * 1.5
    
    if avg_slope >= 0:
        clamped_slope = max(lower_limit, min(upper_limit, local_slope))
    else:
        clamped_slope = max(upper_limit, min(lower_limit, local_slope))
        
    # Return slope per 1.0 DIP (consistent with existing logic)
    return clamped_slope * 10

def get_volume_at_dip(target_dip, sorted_dips, value_map):
    """Calculates volume for any DIP using continuous linear interpolation."""
    # 1. Exact Match
    if target_dip in value_map:
        return value_map[target_dip]
    
    # 2. Find surrounding points
    lower = [d for d in sorted_dips if d < target_dip]
    higher = [d for d in sorted_dips if d > target_dip]
    
    if lower and higher:
        d1, d2 = max(lower), min(higher)
        # Use simple linear interpolation between known points (Standard)
        v1, v2 = value_map[d1], value_map[d2]
        slope = (v2 - v1) / (d2 - d1)
        return v1 + (target_dip - d1) * slope
    
    elif lower: # Extrapolate high (beyond last record)
        d1 = max(lower)
        # Use Smart Slope for safer extrapolation
        slope = calculate_smart_slope(target_dip, sorted_dips, value_map)
        return value_map[d1] + (target_dip - d1) * slope
        
    elif higher: # Extrapolate low (before first record)
        d2 = min(higher)
        # Use Smart Slope for safer extrapolation
        slope = calculate_smart_slope(target_dip, sorted_dips, value_map)
        return value_map[d2] - (d2 - target_dip) * slope
    
    return 0.0

def generate_dip_table_from_records(records, dip_start=None, dip_end=None, mode='kg'):
    """
    Generates a table of volumes for DIP values ranging from 0 to 9 tenths for each integer DIP.
    """
    ref_dips = [rec['DIP'] for rec in records]
    ref_kgs = [rec['Milk (KG)'] for rec in records]
    if not ref_dips or not ref_kgs:
        return ['DIP', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'], []
    
    if dip_start is None:
        dip_start = int(min(ref_dips))
    if dip_end is None:
        dip_end = max(ref_dips)
    
    # Build the correct value map for the selected mode
    if mode == 'kg':
        value_map = {d: kg for d, kg in zip(ref_dips, ref_kgs)}
    else:
        # Strict Conversion applied here
        value_map = {d: convert_kg_to_litres(kg) for d, kg in zip(ref_dips, ref_kgs)}
        
    sorted_dips = sorted(value_map.keys())
    output_data = []

    # Generate table row by row (integer DIPs)
    start_int = int(dip_start)
    end_int = int(dip_end)
    
    for current_int_dip in range(start_int, end_int + 1):
        row = [current_int_dip]
        for tenths in range(10):
            actual_dip = current_int_dip + (tenths / 10.0)
            vol = get_volume_at_dip(actual_dip, sorted_dips, value_map)
            row.append(round(vol, 2))
        output_data.append(row)

    headers = ['DIP', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    return headers, output_data

# --- Export Logic ---

def generate_csv(records, mode='kg'):
    headers, table = generate_dip_table_from_records(
        st.session_state['records'],
        dip_start=None,
        dip_end=None,
        mode=mode
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in table:
        writer.writerow(row)
    return output.getvalue().encode('utf-8')

def generate_pdf(records, mode='kg'):
    headers, table = generate_dip_table_from_records(
        st.session_state['records'],
        dip_start=None,
        dip_end=None,
        mode=mode
    )
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    # Calculate column width for table
    col_width = pdf.w / (len(headers) + 1)
    row_height = pdf.font_size * 1.5
    # Header with border and fill
    pdf.set_fill_color(220, 220, 220)
    for header in headers:
        pdf.cell(col_width, row_height, str(header), border=1, align='C', fill=True)
    pdf.ln(row_height)
    # Table rows with border
    for row in table:
        for item in row:
            pdf.cell(col_width, row_height, str(item), border=1, align='C')
        pdf.ln(row_height)
    return pdf.output(dest='S').encode('latin1')

def generate_raw_pdf(records):
    # Always generates in KG mode for "Raw"
    return generate_pdf(records, mode='kg') # Reusing generate_pdf logic for simplicity if layout checks out

if st.session_state['records']:
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.download_button(
            label="Download KG CSV",
            data=generate_csv(st.session_state['records'], 'kg'),
            file_name="output_kg.csv",
            mime="text/csv"
        )
    with col2:
        st.download_button(
            label="Download Litre CSV",
            data=generate_csv(st.session_state['records'], 'litre'),
            file_name="output_litre.csv",
            mime="text/csv"
        )
    with col3:
        st.download_button(
            label="Download KG PDF",
            data=generate_pdf(st.session_state['records'], 'kg'),
            file_name="output_kg.pdf",
            mime="application/pdf"
        )
    with col4:
        st.download_button(
            label="Download Litre PDF",
            data=generate_pdf(st.session_state['records'], 'litre'),
            file_name="output_litre.pdf",
            mime="application/pdf"
        )
    with col5:
        st.download_button(
            label="Download Raw PDF",
            # Assuming generate_raw_pdf was intended to match generate_pdf structure but explicitly named
            data=generate_pdf(st.session_state['records'], 'kg'), 
            file_name="output_raw.pdf",
            mime="application/pdf"
        )
    with col6:
        if st.button("Clear Records"):
            st.session_state['records'] = []
            st.rerun() # Updated from experimental_rerun
