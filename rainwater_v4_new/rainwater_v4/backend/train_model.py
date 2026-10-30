'''Optional: python train_model.py
Downloads the default NASA POWER dataset for Hyderabad and trains the models.
You can skip this and simply upload your own CSV in the dashboard.'''
import json
import numpy as np, pandas as pd, requests, joblib
from pipeline import run_pipeline

END_TS = pd.Timestamp.today() - pd.Timedelta(days=30)   # POWER daily data lags a few days
END = END_TS.strftime('%Y%m%d')
URL = 'https://power.larc.nasa.gov/api/temporal/daily/point'
# NASA POWER (MERRA-2 + CERES), agroclimatology community: 17 daily variables
PARAMS = ['PRECTOTCORR', 'T2M', 'T2M_MAX', 'T2M_MIN', 'T2MDEW', 'RH2M', 'QV2M', 'WS2M', 'WS10M', 'PS',
          'ALLSKY_SFC_SW_DWN', 'TOA_SW_DWN', 'CLOUD_AMT', 'GWETTOP', 'GWETROOT', 'GWETPROF', 'EVPTRNS']


def fetch(params):
    q = {'parameters': ','.join(params), 'community': 'AG', 'longitude': 78.487, 'latitude': 17.385,
         'start': '20000101', 'end': END, 'format': 'JSON'}
    r = requests.get(URL, params=q, timeout=180)
    r.raise_for_status()
    return pd.DataFrame(r.json()['properties']['parameter'])


try:
    raw = fetch(PARAMS)
except Exception as e:
    print('Full request failed, loading one parameter at a time:', e)
    parts = []
    for p in PARAMS:
        try:
            parts.append(fetch([p]))
        except Exception:
            print('  skipped', p)
    raw = pd.concat(parts, axis=1)

raw.index = pd.to_datetime(raw.index, format='%Y%m%d')
raw = raw.replace(-999, np.nan).rename(columns={'PRECTOTCORR': 'rainfall_mm'})
raw.index.name = 'date'
raw.to_csv('daily_data.csv')                    # you can upload this file in the dashboard too
print('Daily rows:', len(raw), '| columns:', list(raw.columns))

art = run_pipeline(raw, 'daily', 'NASA POWER (MERRA-2), Hyderabad', 'default')
for m in art['results']['metrics']:
    print(m)
json.dump(art['results'], open('results.json', 'w'))
joblib.dump(art['rf'], 'rf_model.pkl'); joblib.dump(art['x_cols'], 'x_cols.pkl')
art['table'].to_csv('table_data.csv'); art['daily'].rename('rainfall_mm').to_csv('daily_rain.csv')
print('Saved rf_model.pkl, x_cols.pkl, table_data.csv, daily_rain.csv, results.json, daily_data.csv')
