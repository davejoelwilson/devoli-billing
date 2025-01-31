from devoli_billing import DevoliBilling

def lookup_xero_contact(search_name):
    """Look up a Xero contact by name"""
    processor = DevoliBilling()
    
    print(f"\nSearching for: {search_name}")
    print("-" * 50)
    
    # Fetch all Xero contacts
    contacts = processor.fetch_xero_contacts()
    
    if not contacts:
        print("No contacts found in Xero")
        return
    
    # Search for exact and partial matches
    exact_matches = []
    partial_matches = []
    
    search_name = search_name.lower()
    for contact in contacts:
        contact_name = contact['Name'].lower()
        if contact_name == search_name:
            exact_matches.append(contact)
        elif search_name in contact_name:
            partial_matches.append(contact)
    
    # Print results
    if exact_matches:
        print("\nExact Matches:")
        print("=" * 20)
        for contact in exact_matches:
            print(f"Name: {contact['Name']}")
            print(f"Contact ID: {contact.get('ContactID', 'N/A')}")
            print(f"Status: {contact.get('ContactStatus', 'N/A')}")
            # Add email information
            print(f"Email: {contact.get('EmailAddress', 'N/A')}")
            # Add accounts email if different
            accounts_email = contact.get('AccountsReceivableEmail', contact.get('EmailAddress', 'N/A'))
            if accounts_email != contact.get('EmailAddress'):
                print(f"Accounts Email: {accounts_email}")
            print("-" * 20)
    
    if partial_matches:
        print("\nPartial Matches:")
        print("=" * 20)
        for contact in partial_matches:
            print(f"Name: {contact['Name']}")
            print(f"Contact ID: {contact.get('ContactID', 'N/A')}")
            print(f"Status: {contact.get('ContactStatus', 'N/A')}")
            print(f"Email: {contact.get('EmailAddress', 'N/A')}")
            accounts_email = contact.get('AccountsReceivableEmail', contact.get('EmailAddress', 'N/A'))
            if accounts_email != contact.get('EmailAddress'):
                print(f"Accounts Email: {accounts_email}")
            print("-" * 20)
    
    if not exact_matches and not partial_matches:
        print("No matches found")

def main():
    search_name = "Dyer Whitechurch Lawyers (SPARK)"  # Default search
    lookup_xero_contact(search_name)

if __name__ == "__main__":
    main() 