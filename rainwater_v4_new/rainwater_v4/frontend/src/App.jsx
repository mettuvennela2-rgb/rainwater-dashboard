import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid, BarChart, Bar, ReferenceArea,
} from 'recharts'

const call = (url, opt) =>
  fetch(url, opt).then((r) => {
    if (!r.ok) throw new Error(r.status)
    return r.json()
  })
const fmt = (n) => Math.round(n).toLocaleString()
const p2 = (n) => String(n).padStart(2, '0')
const ymd = (d) => `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
const parse = (s) => new Date(s + 'T00:00:00')
const addDays = (s, n) => { const d = parse(s); d.setDate(d.getDate() + n); return ymd(d) }
const addMonths = (s, n) => { const d = parse(s); d.setMonth(d.getMonth() + n); return ymd(d) }
const clamp = (s, ds) => (s > ds.max_date ? ds.max_date : s < ds.min_date ? ds.min_date : s)

const FI_COLORS = ['#1e6fe8', '#2fb170', '#f5b335', '#8b4fe0', '#18b4d6', '#8a9bc0']
const NAV = [['s1', 'Overview'], ['s6', 'Predict by Date'], ['s2', 'Forecast'], ['s3', 'Model Performance'], ['s4', 'Planner'], ['s5', 'Recent Predictions']]
const SLIDERS = [
  ['roof', 'Roof area', ' m2', 20, 500, 10],
  ['cap', 'Tank capacity', ' L', 1000, 30000, 500],
  ['level', 'Tank level now', ' L', 0, 30000, 500],
  ['use', 'Daily use', ' L/day', 50, 1000, 10],
]
const TEMPLATE =
  'date,rainfall_mm,temperature,humidity,pressure,wind_speed\n' +
  '2015-01-01,0.0,22.4,48,93.1,2.1\n2015-01-02,0.2,22.9,51,93.0,2.4\n2015-01-03,5.4,21.8,66,92.8,3.0\n'

function Kpi({ color, title, value, unit, note }) {
  return (
    <div className='card kpi'>
      <div className='ic' style={{ background: color }} />
      <div>
        <small>{title}</small>
        <div className='v'>{value} <i>{unit}</i></div>
        <div className='n'>{note}</div>
      </div>
    </div>
  )
}

function Stat({ title, value, unit, note }) {
  return (
    <div className='stat'>
      <small>{title}</small>
      <div className='v'>{value} <span style={{ fontSize: 14 }}>{unit}</span></div>
      <div className='n'>{note}</div>
    </div>
  )
}

function Side({ active, go }) {
  return (
    <aside>
      <div className='logo'><div><b>Rainwater Harvest</b><span>Forecast and Recharge</span></div></div>
      {NAV.map(([id, t]) => <a key={id} className={active === id ? 'on' : ''} onClick={() => go(id)}>{t}</a>)}
      <div className='foot'>Smarter Water Management<br />for a Safer Tomorrow</div>
    </aside>
  )
}

function DataCard({ S, busy, msg, pending, onUpload, onPick, onReset, fileRef }) {
  const d = S && S.dataset
  const [col, setCol] = useState('')
  const template = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv' }))
    a.download = 'dataset_template.csv'
    a.click()
  }
  return (
    <div className='card' style={{ marginBottom: 14 }}>
      <h3>Dataset</h3>
      {d ? (
        <div className='cap'>
          <b>{d.name}</b> | {d.rows.toLocaleString()} {d.mode} rows ({d.from} to {d.to}) | models trained up to {d.train_until}, tested after that |{' '}
          {d.columns.length} variables: {d.columns.join(', ')}.
          {d.notes && d.notes.length > 0 && <span> Notes: {d.notes.join(' ')}</span>}
        </div>
      ) : (
        <div className='cap'>No dataset loaded yet. Upload a file to see all the predictions.</div>
      )}
      <div className='btns'>
        <button className='on' disabled={busy} onClick={() => fileRef.current.click()}>Upload your dataset (any file)</button>
        <input ref={fileRef} type='file' hidden onChange={onUpload} />
        <button disabled={busy} onClick={onReset}>Use the default NASA POWER data</button>
        <button disabled={busy} onClick={template}>Download CSV template</button>
      </div>
      {pending && (
        <div className='msg bad'>
          <div>{pending.text} ({pending.needs === 'date' ? 'date column' : 'rainfall column in mm'})</div>
          <div className='pick' style={{ marginTop: 8 }}>
            <select value={col || pending.columns[0] || ''} onChange={(e) => setCol(e.target.value)}>
              {pending.columns.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <button disabled={busy || !pending.columns.length} onClick={() => onPick(col || pending.columns[0])}>Continue</button>
          </div>
        </div>
      )}
      {msg && <div className={'msg ' + (msg.ok ? 'good' : 'bad')}>{msg.text}</div>}
      <div className='cap' style={{ marginBottom: 0 }}>
        Any table works: CSV, Excel, JSON or text; daily, weekly or monthly rows; missing values are allowed (about 3 years or more of rainfall).
        Other numeric columns (temperature, humidity, soil moisture and so on) are used as extra features automatically.
      </div>
    </div>
  )
}

function DateCard({ S, dateStr, setDateStr, FC, fcErr }) {
  const ds = S.dataset
  const dayAfter = clamp(addDays(ds.to, 1), ds)
  const quick = [['Day after data', dayAfter], ['+1 month', addMonths(ds.to, 1)], ['+3 months', addMonths(ds.to, 3)], ['+6 months', addMonths(ds.to, 6)], ['+12 months', addMonths(ds.to, 12)]]
  const D = FC && FC.day
  return (
    <section className='card g' id='s6' style={{ display: 'block' }}>
      <h3>Predict by Date</h3>
      <div className='cap'>Pick any date. A future date is forecast, a past date shows your data. The chart and table below start from this date and cover 6 months.</div>
      <div className='pick'>
        <input type='date' value={dateStr} min={ds.min_date} max={ds.max_date} onChange={(e) => e.target.value && setDateStr(e.target.value)} />
        {quick.filter(([, v]) => v <= ds.max_date).map(([t, v]) => (
          <button key={t} className={dateStr === v ? 'on' : ''} onClick={() => setDateStr(v)}>{t}</button>
        ))}
      </div>
      <div className='cap' style={{ marginTop: 6 }}>Your data ends on {ds.to}. Dates up to {ds.max_date} can be predicted.</div>
      {fcErr && <div className='msg bad'>{fcErr}</div>}
      {D && D.kind === 'forecast' && (
        <>
          <div className='stats'>
            <Stat title={`Expected rainfall in ${D.month}`} value={D.month_rain} unit='mm' note={`range ${D.month_lower} to ${D.month_upper} mm`} />
            <Stat title='Average per day that month' value={D.avg_per_day} unit='mm' note={D.status} />
            <Stat title={`Chance of rain on ${D.date}`} value={D.rain_chance_pct == null ? '-' : D.rain_chance_pct} unit={D.rain_chance_pct == null ? '' : '%'}
              note={D.rain_chance_pct == null ? 'needs daily data' : `typical rainy day: ${D.rainy_day_mm} mm`} />
            <Stat title='Harvestable water that month' value={fmt(D.month_harvest_l)} unit='L' note='for your roof area' />
          </div>
          <div className='cap' style={{ marginTop: 10, marginBottom: 0 }}>
            Forecast confidence: <b>{D.confidence}</b> ({D.months_ahead} months after the end of your data). The further ahead, the wider the range.
            The chance of rain is how often days around this date had 2.5 mm or more in your history. It is not a daily forecast.
            {D.step_forecast_mm != null && <> Random Forest forecast for the {D.step} ending {D.step_end}: <b>{D.step_forecast_mm} mm</b>.</>}
          </div>
        </>
      )}
      {D && D.kind === 'actual' && (
        <div className='stats'>
          <Stat title={`Actual rainfall on ${D.date}`} value={D.actual_mm == null ? '-' : D.actual_mm} unit={D.actual_mm == null ? '' : 'mm'} note={D.actual_mm == null ? 'daily value not in your file' : 'from your data'} />
          <Stat title={`Total in ${D.month}`} value={D.month_rain} unit='mm' note={D.status} />
          <Stat title='Harvestable that month' value={fmt(D.month_harvest_l)} unit='L' note='for your roof area' />
          <Stat title='Type' value='Past' unit='' note='this date is inside your data' />
        </div>
      )}
    </section>
  )
}

export default function App() {
  const [S, setS] = useState(null)
  const [ready, setReady] = useState(false)
  const [err, setErr] = useState('')
  const [dec, setDec] = useState(null)
  const [mode, setMode] = useState('monthly')
  const [active, setActive] = useState('s1')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [pending, setPending] = useState(null)
  const [dateStr, setDateStr] = useState('')
  const [FC, setFC] = useState(null)
  const [fcErr, setFcErr] = useState('')
  const fileRef = useRef(null)
  const [cfg, setCfg] = useState({ roof: 100, cap: 10000, level: 6000, use: 300, auto: true, rain: 0 })

  const applySummary = (j) => {
    setS(j)
    setDateStr(clamp(addDays(j.dataset.to, 1), j.dataset))   // default: the day after your data ends
    setFcErr('')
  }

  useEffect(() => {
    call('/api/summary')
      .then(applySummary)
      .catch((e) => { if (e.message !== '404') setErr('Cannot reach the API. Start Flask first (python app.py).') })
      .finally(() => setReady(true))
  }, [])

  // decision (store / recharge / release) for the next period
  useEffect(() => {
    if (!S) { setDec(null); return }
    const body = { roof_area_m2: cfg.roof, tank_capacity_l: cfg.cap, tank_level_l: cfg.level, daily_use_l: cfg.use }
    if (!cfg.auto) body.forecast_rain_mm = cfg.rain
    call('/api/decide', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(setDec)
      .catch(() => setErr('The decision request failed.'))
  }, [S, cfg])

  // prediction for the chosen date and the 6 months that start there
  useEffect(() => {
    if (!S || !dateStr) return
    fetch('/api/forecast-from', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: dateStr, roof_area_m2: cfg.roof }),
    })
      .then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.error || 'Prediction failed'); return j })
      .then((j) => { setFC(j); setFcErr('') })
      .catch((e) => setFcErr(e.message))
  }, [S, dateStr, cfg.roof])

  const send = async (file, extra = {}) => {
    setBusy(true); setMsg(null)
    const fd = new FormData()
    fd.append('file', file)
    Object.entries(extra).forEach(([k, v]) => fd.append(k, v))
    try {
      const r = await fetch('/api/upload', { method: 'POST', body: fd })
      const j = await r.json()
      if (r.status === 409) { setPending({ file, extra, needs: j.needs, columns: j.columns, text: j.error }); setBusy(false); return }
      if (!r.ok) throw new Error(j.error || 'Upload failed')
      setPending(null)
      applySummary(j)
      setMsg({ ok: true, text: 'Loaded ' + file.name + '. Every forecast, score and chart now comes from your file.' })
    } catch (ex) {
      setPending(null)
      setMsg({ ok: false, text: ex.message === 'Failed to fetch' ? 'Cannot reach the API. Is Flask running?' : ex.message })
    }
    setBusy(false)
  }
  const onUpload = (e) => {
    const f = e.target.files[0]
    e.target.value = ''
    if (f) send(f)
  }
  const onPick = (col) => send(pending.file, { ...pending.extra, [pending.needs === 'date' ? 'date_col' : 'rain_col']: col })

  const onReset = async () => {
    setBusy(true); setMsg(null); setPending(null)
    try {
      applySummary(await call('/api/reset', { method: 'POST' }))
      setMsg({ ok: true, text: 'Back to the default NASA POWER dataset.' })
    } catch (ex) {
      setMsg({ ok: false, text: 'The default dataset is not trained yet. Run python train_model.py, or upload a file.' })
    }
    setBusy(false)
  }

  const isWeekly = (m) => m.Model.toLowerCase().includes('weekly')
  const insights = useMemo(() => {
    if (!S) return []
    const best = (a) => a.reduce((x, y) => (x.RMSE < y.RMSE ? x : y))
    const mon = S.metrics.filter((m) => !isWeekly(m) && !m.Model.startsWith('Random'))
    const bm = best(mon)
    const pm = mon.find((m) => m.Model.startsWith('Persistence'))
    const rfm = S.metrics.find((m) => m.Model.startsWith('Random'))
    const pw = S.metrics.find((m) => m.Model.startsWith('Weekly')) || pm
    const pct = (a, b) => Math.round((1 - a / b) * 100)
    const gain = pct(rfm.RMSE, pw.RMSE)
    const heavy = FC ? FC.table.filter((r) => r.status === 'Heavy rain').map((r) => r.month) : []
    return [
      `Random Forest expects ${S.forecast} mm next ${S.dataset.step}. SARIMA expects ${S.sarima_next} mm in ${S.sarima_month}.`,
      `${bm.Model} is the best monthly model: ${pct(bm.RMSE, pm.RMSE)}% lower error than persistence.`,
      gain >= 0 ? `Random Forest cuts error by ${gain}% compared with persistence.` : `Random Forest is ${-gain}% worse than persistence on this data: rainfall is hard to predict.`,
      heavy.length ? `Heavy rain expected in ${heavy.join(', ')}: keep the recharge pit ready.` : 'No heavy-rain month in the 6 months you selected.',
      `${S.importance[0].name} is the most important factor (${S.importance[0].value}%).`,
    ]
  }, [S, FC])

  const go = (id) => { setActive(id); const el = document.getElementById(id); if (el) el.scrollIntoView({ behavior: 'smooth' }) }
  const header = (
    <div className='hd' id='s1'>
      <h1>Rainwater Harvesting and Groundwater Recharge</h1>
      <div className='sub'>Upload a dataset, pick a date, and see the rainfall forecast and the store or recharge plan{S ? `. Last updated: ${S.updated}` : ''}</div>
    </div>
  )
  const overlay = busy && (
    <div className='overlay'><div className='spin' /><div>Training the models on your data. This takes about 10 to 90 seconds...</div></div>
  )
  const dataCard = <DataCard S={S} busy={busy} msg={msg} pending={pending} onUpload={onUpload} onPick={onPick} onReset={onReset} fileRef={fileRef} />

  if (err) return <div className='err'>{err}</div>
  if (!ready) return <div className='err' style={{ color: '#5b7092' }}>Loading...</div>
  if (!S) {
    return (
      <div className='shell'>
        <Side active={active} go={go} />
        <main>{header}{dataCard}{overlay}</main>
      </div>
    )
  }
  if (!dec) return <div className='err' style={{ color: '#5b7092' }}>Loading...</div>

  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }))
  const hasWeekly = S.metrics.some(isWeekly)
  const eff = hasWeekly ? mode : 'monthly'
  const rows = S.metrics.filter((m) => isWeekly(m) === (eff === 'weekly')).map((m) => ({ ...m, name: m.Model.replace(' (last month)', '').replace(' (weekly)', '').replace(' (monthly)', '') }))
  const mx = Math.max(...S.importance.map((i) => i.value))
  const pctBar = (v, m) => `${Math.min(100, (v / m) * 100)}%`
  const rain = cfg.auto ? S.forecast : cfg.rain
  const m = S.monthly
  const recent = m.dates.map((d, i) => ({ d, a: m.actual[i], s: m.sarima[i], b: m.seasonal[i] })).slice(-8)

  return (
    <div className='shell'>
      <Side active={active} go={go} />
      <main>
        {header}
        {dataCard}
        {overlay}

        <section className='g4'>
          <Kpi color='#1e6fe8' title='Tank level now' value={fmt(cfg.level)} unit='L' note={`${Math.round((cfg.level / cfg.cap) * 100)}% of capacity`} />
          <Kpi color='#2fb170' title={`Forecast rain, next ${S.dataset.step} (RF)`} value={S.forecast} unit='mm' note={`Period ending ${S.period_end} | SARIMA ${S.sarima_month}: ${S.sarima_next} mm`} />
          <Kpi color='#8b4fe0' title='Harvestable water' value={fmt(dec.harvestable_l)} unit='L' note={`for ${rain} mm on ${cfg.roof} m2`} />
          <Kpi color='#f58220' title='To recharge pit' value={fmt(dec.to_recharge_l)} unit='L' note={dec.overflow_l > 0 ? `Overflow lost: ${fmt(dec.overflow_l)} L` : 'No overflow'} />
        </section>

        <DateCard S={S} dateStr={dateStr} setDateStr={setDateStr} FC={FC} fcErr={fcErr} />

        {FC && (
          <section className='g g2' id='s2'>
            <div className='card'>
              <h3>Rainfall Trend and 6 Months from {FC.window.start}</h3>
              <div className='cap'>Monthly rainfall (mm). The shaded block is the 6 months that start at your date. The light band is the 80% forecast range (SARIMA).</div>
              <ResponsiveContainer width='100%' height={270}>
                <ComposedChart data={FC.chart}>
                  <CartesianGrid strokeDasharray='3 3' />
                  <XAxis dataKey='date' interval='preserveStartEnd' minTickGap={30} />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <ReferenceArea x1={FC.window.start} x2={FC.window.end} fill='#f58220' fillOpacity={0.1} />
                  <Area dataKey='range' name='Forecast range' stroke='none' fill='#1e6fe8' fillOpacity={0.15} connectNulls />
                  <Line dataKey='actual' name='Actual' stroke='#1e6fe8' strokeWidth={2} dot={{ r: 2 }} connectNulls />
                  <Line dataKey='forecast' name='Forecast (SARIMA)' stroke='#f58220' strokeWidth={2} strokeDasharray='6 4' dot={{ r: 3 }} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className='card'>
              <h3>6 Months from {FC.window.start}</h3>
              <div className='cap'>Rainfall and harvestable water for your roof</div>
              <table>
                <thead><tr><th>Month</th><th>Rain (mm)</th><th>Harvest (L)</th><th>Status</th></tr></thead>
                <tbody>
                  {FC.table.map((r) => (
                    <tr key={r.month} className={r.status === 'Heavy rain' ? 'w' : ''}>
                      <td>{r.month}{r.kind === 'actual' ? ' (actual)' : ''}</td>
                      <td>{r.rain}{r.kind === 'forecast' ? ` (${r.lower} to ${r.upper})` : ''}</td>
                      <td>{fmt(r.harvest_l)}</td>
                      <td className={r.status === 'Within range' ? 'ok' : ''}>{r.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <section className='g g3' id='s3'>
          <div className='card'>
            <h3>Model Performance Comparison</h3>
            <div className='cap'>Lower is better (MAE and RMSE, mm)</div>
            {hasWeekly && (
              <div className='tabs'>
                <button className={eff === 'monthly' ? 'on' : ''} onClick={() => setMode('monthly')}>Monthly</button>
                <button className={eff === 'weekly' ? 'on' : ''} onClick={() => setMode('weekly')}>Weekly</button>
              </div>
            )}
            <ResponsiveContainer width='100%' height={215}>
              <BarChart data={rows}>
                <CartesianGrid strokeDasharray='3 3' />
                <XAxis dataKey='name' tick={{ fontSize: 11 }} />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey='MAE' fill='#1e6fe8' />
                <Bar dataKey='RMSE' fill='#8b4fe0' />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className='card'>
            <h3>Feature Importance (Random Forest)</h3>
            <div className='cap'>Which factors have the biggest impact on the forecast?</div>
            {S.importance.map((f, i) => (
              <div className='fi' key={f.name}>
                <span>{f.name}</span>
                <div className='bar' style={{ width: `${(f.value / mx) * 100}%`, background: FI_COLORS[i % 6] }} />
                <b>{f.value}%</b>
              </div>
            ))}
          </div>
          <div className='card'>
            <h3>Key Insights</h3>
            {insights.map((t) => <div className='ins' key={t}><div>{t}</div></div>)}
          </div>
        </section>

        <section className='g g5' id='s4'>
          <div className='card'>
            <h3>Harvesting Planner</h3>
            <div className='cap'>Change your setup to see the decision</div>
            {SLIDERS.map(([k, label, unit, min, max, step]) => (
              <div key={k}>
                <label>{label} <output>{cfg[k]}{unit}</output></label>
                <input type='range' min={min} max={max} step={step} value={cfg[k]} onChange={(e) => set(k, +e.target.value)} />
              </div>
            ))}
            <label><span><input type='checkbox' checked={cfg.auto} onChange={(e) => set('auto', e.target.checked)} /> Use model forecast</span></label>
            <label>Rain this {S.dataset.step} <output>{rain} mm</output></label>
            <input type='range' min='0' max='400' step='1' disabled={cfg.auto} value={Math.round(rain)} onChange={(e) => set('rain', +e.target.value)} />
          </div>
          <div className='card'>
            <h3>Decision</h3>
            <div className='cap'>Store, recharge or release</div>
            <div className='rec'>{dec.recommendation}{dec.water_deficit ? ' (WARNING: tank runs dry)' : ''}</div>
            <div className='vs'>
              {[
                ['Tank after week', `${fmt(dec.tank_after_l)} L`, pctBar(dec.tank_after_l, cfg.cap), '#1e6fe8'],
                ['To recharge pit', `${fmt(dec.to_recharge_l)} L`, pctBar(dec.to_recharge_l, 5000), '#8a6238'],
                ['Overflow lost', `${fmt(dec.overflow_l)} L`, pctBar(dec.overflow_l, 5000), '#d4452a'],
                ['Days of supply', dec.days_of_supply, pctBar(dec.days_of_supply, 30), '#2fb170'],
              ].map(([label, val, h, c]) => (
                <div key={label}>
                  <div className='cy'><div className='fl' style={{ height: h, background: c }} /></div>
                  <b>{val}</b><span>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className='card g' id='s5' style={{ display: 'block' }}>
          <h3>Recent Predictions (test period)</h3>
          <div className='cap'>Last 8 months: actual rainfall vs SARIMA and the seasonal baseline</div>
          <table>
            <thead><tr><th>Month</th><th>Actual (mm)</th><th>SARIMA (mm)</th><th>Seasonal baseline</th><th>SARIMA error</th></tr></thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.d} className={Math.abs(r.s - r.a) > 60 ? 'w' : ''}>
                  <td>{r.d}</td><td>{r.a}</td><td>{r.s}</td><td>{r.b}</td><td>{Math.round(Math.abs(r.s - r.a))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  )
}
