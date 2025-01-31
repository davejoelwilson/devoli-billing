import json
import time
import base64
import requests

class XeroTokenManager:
    def __init__(self, client_id, client_secret, token_file):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file

    def refresh_token_if_expired(self, force_refresh=False):
        """Refresh token if expired or force refresh requested"""
        try:
            with open(self.token_file, 'r') as f:
                tokens = json.load(f)
            
            current_time = time.time()
            expires_at = tokens.get('expires_at', 0)
            
            if force_refresh or current_time + 300 > expires_at:  # Refresh if within 5 minutes of expiry
                print("Refreshing token...")
                refresh_token = tokens.get('refresh_token')
                if not refresh_token:
                    raise ValueError("No refresh token available")
                
                # Exchange refresh token for new tokens
                token_url = "https://identity.xero.com/connect/token"
                auth_str = f"{self.client_id}:{self.client_secret}"
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
                
                new_tokens = response.json()
                new_tokens['expires_at'] = time.time() + new_tokens['expires_in']
                
                # Preserve tenant_id
                if 'tenant_id' in tokens:
                    new_tokens['tenant_id'] = tokens['tenant_id']
                
                # Save new tokens
                with open(self.token_file, 'w') as f:
                    json.dump(new_tokens, f, indent=2)
                
                self.tokens = new_tokens
                print("Token refreshed successfully")
            
        except Exception as e:
            print(f"Error refreshing token: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Status Code: {e.response.status_code}")
                print(f"Response Text: {e.response.text}")
            raise 