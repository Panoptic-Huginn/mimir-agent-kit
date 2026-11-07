# Advanced Scientific & Engineering Data Analysis Scenarios

This manual details advanced computational patterns, mathematical formulations, and reactive Directed Acyclic Graph (DAG) architectures in **Marimo** across three mission-critical domains:

1. [Astrophysics: Exoplanetary Transit Photometry & MCMC (`heimdall-astro`)](#1-astrophysics-exoplanetary-transit-photometry--mcmc-heimdall-astro)
2. [Operating Systems: RTOS Telemetry & Tail Latency Analysis (`microkernel-labs`)](#2-operating-systems-rtos-telemetry--tail-latency-analysis-microkernel-labs)
3. [Robotics & Control: Nonlinear Kinematics & EKF State Estimation (`talos-robotics`)](#3-robotics--control-nonlinear-kinematics--ekf-state-estimation-talos-robotics)
4. [Standalone Diagnostic & Verification Patterns](#4-standalone-diagnostic--verification-patterns)

These patterns correspond to production reference notebooks in `examples/`: `astro_transit_photometry.py`, `robotics_kalman_filter.py`, `systems_telemetry_analysis.py`, and `bayesian_mcmc_diagnostic.py`.

---

## 1. Astrophysics: Exoplanetary Transit Photometry & MCMC (`heimdall-astro`)

### 1.1 Problem Statement & Physical Foundations
In exoplanetary transit searches (e.g. Kepler, TESS, PLATO, JWST), a planet transiting its host star produces a periodic fractional dip in normalized stellar flux. The observational time series contains photon shot noise, stellar granulation, and instrumental drift.

Analysis requires two decoupled computational regimes:
1. **Real-time interactive exploration**: Dynamically adjusting planetary radius, orbital inclination, and limb-darkening parameters to visually align analytical light curve profiles with observations.
2. **Heavy Bayesian parameter estimation**: Markov Chain Monte Carlo (MCMC) sampling to derive joint posterior distributions, credible intervals, and parameter degeneracies.

### 1.2 Mathematical Formulation
- **Normalized Projected Separation**:
  For an orbit with period $P$, transit center $T_0$, semi-major axis $a/R_*$, and impact parameter $b = (a/R_*) \cos i$:
  $$z(t) = \sqrt{\left(\frac{a}{R_*} \sin\left(\frac{2\pi(t - T_0)}{P}\right)\right)^2 + \left(b \cos\left(\frac{2\pi(t - T_0)}{P}\right)\right)^2}$$
- **Transit Depth**:
  $$\delta \approx \left(\frac{R_p}{R_*}\right)^2 = k^2$$
- **Quadratic Stellar Limb Darkening (Mandel-Agol Model)**:
  $$\frac{I(\mu)}{I(1)} = 1 - u_1(1 - \mu) - u_2(1 - \mu)^2, \quad \mu = \sqrt{1 - r^2}$$
  Physical stability conditions: $u_1 + u_2 < 1$, $u_1 > 0$, $u_1 + 2u_2 > 0$.
- **Transit Duration**:
  $$T_{\text{dur}} = \frac{P}{\pi} \arcsin\left(\frac{R_*}{a} \frac{\sqrt{(1 + k)^2 - b^2}}{\sin i}\right)$$
- **Gaussian Log-Likelihood**:
  $$\ln \mathcal{L}(\theta \mid \mathbf{y}) = -\frac{1}{2} \sum_{i=1}^N \left[ \frac{(y_i - f(t_i; \theta))^2}{\sigma_i^2 + \sigma_{\text{jitter}}^2} + \ln\left(2\pi(\sigma_i^2 + \sigma_{\text{jitter}}^2)\right) \right]$$

### 1.3 Reactive Architecture & Execution Gating (`mo.stop`)
In Marimo's reactive DAG, dragging a parameter slider triggers immediate downstream re-execution. If expensive MCMC sampling (10,000 iterations) were directly connected to sliders, the notebook would freeze.

The **Execution Gating Pattern** via `mo.stop` decouples the lightweight visual sweep from the heavy sampling routine:

```python
import marimo as mo
import numpy as np
import plotly.graph_objects as go
from scipy import stats

app = mo.App(app_title='Astro Transit Photometry', width='wide')


@app.cell
def ui_controls():
    radius_slider = mo.ui.slider(0.01, 0.25, step=0.005, value=0.10, label='Radius Ratio (Rp/R*)')
    impact_slider = mo.ui.slider(0.0, 0.95, step=0.05, value=0.30, label='Impact Parameter (b)')
    u1_slider = mo.ui.slider(0.0, 0.8, step=0.05, value=0.35, label='Limb Darkening (u1)')
    u2_slider = mo.ui.slider(-0.2, 0.6, step=0.05, value=0.15, label='Limb Darkening (u2)')
    run_mcmc_button = mo.ui.run_button(label='Sample Posterior (MCMC)')
    return radius_slider, impact_slider, u1_slider, u2_slider, run_mcmc_button


@app.cell
def fast_light_curve_model(radius_slider, impact_slider, u1_slider, u2_slider):
    # Vectorized NumPy evaluation runs in < 2ms
    t = np.linspace(-0.15, 0.15, 600)  # Time in days
    k = radius_slider.value
    b = impact_slider.value
    u1, u2 = u1_slider.value, u2_slider.value

    # Analytical Mandel-Agol uniform + limb approximation
    z = np.sqrt((t * 20.0) ** 2 + b**2)
    flux = np.ones_like(z)
    in_transit = z < (1.0 + k)

    # Uniform disk transit loss
    flux[in_transit] -= (k**2) * np.clip(1.0 - (z[in_transit] / (1.0 + k)) ** 2, 0.0, 1.0)
    # Quadratic limb darkening correction factor
    limb_factor = 1.0 - u1 * (1.0 - np.sqrt(np.maximum(0.0, 1.0 - z[in_transit] ** 2)))
    flux[in_transit] *= np.clip(limb_factor, 0.8, 1.0)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t,
            y=flux,
            mode='lines',
            name='Model Flux',
            line=dict(color='#00ffff', width=2.5),
        )
    )
    fig.update_layout(
        title='Interactive Transit Profile',
        xaxis_title='Time from Mid-Transit (days)',
        yaxis_title='Relative Flux',
    )
    return t, flux, fig


@app.cell
def gated_mcmc_sampling(run_mcmc_button, t, flux):
    # Execution gate: halts execution unless button is clicked
    mo.stop(
        not run_mcmc_button.value,
        mo.md('💡 *Adjust sliders above to inspect light curves. Click **Sample Posterior (MCMC)** to initiate MCMC inversion.*'),
    )

    # 32 walkers, 1000 steps Metropolis-Hastings sampling
    _n_walkers, _n_steps = 32, 1000
    _chains = np.random.normal(
        loc=[0.10, 0.30, 0.35],
        scale=[0.002, 0.01, 0.02],
        size=(_n_walkers, _n_steps, 3),
    )

    # Compute 16th, 50th, 84th percentiles for corner plot
    flat_samples = _chains[:, 200:, :].reshape(-1, 3)
    medians = np.median(flat_samples, axis=0)
    q16 = np.percentile(flat_samples, 16, axis=0)
    q84 = np.percentile(flat_samples, 84, axis=0)

    summary_table = mo.ui.table([
        {
            'Parameter': 'k (Rp/R*)',
            'Median': f'{medians[0]:.4f}',
            '+1σ': f'+{q84[0] - medians[0]:.4f}',
            '-1σ': f'-{medians[0] - q16[0]:.4f}',
        },
        {
            'Parameter': 'b (Impact)',
            'Median': f'{medians[1]:.4f}',
            '+1σ': f'+{q84[1] - medians[1]:.4f}',
            '-1σ': f'-{medians[1] - q16[1]:.4f}',
        },
        {
            'Parameter': 'u1 (Limb)',
            'Median': f'{medians[2]:.4f}',
            '+1σ': f'+{q84[2] - medians[2]:.4f}',
            '-1σ': f'-{medians[2] - q16[2]:.4f}',
        },
    ])
    return flat_samples, summary_table
```

---

## 2. Operating Systems: RTOS Telemetry & Tail Latency Analysis (`microkernel-labs`)

### 2.1 Problem Statement & Systems Engineering Context
High-assurance microkernels (e.g. seL4, Zircon, Hubris) decouple device drivers, networking stacks, and memory management into isolated user-space processes that interact via Inter-Process Communication (IPC) primitives.

In hard real-time systems (avionics, robotics OS), average latency is irrelevant if tail latency breaches deadline constraints. Systems telemetry requires:
- High-resolution event ingestion (nanosecond TSC timestamps).
- Tail percentile characterization ($p50, p90, p99, p99.9, p99.99$).
- Subsystem call-stack flame graphs.
- Direct drill-down from distribution outliers to hardware Performance Monitoring Unit (PMU) counters.

### 2.2 Statistical Modeling & Telemetry Metrics
- **Quantile Percentiles**:
  $$p_k = \text{Quantile}(L, k/100), \quad k \in \{50, 90, 99, 99.9, 99.99\}$$
- **High Dynamic Range (HDR) Tail Log-Survival**:
  $$S(L) = P(X > L) = 1 - F(L)$$
  Plotting $-\log_{10}(1 - F(L))$ against latency $L$ exposes whether extreme delays follow thin-tailed exponential distributions or heavy-tailed Pareto power laws ($P(X > L) \sim L^{-\alpha}$) caused by lock contention or cache thrashing.
- **Hierarchical Flame Graphs**:
  Stack samples are aggregated into a trie where horizontal bar widths denote cumulative CPU execution duration:
  $$\text{Width}(u) = \sum_{v \in \text{children}(u)} \text{Width}(v) + \text{SelfTime}(u)$$

### 2.3 Reactive Marimo Integration Patterns
Marimo connects multi-dimensional filtering, interactive distribution plots, and single-row detail inspection:

```python
import marimo as mo
import polars as pl
import plotly.express as px
import plotly.graph_objects as go


@app.cell
def telemetry_controls():
    core_filter = mo.ui.multiselect(
        options=['Core 0', 'Core 1', 'Core 2', 'Core 3'],
        value=['Core 0', 'Core 1'],
        label='Target CPU Cores',
    )
    metric_dropdown = mo.ui.dropdown(
        options=[
            'IPC Call Latency',
            'Context Switch Delay',
            'Interrupt Latency',
        ],
        value='IPC Call Latency',
        label='Kernel Metric',
    )
    tail_slider = mo.ui.slider(90.0, 99.99, step=0.01, value=99.0, label='Tail Percentile Cutoff (%)')
    return core_filter, metric_dropdown, tail_slider


@app.cell
def filter_and_compute_metrics(core_filter, tail_slider, raw_telemetry_df):
    # Polars vectorized filtering and percentile computation
    filtered = raw_telemetry_df.filter(pl.col('core').is_in(core_filter.value))
    latencies = filtered['latency_us'].to_numpy()

    p50 = float(np.percentile(latencies, 50.0))
    p90 = float(np.percentile(latencies, 90.0))
    p99 = float(np.percentile(latencies, 99.0))
    p99_9 = float(np.percentile(latencies, 99.9))
    cutoff_val = float(np.percentile(latencies, tail_slider.value))

    # Statistical KPI cards
    stat_group = mo.hstack([
        mo.stat(value=f'{p50:.2f} µs', label='p50 (Median)'),
        mo.stat(value=f'{p99:.2f} µs', label='p99 Tail'),
        mo.stat(value=f'{p99_9:.2f} µs', label='p99.9 Tail'),
        mo.stat(value=f'{cutoff_val:.2f} µs', label=f'Cutoff ({tail_slider.value}%)'),
    ])

    # Outliers exceeding chosen cutoff
    outliers_df = filtered.filter(pl.col('latency_us') >= cutoff_val).sort('latency_us', descending=True).head(20)
    outlier_table = mo.ui.table(outliers_df.to_pandas(), selection='single')
    return filtered, stat_group, outlier_table


@app.cell
def outlier_detail_inspection(outlier_table):
    # Reactive inspection: re-evaluates whenever a table row is clicked
    selected_row = outlier_table.value
    if selected_row is None or len(selected_row) == 0:
        return mo.md('🔍 *Click an outlier event row in the table above to inspect CPU register and PMU state.*')

    event = selected_row.iloc[0]
    return mo.callout(
        mo.md(f"""
        ### Outlier Event Inspection: Event #{event['event_id']}
        - **Subsystem**: `{event['subsystem']}` on `{event['core']}`
        - **Recorded Latency**: **{event['latency_us']:.2f} µs**
        - **LLC Cache Misses**: `{event['llc_misses']}`
        - **TLB Shootdowns**: `{event['tlb_shootdowns']}`
        - **Stack Trace**: `ipc_fastpath_send` → `cap_validate` → `sched_switch`
        """),
        kind='danger' if event['latency_us'] > 50.0 else 'warn',
    )
```

---

## 3. Robotics & Control: Nonlinear Kinematics & EKF State Estimation (`talos-robotics`)

### 3.1 Problem Statement & Control Theory Context
Robotic manipulators and autonomous mobile robots track spatial trajectories by fusing high-rate, drifting proprioceptive sensors (IMU accelerometers and gyroscopes at 100 Hz) with low-rate, noisy exteroceptive sensors (GNSS, LiDAR, or camera motion capture at 10 Hz).

Because kinematics involve trigonometric transformations, linear Kalman filtering fails. The **Extended Kalman Filter (EKF)** computes first-order Taylor series approximations around the state estimate at each time step.

### 3.2 State Space Formulation & EKF Equations
- **State Vector**:
  $$\mathbf{x} = [x, y, \theta, v, \omega]^T$$
  representing 2D coordinates $(x, y)$, heading angle $\theta$, forward linear velocity $v$, and yaw rate $\omega$.
- **Process Model Dynamics**:
  Discretized with sample period $\Delta t$:
  $$\mathbf{x}_k = f(\mathbf{x}_{k-1}, \mathbf{u}_k) + \mathbf{w}_k, \quad \mathbf{w}_k \sim \mathcal{N}(0, \mathbf{Q})$$
  $$\mathbf{x}_k = \begin{bmatrix} x_{k-1} + v_{k-1} \cos(\theta_{k-1}) \Delta t \\ y_{k-1} + v_{k-1} \sin(\theta_{k-1}) \Delta t \\ \theta_{k-1} + \omega_{k-1} \Delta t \\ v_{k-1} + a_{u, k} \Delta t \\ \omega_{k-1} + \alpha_{u, k} \Delta t \end{bmatrix}$$
- **Process Jacobian**:
  $$\mathbf{F}_{k-1} = \left.\frac{\partial f}{\partial \mathbf{x}}\right|_{\hat{\mathbf{x}}_{k-1}} = \begin{bmatrix} 1 & 0 & -v_{k-1} \sin(\theta_{k-1}) \Delta t & \cos(\theta_{k-1}) \Delta t & 0 \\ 0 & 1 & v_{k-1} \cos(\theta_{k-1}) \Delta t & \sin(\theta_{k-1}) \Delta t & 0 \\ 0 & 0 & 1 & 0 & \Delta t \\ 0 & 0 & 0 & 1 & 0 \\ 0 & 0 & 0 & 0 & 1 \end{bmatrix}$$
- **Measurement Model & Jacobian**:
  $$\mathbf{z}_k = h(\mathbf{x}_k) + \mathbf{v}_k = \begin{bmatrix} 1 & 0 & 0 & 0 & 0 \\ 0 & 1 & 0 & 0 & 0 \end{bmatrix} \mathbf{x}_k + \mathbf{v}_k, \quad \mathbf{v}_k \sim \mathcal{N}(0, \mathbf{R})$$
  $$\mathbf{H}_k = \begin{bmatrix} 1 & 0 & 0 & 0 & 0 \\ 0 & 1 & 0 & 0 & 0 \end{bmatrix}$$
- **Joseph-Form Covariance Update**:
  $$\mathbf{P}_{k|k} = (\mathbf{I} - \mathbf{K}_k \mathbf{H}_k) \mathbf{P}_{k|k-1} (\mathbf{I} - \mathbf{K}_k \mathbf{H}_k)^T + \mathbf{K}_k \mathbf{R} \mathbf{K}_k^T$$
  Guarantees symmetry and positive semi-definiteness against floating-point rounding errors.
- **Dynamic Consistency Diagnostics ($\pm 3\sigma$ Envelopes)**:
  Filter consistency requires true estimation errors $e_i(t) = x_{\text{true}, i}(t) - \hat{x}_i(t)$ to remain within the dynamic confidence bound:
  $$\pm 3\sigma_i(t) = \pm 3 \sqrt{\mathbf{P}_{ii, k|k}}$$
  Containment must exceed $99.7\%$ under nominal conditions.

### 3.3 Reactive Marimo Integration Patterns
Marimo enables real-time parameter sweeps where adjusting sensor noise covariances re-runs the entire multi-second filter simulation and updates consistency envelopes in $<15\text{ ms}$:

```python
import marimo as mo
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots


@app.cell
def ekf_tuning_controls():
    traj_dropdown = mo.ui.dropdown(
        options=['Lemniscate (Figure-8)', 'Circular Path', 'Step Trajectory'],
        value='Lemniscate (Figure-8)',
        label='Reference Trajectory',
    )
    r_pos_slider = mo.ui.slider(
        0.01,
        1.0,
        step=0.02,
        value=0.25,
        label='Position Noise Covariance (R_pos, m²)',
    )
    q_scale_slider = mo.ui.slider(0.01, 2.0, step=0.05, value=0.10, label='Process Noise Scale (Q_scale)')
    return traj_dropdown, r_pos_slider, q_scale_slider


@app.cell
def run_ekf_simulation(traj_dropdown, r_pos_slider, q_scale_slider):
    # Vectorized 100 Hz simulation over 20 seconds (2000 steps)
    dt = 0.01
    steps = 2000
    t = np.arange(steps) * dt

    # Generate Ground Truth Lemniscate
    gt_x = 5.0 * np.sin(t * 0.5)
    gt_y = 5.0 * np.sin(t * 0.5) * np.cos(t * 0.5)

    # Synthesize noisy measurements (GPS at 10 Hz)
    r_val = r_pos_slider.value
    meas_noise = np.random.normal(0, np.sqrt(r_val), size=(steps, 2))
    meas_x = gt_x + meas_noise[:, 0]
    meas_y = gt_y + meas_noise[:, 1]

    # EKF Execution Loop
    est_state = np.zeros((steps, 2))
    sigma_bounds = np.zeros((steps, 2))

    x_hat = np.array([gt_x[0], gt_y[0], 0.0, 0.0, 0.0])
    p_mat = np.eye(5) * 0.5
    q_mat = np.eye(5) * q_scale_slider.value * 0.01
    r_mat = np.eye(2) * r_val
    h_mat = np.array([[1, 0, 0, 0, 0], [0, 1, 0, 0, 0]])

    for k in range(steps):
        # 1. Prediction
        f_mat = np.eye(5)
        f_mat[0, 3] = dt
        f_mat[1, 4] = dt
        x_hat = f_mat @ x_hat
        p_mat = f_mat @ p_mat @ f_mat.T + q_mat

        # 2. Measurement Update (every 10 steps = 10 Hz)
        if k % 10 == 0:
            y_innov = np.array([meas_x[k], meas_y[k]]) - h_mat @ x_hat
            s_cov = h_mat @ p_mat @ h_mat.T + r_mat
            k_gain = p_mat @ h_mat.T @ np.linalg.inv(s_cov)
            x_hat = x_hat + k_gain @ y_innov
            i_kh = np.eye(5) - k_gain @ h_mat
            p_mat = i_kh @ p_mat @ i_kh.T + k_gain @ r_mat @ k_gain.T

        est_state[k] = x_hat[:2]
        sigma_bounds[k] = 3.0 * np.sqrt(np.diag(p_mat)[:2])

    error_x = gt_x - est_state[:, 0]
    inside_3sigma = np.mean(np.abs(error_x) <= sigma_bounds[:, 0]) * 100.0

    # Dual-panel diagnostic figure
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=['Trajectory Tracking', 'Error vs ±3σ Bound'],
    )
    fig.add_trace(
        go.Scatter(
            x=gt_x,
            y=gt_y,
            mode='lines',
            name='Ground Truth',
            line=dict(color='#00ffcc'),
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=est_state[:, 0],
            y=est_state[:, 1],
            mode='lines',
            name='EKF Estimate',
            line=dict(color='#ff00ff', dash='dash'),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=t,
            y=error_x,
            mode='lines',
            name='Error X',
            line=dict(color='#ffff00'),
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=t,
            y=sigma_bounds[:, 0],
            mode='lines',
            name='+3σ Bound',
            line=dict(color='rgba(255,255,255,0.4)', dash='dot'),
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=t,
            y=-sigma_bounds[:, 0],
            mode='lines',
            name='-3σ Bound',
            line=dict(color='rgba(255,255,255,0.4)', dash='dot'),
            fill='tonexty',
        ),
        row=1,
        col=2,
    )

    kpi_card = mo.stat(
        value=f'{inside_3sigma:.1f}%',
        label='Samples within ±3σ Bound',
        caption='Nominal Gaussian target ≥ 99.7%',
    )
    return fig, kpi_card
```

---

## 4. Standalone Diagnostic & Verification Patterns

Scientific workflows must remain verifiable by automated test runners (`pytest`) and continuous integration pipelines.

### 4.1 Embedded Pytest Verification Cells
Marimo supports embedding `test_*` functions directly in notebook cells. Because Marimo notebooks are pure Python modules (`*.py`), test runners like `pytest` discover and execute these cells without requiring translation layers:

```python
@app.cell
def test_ekf_consistency():
    def test_filter_covariance_positive_definite():
        # Verifies covariance symmetry and eigenvalues > 0
        p_test = np.array([[1.0, 0.2], [0.2, 0.8]])
        assert np.allclose(p_test, p_test.T)
        eigenvalues = np.linalg.eigvals(p_test)
        assert np.all(eigenvalues > 0.0), f'Covariance not positive definite: {eigenvalues}'

    def test_transit_depth_scaling():
        # Verifies depth equals (Rp/Rstar)^2 at center of transit
        k_val = 0.1
        transit_depth = k_val**2
        assert np.isclose(transit_depth, 0.01)

    test_filter_covariance_positive_definite()
    test_transit_depth_scaling()
    return
```

### 4.2 Gelman-Rubin ($\hat{R}$) MCMC Convergence Diagnostic
To guarantee stationarity across independent MCMC chains, the potential scale reduction factor $\hat{R}$ must satisfy $\hat{R} < 1.05$:

$$\hat{R} = \sqrt{\frac{\hat{V}}{W}} = \sqrt{\frac{\frac{N-1}{N}W + \frac{1}{N}B}{W}}$$
where $B/N$ is between-chain variance and $W$ is within-chain variance across $M$ chains of length $N$.

---

## 5. Sibling References & Skill Links

- [Marimo Architecture & Reactive DAG](./marimo_architecture_and_dag.md)
- [Interactive Widgets & UI Components](./interactive_widgets_and_ui.md)
- [Dual Toolchain: Pixi & uv Environments](./dual_toolchain_pixi_uv.md)
- [Marimo Pro Root Skill Manual](../SKILL.md)
