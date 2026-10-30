# Smart Rainwater Harvesting: Full-Stack ML Project (v4)

React dashboard + Flask REST API + ML models (persistence baselines, seasonal persistence, SARIMA/ARIMA, Random Forest).

## New in v4
- **Upload any file**: CSV, TSV, Excel, JSON or text, even without an extension. Daily, weekly or monthly rows. Missing values are allowed.
  If the date or rainfall column cannot be detected, the dashboard shows a dropdown so you can choose it.
- **Predict by Date**: choose a date. The prediction, the chart and the table cover the 6 months that start at that date.
  Future dates are forecast (up to about 3 years ahead, with a wider range the further away), past dates show your data.

## Run
Double-click start.bat, or: cd backend, python -m pip install -r requirements.txt, python app.py, open http://127.0.0.1:5000

## Files accepted (examples)
- date + rainfall (+ any other numeric columns) with one row per day, week or month
- wide tables: Year, Jan, Feb, ... Dec (rainfall per month)
- NASA POWER downloads (YEAR, MO, DY columns, with header text) work as they are
- download_dataset.py (separate) downloads a real NASA POWER daily dataset for any place

## Layers
| Layer | Files |
|---|---|
| Data + ML | backend/pipeline.py, features.py |
| REST API | backend/app.py: /api/upload, /api/summary, /api/forecast-from, /api/decide, /api/reset, /api/health |
| Optional default dataset | backend/train_model.py (NASA POWER, needs internet) |
| Frontend | frontend/src/App.jsx (built into frontend/dist) |

## Algorithms
Persistence baselines, seasonal persistence, SARIMA (monthly, 36 months ahead with an 80% range), Random Forest (weekly or monthly lag features of every column) with feature importance.
Time-based split: the first 80% of the history trains the models, the last 20% tests them.
