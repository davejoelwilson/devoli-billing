import sqlite3
import os
from datetime import datetime
import pandas as pd
import traceback

class LogDatabase:
    def __init__(self, db_path=None):
        """Initialize the logging database"""
        # If no path provided, use data/logs.db as default
        if db_path is None:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            db_path = os.path.join('data', 'logs.db')
            
        self.db_path = db_path
        # Don't store a connection as an instance variable
        # Create it each time it's needed
        self.initialize_db()
    
    def get_connection(self):
        """Get a new database connection (thread-safe)"""
        return sqlite3.connect(self.db_path)
    
    def initialize_db(self):
        """Create database and tables if they don't exist"""
        # os.path.dirname() returns empty string for relative paths without directories
        # Don't try to create directories in this case
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        
        # Create a new connection for initialization
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Create file_processing table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_processing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                processing_date TIMESTAMP NOT NULL,
                user_notes TEXT,
                file_date TEXT,
                status TEXT DEFAULT 'processed'
            )
            ''')
            
            # Create invoice_creation table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS invoice_creation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_processing_id INTEGER,
                xero_customer_name TEXT NOT NULL,
                devoli_customer_names TEXT NOT NULL,
                invoice_number TEXT,
                invoice_date TIMESTAMP NOT NULL,
                amount REAL NOT NULL,
                status TEXT DEFAULT 'created',
                FOREIGN KEY (file_processing_id) REFERENCES file_processing(id)
            )
            ''')
            
            conn.commit()
        finally:
            conn.close()
    
    def log_file_processing(self, filename, user_notes='', file_date=None):
        """Log when a file is processed"""
        # Extract date from filename (e.g., Invoice_134426_2024-12-31.csv)
        if not file_date and '_' in filename and filename.endswith('.csv'):
            try:
                file_date = filename.split('_')[2].split('.')[0]
            except IndexError:
                file_date = None
        
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO file_processing (filename, processing_date, user_notes, file_date)
            VALUES (?, ?, ?, ?)
            ''', (filename, datetime.now().isoformat(), user_notes, file_date))
            conn.commit()
            
            # Return the ID of the new record
            return cursor.lastrowid
        finally:
            conn.close()
    
    def log_invoice_creation(self, file_processing_id, xero_customer_name, 
                            devoli_customer_names, invoice_number, amount):
        """Log when an invoice is created in Xero"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO invoice_creation 
            (file_processing_id, xero_customer_name, devoli_customer_names, 
             invoice_number, invoice_date, amount)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                file_processing_id, 
                xero_customer_name, 
                devoli_customer_names, 
                invoice_number, 
                datetime.now().isoformat(), 
                amount
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def get_processed_files(self):
        """Get list of all processed files"""
        conn = self.get_connection()
        try:
            return pd.read_sql_query('''
            SELECT id, filename, processing_date, user_notes, file_date, status
            FROM file_processing
            ORDER BY processing_date DESC
            ''', conn)
        finally:
            conn.close()
    
    def get_created_invoices(self, file_processing_id=None):
        """Get list of all created invoices, optionally filtered by file_processing_id"""
        conn = self.get_connection()
        try:
            query = '''
            SELECT ic.id, ic.xero_customer_name, ic.devoli_customer_names, 
                   ic.invoice_number, ic.invoice_date, ic.amount, ic.status,
                   fp.filename
            FROM invoice_creation ic
            JOIN file_processing fp ON ic.file_processing_id = fp.id
            '''
            
            if file_processing_id:
                query += f' WHERE ic.file_processing_id = {file_processing_id}'
            
            query += ' ORDER BY ic.invoice_date DESC'
            
            return pd.read_sql_query(query, conn)
        finally:
            conn.close()
    
    def mark_invoice_as_processed(self, xero_customer_name, filename):
        """Mark a specific customer's invoice as processed for a file"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Find the file processing record
            cursor.execute('''
            SELECT id FROM file_processing WHERE filename = ?
            ''', (filename,))
            file_record = cursor.fetchone()
            
            if not file_record:
                # Create a file processing record if it doesn't exist
                cursor.execute('''
                INSERT INTO file_processing (filename, processing_date, user_notes, file_date)
                VALUES (?, ?, ?, ?)
                ''', (filename, datetime.now().isoformat(), "Auto-created during invoice processing", None))
                conn.commit()
                
                # Get the new file ID
                cursor.execute('''
                SELECT id FROM file_processing WHERE filename = ?
                ''', (filename,))
                file_record = cursor.fetchone()
                
                if not file_record:
                    return False
            
            file_processing_id = file_record[0]
            
            # Check if there's already an invoice record
            cursor.execute('''
            SELECT id FROM invoice_creation 
            WHERE file_processing_id = ? AND xero_customer_name = ?
            ''', (file_processing_id, xero_customer_name))
            
            invoice_record = cursor.fetchone()
            
            if invoice_record:
                # Update existing record
                cursor.execute('''
                UPDATE invoice_creation 
                SET status = 'processed'
                WHERE id = ?
                ''', (invoice_record[0],))
            else:
                # Create a new record if none exists
                cursor.execute('''
                INSERT INTO invoice_creation 
                (file_processing_id, xero_customer_name, devoli_customer_names, 
                invoice_number, invoice_date, amount, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file_processing_id, 
                    xero_customer_name, 
                    xero_customer_name, # Use customer name as devoli name if we don't have it
                    'Unknown', # Don't know the invoice number 
                    datetime.now().isoformat(), 
                    0.0, # Don't know the amount
                    'processed'
                ))
                
            conn.commit()
            return True
        finally:
            conn.close()
    
    def check_if_processed(self, filename, xero_customer_name):
        """Check if a specific invoice has been processed already"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            try:
                # First, try direct query using both parameters
                cursor.execute('''
                SELECT ic.status FROM invoice_creation ic
                JOIN file_processing fp ON ic.file_processing_id = fp.id
                WHERE fp.filename = ? AND ic.xero_customer_name = ?
                ''', (filename, xero_customer_name))
                
                invoice_record = cursor.fetchone()
                if invoice_record:
                    # If status is 'processed', it's been processed already
                    return invoice_record[0] == 'processed'
                
                # If not found, check if we have the file at least
                cursor.execute('''
                SELECT id FROM file_processing WHERE filename = ?
                ''', (filename,))
                
                file_record = cursor.fetchone()
                if not file_record:
                    # No file record, definitely not processed
                    return False
                    
                # Finally, check if we have any invoice for this customer (regardless of file)
                cursor.execute('''
                SELECT status FROM invoice_creation 
                WHERE xero_customer_name = ?
                ''', (xero_customer_name,))
                
                invoice_record = cursor.fetchone()
                if not invoice_record:
                    return False
                
                # This is a fallback - if we found any record at all for this customer
                # Return true only if it's specifically marked as processed
                return invoice_record[0] == 'processed'
            
            except Exception as e:
                print(f"Database error in check_if_processed: {str(e)}")
                traceback.print_exc()
                # If there's any error, assume not processed
                return False
        finally:
            conn.close()
    
    def update_file_note(self, file_id, note_text):
        """Update the user notes for a file"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE file_processing SET user_notes = ? WHERE id = ?
            ''', (note_text, file_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating file note: {str(e)}")
            return False
        finally:
            conn.close()

    def clear_all_data(self):
        """Clear all data from the database"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Delete in correct order due to foreign key constraints
            cursor.execute('DELETE FROM invoice_creation')
            cursor.execute('DELETE FROM file_processing')
            conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing database: {str(e)}")
            return False
        finally:
            conn.close()

    def clear_file_data(self, file_id):
        """Clear all data related to a specific file"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            # Delete invoices first due to foreign key constraint
            cursor.execute('DELETE FROM invoice_creation WHERE file_processing_id = ?', (file_id,))
            cursor.execute('DELETE FROM file_processing WHERE id = ?', (file_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing file data: {str(e)}")
            return False
        finally:
            conn.close()

    def clear_invoice_data(self, invoice_id):
        """Clear a specific invoice record"""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM invoice_creation WHERE id = ?', (invoice_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error clearing invoice data: {str(e)}")
            return False
        finally:
            conn.close() 