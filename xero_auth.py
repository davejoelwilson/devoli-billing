import requests
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
import webbrowser
import urllib.parse
import secrets
import json
import os
import time
from typing import Optional, Dict, List
import sys

class XeroTokenManager:
    def __init__(self, token_file: str = 'xero_tokens.json'):
        self.token_file = token_file
        self.tokens = self._load_tokens()
        
        # Load client credentials from environment variables
        self.client_id = os.getenv('XERO_CLIENT_ID')
        self.client_secret = os.getenv('XERO_CLIENT_SECRET')
        
        if not self.client_id or not self.client_secret:
            # Try to load from a config file if environment variables are not set
            try:
                with open('xero_config.json', 'r') as f:
                    config = json.load(f)
                    self.client_id = config.get('client_id')
                    self.client_secret = config.get('client_secret')
            except:
                pass
    
    def _load_tokens(self) -> Dict:
        """Load tokens from file"""
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}
    
    def _save_tokens(self) -> None:
        """Save tokens to file"""
        with open(self.token_file, 'w') as f:
            json.dump(self.tokens, f, indent=2)
    
    def update_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        """Update tokens with new values"""
        self.tokens.update({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': time.time() + expires_in,
            'tenant_id': self.tokens.get('tenant_id')  # Preserve tenant ID
        })
        self._save_tokens()
    
    def set_tenant_id(self, tenant_id: str) -> None:
        """Set the active tenant ID"""
        self.tokens['tenant_id'] = tenant_id
        self._save_tokens()

    def get_auth_headers(self) -> Dict[str, str]:
        """Get headers for API requests"""
        tokens = self._load_tokens()
        if not tokens or 'access_token' not in tokens:
            raise ValueError("No access token available")
            
        headers = {
            'Authorization': f'Bearer {tokens["access_token"]}',
            'Content-Type': 'application/json'
        }
        
        # Add tenant ID if available
        if 'tenant_id' in tokens:
            headers['xero-tenant-id'] = tokens['tenant_id']
            
        return headers

    def refresh_token_if_expired(self, force_refresh=False):
        """
        Check if token is expired and refresh if needed
        
        Args:
            force_refresh (bool): Force token refresh regardless of expiration
        """
        try:
            with open('xero_tokens.json', 'r') as f:
                token_data = json.load(f)
                
            # Check if token is expired or force refresh is requested
            if force_refresh or self._is_token_expired(token_data):
                print("Refreshing Xero token...")
                self.refresh_token()
                print("Token refreshed successfully")
        except FileNotFoundError:
            print("No token file found. Please authenticate first.")
            sys.exit(1)
        except Exception as e:
            print(f"Error refreshing token: {str(e)}")
            sys.exit(1)

    def _is_token_expired(self, token_data):
        """Check if the token is expired"""
        expires_at = token_data.get('expires_at', 0)
        # Add 5 minute buffer before expiration
        return time.time() + 300 > expires_at

    def refresh_token(self) -> None:
        """Refresh the access token using the refresh token"""
        token_url = "https://identity.xero.com/connect/token"
        
        try:
            # Load current tokens
            tokens = self._load_tokens()
            if not tokens or 'refresh_token' not in tokens:
                raise ValueError("No refresh token available")

            # Get client credentials from environment or stored configuration
            if not self.client_id or not self.client_secret:
                # You might want to load these from environment variables or a config file
                raise ValueError("Client credentials not configured")

            # Create Basic auth header
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('utf-8')
            auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
            
            headers = {
                "Authorization": f"Basic {auth_b64}",
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": tokens['refresh_token']
            }
            
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            
            # Update tokens with new values
            self.update_tokens(
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                expires_in=token_data['expires_in']
            )
            
            print("Token refresh successful")
            
        except Exception as e:
            print(f"Error refreshing token: {str(e)}")
            raise

class XeroAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle the callback from Xero"""
        print(f"\nReceived callback with path: {self.path}")
        query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        print(f"Query components: {query_components}")
        
        if 'code' in query_components:
            self.server.auth_code = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Authentication successful! You can close this window.")
        else:
            print(f"No authorization code found in callback")
        
        self.server.stop = True

class StoppableHTTPServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auth_code = None
        self.stop = False
    
    def serve_forever(self):
        while not self.stop:
            self.handle_request()

class XeroAuth:
    def __init__(self, client_id: str, client_secret: str, scope: str = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = "http://localhost:8080"
        self.scope = scope or "offline_access openid profile email accounting.transactions accounting.contacts"
        self.access_token = None
        self.refresh_token = None
        self.token_expires_in = None
        self.token_manager = XeroTokenManager()
    
    def _get_basic_auth_header(self):
        """Create Basic auth header"""
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        return f"Basic {auth_b64}"
    
    def get_authorization_code(self):
        """Get authorization code via browser"""
        state = secrets.token_urlsafe(32)
        
        auth_url = (
            "https://login.xero.com/identity/connect/authorize?"
            f"response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={urllib.parse.quote(self.redirect_uri)}"
            f"&scope={urllib.parse.quote(self.scope)}"
            f"&state={state}"
        )
        
        print("\nOpening browser for authentication...")
        server = StoppableHTTPServer(('localhost', 8080), XeroAuthHandler)
        webbrowser.open(auth_url)
        
        server.serve_forever()
        return server.auth_code

    def exchange_code_for_tokens(self, auth_code: str) -> bool:
        """Exchange authorization code for access and refresh tokens"""
        token_url = "https://identity.xero.com/connect/token"
        headers = {
            "Authorization": self._get_basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri
        }
        
        try:
            response = requests.post(token_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            self.access_token = token_data.get("access_token")
            self.refresh_token = token_data.get("refresh_token")
            self.token_expires_in = token_data.get("expires_in")
            
            # Save tokens using token manager
            self.token_manager.update_tokens(
                self.access_token,
                self.refresh_token,
                self.token_expires_in
            )
            
            print("\nToken exchange successful!")
            print(f"Access token received: {self.access_token[:10]}...")
            print(f"Refresh token received: {self.refresh_token[:10]}...")
            print(f"Token expires in: {self.token_expires_in} seconds")
            
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"\nError exchanging code for tokens: {str(e)}")
            return False

    def get_connected_tenants(self) -> List[Dict]:
        """Get list of tenants connected to this application"""
        if not self.access_token:
            print("No access token available")
            return []
            
        connections_url = "https://api.xero.com/connections"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(connections_url, headers=headers)
            response.raise_for_status()
            tenants = response.json()
            
            print("\nConnected tenants:")
            for tenant in tenants:
                print(f"- {tenant.get('tenantName', 'Unnamed')} ({tenant.get('tenantId')})")
                # Set the first tenant as active
                if tenant == tenants[0]:
                    self.token_manager.set_tenant_id(tenant['tenantId'])
            
            return tenants
            
        except requests.exceptions.RequestException as e:
            print(f"\nError getting connected tenants: {str(e)}")
            return []

def main():
    print("=== Xero Authentication (Debug Mode) ===")
    
    client_id = input("Enter Client ID: ").strip()
    client_secret = input("Enter Client Secret: ").strip()
    
    try:
        auth = XeroAuth(client_id, client_secret)
        
        print("\nStep 1: Getting authorization code...")
        auth_code = auth.get_authorization_code()
        
        if not auth_code:
            print("Failed to get authorization code")
            return
            
        print("\nStep 2: Exchanging code for tokens...")
        if not auth.exchange_code_for_tokens(auth_code):
            print("Failed to exchange code for tokens")
            return
            
        print("\nStep 3: Getting connected tenants...")
        tenants = auth.get_connected_tenants()
        
        if not tenants:
            print("No tenants connected")
            return
            
        print("\nAuthentication and connection verification complete!")
        print("Tokens have been saved to xero_tokens.json")
        
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
