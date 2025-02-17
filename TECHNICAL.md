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

### Regular Tasks
1. Update rate configurations
2. Verify customer mappings
3. Check Xero API version compatibility
4. Update dependencies

### Monitoring
1. Check log files
2. Monitor invoice creation success rates
3. Track API response times

## Future Improvements

1. **Planned Features**
   - Batch processing improvements
   - Additional customer special cases
   - Enhanced error reporting

2. **Technical Debt**
   - Refactor rate calculations
   - Improve test coverage
   - Enhance logging 