import pandas as pd
import os
from datetime import datetime, timedelta
from xero_auth import XeroTokenManager, XeroAuth
import requests
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from typing import Dict, Optional
import json
import re
import streamlit as st
from service_company import ServiceCompanyBilling

class DevoliBilling:
    def __init__(self, simulation_mode=False):
        # Load environment variables
        load_dotenv()
        self.token_manager = XeroTokenManager()
        self.billing_data = None
        self.xero_contacts = None
        self.customer_mapping = {}
        
        # Verify we have a valid token file
        if not os.path.exists('xero_tokens.json'):
            raise ValueError("No Xero tokens found. Please authenticate first.")
        
        # Add simulation mode flag
        self.simulation_mode = simulation_mode
        
        # Add rates as class attribute
        self.rates = {
            'Australia': 0.14,
            'Local': 0.05,
            'Mobile': 0.12,
            'National': 0.05
        }
        
        # Define Xero API URL
        self.XERO_API_URL = "https://api.xero.com/api.xro/2.0"
        
        # Load customer mapping silently
        self.load_customer_mapping()
        
        # Initialize Xero connection once
        self.ensure_xero_connection(force_refresh=True)  # Force initial refresh
    
    # Pre-compiled regex patterns
    CALLS_PATTERN = re.compile(r'(?:.*?\()(\d+) calls? - ((?:\d+ days? )?[\d:]+)\)')
    TRUNK_PATTERN = re.compile(r'trunk: (\d+)')
    DURATION_PATTERN = re.compile(r'(?:(\d+) days? )?(\d{1,2}):(\d{2}):(\d{2})')

    # Add these as class constants
    SPECIAL_CUSTOMERS = {
        'the service company': {
            'base_fee': 55.00,
            'default_number': '6492003366',
            'account_code': '43850',
            'rates': {
                'local': 0.05,
                'mobile': 0.12,
                'national': 0.05,
                'tfree_mobile': 0.28,
                'tfree_national': 0.10,
                'tfree_australia': 0.14,
                'other': 0.14
            }
        }
    }
    
    STANDARD_RATES = {
        'local': 0.05,
        'mobile': 0.12,
        'australia': 0.14,
        'national': 0.05,
        'other': 0.14
    }

    def load_csv(self, file_path):
        """Load and validate the Devoli billing CSV"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Billing CSV file not found: {file_path}")
            
        # Load CSV with all columns
        df = pd.read_csv(file_path)
        
        # Define required columns and their mappings
        required_columns = {
            'Invoice Number': 'invoice_number',
            'Date': 'invoice_date', 
            'Amount': 'amount',
            'Customer Name': 'customer_name',
            'Description': 'description'
        }
        
        # Optional columns with defaults
        optional_columns = {
            'Item Id': 'item_id',
            'Short Description': 'short_description',
            'Tax Rate': 'tax_rate',
            'Product Type': 'product_type',
            'Service Type': 'service_type',
            'Service Item': 'service_number',
            'Start Date': 'start_date',
            'End Date': 'end_date'
        }
        
        # Verify required columns exist
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        
        # Rename required columns
        df = df.rename(columns=required_columns)
        
        # Rename optional columns that exist
        for old_col, new_col in optional_columns.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        # Clean data
        df['customer_name'] = df['customer_name'].str.strip()
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        # Convert dates
        date_columns = ['start_date', 'end_date', 'invoice_date']
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Add total column if needed
        if 'total' not in df.columns:
            df['total'] = df['amount']
        
        print(f"\nLoaded {len(df)} billing items")
        print("\nColumns:", df.columns.tolist())
        
        self.billing_data = df
        return df
        
    def group_by_customer(self):
        """Group billing items by customer and calculate totals"""
        if self.billing_data is None:
            raise ValueError("No billing data loaded. Call load_csv first.")
            
        # Clean customer names once
        self.billing_data['customer_name'] = self.billing_data['customer_name'].str.strip()
        
        # Use groupby iterator for efficiency
        customer_items = {}
        
        # Group once and iterate over groups silently
        for customer, items in self.billing_data.groupby('customer_name'):
            customer_items[customer] = items
        
        # Get summary data
        grouped = self.billing_data.groupby('customer_name').agg({
            'amount': 'sum',
            'invoice_date': 'first',
            'start_date': 'first', 
            'end_date': 'first'
        }).reset_index()
        
        return grouped, customer_items
    
    def ensure_xero_connection(self, force_refresh=False):
        """Ensure we have a valid Xero connection"""
        try:
            # Use session state to store headers
            if not force_refresh and 'xero_headers' in st.session_state:
                return st.session_state.xero_headers
            
            # Force token refresh to ensure we have valid tokens
            self.token_manager.refresh_token_if_expired(force_refresh=force_refresh)
            
            # Get headers with fresh token
            headers = self.token_manager.get_auth_headers()
            
            # Test connection silently
            response = requests.get(
                "https://api.xero.com/connections",
                headers=headers
            )
            response.raise_for_status()
            
            # Get tenant ID if not set
            if not self.token_manager.tokens.get('tenant_id'):
                tenants = response.json()
                if tenants:
                    self.token_manager.set_tenant_id(tenants[0]['tenantId'])
            
            # Store headers in session state
            st.session_state.xero_headers = headers
            return headers
            
        except Exception as e:
            st.error(f"Xero connection error: {str(e)}")
            raise

    def format_call_description(self, call_data):
        """Format calling charges description with details"""
        lines = ["Devoli calling charges:"]
        
        # Handle case where call_data is a DataFrame (old format)
        if isinstance(call_data, pd.DataFrame):
            # Filter for call-related rows
            call_mask = call_data['description'].str.contains('Calls', case=False, na=False)
            call_data = call_data[call_mask]
            
            # Process each call type
            for call_type in ['Australia', 'Local', 'Mobile', 'National']:
                mask = call_data['description'].str.contains(call_type, case=False, na=False)
                if mask.any():
                    desc = call_data[mask]['description'].iloc[0]
                    count, duration = self.parse_call_info(desc)
                    if count > 0:
                        lines.append(f"{call_type} Calls ({count} calls - {duration})")
        
        # Handle case where call_data is from call_details (new format)
        elif isinstance(call_data, list):
            for detail in call_data:
                lines.append(f"{detail['type']} Calls ({detail['count']} calls - {detail['duration']})")
        
        # If no calls found, show zeros
        if len(lines) == 1:
            lines.extend([
                "Australia Calls (0 calls - 00:00:00)",
                "Local Calls (0 calls - 00:00:00)",
                "Mobile Calls (0 calls - 00:00:00)",
                "National Calls (0 calls - 00:00:00)"
            ])
        
        return "\n".join(lines)

    def format_duration(self, duration):
        """Format duration in HH:MM:SS format"""
        # Convert minutes to HH:MM:SS
        hours = duration // 60
        minutes = duration % 60
        return f"{hours:02d}:{minutes:02d}:00"

    def calculate_call_charges(self, data: pd.DataFrame) -> float:
        """Calculate charges based on call durations and rates"""
        total_charge = 0
        call_details = []  # Store details for later display
        
        # Debug print for troubleshooting
        print(f"Processing call charges for data with {len(data)} rows")
        if not data.empty:
            print(f"First row description: {data['description'].iloc[0]}")
        
        # Use self.rates instead of local rates dictionary
        for call_type, rate in self.rates.items():
            mask = data['description'].str.lower().str.contains(call_type.lower(), na=False)
            if mask.any():
                calls = data[mask]['description'].iloc[0]
                count, duration = self.parse_call_info(calls)
                if count > 0:
                    minutes = self.duration_to_minutes(duration)
                    # Add debug logging
                    print(f"Call type: {call_type}, Duration: {duration}, Minutes: {minutes}, Rate: {rate}")
                    charge = minutes * rate
                    total_charge += charge
                    
                    # Store details
                    call_details.append({
                        'type': call_type,
                        'count': count,
                        'duration': duration,
                        'minutes': minutes,
                        'rate': rate,
                        'charge': charge
                    })
        
        # Ensure we return a non-zero value if there are call details
        if len(call_details) > 0 and total_charge == 0:
            print("WARNING: Call details found but total charge is 0, checking raw data...")
            # Try to extract charges directly from the data
            if 'amount' in data.columns:
                direct_charges = data['amount'].sum()
                if direct_charges > 0:
                    print(f"Using direct charges from data: ${direct_charges}")
                    total_charge = direct_charges
        
        return round(total_charge, 2), call_details

    def calculate_customer_totals(self, customer_data: pd.DataFrame) -> Dict:
        """Calculate totals for a customer"""
        # Filter for call-related rows
        call_mask = customer_data['description'].str.contains('Calls', case=False, na=False)
        call_data = customer_data[call_mask]
        
        # Calculate calling charges
        calling_charges, details = self.calculate_call_charges(call_data)
        
        return {
            'calling_charges': calling_charges,
            'call_details': details
        }

    def create_xero_invoice(self, customer, customer_data, invoice_params=None):
        """Create a draft invoice in Xero"""
        try:
            # Normalize column names to lowercase for case-insensitive comparison
            customer_data.columns = customer_data.columns.str.lower()
            
            # Validate and set defaults for invoice params
            if invoice_params is None:
                invoice_params = {}
            
            today = datetime.now().strftime('%Y-%m-%d')
            invoice_params = {
                'date': invoice_params.get('date', today),
                'due_date': invoice_params.get('due_date', 
                    (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')),
                'description': invoice_params.get('description', ''),
                'line_items': invoice_params.get('line_items', []),
                'pre_calculated_results': invoice_params.get('pre_calculated_results', None)
            }
            
            # Check if this is The Service Company
            is_service_company = customer.strip().lower() == 'the service company'
            account_code = self.SPECIAL_CUSTOMERS['the service company']['account_code'] if is_service_company else '43850'
            
            # Create line items
            line_items = []
            
            # Use provided line items if available
            if invoice_params.get('line_items'):
                line_items = invoice_params['line_items']
            else:
                # Calculate charges and format description
                calling_charges, call_details = self.calculate_call_charges(customer_data)
                invoice_desc = invoice_params.get('description', '')
                if not invoice_desc:
                    invoice_desc = self.format_call_description(call_details)
                
                # Add calling charges line item
                if calling_charges > 0:
                    line_items.append({
                        "Description": invoice_desc,
                        "Quantity": 1.0,
                        "UnitAmount": float(calling_charges),
                        "AccountCode": account_code,
                        "TaxType": "OUTPUT2"
                    })
            
            # Skip if no charges or if the total amount is $0
            if not line_items:
                # Check if there's call data before skipping
                call_mask = customer_data['description'].str.contains('Calls', case=False, na=False)
                call_data = customer_data[call_mask]
                
                if len(call_data) > 0:
                    # We have call data but no line items, calculate charges properly
                    print(f"⚠️ {customer} has call data but no line items, calculating charges")
                    calling_charges, call_details = self.calculate_call_charges(call_data)
                    
                    if calling_charges > 0:
                        # Create a line item using our calculated charges
                        invoice_desc = self.format_call_description(call_details)
                        line_items.append({
                            "Description": invoice_desc,
                            "Quantity": 1.0,
                            "UnitAmount": float(calling_charges),
                            "AccountCode": account_code,
                            "TaxType": "OUTPUT2"
                        })
                    else:
                        # If our calculation still gives 0, fall back to the Amount column
                        print(f"⚠️ Calculated charges are 0, falling back to Amount column")
                        total_amount = call_data['amount'].sum()
                        if total_amount > 0:
                            call_desc = call_data['description'].iloc[0]
                            line_items.append({
                                "Description": f"Calling charges: {call_desc}",
                                "Quantity": 1.0,
                                "UnitAmount": float(total_amount),
                                "AccountCode": account_code,
                                "TaxType": "OUTPUT2"
                            })
                        else:
                            print(f"ℹ️ Skipping {customer} - $0 invoice (no charges in call data)")
                            return None
                else:
                    print(f"ℹ️ Skipping {customer} - $0 invoice (no call data)")
                    return None
                    
            # Calculate total invoice amount
            total_invoice_amount = sum(item.get("UnitAmount", 0) * item.get("Quantity", 1) for item in line_items)
            
            # Skip if total invoice amount is $0 or negative
            if total_invoice_amount <= 0:
                print(f"ℹ️ Skipping {customer} - ${total_invoice_amount} invoice amount (zero or negative total)")
                return None
            
            # Find Xero contact - first check if the customer name is already a Xero name
            # This is the case when we get the customer name from the UI where it's already mapped
            xero_name = customer.strip()
            
            # Check if this name exists in Xero contacts
            contacts = self.fetch_xero_contacts()
            if not contacts:
                raise ValueError("Failed to fetch Xero contacts")
            
            # Try direct match first
            xero_contact = None
            search_name = xero_name.lower()
            for contact in contacts:
                if contact['Name'].lower() == search_name:
                    xero_contact = contact
                    break
            
            # If no direct match, try using the mapping
            if not xero_contact:
                # Try to find via mapping
                mapped_name = self.customer_mapping.get(customer.strip())
                if not mapped_name:
                    raise ValueError(f"No Xero mapping found for {customer}")
                
                # Search again with mapped name
                search_name = mapped_name.lower()
                for contact in contacts:
                    if contact['Name'].lower() == search_name:
                        xero_contact = contact
                        break
            
            if not xero_contact:
                raise ValueError(f"Contact '{xero_name}' not found in Xero")
            
            # Create the invoice
            invoice_date = invoice_params.get('date', self.calculate_invoice_date(datetime.now().strftime('%Y-%m-%d')))
            invoice_data = {
                "Type": invoice_params.get('type', 'ACCREC'),
                "Contact": xero_contact,
                "LineItems": line_items,
                "Date": invoice_date,
                "DueDate": invoice_params.get('due_date', (pd.to_datetime(invoice_date) + pd.Timedelta(days=20)).strftime('%Y-%m-%d')),
                "Reference": invoice_params.get('reference', f"Devoli Calling Charges - {pd.to_datetime(invoice_date).strftime('%B %Y')}"),
                "Status": invoice_params.get('status', 'DRAFT')
            }
            
            # Add debug logging
            print(f"Creating Xero invoice for {customer}")
            print(f"Line items: {json.dumps(line_items, indent=2)}")
            
            # Send to Xero
            headers = self.ensure_xero_connection()
            headers['Accept'] = 'application/json'
            
            response = requests.post(
                "https://api.xero.com/api.xro/2.0/Invoices",
                headers=headers,
                json={"Invoices": [invoice_data]}
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            print(f"Error creating Xero invoice: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            raise

    def fetch_xero_contacts(self):
        """Fetch all contacts from Xero"""
        headers = self.ensure_xero_connection()
        
        try:
            # Add Accept header to request JSON
            headers['Accept'] = 'application/json'
            
            response = requests.get(
                "https://api.xero.com/api.xro/2.0/Contacts",
                headers=headers
            )
            response.raise_for_status()
            
            try:
                data = response.json()
                if 'Contacts' in data:
                    self.xero_contacts = data['Contacts']
                    return self.xero_contacts
                else:
                    print("Warning: No 'Contacts' key in response")
                    print("Response data:", data)
                    return []
            except json.JSONDecodeError as e:
                print(f"Error: Received XML instead of JSON")
                print("Response headers:", response.headers)
                print("Response content type:", response.headers.get('Content-Type'))
                return []
                
        except requests.exceptions.RequestException as e:
            print(f"Request Error: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Status Code: {e.response.status_code}")
                print(f"Response Text: {e.response.text[:500]}")
            raise

    def find_best_match(self, devoli_name: str) -> Optional[Dict]:
        """Find the best matching Xero contact for a Devoli customer name"""
        if not self.xero_contacts:
            self.fetch_xero_contacts()
        
        if not hasattr(self, '_contact_names_cache'):
            # Create cache of lowercase names
            self._contact_names_cache = {
                contact['ContactID']: contact['Name'].strip().lower()
                for contact in self.xero_contacts
            }
        
        # Clean the Devoli name once
        devoli_name = devoli_name.strip().lower()
        
        # Try exact match first (using cache)
        for contact in self.xero_contacts:
            if self._contact_names_cache[contact['ContactID']] == devoli_name:
                return contact
        
        # Fuzzy match if needed
        best_match = None
        best_score = 0
        
        # Use pre-computed lowercase names
        for contact in self.xero_contacts:
            score = fuzz.ratio(self._contact_names_cache[contact['ContactID']], devoli_name)
            if score > best_score and score > 80:
                best_score = score
                best_match = contact
        
        return best_match

    def create_xero_contact(self, customer_name: str) -> Optional[Dict]:
        """Create a new contact in Xero"""
        headers = self.ensure_xero_connection()
        
        contact = {
            "Name": customer_name,
            "FirstName": "",
            "LastName": "",
            "EmailAddress": "",
            "IsCustomer": True
        }
        
        try:
            response = requests.post(
                "https://api.xero.com/api.xro/2.0/Contacts",
                headers=headers,
                json={"Contacts": [contact]}
            )
            response.raise_for_status()
            new_contact = response.json()['Contacts'][0]
            print(f"✓ Created new Xero contact for {customer_name}")
            return new_contact
        except Exception as e:
            print(f"✗ Error creating contact for {customer_name}: {str(e)}")
            return None

    def load_customer_mapping(self):
        """Load customer mapping from CSV"""
        try:
            if not os.path.exists('customer_mapping.csv'):
                raise FileNotFoundError("Customer mapping file not found")
            
            mapping_df = pd.read_csv('customer_mapping.csv')
            
            # Create mapping dictionary without debug prints
            self.customer_mapping = dict(zip(
                mapping_df['devoli_name'].str.strip(),
                mapping_df['actual_xero_name'].str.strip()
            ))
            
        except Exception as e:
            st.error(f"Error loading customer mapping: {str(e)}")
            raise

    def parse_call_info(self, description: str) -> tuple[int, str]:
        """Parse call count and duration from description"""
        match = self.CALLS_PATTERN.search(description)
        if not match:
            return 0, "00:00:00"
        
        num_calls = int(match.group(1))
        duration = match.group(2)
        
        # Standardize duration format
        duration = self.parse_duration(duration)
        
        return num_calls, duration

    def get_call_type(self, description):
        """Determine call type from description"""
        # Handle special cases first
        if "TFree Inbound" in description:
            if "AUS Mobile" in description:
                return "TFree Mobile"
            elif "AUS National" in description:
                return "TFree National"
            elif "Mobile" in description:
                return "TFree Mobile"
            elif "National" in description:
                return "TFree National"
            elif "Australia" in description:
                return "TFree Australia"
        
        # Handle standard call types
        if "Australia" in description:
            return "Australian Calls"
        elif "Mobile" in description:
            return "Mobile Calls"
        elif "National" in description:
            return "National Calls"
        elif "Local" in description:
            return "Local Calls"
        else:
            return "Other Calls"

    def get_service_number(self, description: str) -> Optional[str]:
        """Extract service number from description"""
        match = self.TRUNK_PATTERN.search(description)
        return match.group(1) if match else None

    def process_calling_charges(self, data: pd.DataFrame) -> Dict:
        """Process calling charges with vectorized operations where possible"""
        # Standard rates
        rates = {
            'Australian Calls': 0.14,
            'Mobile Calls': 0.12,
            'National Calls': 0.05,
            'Local Calls': 0.05,
            'Other Calls': 0.14,
            'TFree Mobile': 0.28,
            'TFree National': 0.10,
            'TFree Australia': 0.14
        }
        
        # Create call type mask
        call_mask = (
            data['description'].str.contains('Calls', case=False, na=False) |
            data['description'].str.contains('TFree', case=False, na=False)
        )
        call_data = data[call_mask].copy()
        
        # Extract call info using vectorized operations
        call_data['call_info'] = call_data['description'].apply(self.parse_call_info)
        call_data['num_calls'] = call_data['call_info'].apply(lambda x: x[0])
        call_data['duration'] = call_data['call_info'].apply(lambda x: x[1])
        call_data['minutes'] = call_data['duration'].apply(self.duration_to_minutes)
        call_data['call_type'] = call_data['description'].apply(self.get_call_type)
        call_data['rate'] = call_data['call_type'].map(rates)
        call_data['charge'] = call_data['minutes'] * call_data['rate']
        
        results = {}
        
        # Group by customer
        for customer, group in call_data.groupby('customer_name'):
            results[customer] = {
                'charges': {},
                'total': 0,
                'numbers': {}
            }
            
            # Calculate charges by call type
            type_charges = group.groupby('call_type')['charge'].sum()
            results[customer]['charges'].update(type_charges.to_dict())
            results[customer]['total'] = group['charge'].sum()
            
            # Handle The Service Company special case
            if customer == "The Service Company":
                service_numbers = group['service_number'].unique()
                for number in service_numbers:
                    if not pd.isna(number):
                        number_data = group[group['service_number'] == number]
                        results[customer]['numbers'][number] = {
                            'charges': number_data.groupby('call_type')['charge'].sum().to_dict(),
                            'total': number_data['charge'].sum()
                        }
        
        return results

    def format_invoice_lines(self, customer_name, charges, items):
        """Format invoice line items"""
        if customer_name == "The Service Company":
            line_items = []
            
            # Add base fee
            line_items.append({
                "Description": "Base Fee",
                "Quantity": 1,
                "UnitAmount": 55.0,
                "AccountCode": "IS10240",
                "TaxType": "OUTPUT2"
            })
            
            # Add per-number charges
            for number, details in charges['numbers'].items():
                description = f"Calling Charges for {number}:\n"
                for call_type, amount in details['charges'].items():
                    if amount > 0:
                        description += f"{call_type}: ${amount:.2f}\n"
                
                line_items.append({
                    "Description": description,
                    "Quantity": 1,
                    "UnitAmount": details['total'],
                    "AccountCode": "IS10240",
                    "TaxType": "OUTPUT2"
                })
            
            return line_items
        else:
            # Standard formatting for other customers
            description = "Devoli Calling Charges:\n"
            total = 0
            
            for call_type, amount in charges['charges'].items():
                if amount > 0:
                    description += f"{call_type}: ${amount:.2f}\n"
                    total += amount
            
            return [{
                "Description": description,
                "Amount": total,
                "AccountCode": "43850"
            }]

    def process_products(self, data: pd.DataFrame) -> Dict:
        """Process all product types from invoice data using vectorized operations"""
        results = {
            'calling_charges': {},
            'ddi_charges': {},
            'sip_lines': {},
            'ufb_services': {},
            'other_services': {}
        }
        
        # Create masks for each product type
        ddi_mask = data['description'].str.contains('DDI', case=False, na=False)
        sip_mask = data['description'].str.contains('SIP Line', case=False, na=False)
        ufb_mask = data['description'].str.apply(
            lambda x: '/29 Range' in str(x) or 'Static IP' in str(x)
        )
        
        # Group by customer and product type
        for customer in data['customer_name'].unique():
            customer_data = data[data['customer_name'] == customer]
            
            # Initialize customer in all categories
            for category in results:
                if customer not in results[category]:
                    results[category][customer] = {
                        'charges': [],
                        'total': 0
                    }
            
            # Process DDI charges
            ddi_items = customer_data[ddi_mask]
            if not ddi_items.empty:
                charges = ddi_items.apply(
                    lambda row: {
                        'description': row['description'],
                        'amount': float(row['amount']),
                        'period': f"{row['start_date']} - {row['end_date']}",
                        'number': str(row.get('service_number', ''))
                    },
                    axis=1
                ).tolist()
                
                results['ddi_charges'][customer]['charges'].extend(charges)
                results['ddi_charges'][customer]['total'] = ddi_items['amount'].sum()
            
            # Process SIP lines
            sip_items = customer_data[sip_mask]
            if not sip_items.empty:
                charges = sip_items.apply(
                    lambda row: {
                        'description': row['description'],
                        'amount': float(row['amount']),
                        'period': f"{row['start_date']} - {row['end_date']}",
                        'number': str(row.get('service_number', ''))
                    },
                    axis=1
                ).tolist()
                
                results['sip_lines'][customer]['charges'].extend(charges)
                results['sip_lines'][customer]['total'] = sip_items['amount'].sum()
            
            # Process UFB services
            ufb_items = customer_data[ufb_mask]
            if not ufb_items.empty:
                charges = ufb_items.apply(
                    lambda row: {
                        'description': row['description'],
                        'amount': float(row['amount']),
                        'period': f"{row['start_date']} - {row['end_date']}",
                        'service': str(row.get('service_number', ''))
                    },
                    axis=1
                ).tolist()
                
                results['ufb_services'][customer]['charges'].extend(charges)
                results['ufb_services'][customer]['total'] = ufb_items['amount'].sum()
            
            # Process other services (everything else)
            other_mask = ~(ddi_mask | sip_mask | ufb_mask)
            other_items = customer_data[other_mask]
            if not other_items.empty:
                charges = other_items.apply(
                    lambda row: {
                        'description': row['description'],
                        'amount': float(row['amount']),
                        'period': f"{row['start_date']} - {row['end_date']}"
                    },
                    axis=1
                ).tolist()
                
                results['other_services'][customer]['charges'].extend(charges)
                results['other_services'][customer]['total'] = other_items['amount'].sum()
        
        return results

    def parse_duration(self, time_str: str) -> str:
        """Convert any duration string to HH:MM:SS format
        
        Handles formats:
        - HH:MM:SS
        - N days HH:MM:SS
        - MM:SS
        """
        if not time_str or time_str.strip() == "00:00:00":
            return "00:00:00"
            
        # First check if it's already in HH:MM:SS format
        if re.match(r'^\d+:\d{2}:\d{2}$', time_str):
            return time_str
            
        match = self.DURATION_PATTERN.search(time_str)
        if not match:
            return "00:00:00"
            
        days = int(match.group(1) or 0)
        hours = int(match.group(2))
        minutes = int(match.group(3))
        seconds = int(match.group(4))
        
        # Convert everything to hours:minutes:seconds
        total_hours = (days * 24) + hours
        
        return f"{total_hours:02d}:{minutes:02d}:{seconds:02d}"

    def duration_to_minutes(self, time_str: str) -> int:
        """Convert any duration string to total minutes"""
        if not time_str:
            return 0
        
        # Handle direct HH:MM:SS format first
        if re.match(r'^\d+:\d{2}:\d{2}$', time_str):
            hours, minutes, seconds = map(int, time_str.split(':'))
            total_minutes = (hours * 60) + minutes
            if seconds > 0:
                total_minutes += 1
            return total_minutes
            
        # For other formats, use parse_duration
        std_time = self.parse_duration(time_str)
        hours, minutes, seconds = map(int, std_time.split(':'))
        
        # Calculate total minutes, rounding up if there are seconds
        total_minutes = (hours * 60) + minutes
        if seconds > 0:
            total_minutes += 1
            
        return total_minutes

    def calculate_invoice_date(self, date_str: str) -> str:
        """
        Calculate the invoice date based on the logic:
        - For a given month's data, the invoice should be dated the last day of that month
        - E.g., January data -> January 31st invoice date
        
        Args:
            date_str: Date string in format YYYY-MM-DD
            
        Returns:
            Invoice date string in format YYYY-MM-DD
        """
        try:
            # Parse the original date
            original_date = pd.to_datetime(date_str)
            
            # Get the last day of the current month
            if original_date.month == 12:
                next_month = 1
                next_year = original_date.year + 1
            else:
                next_month = original_date.month + 1
                next_year = original_date.year
            
            # Create first day of next month and subtract one day to get last day of current month
            invoice_date = pd.to_datetime(f"{next_year}-{next_month:02d}-01") - pd.Timedelta(days=1)
            
            return invoice_date.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"Error calculating invoice date: {e}")
            # Fall back to today's date if there's an error
            return datetime.now().strftime('%Y-%m-%d')

    def load_voip_customers(self, df):
        """Load only customers with VoIP/calling products"""
        voip_products = [
            'DDI',
            'SIP Line',
            'SIP Trunk',
            'Calling',
            'Voice'
        ]
        
        # Filter for rows containing our product types silently
        mask = df['Description'].str.contains('|'.join(voip_products), case=False, na=False)
        voip_df = df[mask]
        
        # Get unique customers who have these products
        customers = sorted(voip_df['Customer Name'].dropna().unique())
        
        return customers, voip_df

    def get_customer_rates(self, customer_name: str) -> Dict[str, float]:
        """Get customer-specific rates with standardized keys"""
        customer_key = customer_name.strip().lower()
        if customer_key in self.SPECIAL_CUSTOMERS:
            return self.SPECIAL_CUSTOMERS[customer_key]['rates']
        return self.STANDARD_RATES

    def calculate_calling_charges(self, call_data: Dict, customer_name: str = '') -> float:
        """Calculate calling charges with standardized rate keys"""
        rates = self.get_customer_rates(customer_name)
        total_charges = 0
        
        for call_type, data in call_data.items():
            if data['count'] > 0:
                # Use total_seconds for more accurate calculation
                minutes = (data['total_seconds'] + 59) // 60  # Round up
                rate = rates.get(call_type, rates['other'])
                total_charges += minutes * rate
        
        return round(total_charges, 2)

    def aggregate_call_data(self, customer_df: pd.DataFrame) -> Dict:
        """Aggregate all call data for a customer using vectorized operations"""
        # Initialize call data structure
        call_data = {
            'australia': {'count': 0, 'duration': '00:00:00', 'total_seconds': 0},
            'local': {'count': 0, 'duration': '00:00:00', 'total_seconds': 0},
            'mobile': {'count': 0, 'duration': '00:00:00', 'total_seconds': 0},
            'national': {'count': 0, 'duration': '00:00:00', 'total_seconds': 0},
            'other': {'count': 0, 'duration': '00:00:00', 'total_seconds': 0}
        }
        
        # Create masks for each call type
        type_masks = {
            'australia': customer_df['description'].str.contains('Australia', case=False, na=False),
            'local': customer_df['description'].str.contains('Local', case=False, na=False),
            'mobile': customer_df['description'].str.contains('Mobile', case=False, na=False),
            'national': customer_df['description'].str.contains('National', case=False, na=False)
        }
        
        # Process each call type
        for call_type, mask in type_masks.items():
            if not customer_df[mask].empty:
                # Get call info for all matching rows
                calls = customer_df[mask]['description'].apply(self.parse_call_info)
                
                # Sum up counts and durations
                call_data[call_type]['count'] = sum(c[0] for c in calls)
                
                # Convert all durations to seconds and sum
                total_seconds = sum(
                    sum(int(x) * m for x, m in zip(d[1].split(':'), [3600, 60, 1]))
                    for _, d in calls
                )
                
                # Store total duration in HH:MM:SS
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                call_data[call_type]['duration'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                call_data[call_type]['total_seconds'] = total_seconds
        
        # Handle other calls (those not matching any specific type)
        other_mask = ~sum(type_masks.values())
        if not customer_df[other_mask].empty:
            calls = customer_df[other_mask]['description'].apply(self.parse_call_info)
            call_data['other']['count'] = sum(c[0] for c in calls)
            total_seconds = sum(
                sum(int(x) * m for x, m in zip(d[1].split(':'), [3600, 60, 1]))
                for _, d in calls
            )
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            call_data['other']['duration'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            call_data['other']['total_seconds'] = total_seconds
        
        return call_data

    def process_service_company(self, df):
        """Process The Service Company data silently"""
        # Filter TFree rows silently
        tfree_mask = df['short_description'].str.startswith('64800', na=False)
        tfree_rows = df[tfree_mask]
        
        # Get unique customers silently
        customers = sorted(df[tfree_mask]['customer_name'].unique())
        
        # Rest of the processing...

    def add_line_item(self, invoice, line_item):
        """Add a line item to an existing invoice"""
        try:
            # Better extraction of invoice ID with detailed logging
            invoice_id = None
            
            # Handle various response formats
            if isinstance(invoice, dict):
                if 'Invoices' in invoice and invoice['Invoices'] and len(invoice['Invoices']) > 0:
                    if 'InvoiceID' in invoice['Invoices'][0]:
                        invoice_id = invoice['Invoices'][0]['InvoiceID']
                    else:
                        print("InvoiceID not found in Invoices[0], invoice structure:")
                        print(json.dumps(invoice['Invoices'][0], indent=2))
                elif 'InvoiceID' in invoice:
                    invoice_id = invoice['InvoiceID']
                else:
                    print("Could not find InvoiceID in invoice structure:")
                    print(json.dumps(invoice, indent=2)[:500])  # Print first 500 chars to avoid huge output
            else:
                print(f"Invalid invoice type: {type(invoice)}")
                print(f"Invoice value: {invoice}")
            
            if not invoice_id:
                print("Failed to extract invoice ID, cannot add line item")
                return None
                
            print(f"Adding line item to invoice ID: {invoice_id}")
            
            # Set up request
            headers = self.ensure_xero_connection()
            headers['Accept'] = 'application/json'
            headers['Content-Type'] = 'application/json'
            
            # Create update payload directly without fetching first (simpler approach)
            update_payload = {
                "Invoices": [
                    {
                        "InvoiceID": invoice_id,
                        "LineItems": [line_item]
                    }
                ]
            }
            
            # Send the update
            url = f"{self.XERO_API_URL}/Invoices/{invoice_id}"
            print(f"Sending PUT request to: {url}")
            
            response = requests.put(
                url,
                headers=headers,
                json=update_payload
            )
            
            # Check response
            if response.status_code in [200, 201, 202]:
                try:
                    return response.json()
                except Exception as json_error:
                    print(f"Error decoding JSON response: {str(json_error)}")
                    print(f"Response status code: {response.status_code}")
                    print(f"Response text: {response.text[:500]}")  # Limited to first 500 chars
                    # Return success anyway if status code is good
                    if response.status_code in [200, 201, 202]:
                        return {"success": True, "message": "Line item added (status code indicates success)"}
            else:
                print(f"Error adding line item to invoice: {response.status_code}")
                print(f"Response text: {response.text[:500]}")  # Limited to first 500 chars
                return None
        except Exception as e:
            print(f"Error adding line item to invoice: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

def main():
    st.set_page_config(page_title="Devoli Billing", layout="wide")
    
    # Initialize DevoliBilling only once with force_refresh=True
    if 'billing_processor' not in st.session_state:
        st.session_state.billing_processor = DevoliBilling(simulation_mode=False)
    
    # Rest of your main code...

if __name__ == "__main__":
    main()
