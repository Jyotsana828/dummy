import streamlit as st
import csv
import io
from fpdf import FPDF

st.title("Milk DIP Converter & Table Generator")

# Manual entry section (as before)
if 'records' not in st.session_state:
    st.session_state['records'] = []

# --- Manual entry form with Milk (KG) left, DIP right ---
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
    st.table(st.session_state['records'])
else:
    st.info("No records added yet.")

# --- DIP Table Logic ---
def find_consistent_step(dip1, dip2, milk1, milk2):
    milk_diff = milk2 - milk1
    dip_diff = dip2 - dip1
    return milk_diff / (dip_diff * 10)

def generate_dip_table_from_records(records, dip_start=None, dip_end=None, mode='kg'):
    ref_dips = [rec['DIP'] for rec in records]
    ref_kgs = [rec['Milk (KG)'] for rec in records]
    if not ref_dips or not ref_kgs:
        return ['DIP', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'], []
    if dip_start is None:
        dip_start = int(min(ref_dips))
    if dip_end is None:
        dip_end = max(ref_dips)
    max_actual_dip = max(ref_dips)
    # Build the correct value map for the selected mode
    if mode == 'kg':
        value_map = {d: kg for d, kg in zip(ref_dips, ref_kgs)}
    else:
        value_map = {d: round(kg/1.0285, 2) for d, kg in zip(ref_dips, ref_kgs)}
    sorted_dips = sorted(value_map.keys())
    output_data = []
    special_cases = {}
    for i in range(len(sorted_dips) - 1):
        current_dip = sorted_dips[i]
        next_dip = sorted_dips[i + 1]
        current_val = value_map[current_dip]
        next_val = value_map[next_dip]
        if next_dip - current_dip > 1.5:
            curr_whole_dip = int(current_dip)
            next_whole_dip = int(next_dip)
            if curr_whole_dip != next_whole_dip:
                step = find_consistent_step(current_dip, next_dip, current_val, next_val)
                for d in range(curr_whole_dip + 1, next_whole_dip + 1):
                    special_cases[d] = step
    dip = int(dip_start)
    while dip <= dip_end:
        if dip > max_actual_dip:
            break
        row = [dip]
        
        # Check if this DIP is an exact reference point
        if dip in value_map:
            # This is an exact reference point - use it directly
            base_value = value_map[dip]
            higher_dips = [d for d in sorted_dips if d > dip]
            lower_dips = [d for d in sorted_dips if d < dip]
            
            if higher_dips:
                next_dip = min(higher_dips)
                next_val = value_map[next_dip]
                step_size = find_consistent_step(dip, next_dip, base_value, next_val) * 10
            elif lower_dips:
                prev_dip = max(lower_dips)
                prev_val = value_map[prev_dip]
                step_size = find_consistent_step(prev_dip, dip, prev_val, base_value) * 10
            else:
                step_size = 2.5
            
            decimal_step = step_size / 10
            for i in range(10):
                val = round(base_value + i * decimal_step, 2)
                if dip + i/10 > max_actual_dip:
                    break
                row.append(val)
        elif dip in special_cases:
            step_size = special_cases[dip]
            lower_dips = [d for d in sorted_dips if d <= dip]
            higher_dips = [d for d in sorted_dips if d > dip]
            
            # Check if there's a reference point within this DIP range (dip.0 to dip.9)
            refs_in_range = [d for d in sorted_dips if dip < d < dip + 1]
            
            if refs_in_range:
                # There's a reference point within this row
                ref_dip = refs_in_range[0]
                ref_val = value_map[ref_dip]
                
                # Split the row at the reference point
                ref_decimal = int((ref_dip - dip) * 10)
                
                # Before reference point: use interpolation from lower DIP
                if lower_dips:
                    lower_dip = max(lower_dips)
                    lower_val = value_map[lower_dip]
                    step_before = find_consistent_step(lower_dip, ref_dip, lower_val, ref_val)
                    base_before = lower_val + (dip - lower_dip) * step_before * 10
                else:
                    step_before = step_size
                    base_before = ref_val - (ref_dip - dip) * step_before * 10
                
                # After reference point: use interpolation to next higher DIP
                higher_dips_after_ref = [d for d in sorted_dips if d > ref_dip]
                if higher_dips_after_ref:
                    higher_dip = min(higher_dips_after_ref)
                    higher_val = value_map[higher_dip]
                    step_after = find_consistent_step(ref_dip, higher_dip, ref_val, higher_val)
                else:
                    step_after = step_before
                
                # Generate values
                for i in range(10):
                    if i < ref_decimal:
                        val = round(base_before + i * step_before, 2)
                    else:
                        val = round(ref_val + (dip + i/10 - ref_dip) * step_after * 10, 2)
                    if dip + i/10 > max_actual_dip:
                        break
                    row.append(val)
            else:
                # No reference point in this range, use standard interpolation
                if lower_dips:
                    lower_dip = max(lower_dips)
                    lower_val = value_map[lower_dip]
                    base_value = lower_val + (dip - lower_dip) * step_size * 10
                elif higher_dips:
                    higher_dip = min(higher_dips)
                    higher_val = value_map[higher_dip]
                    base_value = higher_val - (higher_dip - dip) * step_size * 10
                else:
                    base_value = 0
                for i in range(10):
                    val = round(base_value + i * step_size, 2)
                    if dip + i/10 > max_actual_dip:
                        break
                    row.append(val)
        else:
            # DIP not in special cases and not an exact reference
            lower_dips = [d for d in sorted_dips if d <= dip]
            higher_dips = [d for d in sorted_dips if d > dip]
            
            if lower_dips and higher_dips:
                lower_dip = max(lower_dips)
                higher_dip = min(higher_dips)
                lower_val = value_map[lower_dip]
                higher_val = value_map[higher_dip]
                step_size = find_consistent_step(lower_dip, higher_dip, lower_val, higher_val) * 10
                base_value = lower_val + (dip - lower_dip) * step_size
            elif lower_dips:
                if len(lower_dips) >= 2:
                    last_dip = max(lower_dips)
                    second_last_idx = sorted_dips.index(last_dip) - 1
                    second_last_dip = sorted_dips[second_last_idx]
                    last_val = value_map[last_dip]
                    second_last_val = value_map[second_last_dip]
                    step_size = find_consistent_step(second_last_dip, last_dip, second_last_val, last_val) * 10
                    base_value = last_val + (dip - last_dip) * step_size
                else:
                    base_value = value_map[max(lower_dips)]
                    step_size = 2.5
            elif higher_dips:
                first_dip = min(higher_dips)
                if len(higher_dips) >= 2:
                    second_dip = sorted_dips[sorted_dips.index(first_dip) + 1]
                    first_val = value_map[first_dip]
                    second_val = value_map[second_dip]
                    step_size = find_consistent_step(first_dip, second_dip, first_val, second_val) * 10
                    base_value = first_val - (first_dip - dip) * step_size
                else:
                    base_value = value_map[min(higher_dips)]
                    step_size = 2.5
            else:
                base_value = 0
                step_size = 2.5
            
            decimal_step = step_size / 10
            for i in range(10):
                val = round(base_value + i * decimal_step, 2)
                if dip + i/10 > max_actual_dip:
                    break
                row.append(val)
        output_data.append(row)
        dip += 1
    headers = ['DIP', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
    return headers, output_data

# Overwrite download logic to use only manual records as reference

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
    headers, table = generate_dip_table_from_records(
        st.session_state['records'],
        dip_start=None,
        dip_end=None,
        mode='kg'
    )
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    col_width = pdf.w / (len(headers) + 1)
    row_height = pdf.font_size * 1.5
    pdf.set_fill_color(220, 220, 220)
    for header in headers:
        pdf.cell(col_width, row_height, str(header), border=1, align='C', fill=True)
    pdf.ln(row_height)
    for row in table:
        for item in row:
            pdf.cell(col_width, row_height, str(item), border=1, align='C')
        pdf.ln(row_height)
    return pdf.output(dest='S').encode('latin1')

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
            data=generate_raw_pdf(st.session_state['records']),
            file_name="output_raw.pdf",
            mime="application/pdf"
        )
    with col6:
        if st.button("Clear Records"):
            st.session_state['records'] = []
            st.experimental_rerun()
