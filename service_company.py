import pandas as pd
import re
from datetime import datetime
import os
import glob

class ServiceCompanyBilling:
    def __init__(self):
        # Base fee is always $55
        self.base_fee = 55.00
        
        # Define rates
        self.rates = {
            # Standard rates
            'Local': 0.05,
            'Mobile': 0.12,
            'National': 0.05,
            'Australia': 0.14,
            
            # Service Company rates
            'TFree Inbound - Mobile': 0.28,
            'TFree Inbound - National': 0.10,
            'TFree Inbound - Australia': 0.14,
            'TFree Inbound - Other': 0.14
        }

    def convert_to_minutes(self, duration):
        """Convert HH:MM:SS to minutes, rounding up partial minutes"""
        parts = duration.split(':')
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        
        total_seconds = (hours * 3600) + (minutes * 60) + seconds
        return (total_seconds + 59) // 60  # Round up to nearest minute

    def process_billing(self, input_data):
        """Process billing for The Service Company"""
        # Handle both DataFrame and file path inputs
        if isinstance(input_data, str):
            df = pd.read_csv(input_data)
        else:
            df = input_data.copy()
        
        # Filter for The Service Company
        df = df[df['Customer Name'].str.strip() == 'The Service Company']
        
        # Initialize results
        results = {
            'base_fee': self.base_fee,  # Keep this for total calculation
            'regular_number': {'calls': [], 'total': 0},
            'numbers': {},
            'total': 0  # Initialize to 0, will add base_fee to total later
        }
        
        # Identify all TFree numbers
        mask = df['Short Description'].str.startswith('64800', na=False)
        tfree_numbers = df[mask]['Short Description'].unique()
        
        # Initialize numbers dict
        for number in tfree_numbers:
            results['numbers'][number] = {'calls': [], 'total': 0}
        
        # Process each row
        for _, row in df.iterrows():
            desc = row['Description']
            
            # Skip non-call rows
            if 'Calls' not in desc:
                continue
                
            # Extract call details using regex
            call_match = re.search(r'(\d+) calls? - ([\d:]+)', desc)
            if not call_match:
                continue
                
            num_calls = int(call_match.group(1))
            duration = call_match.group(2)
            minutes = self.convert_to_minutes(duration)
            number = row['Short Description']
            
            # Process TFree calls
            if 'TFree Inbound' in desc:
                if number not in results['numbers']:
                    continue
                    
                # Determine call type
                if 'Mobile' in desc:
                    call_type = 'TFree Inbound - Mobile'
                elif 'National' in desc:
                    call_type = 'TFree Inbound - National'
                elif 'Australia' in desc:
                    call_type = 'TFree Inbound - Australia'
                elif 'Other' in desc:
                    call_type = 'TFree Inbound - Other'
                else:
                    continue
                
                rate = self.rates.get(call_type)
                if not rate:
                    continue
                    
                charge = round(minutes * rate, 2)
                
                # Store call details
                results['numbers'][number]['calls'].append({
                    'type': call_type,
                    'count': num_calls,
                    'duration': duration,
                    'minutes': minutes,
                    'rate': rate,
                    'charge': charge
                })
                results['numbers'][number]['total'] += charge
            
            # Process regular number calls
            else:
                # Determine call type and rate
                if 'Local' in desc:
                    call_type = 'Local'
                elif 'Mobile' in desc:
                    call_type = 'Mobile'
                elif 'National' in desc:
                    call_type = 'National'
                else:
                    continue
                
                rate = self.rates[call_type]
                charge = round(minutes * rate, 2)
                
                # Store call details
                results['regular_number']['calls'].append({
                    'type': call_type,
                    'count': num_calls,
                    'duration': duration,
                    'minutes': minutes,
                    'rate': rate,
                    'charge': charge
                })
                results['regular_number']['total'] += charge
        
        # Calculate final total - include base_fee in total but not as separate charge
        calling_total = results['regular_number']['total'] + sum(data['total'] for data in results['numbers'].values())
        results['total'] = calling_total + results['base_fee']  # Add base_fee at the end
        
        return results

    def print_results(self, results):
        """Print detailed billing results"""
        print("\nThe Service Company Billing Summary")
        print("=" * 50)
        
        # Print regular number details
        print("\nRegular Number (6492003366):")
        print("-" * 40)
        for call in results['regular_number']['calls']:
            print(f"{call['type']}: {call['count']} calls - {call['duration']}")
            print(f"  {call['minutes']} mins × ${call['rate']} = ${call['charge']:.2f}")
        print(f"Subtotal: ${results['regular_number']['total']:.2f}")
        
        # Print TFree numbers details
        for number, data in results['numbers'].items():
            print(f"\nTFree Number ({number}):")
            print("-" * 40)
            for call in data['calls']:
                print(f"{call['type']}: {call['count']} calls - {call['duration']}")
                print(f"  {call['minutes']} mins × ${call['rate']} = ${call['charge']:.2f}")
            print(f"Subtotal: ${data['total']:.2f}")
        
        # Print summary
        print("\nSummary:")
        print("-" * 40)
        print(f"Base Fee: ${self.base_fee:.2f}")
        print(f"Regular Number: ${results['regular_number']['total']:.2f}")
        tfree_total = sum(data['total'] for data in results['numbers'].values())
        print(f"TFree Numbers: ${tfree_total:.2f}")
        print("-" * 40)
        print(f"Total: ${results['total']:.2f}")

    def parse_call_data(self, df):
        """Parse call data for non-service-company customers"""
        call_data = {
            'australia': {'count': 0, 'duration': '00:00:00'},
            'local': {'count': 0, 'duration': '00:00:00'},
            'mobile': {'count': 0, 'duration': '00:00:00'},
            'national': {'count': 0, 'duration': '00:00:00'}
        }
        
        for _, row in df.iterrows():
            desc = row['Description']
            count, duration = self.extract_call_details(desc)
            call_type = self.classify_call_type(desc)
            
            if call_type in call_data:
                call_data[call_type]['count'] += count
                call_data[call_type]['duration'] = self.sum_durations(
                    call_data[call_type]['duration'], 
                    duration
                )
        
        return call_data

    def calculate_standard_charges(self, call_data):
        """Calculate charges for non-service-company customers"""
        total = 0
        for call_type, data in call_data.items():
            minutes = self.convert_to_minutes(data['duration'])
            rate = self.rates.get(call_type.capitalize(), 0)
            total += minutes * rate
        return total

    def extract_call_details(self, desc):
        """Extract call details from description"""
        try:
            pattern = r'(\d+) calls? - ((?:\d+ days? )?[\d:]+)'
            match = re.search(pattern, desc)
            if not match:
                return 0, "00:00:00"
            
            count = int(match.group(1))
            duration = match.group(2)
            
            # Handle "X days HH:MM:SS" format
            if 'days' in duration or 'day' in duration:
                parts = duration.split()
                days = int(parts[0])
                time_str = parts[2]  # Get HH:MM:SS part
                h, m, s = map(int, time_str.split(':'))
                total_seconds = (days * 24 * 3600) + (h * 3600) + (m * 60) + s
                h = total_seconds // 3600
                m = (total_seconds % 3600) // 60
                s = total_seconds % 60
                duration = f"{h:02d}:{m:02d}:{s:02d}"
            
            # Ensure duration is in HH:MM:SS format
            if ':' not in duration:
                return 0, "00:00:00"
            
            parts = duration.split(':')
            if len(parts) == 2:
                duration = f"00:{duration}"
            
            return count, duration
        except:
            return 0, "00:00:00"

    def classify_call_type(self, desc):
        """Determine call type from description"""
        desc_lower = desc.lower()
        if 'australia' in desc_lower:
            return 'australia'
        elif 'local' in desc_lower:
            return 'local'
        elif 'mobile' in desc_lower:
            return 'mobile'
        elif 'national' in desc_lower:
            return 'national'
        return None

    def sum_durations(self, dur1, dur2):
        """Add two durations in HH:MM:SS format"""
        def to_seconds(dur):
            try:
                # Handle empty or invalid durations
                if not dur or dur == '0' or ':' not in dur:
                    return 0
                
                parts = dur.split(':')
                if len(parts) == 3:
                    h, m, s = map(int, parts)
                elif len(parts) == 2:
                    h, m = map(int, parts)
                    s = 0
                else:
                    return 0
                
                return h * 3600 + m * 60 + s
            except:
                return 0
        
        total_secs = to_seconds(dur1) + to_seconds(dur2)
        h = total_secs // 3600
        m = (total_secs % 3600) // 60
        s = total_secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def format_call_description(self, call_data):
        """Format call data into a description string"""
        desc = ["Calling charges:"]  # Add header
        for call_type, data in call_data.items():
            if data['count'] > 0:
                # Format: "Type Calls (X calls - HH:MM:SS)"
                desc.append(f"{call_type.title()} Calls ({data['count']} calls - {data['duration']})")
        return "\n".join(desc)

    def load_voip_customers(self, df):
        """Load VoIP customers from DataFrame"""
        # Filter for VoIP services
        voip_df = df[
            df['Description'].str.contains('DDI', na=False) |
            df['Description'].str.contains('Calls', na=False)
        ]
        
        # Get unique customer names
        voip_customers = sorted(voip_df['Customer Name'].unique())
        
        return voip_customers, voip_df

def main():
    processor = ServiceCompanyBilling()
    
    # Find most recent invoice file in bills directory
    bills_dir = "bills"
    invoice_files = glob.glob(os.path.join(bills_dir, "Invoice_*.csv"))
    
    if not invoice_files:
        print(f"No invoice files found in {bills_dir} directory")
        return
        
    # Sort by date in filename (assuming format Invoice_NNNNNN_YYYY-MM-DD.csv)
    latest_invoice = sorted(invoice_files, key=lambda x: x.split('_')[2].split('.')[0], reverse=True)[0]
    print(f"Processing: {latest_invoice}")
    
    # Process the invoice
    results = processor.process_billing(latest_invoice)
    processor.print_results(results)

if __name__ == "__main__":
    main() 