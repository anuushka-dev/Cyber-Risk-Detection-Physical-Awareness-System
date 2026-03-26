# dashboard/streamlit_demo_v2.py
"""
Streamlit Demo Dashboard (v2)
- Real-time tail of logs (logs/events.jsonl)
- Attack timeline (events per minute)
- Label counts bar chart
- API tester (call /predict using dataset samples)
- Health / last prediction card

Usage:
  pip install streamlit pandas requests altair
  streamlit run dashboard/streamlit_demo_v2.py
"""

import streamlit as st
import pandas as pd
import json
import time
import requests
from pathlib import Path
from collections import Counter, defaultdict
import altair as alt
from datetime import datetime, timezone

from pathlib import Path

# 🔥 correct root
PROJECT_ROOT = Path(__file__).resolve().parent

# 🔥 your actual folder name (Dataset)
DATASET_PATH = PROJECT_ROOT / "Dataset" / "test.parquet"

FEATURE_LIST_PATH = PROJECT_ROOT / "model" / "feature_list.json"
EVENTS_PATH = PROJECT_ROOT / "logs" / "events.jsonl"

API_PREDICT = "http://127.0.0.1:8000/predict"
API_HEALTH = "http://127.0.0.1:8000/health"
API_MODEL_INFO = "http://127.0.0.1:8000/model-info"

st.set_page_config(page_title="AI IDS — Demo Dashboard", layout="wide")
st.title("AI IDS — Live Demo Dashboard")

# helper: resilient JSONL reader
def read_events(path: Path, max_lines: int = 500):
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        lines = text.splitlines()[-max_lines:]
        events = []
        for l in lines:
            l = l.strip()
            if not l:
                continue
            try:
                obj = json.loads(l)
            except Exception:
                # fallback: try to parse single kv pairs or skip
                obj = {"raw": l}
            # normalize timestamp
            if "timestamp" in obj:
                pass
            elif "first_seen" in obj:
                # likely epoch seconds
                try:
                    ts = float(obj["first_seen"])
                    obj["timestamp"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except Exception:
                    obj["timestamp"] = None
            elif "time" in obj:
                obj["timestamp"] = obj.get("time")
            else:
                # if no timestamp, use file modified time
                try:
                    mtime = path.stat().st_mtime
                    obj["timestamp"] = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                except Exception:
                    obj["timestamp"] = datetime.now(timezone.utc).isoformat()
            events.append(obj)
        return events
    except Exception as e:
        st.error(f"Failed reading events file: {e}")
        return []

@st.cache_data
def load_dataset_and_features():
    df = pd.read_parquet(DATASET_PATH)
    feature_list = json.load(open(FEATURE_LIST_PATH, "r", encoding="utf-8"))
    return df, feature_list

# left and right columns
col1, col2 = st.columns([1, 1.6])

# top row: health + last prediction
with st.container():
    health_col, last_col = st.columns([1, 2])
    # Health card
    with health_col:
        st.subheader("System Health")
        try:
            r = requests.get(API_HEALTH, timeout=2)
            r.raise_for_status()
            h = r.json()
            st.success("API: up")
            st.write(f"Model loaded: `{h.get('model_loaded')}`")
            st.write(f"Uptime (s): {h.get('uptime_seconds')}")
        except Exception as e:
            st.error("API: unreachable")
            st.write(str(e))
    # Last prediction card (reads last line of events.jsonl)
    with last_col:
        st.subheader("Most recent detection")
        events = read_events(EVENTS_PATH, max_lines=10)
        if events:
            last = events[-1]
            label = last.get("label", "N/A")
            conf = last.get("confidence", None) or last.get("probability", None)
            st.metric("Last label", label)
            if conf is not None:
                st.metric("Confidence", f"{conf:.3f}")
            # show mini row
            st.json(last)
        else:
            st.info("No detections yet (run monitor in SIMULATE mode)")

# Left: API tester
with col1:
    st.header("API Tester")
    df, feature_list = load_dataset_and_features()
    classes = sorted(df["Label"].unique().tolist())
    picker = st.selectbox("Pick class to test", ["Random sample"] + classes)
    n_samples = st.slider("Samples", min_value=1, max_value=5, value=1)
    if st.button("Run test"):
        rows = []
        for _ in range(n_samples):
            if picker == "Random sample":
                s = df.sample(1)
            else:
                s = df[df["Label"] == picker].sample(1)
            true_label = s["Label"].values[0]
            features = s[feature_list].values.tolist()[0]
            try:
                resp = requests.post(API_PREDICT, json={"features": features}, timeout=5)
                resp.raise_for_status()
                result = resp.json().get("result", {})
                pred = result.get("label")
                conf = result.get("confidence")
                rows.append({"true": true_label, "pred": pred, "confidence": conf})
            except Exception as e:
                rows.append({"true": true_label, "pred": None, "confidence": None, "error": str(e)})
        st.table(pd.DataFrame(rows))

# Right: live charts and tail
with col2:
    st.header("Live Analytics")
    auto = st.checkbox("Auto-refresh every 2s", value=True)
    lines_to_show = st.slider("Events to show", min_value=10, max_value=500, value=100)
    chart_placeholder = st.empty()
    table_placeholder = st.empty()

    def build_charts():
        events = read_events(EVENTS_PATH, max_lines=1000)
        if not events:
            chart_placeholder.info("No events yet. Start monitor (simulate) to generate events.")
            table_placeholder.empty()
            return
        df_events = pd.json_normalize(events)
        # ensure timestamp
        if "timestamp" in df_events.columns:
            df_events["ts"] = pd.to_datetime(df_events["timestamp"], errors="coerce")
        else:
            df_events["ts"] = pd.Timestamp.now()
        # line: events per minute over last N minutes
        df_events = df_events.dropna(subset=["ts"])
        df_events = df_events.sort_values("ts")
        df_events["minute"] = df_events["ts"].dt.floor("T")
        counts = df_events.groupby("minute").size().reset_index(name="count")
        if counts.empty:
            chart_placeholder.info("Not enough events to render chart yet.")
        else:
            line = alt.Chart(counts).mark_line(point=True).encode(
                x=alt.X("minute:T", title="Time"),
                y=alt.Y("count:Q", title="Events per minute"),
                tooltip=["minute:T", "count:Q"]
            ).properties(height=250, width=700)
            chart_placeholder.altair_chart(line, use_container_width=True)

        # bar: label counts
        label_col = None
        # try common label field names
        for c in ("label", "predicted_label", "Label"):
            if c in df_events.columns:
                label_col = c
                break
        if label_col is None:
            table_placeholder.info("No label column in events; showing raw.")
            table_placeholder.dataframe(df_events.tail(lines_to_show))
            return
        counts_labels = df_events[label_col].value_counts().reset_index()
        counts_labels.columns = ["label", "count"]
        bars = alt.Chart(counts_labels).mark_bar().encode(
            x=alt.X("label:N", sort="-y", title="Label"),
            y=alt.Y("count:Q", title="Count"),
            tooltip=["label", "count"]
        ).properties(height=250)
        st.subheader("Recent label counts")
        st.altair_chart(bars, use_container_width=True)

        # tail
        last_rows = df_events.tail(lines_to_show).copy()
        # make confidence readable
        if "confidence" in last_rows.columns:
            last_rows["confidence"] = last_rows["confidence"].apply(lambda x: round(x, 4) if pd.notnull(x) else x)
        table_placeholder.dataframe(last_rows.sort_values("ts", ascending=False), use_container_width=True)

    build_charts()
    if auto:
        while True:
            time.sleep(2)
            build_charts()