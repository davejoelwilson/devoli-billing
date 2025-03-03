# Devoli Billing - VoIP

A streamlined billing processor for Devoli VoIP services that integrates with Xero for invoice generation.

## Features

- Automated processing of Devoli VoIP call data
- Special handling for The Service Company billing requirements
- Direct integration with Xero for invoice generation
- Support for toll-free and regular number billing
- Customer name mapping between Devoli and Xero
- Detailed call breakdown and charge calculations

## Prerequisites

- Python 3.11+
- Xero API credentials
- Devoli billing data in CSV format

## Installation

1. Clone the repository:
```bash
git clone https://github.com/davejoelwilson/devoli-billing.git
cd devoli-billing
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Xero authentication:
   - Create a Xero app at https://developer.xero.com
   - Configure OAuth2 credentials
   - Place credentials in `.xero_creds` file

## Configuration

1. Customer Mapping:
   - Update `customer_mapping.csv` with Devoli to Xero customer name mappings
   - Run `python run_mapping.py` to validate mappings

2. Product Mapping:
   - Ensure `product_mapping.csv` contains correct product codes
   - Update rates in `service_company.py` if needed

## Authentication Setup

1. Create a Xero app at https://developer.xero.com/app/manage/
2. Configure the OAuth2 settings:
   - Redirect URI: `http://localhost:8080`
   - Make sure this matches exactly - the app uses port 8080 for auth callbacks
3. Copy your Client ID and Client Secret
4. Create a `.env` file with:
   ```
   XERO_CLIENT_ID=your_client_id
   XERO_CLIENT_SECRET=your_client_secret
   ```

## Usage

1. Place Devoli invoice CSV files in the `bills` directory

2. Run the Streamlit application:
```bash
streamlit run streamlit_app.py
```

3. In the web interface:
   - Select the invoice file to process
   - Review customer data and charges
   - Select companies to process
   - Generate Xero invoices

## Invoice Date Logic

The system uses a specific logic for setting invoice dates:

- **Invoice Date**: Set to the last day of the month that is 2 months after the CSV file date
  - Example: CSV file for December 31, 2023 → Invoice date February 29, 2024
  - Example: CSV file for January 31, 2024 → Invoice date March 31, 2024

- **Due Date**: Set to 20 days after the invoice date

This ensures consistent invoice dating aligned with billing cycles.

## Special Cases

### The Service Company Billing

- Base fee of $55.00
- Separate line items for:
  - Regular number (6492003366)
  - Each toll-free number
- Detailed call breakdowns including:
  - Call counts
  - Duration
  - Type (Local, Mobile, National, Australia)

## Special Customer Handling

### SPARK Customers
- Any customer with "SPARK" in their name automatically receives a 6% discount on calling charges
- The discount is shown as a separate line item in Xero invoices
- The discount line uses account code 45900 (SPARK Sales account)
- GST is calculated on the net amount after the discount is applied
- The discount appears in the processing table as:
  - Original call charges (ex GST)
  - Discount amount (6%)
  - Net amount after discount
  - Call charges including GST (calculated on net amount)

## Troubleshooting

1. Xero Authentication:
   - Check `.xero_creds` file exists
   - Verify OAuth2 token is valid
   - Run `python test_xero.py` to test connection

2. Missing Customers:
   - Verify customer exists in `customer_mapping.csv`
   - Check customer name spelling matches Devoli data

3. Incorrect Charges:
   - Verify rates in `service_company.py`
   - Check call data format in CSV

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please contact the development team or raise an issue on GitHub.

# Devoli Billing Analysis

A streamlit application for analyzing Devoli billing data and product trends.

## Features

### Product Analysis Page

The product analysis page provides comprehensive insights into billing data across multiple views:

1. **Summary Tab**
   - Product Summary table showing quantity and revenue by product type
   - Top 5 Products by Revenue visualization
   - Filters out low-quantity items for cleaner analysis

2. **Customer Analysis Tab**
   - Products by Customer matrix showing product distribution
   - Top 10 Customers by Number of Products chart
   - Detailed breakdown of products per customer

3. **Revenue Analysis Tab**
   - Revenue breakdown by product category
   - Category distribution visualization
   - Key metrics:
     - Total Monthly Revenue
     - Average Revenue per Customer
     - Average Revenue per Product

4. **Trends Tab**
   - Current Month Overview with key metrics
   - Category Breakdown showing revenue distribution
   - Interactive time series charts:
     - Unique Customers Over Time
     - Total Products Over Time
     - Total Revenue Over Time (with 3-month moving average)
     - Revenue by Category Over Time
   - Year-over-Year Growth Rate (when sufficient data available)
   - Revenue Distribution pie chart
   - Monthly data tables with detailed breakdowns

## Usage

1. Place invoice CSV files in the `bills` directory
2. Run the Streamlit app:
   ```bash
   streamlit run streamlit_app.py
   ```
3. Select an invoice from the dropdown to analyze
4. Navigate through the tabs to view different aspects of the analysis

## Data Requirements

Invoice files should:
- Be in CSV format
- Start with "Invoice_"
- Include date in filename (e.g., "Invoice_XXX_2024-01.csv")
- Contain columns:
  - description
  - amount
  - customer name

## Dependencies

- streamlit
- pandas
- plotly
- python-dateutil 