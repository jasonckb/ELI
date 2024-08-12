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
        height=600,
        width=800,
        margin=dict(l=50, r=150, t=50, b=50),
        showlegend=False,
        font=dict(size=14)
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