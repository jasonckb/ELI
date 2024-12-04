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
from yahoofinancials import YahooFinancials
from concurrent.futures import ThreadPoolExecutor

# Set page configuration
st.set_page_config(
    layout="wide",
    page_title="Stock Analysis Dashboard",
    page_icon="📈"
)

# Initialize session state for DCF inputs
if 'market_risk_premium' not in st.session_state:
    st.session_state.market_risk_premium = 8.5
if 'terminal_growth_rate' not in st.session_state:
    st.session_state.terminal_growth_rate = 3.0
if 'risk_free_rate' not in st.session_state:
    st.session_state.risk_free_rate = None
if 'high_growth_period' not in st.session_state:
    st.session_state.high_growth_period = 5
if 'dcf_update' not in st.session_state:
    st.session_state.dcf_update = False

st.warning("""
    **Disclaimer:**
    - This app is for educational purposes only and should not be considered as financial advice.
    - We do not guarantee the accuracy of the data. The data source is Yahoo Finance, which may have limitations or inaccuracies.
    - Always conduct your own research and consult with a qualified financial advisor before making any investment decisions.
""")


def format_large_number(number):
    """Format large numbers with proper type checking"""
    try:
        if isinstance(number, str):
            return number
        if not isinstance(number, (int, float)):
            return "N/A"
        if abs(number) >= 1e9:
            return f"${number/1e9:.2f}B"
        elif abs(number) >= 1e6:
            return f"${number/1e6:.2f}M"
        else:
            return f"${number:,.2f}"
    except Exception:
        return "N/A"

@st.cache_data(ttl=3600)
def get_stock_data(ticker, period="1y"):
    """Fetch stock data with caching"""
    try:
        stock = yf.Ticker(ticker)
        data = stock.history(period=period)
        if data.empty:
            raise ValueError(f"No data found for ticker {ticker}")
        return data.dropna()
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return None

@st.cache_data(ttl=3600)
def get_risk_free_rate():
    """Get risk-free rate with caching"""
    try:
        treasury_ticker = "^TNX"
        treasury_data = yf.Ticker(treasury_ticker).history(period="1d")
        return treasury_data['Close'].iloc[-1] / 100
    except:
        return 0.035

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
    if ticker.isdigit():
        # Hong Kong stocks
        url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
        index_name = "Hang Seng Index"
    else:
        # US stocks
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        index_name = "S&P 500"
    
    try:
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
        
        print(f"Fetched {len(constituents)} constituents for {index_name}")
        print(f"First few constituents: {constituents[:5]}")
        return constituents, index_name
    except Exception as e:
        print(f"Error fetching constituents for {index_name}: {str(e)}")
        return [], index_name

# Helper function to format tickers for Yahoo Finance
def format_ticker(ticker):
    if ticker.isdigit():
        return f"{int(ticker):04d}.HK"
    else:
        return ticker.upper()

def get_stock_info(symbol):
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        return {
            'symbol': symbol,
            'industry': info.get('industry', 'Unknown'),
            'pe': info.get('trailingPE', None),
            'roe': info.get('returnOnEquity', None)
        }
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
        "Historical Dividend(%)": info.get("trailingAnnualDividendYield", "N/A")*100,
        "Price/Book": info.get("priceToBook", "N/A"),
        "Net Income": info.get("netIncomeToCommon", "N/A"),
        "Revenue": info.get("totalRevenue", "N/A"),
        "Profit Margin": info.get("profitMargins", "N/A"),
        "ROE": info.get("returnOnEquity", "N/A"),
    }
    
    # Format large numbers
    for key in ["Market Cap", "Net Income", "Revenue", "Outstanding Shares"]:
        if isinstance(metrics[key], (int, float)):
            if abs(metrics[key]) >= 1e12:
                metrics[key] = f"{metrics[key]/1e12:.2f}T"
            elif abs(metrics[key]) >= 1e9:
                metrics[key] = f"{metrics[key]/1e9:.2f}B"
            elif abs(metrics[key]) >= 1e6:
                metrics[key] = f"{metrics[key]/1e6:.2f}M"
    
    # Format percentages
    for key in ["Profit Margin", "ROE"]:
        if isinstance(metrics[key], float):
            metrics[key] = f"{metrics[key]:.2%}"
    
    # Round floating point numbers
    for key, value in metrics.items():
        if isinstance(value, float):
            metrics[key] = round(value, 2)
    
    return metrics
# Helper functions for DCF model

def get_risk_free_rate():
    try:
        treasury_ticker = "^TNX"  # 10-year Treasury Yield
        treasury_data = yf.Ticker(treasury_ticker).history(period="1d")
        return treasury_data['Close'].iloc[-1] / 100  # Convert to decimal
    except:
        return 0.035  # Default to 3.5% if unable to fetch
    
@st.cache_data(ttl=3600)
def get_financial_data(ticker):
    """Get financial data with caching"""
    try:
        stock = yf.Ticker(ticker)
        financials = {}
        
        # Balance sheet data
        balance_sheet = stock.balance_sheet
        financials['total_debt'] = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
        financials['cash'] = balance_sheet.loc['Cash Financial'].iloc[0] if 'Cash Financial' in balance_sheet.index else 0
        financials['cash_equivalents'] = balance_sheet.loc['Cash Equivalents'].iloc[0] if 'Cash Equivalents' in balance_sheet.index else 0
        financials['cash_and_cash_equivalents'] = balance_sheet.loc['Cash Cash Equivalents And Short Term Investments'].iloc[0] if 'Cash Cash Equivalents And Short Term Investments' in balance_sheet.index else 0
        financials['total_equity'] = balance_sheet.loc['Common Stock Equity'].iloc[0] if 'Common Stock Equity' in balance_sheet.index else 0
        financials['net_debt'] = balance_sheet.loc['Net Debt'].iloc[0] if 'Net Debt' in balance_sheet.index else 0
        financials['share_issued'] = stock.info.get("sharesOutstanding", "N/A")
        
        # Income statement data
        income_stmt = stock.financials
        financials['interest_expense'] = abs(income_stmt.loc['Interest Expense'].iloc[0]) if 'Interest Expense' in income_stmt.index else 0
        financials['income_tax'] = income_stmt.loc['Tax Provision'].iloc[0] if 'Tax Provision' in income_stmt.index else 0
        financials['net_income'] = income_stmt.loc['Net Income'].iloc[0] if 'Net Income' in income_stmt.index else 0
        financials['pre_tax_income'] = income_stmt.loc['Pretax Income'].iloc[0] if 'Pretax Income' in income_stmt.index else (financials['net_income'] + financials['income_tax'])
        
        # Cash flow statement data
        cash_flow = stock.cashflow
        if 'Free Cash Flow' in cash_flow.index:
            financials['fcf_latest'] = cash_flow.loc['Free Cash Flow'].iloc[0]
            financials['fcf_1years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[1]
            financials['fcf_2years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[2]
            financials['fcf_3years_ago'] = cash_flow.loc['Free Cash Flow'].iloc[3] if len(cash_flow.columns) > 3 else None
        else:
            operating_cash_flow = cash_flow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cash_flow.index else 0
            capital_expenditures = abs(cash_flow.loc['Capital Expenditure'].iloc[0]) if 'Capital Expenditure' in cash_flow.index else 0
            financials['fcf_latest'] = operating_cash_flow - capital_expenditures
            financials['fcf_3years_ago'] = None

        financials['shares_outstanding'] = stock.info.get('sharesOutstanding')
        financials['market_cap'] = stock.info.get('marketCap')
        
        return financials
    except Exception as e:
        st.error(f"Error fetching financial data: {str(e)}")
        return None
    
def calculate_wacc(financials, risk_free_rate, market_risk_premium, beta):
    # Cost of Equity
    cost_of_equity = risk_free_rate + beta * market_risk_premium/100
    
    # Cost of Debt
    if financials['total_debt'] != 0 and financials['interest_expense'] != 0:
        cost_of_debt = financials['interest_expense'] / financials['total_debt']
    else:
        cost_of_debt = risk_free_rate
    
    # Tax Rate
    pre_tax_income = financials.get('pre_tax_income', financials['net_income'] + financials['income_tax'])
    if pre_tax_income != 0:
        tax_rate = financials['income_tax'] / pre_tax_income
    else:
        tax_rate = 0.30  # Assume a default tax rate of 30%
    
    # Weights
    total_capital = financials['total_debt'] + financials['total_equity']
    weight_of_debt = financials['total_debt'] / total_capital
    weight_of_equity = financials['total_equity'] / total_capital
    
    # WACC
    wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * cost_of_debt * (1 - tax_rate))
    
    return wacc

def calculate_fcf_growth_rate(financials):
    fcf_latest = financials['fcf_latest']
    fcf_1year_ago = financials['fcf_1years_ago']
    fcf_2years_ago = financials['fcf_2years_ago']
    fcf_3years_ago = financials['fcf_3years_ago']

    if fcf_latest <= 0 or all(fcf <= 0 for fcf in [fcf_1year_ago, fcf_2years_ago, fcf_3years_ago] if fcf is not None):
        return None, "Growth rate cannot be estimated due to negative FCF"

    if fcf_3years_ago is not None and fcf_3years_ago > 0:
        return (fcf_latest / fcf_3years_ago) ** (1/3) - 1, None
    elif fcf_2years_ago is not None and fcf_2years_ago > 0:
        return (fcf_latest / fcf_2years_ago) ** (1/2) - 1, None
    elif fcf_1year_ago is not None and fcf_1year_ago > 0:
        return (fcf_latest / fcf_1year_ago) - 1, None
    else:
        return None, "Growth rate cannot be estimated due to negative FCF"


def calculate_excess_return_fair_value(financials, cost_of_equity, terminal_growth_rate):
    try:
        book_value = financials['total_equity']
        net_income = financials['net_income']
        shares_outstanding = financials['share_issued']

        roe = net_income / book_value
        excess_return = (roe - cost_of_equity) * book_value
        terminal_value = excess_return * (1 + terminal_growth_rate) / (cost_of_equity - terminal_growth_rate)
        equity_value = book_value + terminal_value
        fair_value = equity_value / shares_outstanding

        return fair_value, None
    except Exception as e:
        return None, f"Error in excess return calculation: {str(e)}"

def calculate_dcf_valuation(financials, market_risk_premium, terminal_growth_rate, risk_free_rate, high_growth_period, current_price):
    """Calculate DCF valuation with error handling"""
    try:
        if not financials:
            return None, "No financial data available"
            
        stock = yf.Ticker(st.session_state.formatted_ticker)
        beta = float(stock.info.get('beta', 1))
        
        if isinstance(financials['total_equity'], (int, float)) and financials['total_equity'] != 0:
            roe = financials['net_income'] / financials['total_equity']
        else:
            roe = 0
        
        cost_of_equity = risk_free_rate/100 + beta * (market_risk_premium/100)
        
        if isinstance(financials['total_debt'], (int, float)) and isinstance(financials['interest_expense'], (int, float)) and financials['total_debt'] != 0:
            cost_of_debt = financials['interest_expense'] / financials['total_debt']
        else:
            cost_of_debt = risk_free_rate/100
        
        if isinstance(financials['pre_tax_income'], (int, float)) and financials['pre_tax_income'] != 0:
            tax_rate = financials['income_tax'] / financials['pre_tax_income']
        else:
            tax_rate = 0.21
        
        total_capital = financials['total_debt'] + financials['total_equity']
        if total_capital != 0:
            weight_of_debt = financials['total_debt'] / total_capital
            weight_of_equity = financials['total_equity'] / total_capital
        else:
            weight_of_debt = 0
            weight_of_equity = 1
        
        wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * cost_of_debt * (1 - tax_rate))
        
        sector = metrics.get("Sector", "Unknown") if metrics else "Unknown"
        
        if sector == 'Financial Services':
            fair_value, error_message = calculate_excess_return_fair_value(
                financials,
                cost_of_equity,
                terminal_growth_rate/100
            )
            valuation_method = "Excess Return Model (for Financial company)"
        else:
            fair_value, error_message = calculate_dcf_fair_value(
                financials,
                wacc,
                terminal_growth_rate/100,
                high_growth_period,
                current_price
            )
            valuation_method = "Discounted Cash Flow (DCF) Model"
            
        return {
            'fair_value': fair_value,
            'error_message': error_message,
            'valuation_method': valuation_method,
            'wacc': wacc,
            'beta': beta,
            'roe': roe,
            'cost_of_equity': cost_of_equity,
            'cost_of_debt': cost_of_debt,
            'weight_of_debt': weight_of_debt,
            'weight_of_equity': weight_of_equity
        }
    except Exception as e:
        return None, f"Error in DCF calculation: {str(e)}"

def main():
    st.title("Stock Fundamentals with Key Levels and DCF Valuation by JC")

    col1, col2 = st.columns([1, 4])

    with col1:
        ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
        knockout_name = st.radio("Choose name for Knock-out Price:", ("Knock-out Price", "Upper Window"))
        strike_name = st.radio("Choose name for Strike Price:", ("Strike Price", "Lower Window"))
        
        knockout_pct = st.number_input(f"{knockout_name} %:", value=0.0)
        strike_pct = st.number_input(f"{strike_name} %:", value=0.0)
        airbag_pct = st.number_input("Airbag Price %:", value=0.0)
               
        refresh = st.button("Refresh Data")

        # DCF Model Inputs
        st.markdown("### DCF Model Inputs")
        
        def on_dcf_input_change():
            st.session_state.dcf_update = True

        market_risk_premium = st.number_input(
            "Market Risk Premium (%):",
            value=st.session_state.market_risk_premium,
            step=0.1,
            on_change=on_dcf_input_change,
            key='mrp_input'
        )

        terminal_growth_rate = st.number_input(
            "Terminal Growth Rate (%):",
            value=st.session_state.terminal_growth_rate,
            step=0.1,
            on_change=on_dcf_input_change,
            key='tgr_input'
        )

        if st.session_state.risk_free_rate is None:
            st.session_state.risk_free_rate = get_risk_free_rate()

        risk_free_rate = st.number_input(
            "Risk-Free Rate (%):",
            value=st.session_state.risk_free_rate,
            step=0.01,
            on_change=on_dcf_input_change,
            key='rfr_input'
        )

        high_growth_period = st.number_input(
            "High Growth Period (years):",
            value=st.session_state.high_growth_period,
            step=1,
            min_value=1,
            on_change=on_dcf_input_change,
            key='hgp_input'
        )

        # Update session state values
        st.session_state.market_risk_premium = market_risk_premium
        st.session_state.terminal_growth_rate = terminal_growth_rate
        st.session_state.risk_free_rate = risk_free_rate
        st.session_state.high_growth_period = high_growth_period

    try:
        formatted_ticker = format_ticker(ticker)
    except Exception as e:
        st.error(f"Error formatting ticker: {str(e)}")
        return

    if 'formatted_ticker' not in st.session_state or ticker != st.session_state.formatted_ticker or refresh:
        st.session_state.formatted_ticker = format_ticker(ticker)
        st.session_state.dcf_update = True
        try:
            with st.spinner('Fetching stock data...'):
                st.session_state.data = get_stock_data(st.session_state.formatted_ticker)
            if st.session_state.data is not None:
                st.success(f"Data fetched successfully for {st.session_state.formatted_ticker}")

                with st.spinner('Fetching market data...'):
                    constituents, index_name = get_index_constituents(ticker)
                    if constituents:
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
            else:
                st.error("Failed to fetch stock data")

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

            with col2:
                st.markdown("<h3>Financial Metrics & Data from Yahoo Finance:</h3>", unsafe_allow_html=True)
                try:
                    with st.spinner('Fetching financial metrics...'):
                        metrics = get_financial_metrics(st.session_state.formatted_ticker)
                    if metrics:
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

                # Valuation section
                if st.session_state.dcf_update:
                    st.markdown(f"<h3>Fair Value Calculation - {ticker}</h3>", unsafe_allow_html=True)
                    try:
                        with st.spinner('Calculating valuation...'):
                            financials = get_financial_data(st.session_state.formatted_ticker)
                            if financials:
                                valuation_result = calculate_dcf_valuation(
                                    financials,
                                    market_risk_premium,
                                    terminal_growth_rate,
                                    risk_free_rate,
                                    high_growth_period,
                                    current_price
                                )
                                
                                if isinstance(valuation_result, tuple):
                                    _, error_message = valuation_result
                                    st.error(error_message)
                                else:
                                    st.session_state.valuation_result = valuation_result
                                    st.session_state.dcf_update = False
                            else:
                                st.error("Failed to fetch financial data")
                    except Exception as e:
                        st.error(f"Error calculating valuation: {str(e)}")
                
                if hasattr(st.session_state, 'valuation_result'):
                    display_valuation_results(
                        st.session_state.valuation_result,
                        current_price,
                        st.session_state.industry_averages if hasattr(st.session_state, 'industry_averages') else None
                    )

        except Exception as e:
            st.error(f"Error processing data: {str(e)}")
            st.write("Debug information:")
            st.write(f"Data shape: {st.session_state.data.shape}")
            st.write(f"Data columns: {st.session_state.data.columns}")
            st.write(f"Data head:\n{st.session_state.data.head()}")
    else:
        st.warning("No data available. Please check the ticker symbol and try again.")

if __name__ == "__main__":
    main()
