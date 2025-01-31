import streamlit as st
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
import requests
import os
from datetime import datetime, timezone
import time
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()

# Get credentials from environment variables
CLIENT_ID = os.getenv('XERO_CLIENT_ID')
CLIENT_SECRET = os.getenv('XERO_CLIENT_SECRET')
CALLBACK_PORT = 8080
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}"

# Validate credentials
if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError(
        "Missing Xero credentials. Please set XERO_CLIENT_ID and XERO_CLIENT_SECRET "
        "in your .env file. Get these from https://developer.xero.com/app/manage"
    )

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authentication successful! You can close this window.")
        
        self.server.stop = True

def get_authorization_url():
    """Generate the Xero authorization URL"""
    # Required scopes for our application
    scope = (
        "offline_access "  # For refresh token
        "openid profile email "  # Basic user info
        "accounting.transactions "  # For creating invoices
        "accounting.contacts"  # For customer lookups
    )
    
    # Generate state for security
    state = os.urandom(16).hex()
    
    auth_url = (
        "https://login.xero.com/identity/connect/authorize?"
        f"response_type=code&"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"scope={scope}&"
        f"state={state}"
    )
    return auth_url, state

def exchange_code_for_tokens(auth_code):
    """Exchange authorization code for tokens"""
    token_url = "https://identity.xero.com/connect/token"
    
    # Create Basic auth header
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI
    }
    
    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    
    tokens = response.json()
    tokens['expires_at'] = time.time() + tokens['expires_in']
    
    # Save tokens
    with open('xero_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)
    
    return tokens

def refresh_token(refresh_token):
    """Refresh an expired access token"""
    token_url = "https://identity.xero.com/connect/token"
    
    # Create Basic auth header
    auth_str = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {auth_header}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status()
    
    tokens = response.json()
    tokens['expires_at'] = time.time() + tokens['expires_in']
    
    # Save new tokens
    with open('xero_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)
    
    return tokens

def start_auth_flow():
    """Start the Xero authentication flow"""
    try:
        # Start local server to catch callback with the new port
        server = HTTPServer(('localhost', CALLBACK_PORT), CallbackHandler)
        server.auth_code = None
        server.stop = False
        
        # Set socket timeout to prevent hanging
        server.socket.settimeout(60)  # 60 second timeout
        
        # Open browser for auth
        auth_url, state = get_authorization_url()
        webbrowser.open(auth_url)
        
        try:
            # Wait for callback
            while not server.stop:
                server.handle_request()
        finally:
            # Always close the server
            server.server_close()
        
        if server.auth_code:
            try:
                tokens = exchange_code_for_tokens(server.auth_code)
                return {
                    'status': 'success',
                    'message': 'Authentication successful',
                    'expires_at': datetime.fromtimestamp(tokens['expires_at']).strftime('%Y-%m-%d %H:%M:%S')
                }
            except Exception as e:
                return {
                    'status': 'error',
                    'message': f'Error exchanging code for tokens: {str(e)}'
                }
        else:
            return {
                'status': 'error',
                'message': 'No authorization code received'
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error in auth flow: {str(e)}'
        }

def debug_auth_setup():
    """Debug function to check auth setup"""
    env_vars = {
        'XERO_CLIENT_ID': os.getenv('XERO_CLIENT_ID'),
        'XERO_CLIENT_SECRET': bool(os.getenv('XERO_CLIENT_SECRET')),  # Show only existence for security
        'XERO_REDIRECT_URI': os.getenv('XERO_REDIRECT_URI'),
        'ENV_FILE_LOADED': os.path.exists('.env'),
        'ENV_FILE_PATH': os.path.abspath('.env')
    }
    return env_vars

def get_connected_tenants(access_token):
    """Get list of connected Xero tenants"""
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get("https://api.xero.com/connections", headers=headers)
        response.raise_for_status()
        
        return {
            'status': 'success',
            'tenants': response.json()
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error getting tenants: {str(e)}'
        }

def verify_connection():
    """Verify Xero connection and show tenant info"""
    try:
        # Load current tokens
        with open('xero_tokens.json', 'r') as f:
            tokens = json.load(f)
        
        # Get tenants
        tenant_result = get_connected_tenants(tokens['access_token'])
        
        if tenant_result['status'] == 'success':
            return {
                'status': 'success',
                'message': 'Connection verified',
                'expires_at': datetime.fromtimestamp(tokens['expires_at']).strftime('%Y-%m-%d %H:%M:%S'),
                'tenants': tenant_result['tenants']
            }
        else:
            return tenant_result
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error verifying connection: {str(e)}'
        }

def save_tenant_id(tenant_id):
    """Save selected tenant ID to token file"""
    try:
        with open('xero_tokens.json', 'r') as f:
            tokens = json.load(f)
        
        tokens['tenant_id'] = tenant_id
        
        with open('xero_tokens.json', 'w') as f:
            json.dump(tokens, f, indent=2)
            
        return {
            'status': 'success',
            'message': f'Tenant ID saved: {tenant_id}'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error saving tenant ID: {str(e)}'
        }

def test_page():
    st.title("=== Xero Authentication (Debug Mode) ===")
    
    # Load and display environment info
    load_dotenv()
    env_info = debug_auth_setup()
    
    # Show current environment status
    st.write("Current Environment Setup:")
    if env_info['XERO_CLIENT_ID']:
        st.success(f"Client ID: {env_info['XERO_CLIENT_ID']}")
    else:
        st.error("Client ID not found in environment")
        
    if env_info['XERO_CLIENT_SECRET']:
        st.success("Client Secret: [Found]")
    else:
        st.error("Client Secret not found in environment")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Add authentication button
        if st.button("Start Authentication"):
            with st.spinner("Starting authentication flow..."):
                result = start_auth_flow()
                if result['status'] == 'success':
                    st.success(result['message'])
                    st.write(f"Token expires at: {result['expires_at']}")
                else:
                    st.error(result['message'])
    
    with col2:
        # Add verify connection button
        if st.button("Verify Connection"):
            with st.spinner("Verifying connection..."):
                result = verify_connection()
                if result['status'] == 'success':
                    st.success(result['message'])
                    st.write(f"Token expires at: {result['expires_at']}")
                    
                    # Show tenant selection
                    st.write("Select Tenant:")
                    for tenant in result['tenants']:
                        tenant_name = tenant.get('tenantName', 'Unnamed')
                        tenant_id = tenant.get('tenantId')
                        if st.button(f"Use {tenant_name}", key=tenant_id):
                            save_result = save_tenant_id(tenant_id)
                            if save_result['status'] == 'success':
                                st.success(f"Selected tenant: {tenant_name}")
                            else:
                                st.error(save_result['message'])

    # Add test invoice section
    st.subheader("Test Invoice Creation")
    if st.button("Create Test Invoice"):
        with st.spinner("Creating test invoice..."):
            result = test_create_invoice()
            if result['status'] == 'success':
                st.success(result['message'])
                st.json(result['invoice'])
            else:
                st.error(result['message'])

def test_create_invoice():
    """Test creating a simple invoice"""
    try:
        # Load tokens
        with open('xero_tokens.json', 'r') as f:
            tokens = json.load(f)
        
        if 'tenant_id' not in tokens:
            return {
                'status': 'error',
                'message': 'No tenant ID selected. Please select a tenant first.'
            }
        
        headers = {
            'Authorization': f"Bearer {tokens['access_token']}",
            'Content-Type': 'application/json',
            'xero-tenant-id': tokens['tenant_id']
        }
        
        # Create a test invoice
        invoice = {
            "Type": "ACCREC",
            "Contact": {
                "Name": "Test Contact"
            },
            "LineItems": [
                {
                    "Description": "Test Item",
                    "Quantity": 1.0,
                    "UnitAmount": 20.0,
                    "AccountCode": "200"
                }
            ],
            "Status": "DRAFT"
        }
        
        response = requests.post(
            "https://api.xero.com/api.xro/2.0/Invoices",
            headers=headers,
            json=invoice
        )
        response.raise_for_status()
        
        return {
            'status': 'success',
            'message': 'Test invoice created',
            'invoice': response.json()
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error creating test invoice: {str(e)}'
        } 