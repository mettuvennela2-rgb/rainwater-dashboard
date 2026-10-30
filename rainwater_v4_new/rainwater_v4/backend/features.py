import pandas as pd

# W = weekly table (built from daily or weekly data), M = monthly table (built from monthly data)
CFG = {'W': {'lags': [1, 2, 3, 4], 'roll': (4, 12)}, 'M': {'lags': [1, 2, 3, 12], 'roll': (3, 12)}}


def add_features(table, freq='W'):
    '''Lag + rolling + calendar features. Uses past periods only, so there is no data leakage.'''
    c = CFG[freq]
    data = table.copy()
    for col in table.columns:
        for lag in c['lags']:
            data[f'{col}_lag{lag}'] = table[col].shift(lag)
    a, b = c['roll']
    data['rain_roll_short'] = table['rainfall_mm'].shift(1).rolling(a).mean()
    data['rain_roll_long'] = table['rainfall_mm'].shift(1).rolling(b).mean()
    if freq == 'W':
        data['week_of_year'] = data.index.isocalendar().week.astype(int)
    data['month'] = data.index.month
    return data.dropna()


def feature_columns(data):
    return [c for c in data.columns if '_lag' in c or 'roll' in c or c in ('week_of_year', 'month')]


def next_step_features(table, x_cols, freq='W'):
    '''Feature row for the period after the latest data (next week or next month).'''
    c = CFG[freq]
    row = {}
    for col in table.columns:
        for lag in c['lags']:
            row[f'{col}_lag{lag}'] = table[col].iloc[-lag]
    a, b = c['roll']
    row['rain_roll_short'] = table['rainfall_mm'].iloc[-a:].mean()
    row['rain_roll_long'] = table['rainfall_mm'].iloc[-b:].mean()
    nxt = table.index[-1] + (pd.Timedelta(days=7) if freq == 'W' else pd.offsets.MonthEnd(1))
    if freq == 'W':
        row['week_of_year'] = int(nxt.isocalendar().week)
    row['month'] = nxt.month
    return pd.DataFrame([row])[x_cols], nxt
