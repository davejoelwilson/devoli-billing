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
from log_database import LogDatabase
from log_history_page import log_history_page
import datetime

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
    if 'log_db' not in st.session_state:
        st.session_state.log_db = LogDatabase()
    if 'current_file_log_id' not in st.session_state:
        st.session_state.current_file_log_id = None

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
                # Reset current file log ID when invoice changes
                st.session_state.current_file_log_id = None
            
            invoice_file = os.path.join("bills", invoice_options[selected_invoice])
            invoice_filename = invoice_options[selected_invoice]
            
            # Create a placeholder for the temporary message
            msg_placeholder = st.empty()
            msg_placeholder.info(f"Processing: {invoice_options[selected_invoice]}")
            
            # Sleep for 1 second then clear the message
            time.sleep(1)
            msg_placeholder.empty()
            
            df = pd.read_csv(invoice_file)
            # Set the name attribute for tracking
            df.name = invoice_file
            
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
                
                # Log file processing if not already logged
                if 'current_file_log_id' not in st.session_state or not st.session_state.current_file_log_id:
                    file_log_id = st.session_state.log_db.log_file_processing(invoice_filename)
                    st.session_state.current_file_log_id = file_log_id
                
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
                            # Add to process_data for display in table
                            ddi_charges = 0
                            calling_charges = service_results['base_fee'] + sum(data['total'] for data in service_results['numbers'].values())
                            total = service_results['total']
                            
                            # Check if invoice has already been processed
                            already_processed = st.session_state.log_db.check_if_processed(invoice_filename, xero_name)
                            
                            process_data.append({
                                'Select': False,  # Always set to False by default
                                'Devoli Names': ', '.join(customers),
                                'Xero Name': xero_name,
                                'DDI Charges': f"${ddi_charges:.2f}",
                                'Calling Charges': f"${calling_charges:.2f}",
                                'Total': f"${total:.2f}",
                                'Already Processed': already_processed,
                                'customer_data': service_df
                            })
                    else:
                        # Skip if no data
                        if combined_df.empty:
                            continue
                            
                        # Standard calculation 
                        totals = calculate_customer_totals(combined_df)
                        
                        # Skip if $0 total
                        if totals['total_charges'] == 0:
                            continue
                        
                        # Check if invoice has already been processed
                        already_processed = st.session_state.log_db.check_if_processed(invoice_filename, xero_name)
                        
                        # Add to process data
                        process_data.append({
                            'Select': False,  # Always set to False by default
                            'Devoli Names': ', '.join(customers),
                            'Xero Name': xero_name,
                            'DDI Charges': f"${totals['ddi_charges']:.2f}",
                            'Calling Charges': f"${totals['calling_charges']:.2f}",
                            'Total': f"${totals['total_charges']:.2f}",
                            'Already Processed': already_processed,
                            'customer_data': combined_df  # Store customer data for later processing
                        })
                
                # Create dataframe from process_data
                if process_data:
                    df_data = []
                    for item in process_data:
                        df_data.append({
                            'Select': item['Select'],
                            'Devoli Names': item['Devoli Names'],
                            'Xero Name': item['Xero Name'],
                            'DDI Charges': item['DDI Charges'],
                            'Calling Charges': item['Calling Charges'],
                            'Total': item['Total'],
                            'Already Processed': item['Already Processed']
                        })
                    
                    process_df = pd.DataFrame(df_data)
                    
                    # Add process_df to session state
                    st.session_state.process_df = process_df
                    
                    # Add process_data to session state
                    st.session_state.process_data = process_data
                    
                    # Display dataframe
                    st.write(f"Found {len(process_data)} customers with charges")
                    
                    # Create a dataframe with checkboxes
                    edited_df = st.data_editor(
                        process_df,
                        column_config={
                            "Select": st.column_config.CheckboxColumn(
                                "Process",
                                help="Select customers to process",
                                default=False
                            ),
                            "Already Processed": st.column_config.CheckboxColumn(
                                "Already Processed",
                                help="Customer was already processed",
                                disabled=True
                            )
                        },
                        disabled=["Devoli Names", "Xero Name", "DDI Charges", "Calling Charges", "Total", "Already Processed"],
                        hide_index=True,
                        use_container_width=True,
                        key="process_editor"
                    )
                    
                    # Add 'Select All' button
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Select All", key="select_all"):
                            # Update process_df to select all rows that aren't already processed
                            updated_df = st.session_state.process_df.copy()
                            updated_df['Select'] = ~updated_df['Already Processed']
                            st.session_state.process_df = updated_df
                            st.rerun()
                    
                    with col2:
                        if st.button("Clear All", key="clear_all"):
                            # Update process_df to deselect all rows
                            updated_df = st.session_state.process_df.copy()
                            updated_df['Select'] = False
                            st.session_state.process_df = updated_df
                            st.rerun()
                    
                    # Get selected companies
                    selected_rows = edited_df[edited_df['Select'] == True]
                    selected_companies = []
                    
                    if not selected_rows.empty:
                        for _, row in selected_rows.iterrows():
                            xero_name = row['Xero Name']
                            # Find the corresponding process_data entry
                            data_entry = next(item for item in process_data if item['Xero Name'] == xero_name)
                            selected_companies.append({
                                'name': xero_name,
                                'devoli_names': row['Devoli Names'],
                                'total': row['Total'],
                                'data': data_entry['customer_data']
                            })
                    
                    # Store selected companies in session state
                    st.session_state.selected_companies = selected_companies
                    
                    # Add a continue button
                    if selected_companies:
                        if st.button("Process Selected Companies", key="process_selected"):
                            # Process the selected companies
                            results = process_selected_companies(selected_companies, df)
                            
                            # Add details to session state
                            st.session_state.processing_results = results
                            
                            # Show success message
                            st.success(f"Successfully processed {len(results)} companies")
                            
                            # Update the dataframe to reflect processed companies
                            for company in selected_companies:
                                xero_name = company['name']
                                # Mark as processed in database
                                st.session_state.log_db.mark_invoice_as_processed(xero_name, invoice_filename)
                                
                                # Update process_df to show as processed
                                process_df.loc[process_df['Xero Name'] == xero_name, 'Already Processed'] = True
                                process_df.loc[process_df['Xero Name'] == xero_name, 'Select'] = False
                            
                            # Update session state
                            st.session_state.process_df = process_df
                            
                            # Force rerun to refresh the UI
                            st.rerun()
                    else:
                        st.info("Select at least one company to process")
                else:
                    st.warning("No customers found with charges")
                        
            except Exception as e:
                st.error(f"Error processing invoice: {str(e)}")
                traceback.print_exc()
    else:
        st.error("No invoice files found. Place invoice CSV files in the bills directory.")

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
                result = process_customer(company['name'], company_data)
                
                # Add to results
                results.append({
                    'Company': company['name'],
                    'Status': 'Success' if result['success'] else 'Failed',
                    'DDI Charges': len(company_data['ddi_charges']),
                    'Has Calling Charges': bool(company_data['calling_charges']),
                    'Details': result['message']
                })
                
            except Exception as e:
                results.append({
                    'Company': company['name'],
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

def process_customer(customer_name, customer_data):
    """Process a single customer and create Xero invoice"""
    try:
        # Get billing processor
        billing_processor = st.session_state.billing_processor
        
        # Calculate totals
        totals = calculate_customer_totals(customer_data)
        
        # Format dates for invoice based on the first date in the data
        # Extract first date from customer_data
        first_date = None
        try:
            if 'Date' in customer_data.columns:
                first_date = pd.to_datetime(customer_data['Date'].iloc[0])
            elif hasattr(customer_data, 'name'):
                # Try to extract date from filename (e.g., Invoice_123456_2024-01-31.csv)
                date_str = os.path.basename(customer_data.name).split('_')[2].split('.')[0]
                first_date = pd.to_datetime(date_str)
        except (IndexError, ValueError, AttributeError) as e:
            st.warning(f"Could not extract date from data, using current date: {str(e)}")
            
        # Default to current date if extraction failed
        if first_date is None:
            first_date = datetime.datetime.now()
            
        # Add 2 months to get the invoice month, then get last day of that month
        next_month_date = first_date + pd.DateOffset(months=2)
        # Get the last day of the month
        invoice_date = pd.to_datetime(f"{next_month_date.year}-{next_month_date.month + 1 if next_month_date.month < 12 else 1}-01") - pd.Timedelta(days=1)
        
        # Due date is 20 days after invoice date
        due_date = invoice_date + pd.Timedelta(days=20)
        
        # Set reference
        reference = "Devoli Calling Charges"
        
        # Check if this is The Service Company
        is_service_company = customer_name.lower() == 'the service company'
        
        # Create invoice
        if is_service_company:
            # Use special processing for The Service Company
            service_processor = st.session_state.service_processor
            service_results = service_processor.process_billing(customer_data)
            
            # Generate line items
            line_items = []
            
            # Base fee line item
            line_items.append({
                "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
                "Quantity": 1.0,
                "UnitAmount": service_results['base_fee'],
                "AccountCode": billing_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
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
                    "AccountCode": billing_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
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
                        "AccountCode": billing_processor.SPECIAL_CUSTOMERS['the service company']['account_code'],
                        "TaxType": "OUTPUT2"
                    })
            
            # Create Xero invoice
            xero_invoice = billing_processor.create_xero_invoice(
                customer_name,
                customer_data,
                invoice_params={
                    'date': invoice_date.strftime('%Y-%m-%d'),
                    'due_date': due_date.strftime('%Y-%m-%d'),
                    'status': 'DRAFT',
                    'type': 'ACCREC',
                    'line_amount_types': 'Exclusive',
                    'reference': reference,
                    'line_items': line_items
                }
            )
        else:
            # Standard customer processing
            # Format invoice description
            invoice_desc = st.session_state.service_processor.format_call_description(
                st.session_state.service_processor.parse_call_data(customer_data)
            )
            
            # Truncate if too long for Xero
            max_length = 3900
            if len(invoice_desc) > max_length:
                invoice_desc = invoice_desc[:max_length] + "\n... (truncated)"
            
            # Create Xero invoice with parameters
            xero_invoice = billing_processor.create_xero_invoice(
                customer_name,
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
            
            # Add discount line for SPARK customers
            if 'SPARK' in customer_name.upper():
                try:
                    discount_amount = totals['calling_charges'] * 0.06
                    discount_result = billing_processor.add_line_item(
                        xero_invoice,
                        {
                            "Description": "Spark Discount Taken",
                            "Quantity": totals['calling_charges'],
                            "UnitAmount": -0.06,  # Negative to represent discount
                            "AccountCode": "45900",  # SPARK Sales account
                            "TaxType": "OUTPUT2"  # 15% GST
                        }
                    )
                    if not discount_result:
                        st.warning(f"SPARK discount could not be applied for {customer_name}, but invoice was created.")
                except Exception as discount_error:
                    st.warning(f"Error applying SPARK discount: {str(discount_error)}")
                    # Continue processing even if discount fails
                    traceback.print_exc()
        
        # Check for successful invoice creation
        if not xero_invoice:
            return {
                'success': False,
                'name': customer_name,
                'message': "No invoice response received"
            }
        
        # Extract invoice number
        invoice_number = None
        if isinstance(xero_invoice, dict):
            if 'Invoices' in xero_invoice and xero_invoice['Invoices']:
                invoice_number = xero_invoice['Invoices'][0].get('InvoiceNumber', 'Created')
            elif 'InvoiceNumber' in xero_invoice:
                invoice_number = xero_invoice['InvoiceNumber']
        
        return {
            'success': True,
            'name': customer_name,
            'message': f"Invoice {invoice_number} created successfully",
            'invoice_number': invoice_number
        }
        
    except Exception as e:
        # Return error with traceback for debugging
        traceback.print_exc()
        return {
            'success': False,
            'name': customer_name,
            'message': f"Error: {str(e)}"
        }

def process_selected_companies(selected_companies, df):
    """Process selected companies to Xero"""
    # Debug info
    st.write(f"Processing {len(selected_companies)} companies")
    st.write("Selected companies:", [c['name'] for c in selected_companies])
    
    # If no companies selected, return early
    if not selected_companies:
        st.warning("No companies selected for processing")
        return []
    
    results = []
    billing_processor = st.session_state.billing_processor
    
    # Create a progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Show completion message at end of processing
    success_count = 0
    error_count = 0
    
    # Create a container to show real-time updates
    log_container = st.container()
    
    # Ensure log database is initialized
    log_db = st.session_state.log_db
    
    # Get the file log ID - create one if it doesn't exist
    file_log_id = st.session_state.current_file_log_id
    if not file_log_id:
        invoice_file = os.path.basename(df.name) if hasattr(df, 'name') else "unknown_file.csv"
        file_log_id = log_db.log_file_processing(invoice_file)
        st.session_state.current_file_log_id = file_log_id
        st.write(f"Created new file log record: {file_log_id}")
    
    for i, company in enumerate(selected_companies):
        # Update progress
        progress = (i + 1) / len(selected_companies)
        progress_bar.progress(progress)
        status_text.text(f"Processing {i+1} of {len(selected_companies)}: {company['name']}")
        
        try:
            # Check if already processed in this session
            if company.get('processed'):
                with log_container:
                    st.info(f"Skipping {company['name']} - already processed in this session")
                continue
                
            # Check if already processed in database
            invoice_file = os.path.basename(df.name) if hasattr(df, 'name') else "unknown_file.csv"
            if log_db.check_if_processed(invoice_file, company['name']):
                with log_container:
                    st.info(f"Skipping {company['name']} - already processed previously")
                continue
                
            # Process the company
            with log_container:
                st.text(f"Creating invoice for {company['name']}...")
            
            # Get customer data
            customer_data = company['data']
            
            # Process the customer using billing_processor
            result = process_customer(company['name'], customer_data)
            
            if result['success']:
                success_count += 1
                # Mark as processed
                company['processed'] = True
                
                # Clean the total string - remove $ and convert to float
                total_amount = 0
                try:
                    total_amount = float(company['total'].replace('$', '').strip())
                except ValueError:
                    with log_container:
                        st.warning(f"Could not parse total amount: {company['total']}")
                    total_amount = 0
                
                # Log invoice creation - make sure it actually gets logged
                try:
                    invoice_creation_id = log_db.log_invoice_creation(
                        file_log_id,
                        company['name'], 
                        company.get('devoli_names', ''),
                        result.get('invoice_number', ''),
                        total_amount
                    )
                    with log_container:
                        st.success(f"✅ {company['name']}: {result['message']} - Logged: ID {invoice_creation_id}")
                except Exception as log_error:
                    with log_container:
                        st.error(f"⚠️ Invoice created but logging failed: {str(log_error)}")
            else:
                error_count += 1
                with log_container:
                    st.error(f"❌ {company['name']}: {result['message']}")
            
            results.append(result)
            
        except Exception as e:
            # Handle errors
            error_count += 1
            error_msg = str(e)
            traceback.print_exc()
            results.append({
                'success': False,
                'name': company['name'],
                'message': f"Error: {error_msg}"
            })
            with log_container:
                st.error(f"❌ Error processing {company['name']}: {error_msg}")
    
    # Complete progress and show final status
    progress_bar.progress(1.0)
    status_text.text("Processing complete!")
    
    # Show summary
    st.subheader("Processing Summary")
    st.write(f"Successfully processed: {success_count} invoices")
    if error_count > 0:
        st.write(f"Errors: {error_count} invoices")
    
    # Verify logs were created
    try:
        invoices_df = log_db.get_created_invoices(file_log_id)
        st.write(f"Logged {len(invoices_df)} invoices in database")
    except Exception as db_error:
        st.error(f"Error checking logs: {str(db_error)}")
    
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
    
    # Create sidebar for navigation
    with st.sidebar:
        st.title("Navigation")
        # Show invoice count from database if available
        if 'log_db' in st.session_state:
            invoices_df = st.session_state.log_db.get_created_invoices()
            if not invoices_df.empty:
                st.caption(f"Total invoices: {len(invoices_df)}")
        
        if st.button("Home"):
            navigate_to('home')
        if st.button("Process Invoice"):
            navigate_to('process') 
        if st.button("Customer Mapping"):
            navigate_to('mapping')
        if st.button("Product Analysis"):
            navigate_to('product_analysis')
        if st.button("Invoice History"):
            navigate_to('history')
            
        # Show Xero connection status
        if 'xero_connected' in st.session_state and st.session_state.xero_connected:
            st.sidebar.success("✅ Xero Connected")
        else:
            st.sidebar.warning("⚠️ Xero Not Connected")
            if st.sidebar.button("Connect to Xero"):
                try:
                    # Try to connect to Xero
                    processor = st.session_state.billing_processor
                    st.session_state.xero_connected = processor.ensure_xero_connection(force_refresh=True)
                    st.rerun()
                except Exception as e:
                    st.sidebar.error(f"Error connecting to Xero: {str(e)}")

    # Display the selected page
    if st.session_state.page == 'home':
        home_page()
    elif st.session_state.page == 'process':
        process_page()
    elif st.session_state.page == 'select':
        select_page()
    elif st.session_state.page == 'confirm':
        confirm_page()
    elif st.session_state.page == 'mapping':
        mapping_page()
    elif st.session_state.page == 'product_analysis':
        product_analysis_page()
    elif st.session_state.page == 'history':
        log_history_page()

if __name__ == "__main__":
    main()
