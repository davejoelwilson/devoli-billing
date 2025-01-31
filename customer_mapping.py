import streamlit as st
import pandas as pd
from fuzzywuzzy import fuzz
from devoli_billing import DevoliBilling
import json
import time
from datetime import datetime
import requests

def load_devoli_customers(df):
    """Extract unique customer names from Devoli invoice"""
    # Debug print columns
    st.write("Available columns:", df.columns.tolist())
    
    # Check if 'Customer Name' exists, if not try alternatives
    if 'Customer Name' in df.columns:
        customer_col = 'Customer Name'
    elif 'customer_name' in df.columns:
        customer_col = 'customer_name'
    else:
        # Show sample of data to help debug
        st.write("First few rows of data:")
        st.dataframe(df.head())
        raise ValueError("Could not find customer name column. Available columns: " + ", ".join(df.columns))
    
    # Get unique customers
    customers = df[customer_col].dropna().unique()
    
    # Debug print
    st.write(f"Found {len(customers)} unique customers")
    
    return sorted(customers)

def load_xero_contacts():
    """Get contacts from Xero"""
    try:
        processor = DevoliBilling()
        contacts = processor.fetch_xero_contacts()
        if contacts:
            return [contact['Name'] for contact in contacts]
        return []
    except Exception as e:
        st.error(f"Error fetching Xero contacts: {e}")
        return []

def find_matches(devoli_name, xero_contacts, threshold=50):
    """Find potential matches for a Devoli customer name"""
    matches = []
    for xero_name in xero_contacts:
        score = fuzz.ratio(devoli_name.lower(), xero_name.lower())
        if score >= threshold:
            matches.append((xero_name, score))
    return sorted(matches, key=lambda x: x[1], reverse=True)

def debug_xero_tokens():
    """Debug Xero token status"""
    try:
        with open('xero_tokens.json', 'r') as f:
            tokens = json.load(f)
            
        # Check token expiry
        current_time = time.time()
        expires_at = tokens.get('expires_at', 0)
        expires_in = expires_at - current_time
        
        return {
            'status': 'success',
            'has_access_token': bool(tokens.get('access_token')),
            'has_refresh_token': bool(tokens.get('refresh_token')),
            'has_tenant_id': bool(tokens.get('tenant_id')),
            'expires_in_minutes': round(expires_in / 60, 1),
            'is_expired': expires_in <= 0,
            'expires_at': datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S')
        }
    except FileNotFoundError:
        return {
            'status': 'error',
            'message': 'No token file found'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error reading tokens: {str(e)}'
        }

def check_xero_connection():
    """Check and verify Xero connection"""
    try:
        # First check token status
        token_status = debug_xero_tokens()
        if token_status['status'] == 'error':
            return token_status
            
        if token_status['is_expired']:
            return {
                'status': 'error',
                'message': 'Token expired. Please re-authenticate.',
                'token_status': token_status
            }
            
        processor = DevoliBilling(simulation_mode=False)  # Ensure simulation mode is off
        
        # Try to refresh token if needed
        if token_status['expires_in_minutes'] < 5:  # Less than 5 minutes remaining
            processor.token_manager.refresh_token_if_expired(force_refresh=True)
            token_status = debug_xero_tokens()  # Get updated status
        
        # Test connection by fetching contacts
        contacts = processor.fetch_xero_contacts()
        if contacts:
            return {
                'status': 'success',
                'message': f'Connected to Xero ({len(contacts)} contacts found)',
                'contacts': contacts,
                'token_status': token_status
            }
        return {
            'status': 'error',
            'message': 'No contacts found in Xero',
            'token_status': token_status
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error connecting to Xero: {str(e)}',
            'token_status': token_status if 'token_status' in locals() else None
        }

def test_xero_connection():
    """Test Xero connection with detailed error reporting"""
    try:
        processor = DevoliBilling(simulation_mode=False)
        
        # First ensure connection and get headers
        headers = processor.ensure_xero_connection()
        
        # Test fetching contacts
        response = requests.get(
            "https://api.xero.com/api.xro/2.0/Contacts",
            headers=headers
        )
        response.raise_for_status()
        
        return {
            'status': 'success',
            'message': 'Connection successful',
            'headers': {k: v[:20] + '...' if k == 'Authorization' else v for k, v in headers.items()}
        }
        
    except Exception as e:
        error_details = {
            'error': str(e),
            'type': type(e).__name__
        }
        if hasattr(e, 'response'):
            error_details.update({
                'status_code': e.response.status_code,
                'response_text': e.response.text
            })
        return {
            'status': 'error',
            'message': 'Connection failed',
            'details': error_details
        }

def load_voip_customers(df):
    """Load only customers with VoIP/calling products"""
    voip_products = [
        'DDI',
        'SIP Line',
        'SIP Trunk',
        'Calling',
        'Voice'
    ]
    
    mask = df['Description'].str.contains('|'.join(voip_products), case=False, na=False)
    voip_df = df[mask]
    return sorted(voip_df['Customer Name'].dropna().unique()), voip_df

def mapping_page():
    st.title("Customer Mapping Tool")
    
    # Load existing mappings
    try:
        mapping_df = pd.read_csv('customer_mapping.csv')
        st.write("### Current Mappings")
        st.dataframe(mapping_df)
        existing_map = dict(zip(mapping_df['devoli_name'], mapping_df['actual_xero_name']))
    except:
        existing_map = {}
    
    # File upload
    uploaded_file = st.file_uploader("Upload Devoli Invoice CSV", type=['csv'])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        voip_customers, voip_df = load_voip_customers(df)
        
        st.write(f"Found {len(voip_customers)} VoIP customers")
        
        # Mapping interface
        mappings = {}
        for devoli_name in voip_customers:
            col1, col2 = st.columns([2,3])
            with col1:
                st.write(f"**{devoli_name}**")
                if st.checkbox(f"Show products for {devoli_name}"):
                    products = voip_df[voip_df['Customer Name'] == devoli_name]['Description'].unique()
                    for prod in products:
                        st.write(f"- {prod}")
            
            with col2:
                current = existing_map.get(devoli_name)
                if current:
                    st.info(f"Current: {current}")
                
                xero_name = st.text_input(
                    "Xero name",
                    value=current or '',
                    key=f"input_{devoli_name}"
                )
                
                if xero_name:
                    mappings[devoli_name] = xero_name
        
        # Save button
        if mappings and st.button("Save Mappings"):
            mapping_data = []
            for devoli_name, xero_name in mappings.items():
                if xero_name.strip():
                    mapping_data.append({
                        'devoli_name': devoli_name,
                        'actual_xero_name': xero_name
                    })
            
            mapping_df = pd.DataFrame(mapping_data)
            mapping_df.to_csv('customer_mapping.csv', index=False)
            st.success(f"Saved {len(mapping_data)} mappings to customer_mapping.csv")

if __name__ == "__main__":
    mapping_page() 