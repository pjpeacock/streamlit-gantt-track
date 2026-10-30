# streamlit-gantt-track

One draggable Gantt-style track for Streamlit -- a single row/lane, not a full multi-row Gantt
chart (see **Composing multiple tracks** below for building one of those). Three independent
layers share one `[min_value, max_value]` axis, none coupled to any other item on it:

- **Activities** -- their own independent `(start, end)` pair, a real duration with two draggable
  handles and a connecting bar. The only constraint is `end >= start` against its own other
  handle; an activity has no relationship to any other item's position, so gaps between items are
  completely normal.
- **Milestones** -- a single point in time, freely draggable, no ordering constraint at all.
- **Ranges** -- pure labeled visual scaffolding drawn inside the track itself, *not* a draggable
  item and not backed by real data of its own. Each endpoint is independently either a fixed value
  or a reference to a real item's live position, so a range can track a milestone (e.g.
  "Independence" starting wherever a "Leaving the Nest" milestone currently sits) without being a
  draggable thing in its own right.

Siblings in the same family: [streamlit-segment-slider](https://github.com/pjpeacock/streamlit-segment-slider)
(drag dividing points to split a range into connected, ordered segments) and
[streamlit-marker-slider](https://github.com/pjpeacock/streamlit-marker-slider) (independent,
freely-draggable point markers, no ranges). This component is the one for when you need all
three kinds of thing on the same shared axis at once.

Built on [Streamlit Custom Components v2](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component)
and [D3's drag/selection modules](https://d3js.org/d3-drag) (loaded from a CDN at runtime -- see
**Requirements** below). Pure Python, inline component -- no npm install, no build step.

[GitHub repository](https://github.com/pjpeacock/streamlit-gantt-track)

## Install

```bash
pip install streamlit-gantt-track
```

## Usage

```python
import streamlit as st
from streamlit_gantt_track import gantt_track

result = gantt_track(
    min_value=1,
    max_value=30,
    items=[
        {"id": "college", "type": "activity", "start": 18, "end": 22,
         "icon": "\U0001f393", "label": "College", "color": "#1e88e5"},
        {"id": "nest", "type": "milestone", "value": 25,
         "icon": "\U0001f680", "label": "Leaving the Nest", "color": "#e53935"},
    ],
    ranges=[
        {"id": "childhood", "label": "Childhood", "color": "#90caf9", "text_color": "#0d47a1",
         "start": {"type": "fixed", "value": 1},
         "end": {"type": "fixed", "value": 18}},
        {"id": "independence", "label": "Independence", "color": "#ef9a9a", "text_color": "#b71c1c",
         "start": {"type": "ref", "item": "nest", "endpoint": "value"},
         "end": {"type": "fixed", "value": 30}},
    ],
    key="child_timeline",
)
# result == {"college": {"start": 18.0, "end": 22.0}, "nest": 25.0}
```

Run `example.py` in this repo for a live demo:

```bash
streamlit run example.py
```

## API

```python
gantt_track(
    min_value,
    max_value,
    items,
    ranges=None,
    *,
    step=1,
    key=None,
    height=280,
    track_height=20,
    corner_radius=0,
) -> dict[str, float | dict[str, float]]
```

| Parameter | Description |
|---|---|
| `min_value`, `max_value` | The full range of the track. |
| `items` | A list of dicts, one per draggable item. Activity: `{"id", "type":"activity", "start", "end", "icon", "label", "color"}`. Milestone: `{"id", "type":"milestone", "value", "icon", "label", "color"}`. `id` must be unique within the call (it's the key in the returned dict); `start`/`end`/`value` are only used as that item's seed position the first time this widget's `key` is ever rendered -- after that, session state owns the live value. |
| `ranges` | Optional list of dicts, one per labeled range: `{"id", "label", "color", "text_color", "start", "end"}`. `start`/`end` are each either `{"type": "fixed", "value": N}` or `{"type": "ref", "item": item_id, "endpoint": "start"\|"end"\|"value"}` -- a ref endpoint tracks that item's live position. `text_color` is optional (defaults to white). A range whose resolved width is non-positive (`end <= start`) simply isn't drawn that render, not an error. |
| `step` | Granularity every draggable handle snaps to. |
| `key` | Required to track state the normal Streamlit way if you use more than one of these on a page. See **Limitations** for when it needs to change, not just stay fixed. |
| `height` | Component height in pixels. |
| `track_height` | Track thickness in pixels (and the height of each range drawn inside it). |
| `corner_radius` | Corner radius in pixels for the track and ranges. `0` (the default) is square. Activity/milestone handle shapes are unaffected -- those read as handles, not "the timeline" itself. |

Returns a dict `{item_id: value}` for every item in `items` -- a plain `float` for a milestone,
`{"start": float, "end": float}` for an activity. Ranges are never part of the return value;
they're derived presentation, not state of their own.

## Composing multiple tracks

This component is one row, not a full chart -- but stacking several instances gets you most of
the way to one without any new component work. Each instance independently measures its own
track's rendered pixel width and maps `[min_value, max_value]` onto it, so giving several
instances the *same* `min_value`/`max_value` in equal-width containers already aligns their axes
as real rows of one chart.

The one piece that otherwise reads as redundant in a stack -- every instance repeating the same
min/max axis numbers -- has a direct fix: pass `show_range_labels=False` on every instance except
the one you want to carry the shared axis row (typically the bottom one). A thin wrapper that also
adds a left-hand row label (whose track is this) would turn a stack of these into a fully composed
Gantt chart -- not built here, but the one real blocker to it is already solved.

One remaining rough edge, visible once you actually stack rows: each instance still reserves its
full top padding for milestone/tooltip clearance even on a row with no milestones at all (e.g. a
row with only activities), which leaves more dead vertical space above that row's track than it
needs. Not fixed here -- a caller can shrink `height` per row today to compensate, but a cleaner
fix (sizing the padding from what each row actually contains) is future work.

## Dark mode and emoji

Color emoji glyphs (a graduation cap, for instance) are static color images baked into the font --
there's no mechanism in any browser or OS that recolors them for dark mode, and `filter:
hue-rotate()` doesn't help either (it leaves black/gray pixels alone, since there's nothing to
rotate). Milestone badges use a fixed light background (not theme-following) for exactly this
reason -- a dark-inked icon would nearly disappear against a dark badge.

## Requirements

- Streamlit >= 1.61.1 (verified against this version; `st.components.v2` is a newer API, so older
  releases won't have it).
- A network path to `cdn.jsdelivr.net` at runtime -- `d3-drag`/`d3-selection` load from there as
  ES modules (pinned to `3.0.0`, not `latest`), not from a bundled/vendored copy. If your
  deployment blocks that CDN, this component won't render.

## Limitations

- **The `key` needs to change, not just stay fixed, when the *set* of items changes shape** --
  e.g. going from 2 items to 3, or swapping which ids are present. The component keeps its own
  live drag state in session state under `key`; reusing the same key across an incompatible shape
  change can hand the new render a value for an id it no longer has, or miss one it just gained.
- **No collision/overlap handling for labels.** Two items dragged close together (or a milestone
  landing right at a range boundary) can visually overlap -- nothing prevents this or
  auto-spaces labels apart.
- **Ranges are day/unit-granularity linear math, same as the axis itself** -- there's no
  calendar-aware stepping (e.g. "snap to the nearest whole month," where month lengths vary).
- **Shadow DOM isolation.** Like its siblings, this component renders with `isolate_styles=True`
  (the CCv2 default), so it's in a shadow root: app-level CSS injected via
  `st.markdown(unsafe_allow_html=True)` won't reach its internals, and a plain
  `document.querySelector` (including from most browser automation/testing tools) won't find them
  either -- use a tool that pierces shadow roots (e.g. Playwright's own locators do this
  automatically).
- **`st.session_state[key]` is a dict, not the plain shape `gantt_track()` returns.** Components v2
  stores a mounted component's state as `{"value": {...}}` under its `key`. Use `gantt_track()`'s
  own return value rather than reading `st.session_state[key]` directly, unless you specifically
  want that wrapper shape.

## License

MIT -- see [LICENSE](LICENSE).
