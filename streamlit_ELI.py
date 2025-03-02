import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import plotly.io as pio
import os
import time
import random
import json
from pathlib import Path
from yahoofinancials import YahooFinancials
from concurrent.futures import ThreadPoolExecutor

# Create cache directory if it doesn't exist
cache_dir = Path("cache")
cache_dir.mkdir(exist_ok=True)

# Function to create a cache key from ticker and period
def get_cache_key(ticker, data_type, period="1y"):
    return f"{ticker}_{data_type}_{period}.json"

# Function to save data to cache
def save_to_cache(data, ticker, data_type, period="1y"):
    cache_key = get_cache_key(ticker, data_type, period)
    cache_path = cache_dir / cache_key
    
    # Convert datetime index to string for serialization
    if isinstance(data, pd.DataFrame) and isinstance(data.index, pd.DatetimeIndex):
        data_dict = {
            "index": data.index.strftime("%Y-%m-%d %H:%M:%S").tolist(),
            "data": data.to_dict(orient="records")
        }
    else:
        data_dict = data
        
    with open(cache_path, "w") as f:
        json.dump(data_dict, f)

# Function to load data from cache
def load_from_cache(ticker, data_type, period="1y"):
    cache_key = get_cache_key(ticker, data_type, period)
    cache_path = cache_dir / cache_key
    
    if cache_path.exists():
        # Check if cache is recent (less than 24 hours old)
        if time.time() - cache_path.stat().st_mtime < 86400:  # 24 hours in seconds
            with open(cache_path, "r") as f:
                data_dict = json.load(f)
                
            # Reconstruct DataFrame if it's a DataFrame
            if isinstance(data_dict, dict) and "index" in data_dict and "data" in data_dict:
                df = pd.DataFrame(data_dict["data"])
                df.index = pd.DatetimeIndex(data_dict["index"])
                return df
            return data_dict
    return None

# Add rate limiting function
def rate_limited_request(func, *args, **kwargs):
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Add a small random delay to avoid bursts of requests
            time.sleep(random.uniform(0.1, 0.5))
            return func(*args, **kwargs)
        except Exception as e:
            if "Too Many Requests" in str(e) or "Rate limit" in str(e):
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                    st.warning(f"Rate limited, waiting {wait_time:.1f} seconds before retrying...")
                    time.sleep(wait_time)
                else:
                    raise Exception("Too many requests. Please try again later.") from e
            else:
                raise  # Re-raise if it's not a rate limit error

# Set page to wide mode
st.set_page_config(layout="wide")

st.warning("""
    **Disclaimer:**
    - This app is for educational purposes only and should not be considered as financial advice.
    - We do not guarantee the accuracy of the data. The data source is Yahoo Finance, which may have limitations or inaccuracies.
    - Always conduct your own research and consult with a qualified financial advisor before making any investment decisions.
""")


def get_stock_data(ticker, period="1y"):
    # Try to load from cache first
    cached_data = load_from_cache(ticker, "history", period)
    if cached_data is not None:
        return cached_data
    
    try:
        # Use rate limited request with exponential backoff
        def fetch_data():
            stock = yf.Ticker(ticker)
            data = stock.history(period=period)
            data = data.dropna()
            return data
        
        data = rate_limited_request(fetch_data)
        
        # Save to cache for future use
        if not data.empty:
            save_to_cache(data, ticker, "history", period)
        
        return data
    except Exception as e:
        st.error(f"Error fetching stock data: {str(e)}")
        return pd.DataFrame()

def format_ticker(ticker):
    if ticker.isdigit():
        return f"{int(ticker):04d}.HK"
    return ticker

def calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct):
    strike_price = current_price * (strike_pct / 100) if strike_pct != 0 else 0
    airbag_price = current_price * (airbag_pct / 100) if airbag_pct != 0 else 0
    knockout_price = current_price * (knockout_pct / 100) if knockout_pct != 0 else 0
    return strike_price, airbag_price, knockout_price

def calculate_ema(data, period):
    return data['Close'].ewm(span=period, adjust=False).mean()

def calculate_volume_profile(data, bins=40):
    price_range = data['Close'].max() - data['Close'].min()
    bin_size = price_range / bins
    price_bins = pd.cut(data['Close'], bins=bins)
    volume_profile = data.groupby(price_bins)['Volume'].sum()
    bin_centers = [(i.left + i.right) / 2 for i in volume_profile.index]
    
    # Calculate POC
    poc_price = bin_centers[volume_profile.argmax()]
    
    # Calculate Value Area (70% of volume)
    total_volume = volume_profile.sum()
    target_volume = total_volume * 0.7
    cumulative_volume = 0
    value_area_low = value_area_high = poc_price
    
    for price, volume in zip(bin_centers, volume_profile):
        cumulative_volume += volume
        if cumulative_volume <= target_volume / 2:
            value_area_low = price
        if cumulative_volume >= total_volume - target_volume / 2:
            value_area_high = price
            break
    
    return volume_profile, bin_centers, bin_size, poc_price, value_area_low, value_area_high

def plot_stock_chart(data, ticker, strike_price, airbag_price, knockout_price, strike_name, knockout_name):
    fig = go.Figure()

    # Candlestick chart with custom colors
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name='Price',
        increasing_line_color='dodgerblue',  # Bullish bars in Dodge Blue
        decreasing_line_color='red'  # Bearish bars in red
    ))

    # Calculate EMAs
    ema_20 = calculate_ema(data, 20)
    ema_50 = calculate_ema(data, 50)
    ema_200 = calculate_ema(data, 200)

    # Calculate the position for price annotations
    first_date = data.index[0]
    last_date = data.index[-1]
    annotation_x = last_date + pd.Timedelta(days=2)  # 2 days after the last candle
    mid_date = first_date + (last_date - first_date) / 2  # Middle of the date range

    # Add price level lines with annotations on the right (only if not zero)
    if strike_price != 0:
        fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=strike_price, y1=strike_price,
                      line=dict(color="blue", width=2, dash="dash"))
        fig.add_annotation(x=annotation_x, y=strike_price, text=f"{strike_name}: {strike_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="blue"))

    if airbag_price != 0:
        fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=airbag_price, y1=airbag_price,
                      line=dict(color="green", width=2, dash="dash"))
        fig.add_annotation(x=annotation_x, y=airbag_price, text=f"Airbag Price: {airbag_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="green"))

    if knockout_price != 0:
        fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=knockout_price, y1=knockout_price,
                      line=dict(color="orange", width=2, dash="dash"))
        fig.add_annotation(x=annotation_x, y=knockout_price, text=f"{knockout_name}: {knockout_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="orange"))

    # Add EMA lines
    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=ema_20.iloc[-1], y1=ema_20.iloc[-1],
                  line=dict(color="gray", width=1, dash="dash"))
    fig.add_annotation(x=annotation_x, y=ema_20.iloc[-1], text=f"20 EMA: {ema_20.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=ema_50.iloc[-1], y1=ema_50.iloc[-1],
                  line=dict(color="gray", width=2, dash="dash"))
    fig.add_annotation(x=annotation_x, y=ema_50.iloc[-1], text=f"50 EMA: {ema_50.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=ema_200.iloc[-1], y1=ema_200.iloc[-1],
                  line=dict(color="gray", width=3, dash="dash"))
    fig.add_annotation(x=annotation_x, y=ema_200.iloc[-1], text=f"200 EMA: {ema_200.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    # Add current price annotation
    current_price = data['Close'].iloc[-1]
    fig.add_annotation(x=annotation_x, y=current_price, text=f"Current Price: {current_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=14, color="black"))

    # Calculate and add volume profile
    volume_profile, bin_centers, bin_size, poc_price, value_area_low, value_area_high = calculate_volume_profile(data)
    max_volume = volume_profile.max()
    fig.add_trace(go.Bar(
        x=volume_profile.values,
        y=bin_centers,
        orientation='h',
        name='Volume Profile',
        marker_color='rgba(200, 200, 200, 0.5)',
        width=bin_size,
        xaxis='x2'
    ))

    # Add POC line (red)
    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=poc_price, y1=poc_price,
                  line=dict(color="red", width=4))
    fig.add_annotation(x=annotation_x, y=poc_price, text=f"POC: {poc_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="red"))

    # Add Value Area lines (purple) with labels above and below the lines
    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=value_area_low, y1=value_area_low,
                  line=dict(color="purple", width=2))
    fig.add_annotation(x=mid_date, y=value_area_low, text=f"Value at Low: {value_area_low:.2f}",
                       showarrow=False, xanchor="center", yanchor="top", font=dict(size=12, color="purple"),
                       yshift=-5)  # Shift the label 5 pixels below the line

    fig.add_shape(type="line", x0=first_date, x1=annotation_x, y0=value_area_high, y1=value_area_high,
                  line=dict(color="purple", width=2))
    fig.add_annotation(x=mid_date, y=value_area_high, text=f"Value at High: {value_area_high:.2f}",
                       showarrow=False, xanchor="center", yanchor="bottom", font=dict(size=12, color="purple"),
                       yshift=5)  # Shift the label 5 pixels above the line

    fig.update_layout(
        title=f"{ticker} Stock Price",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=600,
        width=800,
        margin=dict(l=50, r=150, t=50, b=50),
        showlegend=False,
        font=dict(size=14),
        xaxis2=dict(
            side='top',
            overlaying='x',
            range=[0, max_volume],
            showgrid=False,
            showticklabels=False,
        ),
    )

    # Set x-axis to show only trading days and extend range for annotations
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # Hide weekends
            dict(values=["2023-12-25", "2024-01-01"])  # Example: hide specific holidays
        ],
        range=[first_date, annotation_x]  # Extend x-axis range for annotations
    )

    return fig


def get_index_constituents(ticker):
    # Create cache key based on index type (Hong Kong or US)
    index_type = "HSI" if ticker.isdigit() else "SP500"
    cached_data = load_from_cache("index", index_type)
    if cached_data is not None:
        return cached_data["constituents"], cached_data["index_name"]
    
    if ticker.isdigit():
        # Hong Kong stocks
        url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
        index_name = "Hang Seng Index"
    else:
        # US stocks
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        index_name = "S&P 500"
    
    try:
        # First check if we already have this info cached
        tables = pd.read_html(url)
        if ticker.isdigit():
            # Look for the table with 'Ticker' and 'Sub-index' columns
            for df in tables:
                if 'Ticker' in df.columns and 'Sub-index' in df.columns:
                    constituents = df['Ticker'].tolist()
                    # Remove 'SEHK:' prefix and format as ####.HK
                    constituents = [f"{int(code.split(':')[1]):04d}.HK" for code in constituents]
                    break
            else:
                raise ValueError("Could not find the correct table for HSI constituents")
        else:
            df = tables[0]  # S&P 500 constituents are in the first table
            constituents = df['Symbol'].tolist()
        
        # Cache results
        save_to_cache({
            "constituents": constituents,
            "index_name": index_name
        }, "index", index_type)
        
        st.success(f"Fetched {len(constituents)} constituents for {index_name}")
        print(f"First few constituents: {constituents[:5]}")
        return constituents, index_name
    except Exception as e:
        st.error(f"Error fetching constituents for {index_name}: {str(e)}")
        return [], index_name

# Helper function to format tickers for Yahoo Finance
def format_ticker(ticker):
    if ticker.isdigit():
        return f"{int(ticker):04d}.HK"
    else:
        return ticker.upper()

def get_stock_info(symbol):
    # Try to load from cache first
    cached_data = load_from_cache(symbol, "stock_info")
    if cached_data is not None:
        return cached_data
        
    try:
        def fetch_stock_info():
            stock = yf.Ticker(symbol)
            info = stock.info
            return {
                'symbol': symbol,
                'industry': info.get('industry', 'Unknown'),
                'pe': info.get('trailingPE', None),
                'roe': info.get('returnOnEquity', None)
            }
        
        # Add delay between consecutive API calls to prevent rate limiting
        time.sleep(random.uniform(0.5, 1.0))
        stock_info = fetch_stock_info()
        
        # Save to cache
        save_to_cache(stock_info, symbol, "stock_info")
        
        return stock_info
    except Exception as e:
        print(f"Error fetching data for {symbol}: {str(e)}")
        return {
            'symbol': symbol,
            'industry': 'Unknown',
            'pe': None,
            'roe': None
        }

def calculate_industry_averages(stocks_data, target_industry):
    industry_stocks = [stock for stock in stocks_data if stock['industry'] == target_industry]
    
    valid_pe = [stock['pe'] for stock in industry_stocks if stock['pe'] is not None and stock['pe'] > 0]
    valid_roe = [stock['roe'] for stock in industry_stocks if stock['roe'] is not None and stock['roe'] > 0]
    
    avg_pe = np.mean(valid_pe) if valid_pe else None
    avg_roe = np.mean(valid_roe) if valid_roe else None
    
    min_pe = min(valid_pe) if valid_pe else None
    max_pe = max(valid_pe) if valid_pe else None
    min_roe = min(valid_roe) if valid_roe else None
    max_roe = max(valid_roe) if valid_roe else None
    
    return avg_pe, avg_roe, len(industry_stocks), min_pe, max_pe, min_roe, max_roe

def get_financial_metrics(ticker):
    # Try to load from cache first
    cached_data = load_from_cache(ticker, "financial_metrics")
    if cached_data is not None:
        return cached_data
    
    try:
        # Use rate limiting to prevent API throttling
        def fetch_metrics():
            stock = yf.Ticker(ticker)
            info = stock.info
            
            metrics = {
                "Sector": info.get("sector", "N/A"),
                "Industry": info.get("industry", "N/A"),
                "Market Cap": info.get("marketCap", "N/A"),
                "Outstanding Shares": info.get("sharesOutstanding", "N/A"),       
                "Historical P/E": info.get("trailingPE", "N/A"),
                "Forward P/E": info.get("forwardPE", "N/A"),
                "PEG Ratio (5yr expected)": info.get("pegRatio", "N/A"),
                "Historical Dividend(%)": info.get("trailingAnnualDividendYield", 0) * 100,
                "Price/Book": info.get("priceToBook", "N/A"),
                "Net Income": info.get("netIncomeToCommon", "N/A"),
                "Revenue": info.get("totalRevenue", "N/A"),
                "Profit Margin": info.get("profitMargins", "N/A"),
                "ROE": info.get("returnOnEquity", "N/A"),
            }
            
            # Format large numbers
            for key in ["Market Cap", "Net Income", "Revenue", "Outstanding Shares"]:
                if isinstance(metrics[key], (int, float)) and metrics[key] is not None:
                    if abs(metrics[key]) >= 1e12:
                        metrics[key] = f"{metrics[key]/1e12:.2f}T"
                    elif abs(metrics[key]) >= 1e9:
                        metrics[key] = f"{metrics[key]/1e9:.2f}B"
                    elif abs(metrics[key]) >= 1e6:
                        metrics[key] = f"{metrics[key]/1e6:.2f}M"
            
            # Format percentages
            for key in ["Profit Margin", "ROE"]:
                if isinstance(metrics[key], float) and metrics[key] is not None:
                    metrics[key] = f"{metrics[key]:.2%}"
            
            # Round floating point numbers
            for key, value in metrics.items():
                if isinstance(value, float) and value is not None:
                    metrics[key] = round(value, 2)
            
            return metrics
        
        metrics = rate_limited_request(fetch_metrics)
        
        # Save to cache
        save_to_cache(metrics, ticker, "financial_metrics")
        
        return metrics
    except Exception as e:
        st.error(f"Error getting financial metrics: {str(e)}")
        # Return empty metrics with N/A values as fallback
        return {
            "Sector": "N/A",
            "Industry": "N/A",
            "Market Cap": "N/A",
            "Outstanding Shares": "N/A",       
            "Historical P/E": "N/A",
            "Forward P/E": "N/A",
            "PEG Ratio (5yr expected)": "N/A",
            "Historical Dividend(%)": "N/A",
            "Price/Book": "N/A",
            "Net Income": "N/A",
            "Revenue": "N/A",
            "Profit Margin": "N/A",
            "ROE": "N/A",
        }

# Helper functions for DCF model

def get_risk_free_rate():
    try:
        treasury_ticker = "^TNX"  # 10-year Treasury Yield
        treasury_data = yf.Ticker(treasury_ticker).history(period="1d")
        return treasury_data['Close'].iloc[-1] / 100  # Convert to decimal
    except:
        return 0.035  # Default to 3.5% if unable to fetch
    

def get_financial_data(ticker):
    # Try to load from cache first
    cached_data = load_from_cache(ticker, "financial_data")
    if cached_data is not None:
        return cached_data
    
    try:
        def fetch_financial_data():
            stock = yf.Ticker(ticker)
            financials = {}
            
            # Balance sheet data
            balance_sheet = stock.balance_sheet
            if balance_sheet is None or balance_sheet.empty:
                st.warning(f"Balance sheet data not available for {ticker}")
            else:
                financials['total_debt'] = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
                financials['cash'] = balance_sheet.loc['Cash Financial'].iloc[0] if 'Cash Financial' in balance_sheet.index else 0
                financials['cash_equivalents'] = balance_sheet.loc['Cash Equivalents'].iloc[0] if 'Cash Equivalents' in balance_sheet.index else 0
                financials['cash_and_cash_equivalents'] = balance_sheet.loc['Cash Cash Equivalents And Short Term Investments'].iloc[0] if 'Cash Cash Equivalents And Short Term Investments' in balance_sheet.index else 0
                financials['total_equity'] = balance_sheet.loc['Common Stock Equity'].iloc[0] if 'Common Stock Equity' in balance_sheet.index else 0
                financials['net_debt'] = balance_sheet.loc['Net Debt'].iloc[0] if 'Net Debt' in balance_sheet.index else 0
            
            # Get shares outstanding from info
            financials['share_issued'] = stock.info.get("sharesOutstanding", 0)
            
            # Income statement data
            income_stmt = stock.financials
            if income_stmt is None or income_stmt.empty:
                st.warning(f"Income statement data not available for {ticker}")
            else:
                financials['interest_expense'] = abs(income_stmt.loc['Interest Expense'].iloc[0]) if 'Interest Expense' in income_stmt.index else 0
                financials['income_tax'] = income_stmt.loc['Tax Provision'].iloc[0] if 'Tax Provision' in income_stmt.index else 0
                financials['net_income'] = income_stmt.loc['Net Income'].iloc[0] if 'Net Income' in income_stmt.index else 0
                financials['pre_tax_income'] = income_stmt.loc['Pretax Income'].iloc[0] if 'Pretax Income' in income_stmt.index else (financials.get('net_income', 0) + financials.get('income_tax', 0))
            
            # Cash flow statement data
            cash_flow = stock.cashflow
            if cash_flow is None or cash_flow.empty:
                st.warning(f"Cash flow data not available for {ticker}")
                financials['fcf_latest'] = 0
                financials['fcf_1years_ago'] = None
                financials['fcf_2years_ago'] = None
                financials['fcf_3years_ago'] = None
            else:
                if 'Free Cash Flow' in cash_flow.index:
                    financials['fcf_latest'] = cash_flow.loc['Free Cash Flow'].iloc[0]
                    financials['fcf_1years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[1] if len(cash_flow.columns) > 1 else None
                    financials['fcf_2years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[2] if len(cash_flow.columns) > 2 else None
                    financials['fcf_3years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[3] if len(cash_flow.columns) > 3 else None
                else:
                    # If Free Cash Flow is not available, calculate it
                    operating_cash_flow = cash_flow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cash_flow.index else 0
                    capital_expenditures = abs(cash_flow.loc['Capital Expenditure'].iloc[0]) if 'Capital Expenditure' in cash_flow.index else 0
                    financials['fcf_latest'] = operating_cash_flow - capital_expenditures
                    financials['fcf_1years_ago'] = None
                    financials['fcf_2years_ago'] = None
                    financials['fcf_3years_ago'] = None

            # Additional info
            financials['shares_outstanding'] = stock.info.get('sharesOutstanding', 0)
            financials['market_cap'] = stock.info.get('marketCap', 0)
            
            # Initialize any missing keys with zero values
            default_fields = [
                'total_debt', 'cash', 'cash_equivalents', 'cash_and_cash_equivalents',
                'total_equity', 'net_debt', 'share_issued', 'interest_expense',
                'income_tax', 'net_income', 'pre_tax_income', 'fcf_latest',
                'fcf_1years_ago', 'fcf_2years_ago', 'fcf_3years_ago',
                'shares_outstanding', 'market_cap'
            ]
            
            for field in default_fields:
                if field not in financials:
                    financials[field] = 0
            
            return financials
        
        financials = rate_limited_request(fetch_financial_data)
        
        # Save to cache
        save_to_cache(financials, ticker, "financial_data")
        
        return financials
    except Exception as e:
        st.error(f"Error getting financial data: {str(e)}")
        # Return default values to prevent errors
        return {
            'total_debt': 0,
            'cash': 0,
            'cash_equivalents': 0,
            'cash_and_cash_equivalents': 0,
            'total_equity': 0,
            'net_debt': 0,
            'share_issued': 0,
            'interest_expense': 0,
            'income_tax': 0,
            'net_income': 0,
            'pre_tax_income': 0,
            'fcf_latest': 0,
            'fcf_1years_ago': 0,
            'fcf_2years_ago': 0,
            'fcf_3years_ago': 0,
            'shares_outstanding': 0,
            'market_cap': 0
        }
    
def calculate_wacc(financials, risk_free_rate, market_risk_premium, beta):
    try:
        # Cost of Equity
        cost_of_equity = risk_free_rate + beta * market_risk_premium/100
        
        # Cost of Debt
        if financials['total_debt'] != 0 and financials['interest_expense'] != 0:
            cost_of_debt = financials['interest_expense'] / financials['total_debt']
        else:
            cost_of_debt = risk_free_rate
        
        # Tax Rate
        pre_tax_income = financials.get('pre_tax_income', 0)
        if pre_tax_income != 0:
            tax_rate = financials['income_tax'] / pre_tax_income
        else:
            tax_rate = 0.30  # Assume a default tax rate of 30%
        
        # Weights
        total_capital = financials['total_debt'] + financials['total_equity']
        if total_capital <= 0:
            return cost_of_equity  # Return cost of equity as fallback
            
        weight_of_debt = financials['total_debt'] / total_capital
        weight_of_equity = financials['total_equity'] / total_capital
        
        # WACC
        wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * cost_of_debt * (1 - tax_rate))
        
        return wacc
    except Exception as e:
        st.error(f"Error calculating WACC: {str(e)}")
        return risk_free_rate  # Return risk-free rate as fallback

def calculate_fcf_growth_rate(financials):
    try:
        fcf_latest = financials.get('fcf_latest', 0)
        fcf_1year_ago = financials.get('fcf_1years_ago', 0)
        fcf_2years_ago = financials.get('fcf_2years_ago', 0)
        fcf_3years_ago = financials.get('fcf_3years_ago', 0)

        if fcf_latest <= 0 or (fcf_1year_ago is None and fcf_2years_ago is None and fcf_3years_ago is None):
            return 0.03, "Growth rate cannot be estimated due to negative FCF, using default 3%"

        if fcf_3years_ago is not None and fcf_3years_ago > 0:
            return (fcf_latest / fcf_3years_ago) ** (1/3) - 1, None
        elif fcf_2years_ago is not None and fcf_2years_ago > 0:
            return (fcf_latest / fcf_2years_ago) ** (1/2) - 1, None
        elif fcf_1year_ago is not None and fcf_1year_ago > 0:
            return (fcf_latest / fcf_1year_ago) - 1, None
        else:
            return 0.03, "Growth rate cannot be estimated, using default 3%"
    except Exception as e:
        return 0.03, f"Error calculating FCF growth rate: {str(e)}, using default 3%"


def calculate_excess_return_fair_value(financials, cost_of_equity, terminal_growth_rate):
    try:
        book_value = financials.get('total_equity', 0)
        if book_value <= 0:
            return None, "Negative or zero book value"
            
        net_income = financials.get('net_income', 0)
        if net_income <= 0:
            return None, "Negative or zero net income"
            
        shares_outstanding = financials.get('share_issued', 0)
        if shares_outstanding <= 0:
            return None, "Share count data unavailable"

        roe = net_income / book_value
        excess_return = (roe - cost_of_equity) * book_value
        
        # Check if denominator is zero or negative
        if cost_of_equity <= terminal_growth_rate:
            return None, "Cost of equity must be greater than terminal growth rate"
            
        terminal_value = excess_return * (1 + terminal_growth_rate) / (cost_of_equity - terminal_growth_rate)
        equity_value = book_value + terminal_value
        fair_value = equity_value / shares_outstanding

        return fair_value, None
    except Exception as e:
        return None, f"Error in excess return calculation: {str(e)}"

def calculate_dcf_fair_value(financials, wacc, terminal_growth_rate, high_growth_period, current_price):
    try:
        fcf_growth_rate, error_message = calculate_fcf_growth_rate(financials)
        
        if fcf_growth_rate is None:
            return None, error_message if error_message else "Unable to calculate FCF growth rate"
        
        fcf = financials.get('fcf_latest', 0)
        if fcf <= 0:
            return None, "Negative or zero free cash flow"
            
        pv_fcf = 0
        
        # High growth period
        for i in range(1, high_growth_period + 1):
            fcf *= (1 + fcf_growth_rate)
            pv_fcf += fcf / ((1 + wacc) ** i)
        
        # Check if denominator is zero or negative
        if wacc <= terminal_growth_rate:
            return None, "WACC must be greater than terminal growth rate"
            
        # Terminal value
        terminal_value = fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
        pv_terminal_value = terminal_value / ((1 + wacc) ** high_growth_period)
        
        # Enterprise Value
        enterprise_value = pv_fcf + pv_terminal_value
        
        # Equity Value
        equity_value = enterprise_value - financials.get('total_debt', 0) + financials.get('cash_and_cash_equivalents', 0)
        
        # Shares outstanding
        shares_outstanding = financials.get('share_issued', 0)
        if shares_outstanding <= 0:
            if current_price <= 0:
                return None, "Invalid current price and shares outstanding"
            shares_outstanding = equity_value / current_price
        
        # Fair value per share
        fair_value = equity_value / shares_outstanding
        
        return fair_value, None
    except Exception as e:
        return None, f"Error in DCF calculation: {str(e)}"

def main():
    st.title("Stock Fundamentals with Key Levels and DCF Valuation by JC")
    
    # Create cache management UI
    with st.sidebar:
        st.header("Cache Management")
        clear_cache = st.button("Clear All Cache")
        if clear_cache:
            # Delete all files in cache directory
            for cached_file in cache_dir.glob("*"):
                cached_file.unlink()
            st.success("Cache cleared successfully!")
            
        # Display cache info
        cache_files = list(cache_dir.glob("*"))
        if cache_files:
            cache_size = sum(f.stat().st_size for f in cache_files) / 1024
            st.info(f"Cache size: {cache_size:.2f} KB, {len(cache_files)} files")
        else:
            st.info("Cache is empty")
        
        st.markdown("---")
        
        # Add toggle for throttling
        enable_throttling = st.checkbox("Enable API throttling", value=True, 
                                     help="Enable to prevent rate limiting by slowing down API requests")
        if enable_throttling:
            st.session_state.throttle_delay = st.slider("Request delay (seconds)", 0.1, 3.0, 1.0, 0.1,
                                                   help="Time to wait between API requests")
        else:
            st.session_state.throttle_delay = 0.0
        
        st.markdown("---")
    
    # Create two columns for layout
    col1, col2 = st.columns([1, 4])

    # Sidebar inputs (now in the first column)
    with col1:
        ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
        knockout_name = st.radio("Choose name for Knock-out Price:", ("Knock-out Price", "Upper Window"))
        strike_name = st.radio("Choose name for Strike Price:", ("Strike Price", "Lower Window"))
        
        knockout_pct = st.number_input(f"{knockout_name} %:", value=0.0)
        strike_pct = st.number_input(f"{strike_name} %:", value=0.0)
        airbag_pct = st.number_input("Airbag Price %:", value=0.0)
        
        # Add option for cached data only
        use_cached_only = st.checkbox("Use cached data only", value=False,
                                    help="If checked, the app will only use cached data and won't make new API calls")
        st.session_state.use_cached_only = use_cached_only
               
        refresh = st.button("Refresh Data")

    try:
        formatted_ticker = format_ticker(ticker)
    except Exception as e:
        st.error(f"Error formatting ticker: {str(e)}")
        return


 for {index_name} constituents..."):
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        stocks_data = list(executor.map(get_stock_info, constituents))
                
                target_stock = get_stock_info(st.session_state.formatted_ticker)
                if target_stock['industry'] != 'Unknown':
                    avg_pe, avg_roe, industry_count, min_pe, max_pe, min_roe, max_roe = calculate_industry_averages(stocks_data, target_stock['industry'])
                    st.session_state.industry_averages = {
                        'avg_pe': avg_pe,
                        'avg_roe': avg_roe,
                        'industry': target_stock['industry'],
                        'count': industry_count,
                        'min_pe': min_pe,
                        'max_pe': max_pe,
                        'min_roe': min_roe,
                        'max_roe': max_roe
                    }
                else:
                    st.warning(f"Unable to fetch industry information for {st.session_state.formatted_ticker}")
            else:
                st.warning(f"Unable to fetch constituents for {index_name}")

        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")

    if hasattr(st.session_state, 'data') and not st.session_state.data.empty:
        try:
            current_price = st.session_state.data['Close'].iloc[-1]
            strike_price, airbag_price, knockout_price = calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct)
            
            with col1:
                st.markdown("<h3>Price Levels:</h3>", unsafe_allow_html=True)
                st.markdown(f"<h4>Current Price: {current_price:.2f}</h4>", unsafe_allow_html=True)
                st.markdown(f"<p>{knockout_name} ({knockout_pct}%): {knockout_price:.2f}</p>", unsafe_allow_html=True)
                st.markdown(f"<p>{strike_name} ({strike_pct}%): {strike_price:.2f}</p>", unsafe_allow_html=True)
                st.markdown(f"<p>Airbag Price ({airbag_pct}%): {airbag_price:.2f}</p>", unsafe_allow_html=True)

                # DCF Model Inputs
                st.markdown("### DCF Model Inputs")
                market_risk_premium = st.number_input("Market Risk Premium (%):", value=8.5, step=0.1)
                terminal_growth_rate = st.number_input("Terminal Growth Rate (%):", value=3.0, step=0.1)
                risk_free_rate = st.number_input("Risk-Free Rate (%):", value=get_risk_free_rate(), step=0.01)
                high_growth_period = st.number_input("High Growth Period (years):", value=5, step=1, min_value=1)

            with col2:
                st.markdown("<h3>Financial Metrics & Data from Yahoo Finance:</h3>", unsafe_allow_html=True)
                try:
                    metrics = get_financial_metrics(st.session_state.formatted_ticker)
                    cols = st.columns(2)
                    for i, (key, value) in enumerate(metrics.items()):
                        cols[i % 2].markdown(f"<b>{key}:</b> {value}", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error fetching financial metrics: {str(e)}")

                st.markdown("<h3>Stock Chart:</h3>", unsafe_allow_html=True)
                fig = plot_stock_chart(st.session_state.data, st.session_state.formatted_ticker, 
                                       strike_price, airbag_price, knockout_price,
                                       strike_name, knockout_name)
                st.plotly_chart(fig, use_container_width=True)               

                st.markdown("<h3>Latest News:</h3>", unsafe_allow_html=True)
                st.info(f"You can try visiting this URL directly for news: https://finance.yahoo.com/quote/{st.session_state.formatted_ticker}/news/")
                st.markdown(f"<h3>Analyst Ratings - {ticker} :</h3>", unsafe_allow_html=True)
                try:
                    stock = yf.Ticker(st.session_state.formatted_ticker)
                    
                    recommendations = stock.recommendations_summary
                    if recommendations is not None and not recommendations.empty:
                        st.subheader("Recommendation Summary")
                        summary = recommendations.set_index('period')

                        col1, col2 = st.columns(2)

                        with col1:
                            fig_summary = go.Figure()
                            categories = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                            colors = ['darkgreen', 'lightgreen', 'gray', 'pink', 'red']
                            period_labels = {
                                '0m': 'Current Month', '-1m': '1 Month Ago',
                                '-2m': '2 Months Ago', '-3m': '3 Months Ago'
                            }

                            for category, color in zip(categories, colors):
                                if category in summary.columns:
                                    fig_summary.add_trace(go.Bar(
                                        x=[period_labels.get(x, x) for x in summary.index],
                                        y=summary[category],
                                        name=category.capitalize(),
                                        marker_color=color
                                    ))

                            fig_summary.update_layout(
                                barmode='stack',
                                title="Analyst Recommendations Over Time",
                                xaxis_title="Period",
                                yaxis_title="Number of Recommendations",
                                legend_title="Recommendation Type",
                                height=400,
                                margin=dict(l=50, r=50, t=50, b=70)
                            )

                            st.plotly_chart(fig_summary, use_container_width=True)

                            # Add rating summary below the chart
                            if not summary.empty:
                                latest = summary.iloc[0]
                                st.markdown("<div style='border:1px solid #cccccc; padding:5px; font-size:0.8em;'>", unsafe_allow_html=True)
                                st.markdown("<p style='text-align:center; font-weight:bold; margin-bottom:5px;'>Current Month's Rating</p>", unsafe_allow_html=True)
                                
                                # Build table with available columns
                                table_html = "<table width='100%'><tr>"
                                for category in categories:
                                    if category in latest.index:
                                        table_html += f"<td><b>{category.capitalize()}:</b> {latest[category]}</td>"
                                table_html += "</tr></table>"
                                
                                st.markdown(table_html, unsafe_allow_html=True)
                                st.markdown("</div>", unsafe_allow_html=True)

                        with col2:
                            price_targets = stock.info
                            current_price = price_targets.get('currentPrice', 0)
                            if current_price == 0:
                                current_price = st.session_state.data['Close'].iloc[-1]
                                
                            target_low = price_targets.get('targetLowPrice', 0)
                            target_mean = price_targets.get('targetMeanPrice', 0)
                            target_high = price_targets.get('targetHighPrice', 0)

                            # Only display price targets if we have valid data
                            if target_low > 0 and target_mean > 0 and target_high > 0:
                                fig_targets = go.Figure()

                                fig_targets.add_trace(go.Indicator(
                                    mode="number+gauge+delta",
                                    value=current_price,
                                    delta={'reference': target_mean, 'position': "top"},
                                    domain={'x': [0, 1], 'y': [0.25, 1]},
                                    title={'text': "Price Target"},
                                    gauge={
                                        'axis': {'range': [None, target_high], 'tickwidth': 1},
                                        'bar': {'color': "darkgray"},
                                        'steps': [
                                            {'range': [0, target_low], 'color': "red"},
                                            {'range': [target_low, target_high], 'color': "lightgreen"}
                                        ],
                                        'threshold': {
                                            'line': {'color': "darkgreen", 'width': 4},
                                            'thickness': 0.75,
                                            'value': target_mean
                                        }
                                    }
                                ))

                                fig_targets.update_layout(
                                    title="Analyst Price Targets",
                                    height=500,
                                    margin=dict(l=50, r=50, t=50, b=70),
                                )

                                annotation_text = (
                                    f"Green Zone: Target range ${target_low:.2f} - ${target_high:.2f}<br>"
                                    f"Green Line: Average target @ ${target_mean:.2f}<br>"
                                    f"Gray Bar: Current price  @ ${current_price:.2f}"
                                )
                                fig_targets.add_annotation(
                                    x=0.5,
                                    y=0,
                                    xref="paper",
                                    yref="paper",
                                    text=annotation_text,
                                    showarrow=False,
                                    font=dict(size=12),
                                    align="left",
                                    xanchor="center",
                                    yanchor="top",
                                    bordercolor="black",
                                    borderwidth=1,
                                    borderpad=10,
                                    bgcolor="white",
                                )

                                st.plotly_chart(fig_targets, use_container_width=True)
                            else:
                                st.info("Analyst price targets not available for this stock")
                    else:
                        st.info("Analyst recommendations not available for this stock")

                except Exception as e:
                    st.error(f"Error fetching analyst ratings: {str(e)}")

                st.markdown("<br>", unsafe_allow_html=True)

                # New section for Valuation Model
                st.markdown(f"<h3>Fair Value Calculation - {ticker} </h3>", unsafe_allow_html=True)
                try:
                    # Fetch required financial data
                    financials = get_financial_data(st.session_state.formatted_ticker)
                    
                    # Get sector information
                    metrics = get_financial_metrics(st.session_state.formatted_ticker)
                    sector = metrics.get("Sector", "Unknown")
                    
                    # Calculate and display WACC components
                    stock = yf.Ticker(st.session_state.formatted_ticker)
                    beta = stock.info.get('beta', 1.0)  # Default to 1 if beta is not available
                    
                    # Check for zero/invalid values to prevent division by zero
                    if financials['total_equity'] > 0 and financials['net_income'] != 0:
                        roe = financials['net_income'] / financials['total_equity']
                    else:
                        roe = 0
                    
                    cost_of_equity = risk_free_rate + beta * (market_risk_premium/100)
                    
                    if financials['total_debt'] != 0 and financials['interest_expense'] != 0:
                        cost_of_debt = financials['interest_expense'] / financials['total_debt']
                    else:
                        cost_of_debt = risk_free_rate
                    
                    if financials['pre_tax_income'] != 0:
                        tax_rate = financials['income_tax'] / financials['pre_tax_income']
                    else:
                        tax_rate = 0.21  # Assume a default corporate tax rate of 21%                    
                    
                    total_capital = financials['total_debt'] + financials['total_equity']
                    if total_capital > 0:
                        weight_of_debt = financials['total_debt'] / total_capital
                        weight_of_equity = financials['total_equity'] / total_capital
                    else:
                        weight_of_debt = 0
                        weight_of_equity = 1                    
                    
                    wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * cost_of_debt * (1 - tax_rate))
                    
                    # Fallback to fetching PE from info if available
                    pe = stock.info.get('trailingPE', None)
                    if pe is None or pe <= 0:
                        pe = "N/A"
                    
                    # Calculate and display FCF Growth Rate
                    fcf_growth_rate, fcf_error = calculate_fcf_growth_rate(financials)
                    
                    # Perform Valuation based on sector
                    if sector == 'Financial Services':
                        fair_value, error_message = calculate_excess_return_fair_value(financials, cost_of_equity, terminal_growth_rate/100)
                        valuation_method = "Excess Return Model (for Financial company)"
                    else:
                        fair_value, error_message = calculate_dcf_fair_value(financials, wacc, terminal_growth_rate/100, high_growth_period, current_price)
                        valuation_method = "Discounted Cash Flow (DCF) Model (Inapplicable to Negative FCF)"
                    
                   
                    st.markdown(f"<h4>Fair Value by {valuation_method}:</h4>", unsafe_allow_html=True)
                    
                    
                    # Display results                  
                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        # Industry averages
                        if hasattr(st.session_state, 'industry_averages'):
                            st.markdown("<h4>Industry Averages:</h4>", unsafe_allow_html=True)
                            st.markdown(f"Industry: {st.session_state.industry_averages['industry']}")
                            st.markdown(f"Number of companies: {st.session_state.industry_averages['count']}")
                            if st.session_state.industry_averages['avg_pe']:
                                st.markdown(f"Average P/E: {st.session_state.industry_averages['avg_pe']:.2f}")
                                st.markdown(f"P/E Range: {st.session_state.industry_averages['min_pe']:.2f} - {st.session_state.industry_averages['max_pe']:.2f}")
                            else:
                                st.markdown("Average P/E: N/A")
                            if st.session_state.industry_averages['avg_roe']:
                                st.markdown(f"Average ROE: {st.session_state.industry_averages['avg_roe']:.2%}")
                                st.markdown(f"ROE Range: {st.session_state.industry_averages['min_roe']:.2%} - {st.session_state.industry_averages['max_roe']:.2%}")
                            else:
                                st.markdown("Average ROE: N/A")
                        

                    with col2:
                        st.markdown(f"<p><b>WACC:</b> {wacc:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Risk-free rate:</b> {risk_free_rate:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Beta:</b> {beta:.2f}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Historical PE:</b> {pe}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Historical ROE:</b> {roe:.2%}</p>", unsafe_allow_html=True)
                        if isinstance(fcf_growth_rate, (int, float)):
                            st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_growth_rate:.2%}</p>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_error}</p>", unsafe_allow_html=True)
                        if error_message:
                            st.markdown(f"<p><b>Fair Value:</b> {error_message}</p>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<p><b>Fair Value:</b> ${fair_value:.2f}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Current Price:</b> ${current_price:.2f}</p>", unsafe_allow_html=True)
                        

                    with col3:
                        # FCF Trend Chart
                        fcf_data = {
                            'Year': ['3 years ago', '2 years ago', '1 year ago', 'Latest'],
                            'FCF': [
                                financials.get('fcf_3years_ago', 0), 
                                financials.get('fcf_2years_ago', 0), 
                                financials.get('fcf_1years_ago', 0), 
                                financials.get('fcf_latest', 0)
                            ]
                        }
                        
                        # Filter out None values
                        valid_years = []
                        valid_fcf = []
                        for year, fcf in zip(fcf_data['Year'], fcf_data['FCF']):
                            if fcf is not None:
                                valid_years.append(year)
                                valid_fcf.append(fcf)
                                
                        if valid_fcf and any(fcf != 0 for fcf in valid_fcf):
                            fcf_df = pd.DataFrame({
                                'Year': valid_years,
                                'FCF': valid_fcf
                            })
                            
                            # Determine the appropriate scale (B or M) based on the maximum FCF value
                            max_fcf = np.max(np.abs(fcf_df['FCF']))
                            if max_fcf >= 1e9:
                                scale = 1e9
                                scale_label = 'B'
                            else:
                                scale = 1e6
                                scale_label = 'M'
                            
                            # Scale the FCF values
                            fcf_df['FCF_scaled'] = fcf_df['FCF'] / scale
                            
                            fig_fcf = go.Figure()
                            fig_fcf.add_trace(go.Scatter(
                                x=fcf_df['Year'], 
                                y=fcf_df['FCF_scaled'], 
                                mode='lines+markers',
                                text=[f'${value:.2f}{scale_label}' for value in fcf_df['FCF_scaled']],
                                hovertemplate='%{text}<extra></extra>'
                            ))
                            
                            fig_fcf.update_layout(
                                title="Free Cash Flow (FCF) Trend",
                                xaxis_title="Year",
                                yaxis_title=f"FCF (${scale_label})",
                                height=300,
                                width=400,
                                margin=dict(l=0, r=0, t=40, b=0),
                            )
                            
                            fig_fcf.update_yaxes(tickformat=".2f")
                            
                            st.plotly_chart(fig_fcf)
                        else:
                            st.info("Free Cash Flow data not available for chart")

                    with col4:
                        if not error_message and isinstance(fair_value, (int, float)) and fair_value > 0:
                            df = pd.DataFrame({
                                'Type': ['Current Price', 'Fair Value'],
                                'Price': [current_price, fair_value]
                            })
                            
                            diff = fair_value - current_price
                            percentage_dis = (1-current_price / fair_value) * 100
                            percentage_pre = (current_price / fair_value-1) * 100
                            
                            if diff > 0:
                                diff_label = f"Discount by {abs(percentage_dis):.1f}%"
                                color_scheme = ['#FF4B4B', '#00CC96']  # Red for current price, green for fair value
                            else:
                                diff_label = f"Premium by {abs(percentage_pre):.1f}%"
                                color_scheme = ['#00CC96', '#FF4B4B']  # Green for current price, red for fair value
                            
                            fig = go.Figure()
                            
                            max_x = max(fair_value, current_price) * 1.1  # Add 10% padding
                            
                            for i, row in df.iterrows():
                                fig.add_trace(go.Bar(
                                    x=[row['Price']],
                                    y=[row['Type']],
                                    orientation='h',
                                    marker_color=color_scheme[i],
                                    text=[f"${row['Price']:.2f}"],
                                    textposition='auto',
                                    insidetextanchor='middle',
                                    textfont=dict(color='white' if row['Price'] / max_x > 0.3 else 'black')
                                ))
                            
                            fig.update_layout(
                                title=f"Price Comparison<br><sub>{diff_label}</sub>",
                                xaxis_title="Price ($)",
                                yaxis_title="",
                                height=300,
                                width=400,
                                margin=dict(l=0, r=50, t=40, b=0),
                                xaxis=dict(range=[0, max_x]),
                                barmode='group',
                                uniformtext=dict(mode='hide', minsize=8),
                            )
                            
                            for i, row in df.iterrows():
                                if row['Price'] / max_x <= 0.3:
                                    fig.add_annotation(
                                        x=row['Price'],
                                        y=row['Type'],
                                        text=f"${row['Price']:.2f}",
                                        showarrow=False,
                                        xanchor='left',
                                        xshift=5,
                                        font=dict(color='black')
                                    )
                            
                            st.plotly_chart(fig)
                            
                            st.markdown(f"<p><b>Difference with Fair Value:</b> ${diff:.2f}</p>", unsafe_allow_html=True)
                            
                        else:
                            st.info("Fair value calculation not available. This could be due to negative FCF or missing data.")
                            if error_message:
                                st.markdown(f"<p><b>Details:</b> {error_message}</p>", unsafe_allow_html=True)

                    # New section: Intermediate Data for the Calculation
                    st.markdown("<h4>Intermediate Data for the Calculation:</h4>", unsafe_allow_html=True)

                    # New function to format large numbers
                    def format_large_number(number):
                        if number is None:
                            return "N/A"
                        if abs(number) >= 1e9:
                            return f"${number/1e9:.2f}B"
                        elif abs(number) >= 1e6:
                            return f"${number/1e6:.2f}M"
                        else:
                            return f"${number:,.2f}"
                        
                    # Create 4 columns for intermediate data
                    int_col1, int_col2, int_col3, int_col4 = st.columns(4)
                    
                    with int_col1:
                        st.markdown(f"<p><b>ROE:</b> {roe:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Cost of Debt:</b> {cost_of_debt:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Cost of Equity:</b> {cost_of_equity:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Weight of Debt:</b> {weight_of_debt:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Weight of Equity:</b> {weight_of_equity:.2%}</p>", unsafe_allow_html=True)
                    
                    with int_col2:
                        st.markdown(f"<p><b>Latest FCF:</b> {format_large_number(financials.get('fcf_latest'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>FCF 1 year ago:</b> {format_large_number(financials.get('fcf_1years_ago'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>FCF 2 years ago:</b> {format_large_number(financials.get('fcf_2years_ago'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>FCF 3 years ago:</b> {format_large_number(financials.get('fcf_3years_ago'))}</p>", unsafe_allow_html=True)
                        if isinstance(fcf_growth_rate, (int, float)):
                            st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_growth_rate:.2%}</p>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<p><b>FCF Growth Rate:</b> N/A</p>", unsafe_allow_html=True)
                    
                    with int_col3:
                        st.markdown(f"<p><b>Interest Expense:</b> {format_large_number(financials.get('interest_expense'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Tax Expense:</b> {format_large_number(financials.get('income_tax'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Pretax Income:</b> {format_large_number(financials.get('pre_tax_income'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Total Equity:</b> {format_large_number(financials.get('total_equity'))}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Total Debt:</b> {format_large_number(financials.get('total_debt'))}</p>", unsafe_allow_html=True)
                    
                    with int_col4:                    
                        st.markdown(f"<p><b>Cash & Cash Equivalents:</b> {format_large_number(financials.get('cash_and_cash_equivalents'))}</p>", unsafe_allow_html=True)                    
                        st.markdown(f"<p><b>Shares Outstanding:</b> {format_large_number(financials.get('share_issued'))}</p>", unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Error calculating DCF valuation: {str(e)}")
                    import traceback
                    st.write("Debug information:")
                    st.code(traceback.format_exc())

        except Exception as e:
            st.error(f"Error processing data: {str(e)}")
            import traceback
            st.write("Debug information:")
            st.code(traceback.format_exc())
    else:
        st.warning("No data available. Please check the ticker symbol and try again.")

if __name__ == "__main__":
    main()
