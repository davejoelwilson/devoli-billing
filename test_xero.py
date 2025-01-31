from xero import Xero
from xero.auth import OAuth2Credentials
import json
import pandas as pd

def test_xero_contacts():
    """Test getting Xero contacts using SDK"""
    try:
        # Load Devoli customers first
        try:
            devoli_df = pd.read_csv('bills/Invoice_134426_2024-12-31.csv')
            devoli_customers = sorted(devoli_df['Customer Name'].unique())
            print("\n=== Devoli Customers ===")
            print(f"Found {len(devoli_customers)} customers:")
            for cust in devoli_customers:
                print(f"- {cust}")
        except Exception as e:
            print(f"Error loading Devoli customers: {e}")
            return

        # Load Xero tokens
        with open('xero_tokens.json', 'r') as f:
            tokens = json.load(f)

        # Set up Xero client
        credentials = {
            'token': tokens['access_token'],
            'tenant_id': tokens['tenant_id']
        }
        xero = Xero(credentials)

        # Get all contacts
        contacts = xero.contacts.all()
        print(f"\n=== Xero Contacts ===")
        print(f"Found {len(contacts)} contacts")
        
        # Create simple lookup
        xero_lookup = {c['Name'].lower(): c['Name'] for c in contacts}
        
        print("\n=== Suggested Mappings ===")
        for devoli_name in devoli_customers:
            print(f"\nDevoli: {devoli_name}")
            # Look for exact match
            if devoli_name.lower() in xero_lookup:
                print(f"✓ Exact match: {xero_lookup[devoli_name.lower()]}")
            else:
                # Look for partial matches
                matches = [name for name in xero_lookup.values() 
                         if devoli_name.lower() in name.lower() or 
                         name.lower() in devoli_name.lower()]
                if matches:
                    print("Possible matches:")
                    for match in matches:
                        print(f"- {match}")
                else:
                    print("❌ No matches found")

    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_xero_contacts() 