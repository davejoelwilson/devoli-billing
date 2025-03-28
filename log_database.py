import sqlite3
import os
from datetime import datetime
import pandas as pd

class LogDatabase:
    def __init__(self, db_path=None):
        """Initialize the logging database"""
        # If no path provided, use data/logs.db as default
        if db_path is None:
            # Create data directory if it doesn't exist
            os.makedirs('data', exist_ok=True)
            db_path = os.path.join('data', 'logs.db')
            
        self.db_path = db_path
        self.conn = None
        self.initialize_db()
    
    def initialize_db(self):
        """Create database and tables if they don't exist"""
        # os.path.dirname() returns empty string for relative paths without directories
        # Don't try to create directories in this case
        dirname = os.path.dirname(self.db_path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        
        # Connect to database
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
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
        
        self.conn.commit()
    
    def log_file_processing(self, filename, user_notes='', file_date=None):
        """Log when a file is processed"""
        # Extract date from filename (e.g., Invoice_134426_2024-12-31.csv)
        if not file_date and '_' in filename and filename.endswith('.csv'):
            try:
                file_date = filename.split('_')[2].split('.')[0]
            except IndexError:
                file_date = None
        
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO file_processing (filename, processing_date, user_notes, file_date)
        VALUES (?, ?, ?, ?)
        ''', (filename, datetime.now().isoformat(), user_notes, file_date))
        self.conn.commit()
        
        # Return the ID of the new record
        return cursor.lastrowid
    
    def log_invoice_creation(self, file_processing_id, xero_customer_name, 
                            devoli_customer_names, invoice_number, amount):
        """Log when an invoice is created in Xero"""
        cursor = self.conn.cursor()
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
        self.conn.commit()
        return cursor.lastrowid
    
    def get_processed_files(self):
        """Get list of all processed files"""
        return pd.read_sql_query('''
        SELECT id, filename, processing_date, user_notes, file_date, status
        FROM file_processing
        ORDER BY processing_date DESC
        ''', self.conn)
    
    def get_created_invoices(self, file_processing_id=None):
        """Get list of all created invoices, optionally filtered by file_processing_id"""
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
        
        return pd.read_sql_query(query, self.conn)
    
    def mark_invoice_as_processed(self, xero_customer_name, filename):
        """Mark a specific customer's invoice as processed for a file"""
        # Find the file processing record
        cursor = self.conn.cursor()
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
            # Nothing to update
            return False
            
        self.conn.commit()
        return True
    
    def check_if_processed(self, filename, xero_customer_name):
        """Check if a specific invoice has been processed already"""
        cursor = self.conn.cursor()
        
        # Get file processing ID
        cursor.execute('''
        SELECT id FROM file_processing WHERE filename = ?
        ''', (filename,))
        
        file_record = cursor.fetchone()
        if not file_record:
            return False
            
        file_id = file_record[0]
        
        # Check invoice creation status
        cursor.execute('''
        SELECT status FROM invoice_creation 
        WHERE file_processing_id = ? AND xero_customer_name = ?
        ''', (file_id, xero_customer_name))
        
        invoice_record = cursor.fetchone()
        if not invoice_record:
            return False
            
        # If status is 'processed', it's been processed already
        return invoice_record[0] == 'processed'
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close() 