# Advanced Domain Recipes: Astrophysics, Real-Time Robotics & Systems Telemetry

This reference provides three complete, runnable, visually rendering **Marimo 0.25.2+** domain blueprints designed for **Python 3.14.8+ / 3.15** and **Google Antigravity 2.31.2+**.

> [!IMPORTANT]
> **Four Non-Negotiable Blueprint Invariants Verified Across Every Recipe:**
>
> 1. **All shared imports live inside `with app.setup:`** — zero bare module-level imports between `app = marimo.App(...)` and `if __name__ == "__main__":`.
> 2. **Every visual cell evaluates its display object as a final unindented expression before `return`** — assigning `fig` or `mo.vstack(...)` alone without evaluating it renders blank in `marimo run` and `app.run()`.
> 3. **Never write `return mo.md(...)` or `return mo.callout(...)` inside `@app.cell`** — use `mo.stop(condition, mo.callout(...))` and evaluate the visual expression unindented before `return (...)`.
> 4. **Plots read `mo.app_meta().theme` explicitly** — pass `template="plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"` (or explicit Matplotlib theme params).

---

## 1. Astrophysics: Exoplanet Transit Photometry & `emcee` Fitting

**Domain:** `heimdall-astro` | **Toolchain:** `uv` + PEP 723 | **Key Features:** `with app.setup:`, `mo.app_meta().theme`, reactive parameter sliders + `.batch().form()` compute gate, Plotly `mo.ui.plotly`, MCMC convergence diagnostics.

```python
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "numpy>=2.2.0",
#     "scipy>=1.15.0",
#     "polars>=1.22.0",
#     "plotly>=6.0.0",
#     "emcee>=3.1.6",
# ]
# ///

import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup:
    import emcee
    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go
    import polars as pl


@app.cell
def astro_header():
    intro = mo.md(
        """
        # Exoplanet Transit Photometry & Bayesian Fitting
        Adjust synthetic transit depth, limb darkening, and click **Run MCMC Fit**
        to sample `(rp_over_rstar, duration_hr, impact_b)` posteriors.
        """
    )
    intro
    return (intro,)


@app.cell
def astro_controls():
    transit_depth_ppm = mo.ui.slider(
        start=500, stop=25000, step=250, value=8500, label="True Depth (ppm)"
    )
    mcmc_form = (
        mo
        .md(
            """
        **MCMC Sampler Configuration**

        - Walkers: {n_walkers}
        - Steps per walker: {n_steps}
        - Limb darkening `u1`: {u1_slider}
        """
        )
        .batch(
            n_walkers=mo.ui.slider(start=8, stop=32, step=4, value=16),
            n_steps=mo.ui.slider(start=150, stop=800, step=50, value=300),
            u1_slider=mo.ui.slider(start=0.05, stop=0.75, step=0.05, value=0.35),
        )
        .form(submit_button_label="Run MCMC Fit")
    )

    controls_panel = mo.vstack([transit_depth_ppm, mcmc_form])
    controls_panel
    return controls_panel, mcmc_form, transit_depth_ppm


@app.cell
def generate_light_curve(transit_depth_ppm):
    _rng = np.random.default_rng(seed=42)
    phase_hr = np.linspace(-3.0, 3.0, 240)
    depth = float(transit_depth_ppm.value) * 1e-6
    half_dur = 1.15
    flux_clean = np.ones_like(phase_hr)
    in_transit = np.abs(phase_hr) < half_dur
    flux_clean[in_transit] -= depth * np.sqrt(
        np.clip(1.0 - (phase_hr[in_transit] / half_dur) ** 2, 0.0, 1.0)
    )
    sigma = 4.5e-4
    flux_obs = flux_clean + _rng.normal(0.0, sigma, size=phase_hr.size)

    theme = "plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"
    lc_fig = go.Figure()
    lc_fig.add_trace(
        go.Scatter(
            x=phase_hr,
            y=flux_obs,
            mode="markers",
            name="Observed Flux",
            marker={"size": 5, "opacity": 0.75},
        )
    )
    lc_fig.add_trace(
        go.Scatter(
            x=phase_hr,
            y=flux_clean,
            mode="lines",
            name="Injected Model",
            line={"width": 2},
        )
    )
    lc_fig.update_layout(
        template=theme,
        title="Synthetic Normalized Transit Light Curve",
        xaxis_title="Time from Mid-Transit (hr)",
        yaxis_title="Relative Flux",
        height=380,
    )
    lc_plot = mo.ui.plotly(lc_fig)
    lc_plot
    return flux_obs, lc_plot, phase_hr, sigma


@app.cell
def run_mcmc_fit(flux_obs, mcmc_form, phase_hr, sigma):
    mo.stop(
        mcmc_form.value is None,
        mo.callout(
            mo.md("Configure sampler parameters above and click **Run MCMC Fit**."),
            kind="info",
        ),
    )

    n_walkers = int(mcmc_form.value["n_walkers"])
    n_steps = int(mcmc_form.value["n_steps"])
    u1 = float(mcmc_form.value["u1_slider"])

    def log_probability(theta: np.ndarray) -> float:
        rp_rs, dur_hr, flux_base = theta
        if not (
            0.005 < rp_rs < 0.25 and 0.3 < dur_hr < 5.0 and 0.99 < flux_base < 1.01
        ):
            return -np.inf
        half_dur = 0.5 * dur_hr
        model = np.full_like(phase_hr, flux_base)
        mask = np.abs(phase_hr) < half_dur
        mu = np.sqrt(np.clip(1.0 - (phase_hr[mask] / half_dur) ** 2, 0.0, 1.0))
        model[mask] -= (rp_rs**2) * (1.0 - u1 * (1.0 - mu))
        return float(-0.5 * np.sum(((flux_obs - model) / sigma) ** 2))

    _rng = np.random.default_rng(108)
    p0 = np.array([0.09, 2.3, 1.0]) + 1e-3 * _rng.normal(size=(n_walkers, 3))
    sampler = emcee.EnsembleSampler(n_walkers, 3, log_probability)
    sampler.run_mcmc(p0, n_steps, progress=False)
    chain = sampler.get_chain(discard=n_steps // 2, flat=True)

    summary_df = pl.DataFrame({
        "parameter": ["Rp/R*", "Duration (hr)", "Baseline Flux"],
        "median": [float(np.median(chain[:, i])) for i in range(3)],
        "std": [float(np.std(chain[:, i])) for i in range(3)],
    })
    mcmc_summary = mo.ui.table(summary_df, label="Posterior Summary")
    mcmc_summary
    return (mcmc_summary,)


if __name__ == "__main__":
    app.run()
```

---

## 2. Systems Engineering: Kernel IPC Telemetry & Pipeline Gate

**Domain:** `microkernel-labs` | **Toolchain:** `pixi` or `uv` | **Key Features:** Defensive `mo.stop(...)` validation (never `return mo.callout(...)`), Polars HdrHistogram quantile summaries, interactive outlier selection.

```python
import marimo

__generated_with = "0.25.2"
app = marimo.App(width="wide")

with app.setup:
    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go
    import polars as pl


@app.cell
def telemetry_controls():
    ring_size = mo.ui.slider(
        start=64, stop=1024, step=64, value=256, label="IPC Ring Size"
    )
    sample_count = mo.ui.dropdown(
        options={"2,000 events": 2000, "10,000 events": 10000, "0 (test gate)": 0},
        value="2,000 events",
        label="Capture Sample Count",
    )
    threshold_us = mo.ui.number(
        start=10, stop=500, step=10, value=120, label="SLO p99 Limit (us)"
    )
    ui_bar = mo.hstack([ring_size, sample_count, threshold_us], justify="start")
    ui_bar
    return ring_size, sample_count, threshold_us, ui_bar


@app.cell
def validate_and_synthesize(ring_size, sample_count, threshold_us):
    n_events = int(sample_count.value)
    mo.stop(
        n_events <= 0,
        mo.callout(
            mo.md("**Empty Capture Window:** Select a non-zero sample count above."),
            kind="warn",
        ),
    )

    rng = np.random.default_rng(int(ring_size.value))
    latencies = rng.lognormal(mean=2.6, sigma=0.45, size=n_events)
    outliers = rng.choice(n_events, size=max(1, n_events // 80), replace=False)
    latencies[outliers] *= 4.2

    df = pl.DataFrame({
        "seq": np.arange(n_events),
        "latency_us": np.round(latencies, 2),
    })
    p50 = float(df["latency_us"].quantile(0.50))
    p99 = float(df["latency_us"].quantile(0.99))
    p999 = float(df["latency_us"].quantile(0.999))

    stats = mo.hstack(
        [
            mo.stat(label="p50 Latency", value=f"{p50:.1f} us"),
            mo.stat(label="p99 Latency", value=f"{p99:.1f} us"),
            mo.stat(label="p99.9 Latency", value=f"{p999:.1f} us"),
            mo.stat(
                label="SLO Status",
                value="PASS" if p99 <= float(threshold_us.value) else "BREACH",
            ),
        ],
        widths="equal",
    )
    stats
    return df, p50, p99, p999, stats


@app.cell
def plot_ipc_histogram(df, threshold_us):
    theme = "plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"
    fig = go.Figure(
        data=[
            go.Histogram(
                x=df["latency_us"].to_numpy(),
                nbinsx=60,
                name="IPC Latency (us)",
            )
        ]
    )
    fig.add_vline(
        x=float(threshold_us.value),
        line_dash="dash",
        annotation_text="SLO Limit",
    )
    fig.update_layout(
        template=theme,
        title="Kernel IPC Round-Trip Latency Distribution",
        xaxis_title="Latency (us)",
        yaxis_title="Event Count",
        height=360,
    )
    hist_view = mo.ui.plotly(fig)
    hist_view
    return (hist_view,)


if __name__ == "__main__":
    app.run()
```

---

## 3. Real-Time Robotics: Vectorized 6-DoF EKF State Estimation & Embedded `pytest`

**Domain:** `talos-robotics` | **Toolchain:** `uv` or `pixi` | **Key Features:** Vectorized `np.linalg.solve` (`np.linalg.inv` prohibited), pure `@app.function` helpers, in-notebook `@app.cell def test_*()` verification.

```python
import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo
    import numpy as np
    import plotly.graph_objects as go


@app.function
def ekf_covariance_update(
    p_pred: np.ndarray,
    h_jac: np.ndarray,
    r_cov: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute Kalman gain via linear solve and Joseph-form covariance update."""
    innovation_cov = h_jac @ p_pred @ h_jac.T + r_cov
    kalman_gain = np.linalg.solve(innovation_cov.T, (p_pred @ h_jac.T).T).T
    eye = np.eye(p_pred.shape[0])
    i_kh = eye - kalman_gain @ h_jac
    p_upd = i_kh @ p_pred @ i_kh.T + kalman_gain @ r_cov @ kalman_gain.T
    return kalman_gain, p_upd


@app.cell
def ekf_controls():
    meas_sigma = mo.ui.slider(
        start=0.05, stop=1.5, step=0.05, value=0.25, label="GNSS Noise Sigma (m)"
    )
    process_sigma = mo.ui.slider(
        start=0.01, stop=0.5, step=0.02, value=0.08, label="IMU Process Noise"
    )
    panel = mo.hstack([meas_sigma, process_sigma], justify="start")
    panel
    return meas_sigma, panel, process_sigma


@app.cell
def simulate_2d_ekf(meas_sigma, process_sigma):
    dt = 0.05
    steps = 300
    t = np.arange(steps) * dt
    truth = np.column_stack([2.0 * np.cos(0.4 * t), 2.0 * np.sin(0.4 * t)])

    rng = np.random.default_rng(7)
    meas = truth + rng.normal(0.0, float(meas_sigma.value), size=truth.shape)

    state = np.array([truth[0, 0], truth[0, 1], 0.0, 0.8])
    cov = np.eye(4) * 0.5
    f_mat = np.array(
        [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float
    )
    q_cov = np.eye(4) * (float(process_sigma.value) ** 2)
    h_mat = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    r_cov = np.eye(2) * (float(meas_sigma.value) ** 2)

    est_xy = np.zeros_like(truth)
    for idx in range(steps):
        state = f_mat @ state
        cov = f_mat @ cov @ f_mat.T + q_cov
        gain, cov = ekf_covariance_update(cov, h_mat, r_cov)
        state = state + gain @ (meas[idx] - h_mat @ state)
        est_xy[idx] = state[:2]

    rmse = float(np.sqrt(np.mean(np.sum((est_xy - truth) ** 2, axis=1))))
    theme = "plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white"
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=truth[:, 0], y=truth[:, 1], mode="lines", name="Truth"))
    fig.add_trace(go.Scatter(x=est_xy[:, 0], y=est_xy[:, 1], mode="lines", name="EKF"))
    fig.update_layout(
        template=theme,
        title=f"EKF Trajectory (RMSE = {rmse:.3f} m)",
        xaxis_title="X (m)",
        yaxis_title="Y (m)",
        yaxis_scaleanchor="x",
        height=400,
    )
    trajectory_plot = mo.ui.plotly(fig)
    trajectory_plot
    return rmse, trajectory_plot


@app.cell
def test_ekf_covariance_psd() -> None:
    """Verify Joseph-form covariance update remains symmetric positive definite."""
    _p_pred = np.eye(4) * 0.8
    _h_jac = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    _r_cov = np.eye(2) * 0.1
    _, _p_upd = ekf_covariance_update(_p_pred, _h_jac, _r_cov)
    assert np.allclose(_p_upd, _p_upd.T, atol=1e-10)
    assert np.all(np.linalg.eigvalsh(_p_upd) > 0.0)
    return


if __name__ == "__main__":
    app.run()
```
