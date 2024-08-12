import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

# Set page to wide mode
st.set_page_config(layout="wide")

# Function definitions (keep all your previous function definitions here)

def get_stock_data(ticker, period="1y"):
    stock = yf.Ticker(ticker)
    data = stock.history(period=period)
    data = data.dropna()
    return data

def format_ticker(ticker):
    if ticker.isdigit():
        return f"{int(ticker):04d}.HK"
    return ticker

def calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct):
    strike_price = current_price * (strike_pct / 100)
    airbag_price = current_price * (airbag_pct / 100)
    knockout_price = current_price * (knockout_pct / 100)
    return strike_price, airbag_price, knockout_price

def plot_stock_chart(data, ticker, strike_price, airbag_price, knockout_price):
    # Your existing plot_stock_chart function here

def get_financial_metrics(ticker):
    # Your existing get_financial_metrics function here

# Initialize session state
if 'formatted_ticker' not in st.session_state:
    st.session_state.formatted_ticker = ''
if 'data' not in st.session_state:
    st.session_state.data = pd.DataFrame()

# Main app layout
st.title("Stock Price Chart with Key Levels")

# Create two columns for layout
col1, col2 = st.columns([1, 4])

# Sidebar inputs (now in the first column)
with col1:
    ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
    strike_pct = st.number_input("Strike Price %:", value=90)
    airbag_pct = st.number_input("Airbag Price %:", value=80)
    knockout_pct = st.number_input("Knock-out Price %:", value=105)
    
    # Add a refresh button
    refresh = st.button("Refresh Data")

    # Display current price and calculated levels with larger text in the sidebar
    st.markdown("<h3>Price Levels:</h3>", unsafe_allow_html=True)

# Format ticker and fetch data when input changes or refresh is clicked
if ticker != st.session_state.formatted_ticker or refresh:
    st.session_state.formatted_ticker = format_ticker(ticker)
    try:
        st.session_state.data = get_stock_data(st.session_state.formatted_ticker)
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")

# Main logic
if not st.session_state.data.empty:
    try:
        current_price = st.session_state.data['Close'].iloc[-1]
        strike_price, airbag_price, knockout_price = calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct)

        # Display current price and calculated levels in the sidebar
        with col1:
            st.markdown(f"<h4>Current Price: {current_price:.2f}</h4>", unsafe_allow_html=True)
            st.markdown(f"<p>Strike Price ({strike_pct}%): {strike_price:.2f}</p>", unsafe_allow_html=True)
            st.markdown(f"<p>Airbag Price ({airbag_pct}%): {airbag_price:.2f}</p>", unsafe_allow_html=True)
            st.markdown(f"<p>Knock-out Price ({knockout_pct}%): {knockout_price:.2f}</p>", unsafe_allow_html=True)

        # Main chart and data display
        with col2:
            # Add financial metrics above the chart
            st.markdown("<h3>Financial Metrics:</h3>", unsafe_allow_html=True)
            try:
                metrics = get_financial_metrics(st.session_state.formatted_ticker)
                cols = st.columns(3)  # Create 3 columns for metrics display
                for i, (key, value) in enumerate(metrics.items()):
                    cols[i % 3].markdown(f"<b>{key}:</b> {value}", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error fetching financial metrics: {str(e)}")

            # Add some space between metrics and chart
            st.markdown("<br>", unsafe_allow_html=True)

            # Plot the chart
            fig = plot_stock_chart(st.session_state.data, st.session_state.formatted_ticker, strike_price, airbag_price, knockout_price)
            st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
else:
    st.warning("No data available. Please check the ticker symbol and try again.")