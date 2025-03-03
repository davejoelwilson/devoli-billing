import streamlit as st
import pandas as pd
from devoli_billing import DevoliBilling
import os
import traceback
from customer_mapping import mapping_page
import re
from service_company import ServiceCompanyBilling
import time
from product_analysis import product_analysis_page

def init_session_state():
    """Initialize session state variables"""
    if 'page' not in st.session_state:
        st.session_state.page = 'home'
    if 'processed_data' not in st.session_state:
        st.session_state.processed_data = None
    if 'selected_companies' not in st.session_state:
        st.session_state.selected_companies = []
    if 'billing_processor' not in st.session_state:
        st.session_state.billing_processor = DevoliBilling()
    if 'service_processor' not in st.session_state:
        st.session_state.service_processor = ServiceCompanyBilling()
    if 'xero_connected' not in st.session_state:
        try:
            st.session_state.xero_connected = st.session_state.billing_processor.ensure_xero_connection()
        except:
            st.session_state.xero_connected = False

def navigate_to(page):
    st.session_state.page = page
    st.session_state.navigation_action = None
    st.rerun()

def home_page():
    st.title("Devoli Billing Processor")
    st.write("Welcome to the Devoli Billing Processor. Click 'Process New Invoice' to begin.")
    
    # Add a key to the button and use a callback
    if st.button("Process New Invoice", key="start_process"):
        st.session_state.navigation_action = 'process'
        navigate_to('process')

def calculate_customer_totals(df, customer=None):
    """Calculate minutes and charges using ServiceCompanyBilling"""
    processor = ServiceCompanyBilling()
    customer_df = df if customer is None else df[df['Customer Name'] == customer]
    
    # Get customer name for rate selection
    customer_name = customer if customer else customer_df['Customer Name'].iloc[0] if not customer_df.empty else ''
    
    if customer_name.strip().lower() == 'the service company':
        # Use the working process_billing method for Service Company
        results = processor.process_billing(customer_df)
        return {
            'minutes': 0,  # Not used for Service Company
            'ddi_charges': 0,  # Move base fee to calling charges
            'calling_charges': results['base_fee'] + sum(data['total'] for data in results['numbers'].values()),
            'total_charges': results['total']
        }
    else:
        # Regular customer processing using service_company.py methods
        ddi_charges = customer_df[customer_df['Description'].str.contains('DDI', na=False)]['Amount'].sum()
        call_data = processor.parse_call_data(customer_df)
        calling_charges = processor.calculate_standard_charges(call_data)
        total = float(ddi_charges) + float(calling_charges)
        
        return {
            'minutes': 0,
            'ddi_charges': float(ddi_charges),
            'calling_charges': float(calling_charges),
            'total_charges': total
        }

def find_invoices():
    """Find all invoices in the bills directory"""
    bills_dir = "bills"
    try:
        invoice_files = [f for f in os.listdir(bills_dir) if f.startswith("Invoice_") and f.endswith(".csv")]
        if not invoice_files:
            return []
            
        # Sort by date in filename (newest first)
        invoice_files.sort(key=lambda x: x.split('_')[2].split('.')[0], reverse=True)
        return invoice_files
    except Exception as e:
        st.error(f"Error finding invoices: {e}")
        return []

def process_page():
    st.title("Select Companies to Process")
    
    # Initialize session state if needed
    init_session_state()
    
    # Show Xero connection status
    if not st.session_state.xero_connected:
        st.warning("⚠️ Xero is not connected. You can still analyze invoices but cannot process them to Xero.")
    
    # Load mappings
    try:
        mapping_df = pd.read_csv('customer_mapping.csv')
        mappings = dict(zip(mapping_df['devoli_name'], mapping_df['actual_xero_name']))
    except:
        st.error("No customer mappings found. Please create mappings first.")
        return

    # Find all invoices
    invoice_files = find_invoices()
    if invoice_files:
        # Create a nice display format for the dropdown
        invoice_options = {}
        for f in invoice_files:
            # Extract date from filename (Invoice_134426_2024-12-31.csv)
            date_str = f.split('_')[2].split('.')[0]
            # Format as "December 2024 (Invoice_134426)"
            display_name = f"{pd.to_datetime(date_str).strftime('%B %Y')} ({f.split('_')[0]}_{f.split('_')[1]})"
            invoice_options[display_name] = f

        # Dropdown for invoice selection
        selected_invoice = st.selectbox(
            "Select Invoice to Process",
            options=list(invoice_options.keys()),
            index=0,  # Default to newest
            format_func=lambda x: x,  # Show full display name
            help="Select which invoice file to process",
            key="invoice_selector"  # Add a key for the selectbox
        )

        if selected_invoice:
            # Clear process_df when invoice changes
            if 'last_invoice' not in st.session_state or st.session_state.last_invoice != selected_invoice:
                if 'process_df' in st.session_state:
                    del st.session_state.process_df
                st.session_state.last_invoice = selected_invoice
            
            invoice_file = os.path.join("bills", invoice_options[selected_invoice])
            
            # Create a placeholder for the temporary message
            msg_placeholder = st.empty()
            msg_placeholder.info(f"Processing: {invoice_options[selected_invoice]}")
            
            # Sleep for 1 second then clear the message
            time.sleep(1)
            msg_placeholder.empty()
            
            df = pd.read_csv(invoice_file)
            
            # Normalize column names to be case-insensitive
            df.columns = df.columns.str.strip()  # Remove any whitespace
            column_mapping = {col: col.title() for col in df.columns}  # Convert to title case
            df = df.rename(columns=column_mapping)
            
            # Clean customer names by stripping whitespace
            df['Customer Name'] = df['Customer Name'].str.strip()
            
            try:
                # Get processors from session state
                devoli_processor = st.session_state.billing_processor
                service_processor = st.session_state.service_processor

                # Before processing any invoices, verify Xero connection
                if not devoli_processor.ensure_xero_connection():
                    st.error("Failed to connect to Xero. Please check your authentication.")
                    return

                # Use devoli_processor for customer loading
                voip_customers, voip_df = devoli_processor.load_voip_customers(df)
                
                # Use service_processor for billing calculations
                # Group customers by Xero name
                xero_groups = {}
                for customer in voip_customers:
                    # Clean customer name
                    clean_customer = customer.strip()
                    xero_name = mappings.get(clean_customer, 'NO MAPPING')
                    if xero_name != 'IGNORE':
                        if xero_name not in xero_groups:
                            xero_groups[xero_name] = []
                        xero_groups[xero_name].append(clean_customer)
                
                # Create selection table
                process_data = []
                for xero_name, customers in xero_groups.items():
                    # Combine data for all customers
                    combined_df = pd.concat([df[df['Customer Name'] == name] for name in customers])
                    
                    # Check if this is The Service Company
                    is_service_company = any(
                        str(name).strip().lower() == 'the service company' 
                        for name in customers
                    )
                    
                    if is_service_company:
                        # Process using service_processor
                        service_df = df[df['Customer Name'].str.strip() == 'The Service Company']
                        service_results = service_processor.process_billing(service_df)
                        
                        if service_results:
                            # Create line items for Xero
                            line_items = []
                            
                            # Base fee line item
                            line_items.append({
                                "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
                                "Quantity": 1.0,
                                "UnitAmount": service_results['base_fee'],
                                "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                "TaxType": "OUTPUT2"
                            })
                            
                            # Add regular number details if they exist
                            if service_results['regular_number']['calls']:
                                regular_desc = ['6492003366']
                                for call in service_results['regular_number']['calls']:
                                    regular_desc.append(f"{call['type']} Calls ({call['count']} calls - {call['duration']})")
                                
                                line_items.append({
                                    "Description": '\n'.join(regular_desc),
                                    "Quantity": 1.0,
                                    "UnitAmount": service_results['regular_number']['total'],
                                    "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                    "TaxType": "OUTPUT2"
                                })
                            
                            # Add toll free number details
                            for number, data in service_results['numbers'].items():
                                if data['calls']:
                                    number_desc = [number]
                                    for call in data['calls']:
                                        number_desc.append(f"{call['type']} ({call['count']} calls - {call['duration']})")
                                    
                                    line_items.append({
                                        "Description": '\n'.join(number_desc),
                                        "Quantity": 1.0,
                                        "UnitAmount": data['total'],
                                        "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                        "TaxType": "OUTPUT2"
                                    })
                            
                            # Calculate total before adding to process_data
                            total_amount = service_results['base_fee'] + service_results['regular_number']['total'] + sum(data['total'] for data in service_results['numbers'].values())
                            
                            # Only add to process_data if total is not $0
                            if total_amount > 0:
                                # Add to process_data for display in table
                                process_data.append({
                                    'Select': True,
                                    'Devoli Names': ', '.join(customers),
                                    'Xero Name': xero_name,
                                    'Description': '\n'.join(regular_desc),
                                    'Minutes': 0,  # Not used for Service Company
                                    'DDI Charges': 0,  # Base fee included in calling charges
                                    'Calling Charges': total_amount,
                                    'Total': total_amount,
                                    'Status': 'Ready'
                                })
                                
                                # Store line items for later use
                                st.session_state[f"line_items_{xero_name}"] = line_items
                            
                        else:
                            st.warning(f"No data found for The Service Company")
                    else:
                        # Regular customer processing
                        totals = calculate_customer_totals(combined_df)
                        invoice_desc = service_processor.format_call_description(service_processor.parse_call_data(combined_df))
                        
                        # After building invoice_desc
                        max_length = 3900
                        if len(invoice_desc) > max_length:
                            invoice_desc = invoice_desc[:max_length] + "\n... (truncated)"
                            st.warning("Description truncated for Xero compatibility")
                        
                        # Only add to process_data if calling charges are not $0
                        if totals['calling_charges'] > 0:
                            process_data.append({
                                'Select': True,
                                'Devoli Names': ', '.join(customers),
                                'Xero Name': xero_name,
                                'Description': invoice_desc,
                                'Minutes': totals['minutes'],
                                'DDI Charges': totals['ddi_charges'],
                                'Calling Charges': totals['calling_charges'],
                                'Total': totals['total_charges'],
                                'Status': 'Ready'
                            })
                
                if process_data:
                    # Set all Select values to False by default
                    for item in process_data:
                        item['Select'] = False
                    
                    # Create DataFrame with selection column
                    process_df = pd.DataFrame(process_data)
                    
                    # Calculate current month total from raw file
                    current_date = pd.to_datetime(invoice_file.split('_')[2].split('.')[0])
                    current_total = df['Amount'].sum()
                    
                    # Calculate previous month total
                    previous_date = current_date - pd.DateOffset(months=1)
                    previous_total = 0
                    
                    # Find previous month's file
                    for f in os.listdir("bills"):
                        if f.startswith("Invoice_") and f.endswith(".csv"):
                            file_date = pd.to_datetime(f.split('_')[2].split('.')[0])
                            if file_date.strftime('%Y-%m') == previous_date.strftime('%Y-%m'):
                                prev_df = pd.read_csv(os.path.join("bills", f))
                                prev_df.columns = prev_df.columns.str.strip()
                                prev_df = prev_df.rename(columns={col: col.title() for col in prev_df.columns})
                                previous_total = prev_df['Amount'].sum()
                                break
                    
                    # Show month totals
                    st.subheader("Monthly Totals")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric(
                            f"Current Month ({current_date.strftime('%B %Y')})",
                            f"${current_total:,.2f}"
                        )
                    
                    with col2:
                        st.metric(
                            f"Previous Month ({previous_date.strftime('%B %Y')})",
                            f"${previous_total:,.2f}"
                        )
                    
                    with col3:
                        change = current_total - previous_total
                        pct_change = ((current_total - previous_total) / previous_total * 100) if previous_total != 0 else 0
                        st.metric(
                            "Month over Month Change",
                            f"${change:+,.2f}",
                            f"{pct_change:+.1f}%",
                            delta_color="normal"
                        )
                    
                    st.divider()
                    
                    # Add Select All button and get its state
                    col1, col2 = st.columns([1, 9])  # Create two columns for layout
                    select_all = col1.button("Select All")
                    
                    # Store the DataFrame in session state if not already there
                    if 'process_df' not in st.session_state:
                        st.session_state.process_df = process_df.copy()
                    
                    # Update all checkboxes when Select All is clicked
                    if select_all:
                        st.session_state.process_df['Select'] = True
                    
                    # Display the dataframe with checkboxes and get edited version
                    edited_df = st.data_editor(
                        st.session_state.process_df[['Select', 'Xero Name', 'Description', 'Calling Charges']].assign(
                            **{
                                'Discount': lambda x: x.apply(lambda row: row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0, axis=1),
                                'Net Amount': lambda x: x.apply(lambda row: row['Calling Charges'] - (row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0), axis=1),
                                'Call Charges inc GST': lambda x: x.apply(lambda row: (row['Calling Charges'] - (row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0)) * 1.15, axis=1)
                            }
                        ),
                        hide_index=True,
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Process",
                                help="Select companies to process",
                                default=False
                            ),
                            "Xero Name": st.column_config.TextColumn(
                                "Company",
                                help="Company name in Xero"
                            ),
                            "Calling Charges": st.column_config.NumberColumn(
                                "Call Charges (ex GST)",
                                help="Call charges excluding GST",
                                format="$%.2f"
                            ),
                            "Discount": st.column_config.NumberColumn(
                                "Discount (6%)",
                                help="6% discount for SPARK customers",
                                format="$%.2f"
                            ),
                            "Net Amount": st.column_config.NumberColumn(
                                "Net Amount (ex GST)",
                                help="Amount after discount, before GST",
                                format="$%.2f"
                            ),
                            "Call Charges inc GST": st.column_config.NumberColumn(
                                "Call Charges (inc GST)",
                                help="Call charges including GST after discount",
                                format="$%.2f"
                            )
                        },
                        disabled=["Xero Name", "Description", "Calling Charges", "Discount", "Net Amount", "Call Charges inc GST"],
                        key="process_editor"
                    )
                    
                    # Add back the Devoli Names and Minutes columns to the edited DataFrame
                    edited_df = edited_df.join(st.session_state.process_df[['Devoli Names', 'Minutes']])
                    
                    # Update session state with edited values
                    st.session_state.process_df = edited_df.copy()
                    
                    # Get selected customers from the edited DataFrame
                    selected_customers = edited_df[edited_df['Select']]['Devoli Names'].tolist()
                    
                    # Show skipped customers
                    st.divider()
                    st.subheader("Skipped Customers")
                    for xero_name, customers in xero_groups.items():
                        # Check if this customer was skipped
                        if not any(xero_name == row['Xero Name'] for row in process_data):
                            st.info(f"ℹ️ Skipping {xero_name} - $0 calling charges")
                    
                    # Process button
                    if selected_customers:
                        process_button_text = "Process Selected Companies" if st.session_state.xero_connected else "Analyze Selected Companies (Xero Disabled)"
                        if st.button(process_button_text):
                            with st.spinner("Processing..."):
                                # Create containers for logging
                                log_container = st.container()
                                results_container = st.container()
                                
                                # Initialize progress bar
                                total_customers = sum(len(customer_list.split(', ')) for customer_list in selected_customers)
                                progress_bar = st.progress(0)
                                progress_text = st.empty()
                                
                                results = []
                                processed_count = 0
                                
                                for customer_list in selected_customers:
                                    for customer in customer_list.split(', '):
                                        try:
                                            clean_customer = customer.strip()
                                            xero_name = mappings[clean_customer]
                                            
                                            # Update progress
                                            processed_count += 1
                                            progress = processed_count / total_customers
                                            progress_bar.progress(progress)
                                            progress_text.text(f"Processing {processed_count} of {total_customers}: {clean_customer}")
                                            
                                            # Get the data for this customer
                                            customer_data = df[df['Customer Name'] == clean_customer]
                                            
                                            # Show processing status in a cleaner way
                                            with log_container:
                                                if st.session_state.xero_connected:
                                                    st.info(f"📝 Creating invoice for {clean_customer} → {xero_name} ({len(customer_data)} records)")
                                                else:
                                                    st.info(f"📝 Analyzing data for {clean_customer} → {xero_name} ({len(customer_data)} records)")
                                            
                                            # Initialize status and details
                                            status = 'Processing'
                                            details = 'Processing started'
                                            xero_invoice = None
                                            
                                            if st.session_state.xero_connected:
                                                try:
                                                    # Check if this is a $0 invoice
                                                    totals = calculate_customer_totals(customer_data)
                                                    
                                                    # Add debug for South Pacific Music
                                                    if 'south pacific music' in clean_customer.lower():
                                                        with log_container:
                                                            st.write(f"DEBUG - South Pacific Music totals: {totals}")
                                                            st.write(f"DEBUG - Calling charges: {totals['calling_charges']}")
                                                            st.write(f"DEBUG - Customer data shape: {customer_data.shape}")
                                                            call_data = customer_data[customer_data['Description'].str.contains('Calls', case=False, na=False)]
                                                            st.write(f"DEBUG - Call data rows: {len(call_data)}")
                                                            if not call_data.empty:
                                                                st.write(f"DEBUG - First call row: {call_data.iloc[0].to_dict()}")
                                                    
                                                    # Check if this is truly a $0 invoice - no calls at all
                                                    call_data = customer_data[customer_data['Description'].str.contains('Calls', case=False, na=False)]
                                                    if totals['calling_charges'] == 0 and len(call_data) == 0:
                                                        status = 'Skipped'
                                                        details = 'Skipped - $0 invoice'
                                                        invoice_number = 'Skipped'
                                                        with log_container:
                                                            st.info(f"ℹ️ Skipping {clean_customer} - $0 invoice")
                                                        results.append({
                                                            'Customer': clean_customer,
                                                            'Status': status,
                                                            'Details': details,
                                                            'Xero Invoice': invoice_number
                                                        })
                                                        continue
                                                    
                                                    # If we have call data but charges are 0, use the Amount column directly
                                                    if totals['calling_charges'] == 0 and len(call_data) > 0:
                                                        with log_container:
                                                            st.warning(f"⚠️ {clean_customer} has call data but calculated charges are 0, using Amount column")
                                                        
                                                        # Try to recalculate using DevoliBilling's method for consistency
                                                        billing = DevoliBilling()
                                                        recalculated_charges, _ = billing.calculate_call_charges(call_data)
                                                        
                                                        if recalculated_charges > 0:
                                                            with log_container:
                                                                st.success(f"✅ Recalculated charges: ${recalculated_charges}")
                                                            totals['calling_charges'] = recalculated_charges
                                                        else:
                                                            # Fall back to Amount column if recalculation still gives 0
                                                            totals['calling_charges'] = call_data['Amount'].sum()
                                                            with log_container:
                                                                st.info(f"ℹ️ Using Amount column: ${totals['calling_charges']}")
                                                    
                                                    # Format dates
                                                    invoice_date = pd.to_datetime(invoice_file.split('_')[2].split('.')[0])
                                                    due_date = invoice_date + pd.Timedelta(days=20)
                                                    
                                                    # Set reference
                                                    reference = "Devoli Calling Charges"
                                                    
                                                    if clean_customer.strip().lower() == 'the service company':
                                                        service_df = df[df['Customer Name'].str.strip() == 'The Service Company']
                                                        service_results = service_processor.process_billing(service_df)
                                                        total_amount = service_results['base_fee'] + service_results['regular_number']['total'] + sum(data['total'] for data in service_results['numbers'].values())
                                                        
                                                        # Check if this is a $0 invoice
                                                        if total_amount == 0:
                                                            status = 'Skipped'
                                                            details = 'Skipped - $0 invoice'
                                                            invoice_number = 'Skipped'
                                                            with log_container:
                                                                st.info(f"ℹ️ Skipping {clean_customer} - $0 invoice")
                                                            results.append({
                                                                'Customer': clean_customer,
                                                                'Status': status,
                                                                'Details': details,
                                                                'Xero Invoice': invoice_number
                                                            })
                                                            continue
                                                        
                                                        # Generate line items for The Service Company
                                                        line_items = []
                                                        
                                                        # Base fee line item
                                                        line_items.append({
                                                            "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
                                                            "Quantity": 1.0,
                                                            "UnitAmount": service_results['base_fee'],
                                                            "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                                            "TaxType": "OUTPUT2"
                                                        })
                                                        
                                                        # Add regular number details if they exist
                                                        if service_results['regular_number']['calls']:
                                                            regular_desc = ['6492003366']
                                                            for call in service_results['regular_number']['calls']:
                                                                regular_desc.append(f"{call['type']} Calls ({call['count']} calls - {call['duration']})")
                                                            
                                                            line_items.append({
                                                                "Description": '\n'.join(regular_desc),
                                                                "Quantity": 1.0,
                                                                "UnitAmount": service_results['regular_number']['total'],
                                                                "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                                                "TaxType": "OUTPUT2"
                                                            })
                                                        
                                                        # Add toll free number details
                                                        for number, data in service_results['numbers'].items():
                                                            if data['calls']:
                                                                number_desc = [number]
                                                                for call in data['calls']:
                                                                    number_desc.append(f"{call['type']} ({call['count']} calls - {call['duration']})")
                                                                
                                                                line_items.append({
                                                                    "Description": '\n'.join(number_desc),
                                                                    "Quantity": 1.0,
                                                                    "UnitAmount": data['total'],
                                                                    "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                                                    "TaxType": "OUTPUT2"
                                                                })
                                                        
                                                        # Create Xero invoice with parameters
                                                        xero_invoice = devoli_processor.create_xero_invoice(
                                                            clean_customer,
                                                            service_df,
                                                            invoice_params={
                                                                'date': invoice_date.strftime('%Y-%m-%d'),
                                                                'due_date': due_date.strftime('%Y-%m-%d'),
                                                                'status': 'DRAFT',
                                                                'type': 'ACCREC',
                                                                'line_amount_types': 'Exclusive',
                                                                'reference': reference,
                                                                'line_items': line_items  # Pass the calculated line items here
                                                            }
                                                        )
                                                        status = 'Success'
                                                        details = f"Total amount: ${total_amount:,.2f}"
                                                    else:
                                                        totals = calculate_customer_totals(customer_data)
                                                        
                                                        # Format invoice description
                                                        invoice_desc = service_processor.format_call_description(service_processor.parse_call_data(customer_data))
                                                        max_length = 3900
                                                        if len(invoice_desc) > max_length:
                                                            invoice_desc = invoice_desc[:max_length] + "\n... (truncated)"
                                                        
                                                        # Create Xero invoice with parameters
                                                        xero_invoice = devoli_processor.create_xero_invoice(
                                                            clean_customer,
                                                            customer_data,
                                                            invoice_params={
                                                                'date': invoice_date.strftime('%Y-%m-%d'),
                                                                'due_date': due_date.strftime('%Y-%m-%d'),
                                                                'status': 'DRAFT',
                                                                'type': 'ACCREC',
                                                                'line_amount_types': 'Exclusive',
                                                                'reference': reference,
                                                                'description': invoice_desc,
                                                                'line_amount': totals['calling_charges']
                                                            }
                                                        )
                                                        status = 'Success'
                                                        details = f"Calling charges: ${totals['calling_charges']:,.2f}"
                                                        
                                                        # Add discount line for SPARK customers
                                                        if 'SPARK' in clean_customer.upper():
                                                            discount_amount = totals['calling_charges'] * 0.06
                                                            devoli_processor.add_line_item(
                                                                xero_invoice,
                                                                {
                                                                    "Description": "Spark Discount Taken",
                                                                    "Quantity": totals['calling_charges'],
                                                                    "UnitAmount": -0.06,  # Negative to represent discount
                                                                    "AccountCode": "45900",  # SPARK Sales account
                                                                    "TaxType": "OUTPUT2"  # 15% GST
                                                                }
                                                            )
                                                        
                                                        # Log the invoice number for debugging
                                                        with log_container:
                                                            if isinstance(xero_invoice, dict):
                                                                if 'Invoices' in xero_invoice and xero_invoice['Invoices']:
                                                                    invoice_num = xero_invoice['Invoices'][0].get('InvoiceNumber')
                                                                    if invoice_num:
                                                                        st.success(f"✅ Created Xero invoice #{invoice_num}")
                                                                    else:
                                                                        st.warning("⚠️ Invoice created but no number returned")
                                                                else:
                                                                    st.warning("⚠️ Invoice created but unexpected response format")
                                                            else:
                                                                st.warning("⚠️ Invoice created but response is not in expected format")
                                                except Exception as xe:
                                                    status = 'Failed'
                                                    details = f"Xero Error: {str(xe)}"
                                                    xero_invoice = None
                                                    with log_container:
                                                        st.error(f"❌ Error creating invoice for {clean_customer}: {str(xe)}")
                                            else:
                                                # Just analyze the data without creating Xero invoice
                                                if clean_customer.strip().lower() == 'the service company':
                                                    service_df = df[df['Customer Name'].str.strip() == 'The Service Company']
                                                    service_results = service_processor.process_billing(service_df)
                                                    total_amount = service_results['base_fee'] + service_results['regular_number']['total'] + sum(data['total'] for data in service_results['numbers'].values())
                                                    status = 'Analyzed'
                                                    details = f"Total amount: ${total_amount:,.2f}"
                                                else:
                                                    totals = calculate_customer_totals(customer_data)
                                                    status = 'Analyzed'
                                                    details = f"Calling charges: ${totals['calling_charges']:,.2f}"
                                                
                                                with log_container:
                                                    st.success(f"✅ Analysis complete for {clean_customer}")
                                            
                                            # Add invoice number to results with better handling
                                            invoice_number = '-'
                                            if isinstance(xero_invoice, dict):
                                                # Try to get invoice number from nested structure first
                                                if 'Invoices' in xero_invoice and xero_invoice['Invoices']:
                                                    invoice_number = xero_invoice['Invoices'][0].get('InvoiceNumber', '-')
                                                # Fallback to direct access
                                                elif 'InvoiceNumber' in xero_invoice:
                                                    invoice_number = xero_invoice['InvoiceNumber']
                                            
                                            results.append({
                                                'Customer': clean_customer,
                                                'Status': status,
                                                'Details': details,
                                                'Xero Invoice': invoice_number
                                            })
                                            
                                        except Exception as e:
                                            with log_container:
                                                st.error(f"❌ System error processing {clean_customer}: {str(e)}")
                                            results.append({
                                                'Customer': clean_customer,
                                                'Status': 'Error',
                                                'Details': f"System Error: {str(e)}",
                                                'Xero Invoice': '-'
                                            })
                                
                                # Clear progress indicators
                                progress_bar.empty()
                                progress_text.empty()
                                
                                # Show final results in a clean table
                                with results_container:
                                    st.subheader("📊 Processing Summary")
                                    results_df = pd.DataFrame(results)
                                    
                                    # Count statuses
                                    status_counts = results_df['Status'].value_counts()
                                    col1, col2, col3, col4 = st.columns(4)
                                    
                                    with col1:
                                        st.metric("Total", len(results))
                                    with col2:
                                        if st.session_state.xero_connected:
                                            st.metric("Success", status_counts.get('Success', 0))
                                        else:
                                            st.metric("Analyzed", status_counts.get('Analyzed', 0))
                                    with col3:
                                        st.metric("Skipped", status_counts.get('Skipped', 0))
                                    with col4:
                                        st.metric("Failed", status_counts.get('Failed', 0) + status_counts.get('Error', 0))
                                    
                                    st.dataframe(
                                        results_df,
                                        column_config={
                                            "Customer": "Company",
                                            "Status": st.column_config.TextColumn(
                                                "Status",
                                                help="Processing status for each company"
                                            ),
                                            "Details": "Details",
                                            "Xero Invoice": st.column_config.TextColumn(
                                                "Xero Invoice #",
                                                help="Xero invoice number if created"
                                            )
                                        },
                                        hide_index=True
                                    )
                    else:
                        st.warning("No companies ready to process. Please check mappings.")
                else:
                    st.warning("No VoIP customers found in invoice.")
                
            except Exception as e:
                st.error(f"Error processing invoice: {str(e)}")
                st.code(traceback.format_exc())
        else:
            st.write("Please select an invoice to process")
    else:
        st.error("No invoice found in bills directory")

def select_page():
    st.title("Select Companies to Process")
    
    # Debug print
    st.write("DEBUG: Processed data:", st.session_state.processed_data is not None)
    
    if st.session_state.processed_data is None:
        st.error("No processed data available")
        if st.button("Return to Home"):
            st.session_state.page = 'home'
            st.rerun()
        return
    
    try:
        # Get customers and ensure they're all strings
        ddi_customers = {str(x) for x in st.session_state.processed_data['products']['ddi_charges'].keys() if x is not None}
        call_customers = {str(x) for x in st.session_state.processed_data['calls'].keys() if x is not None} if st.session_state.processed_data.get('calls') else set()
        
        # Debug customer data
        st.write("DEBUG: DDI customers:", list(ddi_customers)[:5])
        st.write("DEBUG: Call customers:", list(call_customers)[:5])
        
        # Filter out empty strings and None values, convert all to strings
        all_customers = sorted(
            x for x in ddi_customers.union(call_customers) 
            if x and not pd.isna(x) and str(x).strip()
        )
        
        st.write(f"Found {len(all_customers)} customers")
        
        # Use multiselect without form
        selected = st.multiselect(
            "Select companies:",
            options=all_customers,
            default=all_customers,
            key="company_selector"
        )
        
        # Regular button instead of form submit
        if st.button("Process Selected Companies", key="process_selected", type="primary"):
            if selected:
                st.session_state.selected_companies = selected
                st.session_state.page = 'confirm'
                st.rerun()
            else:
                st.warning("Please select at least one company")
        
        # Add debug info
        st.write("DEBUG: Selected companies:", selected)
        st.write("DEBUG: Button clicked")
    
    except Exception as e:
        st.error(f"Error: {str(e)}")
        st.code(traceback.format_exc())
        st.write("DEBUG: Data structure:", {
            'products': type(st.session_state.processed_data['products']),
            'ddi_charges': type(st.session_state.processed_data['products']['ddi_charges']),
            'calls': type(st.session_state.processed_data.get('calls'))
        })

def confirm_page():
    st.title("Processing Results")
    
    # Initialize session state if needed
    init_session_state()
    
    if not st.session_state.selected_companies:
        st.error("No companies selected for processing")
        return
    
    try:
        # Get processor from session state
        processor = st.session_state.billing_processor
        
        # Process each selected company
        results = []
        for company in st.session_state.selected_companies:
            try:
                # Get company data from both products and calls
                company_data = {
                    'ddi_charges': st.session_state.processed_data['products']['ddi_charges'].get(company, []),
                    'calling_charges': st.session_state.processed_data['calls'].get(company, {})
                }
                
                # Create Xero invoice
                result = processor.create_xero_invoice(company, company_data)
                
                # Add to results
                results.append({
                    'Company': company,
                    'Status': 'Success' if result else 'Failed',
                    'DDI Charges': len(company_data['ddi_charges']),
                    'Has Calling Charges': bool(company_data['calling_charges']),
                    'Details': str(result) if result else 'Failed to create invoice'
                })
                
            except Exception as e:
                results.append({
                    'Company': company,
                    'Status': 'Error',
                    'DDI Charges': 0,
                    'Has Calling Charges': False,
                    'Details': str(e)
                })
        
        # Display results
        results_df = pd.DataFrame(results)
        st.dataframe(results_df)
        
        # Show summary
        st.write(f"Processed {len(results)} companies:")
        st.write(f"- Successful: {len(results_df[results_df['Status'] == 'Success'])}")
        st.write(f"- Failed: {len(results_df[results_df['Status'] == 'Failed'])}")
        st.write(f"- Errors: {len(results_df[results_df['Status'] == 'Error'])}")
        
        # Return home button
        if st.button("Start New Process", key="goto_home"):
            # Clear all processing data
            st.session_state.processed_data = None
            st.session_state.selected_companies = []
            st.session_state.page = 'home'
            st.rerun()
            
    except Exception as e:
        st.error(f"Error initializing processor: {str(e)}")
        st.code(traceback.format_exc())

def process_customer(customer_name, billing_data):
    """Process a single customer's billing data"""
    # Handle trailing spaces in customer names consistently
    billing_data['Customer Name'] = billing_data['Customer Name'].str.strip()
    customer_name = customer_name.strip()
    customer_data = billing_data[billing_data['Customer Name'] == customer_name]
    
    # Process TFree numbers consistently
    tfree_numbers = customer_data[customer_data['Short Description'].str.startswith('64800', na=False)]['Short Description'].unique()
    
    # Rest of processing...

def process_selected_companies(selected_companies, df):
    """Process selected companies and create invoices"""
    results = []
    
    for company in selected_companies:
        try:
            # Calculate totals first
            company_df = df[df['Customer Name'] == company]
            calculated_results = calculate_customer_totals(df, company)
            
            # Create invoice with pre-calculated results
            invoice_params = {
                'pre_calculated_results': calculated_results,  # Pass the results
                'date': df['Date'].iloc[0],
                'due_date': (pd.to_datetime(df['Date'].iloc[0]) + pd.Timedelta(days=14)).strftime('%Y-%m-%d')
            }
            
            invoice = st.session_state.billing_processor.create_xero_invoice(
                company, 
                company_df,
                invoice_params=invoice_params
            )
            
            if invoice:
                invoice_number = invoice.get('Invoices', [{}])[0].get('InvoiceNumber', 'Created')
                results.append({
                    'customer': company,
                    'status': 'Success',
                    'details': 'Invoice created successfully',
                    'invoice_number': invoice_number
                })
            else:
                results.append({
                    'customer': company,
                    'status': 'Failed',
                    'details': 'No invoice response received',
                    'invoice_number': 'N/A'
                })
                
        except Exception as e:
            results.append({
                'customer': company,
                'status': 'Failed',
                'details': str(e),
                'invoice_number': 'N/A'
            })
            
    return results

def main():
    st.set_page_config(
        page_title="Devoli Billing",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': None,
            'Report a bug': None,
            'About': None
        }
    )
    
    # Set complete light theme
    st.markdown("""
        <style>
        /* Main app */
        .stApp {
            background-color: white;
            color: black;
        }
        
        /* Sidebar */
        section[data-testid="stSidebar"] {
            background-color: #f8f9fa;
            color: black;
        }
        
        /* Buttons */
        .stButton button {
            background-color: #ff4b4b;
            color: white;
            border: none;
        }
        
        /* Dataframe */
        .stDataFrame {
            background-color: white;
        }
        
        /* Text inputs */
        .stTextInput input {
            background-color: white;
            color: black;
        }
        
        /* Dropdowns */
        .stSelectbox select {
            background-color: white;
            color: black;
        }
        
        /* Progress bar */
        .stProgress > div > div {
            background-color: #ff4b4b;
        }
        
        /* Info boxes */
        .stAlert {
            background-color: white;
            color: black;
        }
        
        /* Radio buttons */
        .stRadio label {
            color: black;
        }
        
        /* Headers */
        h1, h2, h3, h4, h5, h6 {
            color: black;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    init_session_state()
    
    # Updated navigation
    page = st.sidebar.radio("Select Page", ["Process Invoices", "Product Analysis", "Customer Mapping"])
    
    if page == "Customer Mapping":
        mapping_page()
    elif page == "Process Invoices":
        process_page()
    else:
        product_analysis_page()

if __name__ == "__main__":
    main()
