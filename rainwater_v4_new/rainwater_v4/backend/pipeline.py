'''Shared ML pipeline. Used by train_model.py (NASA POWER) and by the dashboard upload.
Accepts almost any rainfall table: CSV, TSV, Excel, JSON, text; daily, weekly or monthly rows;
missing values are allowed. Output: forecasts, model scores and feature importance.'''
import io, json, warnings
from collections import Counter
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from statsmodels.tsa.statespace.sarimax import SARIMAX
from features import add_features, feature_columns
warnings.filterwarnings('ignore')

NAMES = {'rainfall_mm': 'Past rainfall', 'T2M': 'Mean temp', 'T2M_MAX': 'Max temp', 'T2M_MIN': 'Min temp',
         'T2MDEW': 'Dew point', 'RH2M': 'Humidity', 'QV2M': 'Specific humidity', 'WS2M': 'Wind 2 m', 'WS10M': 'Wind 10 m',
         'PS': 'Surface pressure', 'ALLSKY_SFC_SW_DWN': 'Solar radiation', 'TOA_SW_DWN': 'Top-of-atmosphere solar',
         'CLOUD_AMT': 'Cloud amount', 'GWETTOP': 'Surface soil wetness', 'GWETROOT': 'Root-zone soil wetness',
         'GWETPROF': 'Profile soil moisture', 'EVPTRNS': 'Evapotranspiration', 'week_of_year': 'Week of year', 'month': 'Month',
         'rain_roll_short': 'Recent rainfall average', 'rain_roll_long': 'Long rainfall average'}
SKIP = {'year', 'yyyy', 'yr', 'mo', 'mon', 'month', 'dy', 'day', 'doy', 'lat', 'latitude', 'lon', 'longitude', 'lng',
        'week', 'date', 'time', 'index', 'id', 's.no', 'sno'}
MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
HEAVY, LOW = 150, 30          # mm per month thresholds used for the status labels


class NeedColumn(Exception):
    '''Raised when the date or rainfall column cannot be detected: the dashboard then asks the user to pick it.'''
    def __init__(self, field, columns, msg):
        super().__init__(msg)
        self.field, self.columns = field, [str(c) for c in columns]


# ------------------------------------------------------------------ reading any file
def _read_text(text):
    if '-END HEADER-' in text:                                   # NASA POWER Data Access Viewer files
        text = text.split('-END HEADER-', 1)[1]
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        raise ValueError('The file is empty.')
    best = None
    for sep in (',', ';', '\t', '|'):
        c = Counter(l.count(sep) + 1 for l in lines[:80]).most_common(1)[0]
        if c[0] >= 2 and (best is None or c[1] > best[2]):
            best = (sep, c[0], c[1])
    if best is None:
        return pd.read_csv(io.StringIO('\n'.join(lines)), sep=r'\s+', engine='python', on_bad_lines='skip')
    sep, nf, _ = best
    full = lambda l: l.count(sep) + 1 == nf and sum(1 for x in l.split(sep) if x.strip()) >= 2
    start = next((i for i, l in enumerate(lines) if full(l)), 0)                # skip title lines above the header
    return pd.read_csv(io.StringIO('\n'.join(lines[start:])), sep=sep, engine='python', on_bad_lines='skip')


def _load_frame(raw, filename):
    name = (filename or '').lower()
    head = raw[:4]
    try:
        if head[:2] == b'PK' or name.endswith(('.xlsx', '.xlsm')):
            return pd.read_excel(io.BytesIO(raw))
        if head == b'\xd0\xcf\x11\xe0' or name.endswith('.xls'):
            return pd.read_excel(io.BytesIO(raw))
        if name.endswith('.json') or raw.lstrip()[:1] in (b'{', b'['):
            return pd.read_json(io.BytesIO(raw))
    except Exception as e:
        raise ValueError('Could not open this file as a spreadsheet or JSON: ' + str(e)[:120])
    for enc in ('utf-8-sig', 'utf-16', 'latin-1'):
        try:
            return _read_text(raw.decode(enc))
        except UnicodeError:
            continue
    raise ValueError('Could not read this file as text.')


def _to_num(col):
    if pd.api.types.is_numeric_dtype(col):
        return col
    return pd.to_numeric(col.astype(str).str.strip().str.replace(',', '.', regex=False), errors='coerce')


def _parse_one(s, dayfirst=False):
    if pd.api.types.is_numeric_dtype(s):
        v = s.dropna()
        if len(v) and v.between(19000101, 21001231).all():       # 20200615 style
            return pd.to_datetime(s.astype('Int64').astype(str), format='%Y%m%d', errors='coerce')
        return pd.Series(pd.NaT, index=s.index)
    return pd.to_datetime(s, errors='coerce', dayfirst=dayfirst)


def _parse_dates(df, date_col=None):
    if date_col:
        if date_col not in df.columns:
            raise ValueError('The column ' + str(date_col) + ' is not in the file.')
        d = max((_parse_one(df[date_col], dfst) for dfst in (False, True)), key=lambda x: x.notna().mean())
        if d.notna().mean() < 0.5:
            raise ValueError('The column ' + str(date_col) + ' does not look like dates.')
        return d, {date_col}
    up = {str(c).upper(): c for c in df.columns}
    pick = lambda keys: next((up[k] for k in keys if k in up), None)
    yy, mm, dd = pick(('YEAR', 'YR', 'YYYY')), pick(('MO', 'MONTH', 'MON')), pick(('DY', 'DAY', 'DAYOFMONTH'))
    if yy and mm:
        month = pd.to_numeric(df[mm], errors='coerce')
        if month.isna().mean() > 0.5:                              # month given as a name
            month = df[mm].astype(str).str.strip().str.lower().str[:3].map({m: i + 1 for i, m in enumerate(MONTHS)})
        day = pd.to_numeric(df[dd], errors='coerce') if dd else 1
        d = pd.to_datetime(pd.DataFrame({'year': pd.to_numeric(df[yy], errors='coerce'), 'month': month, 'day': day}), errors='coerce')
        if d.notna().mean() > 0.8:
            return d, {c for c in (yy, mm, dd) if c}
    if yy and 'DOY' in up:
        y = pd.to_numeric(df[yy], errors='coerce').astype('Int64').astype(str)
        d = pd.to_datetime(y, format='%Y', errors='coerce') + pd.to_timedelta(pd.to_numeric(df[up['DOY']], errors='coerce') - 1, unit='D')
        return d, {yy, up['DOY']}
    named = [c for c in df.columns if any(k in str(c).lower() for k in ('date', 'time'))]
    others = [c for c in df.columns if c not in named and not pd.api.types.is_numeric_dtype(df[c])]
    best = None
    for c in named + others:
        for dayfirst in (False, True):
            d = _parse_one(df[c], dayfirst)
            ok = d.notna().mean()
            if best is None or ok > best[0]:
                best = (ok, d, c)
    if best is None or best[0] < 0.8:
        raise NeedColumn('date', df.columns, 'Could not find the date column. Choose it below.')
    return best[1], {best[2]}


def _find_rain_col(cols):
    low = {c: str(c).lower().strip() for c in cols}
    for key in ('rainfall_mm', 'rainfall', 'rain', 'precipitation', 'precip', 'prcp', 'prectotcorr', 'prectot', 'rr'):
        for c, l in low.items():
            if l == key:
                return c
    for c, l in low.items():
        if any(k in l for k in ('rain', 'prec', 'prcp', 'rf_', 'mm')):
            return c
    return None


def _wide_to_long(df):
    '''Tables like  Year | Jan | Feb | ... | Dec  become one row per month.'''
    cols = [c for c in df.columns if str(c).strip().lower()[:3] in MONTHS]
    year = next((c for c in df.columns if str(c).strip().lower() in ('year', 'yr', 'yyyy', 'years')), None)
    if len(cols) < 10 or year is None:
        return None
    long = df.melt(id_vars=[year], value_vars=cols, var_name='m', value_name='rainfall_mm')
    month = long['m'].astype(str).str.strip().str.lower().str[:3].map({m: i + 1 for i, m in enumerate(MONTHS)})
    long['date'] = pd.to_datetime(pd.DataFrame({'year': pd.to_numeric(long[year], errors='coerce'), 'month': month, 'day': 1}), errors='coerce')
    long['rainfall_mm'] = _to_num(long['rainfall_mm'])
    return long.dropna(subset=['date']).sort_values('date').set_index('date')[['rainfall_mm']]


def read_upload(f, filename, rain_col=None, date_col=None):
    '''Any file -> (table with DatetimeIndex and a rainfall_mm column, mode: daily | weekly | monthly).'''
    df = _load_frame(f.read(), filename)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all').dropna(axis=1, how='all')
    if df.shape[1] < 2:
        raise ValueError('This file does not look like a table with columns (date, rainfall, ...).')
    num = _wide_to_long(df) if not rain_col and not date_col else None
    if num is None:
        dates, used = _parse_dates(df, date_col)
        body = df.drop(columns=[c for c in used if c in df.columns]).apply(_to_num)
        body.index = pd.DatetimeIndex(dates)
        num = body[body.index.notna()].dropna(axis=1, how='all')
        num = num.loc[:, [c for c in num.columns if str(c).lower() not in SKIP and not str(c).lower().startswith('unnamed')]]
        if num.shape[1] == 0:
            raise ValueError('No numeric columns were found in this file.')
        rain = rain_col if rain_col else _find_rain_col(num.columns)
        if rain is None:
            raise NeedColumn('rain', num.columns, 'Could not find the rainfall column. Choose it below.')
        if rain not in num.columns:
            raise ValueError('The column ' + str(rain) + ' is not a numeric column in the file.')
        num = num.rename(columns={rain: 'rainfall_mm'})
    num = num.replace([-999, -9999, -99999], np.nan)
    num.loc[num['rainfall_mm'] < 0, 'rainfall_mm'] = np.nan
    num = num.groupby(level=0).mean().sort_index()
    if len(num) < 12:
        raise ValueError('Too few rows (%d). A rainfall history of at least 3 years is needed.' % len(num))
    gap = num.index.to_series().diff().dt.days.median()
    agg = {c: 'mean' for c in num.columns}
    agg['rainfall_mm'] = 'sum'
    if gap <= 1.5:
        return num.resample('D').mean(), 'daily'
    if gap <= 10:
        return num.resample('W').agg(agg), 'weekly'
    return num.resample('ME').agg(agg), 'monthly'


# ------------------------------------------------------------------ cleaning and helpers
def _clean(raw):
    notes = []
    r = raw['rainfall_mm']
    if r.notna().sum() == 0:
        raise ValueError('The rainfall column has no numbers in it. Check that you chose the right column.')
    miss = float(r.isna().mean())
    if miss > 0:
        notes.append('%.0f%% of the rainfall values were missing and are treated as 0 mm%s.' %
                     (miss * 100, ' (results may be unreliable)' if miss > 0.2 else ''))
    rain = r.fillna(0)
    if rain.nunique() < 3:
        raise ValueError('The rainfall column has almost no variation, so nothing can be forecast.')
    feats = raw.drop(columns='rainfall_mm')
    kept = feats.loc[:, feats.isna().mean() < 0.5]
    kept = kept[list(kept.isna().mean().sort_values().index[:24])]
    dropped = len(feats.columns) - len(kept.columns)
    if dropped:
        notes.append('%d columns were not used (too many missing values, or more than 24 columns).' % dropped)
    kept = kept.interpolate(limit=60).bfill().ffill()
    return pd.concat([rain, kept], axis=1), notes


def _score(y, p, name):
    return {'Model': name, 'RMSE': round(float(np.sqrt(mean_squared_error(y, p))), 2),
            'MAE': round(float(mean_absolute_error(y, p)), 2), 'R2': round(float(r2_score(y, p)), 3)}


def _make_rf():
    return RandomForestRegressor(n_estimators=300, max_depth=12, min_samples_leaf=3, random_state=42, n_jobs=-1)


def _climatology(daily):
    '''For each day of the year: chance of a rainy day (2.5 mm or more) and the typical rainy-day amount,
    using all years in the data, plus or minus 7 days.'''
    doy = daily.index.dayofyear.values
    vals = daily.values
    prob, amt = [], []
    for d in range(1, 367):
        dist = np.abs(doy - d)
        sel = vals[np.minimum(dist, 366 - dist) <= 7]
        wet = sel[sel >= 2.5]
        prob.append(round(float((sel >= 2.5).mean()) * 100, 1) if len(sel) else None)
        amt.append(round(float(wet.mean()), 1) if len(wet) else 0.0)
    return {'prob': prob, 'rainy_mean': amt}


# ------------------------------------------------------------------ the whole ML pipeline
def run_pipeline(num, mode, name, source='uploaded'):
    raw, notes = _clean(num.copy())
    first, last = raw.index[0], raw.index[-1]
    L = lambda s, n=1: [round(float(v), n) for v in s]
    ym = lambda idx: [str(i.date())[:7] for i in idx]

    if mode == 'daily':
        monthly = raw['rainfall_mm'].resample('ME').sum()
        monthly = monthly[monthly.index <= last]
        if first.day != 1:
            monthly = monthly.iloc[1:]
        agg = {c: 'mean' for c in raw.columns}
        agg['rainfall_mm'] = 'sum'
        table = raw.resample('W').agg(agg)
        table = table[table.index <= last].iloc[1:]
        freq, step = 'W', 'week'
    elif mode == 'weekly':
        monthly = raw['rainfall_mm'].resample('ME').sum()
        monthly = monthly.iloc[1:-1] if len(monthly) > 14 else monthly
        table, freq, step = raw, 'W', 'week'
    else:
        monthly = raw['rainfall_mm']
        table, freq, step = raw, 'M', 'month'

    n = len(monthly)
    test_n = max(6, int(round(n * 0.2)))
    if n - test_n < 24:
        raise ValueError('Need at least about 3 years of rainfall history (36 months). Your file has %d months.' % n)
    train, test = monthly.iloc[:-test_n], monthly.iloc[-test_n:]
    train_end = train.index[-1]

    # 1) persistence baselines  2) SARIMA (ARIMA with a yearly season) on monthly totals
    persist = monthly.shift(1)[test.index].fillna(0)
    seasonal = monthly.shift(12)[test.index].fillna(0)
    sar = SARIMAX(train, order=(1, 0, 1), seasonal_order=(1, 1, 1, 12)).fit(disp=False)
    sar_pred = sar.forecast(len(test)).clip(lower=0)
    metrics = [_score(test, persist, 'Persistence (last month)'), _score(test, seasonal, 'Seasonal persistence'),
               _score(test, sar_pred, 'SARIMA')]

    # 3) Random Forest on lag features of every column (weekly table, or monthly table for monthly files)
    data = add_features(table, freq)
    x_cols = feature_columns(data)
    X, y = data[x_cols], data['rainfall_mm']
    tr = data.index <= train_end
    if (~tr).sum() < 3 or tr.sum() < 20:
        raise ValueError('Not enough rows to train and test the Random Forest. Use a longer file.')
    rf_test = _make_rf().fit(X[tr], y[tr])
    yt = y[~tr]
    rf_name = 'Random Forest (weekly)' if freq == 'W' else 'Random Forest (monthly)'
    if freq == 'W':
        metrics.append(_score(yt, y.shift(1)[yt.index].fillna(0), 'Weekly persistence'))
    metrics.append(_score(yt, rf_test.predict(X[~tr]), rf_name))

    # final models on all the data; SARIMA looks 36 months ahead so any date can be asked for
    rf = _make_rf().fit(X, y)
    full = SARIMAX(monthly, order=(1, 0, 1), seasonal_order=(1, 1, 1, 12)).fit(disp=False)
    f36 = full.get_forecast(36)
    mean = f36.predicted_mean.clip(lower=0)
    ci = f36.conf_int(alpha=0.2).clip(lower=0)
    sarima_long = {'dates': ym(mean.index), 'mean': L(mean), 'lower': L(ci.iloc[:, 0]), 'upper': L(ci.iloc[:, 1])}

    imp = {}
    for c, v in zip(x_cols, rf.feature_importances_):
        b = c.split('_lag')[0] if '_lag' in c else ('rainfall_mm' if 'roll' in c else c)
        imp[b] = imp.get(b, 0) + v
    importance = sorted([{'name': NAMES.get(k, k), 'value': round(float(v) * 100, 1)} for k, v in imp.items()],
                        key=lambda i: -i['value'])[:6]

    daily = raw['rainfall_mm'] if mode == 'daily' else None
    results = {
        'updated': str(pd.Timestamp.today().date()), 'metrics': metrics,
        'dataset': {'name': name, 'source': source, 'mode': mode, 'step': step, 'rows': int(len(raw)),
                    'from': str(first.date()), 'to': str(last.date()), 'train_until': str(train_end.date()), 'notes': notes,
                    'columns': ['Rainfall (target)' if c == 'rainfall_mm' else NAMES.get(c, c) for c in raw.columns],
                    'min_date': str(first.date()),
                    'max_date': str((pd.Period(sarima_long['dates'][-1], 'M') - 5).end_time.date())},
        'monthly': {'dates': ym(test.index), 'actual': L(test), 'seasonal': L(seasonal), 'sarima': L(sar_pred)},
        'recent': {'dates': ym(monthly.index[-24:]), 'actual': L(monthly.iloc[-24:])},
        'sarima_fc': {k: v[:6] for k, v in sarima_long.items()},
        'sarima_long': sarima_long,
        'monthly_all': {'dates': ym(monthly.index), 'actual': L(monthly)},
        'clim': _climatology(daily) if daily is not None else None,
        'importance': importance}
    return {'results': results, 'rf': rf, 'x_cols': x_cols, 'table': table, 'daily': daily, 'freq': freq}
