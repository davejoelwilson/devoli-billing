import streamlit as st
import pandas as pd
import os
import json
import traceback
from service_company import ServiceCompanyBilling
from devoli_billing import DevoliBilling
from datetime import datetime
import re

def fix_tsc_invoices():
    """Fix The Service Company invoices by ensuring multiple line items"""
    print("Starting TSC invoice fix")
    
    # Initialize processors
    service_processor = ServiceCompanyBilling()
    billing_processor = DevoliBilling(simulation_mode=False)
    
    # Find the latest invoice file
    bills_dir = "bills"
    invoice_files = [f for f in os.listdir(bills_dir) if f.startswith("Invoice_") and f.endswith(".csv")]
    if not invoice_files:
        print("No invoice files found in bills directory")
        return
        
    # Sort by date in filename (newest first)
    latest_invoice = sorted(invoice_files, key=lambda x: x.split('_')[2].split('.')[0], reverse=True)[0]
    invoice_path = os.path.join(bills_dir, latest_invoice)
    print(f"Processing: {invoice_path}")
    
    # Load invoice data
    df = pd.read_csv(invoice_path)
    
    # Clean up column names and customer names
    df.columns = [col.strip() for col in df.columns]
    if 'Customer Name' in df.columns:
        df['Customer Name'] = df['Customer Name'].str.strip()
    
    # Filter for The Service Company
    tsc_data = df[df['Customer Name'].str.lower() == 'the service company']
    if tsc_data.empty:
        print("No data found for The Service Company")
        return
    
    print(f"Found {len(tsc_data)} records for The Service Company")
    
    # Process TSC billing
    try:
        # Process with service company processor
        service_results = service_processor.process_billing(tsc_data)
        
        print(f"Processed TSC billing:")
        print(f"Base fee: ${service_results['base_fee']}")
        print(f"Regular number calls: {len(service_results['regular_number']['calls'])}")
        print(f"Regular number total: ${service_results['regular_number']['total']}")
        print(f"TFree numbers: {len(service_results['numbers'])}")
        
        # Create line items
        line_items = []
        
        # Base fee line item
        line_items.append({
            "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
            "Quantity": 1.0, 
            "UnitAmount": service_results['base_fee'],
            "AccountCode": "43850",
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
                "AccountCode": "43850", 
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
                    "AccountCode": "43850",
                    "TaxType": "OUTPUT2"
                })
        
        print(f"Created {len(line_items)} line items")
        
        # Get the date from the invoice file name
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', latest_invoice)
        invoice_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
        
        # Due date is 20 days after invoice date
        due_date = (pd.to_datetime(invoice_date) + pd.Timedelta(days=20)).strftime('%Y-%m-%d')
        
        # Create invoice reference
        reference = f"Devoli Calling Charges - {pd.to_datetime(invoice_date).strftime('%B %Y')}"
        
        # Create the invoice
        print(f"Creating invoice for The Service Company Limited")
        print(f"Date: {invoice_date}, Due: {due_date}, Reference: {reference}")
        print(f"Line items: {json.dumps(line_items, indent=2)}")
        
        # Direct Xero API call
        xero_invoice = billing_processor.create_xero_invoice(
            "The Service Company Limited",  # Use full company name as in Xero
            tsc_data,
            invoice_params={
                'date': invoice_date,
                'due_date': due_date,
                'status': 'DRAFT',
                'type': 'ACCREC',
                'line_amount_types': 'Exclusive',
                'reference': reference,
                'line_items': line_items
            }
        )
        
        # Log the result
        if xero_invoice:
            invoice_number = None
            if 'Invoices' in xero_invoice and xero_invoice['Invoices']:
                invoice_number = xero_invoice['Invoices'][0].get('InvoiceNumber')
            
            print(f"Success! Created invoice {invoice_number}")
            
            # Save response for debugging
            with open('tsc_invoice_response.json', 'w') as f:
                json.dump(xero_invoice, f, indent=2)
                
            print("Response saved to tsc_invoice_response.json")
        else:
            print("No response received from Xero")
    
    except Exception as e:
        print(f"Error processing TSC invoice: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    fix_tsc_invoices() 