import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

# ... (previous code remains the same)

st.title("Stock Price Chart with Key Levels")

# Create two columns for layout
col1, col2 = st.columns([1, 3])

# Sidebar inputs (now in the first column)
with col1:
    ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
    strike_pct = st.number_input("Strike Price %:", value=90)
    airbag_pct = st.number_input("Airbag Price %:", value=80)
    knockout_pct = st.number_input("Knock-out Price %:", value=105)
    
    # Add a refresh button
    refresh = st.button("Refresh Data")

# Format ticker if it's a HK stock
formatted_ticker = format_ticker(ticker)

# Initialize data as an empty DataFrame
data = pd.DataFrame()

# Fetch stock data
try:
    if 'data' not in st.session_state or refresh:
        data = get_stock_data(formatted_ticker)
        st.session_state.data = data
    else:
        data = st.session_state.data
except Exception as e:
    st.error(f"Error fetching data: {str(e)}")

if not data.empty:
    try:
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
            try:
                metrics = get_financial_metrics(formatted_ticker)
                for key, value in metrics.items():
                    st.markdown(f"<b>{key}:</b> {value}", unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error fetching financial metrics: {str(e)}")

    except Exception as e:
        st.error(f"Error processing data: {str(e)}")
else:
    st.warning("No data available. Please check the ticker symbol and try again.")