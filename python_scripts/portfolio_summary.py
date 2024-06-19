# yfinance Python library to download market data from Yahoo!Ⓡ finance, https://github.com/ranaroussi/yfinance
import yfinance as yf
# PyPortfolioOpt library for portfolio optimisation, https://pyportfolioopt.readthedocs.io
from pypfopt import risk_models, expected_returns, EfficientFrontier, EfficientSemivariance, DiscreteAllocation
import pandas as pd
from collections import OrderedDict
from datetime import datetime, timedelta

# ====== Prepare the dataframe ==========

selected_parameters_df = pd.DataFrame(_arg1)

# Convert the Portfolio_value column to a variable
portfolio_value = selected_parameters_df['Portfolio_value'].copy()[0]

# Convert the Portfolio_value column to a variable
target_return = selected_parameters_df['Target_return'].copy()[0]

# Drop the Portfolio_value column from the DataFrame
selected_companies_df = selected_parameters_df.drop(columns=['Portfolio_value', 'Target_return'], inplace=False)

# ====== Get daily adjusted prices for the selected list of tickers ============

# Set the list of stocks to get data for. 
# Select the row you want to convert 
row = selected_companies_df.iloc[0] 

# Convert the row to a list
equities = row.tolist()

# Get the start date of the historical period: the first date when all selectedtickers were traiding. 
# This date shoudl b enot longer than 5 years away today

# Function to get the first trading date for a given ticker
def get_first_trading_date(ticker):
    epoch = yf.Ticker(ticker).info['firstTradeDateEpochUtc']
    first_trade_date = pd.to_datetime(epoch, unit='s', utc=True).strftime('%Y-%m-%d')
    return first_trade_date

# Retrieve the first trading dates for all tickers
first_trading_dates = {ticker: get_first_trading_date(ticker) for ticker in equities}

# Find the latest first trading date
latest_first_trading_date = max(first_trading_dates.values())

# Ensure the latest first trading date is not more than 5 years in the past
latest_date = datetime.strptime(latest_first_trading_date, '%Y-%m-%d')
five_years_ago = datetime.utcnow() - timedelta(days=5*365)

# Check if the latest date is within the past 5 years
if latest_date > five_years_ago:
    start_date = latest_date.strftime('%Y-%m-%d')
else:
    start_date = five_years_ago.strftime('%Y-%m-%d')

# Get historical data for selected tickers. 
today = datetime.today().strftime('%Y-%m-%d')
full_data = yf.download(equities, start=start_date, end=today)

# Keep only daily adjusted close prices for every stock. Reset the index to give columns correct names
full_data_filtered = full_data['Adj Close']

# Flatten multiindex
daily_adj_prices_df = pd.DataFrame(full_data_filtered.to_records())

# Convert Date column to a string type
daily_adj_prices_df['Date'] = daily_adj_prices_df['Date'].astype(str)

# ===== Mean-variance portfolio ===============

# ===== Calculate main variables ==============

# Make Date column into index. False to not replace the original df stracture
adjusted_close_df = daily_adj_prices_df.set_index('Date', inplace=False)

# Calculate mean daily historical returns
# frequency: number of time periods in a year; 252 (the number of trading days in a year)
# https://pyportfolioopt.readthedocs.io/en/latest/ExpectedReturns.html
mu = expected_returns.mean_historical_return(adjusted_close_df,
                                                returns_data=False,
                                                compounding=True,
                                                frequency=252)

# Covariance matrix
# https://pyportfolioopt.readthedocs.io/en/latest/RiskModels.html
# "Mean-variance optimisation (MVO) requires a good risk model, i.e a good estimator of covariance. 
# The sample covariance is the default choice, but often has coefficients with extreme errors which are
# particularly dangerous in MVO because the optimiser is likely to make large allocations based on these coefficients.
# One possible improvement is to move extreme values towards the centre, in a process called shrinkage." 
# (https://reasonabledeviations.com/notes/papers/ledoit_wolf_covariance/)
S = risk_models.CovarianceShrinkage(adjusted_close_df,
                                    returns_data=False,
                                    frequency=252).ledoit_wolf()

# 10 year Treasury rate, as of 30 April 2021
# https://www.treasury.gov/resource-center/data-chart-center/interest-rates/pages/textview.aspx?data=yield
rate = 0.0165

# Inflation rate as of 13 April 2021
# https://tradingeconomics.com/united-states/inflation-cpi
inflation = 0.026

# Calculate the risk free rate (rfr) of borrowing/lending.
#https://www.investopedia.com/terms/r/risk-freerate.asp
rfr = rate - inflation        

# Calculate Efficient Frontier
ef = EfficientFrontier(mu,S)

# Calculate weights for Mean-variance portfolio
weights_max_sharpe = ef.max_sharpe(risk_free_rate=rfr)
cleaned_weights_max_sharpe = ef.clean_weights()

# ====== Mean-variance portfolio summary ===============

# Print portfolio summary and create new variables for each indicator
(expected_return, annual_volatility,sharpe_ratio) = ef.portfolio_performance(verbose=False)

#Create a dictionary with values and names of metrics, then convert it to a dataframe
summary = {'Expected annual return':expected_return,
            'Annual volatility':annual_volatility,
            'Sharpe Ratio':sharpe_ratio}

# Create a dataframe with portfolio summary that will be brought to Tableau
portfolio_summary_sharpe = pd.DataFrame.from_dict(summary,orient='index').reset_index().rename(columns={'index':'Metric',0:'Value'})

# Adding a column for the Method; True is to allow duplicates
portfolio_summary_sharpe.insert(0,'Method','Max Sharpe', True)

# ====== Mean-semivariance portfolio ==========
# ===== Calculate main variables ==============

# Mean-semivariance portfolio (risk is not important, maximising the ups)
# Calculate daily historical returns form daily prices
historical_returns = expected_returns.returns_from_prices(adjusted_close_df)

# Calculate Efficient semivariance
# frequency: number of time periods in a year; 252 (the number of trading days in a year)
es = EfficientSemivariance(mu,historical_returns,frequency=252,verbose=True)

# Efficient_return takes the desired return of the resulting portfolio.
# If when running the code you get a Solver error, try lowering the return value below.
es.efficient_return(target_return)

# Calculate clean weights for the Mean-semivariance portfolio
weights_es = es.clean_weights()

# ====== Mean-semivariance portfolio summary =========

# Print portfolio summary
# https://pyportfolioopt.readthedocs.io/en/latest/GeneralEfficientFrontier.html
# Create new variables for each indicator
(expected_return, semivariance,sortino_ratio) = es.portfolio_performance(verbose=False)

#Create a dictionary with values and names of metrics. Then convert it into a dataframe
summary_es = {'Expected annual return':expected_return,
                'Semivariance':semivariance,
                'Sortino Ratio':sortino_ratio}

# Create a dataframe with portfolio summary for the Mean-semivariance portfolio
#that will be brought to Tableau
portfolio_summary_es = pd.DataFrame.from_dict(summary_es,orient='index').reset_index().rename(columns={'index':'Metric',0:'Value'})

# Adding a column for the Method; True is to allow duplicates
portfolio_summary_es.insert(0,'Method','Efficient semivariance', True)

# ====== Combine dataframes ===============
# Append dataframes with portfolio summary for both methods
portfolio_summary_combined = pd.concat([portfolio_summary_sharpe, portfolio_summary_es])

return portfolio_summary_combined.to_dict(orient='list')