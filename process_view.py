import streamlit as st
import pandas as pd
from devoli_billing import DevoliBilling

def calculate_customer_totals(df, customer):
    """Calculate minutes and charges for a customer"""
    customer_df = df[df['Customer Name'] == customer]
    
    # Calculate total minutes
    call_rows = customer_df[customer_df['Description'].str.contains('Calling|Voice', na=False, case=False)]
    total_minutes = call_rows['Quantity'].sum() if 'Quantity' in call_rows else 0
    
    # Calculate DDI charges
    ddi_rows = customer_df[customer_df['Description'].str.contains('DDI', na=False)]
    ddi_charges = ddi_rows['Amount'].sum()
    
    # Total charges
    total_charges = customer_df['Amount'].sum()
    
    return {
        'minutes': int(total_minutes),
        'ddi_charges': float(ddi_charges),
        'total_charges': float(total_charges)
    }

def process_page():
    st.title("Process Invoices")
    
    # Load customer mappings
    try:
        mapping_df = pd.read_csv('customer_mapping.csv')
        mappings = dict(zip(mapping_df['devoli_name'], mapping_df['actual_xero_name']))
    except:
        st.error("No customer mappings found. Please create mappings first.")
        return
    
    # File upload
    uploaded_file = st.file_uploader("Upload Devoli Invoice CSV", type=['csv'])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        # Get VoIP customers
        processor = DevoliBilling()
        voip_customers, voip_df = processor.load_voip_customers(df)
        
        # Create processing table
        process_data = []
        for customer in voip_customers:
            xero_name = mappings.get(customer, 'NO MAPPING')
            totals = calculate_customer_totals(df, customer)
            
            process_data.append({
                'Devoli Name': customer,
                'Xero Name': xero_name,
                'Minutes': totals['minutes'],
                'DDI Charges': f"${totals['ddi_charges']:.2f}",
                'Total Charges': f"${totals['total_charges']:.2f}",
                'Status': 'Ready' if xero_name != 'NO MAPPING' else 'Missing Mapping'
            })
        
        # Show processing table
        st.write("### Customers to Process")
        process_df = pd.DataFrame(process_data)
        st.dataframe(process_df)
        
        # Process button
        ready_to_process = len([x for x in process_data if x['Status'] == 'Ready'])
        if ready_to_process > 0:
            if st.button(f"Process {ready_to_process} Customers"):
                with st.spinner("Processing invoices..."):
                    # Process logic here
                    st.success(f"Processed {ready_to_process} customers")
        else:
            st.warning("No customers ready to process. Please check mappings.")

if __name__ == "__main__":
    process_page() 