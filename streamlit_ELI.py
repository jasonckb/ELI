import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

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

    # Calculate EMAs
    ema_20 = calculate_ema(data, 20)
    ema_50 = calculate_ema(data, 50)
    ema_200 = calculate_ema(data, 200)

    # Calculate the position for price annotations
    last_date = data.index[-1]
    annotation_x = last_date + pd.Timedelta(days=2)  # 2 days after the last candle

    # Add price level lines with annotations on the right (only if not zero)
    if strike_price != 0:
        fig.add_hline(y=strike_price, line_dash="dash", line_color="blue")
        fig.add_annotation(x=annotation_x, y=strike_price, text=f"Strike Price: {strike_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="blue"))

    if airbag_price != 0:
        fig.add_hline(y=airbag_price, line_dash="dash", line_color="green")
        fig.add_annotation(x=annotation_x, y=airbag_price, text=f"Airbag Price: {airbag_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="green"))

    if knockout_price != 0:
        fig.add_hline(y=knockout_price, line_dash="dash", line_color="orange")
        fig.add_annotation(x=annotation_x, y=knockout_price, text=f"Knock-out Price: {knockout_price:.2f}",
                           showarrow=False, xanchor="left", font=dict(size=14, color="orange"))

    # Add EMA lines
    fig.add_hline(y=ema_20.iloc[-1], line_dash="dash", line_color="gray", line_width=1)
    fig.add_annotation(x=annotation_x, y=ema_20.iloc[-1], text=f"20 EMA: {ema_20.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_hline(y=ema_50.iloc[-1], line_dash="dash", line_color="gray", line_width=2)
    fig.add_annotation(x=annotation_x, y=ema_50.iloc[-1], text=f"50 EMA: {ema_50.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_hline(y=ema_200.iloc[-1], line_dash="dash", line_color="gray", line_width=3)
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
    fig.add_hline(y=poc_price, line_color="red", line_width=2)
    fig.add_annotation(x=annotation_x, y=poc_price, text=f"POC: {poc_price:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="red"))

    # Add Value Area lines (yellow)
    fig.add_hline(y=value_area_low, line_color="yellow", line_width=2)
    fig.add_annotation(x=annotation_x, y=value_area_low, text=f"VAL: {value_area_low:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="yellow"))

    fig.add_hline(y=value_area_high, line_color="yellow", line_width=2)
    fig.add_annotation(x=annotation_x, y=value_area_high, text=f"VAH: {value_area_high:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="yellow"))

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

def main():
    st.title("Stock Price Chart with Key Levels")

    # Create two columns for layout
    col1, col2 = st.columns([1, 4])

    # Sidebar inputs (now in the first column)
    with col1:
        ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
        strike_pct = st.number_input("Strike Price %:", value=0.0)
        airbag_pct = st.number_input("Airbag Price %:", value=0.0)
        knockout_pct = st.number_input("Knock-out Price %:", value=0.0)
        
        # Add a refresh button
        refresh = st.button("Refresh Data")

        # Display current price and calculated levels with larger text in the sidebar
        st.markdown("<h3>Price Levels:</h3>", unsafe_allow_html=True)

    # Format ticker and fetch data when input changes or refresh is clicked
    if 'formatted_ticker' not in st.session_state or ticker != st.session_state.formatted_ticker or refresh:
        st.session_state.formatted_ticker = format_ticker(ticker)
        try:
            st.session_state.data = get_stock_data(st.session_state.formatted_ticker)
            st.success(f"Data fetched successfully for {st.session_state.formatted_ticker}")
        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")

    # Main logic
    if hasattr(st.session_state, 'data') and not st.session_state.data.empty:
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
                st.markdown("<h3>Stock Chart:</h3>", unsafe_allow_html=True)
                fig = plot_stock_chart(st.session_state.data, st.session_state.formatted_ticker, strike_price, airbag_price, knockout_price)
                st.plotly_chart(fig, use_container_width=True)

                # Display EMA values
                st.markdown("<h3>Exponential Moving Averages:</h3>", unsafe_allow_html=True)
                ema_20 = calculate_ema(st.session_state.data, 20).iloc[-1]
                ema_50 = calculate_ema(st.session_state.data, 50).iloc[-1]
                ema_200 = calculate_ema(st.session_state.data, 200).iloc[-1]
                st.markdown(f"<p>20 EMA: {ema_20:.2f}</p>", unsafe_allow_html=True)
                st.markdown(f"<p>50 EMA: {ema_50:.2f}</p>", unsafe_allow_html=True)
                st.markdown(f"<p>200 EMA: {ema_200:.2f}</p>", unsafe_allow_html=True)

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