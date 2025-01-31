import pandas as pd
import os
from datetime import datetime
from xero_auth import XeroTokenManager, XeroAuth
import requests
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
from typing import Dict, Optional
import json

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
    
    def load_csv(self, file_path):
        """Load and validate the Devoli billing CSV"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Billing CSV file not found: {file_path}")
            
        self.billing_data = pd.read_csv(file_path)
        print(f"Loaded {len(self.billing_data)} billing items")
        return self.billing_data
        
    def group_by_customer(self):
        """Group billing items by customer and calculate totals"""
        if self.billing_data is None:
            raise ValueError("No billing data loaded. Call load_csv first.")
            
        # Group by customer and calculate totals
        grouped = self.billing_data.groupby('customer_name').agg({
            'amount': 'sum',
            'invoice_date': 'first',
            'start_date': 'first',
            'end_date': 'first'
        }).reset_index()
        
        # Get line items for each customer
        customer_items = {}
        print("\nCustomer Summary:")
        for customer in grouped['customer_name']:
            items = self.billing_data[self.billing_data['customer_name'] == customer]
            customer_items[customer] = items
            print(f"{customer}: ${items['amount'].sum():.2f} ({len(items)} items)")
            
        return grouped, customer_items
    
    def ensure_xero_connection(self):
        """Ensure we have valid Xero tokens"""
        try:
            self.token_manager.refresh_token_if_expired()
            return self.token_manager.get_auth_headers()
        except Exception as e:
            print(f"Error with Xero connection: {str(e)}")
            raise
        
    def create_xero_invoice(self, customer_name, items):
        """Create or simulate invoice creation in Xero for a customer"""
        # Get Xero name from mapping
        xero_name = self.customer_mapping.get(customer_name)
        if not xero_name:
            print(f"⚠️ Skipping {customer_name} - no mapping found")
            return None
        
        # Skip customers marked as [IGNORE]
        if xero_name == '[IGNORE]':
            print(f"ℹ️ Skipping {customer_name} - marked as [IGNORE]")
            return None

        # Group similar items
        grouped_items = {}
        ddi_details = []  # Store DDI details for notes
        
        for _, item in items.iterrows():
            # Extract the base product type (e.g., "DDI", "SIP Line & DDI", etc.)
            description_parts = item['description'].split(' - ')
            product_type = description_parts[1] if len(description_parts) > 1 else description_parts[0]
            
            # Create a key for grouping (product type + unit amount)
            key = f"{product_type}_{item['amount']}"
            
            if key not in grouped_items:
                grouped_items[key] = {
                    'description': product_type,
                    'quantity': 0,
                    'unit_amount': float(item['amount']),
                    'period': f"{item['start_date']} - {item['end_date']}",
                    'details': []
                }
            
            grouped_items[key]['quantity'] += float(item['quantity'])
            
            # Store DDI details for notes
            if 'DDI' in product_type:
                ddi_number = description_parts[2].strip() if len(description_parts) > 2 else ''
                ddi_details.append(f"{ddi_number} ({product_type})")
            
            # Store full line details
            grouped_items[key]['details'].append(item['description'])

        # Format line items for Xero
        line_items = []
        total_amount = 0
        
        for key, group in grouped_items.items():
            amount = group['unit_amount'] * group['quantity']
            total_amount += amount
            
            # Create main line item
            description = (f"{group['description']}\n"
                          f"Period: {group['period']}")
            
            line_items.append({
                "Description": description,
                "Quantity": group['quantity'],
                "UnitAmount": group['unit_amount'],
                "AccountCode": "200",
                "TaxType": "OUTPUT2"
            })

        # Add DDI details as a note line item if there are DDIs
        if ddi_details:
            ddi_note = "DDI Details:\n" + "\n".join(sorted(ddi_details))
            line_items.append({
                "Description": ddi_note,
                "Quantity": 0,
                "UnitAmount": 0,
                "AccountCode": "200",
                "TaxType": "OUTPUT2"
            })

        # In simulation mode, print what would have been created
        print(f"\n=== SIMULATED DRAFT INVOICE: {customer_name} ===")
        print(f"Xero Name: {xero_name}")
        print(f"Total Amount: ${total_amount:.2f}")
        print(f"Date Range: {items['start_date'].iloc[0]} - {items['end_date'].iloc[0]}")
        print(f"Items: {len(grouped_items)}")
        
        print("\nLine Items:")
        for item in line_items:
            if item['Quantity'] > 0:  # Regular line item
                print(f"\n- {item['Description']}")
                print(f"  Quantity: {item['Quantity']}")
                print(f"  Unit Amount: ${item['UnitAmount']:.2f}")
                print(f"  Total: ${item['Quantity'] * item['UnitAmount']:.2f}")
            else:  # Note line item
                print(f"\n{item['Description']}")
        
        print("\nStatus: DRAFT (simulation only - no invoice created)")
        print("=" * 50)
        
        return {
            "status": "simulated",
            "customer": customer_name,
            "xero_name": xero_name,
            "total_amount": total_amount,
            "line_items": len(line_items),
            "date_range": f"{items['start_date'].iloc[0]} - {items['end_date'].iloc[0]}",
            "grouped_items": grouped_items
        }

    def fetch_xero_contacts(self):
        """Fetch all contacts from Xero"""
        headers = self.ensure_xero_connection()
        
        try:
            response = requests.get(
                "https://api.xero.com/api.xro/2.0/Contacts",
                headers=headers
            )
            response.raise_for_status()
            
            # Debug information
            print("\nDebug: Xero API Response")
            print(f"Status Code: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type')}")
            print("Response Preview:", response.text[:200], "...\n")
            
            try:
                data = response.json()
                if 'Contacts' in data:
                    self.xero_contacts = data['Contacts']
                    print(f"Fetched {len(self.xero_contacts)} contacts from Xero")
                    return self.xero_contacts
                else:
                    print("Warning: No 'Contacts' key in response")
                    print("Response data:", data)
                    return []
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {str(e)}")
                print("Raw Response:", response.text[:500])
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
            
        best_match = None
        best_score = 0
        
        # Clean the Devoli name
        devoli_name = devoli_name.strip().lower()
        
        for contact in self.xero_contacts:
            xero_name = contact['Name'].strip().lower()
            
            # Try exact match first
            if xero_name == devoli_name:
                return contact
                
            # Try fuzzy matching
            score = fuzz.ratio(xero_name, devoli_name)
            if score > best_score and score > 80:  # 80% similarity threshold
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
        if not os.path.exists('customer_mapping.csv'):
            raise FileNotFoundError("Customer mapping file not found. Please run create_customer_mapping.py first")
            
        mapping_df = pd.read_csv('customer_mapping.csv')
        
        # Only use rows where actual_xero_name is filled in
        mapping_df = mapping_df[mapping_df['actual_xero_name'].notna() & (mapping_df['actual_xero_name'] != '')]
        
        # Create mapping dictionary
        self.customer_mapping = dict(zip(mapping_df['devoli_name'], mapping_df['actual_xero_name']))
        print(f"Loaded {len(self.customer_mapping)} customer mappings")

def main():
    print("\n=== Devoli Billing Processing (SIMULATION MODE) ===\n")
    
    # Create output directory if it doesn't exist
    os.makedirs('output', exist_ok=True)
    
    # Initialize
    try:
        processor = DevoliBilling(simulation_mode=True)
    except ValueError as e:
        print(f"Initialization error: {str(e)}")
        return
    
    # Load product mapping
    try:
        print("Loading product mapping...")
        product_mapping = pd.read_csv('product_mapping.csv')
        print(f"Loaded {len(product_mapping)} products from product_mapping.csv")
    except (FileNotFoundError, ValueError):
        print("No product mapping found. Please ensure product_mapping.csv is in the root directory.")
        return
    
    # Load CSV
    try:
        billing_data = processor.load_csv("bills/IT360 Limited - Devoli Summary Bill Report 133115 2024-09-30.csv")
    except Exception as e:
        print(f"Error loading CSV: {str(e)}")
        return
    
    # Group by customer
    try:
        grouped_data, customer_items = processor.group_by_customer()
    except Exception as e:
        print(f"Error grouping data: {str(e)}")
        return
    
    # Prepare data for invoice-style CSV
    invoice_data = []
    
    for customer in grouped_data['customer_name']:
        items = customer_items[customer]
        
        # Get customer details
        customer_info = {
            'invoice_type': 'HEADER',
            'customer_name': customer,
            'product_code': '',
            'line_item_description': '',
            'quantity': '',
            'unit_price': '',
            'line_total': '',
            'total_amount': items['amount'].sum(),
            'invoice_date': items['invoice_date'].iloc[0],
            'start_date': items['start_date'].iloc[0],
            'end_date': items['end_date'].iloc[0]
        }
        invoice_data.append(customer_info)
        
        # Group similar items
        grouped_items = {}
        for _, item in items.iterrows():
            product = str(item['product']).strip() if pd.notna(item.get('product')) else ''
            amount = float(item['amount'])
            
            # Look up product in mapping
            product_info = product_mapping[
                (product_mapping['product_code'] == product) & 
                (product_mapping['cost'] == amount)
            ].iloc[0] if len(product_mapping[
                (product_mapping['product_code'] == product) & 
                (product_mapping['cost'] == amount)
            ]) > 0 else None
            
            # Use mapped sale price if available
            sale_price = float(product_info['sale_price']) if product_info is not None else amount * 1.15
            
            # Create key for grouping
            key = f"{product}_{amount}"
            
            if key not in grouped_items:
                grouped_items[key] = {
                    'product_code': product,
                    'description': item['description'],
                    'quantity': 0,
                    'unit_amount': amount,
                    'sale_price': sale_price
                }
            
            grouped_items[key]['quantity'] += float(item['quantity'])
        
        # Add line items
        for key, group in grouped_items.items():
            line_item = {
                'invoice_type': 'LINE',
                'customer_name': customer,
                'product_code': group['product_code'],
                'line_item_description': group['description'],
                'quantity': group['quantity'],
                'unit_price': group['sale_price'],  # Use sale price instead of cost
                'line_total': group['quantity'] * group['sale_price'],
                'total_amount': '',
                'invoice_date': '',
                'start_date': '',
                'end_date': ''
            }
            invoice_data.append(line_item)
        
        # Add a blank row for spacing
        invoice_data.append({
            'invoice_type': 'BLANK',
            'customer_name': '',
            'product_code': '',
            'line_item_description': '',
            'quantity': '',
            'unit_price': '',
            'line_total': '',
            'total_amount': '',
            'invoice_date': '',
            'start_date': '',
            'end_date': ''
        })
    
    # Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f'output/invoice_simulation_{timestamp}.csv'
    
    invoice_df = pd.DataFrame(invoice_data)
    
    # Format numbers
    invoice_df['total_amount'] = invoice_df['total_amount'].apply(lambda x: f"${x:.2f}" if x != '' else '')
    invoice_df['unit_price'] = invoice_df['unit_price'].apply(lambda x: f"${x:.2f}" if x != '' else '')
    invoice_df['line_total'] = invoice_df['line_total'].apply(lambda x: f"${x:.2f}" if x != '' else '')
    
    # Reorder columns
    column_order = [
        'invoice_type',
        'customer_name',
        'product_code',
        'line_item_description',
        'quantity',
        'unit_price',
        'line_total',
        'total_amount',
        'invoice_date',
        'start_date',
        'end_date'
    ]
    
    # Reorder and save
    invoice_df = invoice_df[column_order]
    invoice_df.to_csv(output_file, index=False)
    
    print(f"\nProcessing complete!")
    print(f"Invoice details saved to: {output_file}")
    
    return

if __name__ == "__main__":
    main()
