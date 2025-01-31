import streamlit as st
from devoli_billing import DevoliBilling
import pandas as pd
import os
import json
import time
from datetime import datetime
from .xero_auth import start_auth_flow, debug_auth_setup  # Add this import

def test_xero_connection():
    """Test Xero connection and return status"""
    try:
        processor = DevoliBilling(simulation_mode=True)
        headers = processor.ensure_xero_connection()
        
        # Try to fetch contacts as a test
        response = processor.fetch_xero_contacts()
        
        if response:
            return {
                'status': 'success',
                'message': f'Connected to Xero. Found {len(response)} contacts.',
                'sample_contacts': [c['Name'] for c in response[:5]]
            }
        else:
            return {
                'status': 'error',
                'message': 'No contacts found in Xero'
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error connecting to Xero: {str(e)}'
        }

def test_customer_mapping():
    """Test customer mapping file and show status"""
    try:
        # Try to load mapping file
        mapping_df = pd.read_csv('customer_mapping.csv')
        
        # Basic validation
        required_columns = ['devoli_name', 'actual_xero_name']
        missing_columns = [col for col in required_columns if col not in mapping_df.columns]
        
        if missing_columns:
            return {
                'status': 'error',
                'message': f'Missing required columns: {missing_columns}'
            }
        
        # Check for empty mappings
        empty_mappings = mapping_df[mapping_df['actual_xero_name'].isna() | (mapping_df['actual_xero_name'] == '')]
        
        return {
            'status': 'success',
            'message': f'Found {len(mapping_df)} mappings',
            'total_mappings': len(mapping_df),
            'empty_mappings': len(empty_mappings),
            'sample_mappings': mapping_df.head().to_dict('records')
        }
    except FileNotFoundError:
        return {
            'status': 'error',
            'message': 'Customer mapping file not found'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error loading customer mapping: {str(e)}'
        }

def test_xero_auth_files():
    """Test if Xero auth files exist and are valid"""
    try:
        # Check token file
        token_file = 'xero_tokens.json'
        if not os.path.exists(token_file):
            return {
                'status': 'error',
                'message': 'xero_tokens.json not found'
            }
            
        with open(token_file, 'r') as f:
            tokens = json.load(f)
            
        # Check required token fields
        required_fields = ['access_token', 'refresh_token', 'expires_at', 'tenant_id']
        missing_fields = [f for f in required_fields if f not in tokens]
        
        if missing_fields:
            return {
                'status': 'error',
                'message': f'Missing fields in token file: {missing_fields}'
            }
            
        # Check if token is expired
        if tokens['expires_at'] < time.time():
            return {
                'status': 'warning',
                'message': 'Token is expired and needs refresh',
                'expires_at': datetime.fromtimestamp(tokens['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
            }
            
        return {
            'status': 'success',
            'message': 'Auth files look valid',
            'expires_at': datetime.fromtimestamp(tokens['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error checking auth files: {str(e)}'
        }

def test_page():
    """Streamlit page for testing Xero and mappings"""
    st.title("Xero Integration Tests")
    
    # Debug environment setup
    st.subheader("Environment Setup")
    if st.button("Check Environment"):
        env_info = debug_auth_setup()
        st.write("Environment Variables:")
        st.json(env_info)
    
    # Add auth file check first
    st.subheader("Xero Authentication")
    col1, col2 = st.columns([2,1])
    
    with col1:
        if st.button("Check Auth Files"):
            result = test_xero_auth_files()
            if result['status'] == 'success':
                st.success(result['message'])
                st.write(f"Token expires: {result['expires_at']}")
            elif result['status'] == 'warning':
                st.warning(result['message'])
                st.write(f"Token expired: {result['expires_at']}")
            else:
                st.error(result['message'])
    
    with col2:
        if st.button("Re-authenticate Xero"):
            with st.spinner("Authenticating with Xero..."):
                result = start_auth_flow()
                if result['status'] == 'success':
                    st.success(result['message'])
                    st.write(f"New token expires: {result['expires_at']}")
                else:
                    st.error(result['message'])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Xero Connection")
        if st.button("Test Xero Connection"):
            result = test_xero_connection()
            if result['status'] == 'success':
                st.success(result['message'])
                st.write("Sample contacts:", result['sample_contacts'])
            else:
                st.error(result['message'])
    
    with col2:
        st.subheader("Customer Mapping")
        if st.button("Test Customer Mapping"):
            result = test_customer_mapping()
            if result['status'] == 'success':
                st.success(result['message'])
                st.write(f"Total mappings: {result['total_mappings']}")
                st.write(f"Empty mappings: {result['empty_mappings']}")
                st.write("Sample mappings:")
                st.dataframe(pd.DataFrame(result['sample_mappings']))
            else:
                st.error(result['message'])

if __name__ == "__main__":
    test_page() 