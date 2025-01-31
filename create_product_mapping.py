import pandas as pd
import os
from datetime import datetime

def create_product_mapping():
    print("\n=== Creating Product Mapping ===\n")
    
    # Create output directory if it doesn't exist
    os.makedirs('output', exist_ok=True)
    
    # Load billing data
    billing_df = pd.read_csv("bills/IT360 Limited - Devoli Summary Bill Report 133115 2024-09-30.csv")
    
    # Extract unique products with their details
    products = []
    
    for _, row in billing_df.iterrows():
        # Use product as primary identifier
        product = str(row['product']).strip() if pd.notna(row.get('product')) else ''
        
        # Calculate sale price (cost + 15% margin)
        cost = float(row['amount'])
        sale_price = round(cost * 1.15, 2)
        
        products.append({
            'product_code': product,
            'description': row['description'],
            'cost': cost,
            'sale_price': sale_price,
            'margin': '15%',
            'period': f"{row['start_date']} - {row['end_date']}",
            'notes': ''  # For any manual additions/notes
        })
    
    # Convert to DataFrame
    products_df = pd.DataFrame(products)
    
    # Remove duplicates based on product code and cost
    products_df = products_df.drop_duplicates(subset=['product_code', 'cost'])
    
    # Sort by product code and cost
    products_df = products_df.sort_values(['product_code', 'cost'])
    
    # Save to CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f'output/product_mapping_{timestamp}.csv'
    products_df.to_csv(output_file, index=False)
    
    # Print summary
    print(f"Found {len(products_df)} unique products")
    print("\nProduct Codes:")
    for code in sorted(products_df['product_code'].unique()):
        if pd.notna(code) and code.strip():  # Only show non-empty codes
            count = len(products_df[products_df['product_code'] == code])
            print(f"- {code}: {count} variations")
    
    print(f"\nProduct mapping saved to: {output_file}")
    print("\nPlease review the product mapping CSV and:")
    print("1. Verify the product codes and descriptions")
    print("2. Verify the auto-calculated sale prices")
    print("3. Adjust margins as needed")
    print("4. Add any notes or additional information")
    
    return products_df

if __name__ == "__main__":
    try:
        create_product_mapping()
    except Exception as e:
        print(f"\nError: {str(e)}")
        import traceback
        traceback.print_exc()
