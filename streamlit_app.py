import streamlit as st
import pandas as pd
from devoli_billing import DevoliBilling
import os
import traceback
from customer_mapping import mapping_page
import re
from service_company import ServiceCompanyBilling
import time

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
            help="Select which invoice file to process"
        )

        if selected_invoice:
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
                            
                            # Build description for display
                            invoice_desc = ["Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)"]
                            
                            # Add regular number details
                            if service_results['regular_number']['calls']:
                                regular_desc = ['6492003366']
                                for call in service_results['regular_number']['calls']:
                                    regular_desc.append(f"{call['type']} Calls ({call['count']} calls - {call['duration']})")
                                invoice_desc.extend(regular_desc)
                                
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
                                    invoice_desc.extend(number_desc)
                                    
                                    line_items.append({
                                        "Description": '\n'.join(number_desc),
                                        "Quantity": 1.0,
                                        "UnitAmount": data['total'],
                                        "AccountCode": devoli_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                                        "TaxType": "OUTPUT2"
                                    })
                            
                            # Calculate total before adding to process_data
                            total_amount = service_results['base_fee'] + sum(data['total'] for data in service_results['numbers'].values())
                            
                            # Only add to process_data if total is not $0
                            if total_amount > 0:
                                # Add to process_data for display in table
                                process_data.append({
                                    'Select': True,
                                    'Devoli Names': ', '.join(customers),
                                    'Xero Name': xero_name,
                                    'Description': '\n'.join(invoice_desc),
                                    'Minutes': 0,  # Not used for Service Company
                                    'DDI Charges': 0,  # Base fee included in calling charges
                                    'Calling Charges': total_amount,
                                    'Total': total_amount,
                                    'Status': 'Ready'
                                })
                                
                                # Store line items for later use
                                st.session_state[f"line_items_{xero_name}"] = line_items
                            else:
                                st.info(f"ℹ️ Skipping {xero_name} - $0 invoice")
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
                        else:
                            st.info(f"ℹ️ Skipping {xero_name} - $0 calling charges")
                
                if process_data:
                    # Set all Select values to False by default
                    for item in process_data:
                        item['Select'] = False
                    
                    # Create DataFrame with selection column
                    process_df = pd.DataFrame(process_data)
                    
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
                        st.session_state.process_df,
                        hide_index=True,
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Process",
                                help="Select companies to process",
                                default=False
                            )
                        },
                        disabled=["Devoli Names", "Xero Name", "Description", "Minutes", "DDI Charges", "Calling Charges", "Total", "Status"],
                        key="process_editor"
                    )
                    
                    # Update session state with edited values
                    st.session_state.process_df = edited_df.copy()
                    
                    # Get selected customers from the edited DataFrame
                    selected_customers = edited_df[edited_df['Select']]['Devoli Names'].tolist()
                    
                    # Process button
                    if selected_customers:
                        if st.button(f"Process {len(selected_customers)} Selected Companies"):
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
                                                st.info(f"📝 Creating invoice for {clean_customer} → {xero_name} ({len(customer_data)} records)")
                                            
                                            # Create invoice with more detailed error handling
                                            try:
                                                # Prepare invoice parameters
                                                invoice_date = pd.to_datetime(invoice_file.split('_')[2].split('.')[0])  # Get date from filename
                                                due_date = invoice_date + pd.Timedelta(days=20)  # Due in 20 days
                                                reference = invoice_date.strftime('%b') + ' Devoli Calling Charges'
                                                if clean_customer.strip().lower() == 'the service company':
                                                    service_df = df[df['Customer Name'].str.strip() == 'The Service Company']
                                                    service_results = service_processor.process_billing(service_df)
                                                    
                                                    # Get stored line items for The Service Company
                                                    line_items = st.session_state.get(f"line_items_{xero_name}")
                                                    if not line_items:
                                                        raise ValueError("Line items not found for The Service Company")
                                                    
                                                    # Calculate total amount
                                                    total_amount = sum(item.get('UnitAmount', 0) for item in line_items)
                                                    
                                                    # Skip if total is $0
                                                    if total_amount == 0:
                                                        with log_container:
                                                            st.warning(f"⚠️ Skipping {clean_customer} - $0 invoice")
                                                        results.append({
                                                            'Customer': clean_customer,
                                                            'Status': 'Skipped',
                                                            'Details': 'Invoice total is $0 - skipped'
                                                        })
                                                        continue
                                                    
                                                    with log_container:
                                                        st.text(f"💰 Total amount: ${total_amount:.2f}")
                                                    
                                                    result = devoli_processor.create_xero_invoice(
                                                        clean_customer,
                                                        service_df,
                                                        invoice_params={
                                                            'date': pd.to_datetime(invoice_file.split('_')[2].split('.')[0]).strftime('%Y-%m-%d'),
                                                            'due_date': (pd.to_datetime(invoice_file.split('_')[2].split('.')[0]) + pd.Timedelta(days=20)).strftime('%Y-%m-%d'),
                                                            'status': 'DRAFT',
                                                            'type': 'ACCREC',
                                                            'line_amount_types': 'Exclusive',
                                                            'reference': reference,
                                                            'line_items': line_items
                                                        }
                                                    )
                                                else:
                                                    # Regular customer processing (existing code)
                                                    invoice_desc = service_processor.format_call_description(service_processor.parse_call_data(customer_data))
                                                    max_length = 3900
                                                    if len(invoice_desc) > max_length:
                                                        invoice_desc = invoice_desc[:max_length] + "\n... (truncated)"
                                                        st.warning("Description truncated for Xero compatibility")
                                                    totals = calculate_customer_totals(customer_data)
                                                    pricing = round(totals['calling_charges'], 2)  # Use calling charges instead of total
                                                    
                                                    # Skip if calling charges are $0
                                                    if pricing == 0:
                                                        with log_container:
                                                            st.warning(f"⚠️ Skipping {clean_customer} - $0 calling charges")
                                                        results.append({
                                                            'Customer': clean_customer,
                                                            'Status': 'Skipped',
                                                            'Details': 'Calling charges are $0 - skipped'
                                                        })
                                                        continue
                                                    
                                                    with log_container:
                                                        st.text(f"💰 Calling charges: ${pricing:.2f}")
                                                    
                                                    result = devoli_processor.create_xero_invoice(
                                                        clean_customer,
                                                        customer_data,
                                                        invoice_params={
                                                            'date': pd.to_datetime(invoice_file.split('_')[2].split('.')[0]).strftime('%Y-%m-%d'),
                                                            'due_date': (pd.to_datetime(invoice_file.split('_')[2].split('.')[0]) + pd.Timedelta(days=20)).strftime('%Y-%m-%d'),
                                                            'status': 'DRAFT',
                                                            'type': 'ACCREC',
                                                            'line_amount_types': 'Exclusive',
                                                            'reference': reference,
                                                            'description': invoice_desc,
                                                            'line_amount': pricing  # This will now be just the calling charges
                                                        }
                                                    )
                                                
                                                status = 'Success' if result else 'Failed'
                                                details = str(result) if result else 'Invoice creation returned None'
                                                
                                                # Show success/failure in a cleaner way
                                                with log_container:
                                                    if status == 'Success':
                                                        st.success(f"✅ Successfully created invoice for {clean_customer}")
                                                    else:
                                                        st.error(f"❌ Failed to create invoice for {clean_customer}")
                                                
                                            except Exception as xe:
                                                status = 'Failed'
                                                details = f"Xero Error: {str(xe)}"
                                                with log_container:
                                                    st.error(f"❌ Error creating invoice for {clean_customer}: {str(xe)}")
                                            
                                            results.append({
                                                'Customer': clean_customer,
                                                'Status': status,
                                                'Details': details
                                            })
                                            
                                        except Exception as e:
                                            with log_container:
                                                st.error(f"❌ System error processing {clean_customer}: {str(e)}")
                                            results.append({
                                                'Customer': clean_customer,
                                                'Status': 'Error',
                                                'Details': f"System Error: {str(e)}"
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
                                        st.metric("Success", status_counts.get('Success', 0))
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
                                            "Details": "Details"
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
    
    # Navigation
    page = st.sidebar.radio("Select Page", ["Customer Mapping", "Process Invoices"])
    
    if page == "Customer Mapping":
        mapping_page()
    else:
        process_page()

if __name__ == "__main__":
    main()
