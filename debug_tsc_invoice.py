import requests
import os
import json
from dotenv import load_dotenv
from xero_auth import XeroTokenManager

# Load environment variables
load_dotenv()

def ensure_xero_connection():
    token_manager = XeroTokenManager()
    token_manager.refresh_token_if_expired(force_refresh=True)
    headers = token_manager.get_auth_headers()
    headers['Accept'] = 'application/json'
    headers['Content-Type'] = 'application/json'
    return headers

def debug_tsc_invoice():
    """Create a test invoice directly to debug multiple line items"""
    print("Creating test invoice with multiple line items for The Service Company")
    
    # Get Xero contact ID for TSC
    headers = ensure_xero_connection()
    
    # Find TSC contact
    response = requests.get(
        "https://api.xero.com/api.xro/2.0/Contacts",
        headers=headers
    )
    response.raise_for_status()
    data = response.json()
    
    tsc_contact = None
    for contact in data.get('Contacts', []):
        if contact['Name'].lower() == 'the service company limited':
            tsc_contact = contact
            break
    
    if not tsc_contact:
        print("Error: Could not find The Service Company Limited contact")
        return
    
    # Create invoice with multiple line items
    line_items = [
        {
            "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
            "Quantity": 1.0,
            "UnitAmount": 55.00,
            "AccountCode": "43850",
            "TaxType": "OUTPUT2"
        },
        {
            "Description": "6492003366\nLocal Calls (129 calls - 04:41:47)\nMobile Calls (703 calls - 20:19:40)\nNational Calls (199 calls - 07:38:47)",
            "Quantity": 1.0,
            "UnitAmount": 120.50,
            "AccountCode": "43850",
            "TaxType": "OUTPUT2"
        },
        {
            "Description": "64800366080\nTFree Inbound - Mobile (45 calls - 02:15:20)\nTFree Inbound - National (22 calls - 01:12:30)",
            "Quantity": 1.0,
            "UnitAmount": 37.45,
            "AccountCode": "43850",
            "TaxType": "OUTPUT2"
        },
        {
            "Description": "64800753753\nTFree Inbound - Mobile (12 calls - 00:45:10)",
            "Quantity": 1.0,
            "UnitAmount": 21.06,
            "AccountCode": "43850",
            "TaxType": "OUTPUT2"
        }
    ]
    
    invoice_data = {
        "Type": "ACCREC",
        "Contact": tsc_contact,
        "LineItems": line_items,
        "Date": "2025-04-30",
        "DueDate": "2025-05-20",
        "Reference": "Devoli Calling Charges - April 2025",
        "Status": "DRAFT",
        "LineAmountTypes": "Exclusive"  # Critical!
    }
    
    # Send to Xero
    print("Sending invoice to Xero")
    print(f"Line items: {json.dumps(line_items, indent=2)}")
    
    response = requests.post(
        "https://api.xero.com/api.xro/2.0/Invoices",
        headers=headers,
        json={"Invoices": [invoice_data]}
    )
    
    # Check response
    if response.status_code in [200, 201, 202]:
        print("Success! Invoice created with multiple line items")
        result = response.json()
        invoice_number = None
        if 'Invoices' in result and result['Invoices']:
            invoice_number = result['Invoices'][0].get('InvoiceNumber')
        print(f"Invoice number: {invoice_number}")
        
        # Log the full response for debugging
        with open('debug_response.json', 'w') as f:
            json.dump(result, f, indent=2)
            
        print("Response saved to debug_response.json")
    else:
        print(f"Error: {response.status_code}")
        print(f"Response text: {response.text}")

if __name__ == "__main__":
    debug_tsc_invoice() 