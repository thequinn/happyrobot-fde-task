from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# The argument, "API_BASE_URL", is the base URL for the FastAPI server.
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# The argument, "LOAD_API_KEY", is the shared secret for the FastAPI server.
LOAD_API_KEY = os.getenv("LOAD_API_KEY")


@st.cache_data(ttl=60)
def fetch_metrics_summary(limit: Optional[int] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if limit is not None:
        params["limit"] = limit

    headers: Dict[str, str] = {}
    if LOAD_API_KEY:
        headers["Authorization"] = f"Bearer {LOAD_API_KEY}"

    response = requests.get(
        f"{API_BASE_URL.rstrip('/')}/metrics/summary",
        headers=headers,
        params=params,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def render_metric_cards(metrics: Dict[str, Any]) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Calls", metrics.get("total_calls", 0))

    sentiment = metrics.get("sentiment_distribution", {})
    positive = sentiment.get("positive", 0)
    neutral = sentiment.get("neutral", 0)
    negative = sentiment.get("negative", 0)

    col2.metric("Positive Sentiment", positive)
    col3.metric("Negative Sentiment", negative)

    if neutral and neutral > 0:
        st.info(f"Neutral sentiment calls: {neutral}")


def render_distribution_charts(metrics: Dict[str, Any]) -> None:
    sentiment_distribution = metrics.get("sentiment_distribution", {})
    outcome_breakdown = metrics.get("outcome_breakdown", {})

    if sentiment_distribution:
        st.subheader("Sentiment Distribution")
        st.bar_chart(sentiment_distribution)

    if outcome_breakdown:
        st.subheader("Call Outcome Breakdown")
        st.bar_chart(outcome_breakdown)


def main() -> None:
    st.set_page_config(page_title="Call Metrics Dashboard", layout="wide")
    st.title("Inbound Call Metrics")
    st.caption(
        "Visualization powered by the HappyRobot. "
        "Ensure API_BASE_URL and LOAD_API_KEY are set for authenticated access."
    )

    limit = st.sidebar.number_input(
        "Records to include", min_value=1, max_value=10_000, value=500, step=50
    )

    try:
        metrics = fetch_metrics_summary(limit=limit)
    except requests.HTTPError as exc:
        st.error(f"API responded with an error: {exc.response.text}")
        return
    except requests.RequestException as exc:
        st.error(f"Failed to reach API: {exc}")
        return

    if not metrics or metrics.get("total_calls", 0) == 0:
        st.warning("No metrics available. Seed call_logs and try again.")
        return

    render_metric_cards(metrics)
    render_distribution_charts(metrics)


if __name__ == "__main__":
    main()
