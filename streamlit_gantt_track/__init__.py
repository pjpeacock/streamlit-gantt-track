"""One draggable Gantt-style track for Streamlit -- a single row/lane, not a full multi-row Gantt
chart (stack several instances sharing the same min_value/max_value to build one of those; see
README). Three independent layers share one [min_value, max_value] axis, none coupled to any
other item on the line:

  - "ranges": pure labeled visual scaffolding, drawn INSIDE a thickened track, each with its own
    background and text color. A range is NOT a draggable item and NOT backed by real data of its
    own -- it exists purely to label a span of the axis for the viewer (e.g. "Childhood",
    "Independence"). Each endpoint is independently either a fixed value or a reference to a real
    item's current position (`{"type": "ref", "item": id, "endpoint": "start"|"end"|"value"}`),
    so a range can track a milestone's live position (e.g. "Independence" starting wherever a
    "Leaving the Nest" milestone currently sits) without being a draggable thing in its own right,
    and without hardcoding which milestone that has to be.
  - "milestones": a single point in time, above the track. Three interchangeable presentation
    styles (`milestone_style` -- see `gantt_track()`'s own docstring): "badge" (circular
    background + floating value tooltip + label below), "bare" (plain icon with its value inline
    beside it, label below), "row" (value in a box, then icon+label together on the line closest
    to the bar).
  - "activities": an independent (start, end) pair -- a real duration with its own two draggable
    handles below the track and a connecting bar between just those two handles. The only
    constraint is end >= start against its own other handle; an activity has no relationship to
    any other item's position, so gaps between items (nothing covering part of the axis) are
    completely normal, not something this forces you to avoid.

    from streamlit_gantt_track import gantt_track

    result = gantt_track(
        min_value=1, max_value=30,
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

Built on [Streamlit Custom Components v2](https://docs.streamlit.io/develop/api-reference/custom-components/st.components.v2.component)
and [D3's drag/selection modules](https://d3js.org/d3-drag) (loaded from a CDN at runtime -- see
README's Requirements section). Pure Python, inline component -- no npm install, no build step.
See example.py for a runnable demo.
"""
import streamlit as st

__all__ = ["gantt_track"]

HTML = """
<div class="gc-widget">
  <div class="gc-track-wrap">
    <div class="gc-track"></div>
    <div class="gc-ranges"></div>
    <div class="gc-activities"></div>
    <div class="gc-milestones"></div>
    <div class="gc-range-labels">
      <span class="gc-min-label"></span>
      <span class="gc-max-label"></span>
    </div>
  </div>
</div>
"""

CSS = """
.gc-widget {
    width: 100%;
    /* border-box -- gc-bordered's own padding/border must come out of the 100% width, not add to
       it. Without this, the bordered variant overflows its host by the padding+border amount and
       triggers a horizontal scrollbar (found live: the whole track rendered partially cropped). */
    box-sizing: border-box;
    font-family: var(--st-font);
    color: var(--st-text-color);
    /* Dragging fast enough can sweep the mouse over neighboring text (labels, tooltips, range
       text), and the browser's default text-selection would otherwise kick in mid-drag,
       highlighting whatever the cursor passed over -- touch-action:none on the handles themselves
       stops touch scrolling but does nothing for mouse-driven text selection. One blanket rule
       here covers every descendant instead of chasing it element by element. */
    user-select: none;
    -webkit-user-select: none;
    -moz-user-select: none;
}
.gc-widget.gc-bordered {
    border: 1px solid var(--st-border-color);
    border-radius: var(--st-base-radius);
    padding: 0 1rem;
}

.gc-track-wrap {
    /* Left/right only here -- top/bottom are set inline from JS (milestoneClearance-driven),
       since how much clearance is actually needed above the track depends on
       show_milestone_badges (a bare icon+value row needs much less room than a 24px badge +
       floating tooltip box did). A too-tight value here silently clips a tooltip or label
       against this component's own fixed-height host, with no scrollbar and no visible sign
       anything's missing -- found live more than once, so these are deliberately generous rather
       than trimmed to the exact pixel. */
    padding: 0 14px;
    position: relative;
}

.gc-track {
    /* height/border-radius set inline from track_height/corner_radius (set in JS) -- these are
       per-call parameters, not something a shared stylesheet authored once at import time could
       express. */
    background: var(--st-secondary-background-color);
    position: relative;
}

/* ---- Ranges: pure labeled scaffolding INSIDE the track itself, not a separate floating label.
   top/height are set inline in JS to exactly overlay .gc-track's own box (this layer's own zero-
   point starts at .gc-track's BOTTOM edge like every sibling layer here, same as every other
   per-item element below -- shifting up by the track's own height re-aligns it with the track's
   TOP edge instead). ---- */
.gc-ranges { position: relative; height: 0; }
.gc-range {
    position: absolute;
    border-radius: inherit;
}
/* The label is a SEPARATE free-floating element, not text set directly on .gc-range -- a short
   range (e.g. a one-month sabbatical) is often narrower than its own label text, and clipping to
   its own box (the old behavior) meant it could never show a label at all. Anchored at the
   range's own midpoint (left + width/2, translateX(-50%)) with no width constraint of its own,
   so the text can overflow past the colored box into the empty track space around it -- hidden
   only if it would overflow the TRACK's own edges (checked in JS), the same fallback the "row"
   milestone style already uses for its own label. */
.gc-range-label {
    position: absolute;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: translateX(-50%);
    /* color: NOT set here -- it's per-range (r.text_color), set inline in JS, same reasoning as
       before: a flat fixed color doesn't reliably read against an arbitrary caller background. */
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
    pointer-events: none;
}

/* ---- Milestones: above the track. top is set inline in JS (-(track_height + 56)) since the
   clearance needed depends on the caller's own track_height, not a fixed value a shared
   stylesheet could express -- the label trails 28px below the badge's own top edge, so the
   group's clearance has to account for the label too, not just the badge itself. ---- */
.gc-milestones { position: relative; height: 0; }
.gc-milestone {
    position: absolute;
    width: 24px;
    height: 24px;
    margin-left: -12px;
    border-radius: 50%;
    /* Fixed light background, not theme-following -- most emoji (a graduation cap especially)
       are drawn mostly in black/dark ink, a fixed platform glyph color no CSS can repaint;
       against a dark-mode background that dark ink nearly disappears. */
    background: #fdfdfd;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    cursor: grab;
    touch-action: none;
    z-index: 5;
}
.gc-milestone:active { cursor: grabbing; }
/* ---- Bare milestones (show_milestone_badges=False): no circle, no background -- just the icon
   and its "(value)" sitting plainly above the track. The badge's fixed-width centering
   (margin-left: -12px against a known 24px box) doesn't work once the box is "however wide the
   icon+value text happens to be," so this switches to a percentage-based translateX(-50%)
   instead -- correct regardless of actual rendered width. ---- */
.gc-milestone.gc-milestone-bare {
    width: auto;
    height: auto;
    margin-left: 0;
    border: none;
    background: none;
    border-radius: 0;
    transform: translateX(-50%);
    display: flex;
    align-items: baseline;
    gap: 0.2rem;
    font-size: 16px;
}
.gc-milestone-label {
    position: absolute;
    top: 28px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
    pointer-events: none;
}
/* Shorter clearance than the badge default -- a bare icon+value row is one line of text, not a
   24px circle, so the label can trail it much closer. */
.gc-milestone-bare .gc-milestone-label { top: 20px; }
.gc-tooltip-above {
    position: absolute;
    bottom: 160%;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.75rem;
    color: var(--st-text-color);
    background: var(--st-background-color);
    border: 1px solid var(--st-border-color);
    border-radius: var(--st-base-radius);
    padding: 0.15rem 0.4rem;
    white-space: nowrap;
    pointer-events: none;
}
/* Bare mode: back to plain, static, inline text right next to the icon -- not an absolutely-
   positioned bordered box floating above it. */
.gc-milestone-bare .gc-tooltip-above {
    position: static;
    bottom: auto;
    left: auto;
    transform: none;
    background: none;
    border: none;
    padding: 0;
    font-weight: 600;
}

/* ---- "row" milestones: a mirror of how an activity's own handles are laid out (value in a
   bordered box, then the actual handle closest to the bar) -- here, value box on top, then an
   icon+label row sitting closest to the bar. Not a true mirror (the label sits beside the icon,
   not on its own third line) -- direct request, "keeps it to 2 lines". The label's own anchor
   (beside the icon, or beside the value box instead) is decided in JS per render -- see
   milestoneLabelOnTop's own comment -- not fixed by this stylesheet.

   Both the value box and the icon have to land exactly on the item's real position regardless of
   whether a label is shown beside either one (direct request: "if the label wasn't displayed, the
   icon and age would appear the same either way, completely centered over the correct age"). A
   plain flex row centered as a whole would instead center on the ICON+LABEL PAIR's combined
   width, dragging the icon off the true position by roughly half the label's width. So
   .gc-milestone-row itself holds NO in-flow children at all (both rows below are pulled out via
   position:absolute, independently centered left:50% against el's own anchor point) -- within
   each row, the value box/icon is independently re-centered on THAT SAME anchor point (its own
   nested translateX(-50%)) while an optional label is independently offset from it by a fixed
   gap, rather than flowing after the icon/box's own rendered width -- the two could not otherwise
   both reference the identical center point using plain flexbox alone. ---- */
.gc-milestone.gc-milestone-row {
    width: auto;
    height: auto;
    margin-left: 0;
    border: none;
    background: none;
    border-radius: 0;
    transform: translateX(-50%);
    /* position stays "absolute" (inherited from the base .gc-milestone rule just above) --
       NOT "relative". Found live: writing "relative" here to give gc-milestone-row-bottom a
       containing block to anchor against also overrode the base rule's own "absolute", turning
       the whole milestone group into a normal in-flow, full-width block (a position:relative
       block defaults to filling its parent's width, unlike position:absolute's shrink-to-fit) --
       that's what caused the horizontal overflow/scrollbars. position:absolute is an equally
       valid containing block for an absolutely-positioned descendant, so nothing else needs to
       change to fix this. */
}
.gc-milestone-row .gc-tooltip-above {
    position: static;
    bottom: auto;
    left: auto;
    transform: none;
}
.gc-milestone-row-top {
    /* display:inline-block + position:relative (NOT position:absolute, unlike bottomRow) -- this
       one stays a normal in-flow child, same role .gc-tooltip-above itself used to play directly,
       so it still establishes el's real rendered height (needed for bottomRow's own `top:100%` to
       mean anything -- found live: pulling this out of flow the same way as bottomRow collapsed
       el's height to 0, landing both rows on the exact same pixel). position:relative only serves
       as the containing block for the optional label below. */
    display: inline-block;
    position: relative;
    white-space: nowrap;
}
.gc-milestone-row-bottom {
    position: absolute;
    top: 100%;
    left: 50%;
    margin-top: 0.15rem;
    white-space: nowrap;
}
.gc-milestone-row-icon {
    display: inline-block;
    transform: translateX(-50%);
    font-size: 16px;
}
.gc-milestone-label-inline {
    position: absolute;
    left: 50%;
    top: 0;
    margin-left: 0.6rem;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
}
/* Beside the value box instead of the icon -- used only when a milestone is close enough to a
   neighbor that both labels sharing the icon-level band would collide (see milestoneLabelOnTop
   in the JS). left:100% of gc-milestone-row-top (not 50%+margin -- that container is sized
   exactly to the value box, with no independent centering of its own to replicate), so the label
   starts right at the box's own right edge. Vertically centered against the box's height via
   top:50%/translateY, since that height is font+padding driven, not a fixed constant this
   stylesheet could otherwise target directly. */
.gc-milestone-label-inline-top {
    position: absolute;
    left: 100%;
    top: 50%;
    transform: translateY(-50%);
    margin-left: 0.6rem;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
}

/* ---- Activities: below the track. These offsets don't depend on track_height at all -- normal
   document flow already moves this layer's own zero-point to sit right at the track's bottom
   edge regardless of how tall the track itself is, so a plain fixed gap here always lands just
   below it. ---- */
.gc-activities { position: relative; height: 0; }
.gc-activity-bar {
    position: absolute;
    top: 20px;
    height: 5px;
    border-radius: 999px;
    opacity: 0.55;
}
.gc-activity-handle {
    position: absolute;
    /* Narrow upright rectangle, not a 20x20 square (direct request -- the square read as too
       blocky/wide) -- width is purely visual and can go this narrow because dragging binds to
       the whole element's hit box, not an exaggerated visual footprint; height grows instead to
       keep the same total tap target area and the same vertical center against the 5px bar. */
    top: 11px;
    width: 10px;
    height: 24px;
    margin-left: -5px;
    border-radius: 4px;
    cursor: grab;
    touch-action: none;
    z-index: 5;
}
.gc-activity-handle:active { cursor: grabbing; }
.gc-tooltip-below {
    position: absolute;
    top: 160%;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.75rem;
    color: var(--st-text-color);
    background: var(--st-background-color);
    border: 1px solid var(--st-border-color);
    border-radius: var(--st-base-radius);
    padding: 0.15rem 0.4rem;
    white-space: nowrap;
    pointer-events: none;
}
.gc-activity-label {
    position: absolute;
    /* Below the handles' own tooltip-below boxes (~45-69px), not beside them -- found live: a
       SHORT activity (e.g. a half-year sabbatical) puts its label's horizontal center almost
       exactly at the handles' own x-position, so at the old top:46px the label shared the same
       vertical band as the opaque tooltip-below boxes and got visually covered by them (the
       label's own text was still fully in the DOM, just hidden behind a same-position, opaque
       sibling -- not a clipping bug). A longer activity has no such x-overlap and tolerates the
       extra 24px fine. */
    top: 70px;
    text-align: center;
    font-size: 0.75rem;
    font-weight: 600;
    white-space: nowrap;
    pointer-events: none;
}

.gc-range-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 0.5rem;
    color: var(--st-gray-text-color);
    font-size: 0.75rem;
}
"""

JS = """
import { drag as d3drag } from "https://cdn.jsdelivr.net/npm/d3-drag@3.0.0/+esm";
import { select as d3select } from "https://cdn.jsdelivr.net/npm/d3-selection@3.0.0/+esm";

export default function(component) {
    const { parentElement, data, setStateValue } = component;

    const track = parentElement.querySelector(".gc-track");
    const rangesLayer = parentElement.querySelector(".gc-ranges");
    const activitiesLayer = parentElement.querySelector(".gc-activities");
    const milestonesLayer = parentElement.querySelector(".gc-milestones");
    const minLabel = parentElement.querySelector(".gc-min-label");
    const maxLabel = parentElement.querySelector(".gc-max-label");
    const rangeLabelsRow = parentElement.querySelector(".gc-range-labels");

    minLabel.textContent = data.min;
    maxLabel.textContent = data.max;
    // Direct request -- hiding this row (not just blanking its text) is what makes stacking
    // several tracks under one shared axis label row possible: show it on just one instance in
    // the stack (typically the bottom one) and turn it off on the rest, instead of every row
    // repeating the same min/max numbers.
    rangeLabelsRow.style.display = data.show_range_labels ? "flex" : "none";
    parentElement.querySelector(".gc-widget").classList.toggle("gc-bordered", !!data.bordered);

    // track_height/corner_radius are per-call parameters, applied here every render rather than
    // baked into the shared stylesheet (which is authored once at import time and can't vary per
    // call).
    track.style.height = data.track_height + "px";
    track.style.borderRadius = data.corner_radius + "px";
    // Clearance needed above the track varies by milestone_style -- "badge" (24px circle +
    // floating tooltip box) needs the most, "bare" (one inline icon+value line) the least, "row"
    // (value box, then an icon+label line) in between.
    const milestoneClearance = data.milestone_style === "badge" ? 56
        : data.milestone_style === "row" ? 56 : 44;
    const hasMilestones = data.items.some((item) => item.type === "milestone");
    const hasActivities = data.items.some((item) => item.type === "activity");
    // .gc-track-wrap's own top/bottom padding, set here (not a flat CSS constant) so it tracks
    // milestoneClearance -- and, direct request, collapses to a small flat constant when there
    // are no milestones/activities at all this render (nothing is drawn above/below the track in
    // that case, so reserving milestone/activity-sized clearance there is pure dead space --
    // found live: a milestones-only track still reserved the full activity-label clearance below
    // it, leaving a visibly larger gap before whatever rendered next than a track that actually
    // had an activity to show there).
    const trackWrap = parentElement.querySelector(".gc-track-wrap");
    trackWrap.style.paddingTop = hasMilestones
        ? (data.track_height + milestoneClearance + 4) + "px" : "16px";
    // 80 (not a smaller flat default) clears .gc-activity-label's own top:70px + its own line
    // height -- see that rule's comment for why an activity needs this much room. Only reserved
    // when an activity is actually present; otherwise the same small constant the "no milestones"
    // case above uses.
    trackWrap.style.paddingBottom = hasActivities ? "80px" : "16px";

    function scaleXToPx(value) {
        const w = track.getBoundingClientRect().width;
        const frac = (value - data.min) / (data.max - data.min);
        return Math.max(0, Math.min(w, frac * w));
    }
    function scalePxToX(px) {
        const w = track.getBoundingClientRect().width;
        const frac = w > 0 ? Math.max(0, Math.min(1, px / w)) : 0;
        return data.min + frac * (data.max - data.min);
    }
    function snap(value) {
        const stepped = Math.round(value / data.step) * data.step;
        return Math.max(data.min, Math.min(data.max, stepped));
    }
    // decimals is derived from `step` (e.g. step=0.1 -> 1 decimal place) -- NOT a flat
    // Math.round(), which would silently hide real precision for a fractional step (a handle
    // snapping to tenths would still show a whole-number tooltip).
    function formatValue(value) {
        return Number(value).toFixed(data.decimals);
    }
    // Bare milestones show "(value)" right next to the icon (no separate floating box to label
    // on its own); badge milestones keep the plain bordered-tooltip number as before.
    function formatMilestoneValue(value) {
        // Only "bare" wraps the value in parentheses -- it's the one style where the value sits
        // as plain inline text with nothing else (no box, no separate line) marking it as a
        // value rather than a label; "badge" and "row" both show it in its own bordered box,
        // where that's already unambiguous.
        return data.milestone_style === "bare" ? "(" + formatValue(value) + ")" : formatValue(value);
    }

    // ---- CREATE ONCE / SYNC FROM PYTHON -- values live on parentElement, not local `let`, and
    // DOM elements are built exactly once. Streamlit v2 components re-run this whole module on
    // every rerun, including the one a drag's own "end" -> setStateValue(...) triggers; without
    // this guard that rerun would re-create a brand new set of elements on top of the still-there
    // previous ones every time. ----
    if (!parentElement._gcValues) {
        parentElement._gcValues = {};
        data.items.forEach((item) => {
            parentElement._gcValues[item.id] = item.type === "activity"
                ? { start: item.start, end: item.end }
                : { value: item.value };
        });
    }
    const values = parentElement._gcValues;

    // ---- "row" style label placement -- NOT a change to the marker's own position (direct
    // correction: "the marker and age [box] [should] still be in the same vertical distance from
    // the timeline") -- the icon and value box stay at their normal, single fixed clearance for
    // every milestone, always. Only the LABEL TEXT's own anchor alternates, and only between
    // milestones that are actually close together in rendered pixels: by default a label sits
    // beside the icon (bottom line); when a milestone's nearest neighbor (by value) is within
    // PROXIMITY_PX of it, one of the pair instead sits beside the value box (top line) so the two
    // labels don't share the same horizontal band. Milestones with no close neighbor are left
    // alone entirely, even if there are several on the timeline overall -- found live: blanket-
    // alternating every milestone by list position moved two WIDELY-spaced milestones to
    // different heights for no reason. Computed fresh every time this widget MOUNTS (i.e.
    // whenever the caller's own key changes, which lifecalc_setup.py already does any time the
    // checked-item set changes, re-seeding from each item's then-current value) and then used
    // once, below, to decide which row each label's DOM node is created in -- not recomputed
    // live while an existing mount is being dragged, same as everything else under "CREATE ONCE"
    // further down; a mid-drag label handoff between rows would need re-parenting a live DOM
    // node and isn't attempted here. ----
    const PROXIMITY_PX = 100;
    const milestoneLabelOnTop = {};
    if (data.milestone_style === "row") {
        const sortedMilestones = data.items
            .filter((item) => item.type === "milestone")
            .slice()
            .sort((a, b) => values[a.id].value - values[b.id].value);
        let onTop = false;
        sortedMilestones.forEach((item, idx) => {
            if (idx > 0) {
                const gapPx = scaleXToPx(values[item.id].value) - scaleXToPx(values[sortedMilestones[idx - 1].id].value);
                onTop = gapPx < PROXIMITY_PX ? !onTop : false;
            }
            milestoneLabelOnTop[item.id] = onTop;
        });
    }

    // Per-item reposition functions, registered once at creation time below, so a later render
    // can reposition a single already-existing item (see the "SYNC FROM PYTHON" branch further
    // down) without needing to rebuild or touch any other item's DOM.
    if (!parentElement._gcRedraw) {
        parentElement._gcRedraw = {};
    }
    const redrawFns = parentElement._gcRedraw;

    function resolveEndpoint(ref) {
        if (ref.type === "fixed") return ref.value;
        const v = values[ref.item];
        return ref.endpoint === "value" ? v.value : v[ref.endpoint];
    }

    function sendState() {
        // Rounded to `decimals` before being sent, not just when displayed -- found live: the
        // raw dragged value can carry float residue (e.g. 26.200000000000003 from repeated
        // division/multiplication in snap()), which a display-only fix never touches since it
        // doesn't change what's actually committed back to Python.
        const out = {};
        data.items.forEach((item) => {
            const v = values[item.id];
            out[item.id] = item.type === "activity"
                ? { start: Number(v.start.toFixed(data.decimals)), end: Number(v.end.toFixed(data.decimals)) }
                : Number(v.value.toFixed(data.decimals));
        });
        setStateValue("value", out);
    }

    // ---- ranges: pure labeled scaffolding, re-resolved (fixed or ref-to-a-live-item) any time
    // anything moves. What fits is a real measurement (scrollWidth vs clientWidth), not a
    // percentage-of-track guess. ----
    function renderRanges() {
        rangesLayer.replaceChildren();
        data.ranges.forEach((r) => {
            const fromV = resolveEndpoint(r.start);
            const toV = resolveEndpoint(r.end);
            if (toV <= fromV) return;
            const left = scaleXToPx(fromV);
            const width = scaleXToPx(toV) - left;

            const el = document.createElement("div");
            el.className = "gc-range";
            el.style.left = left + "px";
            el.style.width = width + "px";
            el.style.top = -data.track_height + "px";
            el.style.height = data.track_height + "px";
            el.style.borderRadius = data.corner_radius + "px";
            el.style.background = r.color;
            rangesLayer.appendChild(el);

            if (r.label) {
                const label = document.createElement("div");
                label.className = "gc-range-label";
                label.style.left = (left + width / 2) + "px";
                label.style.top = -data.track_height + "px";
                label.style.height = data.track_height + "px";
                label.style.color = r.text_color;
                label.textContent = r.label;
                rangesLayer.appendChild(label);

                const trackRect = track.getBoundingClientRect();
                const labelRect = label.getBoundingClientRect();
                if (labelRect.left < trackRect.left || labelRect.right > trackRect.right) {
                    label.textContent = "";
                }
            }
        });
    }

    if (!parentElement._gcInitialized) {
        parentElement._gcInitialized = true;
        renderRanges();

        data.items.forEach((item) => {
            if (item.type === "milestone") {
                const el = document.createElement("div");
                const styleClass = data.milestone_style === "badge" ? ""
                    : data.milestone_style === "row" ? " gc-milestone-row" : " gc-milestone-bare";
                el.className = "gc-milestone" + styleClass;
                if (data.milestone_style === "badge") {
                    el.style.border = `2px solid ${item.color}`;
                }
                el.style.top = -(data.track_height + milestoneClearance) + "px";
                el.style.left = scaleXToPx(values[item.id].value) + "px";

                const tooltip = document.createElement("div");
                tooltip.className = "gc-tooltip-above";
                tooltip.textContent = formatMilestoneValue(values[item.id].value);

                const icon = document.createElement("span");
                icon.textContent = item.icon;

                let label;
                let clampRowLabel = null;
                if (data.milestone_style === "row") {
                    // Value box on its own row first, then icon+label together as a second row
                    // closest to the bar -- a distinct structure from badge/bare (which keep icon
                    // and label as independent siblings, label absolutely positioned below the
                    // icon) because the label has to sit INLINE beside the icon (or, when close to
                    // a neighbor, beside the value box instead) rather than underneath it.
                    const topRow = document.createElement("div");
                    topRow.className = "gc-milestone-row-top";
                    topRow.appendChild(tooltip);
                    el.appendChild(topRow);

                    const bottomRow = document.createElement("div");
                    bottomRow.className = "gc-milestone-row-bottom";
                    icon.className = "gc-milestone-row-icon";
                    bottomRow.appendChild(icon);
                    el.appendChild(bottomRow);

                    // Which row the label lands in is decided once per render, above (see
                    // milestoneLabelOnTop's own comment) -- purely based on proximity to a
                    // neighboring milestone, not a fixed per-item choice.
                    label = document.createElement("span");
                    label.style.color = item.color;
                    label.textContent = item.label;
                    if (milestoneLabelOnTop[item.id]) {
                        label.className = "gc-milestone-label-inline-top";
                        topRow.appendChild(label);
                    } else {
                        label.className = "gc-milestone-label-inline";
                        bottomRow.appendChild(label);
                    }

                    // "row"'s label sits entirely to the RIGHT of the icon's (or value box's) own centered anchor
                    // (direct request -- the icon itself must stay exactly centered on the real
                    // position, so the label can't share that centering the way badge/bare's
                    // labels do). For a milestone anchored near the track's own right edge, that
                    // one-sided growth can push the label past the track's right boundary --
                    // found live: it overflowed the whole component's own box, which made the
                    // component's host show scrollbars and crop/shift the visible area (looked
                    // like an unrelated milestone had moved inside the track bar, but that was
                    // just a scrolled, cropped view of the real layout). Same fix ranges already
                    // use for their own label (hide the text, not the icon/value, when it
                    // wouldn't fit) -- re-checked on every reposition, not just at creation, since
                    // dragging a milestone changes how close it is to the edge live.
                    const labelText = item.label;
                    clampRowLabel = () => {
                        label.textContent = labelText;
                        const trackRight = track.getBoundingClientRect().right;
                        if (label.getBoundingClientRect().right > trackRight) {
                            label.textContent = "";
                        }
                    };
                    // Not called yet here -- el isn't attached to the live DOM until
                    // milestonesLayer.appendChild(el) below, and getBoundingClientRect() on a
                    // detached element always returns a zero rect, making the overflow check
                    // meaningless. Called once, right after that append, further down.
                } else {
                    // Icon before the value (not after) -- badge mode doesn't care (the tooltip
                    // is absolutely positioned above it regardless of DOM order), but bare mode
                    // lays them out left-to-right as a normal inline-flex row, where order
                    // matters: icon first, then "(value)" beside it.
                    el.appendChild(icon);
                    el.appendChild(tooltip);
                    label = document.createElement("div");
                    label.className = "gc-milestone-label";
                    label.style.color = item.color;
                    label.textContent = item.label;
                    el.appendChild(label);
                }

                milestonesLayer.appendChild(el);
                if (clampRowLabel) clampRowLabel();

                const drag = d3drag()
                    .on("drag", (event) => {
                        const rect = track.getBoundingClientRect();
                        const px = event.sourceEvent.clientX - rect.left;
                        const v = snap(scalePxToX(Math.max(0, Math.min(rect.width, px))));
                        values[item.id].value = v;
                        el.style.left = scaleXToPx(v) + "px";
                        tooltip.textContent = formatMilestoneValue(v);
                        if (clampRowLabel) clampRowLabel();
                        renderRanges();
                    })
                    .on("end", sendState);
                d3select(el).call(drag);

                redrawFns[item.id] = () => {
                    el.style.left = scaleXToPx(values[item.id].value) + "px";
                    tooltip.textContent = formatMilestoneValue(values[item.id].value);
                    if (clampRowLabel) clampRowLabel();
                };

            } else {
                // activity: bar + two independent handles (start, end), clamped only to each other
                const bar = document.createElement("div");
                bar.className = "gc-activity-bar";
                bar.style.background = item.color;
                activitiesLayer.appendChild(bar);

                const startHandle = document.createElement("div");
                startHandle.className = "gc-activity-handle";
                startHandle.style.background = item.color;
                const startTooltip = document.createElement("div");
                startTooltip.className = "gc-tooltip-below";
                startHandle.appendChild(startTooltip);
                activitiesLayer.appendChild(startHandle);

                const endHandle = document.createElement("div");
                endHandle.className = "gc-activity-handle";
                endHandle.style.background = item.color;
                const endTooltip = document.createElement("div");
                endTooltip.className = "gc-tooltip-below";
                endHandle.appendChild(endTooltip);
                activitiesLayer.appendChild(endHandle);

                const label = document.createElement("div");
                label.className = "gc-activity-label";
                label.style.color = item.color;
                label.textContent = item.label;
                activitiesLayer.appendChild(label);

                function redraw() {
                    const v = values[item.id];
                    const leftPx = scaleXToPx(v.start);
                    const rightPx = scaleXToPx(v.end);
                    bar.style.left = leftPx + "px";
                    bar.style.width = Math.max(0, rightPx - leftPx) + "px";
                    startHandle.style.left = leftPx + "px";
                    endHandle.style.left = rightPx + "px";
                    startTooltip.textContent = formatValue(v.start);
                    endTooltip.textContent = formatValue(v.end);
                    label.style.left = leftPx + "px";
                    label.style.width = Math.max(0, rightPx - leftPx) + "px";
                }
                redraw();
                redrawFns[item.id] = redraw;

                const startDrag = d3drag()
                    .on("drag", (event) => {
                        const rect = track.getBoundingClientRect();
                        const px = event.sourceEvent.clientX - rect.left;
                        const raw = snap(scalePxToX(Math.max(0, Math.min(rect.width, px))));
                        values[item.id].start = Math.min(raw, values[item.id].end);
                        redraw();
                        renderRanges();
                    })
                    .on("end", sendState);
                d3select(startHandle).call(startDrag);

                const endDrag = d3drag()
                    .on("drag", (event) => {
                        const rect = track.getBoundingClientRect();
                        const px = event.sourceEvent.clientX - rect.left;
                        const raw = snap(scalePxToX(Math.max(0, Math.min(rect.width, px))));
                        values[item.id].end = Math.max(raw, values[item.id].start);
                        redraw();
                        renderRanges();
                    })
                    .on("end", sendState);
                d3select(endHandle).call(endDrag);
            }
        });
    } else {
        // SYNC FROM PYTHON: if Python passed a different value for an item than what's cached
        // in the browser (e.g. a caller-driven `overrides` forced a new end date), adopt it and
        // reposition just that item via its own stored redraw function -- no rebuild. An item
        // the user is mid-drag on, or already reported back via setStateValue and Python simply
        // echoed back unchanged, is left completely alone; this only fires on a genuine external
        // change.
        data.items.forEach((item) => {
            const v = values[item.id];
            const redraw = parentElement._gcRedraw[item.id];
            if (item.type === "activity") {
                if (v.start !== item.start || v.end !== item.end) {
                    v.start = item.start;
                    v.end = item.end;
                    if (redraw) redraw();
                }
            } else if (v.value !== item.value) {
                v.value = item.value;
                if (redraw) redraw();
            }
        });
        renderRanges();
    }

    // ---- Responsive width: every item/range position above is computed from track's rendered
    // PIXEL width at the moment this module last ran -- which only happens on a Streamlit rerun
    // (a drag's own "end", or any other widget changing elsewhere on the page), never on a plain
    // browser/window resize. Found live: squeezing the viewport narrower (checking how this looks
    // on mobile) shrank the track itself (a plain CSS block, naturally responsive) and the host's
    // own bordered box, but left every range/milestone/activity exactly where they were in PIXELS
    // -- so they visually overflowed past the now-narrower track and its border, looking like "the
    // main bar didn't shrink" even though .gc-track itself had. A ResizeObserver on the track
    // re-runs the same reposition functions (no data changed, so no setStateValue/rerun needed)
    // whenever its rendered width actually changes, independent of any Streamlit rerun. ----
    if (!parentElement._gcResizeObserver) {
        parentElement._gcResizeObserver = new ResizeObserver(() => {
            renderRanges();
            Object.values(parentElement._gcRedraw).forEach((redraw) => redraw());
        });
        parentElement._gcResizeObserver.observe(track);
    }
}
"""

_gantt_track_component = st.components.v2.component(
    name="gantt_track",
    html=HTML,
    css=CSS,
    js=JS,
)


def _decimal_places(step):
    # Same helper as streamlit-segment-slider's/streamlit-marker-slider's own _decimal_places() --
    # decides how many decimal places to display/round to, derived from the step itself (step=1
    # -> 0, step=0.1 -> 1, step=0.25 -> 2) rather than a fixed assumption that every value is a
    # whole number.
    text = f"{step:.10f}".rstrip("0")
    if "." not in text:
        return 0
    return len(text.split(".")[1])


def gantt_track(min_value, max_value, items, ranges=None, *, step=1, key=None, height=None,
                 track_height=20, corner_radius=0, show_range_labels=True, overrides=None,
                 milestone_style="badge", bordered=False):
    """items: list of dicts, one per draggable item:
      - activity: {"id", "type":"activity", "start", "end", "icon", "label", "color"}
      - milestone: {"id", "type":"milestone", "value", "icon", "label", "color"}
    `id` must be unique within the call (it's the key in the returned dict); `start`/`end`/`value`
    are only used as that item's seed position the first time this widget's `key` is ever
    rendered -- after that, session state owns the live value.

    `overrides` (optional): `{item_id: new_value}` (a plain float for a milestone, `{"start",
    "end"}` for an activity) -- forces that item to the given value on THIS render even though
    the widget already has a live session-state value, for when something else on the page
    should move a handle (e.g. picking a 2-year program should snap College's end date to
    start+2). Without this, `start`/`end`/`value` in `items` are silently ignored for any item
    the widget's session state already has a stored value for -- they only seed the position the
    very first time this `key` is ever rendered. Only pass the ids that actually need to change;
    everything else keeps its current live value untouched (a user's own in-progress drag is
    never overwritten by an unrelated rerun that happens to call this again with the same old
    `items`).

    `ranges` (optional): list of dicts, one per labeled range:
      {"id", "label", "color", "text_color", "start", "end"}
    where `start`/`end` are each either `{"type": "fixed", "value": N}` or
    `{"type": "ref", "item": item_id, "endpoint": "start"|"end"|"value"}` -- a ref endpoint tracks
    that item's live position, so e.g. a range can start wherever a milestone currently sits
    without being a draggable thing of its own. `text_color` is optional per range (defaults to
    white) -- background and text are independently parameterized, since no single fixed text
    color reads well against every caller-chosen background. A range with a non-positive resolved
    width (end <= start) is simply not drawn that render -- not an error.

    `track_height`/`corner_radius` (px) size and shape the main track and the ranges drawn inside
    it. `corner_radius=0` (the default) is square; activity/milestone handle shapes are
    unaffected by this (still round/rounded -- those read as handles, not "the timeline" itself).

    `step` can be fractional (e.g. `step=0.1`) -- the tooltips shown above/below each handle while
    dragging display and round to the same number of decimal places `step` itself implies
    (`step=1` -> whole numbers, `step=0.1` -> 1 decimal place), not a flat `Math.round()` that
    would hide the real precision a fractional step snaps to.

    `show_range_labels=False` hides the min/max row entirely (not just its text) -- this is what
    makes stacking several tracks under one shared axis label row possible: give it `True` on just
    one instance in the stack (typically the bottom one) and `False` on the rest, rather than every
    row repeating the same min/max numbers. See README's "Composing multiple tracks" section.

    `milestone_style` picks how every milestone in this call is drawn (applies to all of them,
    not per-item -- there was no real case for mixing styles on the same track):
      - `"badge"` (default): the original circular white background + 2px colored border +
        bordered tooltip box above + label below. Needed when an icon isn't reliably legible on
        its own (a dark-ink emoji like a graduation cap against a dark theme background) --
        the fixed light background is what keeps it readable regardless of theme.
      - `"bare"`: no circle, no background -- just the plain icon with its value inline beside it
        in parentheses (e.g. "🚀 (23.0)"), label below. For icons that read fine without a
        background (most simple, bright emoji). Needs much less vertical clearance than badge.
      - `"row"`: value in a bordered box on its own line, then icon+label together on a second
        line closest to the bar -- a loose mirror of how an activity's own handle is laid out
        (value box, then the handle right at the bar), done in 2 lines instead of 3 by putting
        the label beside the icon rather than under it.

    `bordered=True` wraps the whole widget in a bordered, rounded, padded box (matching
    `st.container(border=True)`'s look) -- a presentation-only toggle, independent of every other
    parameter here.

    `height` (px) sizes this component's fixed-height host. Left at its default (`None`), it's
    computed from `track_height`/`milestone_style`/`show_range_labels`/whether `items` actually
    has any milestones -- tall enough for whatever's really going to render, not a flat guess that
    leaves dead space below a more compact style (found live: a generic fixed default left a large
    gap below the widget once milestones/padding were trimmed down). Pass an explicit value to
    override.

    Returns a dict `{item_id: value}` for every item in `items` -- a plain float for a milestone,
    `{"start": float, "end": float}` for an activity. Ranges are never part of the return value;
    they're derived presentation, not state of their own.
    """
    if milestone_style not in ("badge", "bare", "row"):
        raise ValueError(f"milestone_style must be 'badge', 'bare', or 'row', got {milestone_style!r}")
    ranges = [{"text_color": "#ffffff", **r} for r in (ranges or [])]
    default = {}
    for item in items:
        default[item["id"]] = (
            {"start": float(item["start"]), "end": float(item["end"])}
            if item["type"] == "activity" else float(item["value"])
        )

    state = st.session_state.get(key, {})
    current = state.get("value", default) if isinstance(state, dict) else default

    if overrides:
        current = {**current, **overrides}
        # Written back into session state too, not just used for this render's `resolved_items`
        # -- otherwise the NEXT rerun (with no override passed) would read the old pre-override
        # value straight back out of session state, undoing this the moment anything else on the
        # page triggers a rerun.
        if key is not None:
            st.session_state[key] = {**state, "value": current} if isinstance(state, dict) else {"value": current}

    resolved_items = []
    for item in items:
        cur = current.get(item["id"], default[item["id"]])
        if item["type"] == "activity":
            resolved_items.append({**item, "start": float(cur["start"]), "end": float(cur["end"])})
        else:
            resolved_items.append({**item, "value": float(cur)})

    if height is None:
        # Mirrors the JS padding logic exactly (milestoneClearance/hasMilestones/paddingBottom
        # above) so the host box is sized to what will actually render, not a generic guess --
        # these two must be kept in sync if either side's constants change.
        has_milestones = any(item["type"] == "milestone" for item in items)
        has_activities = any(item["type"] == "activity" for item in items)
        milestone_clearance = {"badge": 56, "row": 56, "bare": 44}[milestone_style]
        padding_top = (track_height + milestone_clearance + 4) if has_milestones else 16
        padding_bottom = 80 if has_activities else 16
        range_labels_height = 26 if show_range_labels else 0
        border_allowance = 2 if bordered else 0
        height = int(padding_top + track_height + padding_bottom + range_labels_height + border_allowance + 8)

    result = _gantt_track_component(
        data={
            "min": float(min_value), "max": float(max_value), "step": float(step),
            "decimals": _decimal_places(step),
            "items": resolved_items,
            "ranges": ranges,
            "track_height": float(track_height),
            "corner_radius": float(corner_radius),
            "show_range_labels": bool(show_range_labels),
            "milestone_style": milestone_style,
            "bordered": bool(bordered),
        },
        default={"value": default},
        on_value_change=lambda: None,
        key=key,
        width="stretch",
        height=height,
    )
    return result.get("value", default) if isinstance(result, dict) else default
