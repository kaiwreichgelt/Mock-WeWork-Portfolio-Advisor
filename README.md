# WeWork Executive Portfolio Advisor

A classroom proof-of-concept dashboard built with Streamlit. It displays WeWork's portfolio of regions, markets, and locations with simulated operational and financial metrics, and includes an optional AI chat advisor that answers questions about the selected portfolio.

> **Note:** The region, market, and location hierarchy reflects real WeWork locations. All metrics (capacity, utilization, margins, lease timing, etc.) are randomly simulated each session and are not real data.

## Features

- **Portfolio filters:** Narrow the view by region, market, or individual location from the sidebar.
- **Portfolio overview:** Total capacity, utilization, available capacity, and pipeline for the current selection.
- **Summary cards:** Utilization, capacity, demand growth, operating margin, and next lease event for each region, market, or location.
- **AI Portfolio Advisor:** Ask questions such as "Which locations have high utilization but weak margins?" The advisor answers using only the data in the current view.

## Files

| File | Description |
|------|-------------|
| `app.py` | The Streamlit dashboard and AI chat |
| `portfolio.py` | The WeWork region/market/location hierarchy |

## Setup

1. **Install Python** (3.9 or newer).

2. **Install the required packages:**

   ```bash
   python -m pip install streamlit openai
   ```

3. **Add an OpenAI API key (optional).** The dashboard works without a key, but the AI chat requires one. Create a file named `api_secrets.py` in the same folder as `app.py`:

   ```python
   OPENAI_API_KEY = "your-api-key"
   ```

   ⚠️ Never upload `api_secrets.py` to GitHub. It is listed in `.gitignore` to prevent this.

4. **Run the app:**

   ```bash
   streamlit run app.py
   ```

   The dashboard opens in your browser automatically.

## How Metrics Are Calculated

- Seat counts (capacity, available capacity, pipeline) are summed.
- Rates (utilization, demand growth, operating margin) are weighted by capacity.
- Next lease event shows the soonest lease date among the selected locations.
- Metrics stay the same throughout a session and are regenerated when the app restarts. Nothing is saved to disk.

## Team

Group 12
