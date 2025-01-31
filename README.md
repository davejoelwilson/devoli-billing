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