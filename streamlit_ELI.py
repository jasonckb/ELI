import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

# ... (previous code remains the same)

def get_financial_metrics(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    metrics = {
        "Market Cap": info.get("marketCap", "N/A"),
        "Enterprise Value": info.get("enterpriseValue", "N/A"),
        "Trailing P/E": info.get("trailingPE", "N/A"),
        "Forward P/E": info.get("forwardPE", "N/A"),
        "PEG Ratio (5yr expected)": info.get("pegRatio", "N/A"),
        "Price/Sales": info.get("priceToSalesTrailing12Months", "N/A"),
        "Price/Book": info.get("priceToBook", "N/A"),
        "Enterprise Value/Revenue": info.get("enterpriseToRevenue", "N/A"),
        "Enterprise Value/EBITDA": info.get("enterpriseToEbitda", "N/A")
    }
    
    # Format large numbers
    for key in ["Market Cap", "Enterprise Value"]:
        if isinstance(metrics[key], (int, float)):
            metrics[key] = f"{metrics[key]/1e12:.2f}T" if metrics[key] >= 1e12 else f"{metrics[key]/1e9:.2f}B"
    
    # Round floating point numbers
    for key, value in metrics.items():
        if isinstance(value, float):
            metrics[key] = round(value, 2)
    
    return metrics

# ... (rest of the previous code)

# In the main app logic:
if not data.empty:
    current_price = data['Close'].iloc[-1]
    strike_price, airbag_price, knockout_price = calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct)

    # Plot the chart in the second (wider) column
    with col2:
        fig = plot_stock_chart(data, formatted_ticker, strike_price, airbag_price, knockout_price)
        st.plotly_chart(fig, use_container_width=True)

    # Display current price and calculated levels with larger text in the sidebar
    with col1:
        st.markdown(f"<h2>Current Price: {current_price:.2f}</h2>", unsafe_allow_html=True)
        st.markdown(f"<h3>Strike Price ({strike_pct}%): {strike_price:.2f}</h3>", unsafe_allow_html=True)
        st.markdown(f"<h3>Airbag Price ({airbag_pct}%): {airbag_price:.2f}</h3>", unsafe_allow_html=True)
        st.markdown(f"<h3>Knock-out Price ({knockout_pct}%): {knockout_price:.2f}</h3>", unsafe_allow_html=True)
        
        # Add financial metrics
        st.markdown("<h3>Financial Metrics:</h3>", unsafe_allow_html=True)
        metrics = get_financial_metrics(formatted_ticker)
        for key, value in metrics.items():
            st.markdown(f"<b>{key}:</b> {value}", unsafe_allow_html=True)

else:
    st.error("Unable to fetch stock data. Please check the ticker symbol and try again.")