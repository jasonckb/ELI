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

def get_financial_metrics(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    metrics = {
        "Sector": info.get("sector", "N/A"),
        "Industry": info.get("industry", "N/A"),
        "Market Cap": info.get("marketCap", "N/A"),
        "Outstanding Shares": info.get("impliedSharesOutstanding", "N/A"),       
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
    

def get_financial_data(ticker):
    stock = yf.Ticker(ticker)
    financials = {}
    
    # Balance sheet data
    balance_sheet = stock.balance_sheet
    financials['total_debt'] = balance_sheet.loc['Total Debt'].iloc[0] if 'Total Debt' in balance_sheet.index else 0
    financials['cash'] = balance_sheet.loc['Cash Financial'].iloc[0] if 'Cash Financial' in balance_sheet.index else 0
    financials['cash_equivalents'] = balance_sheet.loc['Cash Equivalents'].iloc[0] if 'Cash Equivalents' in balance_sheet.index else 0
    financials['cash_and_cash_equivalents'] = balance_sheet.loc['Cash Cash Equivalents And Short Term Investments'].iloc[0] if 'Cash Cash Equivalents And Short Term Investments' in balance_sheet.index else 0
    #financials['cash_and_cash_equivalents'] = financials['cash'] + financials['cash_equivalents']
    financials['total_equity'] = balance_sheet.loc['Common Stock Equity'].iloc[0] if 'Common Stock Equity' in balance_sheet.index else 0
    financials['net_debt'] = balance_sheet.loc['Net Debt'].iloc[0] if 'Net Debt' in balance_sheet.index else 0
    financials['share_issued'] = balance_sheet.loc['Share Issued'].iloc[0] if 'Share Issued' in balance_sheet.index else 0
    
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
        # If Free Cash Flow is not available, calculate it
        operating_cash_flow = cash_flow.loc['Operating Cash Flow'].iloc[0] if 'Operating Cash Flow' in cash_flow.index else 0
        capital_expenditures = abs(cash_flow.loc['Capital Expenditure'].iloc[0]) if 'Capital Expenditure' in cash_flow.index else 0
        financials['fcf_latest'] = operating_cash_flow - capital_expenditures
        financials['fcf_3years_ago'] = None  # We don't have enough data to calculate this

    # Additional info
    financials['shares_outstanding'] = stock.info.get('sharesOutstanding')
    financials['market_cap'] = stock.info.get('marketCap')
    
    return financials
    
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

def calculate_dcf_fair_value(financials, wacc, terminal_growth_rate, high_growth_period, current_price):
    fcf_growth_rate, error_message = calculate_fcf_growth_rate(financials)
    
    if error_message:
        return None, error_message
    
    fcf = financials['fcf_latest']
    pv_fcf = 0
    
    # High growth period
    for i in range(1, high_growth_period + 1):
        fcf *= (1 + fcf_growth_rate)
        pv_fcf += fcf / ((1 + wacc) ** i)
    
    # Terminal value
    terminal_value = fcf * (1 + terminal_growth_rate) / (wacc - terminal_growth_rate)
    pv_terminal_value = terminal_value / ((1 + wacc) ** high_growth_period)
    
    # Enterprise Value
    enterprise_value = pv_fcf + pv_terminal_value
    
    # Equity Value
    equity_value = enterprise_value - financials['total_debt'] + financials.get('cash_and_cash_equivalents', 0)
    
    # Shares outstanding
    shares_outstanding = financials['share_issued'] #financials.get('shares_outstanding')
    if shares_outstanding is None:
        if current_price <= 0:
            return None, "Invalid current price for calculating shares outstanding"
        shares_outstanding = equity_value / current_price
    
    # Fair value per share
    fair_value = equity_value / shares_outstanding
    
    return fair_value, None

def main():
    st.title("Stock Fundamentals with Key Levels and DCF Valuation by JC")

    # Create two columns for layout
    col1, col2 = st.columns([1, 4])

    # Sidebar inputs (now in the first column)
    with col1:
        ticker = st.text_input("Enter Stock Ticker:", value="AAPL")
        
        knockout_name = st.radio("Choose name for Knock-out Price:", ("Knock-out Price", "Upper Window"))
        strike_name = st.radio("Choose name for Strike Price:", ("Strike Price", "Lower Window"))
        
        knockout_pct = st.number_input(f"{knockout_name} %:", value=0.0)
        strike_pct = st.number_input(f"{strike_name} %:", value=0.0)
        airbag_pct = st.number_input("Airbag Price %:", value=0.0)
               
        refresh = st.button("Refresh Data")

    if 'formatted_ticker' not in st.session_state or ticker != st.session_state.formatted_ticker or refresh:
        st.session_state.formatted_ticker = format_ticker(ticker)
        try:
            st.session_state.data = get_stock_data(st.session_state.formatted_ticker)
            st.success(f"Data fetched successfully for {st.session_state.formatted_ticker}")
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

                # DCF Model Inputs
                st.markdown("### DCF Model Inputs")
                market_risk_premium = st.number_input("Market Risk Premium (%):", value=8.5, step=0.1)
                terminal_growth_rate = st.number_input("Terminal Growth Rate (%):", value=3.0, step=0.1)
                risk_free_rate = st.number_input("Risk-Free Rate (%):", value=get_risk_free_rate(), step=0.01)
                high_growth_period = st.number_input("High Growth Period (years):", value=5, step=1, min_value=1)

            with col2:
                st.markdown("<h3>Financial Metrics & Data from Yahoo Finance:</h3>", unsafe_allow_html=True)
                try:
                    metrics = get_financial_metrics(st.session_state.formatted_ticker)
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

                st.markdown("<h3>Latest News:</h3>", unsafe_allow_html=True)
                st.info(f"You can try visiting this URL directly for news: https://finance.yahoo.com/quote/{st.session_state.formatted_ticker}/news/")
                st.markdown("<h3>Analyst Ratings:</h3>", unsafe_allow_html=True)
                try:
                    stock = yf.Ticker(st.session_state.formatted_ticker)
                    
                    if not stock.recommendations_summary.empty:
                        st.subheader("Recommendation Summary")
                        summary = stock.recommendations_summary.set_index('period')

                        col1, col2 = st.columns(2)

                        with col1:
                            fig_summary = go.Figure()
                            categories = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
                            colors = ['darkgreen', 'lightgreen', 'gray', 'pink', 'red']
                            period_labels = {
                                '0m': 'Current Month', '-1m': '1 Month Ago',
                                '-2m': '2 Months Ago', '-3m': '3 Months Ago'
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
                                legend_title="Recommendation Type",
                                height=400,
                                margin=dict(l=50, r=50, t=50, b=70)
                            )

                            st.plotly_chart(fig_summary, use_container_width=True)

                            # Add rating summary below the chart
                            latest = summary.iloc[0]
                            st.markdown("<div style='border:1px solid #cccccc; padding:5px; font-size:0.8em;'>", unsafe_allow_html=True)
                            st.markdown("<p style='text-align:center; font-weight:bold; margin-bottom:5px;'>Current Month's Rating</p>", unsafe_allow_html=True)
                            st.markdown(f"""
                                <table width="100%">
                                    <tr>
                                        <td><b>Strong Buy:</b> {latest['strongBuy']}</td>
                                        <td><b>Buy:</b> {latest['buy']}</td>
                                        <td><b>Hold:</b> {latest['hold']}</td>
                                        <td><b>Sell:</b> {latest['sell']}</td>
                                        <td><b>Strong Sell:</b> {latest['strongSell']}</td>
                                    </tr>
                                </table>
                                """, unsafe_allow_html=True)
                            st.markdown("</div>", unsafe_allow_html=True)

                        with col2:
                            price_targets = stock.info
                            current_price = price_targets.get('currentPrice', 0)
                            target_low = price_targets.get('targetLowPrice', 0)
                            target_mean = price_targets.get('targetMeanPrice', 0)
                            target_high = price_targets.get('targetHighPrice', 0)

                            fig_targets = go.Figure()

                            fig_targets.add_trace(go.Indicator(
                                mode="number+gauge+delta",
                                value=current_price,
                                delta={'reference': target_mean, 'position': "top"},
                                domain={'x': [0, 1], 'y': [0.25, 1]},
                                title={'text': "Price Target"},
                                gauge={
                                    'axis': {'range': [None, target_high], 'tickwidth': 1},
                                    'bar': {'color': "darkgray"},
                                    'steps': [
                                        {'range': [0, target_low], 'color': "red"},
                                        {'range': [target_low, target_high], 'color': "lightgreen"}
                                    ],
                                    'threshold': {
                                        'line': {'color': "darkgreen", 'width': 4},
                                        'thickness': 0.75,
                                        'value': target_mean
                                    }
                                }
                            ))

                            fig_targets.update_layout(
                                title="Analyst Price Targets",
                                height=500,
                                margin=dict(l=50, r=50, t=50, b=70),
                            )

                            annotation_text = (
                                f"Green Zone: Target range ${target_low:.2f} - ${target_high:.2f}<br>"
                                f"Green Line: Average target @ ${target_mean:.2f}<br>"
                                f"Gray Bar: Current price  @ ${current_price:.2f}"
                            )
                            fig_targets.add_annotation(
                                x=0.5,
                                y=0,
                                xref="paper",
                                yref="paper",
                                text=annotation_text,
                                showarrow=False,
                                font=dict(size=12),
                                align="left",
                                xanchor="center",
                                yanchor="top",
                                bordercolor="black",
                                borderwidth=1,
                                borderpad=10,
                                bgcolor="white",
                            )

                            st.plotly_chart(fig_targets, use_container_width=True)

                except Exception as e:
                    st.error(f"Error fetching analyst ratings: {str(e)}")

                st.markdown("<br>", unsafe_allow_html=True)

                # New section for DCF Model
                st.markdown("<h3>Fair Value by Discounted Cash Flow (DCF) Model: (Not Suitable for Financial & Negative FCF Stock) </h3>", unsafe_allow_html=True)
                try:
                    # Fetch required financial data
                    financials = get_financial_data(st.session_state.formatted_ticker)
                    
                    # Calculate and display WACC components
                    stock = yf.Ticker(st.session_state.formatted_ticker)
                    beta = stock.info.get('beta', 1)  # Default to 1 if beta is not available
                    
                    cost_of_equity = risk_free_rate + beta * (market_risk_premium/100)
                    
                    if financials['total_debt'] != 0 and financials['interest_expense'] != 0:
                        cost_of_debt = financials['interest_expense'] / financials['total_debt']
                    else:
                        cost_of_debt = risk_free_rate
                    
                    if financials['pre_tax_income'] != 0:
                        tax_rate = financials['income_tax'] / financials['pre_tax_income']
                    else:
                        tax_rate = 0.21  # Assume a default corporate tax rate of 21%                    
                    
                    total_capital = financials['total_debt'] + financials['total_equity']
                    if total_capital != 0:
                        weight_of_debt = financials['total_debt'] / total_capital
                        weight_of_equity = financials['total_equity'] / total_capital
                    else:
                        weight_of_debt = 0
                        weight_of_equity = 1                    
                    
                    wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * cost_of_debt * (1 - tax_rate))
                    
                    # Calculate and display FCF Growth Rate
                    fcf_growth_rate, fcf_error = calculate_fcf_growth_rate(financials)
                    
                    # Perform DCF Valuation                    
                    fair_value, error_message = calculate_dcf_fair_value(financials, wacc, terminal_growth_rate/100, high_growth_period, current_price)
                    
                    # Display results                  
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.markdown(f"<p><b>WACC:</b> {wacc:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Risk-free rate:</b> {risk_free_rate:.2%}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Beta:</b> {beta:.2f}</p>", unsafe_allow_html=True)
                        if isinstance(fcf_growth_rate, (int, float)):
                            st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_growth_rate:.2%}</p>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_error}</p>", unsafe_allow_html=True)
                        if error_message:
                            st.markdown(f"<p><b>Fair Value:</b> {error_message}</p>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<p><b>Fair Value:</b> ${fair_value:.2f}</p>", unsafe_allow_html=True)
                        st.markdown(f"<p><b>Current Price:</b> ${current_price:.2f}</p>", unsafe_allow_html=True)

                    with col2:
                        # FCF Trend Chart                        
                        
                        fcf_data = pd.DataFrame({
                            'Year': ['3 years ago', '2 years ago', '1 year ago', 'Latest'],
                            'FCF': [financials['fcf_3years_ago'], financials['fcf_2years_ago'], 
                                    financials['fcf_1years_ago'], financials['fcf_latest']]
                        })
                        
                        # Determine the appropriate scale (B or M) based on the maximum FCF value
                        max_fcf = np.max(np.abs(fcf_data['FCF']))
                        if max_fcf >= 1e9:
                            scale = 1e9
                            scale_label = 'B'
                        else:
                            scale = 1e6
                            scale_label = 'M'
                        
                        # Scale the FCF values
                        fcf_data['FCF_scaled'] = fcf_data['FCF'] / scale
                        
                        fig_fcf = go.Figure()
                        fig_fcf.add_trace(go.Scatter(
                            x=fcf_data['Year'], 
                            y=fcf_data['FCF_scaled'], 
                            mode='lines+markers',
                            text=[f'${value:.2f}{scale_label}' for value in fcf_data['FCF_scaled']],
                            hovertemplate='%{text}<extra></extra>'
                        ))
                        
                        fig_fcf.update_layout(
                            title="Free Cash Flow (FCF) Trend",
                            xaxis_title="Year",
                            yaxis_title=f"FCF (${scale_label})",
                            height=300,
                            width=400,
                            margin=dict(l=0, r=0, t=40, b=0),
                        )
                        
                        fig_fcf.update_yaxes(tickformat=".2f")
                        
                        st.plotly_chart(fig_fcf)

                    with col3:
                        if not error_message and isinstance(fair_value, (int, float)):
                            df = pd.DataFrame({
                                'Type': ['Current Price', 'Fair Value'],
                                'Price': [current_price, fair_value]
                            })
                            
                            diff = fair_value - current_price
                            percentage_dis = (1-current_price / fair_value) * 100
                            percentage_pre = (current_price / fair_value-1) * 100
                            
                            if diff > 0:
                                diff_label = f"Discount by {abs(percentage_dis):.1f}%"
                                color_scheme = ['#FF4B4B', '#00CC96']  # Red for current price, green for fair value
                            else:
                                diff_label = f"Premium by {abs(percentage_pre):.1f}%"
                                color_scheme = ['#00CC96', '#FF4B4B']  # Green for current price, red for fair value
                            
                            fig = go.Figure()
                            
                            max_x = max(fair_value, current_price) * 1.1  # Add 10% padding
                            
                            for i, row in df.iterrows():
                                fig.add_trace(go.Bar(
                                    x=[row['Price']],
                                    y=[row['Type']],
                                    orientation='h',
                                    marker_color=color_scheme[i],
                                    text=[f"${row['Price']:.2f}"],
                                    textposition='auto',
                                    insidetextanchor='middle',
                                    textfont=dict(color='white' if row['Price'] / max_x > 0.3 else 'black')
                                ))
                            
                            fig.update_layout(
                                title=f"Price Comparison<br><sub>{diff_label}</sub>",
                                xaxis_title="Price ($)",
                                yaxis_title="",
                                height=300,
                                width=400,
                                margin=dict(l=0, r=50, t=70, b=0),
                                xaxis=dict(range=[0, max_x]),
                                barmode='group',
                                uniformtext=dict(mode='hide', minsize=8),
                            )
                            
                            for i, row in df.iterrows():
                                if row['Price'] / max_x <= 0.3:
                                    fig.add_annotation(
                                        x=row['Price'],
                                        y=row['Type'],
                                        text=f"${row['Price']:.2f}",
                                        showarrow=False,
                                        xanchor='left',
                                        xshift=5,
                                        font=dict(color='black')
                                    )
                            
                            st.plotly_chart(fig)
                            
                            st.markdown(f"<p><b>Difference with Fair Value:</b> ${diff:.2f}</p>", unsafe_allow_html=True)
                            
                            
                        else:
                            st.markdown("<p>Fair value cannot be estimated due to negative FCF.</p>", unsafe_allow_html=True)
                            if error_message:
                                st.markdown(f"<p><b>Error Details:</b> {error_message}</p>", unsafe_allow_html=True)
                            st.markdown("<p>Please check the input data and ensure all required financial information is available.</p>", unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Error calculating DCF valuation: {str(e)}")
                    st.write("Debug information:")
                    st.write(f"Financials: {financials}")
                    
                
                # New section: Intermediate Data for the Calculation
                st.markdown("<h4>Intermediate Data for the Calculation:</h4>", unsafe_allow_html=True)

                # New function to format large numbers
                def format_large_number(number):
                    if abs(number) >= 1e9:
                        return f"${number/1e9:.2f}B"
                    elif abs(number) >= 1e6:
                        return f"${number/1e6:.2f}M"
                    else:
                        return f"${number:,.2f}"
                    
                # Create 4 columns for intermediate data
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown(f"<p><b>Tax Rate:</b> {tax_rate:.2%}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Cost of Debt:</b> {cost_of_debt:.2%}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Cost of Equity:</b> {cost_of_equity:.2%}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Weight of Debt:</b> {weight_of_debt:.2%}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Weight of Equity:</b> {weight_of_equity:.2%}</p>", unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f"<p><b>Latest FCF:</b> {format_large_number(financials['fcf_latest'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>FCF 1 year ago:</b> {format_large_number(financials['fcf_1years_ago'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>FCF 2 years ago:</b> {format_large_number(financials['fcf_2years_ago'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>FCF 3 years ago:</b> {format_large_number(financials['fcf_3years_ago'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>FCF Growth Rate:</b> {fcf_growth_rate:.2%}</p>", unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f"<p><b>Interest Expense:</b> {format_large_number(financials['interest_expense'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Tax Expense:</b> {format_large_number(financials['income_tax'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Pretax Income:</b> {format_large_number(financials['pre_tax_income'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Total Equity:</b> {format_large_number(financials['total_equity'])}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p><b>Total Debt:</b> {format_large_number(financials['total_debt'])}</p>", unsafe_allow_html=True)
                
                with col4:                    
                    st.markdown(f"<p><b>Cash & Cash Equivalents:</b> {format_large_number(financials['cash_and_cash_equivalents'])}</p>", unsafe_allow_html=True)                    
                    st.markdown(f"<p><b>Shares Outstanding:</b> {format_large_number(financials['share_issued'])}</p>", unsafe_allow_html=True)
                    
                    
                st.markdown("<h3>Latest News:</h3>", unsafe_allow_html=True)
                st.info(f"You can try visiting this URL directly for news: https://finance.yahoo.com/quote/{st.session_state.formatted_ticker}/news/")

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