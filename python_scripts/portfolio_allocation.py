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
# This date should be not longer than 5 years away today

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

# ============== Get prices for the first & last day of the period ===============

# Get the prices on the first date in the data set
first_date = pd.DataFrame(daily_adj_prices_df.head(1))
first_date = first_date.melt(id_vars=['Date'],var_name='Ticker', value_name='First price')
first_date = first_date.rename(columns={"Date":"First date"})

# Get the prices on the last date in the data set
last_date = pd.DataFrame(daily_adj_prices_df.tail(1))
last_date = last_date.melt(id_vars=['Date'],var_name='Ticker', value_name='Last price')
last_date = last_date.rename(columns={"Date":"Last date"})

# Merge two data frames together on the Ticker column
minmax_prices = first_date.merge(last_date,how='left',on='Ticker')

# =============================

# Extract column names
columns = daily_adj_prices_df.columns

# Filter out the 'Date' column
tickers = [col for col in columns if col != 'Date']

latest_price = daily_adj_prices_df.iloc[-1]

# Convert latest_prices to pd.Series and ensure all values are numeric, coercing non-numeric values to NaN
latest_prices = pd.Series(latest_price).apply(pd.to_numeric, errors='coerce').dropna()

# ===== Mean-variance portfolio  ===============

# ===== Calculate main variables  ==============

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

# 10 year Treasury rate, as of June 18, 2024
# https://www.treasury.gov/resource-center/data-chart-center/interest-rates/pages/textview.aspx?data=yield
rate = 0.0212

# Inflation rate as of June 2024
# https://tradingeconomics.com/united-states/inflation-cpi
inflation = 0.033

# Calculate the risk free rate (rfr) of borrowing/lending.
#https://www.investopedia.com/terms/r/risk-freerate.asp
rfr = rate - inflation        

# ====== Calculate weights  ===============

# Calculate Efficient Frontier
ef = EfficientFrontier(mu,S)

# Calculate weights for Mean-variance portfolio
weights_max_sharpe = ef.max_sharpe(risk_free_rate=rfr)
cleaned_weights_max_sharpe = ef.clean_weights()

# ====== Calculate allocation  ===============

# Calculate Leftover (in USD) and discrete allocation of shares (no fractional shares) for Mean-variance portfolio
# based on the portfolio value passed from Tableau

# List to store results
results_sharpe = []

# Iterate over the list of tickers and call the function for each ticker
for ticker in tickers:
    allocation_sharpe = DiscreteAllocation(cleaned_weights_max_sharpe,
                                latest_prices,
                                total_portfolio_value=portfolio_value,
                                short_ratio=None)
    alloc_sharpe, leftover_sharpe = allocation_sharpe.lp_portfolio()
    # Check that the ticker exists in the dictionary 
    #(as some tickers might not have any shares allocated and won't appear in the output)
    if ticker in alloc_sharpe:
        shares_sharpe = alloc_sharpe[ticker]
    else:
        shares_sharpe = int(0)
    results_sharpe.append({'Ticker': ticker, 'Shares_sharpe': shares_sharpe})
    
# Convert the results list to a DataFrame
sharpe_allocation_df = pd.DataFrame(results_sharpe)

# Adding a column for the leftover value; True is to allow duplicates
sharpe_allocation_df.insert(2,'Leftover_sharpe',leftover_sharpe, True)


# ====== Mean-semivariance portfolio ======

# ===== Calculate main variables =========


# Mean-semivariance portfolio (risk is not important, maximising the ups)

# Calculate daily historical returns form daily prices

historical_returns = expected_returns.returns_from_prices(adjusted_close_df)

# Calculate Efficient semivariance

# frequency: number of time periods in a year; 252 (the number of trading days in a year)

es = EfficientSemivariance(mu,historical_returns,frequency=252,verbose=True)

# ====== Calculate weights ===============

# Efficient_return takes the desired return of the resulting portfolio.

# If when running the code you get a Solver error, try lowering the return value below.

es.efficient_return(target_return)

# Calculate clean weights for the Mean-semivariance portfolio

weights_es = es.clean_weights()

# ====== Calculate allocation  ===============

# Calculate Leftover (in USD) and discrete allocation of shares (no fractional shares) for Mean-semivariance portfolio
# based on the portfolio value passed from Tableau

# List to store results
results_es = []

# Iterate over the list of tickers and call the function for each ticker
for ticker in tickers:
    allocation_es = DiscreteAllocation(weights_es,
                                latest_prices,
                                total_portfolio_value=portfolio_value,
                                short_ratio=None)
    alloc_es, leftover_es = allocation_es.lp_portfolio()
    # Check that the ticker exists in the dictionary 
    #(as some tickers might not have any shares allocated and won't appear in the output)
    if ticker in alloc_es:
        shares_es = alloc_es[ticker]
    else:
        shares_es = int(0)
    results_es.append({'Ticker': ticker, 'Shares_es': shares_es})
    
# Convert the results list to a DataFrame
es_allocation_df = pd.DataFrame(results_es)

# Adding a column for the leftover value; True is to allow duplicates
es_allocation_df.insert(2,'Leftover_es',leftover_es, True)

# Merge dataframes for both methods on the Ticker column
allocation_combined_df = sharpe_allocation_df.merge(es_allocation_df,how='left',on='Ticker')

# Merge the allocation_combined_df dataframe with the minmax_prices dataframe
final_combined_df = allocation_combined_df.merge(minmax_prices,how='left',on='Ticker')

return final_combined_df.to_dict(orient='list')
