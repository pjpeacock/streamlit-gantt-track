"""Demo for streamlit_gantt_track -- run with:

    streamlit run example.py

College is a real activity with its own independent start/end (18-22). Leaving the Nest and New
Car are independent milestones -- New Car can be dragged anywhere, including past or on top of
College or Leaving the Nest, with nothing breaking. Childhood and Independence are labeled ranges:
Childhood's end is a fixed value (18); Independence's start is a reference to the Leaving the Nest
milestone's live value, so dragging that milestone pushes Independence's start with it
automatically, without Independence being a draggable thing of its own.
"""
import streamlit as st
from streamlit_gantt_track import gantt_track

st.set_page_config(page_title="gantt_track demo", layout="wide")

st.title("gantt_track")
st.write(
    "A Gantt-chart-style interactive timeline: activities (their own independent start/end), "
    "milestones (a single point in time), and labeled ranges (pure visual scaffolding, not "
    "draggable) all share one axis, none coupled to any other item on it."
)

result = gantt_track(
    min_value=1, max_value=30,
    items=[
        {"id": "college", "type": "activity", "start": 18, "end": 22,
         "icon": "\U0001f393", "label": "College", "color": "#1e88e5"},
        {"id": "nest", "type": "milestone", "value": 25,
         "icon": "\U0001f680", "label": "Leaving the Nest", "color": "#e53935"},
        {"id": "car", "type": "milestone", "value": 16,
         "icon": "\U0001f697", "label": "New Car", "color": "#8e24aa"},
    ],
    ranges=[
        {"id": "childhood", "label": "Childhood", "color": "#90caf9", "text_color": "#0d47a1",
         "start": {"type": "fixed", "value": 1},
         "end": {"type": "fixed", "value": 18}},
        {"id": "independence", "label": "Independence", "color": "#ef9a9a", "text_color": "#b71c1c",
         "start": {"type": "ref", "item": "nest", "endpoint": "value"},
         "end": {"type": "fixed", "value": 30}},
    ],
    key="demo_timeline",
)

st.divider()
st.write("Values:", result)
