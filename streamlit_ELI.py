import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import pandas as pd

# ... (previous imports and setup remain the same)

def calculate_ema(data, period):
    return data['Close'].ewm(span=period, adjust=False).mean()

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

    # Add EMA lines
    fig.add_hline(y=ema_20.iloc[-1], line_dash="solid", line_color="gray", line_width=1)
    fig.add_annotation(x=annotation_x, y=ema_20.iloc[-1], text=f"20 EMA: {ema_20.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_hline(y=ema_50.iloc[-1], line_dash="solid", line_color="gray", line_width=1)
    fig.add_annotation(x=annotation_x, y=ema_50.iloc[-1], text=f"50 EMA: {ema_50.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

    fig.add_hline(y=ema_200.iloc[-1], line_dash="solid", line_color="gray", line_width=1)
    fig.add_annotation(x=annotation_x, y=ema_200.iloc[-1], text=f"200 EMA: {ema_200.iloc[-1]:.2f}",
                       showarrow=False, xanchor="left", font=dict(size=12, color="gray"))

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

# ... (rest of the code remains the same)

# In the main logic section, after plotting the chart:
with col2:
    # ... (previous code for financial metrics)

    # Plot the chart
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

# ... (rest of the code remains the same)