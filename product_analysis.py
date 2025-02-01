import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import os
import traceback
from datetime import datetime
import numpy as np

def process_all_invoices():
    """Process all invoice files and return monthly metrics.
    
    Reads all invoice CSV files from the bills directory and processes them to generate:
    1. Monthly metrics (unique customers, total quantity, total revenue)
    2. Category metrics (revenue and quantity by product category)
    
    Returns:
        tuple: (monthly_metrics_df, category_metrics_df)
            - monthly_metrics_df: DataFrame with columns [date, unique_customers, total_quantity, total_revenue]
            - category_metrics_df: DataFrame with columns [date, category, revenue, quantity]
    """
    monthly_metrics = []
    category_metrics = []
    
    for f in os.listdir("bills"):
        if f.startswith("Invoice_") and f.endswith(".csv"):
            try:
                # Extract date from filename
                date_str = f.split('_')[2].split('.')[0]
                invoice_date = pd.to_datetime(date_str)
                
                # Read and process invoice
                df = pd.read_csv(os.path.join("bills", f))
                df.columns = df.columns.str.lower().str.strip()
                
                # Clean descriptions
                descriptions = [clean_product_description(str(desc)) for desc in df['description'].fillna('')]
                df['clean description'] = descriptions
                df = df[df['clean description'].notna() & (df['clean description'] != '')]
                
                # Add categories
                df['category'] = df['clean description'].apply(lambda x: 
                    'UFB Services' if 'UFB' in x 
                    else 'Call Services' if 'Calls' in x 
                    else 'DDI Services' if 'DDI' in x 
                    else 'Data Services' if 'Data' in x 
                    else 'Other Services'
                )
                
                # Calculate overall metrics
                metrics = {
                    'date': invoice_date,
                    'unique_customers': df['customer name'].nunique(),
                    'total_quantity': len(df),
                    'total_revenue': df['amount'].sum()
                }
                monthly_metrics.append(metrics)
                
                # Calculate category metrics
                for category in df['category'].unique():
                    cat_data = df[df['category'] == category]
                    category_metrics.append({
                        'date': invoice_date,
                        'category': category,
                        'revenue': cat_data['amount'].sum(),
                        'quantity': len(cat_data)
                    })
                
            except Exception as e:
                print(f"Error processing {f}: {str(e)}")
    
    return pd.DataFrame(monthly_metrics), pd.DataFrame(category_metrics)

def clean_product_description(desc: str) -> str:
    """Clean and standardize product descriptions.
    
    Processes raw product descriptions to extract standardized product types:
    - Handles various call types (Mobile, Local, Australia, International)
    - Processes UFB products with different speeds
    - Standardizes DDI and Data product names
    - Removes dates and extra information
    
    Args:
        desc (str): Raw product description from invoice
        
    Returns:
        str or None: Standardized product description, or None if description should be filtered out
    """
    if not isinstance(desc, str):
        return None
    
    desc = desc.strip()
    
    # Handle call types first
    if 'Calls' in desc:
        if 'Mobile Calls' in desc:
            return 'Mobile Calls'
        elif 'Local Calls' in desc:
            return 'Local Calls'
        elif 'Australia Calls' in desc:
            return 'Australia Calls'
        elif 'International Calls' in desc:
            return 'International Calls'
        return 'Other Calls'
    
    # Extract the product type before any ID or date
    parts = desc.split('-', 1)
    if len(parts) < 2:
        # Handle DDI blocks
        if 'DDI Block' in desc:
            if 'Australia' in desc:
                return 'Australia DDI Block'
            return 'DDI Block'
        return None
        
    product_type = parts[0].strip()
    details = parts[1].strip()
    
    # Basic product name cleaning
    if product_type == 'UFB':
        if 'Small Business Fibre 920' in details:
            desc = 'UFB - Small Business Fibre 920'
        elif 'Small Business Fibre 500' in details:
            desc = 'UFB - Small Business Fibre 500'
        elif 'Home Fibre 920' in details:
            desc = 'UFB - Home Fibre 920'
        elif 'Evolve 200/20/S' in details:
            desc = 'UFB - Evolve 200/20/S'
        else:
            desc = 'UFB - Other'
    elif product_type == 'Wholesale International DDI':
        desc = 'DDI'
    elif product_type == 'Unlimited Data':
        if 'CG Nat' in details:
            desc = 'Unlimited Data - CG NAT'
        elif 'Static IP' in details:
            desc = 'Unlimited Data - Static IP'
        elif 'Public' in details:
            desc = 'Unlimited Data - Public'
        else:
            desc = 'Unlimited Data - Other'
            
    return desc.strip() if desc else None

def product_analysis_page():
    """Main product analysis page with multiple analysis views.
    
    Features:
    1. Summary Tab:
       - Product summary with quantity and revenue
       - Top products visualization
    
    2. Customer Analysis Tab:
       - Products by customer matrix
       - Top customer charts
    
    3. Revenue Analysis Tab:
       - Category breakdowns
       - Revenue metrics
    
    4. Trends Tab:
       - Time series analysis
       - Category trends
       - Growth metrics
    """
    st.title("Product Analysis")
    
    # Find all invoices
    invoice_files = [f for f in os.listdir("bills") if f.startswith("Invoice_") and f.endswith(".csv")]
    if not invoice_files:
        st.error("No invoice found in bills directory")
        return
        
    # Create dropdown for invoice selection with proper sorting
    invoice_options = {}
    file_dates = []
    for f in invoice_files:
        date_str = f.split('_')[2].split('.')[0]
        file_date = pd.to_datetime(date_str)
        display_name = f"{file_date.strftime('%B %Y')} ({f.split('_')[0]}_{f.split('_')[1]})"
        invoice_options[display_name] = f
        file_dates.append((display_name, file_date))
    
    # Sort by date in descending order (newest first)
    sorted_options = [x[0] for x in sorted(file_dates, key=lambda x: x[1], reverse=True)]

    selected_invoice = st.selectbox(
        "Select Invoice to Analyze",
        options=sorted_options,
        index=0  # Default to first (latest) invoice
    )

    if selected_invoice:
        invoice_file = os.path.join("bills", invoice_options[selected_invoice])
        
        try:
            # Read CSV
            df = pd.read_csv(invoice_file)
            
            # Convert columns to lowercase
            df.columns = df.columns.str.lower().str.strip()
            
            # Clean descriptions using list comprehension instead of apply
            descriptions = [clean_product_description(str(desc)) for desc in df['description'].fillna('')]
            df['clean description'] = descriptions
            
            # Remove None values and empty strings
            df = df[df['clean description'].notna() & (df['clean description'] != '')]
            
            # Create tabs for different views
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["Summary", "Customer Analysis", "Revenue Analysis", "Trends", "Changes"])
            
            with tab1:
                # Product Summary
                st.subheader("Product Summary")
                product_counts = df.groupby('clean description').agg({
                    'customer name': 'nunique',  # Count unique customers
                    'amount': ['count', 'sum']
                }).reset_index()
                
                # Flatten and rename columns
                product_counts.columns = ['Product Type', 'Unique Customers', 'Quantity', 'Total Revenue']
                
                # Filter significant products
                significant_products = product_counts[
                    (product_counts['Quantity'] > 1) |  # More than one instance
                    (product_counts['Total Revenue'] > 40)  # Or significant revenue
                ]
                
                st.dataframe(
                    significant_products.sort_values(['Quantity', 'Total Revenue'], ascending=[False, False]),
                    column_config={
                        'Product Type': st.column_config.TextColumn('Product Type'),
                        'Unique Customers': st.column_config.NumberColumn('Unique Customers'),
                        'Quantity': st.column_config.NumberColumn('Quantity'),
                        'Total Revenue': st.column_config.NumberColumn(
                            'Total Revenue',
                            format="$%.2f"
                        )
                    },
                    hide_index=True
                )
                
                # Top 5 Products by Revenue
                st.subheader("Top 5 Products by Revenue")
                fig_revenue = st.bar_chart(
                    significant_products.nlargest(5, 'Total Revenue').set_index('Product Type')['Total Revenue']
                )
            
            with tab2:
                # Customer Analysis
                st.subheader("Products by Customer")
                significant_products_list = significant_products['Product Type'].tolist()
                df_filtered = df[df['clean description'].isin(significant_products_list)]
                
                # Add category for revenue analysis
                df_filtered['category'] = df_filtered['clean description'].apply(lambda x: 
                    'UFB Services' if 'UFB' in x 
                    else 'Call Services' if 'Calls' in x 
                    else 'DDI Services' if 'DDI' in x 
                    else 'Data Services' if 'Data' in x 
                    else 'Other Services'
                )
                
                # Create revenue by customer and category
                customer_revenue = df_filtered.pivot_table(
                    values='amount',
                    index='customer name',
                    columns='category',
                    aggfunc='sum',
                    fill_value=0
                ).reset_index()
                
                # Sort by total revenue
                customer_revenue['total_revenue'] = customer_revenue.iloc[:, 1:].sum(axis=1)
                customer_revenue = customer_revenue.sort_values('total_revenue', ascending=False)
                
                # Create stacked bar chart for top 15 customers
                st.subheader("Top 15 Customers by Revenue (with Category Breakdown)")
                top_customers = customer_revenue.head(15)
                
                fig_customer_revenue = go.Figure()
                categories = [col for col in top_customers.columns if col not in ['customer name', 'total_revenue']]
                
                for category in categories:
                    fig_customer_revenue.add_trace(
                        go.Bar(
                            name=category,
                            x=top_customers['customer name'],
                            y=top_customers[category],
                            text=top_customers[category].apply(lambda x: f'${x:,.2f}' if x > 0 else ''),
                            textposition='auto',
                        )
                    )
                
                fig_customer_revenue.update_layout(
                    barmode='stack',
                    title='Revenue by Customer and Category',
                    xaxis_title='Customer',
                    yaxis_title='Revenue ($)',
                    showlegend=True,
                    legend=dict(
                        yanchor="top",
                        y=0.99,
                        xanchor="left",
                        x=0.01
                    ),
                    hovermode='x unified'
                )
                
                # Rotate x-axis labels for better readability
                fig_customer_revenue.update_xaxes(tickangle=45)
                
                st.plotly_chart(fig_customer_revenue, use_container_width=True)
                
                # Show detailed revenue table
                st.subheader("Customer Revenue Breakdown")
                st.dataframe(
                    customer_revenue,
                    column_config={
                        'customer name': st.column_config.TextColumn('Customer'),
                        'UFB Services': st.column_config.NumberColumn('UFB Services', format="$%.2f"),
                        'Call Services': st.column_config.NumberColumn('Call Services', format="$%.2f"),
                        'DDI Services': st.column_config.NumberColumn('DDI Services', format="$%.2f"),
                        'Data Services': st.column_config.NumberColumn('Data Services', format="$%.2f"),
                        'Other Services': st.column_config.NumberColumn('Other Services', format="$%.2f"),
                        'total_revenue': st.column_config.NumberColumn('Total Revenue', format="$%.2f")
                    },
                    hide_index=True
                )
                
                # Original Products by Customer matrix
                st.subheader("Products by Customer (Quantity)")
                pivot_df = pd.pivot_table(
                    df_filtered,
                    values='amount',
                    index='customer name',
                    columns='clean description',
                    aggfunc='count',
                    fill_value=0
                ).reset_index()
                
                # Process pivot table as before
                pivot_df = pivot_df.rename(columns={'customer name': 'Customer'})
                product_columns = [col for col in pivot_df.columns if col != 'Customer']
                pivot_df['total_products'] = pivot_df[product_columns].sum(axis=1)
                pivot_df = pivot_df[pivot_df['total_products'] > 0].drop('total_products', axis=1)
                pivot_df['total_count'] = pivot_df[product_columns].sum(axis=1)
                pivot_df = pivot_df.sort_values(['total_count', 'Customer'], ascending=[False, True])
                pivot_df = pivot_df.drop('total_count', axis=1)
                
                st.dataframe(
                    pivot_df,
                    column_config={
                        'Customer': st.column_config.TextColumn('Customer Name')
                    },
                    hide_index=True
                )
                
                # Top Customers by Product Count
                st.subheader("Top 10 Customers by Number of Products")
                customer_totals = pivot_df.iloc[:, 1:].sum(axis=1)
                customer_totals = pd.DataFrame({
                    'Customer': pivot_df['Customer'],
                    'Total Products': customer_totals
                })
                st.bar_chart(customer_totals.nlargest(10, 'Total Products').set_index('Customer'))
            
            with tab3:
                # Revenue Analysis
                st.subheader("Revenue Insights")
                
                # Revenue by Product Category
                product_categories = []
                for product in df['clean description']:
                    if 'UFB' in product:
                        category = 'UFB Services'
                    elif 'Calls' in product:
                        category = 'Call Services'
                    elif 'DDI' in product:
                        category = 'DDI Services'
                    elif 'Data' in product:
                        category = 'Data Services'
                    else:
                        category = 'Other Services'
                    product_categories.append(category)
                
                df['category'] = product_categories
                category_revenue = df.groupby('category')['amount'].sum().reset_index()
                
                # Show category breakdown
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Revenue by Category")
                    st.dataframe(
                        category_revenue.sort_values('amount', ascending=False),
                        column_config={
                            'category': 'Category',
                            'amount': st.column_config.NumberColumn(
                                'Revenue',
                                format="$%.2f"
                            )
                        },
                        hide_index=True
                    )
                
                with col2:
                    st.subheader("Category Distribution")
                    st.bar_chart(category_revenue.set_index('category'))
                
                # Monthly metrics
                st.subheader("Key Metrics")
                total_revenue = df['amount'].sum()
                avg_revenue_per_customer = total_revenue / df['customer name'].nunique()
                avg_revenue_per_product = total_revenue / len(significant_products)
                
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                with metric_col1:
                    st.metric("Total Monthly Revenue", f"${total_revenue:,.2f}")
                with metric_col2:
                    st.metric("Avg Revenue per Customer", f"${avg_revenue_per_customer:,.2f}")
                with metric_col3:
                    st.metric("Avg Revenue per Product", f"${avg_revenue_per_product:,.2f}")
                
            with tab4:
                st.subheader("Monthly Trends")
                
                # Get metrics for all months
                monthly_df, category_df = process_all_invoices()
                monthly_df = monthly_df.sort_values('date')
                
                # Get the latest month's data for detailed breakdown
                latest_month = monthly_df['date'].max()
                latest_file = None
                for f in os.listdir("bills"):
                    if f.startswith("Invoice_") and f.endswith(".csv"):
                        date_str = f.split('_')[2].split('.')[0]
                        if pd.to_datetime(date_str).strftime('%Y-%m') == latest_month.strftime('%Y-%m'):
                            latest_file = f
                            break
                
                if latest_file:
                    latest_df = pd.read_csv(os.path.join("bills", latest_file))
                    latest_df.columns = latest_df.columns.str.lower().str.strip()
                    latest_df['clean description'] = [clean_product_description(str(desc)) for desc in latest_df['description'].fillna('')]
                    latest_df = latest_df[latest_df['clean description'].notna() & (latest_df['clean description'] != '')]
                    
                    # Calculate category metrics
                    latest_df['category'] = latest_df['clean description'].apply(lambda x: 
                        'UFB Services' if 'UFB' in x 
                        else 'Call Services' if 'Calls' in x 
                        else 'DDI Services' if 'DDI' in x 
                        else 'Data Services' if 'Data' in x 
                        else 'Other Services'
                    )
                    
                    category_metrics = latest_df.groupby('category').agg({
                        'amount': 'sum',
                        'clean description': 'count'
                    }).reset_index()
                    
                    # Display current month metrics
                    st.subheader(f"Current Month Overview ({latest_month.strftime('%B %Y')})")
                    
                    # Overall metrics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Customers", f"{latest_df['customer name'].nunique():,}")
                    with col2:
                        st.metric("Total Products", f"{len(latest_df):,}")
                    with col3:
                        st.metric("Total Revenue", f"${latest_df['amount'].sum():,.2f}")
                    
                    # Category breakdown
                    st.subheader("Category Breakdown")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.dataframe(
                            category_metrics,
                            column_config={
                                'category': 'Category',
                                'clean description': st.column_config.NumberColumn('Products'),
                                'amount': st.column_config.NumberColumn('Revenue', format="$%.2f")
                            },
                            hide_index=True
                        )
                    
                    with col2:
                        st.bar_chart(category_metrics.set_index('category')['amount'])
                
                # Set date as index and resample monthly for overall metrics
                monthly_df = monthly_df.set_index('date')
                monthly_df = monthly_df.resample('M').agg({
                    'unique_customers': 'last',
                    'total_quantity': 'sum',
                    'total_revenue': 'sum'
                }).reset_index()
                
                # Process category trends
                category_df = category_df.set_index('date')
                category_df = category_df.groupby(['date', 'category'])['revenue'].sum().reset_index()
                category_df = category_df.set_index('date').groupby('category').resample('M')['revenue'].sum().reset_index()
                
                # Sort chronologically and format dates
                monthly_df = monthly_df.sort_values('date')
                category_df = category_df.sort_values('date')
                
                # Format dates after sorting
                monthly_df['month_label'] = pd.to_datetime(monthly_df['date']).dt.strftime('%b %Y')
                category_df['month_label'] = pd.to_datetime(category_df['date']).dt.strftime('%b %Y')
                
                # Plot overall metrics
                st.subheader("Overall Trends")
                
                # Enhanced Unique Customers plot
                st.subheader("Unique Customers Over Time")
                fig_customers = px.line(monthly_df, 
                    x='month_label', 
                    y='unique_customers',
                    title='Unique Customers Trend',
                    markers=True,
                    labels={'month_label': 'Month', 'unique_customers': 'Number of Customers'}
                )
                fig_customers.update_layout(
                    hovermode='x unified',
                    yaxis_title='Number of Customers',
                    xaxis_title='Month'
                )
                st.plotly_chart(fig_customers, use_container_width=True)
                
                # Enhanced Products plot
                st.subheader("Total Products Over Time")
                fig_products = px.line(monthly_df, 
                    x='month_label', 
                    y='total_quantity',
                    title='Total Products Trend',
                    markers=True,
                    labels={'month_label': 'Month', 'total_quantity': 'Number of Products'}
                )
                fig_products.update_layout(
                    hovermode='x unified',
                    yaxis_title='Number of Products',
                    xaxis_title='Month'
                )
                st.plotly_chart(fig_products, use_container_width=True)
                
                # Enhanced Revenue plot
                st.subheader("Total Revenue Over Time")
                fig_revenue = px.line(monthly_df, 
                    x='month_label', 
                    y='total_revenue',
                    title='Total Revenue Trend',
                    markers=True,
                    labels={'month_label': 'Month', 'total_revenue': 'Revenue ($)'}
                )
                fig_revenue.update_layout(
                    hovermode='x unified',
                    yaxis_title='Revenue ($)',
                    xaxis_title='Month'
                )
                # Add moving average
                ma_period = 3  # 3-month moving average
                monthly_df['revenue_ma'] = monthly_df['total_revenue'].rolling(window=ma_period).mean()
                fig_revenue.add_trace(
                    go.Scatter(
                        x=monthly_df['month_label'],
                        y=monthly_df['revenue_ma'],
                        name=f'{ma_period}-Month Moving Average',
                        line=dict(dash='dash')
                    )
                )
                st.plotly_chart(fig_revenue, use_container_width=True)
                
                # Enhanced Category Revenue plot
                st.subheader("Revenue by Category Over Time")
                category_df_wide = category_df.pivot(index='date', columns='category', values='revenue').reset_index()
                category_df_wide['month_label'] = pd.to_datetime(category_df_wide['date']).dt.strftime('%b %Y')
                category_df_wide = category_df_wide.sort_values('date')  # Sort by actual date
                
                fig_categories = go.Figure()
                
                for category in category_df_wide.columns[2:]:  # Skip date and month_label columns
                    fig_categories.add_trace(
                        go.Scatter(
                            x=category_df_wide['month_label'],
                            y=category_df_wide[category],
                            name=category,
                            mode='lines+markers'
                        )
                    )
                
                fig_categories.update_layout(
                    title='Revenue by Category',
                    hovermode='x unified',
                    yaxis_title='Revenue ($)',
                    xaxis_title='Month',
                    showlegend=True,
                    legend=dict(
                        yanchor="top",
                        y=0.99,
                        xanchor="left",
                        x=0.01
                    ),
                    xaxis=dict(
                        type='category',  # Force categorical axis to maintain order
                        categoryorder='array',
                        categoryarray=category_df_wide['month_label'].tolist()
                    )
                )
                st.plotly_chart(fig_categories, use_container_width=True)
                
                # Add YoY Growth Rate
                if len(monthly_df) >= 13:  # Need at least 13 months for YoY comparison
                    st.subheader("Year-over-Year Growth")
                    monthly_df['YoY_growth'] = (monthly_df['total_revenue'].pct_change(periods=12) * 100)
                    fig_yoy = px.bar(
                        monthly_df.dropna(), 
                        x='month_label', 
                        y='YoY_growth',
                        title='Year-over-Year Revenue Growth',
                        labels={'month_label': 'Month', 'YoY_growth': 'Growth Rate (%)'}
                    )
                    fig_yoy.update_layout(
                        hovermode='x unified',
                        yaxis_title='Growth Rate (%)',
                        xaxis_title='Month'
                    )
                    st.plotly_chart(fig_yoy, use_container_width=True)
                
                # Revenue Distribution
                st.subheader("Revenue Distribution by Category")
                latest_month_data = category_df[category_df['date'] == category_df['date'].max()]
                fig_pie = px.pie(
                    latest_month_data,
                    values='revenue',
                    names='category',
                    title=f"Revenue Distribution ({latest_month_data['date'].iloc[0].strftime('%B %Y')})"
                )
                st.plotly_chart(fig_pie, use_container_width=True)
                
                # Show raw data
                st.subheader("Monthly Data")
                display_df = monthly_df[['date', 'unique_customers', 'total_quantity', 'total_revenue']].copy()
                st.dataframe(
                    display_df,
                    column_config={
                        'date': st.column_config.DateColumn('Month'),
                        'unique_customers': st.column_config.NumberColumn('Unique Customers'),
                        'total_quantity': st.column_config.NumberColumn('Total Products'),
                        'total_revenue': st.column_config.NumberColumn('Total Revenue', format="$%.2f")
                    },
                    hide_index=True
                )
                
                # Show category data
                st.subheader("Monthly Category Revenue")
                category_display = category_df.pivot(index='date', columns='category', values='revenue').reset_index()
                st.dataframe(
                    category_display,
                    column_config={
                        'date': st.column_config.DateColumn('Month'),
                        'UFB Services': st.column_config.NumberColumn('UFB Services', format="$%.2f"),
                        'Call Services': st.column_config.NumberColumn('Call Services', format="$%.2f"),
                        'DDI Services': st.column_config.NumberColumn('DDI Services', format="$%.2f"),
                        'Data Services': st.column_config.NumberColumn('Data Services', format="$%.2f"),
                        'Other Services': st.column_config.NumberColumn('Other Services', format="$%.2f")
                    },
                    hide_index=True
                )
            
            with tab5:
                st.subheader("Month-over-Month Changes")
                
                # Get current and previous month files
                current_date = pd.to_datetime(invoice_file.split('_')[2].split('.')[0])
                previous_date = current_date - pd.DateOffset(months=1)
                
                previous_file = None
                for f in os.listdir("bills"):
                    if f.startswith("Invoice_") and f.endswith(".csv"):
                        file_date = pd.to_datetime(f.split('_')[2].split('.')[0])
                        if file_date.strftime('%Y-%m') == previous_date.strftime('%Y-%m'):
                            previous_file = os.path.join("bills", f)
                            break
                
                if previous_file:
                    # Read previous month's data
                    prev_df = pd.read_csv(previous_file)
                    prev_df.columns = prev_df.columns.str.lower().str.strip()
                    prev_df['clean description'] = [clean_product_description(str(desc)) for desc in prev_df['description'].fillna('')]
                    prev_df = prev_df[prev_df['clean description'].notna() & (prev_df['clean description'] != '')]
                    
                    # Add categories
                    for data in [prev_df, df]:
                        data['category'] = data['clean description'].apply(lambda x: 
                            'UFB Services' if 'UFB' in x 
                            else 'Call Services' if 'Calls' in x 
                            else 'DDI Services' if 'DDI' in x 
                            else 'Data Services' if 'Data' in x 
                            else 'Other Services'
                        )
                    
                    # 1. Overall Changes
                    st.subheader(f"Overall Changes ({previous_date.strftime('%B %Y')} → {current_date.strftime('%B %Y')})")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    # Customer changes
                    prev_customers = prev_df['customer name'].nunique()
                    curr_customers = df['customer name'].nunique()
                    customer_change = curr_customers - prev_customers
                    
                    # Revenue changes
                    prev_revenue = prev_df['amount'].sum()
                    curr_revenue = df['amount'].sum()
                    revenue_change = curr_revenue - prev_revenue
                    revenue_pct = (revenue_change / prev_revenue) * 100 if prev_revenue != 0 else 0
                    
                    # Product changes
                    prev_products = len(prev_df)
                    curr_products = len(df)
                    product_change = curr_products - prev_products
                    
                    with col1:
                        st.metric(
                            "Customers",
                            f"{curr_customers}",
                            f"{customer_change:+d}",
                            delta_color="normal"
                        )
                    
                    with col2:
                        st.metric(
                            "Total Revenue",
                            f"${curr_revenue:,.2f}",
                            f"${revenue_change:+,.2f} ({revenue_pct:+.1f}%)",
                            delta_color="normal"
                        )
                    
                    with col3:
                        st.metric(
                            "Total Products",
                            f"{curr_products}",
                            f"{product_change:+d}",
                            delta_color="normal"
                        )
                    
                    # Add customer movement analysis
                    st.subheader("Customer Movement")
                    
                    # Get sets of customers from both months
                    prev_customers_set = set(prev_df['customer name'].unique())
                    curr_customers_set = set(df['customer name'].unique())
                    
                    # Find added and removed customers
                    added_customers = curr_customers_set - prev_customers_set
                    removed_customers = prev_customers_set - curr_customers_set
                    
                    # Create two columns for display
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("##### 🟢 New Customers")
                        if added_customers:
                            for customer in sorted(added_customers):
                                revenue = df[df['customer name'] == customer]['amount'].sum()
                                st.write(f"- {customer} (${revenue:,.2f})")
                        else:
                            st.write("*No new customers*")
                    
                    with col2:
                        st.markdown("##### 🔴 Churned Customers")
                        if removed_customers:
                            for customer in sorted(removed_customers):
                                prev_revenue = prev_df[prev_df['customer name'] == customer]['amount'].sum()
                                st.write(f"- {customer} (${prev_revenue:,.2f})")
                        else:
                            st.write("*No churned customers*")
                    
                    st.divider()
                    
                    # 2. Category Changes
                    st.subheader("Changes by Category")
                    
                    # Calculate category metrics
                    prev_cat = prev_df.groupby('category')['amount'].sum().reset_index()
                    curr_cat = df.groupby('category')['amount'].sum().reset_index()
                    
                    # Merge and calculate changes
                    cat_changes = pd.merge(
                        prev_cat, 
                        curr_cat, 
                        on='category', 
                        suffixes=('_prev', '_curr')
                    )
                    cat_changes['change'] = cat_changes['amount_curr'] - cat_changes['amount_prev']
                    cat_changes['pct_change'] = (cat_changes['change'] / cat_changes['amount_prev']) * 100
                    
                    # Plot category changes
                    fig_cat_changes = go.Figure()
                    
                    # Add bars for previous month
                    fig_cat_changes.add_trace(
                        go.Bar(
                            name=previous_date.strftime('%B %Y'),
                            x=cat_changes['category'],
                            y=cat_changes['amount_prev'],
                            text=cat_changes['amount_prev'].apply(lambda x: f'${x:,.2f}'),
                            textposition='auto',
                        )
                    )
                    
                    # Add bars for current month
                    fig_cat_changes.add_trace(
                        go.Bar(
                            name=current_date.strftime('%B %Y'),
                            x=cat_changes['category'],
                            y=cat_changes['amount_curr'],
                            text=cat_changes['amount_curr'].apply(lambda x: f'${x:,.2f}'),
                            textposition='auto',
                        )
                    )
                    
                    fig_cat_changes.update_layout(
                        barmode='group',
                        title='Revenue by Category - Month over Month Comparison',
                        xaxis_title='Category',
                        yaxis_title='Revenue ($)',
                        hovermode='x unified'
                    )
                    
                    st.plotly_chart(fig_cat_changes, use_container_width=True)
                    
                    # Show category changes table
                    st.dataframe(
                        cat_changes,
                        column_config={
                            'category': 'Category',
                            'amount_prev': st.column_config.NumberColumn(f'Revenue {previous_date.strftime("%B %Y")}', format="$%.2f"),
                            'amount_curr': st.column_config.NumberColumn(f'Revenue {current_date.strftime("%B %Y")}', format="$%.2f"),
                            'change': st.column_config.NumberColumn('Change', format="$%.2f"),
                            'pct_change': st.column_config.NumberColumn('% Change', format="%.1f%%")
                        },
                        hide_index=True
                    )
                    
                    # 3. Customer Changes
                    st.subheader("Customer Revenue Changes")
                    
                    # Calculate customer revenue for both months
                    prev_cust = prev_df.groupby('customer name')['amount'].sum().reset_index()
                    curr_cust = df.groupby('customer name')['amount'].sum().reset_index()
                    
                    # Merge and calculate changes
                    cust_changes = pd.merge(
                        prev_cust,
                        curr_cust,
                        on='customer name',
                        how='outer',
                        suffixes=('_prev', '_curr')
                    ).fillna(0)
                    
                    cust_changes['change'] = cust_changes['amount_curr'] - cust_changes['amount_prev']
                    cust_changes['pct_change'] = (cust_changes['change'] / cust_changes['amount_prev']) * 100
                    cust_changes = cust_changes.replace([np.inf, -np.inf], np.nan)
                    
                    # Sort by absolute change
                    cust_changes = cust_changes.sort_values('change', key=abs, ascending=False)
                    
                    # Show top changes with drill-downs
                    st.subheader("Top 10 Customer Changes (Click to expand details)")
                    
                    for _, row in cust_changes.head(10).iterrows():
                        change_color = "🔴" if row['change'] < 0 else "🟢"
                        expander_title = f"{change_color} {row['customer name']}: {row['change']:+,.2f} ({row['pct_change']:+.1f}%)"
                        
                        with st.expander(expander_title):
                            # Get detailed data for this customer
                            prev_detail = prev_df[prev_df['customer name'] == row['customer name']]
                            curr_detail = df[df['customer name'] == row['customer name']]
                            
                            # Product breakdown comparison
                            st.subheader("Product Changes")
                            
                            # Compare products side by side
                            product_comparison = pd.merge(
                                prev_detail.groupby(['clean description', 'category'])['amount'].sum().reset_index(),
                                curr_detail.groupby(['clean description', 'category'])['amount'].sum().reset_index(),
                                on=['clean description', 'category'],
                                how='outer',
                                suffixes=('_prev', '_curr')
                            ).fillna(0)
                            
                            product_comparison['change'] = product_comparison['amount_curr'] - product_comparison['amount_prev']
                            product_comparison['pct_change'] = (product_comparison['change'] / product_comparison['amount_prev'] * 100).replace([np.inf, -np.inf], np.nan)
                            
                            # Sort by absolute change
                            product_comparison = product_comparison.sort_values('change', key=abs, ascending=False)
                            
                            # Show product comparison table
                            st.dataframe(
                                product_comparison,
                                column_config={
                                    'clean description': 'Product',
                                    'category': 'Category',
                                    'amount_prev': st.column_config.NumberColumn(f'Revenue {previous_date.strftime("%B %Y")}', format="$%.2f"),
                                    'amount_curr': st.column_config.NumberColumn(f'Revenue {current_date.strftime("%B %Y")}', format="$%.2f"),
                                    'change': st.column_config.NumberColumn('Change', format="$%.2f"),
                                    'pct_change': st.column_config.NumberColumn('% Change', format="%.1f%%")
                                },
                                hide_index=True
                            )
                            
                            # Show category summary for this customer
                            st.subheader("Category Summary")
                            category_comparison = pd.merge(
                                prev_detail.groupby('category')['amount'].sum().reset_index(),
                                curr_detail.groupby('category')['amount'].sum().reset_index(),
                                on='category',
                                how='outer',
                                suffixes=('_prev', '_curr')
                            ).fillna(0)
                            
                            category_comparison['change'] = category_comparison['amount_curr'] - category_comparison['amount_prev']
                            category_comparison['pct_change'] = (category_comparison['change'] / category_comparison['amount_prev'] * 100).replace([np.inf, -np.inf], np.nan)
                            
                            # Create category comparison chart
                            fig_cat = go.Figure()
                            
                            fig_cat.add_trace(
                                go.Bar(
                                    name=previous_date.strftime('%B %Y'),
                                    x=category_comparison['category'],
                                    y=category_comparison['amount_prev'],
                                    text=category_comparison['amount_prev'].apply(lambda x: f'${x:,.2f}'),
                                    textposition='auto',
                                )
                            )
                            
                            fig_cat.add_trace(
                                go.Bar(
                                    name=current_date.strftime('%B %Y'),
                                    x=category_comparison['category'],
                                    y=category_comparison['amount_curr'],
                                    text=category_comparison['amount_curr'].apply(lambda x: f'${x:,.2f}'),
                                    textposition='auto',
                                )
                            )
                            
                            fig_cat.update_layout(
                                barmode='group',
                                title=f'Category Revenue Comparison for {row["customer name"]}',
                                xaxis_title='Category',
                                yaxis_title='Revenue ($)',
                                hovermode='x unified'
                            )
                            
                            st.plotly_chart(fig_cat, use_container_width=True)
                    
                    # Original summary table
                    st.subheader("Summary Table")
                    st.dataframe(
                        cust_changes.head(10),
                        column_config={
                            'customer name': 'Customer',
                            'amount_prev': st.column_config.NumberColumn(f'Revenue {previous_date.strftime("%B %Y")}', format="$%.2f"),
                            'amount_curr': st.column_config.NumberColumn(f'Revenue {current_date.strftime("%B %Y")}', format="$%.2f"),
                            'change': st.column_config.NumberColumn('Change', format="$%.2f"),
                            'pct_change': st.column_config.NumberColumn('% Change', format="%.1f%%")
                        },
                        hide_index=True
                    )
                
                else:
                    st.warning(f"No data available for previous month ({previous_date.strftime('%B %Y')})")
            
        except Exception as e:
            st.error(f"Error analyzing invoice: {str(e)}")
            st.code(traceback.format_exc()) 