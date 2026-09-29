# WeWork Executive Portfolio Advisor — local classroom proof of concept.
# Install dependencies: python -m pip install streamlit openai
# Create api_secrets.py in the same directory:
#
# OPENAI_API_KEY = "your-api-key"
#
# Then run: streamlit run app.py
# Submit only app.py and the supplied portfolio.py. Never submit api_secrets.py.
# Metrics are simulated once per session; nothing is saved to disk.

from copy import deepcopy
import json
import random


def load_api_key():
    """Read the local API key, or return an empty string to disable AI chat."""
    try:
        from api_secrets import OPENAI_API_KEY
    except Exception:
        # Keep the dashboard usable if the file is missing or cannot be loaded.
        # Never display exception text: it could contain the credential.
        return ""
    return OPENAI_API_KEY.strip() if isinstance(OPENAI_API_KEY, str) else ""


API_KEY = load_api_key()

import streamlit as st
from openai import OpenAI, OpenAIError
from portfolio import WEWORK_PORTFOLIO


MODEL = "gpt-4.1-mini"
SYSTEM_PROMPT = """You are an executive decision-support advisor for WeWork.
Use ONLY the supplied current-scope portfolio JSON as factual evidence. Its
hierarchy is supplied; all operational and financial metrics are simulated.
Use the precomputed aggregates; do not independently aggregate the portfolio.
Conversation history supports follow-ups but is not a source of portfolio facts.
Respect the current scope even when earlier messages used a different scope.
If a question needs excluded locations, explain which filters to broaden.
Never invent revenue, costs, causes, trends, probabilities, or missing data.
Explain risks, opportunities, and conflicting signals with supplied numbers.
Distinguish observed metrics from possible explanations requiring investigation.
Separate user assumptions and temporary hypothetical scenarios from source facts;
never claim to change source data. Clarify ambiguous scenario inputs before
calculating; a demand increase does not automatically change utilization.
You may suggest Expand, Maintain, Optimize, Reduce / Consolidate, or Investigate
Further, with evidence and limitations. Treat pipeline as uncommitted demand.
State when evidence is insufficient. Keep answers concise and executive-oriented.
"""


def simulate_portfolio(source):
    """Copy the authoritative hierarchy and generate internally consistent metrics."""
    portfolio = deepcopy(source)
    rng = random.Random()
    for markets in portfolio.values():
        for locations in markets.values():
            for metrics in locations.values():
                capacity = rng.randrange(150, 1201, 25)
                occupied = round(capacity * rng.uniform(0.42, 0.97))
                metrics.update(
                    capacity=capacity,
                    utilization=occupied / capacity,
                    available_capacity=capacity - occupied,
                    demand_growth=round(rng.uniform(-0.12, 0.20), 3),
                    pipeline=round(capacity * rng.uniform(0.03, 0.35)),
                    operating_margin=round(rng.uniform(-0.10, 0.32), 3),
                    lease_remaining=rng.randint(3, 84),
                )
    return portfolio


def filter_locations(portfolio, region=None, market=None, location=None):
    """Flatten selected locations without changing the session portfolio."""
    return [
        {"region": r, "market": m, "location": name, **metrics}
        for r, markets in portfolio.items()
        for m, locations in markets.items()
        for name, metrics in locations.items()
        if (region is None or r == region)
        and (market is None or m == market)
        and (location is None or name == location)
    ]


def aggregate(rows):
    """Sum seats; weight rates by capacity; use the nearest lease event."""
    capacity = sum(row["capacity"] for row in rows)
    result = {"location_count": len(rows), "capacity": capacity}
    for metric in ("available_capacity", "pipeline"):
        result[metric] = sum(row[metric] for row in rows)
    for metric in ("utilization", "demand_growth", "operating_margin"):
        result[metric] = ( #type: ignore
            sum(row[metric] * row["capacity"] for row in rows) / capacity
            if capacity else 0
        )
    result["lease_remaining"] = min( #type: ignore
        (row["lease_remaining"] for row in rows), default=None
    )
    return result


def grouped_summaries(rows, fields):
    groups = {}
    for row in rows:
        identity = tuple(row[field] for field in fields)
        groups.setdefault(identity, []).append(row)
    return [
        {**dict(zip(fields, identity)), **aggregate(members)}
        for identity, members in groups.items()
    ]


def render_card(title, metrics):
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.caption(f"{metrics['location_count']} location(s) · Simulated metrics")
        left, middle, right = st.columns(3)
        left.metric("Utilization", f"{metrics['utilization']:.1%}")
        middle.metric("Capacity", f"{metrics['capacity']:,}")
        right.metric("Demand YoY", f"{metrics['demand_growth']:+.1%}")
        st.caption(
            f"Available capacity: {metrics['available_capacity']:,} seats  |  "
            f"Pipeline: {metrics['pipeline']:,} seats"
        )
        # Bars use fixed scales with their actual units labeled.
        # Negative margins cannot extend left of zero; preserve the signed label.
        margin = metrics["operating_margin"]
        st.progress(
            max(0.0, min(1.0, margin)),
            text=f"Operating margin: {margin:.1%}",
        )
        st.caption("0% — 100%" + (" · Negative margin; bar shown at zero" if margin < 0 else ""))
        lease_months = metrics["lease_remaining"]
        st.progress(
            max(0.0, min(1.0, lease_months / 100)),
            text=f"Next lease event: {lease_months} months",
        )
        st.caption("0 — 100 months" + (" · Bar capped at 100 months" if lease_months > 100 else ""))


def build_chat_context(rows, scope, history):
    """Send the same data as the cards, plus Python-computed scope rollups."""
    payload = {
        "scope": scope,
        "metrics_are_simulated": True,
        "definitions": {
            "capacity": "total seats",
            "utilization": "occupied seats / capacity; fraction",
            "available_capacity": "unoccupied seats",
            "pipeline": "uncommitted prospective seats over the next 12 months",
            "demand_growth": "year-over-year demand growth; fraction",
            "operating_margin": "operating profit / revenue; fraction (revenue not supplied)",
            "lease_remaining": "months from session start to next lease event",
            "aggregation": "sum seats; capacity-weight rates; minimum lease months",
        },
        "scope_summary": aggregate(rows),
        "region_summaries": grouped_summaries(rows, ["region"]),
        "market_summaries": grouped_summaries(rows, ["region", "market"]),
        "locations": rows,
    }
    messages = [{"role": "developer", "content": "Current portfolio data:\n" + json.dumps(payload)}]
    # Full session history keeps even early follow-up references available.
    for message in history:
        content = message["content"]
        if message["role"] == "user":
            content = f"[Scope when asked: {message['scope']}]\n{content}"
        messages.append({"role": message["role"], "content": content})
    return messages


def ask_advisor(api_key, messages):
    """The only external service call; edit MODEL above to change the model."""
    with OpenAI(api_key=api_key, timeout=45.0, max_retries=0) as client:
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM_PROMPT,
            input=messages,
            max_output_tokens=1200,
            store=False,
        )
    return response.output_text.strip()


def main():
    st.set_page_config(page_title="WeWork Executive Portfolio Advisor", page_icon="🏢", layout="wide")
    st.markdown(
        """<style>
        .st-key-portfolio_cards [data-testid="stMetricValue"] {
            font-size: 1.5rem;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    if "portfolio" not in st.session_state:
        st.session_state.portfolio = simulate_portfolio(WEWORK_PORTFOLIO)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    portfolio = st.session_state.portfolio

    with st.sidebar:
        st.title("WeWork")
        st.caption("EXECUTIVE PORTFOLIO ADVISOR")
        st.divider()
        st.subheader("Portfolio filters")
        region = st.selectbox("Region", [None, *portfolio], format_func=lambda x: x or "All regions")
        eligible = filter_locations(portfolio, region)
        market = st.selectbox(
            "Market", [None, *dict.fromkeys(row["market"] for row in eligible)],
            format_func=lambda x: x or "All markets", key=f"market_{region}",
        )
        eligible = filter_locations(portfolio, region, market)
        # Full paths keep identical street names in different markets distinct.
        location_path = st.selectbox(
            "Location", [None, *[(row["region"], row["market"], row["location"]) for row in eligible]],
            format_func=lambda x: f"{x[2]} · {x[1]}" if x else "All locations",
            key=f"location_{region}_{market}",
        )
        st.divider()
        st.caption("People. Places. Possibilities.")
        st.caption("Metrics stay fixed throughout this session.")

    rows = filter_locations(portfolio, *(location_path or (region, market, None)))
    if location_path:
        scope = " / ".join(("United States", *location_path))
        cards = [(location_path[2], aggregate(rows))]
    else:
        scope = " / ".join(["United States", *dict.fromkeys(row["region"] for row in rows)]) if market else "United States"
        if market:
            scope += f" / {market}"
        elif region:
            scope += f" / {region}"
        fields = ["region", "market", "location"] if market else ["region", "market"] if region else ["region"]
        cards = [(item[fields[-1]], item) for item in grouped_summaries(rows, fields)]

#    st.caption("PEOPLE. PLACES. POSSIBILITIES.")
    st.title("WeWork Executive Portfolio Advisor")
#    st.info(
#        "Classroom proof of concept · The supplied hierarchy represents real WeWork "
#        "regions, markets, and locations. All operational and financial metrics are simulated. "
#        "Production analysis would require WeWork's internal systems."
#    )
    st.subheader("Portfolio overview")
    st.caption(f"{scope} · {len(rows)} locations")
    summary = aggregate(rows)
    columns = st.columns(4)
    for column, label, value in zip(columns, ["Total capacity", "Utilization", "Available capacity", "Pipeline"], [
        f"{summary['capacity']:,} seats", f"{summary['utilization']:.1%}",
        f"{summary['available_capacity']:,} seats", f"{summary['pipeline']:,} seats",
    ]):
        column.metric(label, value)
    with st.container(key="portfolio_cards"):
        for start in range(0, len(cards), 4):
            for column, (title, metrics) in zip(st.columns(4), cards[start:start + 4]):
                with column:
                    render_card(title, metrics)
    st.caption(
        "Rates are capacity-weighted. Next lease event is the minimum months remaining. "
        "Demand growth is year-over-year; pipeline is uncommitted prospective seats over 12 months."
    )

    st.divider()
    st.subheader("✨ Ask the Portfolio Advisor")
    st.caption(f"Current analytical scope: {scope}. Earlier messages retain their original scope.")
    st.caption("Try: Which locations have high utilization but weak margins? Which lease decisions deserve attention?")
    ready = bool(API_KEY and API_KEY not in {"your-api-key", "key-goes-here"})
    if not ready:
        st.info("AI chat requires OPENAI_API_KEY in a local api_secrets.py beside app.py. Add your key and restart the app. The dashboard is available without a key.")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.caption(message["scope"])
            st.markdown(message["content"])
    question = st.chat_input("Ask a question about your portfolio…", disabled=not ready)
    if question:
        message = {"role": "user", "content": question, "scope": scope}
        with st.chat_message("user"):
            st.caption(scope)
            st.markdown(question)
        try:
            with st.spinner("Analyzing the selected portfolio…"):
                answer = ask_advisor(API_KEY, build_chat_context(rows, scope, [*st.session_state.messages, message]))
            if not answer:
                st.warning("The advisor returned no text. Please try your question again.")
                return
        except OpenAIError:
            st.error("AI chat could not complete the request. Check your API key, account access, quota, and connection, then try again. Portfolio data are unchanged.")
            return
        st.session_state.messages.extend([message, {"role": "assistant", "content": answer, "scope": scope}])
        with st.chat_message("assistant"):
            st.caption(scope)
            st.markdown(answer)


if __name__ == "__main__":
    main()
