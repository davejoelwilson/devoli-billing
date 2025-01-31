import pandas as pd
import requests
from xero_auth import XeroTokenManager
from dotenv import load_dotenv
from fuzzywuzzy import fuzz
import os
import json
import traceback
import xml.etree.ElementTree as ET

def parse_xero_response(response):
    """Parse Xero response which could be XML or JSON"""
    content_type = response.headers.get('Content-Type', '')
    
    if 'application/json' in content_type:
        return response.json()['Contacts']
    elif 'text/xml' in content_type or 'application/xml' in content_type:
        # Parse XML
        try:
            root = ET.fromstring(response.text)
            contacts = []
            
            # Find all Contact elements
            for contact in root.findall('.//Contact'):
                contact_data = {
                    'ContactID': contact.find('ContactID').text if contact.find('ContactID') is not None else None,
                    'Name': contact.find('Name').text if contact.find('Name') is not None else None,
                    'IsCustomer': 'true'  # In this context, all contacts are customers
                }
                
                # Only include active contacts
                status = contact.find('ContactStatus')
                if status is not None and status.text == 'ACTIVE':
                    contacts.append(contact_data)
            
            print(f"Successfully parsed {len(contacts)} contacts from XML")
            return contacts
            
        except ET.ParseError as e:
            print("Error parsing XML response:")
            print(response.text[:1000])  # Print first 1000 chars of response
            raise
    else:
        print(f"Unexpected content type: {content_type}")
        print("Response:", response.text[:500])  # Print first 500 chars of response
        raise ValueError(f"Unexpected content type: {content_type}")

def load_customer_mapping():
    """Load and validate the customer mapping from CSV"""
    try:
        mapping_df = pd.read_csv('customer_mapping.csv')
        
        # Filter for rows where actual_xero_name is filled in
        valid_mappings = mapping_df[mapping_df['actual_xero_name'].notna()]
        
        # Create a dictionary of Devoli name to Xero details
        mapping_dict = {}
        for _, row in valid_mappings.iterrows():
            mapping_dict[row['devoli_name']] = {
                'xero_name': row['actual_xero_name'],
                'xero_contact_id': row['xero_contact_id']
            }
        
        print(f"\nLoaded {len(mapping_dict)} valid customer mappings")
        return mapping_dict
    
    except Exception as e:
        print(f"Error loading customer mapping: {str(e)}")
        return None

def create_customer_mapping(process_existing=False):
    """
    Create or process customer mapping
    Args:
        process_existing (bool): If True, load existing mapping instead of creating new one
    """
    if process_existing:
        return load_customer_mapping()
        
    # Initialize
    load_dotenv()
    token_manager = XeroTokenManager()
    
    print("Ensuring valid Xero token...")
    try:
        # Force token refresh
        token_manager.refresh_token_if_expired(force_refresh=True)
        headers = token_manager.get_auth_headers()
    except Exception as e:
        print(f"Error refreshing token: {str(e)}")
        return
    
    print("Fetching Xero contacts...")
    
    # Fetch Xero contacts with error handling
    try:
        response = requests.get(
            "https://api.xero.com/api.xro/2.0/Contacts",
            headers=headers,
            params={"where": "IsCustomer==true"}
        )
        response.raise_for_status()
        
        # Parse response
        xero_contacts = parse_xero_response(response)
        print(f"Successfully fetched {len(xero_contacts)} Xero contacts")
        
    except Exception as e:
        print(f"Error fetching Xero contacts: {str(e)}")
        if hasattr(response, 'text'):
            print("Response text:", response.text[:500])
        return
    
    # Load Devoli CSV
    print("\nLoading Devoli billing data...")
    devoli_df = pd.read_csv("bills/IT360 Limited - Devoli Summary Bill Report 133115 2024-09-30.csv")
    unique_customers = devoli_df['customer_name'].unique()
    print(f"Found {len(unique_customers)} unique customers in Devoli data")
    
    # Create mapping data
    print("\nCreating customer mapping...")
    mapping_data = []
    for devoli_name in unique_customers:
        best_match = None
        best_score = 0
        best_match_id = ''
        top_matches = []  # Store top 3 matches
        
        # Clean the Devoli name
        clean_devoli_name = devoli_name.strip().lower()
        
        for contact in xero_contacts:
            xero_name = contact['Name'].strip()
            clean_xero_name = xero_name.lower()
            
            # Try exact match first
            if clean_xero_name == clean_devoli_name:
                best_match = xero_name
                best_score = 100
                best_match_id = contact.get('ContactID', '')
                break
            
            # Try fuzzy matching
            score = fuzz.ratio(clean_xero_name, clean_devoli_name)
            if score > 30:  # Changed threshold to 30
                top_matches.append((xero_name, score, contact.get('ContactID', '')))
            
            if score > best_score:
                best_score = score
                best_match = xero_name
                best_match_id = contact.get('ContactID', '')
        
        # Sort top matches by score
        top_matches.sort(key=lambda x: x[1], reverse=True)
        top_3_matches = top_matches[:3]
        
        # Format suggested matches string
        suggested_matches = '; '.join([f"{name} ({score}%)" for name, score, _ in top_3_matches])
        
        mapping_data.append({
            'devoli_name': devoli_name,
            'suggested_xero_name': suggested_matches if best_score > 30 else '',
            'actual_xero_name': best_match if best_score == 100 else '',  # Only auto-fill exact matches
            'match_score': best_score,
            'xero_contact_id': best_match_id if best_score == 100 else '',
            'top_matches': suggested_matches
        })
    
    # Create DataFrame and save to CSV
    mapping_df = pd.DataFrame(mapping_data)
    mapping_df = mapping_df.sort_values('match_score', ascending=False)
    
    # Save to CSV
    output_file = 'customer_mapping.csv'
    mapping_df.to_csv(output_file, index=False)
    
    # Print summary
    print(f"\nCreated mapping file: {output_file}")
    print("\nMapping Summary:")
    print(f"Total Devoli customers: {len(unique_customers)}")
    exact_matches = len(mapping_df[mapping_df['match_score'] == 100])
    good_matches = len(mapping_df[(mapping_df['match_score'] > 80) & (mapping_df['match_score'] < 100)])
    medium_matches = len(mapping_df[(mapping_df['match_score'] > 30) & (mapping_df['match_score'] <= 80)])
    poor_matches = len(mapping_df[mapping_df['match_score'] <= 30])
    
    print(f"Exact matches (100% confidence): {exact_matches}")
    print(f"Good matches (>80% confidence): {good_matches}")
    print(f"Medium matches (30-80% confidence): {medium_matches}")
    print(f"Poor matches (<30% confidence): {poor_matches}")
    
    print("\nDetailed Matches:")
    for _, row in mapping_df.iterrows():
        print(f"\nDevoli: {row['devoli_name']}")
        if row['match_score'] == 100:
            print(f"  ✓ Exact match: {row['actual_xero_name']}")
        elif row['top_matches']:
            print(f"  Suggested matches:")
            for match in row['top_matches'].split(';'):
                print(f"    - {match.strip()}")
        else:
            print("  No matches found")
    
    print("\nPlease review customer_mapping.csv and:")
    print("1. Verify the auto-filled exact matches")
    print("2. Review suggested matches")
    print("3. Fill in the 'actual_xero_name' column with the correct Xero contact name")

if __name__ == "__main__":
    try:
        # Set to True to process existing mapping instead of creating new one
        create_customer_mapping(process_existing=True)
    except Exception as e:
        print(f"\nError: {str(e)}")
        traceback.print_exc()
