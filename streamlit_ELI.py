import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

# Set page to wide mode
st.set_page_config(layout="wide")

def get_stock_data(ticker, period="1y"):
    stock = yf.Ticker(ticker)
    data = stock.history(period=period)
    # Remove rows with NaN values (days without data)
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

    # Calculate the position for price annotations
    last_date = data.index[-1]
    annotation_x = last_date + pd.Timedelta(days=2)  # 2 days after the last candle

    # Add price level lines with annotations on the right
    fig.add_hline(y=strike_price, line_dash="dash", line_color="blue")
    fig.add_annotation(x=annotation_x, y=strike_price, text=f"Strike Price: {strike_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=14, color="blue"))

    fig.add_hline(y=airbag_price, line_dash="dash", line_color="green")
    fig.add_annotation(x=annotation_x, y=airbag_price, text=f"Airbag Price: {airbag_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=14, color="green"))

    fig.add_hline(y=knockout_price, line_dash="dash", line_color="orange")
    fig.add_annotation(x=annotation_x, y=knockout_price, text=f"Knock-out Price: {knockout_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=14, color="orange"))

    # Add current price annotation
    current_price = data['Close'].iloc[-1]
    fig.add_annotation(x=annotation_x, y=current_price, text=f"Current Price: {current_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=14, color="black"))

    fig.update_layout(
        title=f"{ticker} Stock Price",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        height=600,  # Adjusted height
        width=800,   # Set a fixed width for the chart
        margin=dict(l=50, r=150, t=50, b=50),  # Increase right margin for annotations
        showlegend=False,
        font=dict(size=14)  # Increase the overall font size
    )

    # Set x-axis to show only trading days and extend range for annotations
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),  # Hide weekends
            dict(values=["2023-12-25", "2024-01-01"])  # Example: hide specific holidays
        ],
        range=[data.index[0], annotation_x]  # Extend x-axis range for annotations
    )

    return fig

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

# Fetch stock data
if 'data' not in st.session_state or refresh:
    data = get_stock_data(formatted_ticker)
    st.session_state.data = data
else:
    data = st.session_state.data

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
else:
    st.error("Unable to fetch stock data. Please check the ticker symbol and try again.")