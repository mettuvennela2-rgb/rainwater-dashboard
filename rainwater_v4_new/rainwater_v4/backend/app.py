import os, json
import joblib, pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from features import next_step_features
from pipeline import read_upload, run_pipeline, NeedColumn, HEAVY, LOW

BASE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(BASE, '..', 'frontend', 'dist')
app = Flask(__name__, static_folder=DIST, static_url_path='')
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024
CORS(app)

STATE = {}          # the models and results currently shown in the dashboard
BIG = ('monthly_all', 'sarima_long', 'clim')     # kept on the server, not sent with every summary


def load_default():
    '''Load the models saved by train_model.py (if you ran it).'''
    p = lambda f: os.path.join(BASE, f)
    files = ('rf_model.pkl', 'x_cols.pkl', 'table_data.csv', 'results.json', 'daily_rain.csv')
    if not all(os.path.exists(p(f)) for f in files):
        return False
    results = json.load(open(p('results.json')))
    mode = results['dataset']['mode']
    STATE.clear()
    STATE.update(rf=joblib.load(p('rf_model.pkl')), x_cols=joblib.load(p('x_cols.pkl')),
                 table=pd.read_csv(p('table_data.csv'), index_col=0, parse_dates=True),
                 daily=pd.read_csv(p('daily_rain.csv'), index_col=0, parse_dates=True)['rainfall_mm'],
                 freq='W' if mode in ('daily', 'weekly') else 'M', results=results)
    return True


load_default()


def step_forecast():
    X, nxt = next_step_features(STATE['table'], STATE['x_cols'], STATE['freq'])
    return max(float(STATE['rf'].predict(X)[0]), 0.0), nxt


def build_summary():
    pred, nxt = step_forecast()
    R = {k: v for k, v in STATE['results'].items() if k not in BIG}
    return {**R, 'forecast': round(pred, 1), 'period_end': str(nxt.date()), 'week_ending': str(nxt.date()),
            'sarima_next': R['sarima_fc']['mean'][0], 'sarima_month': R['sarima_fc']['dates'][0]}


def harvest_estimate(rain_mm, roof_area_m2, runoff_coeff=0.85, first_flush_mm=1.0):
    return max(rain_mm - first_flush_mm, 0) * roof_area_m2 * runoff_coeff


def status_of(mm):
    return 'Heavy rain' if mm > HEAVY else 'Low rain' if mm < LOW else 'Within range'


def decide(rain_mm, roof, cap, level, daily_use, pit=5000):
    inflow = harvest_estimate(rain_mm, roof)
    free, weekly_use = cap - level, daily_use * 7
    if inflow <= free:
        action, to_tank, to_rech = 'STORE: send all harvested water to the tank', inflow, 0
    elif level > 0.8 * cap:
        action = 'FREE UP TANK SPACE: use or release water before the rain'
        to_tank, to_rech = free, min(inflow - free, pit)
    else:
        action = 'STORE + RECHARGE: fill the tank, divert the excess to the recharge pit'
        to_tank, to_rech = free, min(inflow - free, pit)
    overflow = max(inflow - to_tank - to_rech, 0)
    after = min(max(level + to_tank - weekly_use, 0), cap)
    return {'rain_mm': round(rain_mm, 1), 'harvestable_l': round(inflow), 'to_tank_l': round(to_tank),
            'to_recharge_l': round(to_rech), 'overflow_l': round(overflow), 'tank_after_l': round(after),
            'tank_before_l': round(level), 'recommendation': action, 'water_deficit': after == 0,
            'days_of_supply': round(after / daily_use, 1) if daily_use else 0}


def forecast_from(date_str, roof):
    '''Everything the dashboard shows for a chosen date: the 6 months starting at that date and the date itself.'''
    R = STATE['results']
    try:
        d = pd.Timestamp(date_str)
    except Exception:
        raise ValueError('Enter a valid date.')
    ds = R['dataset']
    if d < pd.Timestamp(ds['min_date']):
        raise ValueError('That date is before your data starts (%s).' % ds['min_date'])
    if d > pd.Timestamp(ds['max_date']):
        raise ValueError('That date is too far ahead. The latest date that can be predicted is %s.' % ds['max_date'])
    ma, sl = R['monthly_all'], R['sarima_long']
    actual = dict(zip(ma['dates'], ma['actual']))
    fc = {m: (sl['mean'][i], sl['lower'][i], sl['upper'][i]) for i, m in enumerate(sl['dates'])}
    last_m = pd.Period(ma['dates'][-1], 'M')
    start = pd.Period(d, 'M')
    window = [start + i for i in range(6)]

    def row(p):
        k = str(p)
        if k in actual:
            return {'month': k, 'kind': 'actual', 'rain': actual[k], 'lower': None, 'upper': None}
        m, lo, hi = fc[k]
        return {'month': k, 'kind': 'forecast', 'rain': m, 'lower': lo, 'upper': hi}

    table = []
    for p in window:
        r = row(p)
        r['harvest_l'] = round(harvest_estimate(r['rain'], roof))
        r['status'] = status_of(r['rain'])
        table.append(r)
    c0, c1 = min(start, last_m - 11), max(window[-1], last_m)
    chart, p = [], c0
    while p <= c1:
        r = row(p)
        chart.append({'date': r['month'], 'actual': r['rain'] if r['kind'] == 'actual' else None,
                      'forecast': r['rain'] if r['kind'] == 'forecast' else None,
                      'range': [r['lower'], r['upper']] if r['kind'] == 'forecast' else None})
        p += 1
    for c in chart:                                 # join the actual line to the forecast line
        if c['date'] == str(last_m) and c['actual'] is not None and any(x['forecast'] is not None for x in chart):
            c['forecast'] = c['actual']
            c['range'] = [c['actual'], c['actual']]

    data_end = pd.Timestamp(ds['to'])
    mrow = row(start)
    day = {'date': str(d.date()), 'month': str(start), 'month_rain': mrow['rain'], 'month_lower': mrow['lower'],
           'month_upper': mrow['upper'], 'month_harvest_l': round(harvest_estimate(mrow['rain'], roof)),
           'status': status_of(mrow['rain'])}
    daily = STATE.get('daily')
    if d <= data_end:
        day['kind'] = 'actual'
        day['actual_mm'] = round(float(daily.get(d)), 1) if daily is not None and d in daily.index else None
    else:
        day['kind'] = 'forecast'
        days_in_month = start.days_in_month
        day['avg_per_day'] = round(mrow['rain'] / days_in_month, 1)
        day['months_ahead'] = max((start - last_m).n, 0)
        day['confidence'] = 'Good' if day['months_ahead'] <= 1 else 'Medium' if day['months_ahead'] <= 6 else 'Low'
        clim = R.get('clim')
        doy = min(d.dayofyear, 366)
        day['rain_chance_pct'] = clim['prob'][doy - 1] if clim else None
        day['rainy_day_mm'] = clim['rainy_mean'][doy - 1] if clim else None
        pred, nxt = step_forecast()
        span = pd.Timedelta(days=6) if STATE['freq'] == 'W' else pd.Timedelta(days=27)
        if nxt - span <= d <= nxt:
            day['step_forecast_mm'] = round(pred, 1)
            day['step'] = 'week' if STATE['freq'] == 'W' else 'month'
            day['step_end'] = str(nxt.date())
    return {'table': table, 'chart': chart, 'window': {'start': str(window[0]), 'end': str(window[-1])}, 'day': day}


@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'dataset_loaded': bool(STATE)})


@app.route('/api/summary')
def summary():
    if not STATE:
        return jsonify({'error': 'no_dataset'}), 404
    return jsonify(build_summary())


@app.route('/api/upload', methods=['POST'])
def upload():
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'error': 'No file received.'}), 400
    try:
        num, mode = read_upload(f, f.filename, request.form.get('rain_col') or None, request.form.get('date_col') or None)
        art = run_pipeline(num, mode, f.filename, 'uploaded')
    except NeedColumn as e:
        return jsonify({'error': str(e), 'needs': e.field, 'columns': e.columns}), 409
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Could not process this file: ' + str(e)[:200]}), 500
    STATE.clear()
    STATE.update(rf=art['rf'], x_cols=art['x_cols'], table=art['table'], daily=art['daily'],
                 freq=art['freq'], results=art['results'])
    return jsonify(build_summary())


@app.route('/api/reset', methods=['POST'])
def reset():
    if not load_default():
        return jsonify({'error': 'The default dataset is not trained. Run python train_model.py, or upload a file.'}), 404
    return jsonify(build_summary())


@app.route('/api/forecast-from', methods=['POST'])
def api_forecast_from():
    if not STATE:
        return jsonify({'error': 'no_dataset'}), 400
    d = request.get_json() or {}
    try:
        return jsonify(forecast_from(d.get('date'), float(d.get('roof_area_m2', 100))))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/decide', methods=['POST'])
def api_decide():
    d = request.get_json()
    rain = d.get('forecast_rain_mm')
    if rain is None:
        if not STATE:
            return jsonify({'error': 'no_dataset'}), 400
        rain, _ = step_forecast()
    cap = float(d['tank_capacity_l'])
    return jsonify(decide(float(rain), float(d['roof_area_m2']), cap,
                          min(float(d['tank_level_l']), cap), float(d['daily_use_l'])))


@app.route('/')
def index():
    if os.path.exists(os.path.join(DIST, 'index.html')):
        return send_from_directory(DIST, 'index.html')
    return jsonify({'message': 'API is running. Start the React app (npm run dev) or build it (npm run build).'})


if __name__ == '__main__':
    print()
    print('=' * 60)
    print(' Dashboard is ready. Open this address in your browser:')
    print('     http://127.0.0.1:5000')
    print(' Keep this window open. Press Ctrl+C to stop.')
    print('=' * 60)
    app.run(host='127.0.0.1', port=5000, debug=False)
