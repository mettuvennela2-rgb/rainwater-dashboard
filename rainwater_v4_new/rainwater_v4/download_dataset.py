'''Downloads a REAL daily weather dataset from NASA POWER and saves it as a CSV
that you can upload straight into the dashboard.

Usage:
    python download_dataset.py                          (Hyderabad)
    python download_dataset.py 12.97 77.59 Bengaluru    (any place: latitude longitude name)

Needs internet. Takes about 1 minute. Data: 2000-01-01 up to a few days ago.'''
import sys
import numpy as np, pandas as pd, requests

lat = float(sys.argv[1]) if len(sys.argv) >= 3 else 17.385
lon = float(sys.argv[2]) if len(sys.argv) >= 3 else 78.487
city = sys.argv[3] if len(sys.argv) >= 4 else 'Hyderabad'

URL = 'https://power.larc.nasa.gov/api/temporal/daily/point'
# 17 daily variables (PRECTOTCORR = rainfall in mm/day)
PARAMS = ['PRECTOTCORR', 'T2M', 'T2M_MAX', 'T2M_MIN', 'T2MDEW', 'RH2M', 'QV2M', 'WS2M', 'WS10M', 'PS',
          'ALLSKY_SFC_SW_DWN', 'TOA_SW_DWN', 'CLOUD_AMT', 'GWETTOP', 'GWETROOT', 'GWETPROF', 'EVPTRNS']


def fetch(params, end):
    q = {'parameters': ','.join(params), 'community': 'AG', 'longitude': lon, 'latitude': lat,
         'start': '20000101', 'end': end, 'format': 'JSON'}
    r = requests.get(URL, params=q, timeout=180)
    r.raise_for_status()
    return pd.DataFrame(r.json()['properties']['parameter'])


raw = None
for lag_days in (10, 30):                      # newest data first; fall back to an older end date
    end = (pd.Timestamp.today() - pd.Timedelta(days=lag_days)).strftime('%Y%m%d')
    print('Downloading NASA POWER data for', city, 'up to', end, '...')
    try:
        raw = fetch(PARAMS, end)
        break
    except Exception as e:
        print('  full request failed (' + str(e)[:80] + '), trying one variable at a time...')
        parts = []
        for p in PARAMS:
            try:
                parts.append(fetch([p], end))
            except Exception:
                print('   skipped', p)
        if parts:
            raw = pd.concat(parts, axis=1)
            break

if raw is None or 'PRECTOTCORR' not in raw.columns:
    sys.exit('Download failed. Check your internet and run the script again.')

raw.index = pd.to_datetime(raw.index, format='%Y%m%d')
raw = raw.replace(-999, np.nan).rename(columns={'PRECTOTCORR': 'rainfall_mm'})
raw.index.name = 'date'
name = city.lower().replace(' ', '_') + '_daily_dataset.csv'
raw.to_csv(name)
print()
print('Saved:', name)
print('Rows:', len(raw), '| from', raw.index[0].date(), 'to', raw.index[-1].date())
print('Columns (%d):' % raw.shape[1], ', '.join(raw.columns))
print('Now upload this file in the dashboard.')
