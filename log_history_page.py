import streamlit as st
import pandas as pd
from datetime import datetime
import os
import traceback
from log_database import LogDatabase

def format_datetime(dt_str):
    """Format datetime string for display"""
    try:
        if not dt_str or pd.isna(dt_str):
            return ""
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except:
        return str(dt_str)

def log_history_page():
    """Streamlit page for viewing log history"""
    st.title("Billing Processing History")
    
    # Add refresh button
    if st.button("🔄 Refresh Data", key="refresh_logs"):
        st.experimental_rerun()
    
    # Initialize the database
    try:
        db = LogDatabase()
    except Exception as e:
        st.error(f"Error initializing database: {str(e)}")
        st.code(traceback.format_exc())
        
        # Provide recovery instructions
        st.warning("""
        If you're seeing database errors, you might need to reset the database:
        1. Stop the application
        2. Delete the `data/logs.db` file
        3. Restart the application
        """)
        return
        
    # Create tabs for Files and Invoices
    tab1, tab2 = st.tabs(["Processed Files", "Created Invoices"])
    
    with tab1:
        st.subheader("Files Processing History")
        
        try:
            # Get processed files
            files_df = db.get_processed_files()
            
            if files_df.empty:
                st.info("No files have been processed yet.")
            else:
                # Format dates for display
                files_df['processing_date'] = files_df['processing_date'].apply(format_datetime)
                
                # Display as a dataframe with filters
                st.dataframe(
                    files_df,
                    column_config={
                        "id": st.column_config.NumberColumn("ID"),
                        "filename": st.column_config.TextColumn("Filename"),
                        "processing_date": st.column_config.TextColumn("Processed On"),
                        "file_date": st.column_config.DateColumn("Invoice Date"),
                        "status": st.column_config.TextColumn("Status"),
                        "user_notes": st.column_config.TextColumn("Notes"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # Add debug info
                st.caption(f"Debug: Found {len(files_df)} processed files")
        except Exception as e:
            st.error(f"Error loading processed files: {str(e)}")
            st.code(traceback.format_exc())
    
    with tab2:
        st.subheader("Invoice Creation History")
        
        try:
            # Get created invoices
            invoices_df = db.get_created_invoices()
            
            if invoices_df.empty:
                st.info("No invoices have been created yet.")
                
                # Check if files exist but no invoices
                try:
                    files_df = db.get_processed_files()
                    if not files_df.empty:
                        st.warning("Files have been processed, but no invoices were recorded. This could indicate a logging issue.")
                except:
                    pass
            else:
                # Format dates for display
                invoices_df['invoice_date'] = invoices_df['invoice_date'].apply(format_datetime)
                
                # Calculate total amount processed
                total_amount = invoices_df['amount'].sum()
                
                # Display metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Invoices", len(invoices_df))
                col2.metric("Total Amount", f"${total_amount:.2f}")
                col3.metric("Average Invoice", f"${(total_amount / len(invoices_df)):.2f}" if len(invoices_df) > 0 else "$0.00")
                
                # Add filter by file
                unique_files = invoices_df['filename'].unique()
                selected_file = st.selectbox(
                    "Filter by file",
                    options=["All Files"] + list(unique_files),
                    index=0
                )
                
                if selected_file != "All Files":
                    filtered_df = invoices_df[invoices_df['filename'] == selected_file]
                else:
                    filtered_df = invoices_df
                    
                # Display as a dataframe
                st.dataframe(
                    filtered_df,
                    column_config={
                        "xero_customer_name": st.column_config.TextColumn("Xero Customer"),
                        "devoli_customer_names": st.column_config.TextColumn("Devoli Names"),
                        "invoice_number": st.column_config.TextColumn("Invoice #"),
                        "invoice_date": st.column_config.TextColumn("Created On"),
                        "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                        "status": st.column_config.TextColumn("Status"),
                        "filename": st.column_config.TextColumn("Source File"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # Add debug info
                st.caption(f"Debug: Found {len(invoices_df)} invoices")
        except Exception as e:
            st.error(f"Error loading created invoices: {str(e)}")
            st.code(traceback.format_exc())
            
    # Add section for adding notes to files
    st.subheader("Add Notes to File")
    
    try:
        files_df = db.get_processed_files()
        files = files_df['filename'].tolist() if not files_df.empty else []
        
        if not files:
            st.info("No files available to add notes.")
        else:
            selected_file = st.selectbox("Select file", files, index=0 if files else None)
            
            if selected_file:
                try:
                    file_id = files_df[files_df['filename'] == selected_file]['id'].iloc[0]
                    current_note = files_df[files_df['filename'] == selected_file]['user_notes'].iloc[0]
                    
                    new_note = st.text_area("Notes", value=str(current_note) if current_note else "")
                    
                    if st.button("Update Notes"):
                        try:
                            # Update note in database
                            cursor = db.conn.cursor()
                            cursor.execute('''
                            UPDATE file_processing SET user_notes = ? WHERE id = ?
                            ''', (new_note, file_id))
                            db.conn.commit()
                            st.success(f"Notes updated for {selected_file}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error updating notes: {str(e)}")
                except Exception as e:
                    st.error(f"Error retrieving file details: {str(e)}")
    except Exception as e:
        st.error(f"Error with file notes: {str(e)}")
        st.code(traceback.format_exc()) 