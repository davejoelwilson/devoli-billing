# Technical Documentation

## Architecture Overview

The application is structured into several key components:

### Core Components

1. **Billing Processor (`devoli_billing.py`)**
   - Main class: `DevoliBilling`
   - Handles Xero integration
   - Manages invoice creation
   - Implements core billing logic

2. **Service Company Handler (`service_company.py`)**
   - Main class: `ServiceCompanyBilling`
   - Special case billing logic
   - Call rate calculations
   - Duration and charge computations

3. **Xero Integration (`xero_auth.py`, `xero_token_manager.py`)**
   - OAuth2 authentication
   - Token management
   - API request handling

4. **Web Interface (`streamlit_app.py`)**
   - User interface using Streamlit
   - File selection and processing
   - Invoice review and generation

5. **Log Management (`log_database.py`)**
   - Tracks processed invoices
   - Manages file processing history
   - Prevents duplicate processing
   - Supports multi-month invoice creation

### Data Flow

1. **Input Processing**
   ```
   CSV File → DevoliBilling.load_voip_customers() → DataFrame
   ```

2. **Billing Calculation**
   ```
   For regular customers:
   DataFrame → calculate_call_charges() → Charges + Details

   For Service Company:
   DataFrame → ServiceCompanyBilling.process_billing() → Detailed Results
   ```

3. **Invoice Generation**
   ```
   Billing Data → create_xero_invoice() → Xero API → Invoice
   ```

4. **Log Management**
   ```
   Process Result → log_db.mark_invoice_as_processed() → SQLite Database
   ```

## Implementation Details

### Call Processing

1. **Regular Numbers**
   ```python
   def calculate_call_charges(self, data):
       # Groups calls by type
       # Calculates minutes
       # Applies rates
       return charges, call_details
   ```

2. **Toll-Free Numbers**
   ```python
   def process_billing(self, df):
       # Filters TFree numbers
       # Processes each number separately
       # Adds base fee
       return results
   ```

### Rate Structure

```python
rates = {
    'Local': 0.05,
    'Mobile': 0.12,
    'National': 0.05,
    'Australia': 0.14,
    'TFree Inbound - Mobile': 0.28,
    'TFree Inbound - National': 0.10,
    'TFree Inbound - Australia': 0.14,
    'TFree Inbound - Other': 0.14
}
```

### Customer Mapping

- CSV format: `devoli_name,actual_xero_name`
- Loaded at runtime
- Case-sensitive matching

### Xero Integration

1. **Authentication Flow**
   ```
   1. Load credentials
   2. Request OAuth2 token
   3. Refresh as needed
   4. Store in xero_tokens.json
   ```

2. **Invoice Creation**
   ```python
   invoice_data = {
       "Type": "ACCREC",
       "Contact": {"ContactID": contact_id},
       "LineItems": [...],
       "Status": "DRAFT"
   }
   ```

### Invoice Date Calculation

The application uses a specific algorithm to determine invoice dates:

1. **Date Extraction**:
   - The original date is extracted from the invoice filename
   - Format: `Invoice_[NUMBER]_[DATE].csv` (e.g., `Invoice_132212_2024-07-31.csv`)

2. **Invoice Date Calculation**:
   ```python
   def calculate_invoice_date(self, date_str: str) -> str:
       # Parse the original date
       original_date = pd.to_datetime(date_str)
       
       # Add 2 months to get the new month
       next_month_date = original_date + pd.DateOffset(months=2)
       
       # Get the last day of the month
       next_month = next_month_date.month + 1 if next_month_date.month < 12 else 1
       next_year = next_month_date.year + 1 if next_month_date.month == 12 else next_month_date.year
       
       invoice_date = pd.to_datetime(f"{next_year}-{next_month:02d}-01") - pd.Timedelta(days=1)
       
       return invoice_date.strftime('%Y-%m-%d')
   ```

3. **Due Date Calculation**:
   - Due date is set to 20 days after the invoice date
   - Implemented in both Streamlit UI and Xero API integration

4. **Implementation**:
   - In `streamlit_app.py`: Extracts date from filename and calculates invoice date
   - In `devoli_billing.py`: Helper method `calculate_invoice_date()` ensures consistent calculation
   - Fallback logic uses current date if no date is provided

## Customer Discounts

### SPARK Customer Discount (6%)
The application automatically applies a 6% discount to all SPARK customers' calling charges.

#### Implementation Details
1. **Detection**: 
   - Customers are identified by checking for "SPARK" in their Xero name (case-insensitive)
   - This check is performed in the data editor and invoice creation process

2. **Display**:
   ```python
   'Discount': lambda x: x.apply(lambda row: row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0, axis=1)
   'Net Amount': lambda x: x.apply(lambda row: row['Calling Charges'] - (row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0), axis=1)
   'Call Charges inc GST': lambda x: x.apply(lambda row: (row['Calling Charges'] - (row['Calling Charges'] * 0.06 if 'SPARK' in row['Xero Name'].upper() else 0)) * 1.15, axis=1)
   ```

3. **Xero Integration**:
   - Discount is added as a separate line item in Xero
   - Uses account code 45900 (SPARK Sales account)
   - Description: "Spark Discount Taken"
   - Amount is calculated as -6% of the total calling charges
   - GST (15%) is applied to the net amount after discount

4. **Line Item Structure**:
   ```python
   {
       "Description": "Spark Discount Taken",
       "Quantity": total_calling_charges,
       "UnitAmount": -0.06,  # Negative to represent discount
       "AccountCode": "45900",
       "TaxType": "OUTPUT2"  # 15% GST
   }
   ```

## The Service Company Special Handling

The application provides special handling for The Service Company with detailed line-item structure in Xero invoices:

### Detection and Processing Flow

1. **Identification**:
   ```python
   is_service_company = (
       customer_name.lower() == 'the service company' or
       customer_name.lower() == 'the service company limited' or
       getattr(customer_data, 'is_tsc', False)
   )
   ```

2. **Contact Name Handling**:
   - Always uses the full legal name "The Service Company Limited" for Xero contact
   - Ensures consistent contact recognition in Xero

3. **Invoice Line Items**:
   ```python
   # Base fee line item
   line_items.append({
       "Description": "Monthly Charges for Toll Free Numbers (0800 366080, 650252, 753753)",
       "Quantity": 1.0,
       "UnitAmount": service_results['base_fee'],  # $55.00
       "AccountCode": "43850",
       "TaxType": "OUTPUT2"
   })
   
   # Regular number line item (if calls exist)
   regular_desc = ['6492003366']
   for call in service_results['regular_number']['calls']:
       regular_desc.append(f"{call['type']} Calls ({call['count']} calls - {call['duration']})")
   
   line_items.append({
       "Description": '\n'.join(regular_desc),
       "Quantity": 1.0,
       "UnitAmount": service_results['regular_number']['total'],
       "AccountCode": "43850",
       "TaxType": "OUTPUT2"
   })
   
   # Individual TFree number line items
   for number, data in service_results['numbers'].items():
       if data['calls']:
           number_desc = [number]
           for call in data['calls']:
               number_desc.append(f"{call['type']} ({call['count']} calls - {call['duration']})")
           
           line_items.append({
               "Description": '\n'.join(number_desc),
               "Quantity": 1.0,
               "UnitAmount": data['total'],
               "AccountCode": "43850",
               "TaxType": "OUTPUT2"
           })
   ```

## Log Database Management

The application uses SQLite to track processed invoices and prevent duplicate processing:

### Database Schema

```sql
-- File processing table
CREATE TABLE file_processing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    processing_date TEXT,
    user_notes TEXT,
    file_date TEXT
);

-- Invoice creation table
CREATE TABLE invoice_creation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_processing_id INTEGER,
    xero_customer_name TEXT,
    devoli_customer_names TEXT,
    invoice_number TEXT,
    invoice_date TEXT,
    amount REAL,
    status TEXT,
    FOREIGN KEY (file_processing_id) REFERENCES file_processing(id)
);
```

### Key Functions

1. **Log File Processing**:
   ```python
   def log_file_processing(self, filename):
       # Creates a new file processing record
       # Returns the file ID for use in invoice records
   ```

2. **Mark Invoice as Processed**:
   ```python
   def mark_invoice_as_processed(self, xero_customer_name, filename):
       # Links invoice to file processing record
       # Sets status to 'processed'
   ```

3. **Check if Already Processed**:
   ```python
   def check_if_processed(self, filename, xero_customer_name):
       # Checks if exact file+customer combination exists
       # For non-TSC customers, also checks by month
       # Allows TSC to be processed in same month with different files
   ```

4. **Clear File Data**:
   ```python
   def clear_file_data(self, file_id):
       # Removes all processing records for a file
       # Allows reprocessing
   ```

## Debugging Utilities

### Debug Scripts

1. **debug_tsc_invoice.py**:
   - Direct Xero API interaction
   - Creates TSC invoice with multiple line items
   - Useful for isolating UI vs. API issues

2. **direct_invoice_fix.py**:
   - Processes invoice CSV directly
   - Bypasses Streamlit UI
   - Useful for testing core processing logic

### Logging

1. **Detailed Debug Logs**:
   - Includes detailed TSC processing steps
   - Shows line item generation
   - Reports Xero API response data
   - Helps identify issues in multi-step process

2. **Log File Visibility**:
   - UI shows log status for each file
   - Indicates which customers are already processed
   - Provides clear feedback about processing state

## Testing

### Unit Tests
- Test call calculations
- Test rate applications
- Test duration conversions

### Integration Tests
- Test Xero connectivity
- Test invoice creation
- Test data processing

## Error Handling

1. **Data Validation**
   - Customer name verification
   - Call data format checking
   - Rate validation

2. **Xero API**
   - Token refresh handling
   - Rate limiting
   - Error response processing

3. **TSC Fallback Logic**
   - Graceful degradation to single line item if needed
   - Error reporting with clear diagnostics
   - Prevents complete failure when partial data is available

## Configuration

### Required Files
```
.xero_creds
customer_mapping.csv
product_mapping.csv
```

### Environment Variables
```
XERO_CLIENT_ID
XERO_CLIENT_SECRET
XERO_TENANT_ID
DEBUG_TSC_INVOICES  # Optional - set to 'true' for additional debugging
```

## Performance Considerations

1. **Data Processing**
   - Batch processing for large files
   - Efficient DataFrame operations
   - Memory management for large datasets

2. **API Calls**
   - Rate limiting compliance
   - Batch invoice creation
   - Token caching

## Security

1. **Credentials**
   - Stored in separate files
   - Not committed to repository
   - Environment variable usage

2. **Data Protection**
   - Input validation
   - Secure API communication
   - Error message sanitization

## Maintenance

1. **Updating Rate Tables**
   - Update the RATES dictionary in `service_company.py`

2. **Customer Mapping**
   - Edit `customer_mapping.csv` to update/add customers

3. **Xero Token Refresh**
   - Automatic token refresh via `xero_token_manager.py`
   - Manual refresh with `python test_xero.py`

## Authentication Flow

### Configuration
- OAuth2 callback is configured to use `http://localhost:8080`
- The `StoppableHTTPServer` listens on port 8080 to capture the auth code
- Token refresh is attempted first, with fallback to re-authentication if refresh fails
- Tokens are stored in `xero_tokens.json`

### Token Management
- Tokens are automatically refreshed when expired (with 5-minute buffer)
- If refresh fails, the app will trigger a new authentication flow
- Token data includes:
  - access_token
  - refresh_token
  - expires_at
  - tenant_id 