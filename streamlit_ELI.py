import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta

def get_stock_data(ticker, period="1y"):
    stock = yf.Ticker(ticker)
    data = stock.history(period=period)
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
    fig = go.Figure()

    # Candlestick chart
    fig.add_trace(go.Candlestick(
        x=data.index,
        open=data['Open'],
        high=data['High'],
        low=data['Low'],
        close=data['Close'],
        name='Price'
    ))

    # Add price level lines
    fig.add_hline(y=strike_price, line_dash="dash", line_color="blue", annotation_text=f"Strike Price: {strike_price:.2f}")
    fig.add_hline(y=airbag_price, line_dash="dash", line_color="green", annotation_text=f"Airbag Price: {airbag_price:.2f}")
    fig.add_hline(y=knockout_price, line_dash="dash", line_color="red", annotation_text=f"Knock-out Price: {knockout_price:.2f}")

    fig.update_layout(
        title=f"{ticker} Stock Price",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False
    )

    return fig

st.title("Stock Price Chart with Key Levels")

# Sidebar inputs
ticker = st.sidebar.text_input("Enter Stock Ticker:", value="AAPL")
strike_pct = st.sidebar.number_input("Strike Price %:", value=90)
airbag_pct = st.sidebar.number_input("Airbag Price %:", value=80)
knockout_pct = st.sidebar.number_input("Knock-out Price %:", value=105)

# Format ticker if it's a HK stock
formatted_ticker = format_ticker(ticker)

# Fetch stock data
data = get_stock_data(formatted_ticker)

if not data.empty:
    current_price = data['Close'].iloc[-1]
    strike_price, airbag_price, knockout_price = calculate_price_levels(current_price, strike_pct, airbag_pct, knockout_pct)

    # Plot the chart
    fig = plot_stock_chart(data, formatted_ticker, strike_price, airbag_price, knockout_price)
    st.plotly_chart(fig, use_container_width=True)

    # Display current price and calculated levels
    st.write(f"Current Price: {current_price:.2f}")
    st.write(f"Strike Price ({strike_pct}%): {strike_price:.2f}")
    st.write(f"Airbag Price ({airbag_pct}%): {airbag_price:.2f}")
    st.write(f"Knock-out Price ({knockout_pct}%): {knockout_price:.2f}")
else:
    st.error("Unable to fetch stock data. Please check the ticker symbol and try again.")