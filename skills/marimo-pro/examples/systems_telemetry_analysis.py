# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "numpy>=2.0.0",
#     "plotly>=6.0.0",
# ]
# ///
"""Real-time microkernel IPC telemetry, tail latency percentiles, and flame graph dashboard."""

import marimo

__generated_with = "0.25.2"
app = marimo.App(
    width="wide",
    app_title="RTOS Microkernel Telemetry & Tail Latency Analysis",
)


@app.cell
def setup_telemetry_env():
    import math

    import marimo as mo
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    return go, make_subplots, math, mo, np, px


@app.cell
def render_telemetry_header(mo):
    telemetry_header_card = mo.md(
        r"""
        # ⚡ High-Assurance RTOS IPC Telemetry & Tail Latency Dashboard

        This reactive **Marimo** notebook performs tail latency characterization,
        High Dynamic Range (HDR) log-survival analysis, and IPC queue execution timeline visualization
        for hard real-time microkernels (such as **seL4**, **Hubris**, and **Zircon**).

        ### Statistical Foundations
        - **Tail Quantiles**: $p50, p90, p99, p99.9, p99.99$ characterize worst-case execution deadlines.
        - **High Dynamic Range (HDR) Log-Survival Function**:
          $$S(L) = P(X > L) = 1 - F(L)$$
          Plotting $-\log_{10}(1 - F(L))$ against latency $L$ exposes whether extreme delays follow
          thin-tailed exponential distributions or heavy-tailed Pareto power laws ($P(X > L) \sim L^{-\alpha}$)
          induced by lock contention, TLB shootdowns, or cache thrashing.
        - **Hardware PMU Outlier Drill-Down**: Interactive inspection of Last-Level Cache (LLC) misses,
          TLB invalidation shootdowns, and microkernel call-stack traces.
        """
    )
    return (telemetry_header_card,)


@app.cell
def build_telemetry_controls(mo):
    core_multiselect = mo.ui.multiselect(
        options=["Core 0", "Core 1", "Core 2", "Core 3"],
        value=["Core 0", "Core 1", "Core 2", "Core 3"],
        label="Filter Target CPU Cores",
    )
    metric_dropdown = mo.ui.dropdown(
        options=[
            "IPC Fastpath Call Latency",
            "Thread Context Switch Delay",
            "Hardware IRQ Dispatch Latency",
        ],
        value="IPC Fastpath Call Latency",
        label="Microkernel Metric",
    )
    workload_dropdown = mo.ui.dropdown(
        options=[
            "Nominal IPC Traffic",
            "Lock Contention Storm",
            "LLC Cache Thrashing Burst",
        ],
        value="Lock Contention Storm",
        label="Kernel Workload Scenario",
    )
    tail_percentile_slider = mo.ui.slider(
        start=90.0,
        stop=99.99,
        step=0.01,
        value=99.0,
        label="Tail Percentile Cutoff (%)",
    )
    controls_panel = mo.vstack(
        [
            mo.md("### 🎛️ Telemetry Stream & Filtering Controls"),
            mo.hstack([core_multiselect, metric_dropdown], justify="start"),
            mo.hstack([workload_dropdown, tail_percentile_slider], justify="start"),
        ]
    )
    return (
        controls_panel,
        core_multiselect,
        metric_dropdown,
        tail_percentile_slider,
        workload_dropdown,
    )


@app.cell
def analyze_telemetry_stream(
    core_multiselect,
    go,
    make_subplots,
    metric_dropdown,
    mo,
    np,
    tail_percentile_slider,
    workload_dropdown,
):
    _rng = np.random.default_rng(seed=1337)
    _n_events = 6000

    # 1. Synthesize Hardware Telemetry Stream Based on Selected Workload Scenario
    _scenario = workload_dropdown.value
    _cores_pool = ["Core 0", "Core 1", "Core 2", "Core 3"]
    _subsystems_pool = [
        "ipc_fastpath",
        "capability_space",
        "mem_manager",
        "vfs_driver",
        "sensor_bridge",
        "crypto_vault",
    ]

    _raw_cores = _rng.choice(_cores_pool, size=_n_events, p=[0.35, 0.25, 0.20, 0.20])
    _raw_subsystems = _rng.choice(_subsystems_pool, size=_n_events)

    if _scenario == "Nominal IPC Traffic":
        _latencies = _rng.lognormal(mean=1.0, sigma=0.25, size=_n_events)
        _base_llc = _rng.poisson(lam=2, size=_n_events)
        _base_tlb = _rng.poisson(lam=0.1, size=_n_events)
    elif _scenario == "LLC Cache Thrashing Burst":
        _lat_nom = _rng.lognormal(mean=1.1, sigma=0.30, size=int(_n_events * 0.85))
        _lat_burst = _rng.pareto(a=2.0, size=int(_n_events * 0.15)) * 18.0 + 12.0
        _latencies = np.concatenate([_lat_nom, _lat_burst])
        _rng.shuffle(_latencies)
        _base_llc = _rng.poisson(lam=18, size=_n_events)
        _base_tlb = _rng.poisson(lam=2.5, size=_n_events)
    else:  # 'Lock Contention Storm'
        _lat_nom = _rng.lognormal(mean=1.1, sigma=0.35, size=int(_n_events * 0.92))
        _lat_contention = _rng.pareto(a=1.6, size=int(_n_events * 0.08)) * 30.0 + 20.0
        _latencies = np.concatenate([_lat_nom, _lat_contention])
        _rng.shuffle(_latencies)
        _base_llc = _rng.poisson(lam=6, size=_n_events)
        _base_tlb = _rng.poisson(lam=8.0, size=_n_events)

    # 2. Filter by Selected CPU Cores
    _selected_cores = (
        set(core_multiselect.value) if core_multiselect.value else set(_cores_pool)
    )
    _core_mask = np.array([c in _selected_cores for c in _raw_cores])

    _filtered_latencies = _latencies[_core_mask]
    _filtered_cores = _raw_cores[_core_mask]
    _filtered_subsystems = _raw_subsystems[_core_mask]
    _filtered_llc = _base_llc[_core_mask]
    _filtered_tlb = _base_tlb[_core_mask]

    # Handle empty filter fallback safely
    if len(_filtered_latencies) == 0:
        _filtered_latencies = np.array([1.0])
        _filtered_cores = np.array(["Core 0"])
        _filtered_subsystems = np.array(["ipc_fastpath"])
        _filtered_llc = np.array([0])
        _filtered_tlb = np.array([0])

    # 3. Percentile Quantification
    _p50 = float(np.percentile(_filtered_latencies, 50.0))
    _p90 = float(np.percentile(_filtered_latencies, 90.0))
    _p99 = float(np.percentile(_filtered_latencies, 99.0))
    _p99_9 = float(np.percentile(_filtered_latencies, 99.9))
    _p99_99 = float(np.percentile(_filtered_latencies, 99.99))
    _cutoff_val = float(
        np.percentile(_filtered_latencies, tail_percentile_slider.value)
    )

    percentiles_map = {
        "p50": _p50,
        "p90": _p90,
        "p99": _p99,
        "p99.9": _p99_9,
        "p99.99": _p99_99,
        "cutoff": _cutoff_val,
    }

    # 4. Statistical Summary Cards
    kpi_stat_cards = mo.hstack(
        [
            mo.stat(
                value=f"{_p50:.2f} µs",
                label="p50 (Median)",
                caption=f"Metric: {metric_dropdown.value}",
            ),
            mo.stat(
                value=f"{_p90:.2f} µs",
                label="p90 Latency",
                caption="90th percentile threshold",
            ),
            mo.stat(
                value=f"{_p99:.2f} µs",
                label="p99 Tail",
                caption="High-priority deadline",
            ),
            mo.stat(
                value=f"{_p99_9:.2f} µs",
                label="p99.9 Extreme Tail",
                caption="Worst-case SLA bound",
            ),
            mo.stat(
                value=f"{_cutoff_val:.2f} µs",
                label=f"Cutoff ({tail_percentile_slider.value:.2f}%)",
                caption="Interactive Outlier Filter",
            ),
        ]
    )

    # 5. Extract Outlier Events Exceeding Tail Cutoff
    _outlier_idx = np.where(_filtered_latencies >= _cutoff_val)[0]
    # Sort descending by latency
    _sorted_outlier_idx = _outlier_idx[np.argsort(-_filtered_latencies[_outlier_idx])]

    _call_stacks = [
        "seL4_Call -> cap_lookup -> fastpath_copy -> sched_switch",
        "msg_queue_enqueue -> spinlock_acquire_slowpath -> yield_core",
        "irq_handler_top -> softirq_dispatch -> tlb_shootdown_sync",
        "vfs_write -> page_cache_evict -> llc_stall_drain",
    ]

    _outlier_records = []
    for _idx in _sorted_outlier_idx[:50]:
        _outlier_records.append(
            {
                "event_id": int(_idx + 1000),
                "core": str(_filtered_cores[_idx]),
                "subsystem": str(_filtered_subsystems[_idx]),
                "latency_us": round(float(_filtered_latencies[_idx]), 2),
                "llc_misses": int(_filtered_llc[_idx]),
                "tlb_shootdowns": int(_filtered_tlb[_idx]),
                "stack_trace": _call_stacks[_idx % len(_call_stacks)],
            }
        )

    outlier_events_table = mo.ui.table(
        data=_outlier_records,
        selection="single",
        page_size=8,
    )

    # 6. High Dynamic Range (HDR) Tail Log-Survival Figure
    _sorted_l = np.sort(_filtered_latencies)
    _cdf = np.arange(1, len(_sorted_l) + 1) / len(_sorted_l)
    _survival = 1.0 - _cdf
    _valid = _survival > 0.0
    _hdr_y = -np.log10(_survival[_valid])
    _hdr_x = _sorted_l[_valid]

    hdr_survival_figure = go.Figure()
    hdr_survival_figure.add_trace(
        go.Scatter(
            x=_hdr_x,
            y=_hdr_y,
            mode="lines",
            name="Log-Survival Curve -log10(1 - F(L))",
            line={"color": "#00ffcc", "width": 2.5},
        )
    )

    # Annotate percentiles on the HDR plot
    _p_annotations = [
        (1 - 0.50, _p50, "p50", "#00ff00"),
        (1 - 0.90, _p90, "p90", "#ffff00"),
        (1 - 0.99, _p99, "p99", "#ffa500"),
        (1 - 0.999, _p99_9, "p99.9", "#ff3366"),
        (1 - 0.9999, _p99_99, "p99.99", "#ff0033"),
    ]
    for _surv_val, _lat_val, _label, _color in _p_annotations:
        _y_log = -np.log10(_surv_val)
        hdr_survival_figure.add_vline(
            x=_lat_val,
            line_dash="dot",
            line_color=_color,
            annotation_text=f"{_label} ({_lat_val:.1f}µs)",
            annotation_position="top left",
        )

    hdr_survival_figure.update_layout(
        title=f"High Dynamic Range (HDR) Tail Latency Log-Survival ({metric_dropdown.value})",
        xaxis_title="Recorded Microkernel Latency (µs)",
        yaxis_title="Log-Survival: -log10(1 - Percentile / 100)",
        template="plotly_dark",
        height=400,
    )

    # 7. Real-Time Microkernel Execution Timeline & Flame Graph
    # Visualizes task slice sequence and IPC handoffs across cores
    _timeline_samples = min(len(_filtered_latencies), 150)
    _sample_indices = np.arange(_timeline_samples)
    _sample_lats = _filtered_latencies[:_timeline_samples]
    _sample_cores = _filtered_cores[:_timeline_samples]
    _sample_subsys = _filtered_subsystems[:_timeline_samples]

    _is_outlier = _sample_lats >= _cutoff_val

    ipc_timeline_figure = go.Figure()

    # Base task execution scatter
    ipc_timeline_figure.add_trace(
        go.Scatter(
            x=_sample_indices,
            y=_sample_lats,
            mode="markers+lines",
            name="Nominal IPC Transactions",
            marker={
                "size": 7,
                "color": _sample_lats,
                "colorscale": "Viridis",
                "showscale": True,
                "colorbar": {"title": "Latency (µs)"},
            },
            line={"color": "rgba(255, 255, 255, 0.25)", "width": 1},
        )
    )

    # Highlight tail outlier breaches
    if np.any(_is_outlier):
        ipc_timeline_figure.add_trace(
            go.Scatter(
                x=_sample_indices[_is_outlier],
                y=_sample_lats[_is_outlier],
                mode="markers",
                name="Tail Outlier Breach (> Cutoff)",
                marker={
                    "symbol": "diamond-open",
                    "size": 14,
                    "color": "#ff0033",
                    "line": {"width": 2.5, "color": "#ff0033"},
                },
            )
        )

    ipc_timeline_figure.add_hline(
        y=_cutoff_val,
        line_dash="dash",
        line_color="#ff0033",
        annotation_text=f"Cutoff ({tail_percentile_slider.value}%) = {_cutoff_val:.2f} µs",
        annotation_position="bottom right",
    )

    ipc_timeline_figure.update_layout(
        title="IPC Queue Transaction Timeline & Anomaly Detection",
        xaxis_title="Chronological Telemetry Event Sequence Index",
        yaxis_title="Execution Latency (µs)",
        template="plotly_dark",
        height=380,
    )

    return (
        hdr_survival_figure,
        ipc_timeline_figure,
        kpi_stat_cards,
        outlier_events_table,
        percentiles_map,
    )


@app.cell
def inspect_outlier_event(mo, outlier_events_table):
    _selection = outlier_events_table.value
    if _selection is None or len(_selection) == 0:
        outlier_inspector_card = mo.md(
            "🔍 *Click any outlier event row in the table above to inspect CPU hardware registers, PMU counters, and microkernel call stack.*"
        )
    else:
        _event = _selection[0] if isinstance(_selection, list) else _selection.iloc[0]
        _lat = float(_event["latency_us"])
        _severity = "danger" if _lat > 40.0 else "warn"

        outlier_inspector_card = mo.callout(
            mo.md(
                f"""
                ### ⚠️ Outlier PMU Diagnostic Inspection: Event #{_event["event_id"]}
                - **Target CPU Core**: **`{_event["core"]}`**
                - **Subsystem**: `{_event["subsystem"]}`
                - **Recorded IPC Latency**: **`{_lat:.2f} µs`** (Classification: `{_severity.upper()}`)
                - **Hardware PMU Counters**:
                  - **Last-Level Cache (LLC) Misses**: `{_event["llc_misses"]}` misses
                  - **TLB Shootdown Cross-Calls**: `{_event["tlb_shootdowns"]}` shootdowns
                - **Microkernel Call Stack**:
                  ```text
                  {_event["stack_trace"]}
                  ```
                """
            ),
            kind=_severity,
        )
    return (outlier_inspector_card,)


@app.cell
def render_telemetry_dashboard(
    controls_panel,
    hdr_survival_figure,
    ipc_timeline_figure,
    kpi_stat_cards,
    mo,
    outlier_events_table,
    outlier_inspector_card,
    telemetry_header_card,
):
    telemetry_dashboard_layout = mo.vstack(
        [
            telemetry_header_card,
            controls_panel,
            kpi_stat_cards,
            mo.hstack(
                [
                    mo.vstack(
                        [
                            mo.md("### 📋 Outlier Events Exceeding Tail Threshold"),
                            outlier_events_table,
                            outlier_inspector_card,
                        ]
                    ),
                ]
            ),
            mo.ui.plotly(hdr_survival_figure),
            mo.ui.plotly(ipc_timeline_figure),
        ]
    )
    return (telemetry_dashboard_layout,)


@app.cell
def test_telemetry_invariants(outlier_events_table, percentiles_map):
    def test_percentile_monotonicity():
        assert percentiles_map["p50"] <= percentiles_map["p90"], (
            "p50 > p90 ordering violation"
        )
        assert percentiles_map["p90"] <= percentiles_map["p99"], (
            "p90 > p99 ordering violation"
        )
        assert percentiles_map["p99"] <= percentiles_map["p99.9"], (
            "p99 > p99.9 ordering violation"
        )
        assert percentiles_map["p99.9"] <= percentiles_map["p99.99"], (
            "p99.9 > p99.99 ordering violation"
        )

    def test_outliers_exceed_cutoff():
        _cutoff = percentiles_map["cutoff"]
        for _item in outlier_events_table.data:
            assert _item["latency_us"] >= _cutoff - 0.05, (
                f"Outlier latency {_item['latency_us']} < cutoff {_cutoff}"
            )

    test_percentile_monotonicity()
    test_outliers_exceed_cutoff()
    return (
        test_outliers_exceed_cutoff,
        test_percentile_monotonicity,
    )


if __name__ == "__main__":
    app.run()
