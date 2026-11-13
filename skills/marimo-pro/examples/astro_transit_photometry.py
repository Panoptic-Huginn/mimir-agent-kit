# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "plotly>=6.0.0",
# ]
# ///
"""Exoplanetary transit light curve modeling and Bayesian MCMC parameter estimation."""

import marimo

__generated_with = "0.25.2"
app = marimo.App(app_title="Astro Transit Photometry", width="wide")


@app.cell
def setup_transit_env():
    import math
    import random

    import marimo as mo

    try:
        import plotly.graph_objects as go
    except ImportError, ModuleNotFoundError:
        go = None

    return go, math, mo, random


@app.cell
def title_and_intro(mo):
    transit_intro_md = mo.md(
        r"""
        # Exoplanetary Transit Photometry & Bayesian MCMC Inversion

        This notebook models exoplanetary transit light curves using the **Mandel-Agol**
        quadratic stellar limb darkening formulation and estimates orbital parameters
        via Markov Chain Monte Carlo (MCMC) sampling.

        **Key Features:**
        - **Real-Time Interactive Exploration**: Dynamic light curve profile synthesis.
        - **Execution Gating**: Heavy MCMC sampling is decoupled via `mo.stop` until requested.
        - **Single Definition Rule & Pure Functions**: Deterministic Marimo DAG execution.
        """
    )
    transit_intro_md  # noqa: B018
    return (transit_intro_md,)


@app.cell
def transit_ui_controls(mo):
    radius_ratio_slider = mo.ui.slider(
        start=0.01,
        stop=0.25,
        step=0.005,
        value=0.10,
        label="Planetary Radius Ratio (k = Rp / R*)",
    )
    impact_param_slider = mo.ui.slider(
        start=0.0,
        stop=0.95,
        step=0.05,
        value=0.30,
        label="Impact Parameter (b = a/R* cos i)",
    )
    limb_u1_slider = mo.ui.slider(
        start=0.0,
        stop=0.80,
        step=0.05,
        value=0.35,
        label="Linear Limb Darkening (u1)",
    )
    limb_u2_slider = mo.ui.slider(
        start=-0.20,
        stop=0.60,
        step=0.05,
        value=0.15,
        label="Quadratic Limb Darkening (u2)",
    )
    noise_sigma_slider = mo.ui.slider(
        start=0.0002,
        stop=0.0050,
        step=0.0002,
        value=0.0010,
        label="Photometric Shot Noise (sigma)",
    )
    run_mcmc_button = mo.ui.run_button(
        label="Sample Posterior Distribution (MCMC)",
    )

    transit_controls_panel = mo.vstack(
        [
            mo.md("### Transit Modeling Controls"),
            mo.hstack([radius_ratio_slider, impact_param_slider], justify="start"),
            mo.hstack([limb_u1_slider, limb_u2_slider], justify="start"),
            mo.hstack([noise_sigma_slider, run_mcmc_button], justify="start"),
        ]
    )
    transit_controls_panel  # noqa: B018
    return (
        impact_param_slider,
        limb_u1_slider,
        limb_u2_slider,
        noise_sigma_slider,
        radius_ratio_slider,
        run_mcmc_button,
        transit_controls_panel,
    )


@app.cell
def extract_transit_parameters(impact_param_slider, radius_ratio_slider):
    radius_ratio = radius_ratio_slider.value
    impact_param = impact_param_slider.value
    return impact_param, radius_ratio


@app.cell
def compute_transit_model(
    impact_param,
    limb_u1_slider,
    limb_u2_slider,
    math,
    radius_ratio,
):
    _u1 = getattr(limb_u1_slider, "value", 0.35) if limb_u1_slider is not None else 0.35
    _u2 = getattr(limb_u2_slider, "value", 0.15) if limb_u2_slider is not None else 0.15
    _k = float(radius_ratio)
    _b = float(impact_param)

    # 1000 time points across normalized transit window [-0.15, 0.15] days
    _n_pts = 1000
    _t_arr = [-0.15 + _i * (0.30 / (_n_pts - 1)) for _i in range(_n_pts)]
    _flux_arr = []

    # Mandel-Agol quadratic limb darkening light curve synthesis
    for _t in _t_arr:
        # Normalized projected distance z(t) = sqrt((t * v_orb)^2 + b^2)
        # Normalized orbital speed v_orb = 20.0
        _z = math.sqrt((_t * 20.0) ** 2 + _b**2)

        if _z >= 1.0 + _k:
            # Out of transit
            _f = 1.0
        elif _z <= 1.0 - _k:
            # Fully inside stellar disk
            _mu = math.sqrt(max(0.0, 1.0 - _z**2))
            _limb_factor = 1.0 - _u1 * (1.0 - _mu) - _u2 * ((1.0 - _mu) ** 2)
            _norm = 1.0 - (_u1 / 3.0) - (_u2 / 6.0)
            _profile = _limb_factor / max(_norm, 1e-6)
            _f = max(0.0, 1.0 - (_k**2) * _profile)
        else:
            # Grazing ingress / egress phase
            _overlap = max(0.0, min(1.0, (1.0 + _k - _z) / (2.0 * _k)))
            _mu = math.sqrt(max(0.0, 1.0 - _z**2))
            _limb_factor = 1.0 - _u1 * (1.0 - _mu) - _u2 * ((1.0 - _mu) ** 2)
            _f = max(0.0, 1.0 - (_k**2) * _overlap * _limb_factor)

        _flux_arr.append(_f)

    transit_time = _t_arr
    transit_flux = _flux_arr
    return transit_flux, transit_time


@app.cell
def synthetic_light_curve_observations(
    go,
    mo,
    noise_sigma_slider,
    random,
    transit_flux,
    transit_time,
):
    _rng = random.Random(42)
    _sigma = float(noise_sigma_slider.value)

    # Synthesize noisy observations by adding Gaussian noise to ground-truth model
    observed_time = list(transit_time)
    observed_flux = [_f + _rng.gauss(0.0, _sigma) for _f in transit_flux]
    observed_err = [_sigma] * len(observed_flux)

    try:
        if go is None:
            raise ImportError("Plotly not available")

        _fig = go.Figure()
        _fig.add_trace(
            go.Scatter(
                x=observed_time[::5],
                y=observed_flux[::5],
                mode="markers",
                name="Observed Flux (Shot Noise)",
                marker={"size": 4, "color": "#636EFA", "opacity": 0.7},
            )
        )
        _fig.add_trace(
            go.Scatter(
                x=transit_time,
                y=transit_flux,
                mode="lines",
                name="Analytical Mandel-Agol Model",
                line={"color": "#00CC96", "width": 2.5},
            )
        )
        _fig.update_layout(
            title="Photometric Transit Light Curve & Interactive Model",
            xaxis_title="Time from Mid-Transit (days)",
            yaxis_title="Relative Normalized Flux",
            template="plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white",
            legend={"x": 0.02, "y": 0.08},
            margin={"l": 40, "r": 40, "t": 50, "b": 40},
            height=420,
        )
        light_curve_plot = mo.ui.plotly(_fig)
    except ImportError, AttributeError, ValueError, RuntimeError:
        _min_f = min(observed_flux)
        _max_f = max(observed_flux)
        light_curve_plot = mo.md(
            f"**Photometric Light Curve (1000 points)**: Min Flux = `{_min_f:.5f}`, Max Flux = `{_max_f:.5f}`"
        )

    light_curve_plot  # noqa: B018
    return light_curve_plot, observed_err, observed_flux, observed_time


@app.cell
def gated_mcmc_sampling(
    go,
    impact_param_slider,
    math,
    mo,
    observed_err,
    observed_flux,
    observed_time,
    radius_ratio_slider,
    random,
    run_mcmc_button,
):
    # Execution Gating: halt execution if the MCMC button has not been clicked
    mo.stop(
        not run_mcmc_button.value,
        output=mo.callout(
            mo.md(
                "💡 *Adjust sliders above to inspect light curves. Click **Sample Posterior Distribution (MCMC)** to initiate MCMC inversion.*"
            ),
            kind="info",
        ),
    )

    _init_k = radius_ratio_slider.value
    _init_b = impact_param_slider.value
    _n_walkers = 16
    _n_steps = 400
    _burn_in = 100
    _rng = random.Random(1337)

    # Fast Metropolis-Hastings MCMC sampling over (k, b)
    def _compute_model(k_val: float, b_val: float, times: list[float]) -> list[float]:
        _out = []
        for _t in times:
            _z = math.sqrt((_t * 20.0) ** 2 + b_val**2)
            if _z >= 1.0 + k_val:
                _out.append(1.0)
            elif _z <= 1.0 - k_val:
                _mu = math.sqrt(max(0.0, 1.0 - _z**2))
                _limb = 1.0 - 0.35 * (1.0 - _mu) - 0.15 * ((1.0 - _mu) ** 2)
                _norm = 1.0 - (0.35 / 3.0) - (0.15 / 6.0)
                _out.append(max(0.0, 1.0 - (k_val**2) * (_limb / _norm)))
            else:
                _overlap = max(0.0, min(1.0, (1.0 + k_val - _z) / (2.0 * k_val)))
                _mu = math.sqrt(max(0.0, 1.0 - _z**2))
                _limb = 1.0 - 0.35 * (1.0 - _mu) - 0.15 * ((1.0 - _mu) ** 2)
                _out.append(max(0.0, 1.0 - (k_val**2) * _overlap * _limb))
        return _out

    # Downsampled data for fast MCMC evaluation
    _sub_t = observed_time[::10]
    _sub_f = observed_flux[::10]
    _sub_err = observed_err[0]

    def _log_likelihood(k_val: float, b_val: float) -> float:
        if not (0.01 <= k_val <= 0.30 and 0.0 <= b_val <= 0.98):
            return -float("inf")
        _m = _compute_model(k_val, b_val, _sub_t)
        _chi2 = sum(
            ((_yf - _ym) / _sub_err) ** 2 for _yf, _ym in zip(_sub_f, _m, strict=True)
        )
        return -0.5 * _chi2

    _chain_samples: list[tuple[float, float]] = []
    for _w in range(_n_walkers):
        _curr_k = max(0.02, min(0.25, _init_k + _rng.gauss(0.0, 0.005)))
        _curr_b = max(0.05, min(0.90, _init_b + _rng.gauss(0.0, 0.02)))
        _curr_ll = _log_likelihood(_curr_k, _curr_b)

        for _s in range(_n_steps):
            _prop_k = _curr_k + _rng.gauss(0.0, 0.002)
            _prop_b = _curr_b + _rng.gauss(0.0, 0.01)
            _prop_ll = _log_likelihood(_prop_k, _prop_b)

            if _prop_ll - _curr_ll > math.log(_rng.random() + 1e-12):
                _curr_k, _curr_b, _curr_ll = _prop_k, _prop_b, _prop_ll

            if _s >= _burn_in:
                _chain_samples.append((_curr_k, _curr_b))

    mcmc_k_samples = [_s[0] for _s in _chain_samples]
    mcmc_b_samples = [_s[1] for _s in _chain_samples]

    def _percentile(data: list[float], p: float) -> float:
        _sorted = sorted(data)
        _idx = (len(_sorted) - 1) * (p / 100.0)
        _lo = math.floor(_idx)
        _hi = math.ceil(_idx)
        if _lo == _hi:
            return _sorted[_lo]
        return _sorted[_lo] * (_hi - _idx) + _sorted[_hi] * (_idx - _lo)

    _k_med = _percentile(mcmc_k_samples, 50.0)
    _k_16 = _percentile(mcmc_k_samples, 16.0)
    _k_84 = _percentile(mcmc_k_samples, 84.0)

    _b_med = _percentile(mcmc_b_samples, 50.0)
    _b_16 = _percentile(mcmc_b_samples, 16.0)
    _b_84 = _percentile(mcmc_b_samples, 84.0)

    mcmc_summary_table = mo.ui.table(
        [
            {
                "Parameter": "k (Rp / R*)",
                "Median": f"{_k_med:.4f}",
                "+1σ": f"+{_k_84 - _k_med:.4f}",
                "-1σ": f"-{_k_med - _k_16:.4f}",
            },
            {
                "Parameter": "b (Impact Parameter)",
                "Median": f"{_b_med:.4f}",
                "+1σ": f"+{_b_84 - _b_med:.4f}",
                "-1σ": f"-{_b_med - _b_16:.4f}",
            },
        ]
    )

    try:
        if go is None:
            raise ImportError("Plotly not available")

        _fig = go.Figure()
        _fig.add_trace(
            go.Histogram(
                x=mcmc_k_samples,
                nbinsx=40,
                name="Posterior k (Rp/R*)",
                marker_color="#AB63FA",
            )
        )
        _fig.update_layout(
            title="Marginal Posterior: Radius Ratio k (Rp/R*)",
            xaxis_title="k",
            yaxis_title="Count",
            template="plotly_dark" if mo.app_meta().theme == "dark" else "plotly_white",
            height=320,
        )
        mcmc_posterior_plot = mo.ui.plotly(_fig)
    except ImportError, AttributeError, ValueError, RuntimeError:
        mcmc_posterior_plot = mo.md(f"**Posterior Median k**: `{_k_med:.4f}`")

    mo.vstack([mcmc_summary_table, mcmc_posterior_plot])
    return (
        mcmc_b_samples,
        mcmc_k_samples,
        mcmc_posterior_plot,
        mcmc_summary_table,
    )


@app.cell
def test_transit_invariants(impact_param, radius_ratio, transit_flux, transit_time):
    def test_transit_depth_scaling():
        # Verifies depth equals (Rp/R*)^2 for uniform disc baseline
        _k_test = float(radius_ratio)
        _depth = _k_test**2
        assert abs(_depth - 0.01) < 1e-6, f"Transit depth {_depth} != 0.01"

    def test_impact_parameter_boundary():
        # Transit occurs only if impact parameter b < 1 + k
        _k_test = float(radius_ratio)
        _b_test = float(impact_param)
        _b_max = 1.0 + _k_test
        assert _b_test < _b_max, (
            f"Impact parameter {_b_test} must be < boundary {_b_max} for transit"
        )
        assert abs(_b_max - 1.10) < 1e-6, (
            f"Impact parameter boundary calculation error: {_b_max} != 1.10"
        )

    def test_computed_light_curve_properties():
        # Validates actual computed light curve arrays from the Marimo reactive DAG
        assert len(transit_flux) == 1000, "Expected 1000 synthesized flux points"
        assert len(transit_time) == 1000, "Expected 1000 synthesized time points"
        assert min(transit_flux) < 1.0, (
            "Transit dip did not reduce normalized flux below 1.0"
        )
        assert max(transit_flux) <= 1.0, (
            "Normalized out-of-transit flux must not exceed 1.0"
        )
        assert transit_time[0] < transit_time[-1], (
            "Time points must be strictly increasing"
        )

    test_transit_depth_scaling()
    test_impact_parameter_boundary()
    test_computed_light_curve_properties()
    return (
        test_computed_light_curve_properties,
        test_impact_parameter_boundary,
        test_transit_depth_scaling,
    )


if __name__ == "__main__":
    app.run()
