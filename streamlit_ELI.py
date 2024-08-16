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

# Set page to wide mode
st.set_page_config(layout="wide")

# Define all the necessary functions here
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
    # Implementation of plot_stock_chart function
    # (This function is quite long, so I'm not including its full implementation here)
    pass

def get_financial_metrics(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    metrics = {
        "Market Cap": info.get("marketCap", "N/A"),       
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
    for key in ["Market Cap", "Net Income", "Revenue"]:
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

def main():
    st.title("Stock Fundamentals with Key Levels by JC")

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
                st.markdown("<h3>Financial Metrics & Data from Yahoo Finance:</h3>", unsafe_allow_html=True)
                try:
                    metrics = get_financial_metrics(st.session_state.formatted_ticker)
                    cols = st.columns(2)  # Create 2 columns for metrics display
                    for i, (key, value) in enumerate(metrics.items()):
                        cols[i % 2].markdown(f"<b>{key}:</b> {value}", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error fetching financial metrics: {str(e)}")

                # Add analyst ratings
                st.markdown("<h3>Analyst Ratings:</h3>", unsafe_allow_html=True)
                try:
                    stock = yf.Ticker(st.session_state.formatted_ticker)
                    
                    if not stock.recommendations_summary.empty:
                        st.subheader("Recommendation Summary")
                        summary = stock.recommendations_summary.set_index('period')

                        # Create a bar chart for the summary
                        fig_summary = go.Figure()
                        categories = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                        colors = ['darkgreen', 'lightgreen', 'gray', 'pink', 'red']

                        # Create a mapping for x-axis labels
                        period_labels = {
                            '0m': 'Current Month',
                            '-1m': '1 Month Ago',
                            '-2m': '2 Months Ago',
                            '-3m': '3 Months Ago'
                        }

                        for category, color in zip(categories, colors):
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
                            legend_title="Recommendation Type"
                        )

                        st.plotly_chart(fig_summary, use_container_width=True)

                        # Display the latest recommendations
                        latest = summary.iloc[0]
                        col1, col2, col3, col4, col5 = st.columns(5)
                        col1.metric("Strong Buy", latest['strongBuy'])
                        col2.metric("Buy", latest['buy'])
                        col3.metric("Hold", latest['hold'])
                        col4.metric("Sell", latest['sell'])
                        col5.metric("Strong Sell", latest['strongSell'])

                    if not stock.recommendations.empty:
                        st.subheader("Recent Analyst Recommendations")
                        recent_recommendations = stock.recommendations.sort_index(ascending=False).head(10)
                        
                        # Ensure 'Date' column is in datetime format
                        recent_recommendations.index = pd.to_datetime(recent_recommendations.index)
                        
                        # Check available columns and use them flexibly
                        available_columns = recent_recommendations.columns
                        
                        firm_column = next((col for col in ['Firm', 'firm', 'Company', 'company'] if col in available_columns), None)
                        to_grade_column = next((col for col in ['To Grade', 'to_grade', 'New Rating', 'new_rating'] if col in available_columns), None)
                        from_grade_column = next((col for col in ['From Grade', 'from_grade', 'Old Rating', 'old_rating'] if col in available_columns), None)
                        
                        if firm_column and to_grade_column:
                            # Create a new DataFrame with the desired columns and format
                            display_recommendations = pd.DataFrame({
                                'Date': recent_recommendations.index.date,
                                'Firm': recent_recommendations[firm_column] if firm_column else 'N/A',
                                'To Grade': recent_recommendations[to_grade_column] if to_grade_column else 'N/A',
                                'From Grade': recent_recommendations[from_grade_column] if from_grade_column else 'N/A',
                                'Action': recent_recommendations.apply(
                                    lambda row: f"{row[from_grade_column]} → {row[to_grade_column]}" 
                                    if from_grade_column and to_grade_column and row[from_grade_column] != row[to_grade_column] 
                                    else "Reiterated", 
                                    axis=1
                                ) if from_grade_column and to_grade_column else 'N/A'
                            })
                            
                            st.dataframe(display_recommendations)
                        else:
                            st.write("Required columns not found in the recommendations data.")
                    
                    if stock.recommendations_summary.empty and stock.recommendations.empty:
                        st.write("No analyst recommendations available.")

                    # Add debug information
                    st.write("Debug information:")
                    st.write(f"Recommendations summary shape: {stock.recommendations_summary.shape if hasattr(stock, 'recommendations_summary') else 'N/A'}")
                    st.write(f"Recommendations shape: {stock.recommendations.shape if hasattr(stock, 'recommendations') else 'N/A'}")
                    st.write("Available columns in recommendations:", stock.recommendations.columns.tolist() if hasattr(stock, 'recommendations') else 'N/A')
                    st.write("First few rows of recommendations:")
                    st.write(stock.recommendations.head() if hasattr(stock, 'recommendations') else 'N/A')

                except Exception as e:
                    st.error(f"Error fetching analyst ratings: {str(e)}")

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

                # Display news
                st.markdown("<h3>Latest News:</h3>", unsafe_allow_html=True)
                st.info(f"You can try visiting this URL directly for news: https://finance.yahoo.com/quote/{st.session_state.formatted_ticker}/news/")

                # Add screenshot button
                # Add screenshot button
                if st.button("Take Screenshot"):
                    try:
                        # Save the figure as a temporary file
                        temp_file = f"{st.session_state.formatted_ticker}_chart.png"
                        pio.write_image(fig, temp_file)
                        
                        # Read the file and create a download button
                        with open(temp_file, "rb") as file:
                            btn = st.download_button(
                                label="Download Chart Screenshot",
                                data=file,
                                file_name=f"{st.session_state.formatted_ticker}_chart.png",
                                mime="image/png"
                            )
                        
                        # Remove the temporary file
                        os.remove(temp_file)
                        
                    except Exception as e:
                        st.error(f"Error generating screenshot: {str(e)}")
                        st.error("If the error persists, please try updating plotly and kaleido: pip install -U plotly kaleido")

        except Exception as e:
            st.error(f"Error processing data: {str(e)}")
            st.write("Debug information:")
            st.write(f"Data shape: {st.session_state.data.shape}")
            st.write(f"Data columns: {st.session_state.data.columns}")
            st.write(f"Data head:\n{st.session_state.data.head()}")
    else:
        st.warning("No data available. Please check the ticker symbol and try again.")

# Run the Streamlit app
if __name__ == "__main__":
    main()