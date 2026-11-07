# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "marimo>=0.25.2",
#     "plotly>=6.0.0",
# ]
# ///
"""Bayesian MCMC convergence diagnostics, Gelman-Rubin R-hat, and integrated autocorrelation time."""

import marimo

__generated_with = "0.25.2"
app = marimo.App(
    width="wide",
    app_title="Bayesian MCMC Diagnostics",
)


@app.cell
def setup_diagnostic_env():
    import math
    import random

    import marimo as mo

    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError, ModuleNotFoundError:
        go = None
        make_subplots = None

    return go, make_subplots, math, mo, random


@app.cell
def title_and_intro(mo):
    diagnostic_intro_md = mo.md(
        r"""
        # Bayesian MCMC Convergence Diagnostics & Embedded Pytest Verification

        This notebook implements rigorous Markov Chain Monte Carlo (MCMC) convergence diagnostics:
        - **Gelman-Rubin Potential Scale Reduction Factor ($\hat{R}$)**: Evaluates variance between and within parallel chains.
        - **Integrated Autocorrelation Time ($\tau_{\text{int}}$)**: Quantifies chain autocorrelation and effective sample size ($N_{\text{eff}}$).
        - **Embedded Pytest Discovery**: Test assertions embedded directly within notebook cells for continuous verification.
        """
    )
    return (diagnostic_intro_md,)


@app.cell
def diagnostic_ui_controls(mo):
    chain_count_slider = mo.ui.slider(
        start=2,
        stop=8,
        step=1,
        value=4,
        label="Number of Parallel Chains (M)",
    )
    chain_length_slider = mo.ui.slider(
        start=200,
        stop=2000,
        step=100,
        value=500,
        label="Iterations per Chain (N)",
    )
    chain_drift_slider = mo.ui.slider(
        start=0.0,
        stop=3.0,
        step=0.2,
        value=0.0,
        label="Between-Chain Mean Dispersal (Drift)",
    )
    diagnostic_controls_panel = mo.vstack(
        [
            mo.md("### MCMC Chain Simulation Parameters"),
            mo.hstack([chain_count_slider, chain_length_slider], justify="start"),
            chain_drift_slider,
        ]
    )
    return (
        chain_count_slider,
        chain_drift_slider,
        chain_length_slider,
        diagnostic_controls_panel,
    )


@app.cell
def generate_mcmc_chains(
    chain_count_slider,
    chain_drift_slider,
    chain_length_slider,
    random,
):
    _rng = random.Random(42)
    _m = int(chain_count_slider.value)
    _n = int(chain_length_slider.value)
    _drift = float(chain_drift_slider.value)

    # Synthesize AR(1) autoregressive chains: x_t = phi * x_{t-1} + sqrt(1 - phi^2) * eps
    _phi = 0.60
    _var_innov = (1.0 - _phi**2) ** 0.5
    _chains: list[list[float]] = []

    for _chain_idx in range(_m):
        _mean_offset = (_chain_idx - (_m - 1) / 2.0) * _drift
        _chain = [0.0] * _n
        _curr = _rng.gauss(_mean_offset, 1.0)
        for _t in range(_n):
            _curr = (
                _mean_offset
                + _phi * (_curr - _mean_offset)
                + _var_innov * _rng.gauss(0.0, 1.0)
            )
            _chain[_t] = _curr
        _chains.append(_chain)

    simulated_mcmc_chains = _chains
    return (simulated_mcmc_chains,)


@app.cell
def compute_gelman_rubin_diagnostic(math, simulated_mcmc_chains):
    _m = len(simulated_mcmc_chains)
    _n = len(simulated_mcmc_chains[0])

    # Chain means and overall grand mean
    _chain_means = [sum(_c) / _n for _c in simulated_mcmc_chains]
    _overall_mean = sum(_chain_means) / _m

    # Between-chain variance B
    _b_var = (_n / (_m - 1.0)) * sum(
        (_mean - _overall_mean) ** 2 for _mean in _chain_means
    )

    # Within-chain variance W
    _chain_vars = [
        sum((_x - _mean) ** 2 for _x in _chain) / (_n - 1.0)
        for _chain, _mean in zip(simulated_mcmc_chains, _chain_means, strict=True)
    ]
    _w_var = sum(_chain_vars) / _m

    # Estimated marginal posterior variance
    _var_plus = ((_n - 1.0) / _n) * _w_var + (1.0 / _n) * _b_var
    _r_hat = math.sqrt(_var_plus / max(_w_var, 1e-12))

    gelman_rubin_r_hat = _r_hat
    chains_converged = bool(_r_hat < 1.05)
    return chains_converged, gelman_rubin_r_hat


@app.cell
def compute_autocorrelation_time(simulated_mcmc_chains):
    # Compute average autocorrelation function and integrated autocorrelation time
    _m = len(simulated_mcmc_chains)
    _n = len(simulated_mcmc_chains[0])
    _max_lag = min(100, _n // 4)

    _avg_rho = [0.0] * _max_lag
    for _chain in simulated_mcmc_chains:
        _mean = sum(_chain) / _n
        _denom = sum((_x - _mean) ** 2 for _x in _chain)
        if _denom <= 1e-12:
            continue
        for _lag in range(_max_lag):
            _num = sum(
                (_chain[_t] - _mean) * (_chain[_t + _lag] - _mean)
                for _t in range(_n - _lag)
            )
            _avg_rho[_lag] += (_num / _denom) / _m

    # Integrated autocorrelation time: tau_int = 1 + 2 * sum_{k=1}^K rho(k)
    # Truncate at first negative autocorrelation or window limit
    _tau = 1.0
    for _lag in range(1, _max_lag):
        if _avg_rho[_lag] <= 0.0:
            break
        _tau += 2.0 * _avg_rho[_lag]

    integrated_autocorr_time = _tau
    effective_sample_size = (_m * _n) / max(_tau, 1.0)
    autocorr_lags = list(range(_max_lag))
    autocorr_values = _avg_rho
    return (
        autocorr_lags,
        autocorr_values,
        effective_sample_size,
        integrated_autocorr_time,
    )


@app.cell
def visualize_diagnostics(
    autocorr_lags,
    autocorr_values,
    chains_converged,
    effective_sample_size,
    gelman_rubin_r_hat,
    go,
    integrated_autocorr_time,
    make_subplots,
    mo,
    simulated_mcmc_chains,
):
    # Statistical KPI cards
    diagnostic_kpi_cards = mo.hstack(
        [
            mo.stat(
                value=f"{gelman_rubin_r_hat:.4f}",
                label="Gelman-Rubin R-hat",
                caption="Convergence Target < 1.05",
            ),
            mo.stat(
                value=f"{integrated_autocorr_time:.2f} iters",
                label="Autocorrelation Time (tau)",
                caption="Window cutoff lag",
            ),
            mo.stat(
                value=f"{int(effective_sample_size):,}",
                label="Effective Sample Size (N_eff)",
                caption="Across all chains",
            ),
            mo.stat(
                value="CONVERGED" if chains_converged else "NON-CONVERGED",
                label="Convergence Verdict",
                caption="Stationarity check",
            ),
        ]
    )

    try:
        if go is None or make_subplots is None:
            raise ImportError("Plotly not available")

        _fig = make_subplots(
            rows=1,
            cols=2,
            subplot_titles=[
                "Parallel MCMC Chains Trace",
                "Mean Autocorrelation Function",
            ],
        )

        for _idx, _chain in enumerate(simulated_mcmc_chains):
            _fig.add_trace(
                go.Scatter(
                    y=_chain,
                    mode="lines",
                    name=f"Chain {_idx + 1}",
                    opacity=0.75,
                ),
                row=1,
                col=1,
            )

        _fig.add_trace(
            go.Scatter(
                x=autocorr_lags,
                y=autocorr_values,
                mode="lines+markers",
                name="Autocorrelation rho(lag)",
                line={"color": "#FF6692", "width": 2},
                marker={"size": 4},
            ),
            row=1,
            col=2,
        )

        _fig.update_layout(
            template="plotly_white",
            height=380,
            margin={"l": 40, "r": 40, "t": 50, "b": 40},
        )
        diagnostic_dashboard_plot = mo.ui.plotly(_fig)
    except ImportError, AttributeError, ValueError, RuntimeError, TypeError:
        diagnostic_dashboard_plot = mo.md(
            f"**Diagnostic Summary**: R-hat = `{gelman_rubin_r_hat:.4f}`, tau = `{integrated_autocorr_time:.2f}`"
        )

    return diagnostic_dashboard_plot, diagnostic_kpi_cards


@app.cell
def test_bayesian_mcmc_diagnostics(
    chain_drift_slider,
    chains_converged,
    effective_sample_size,
    gelman_rubin_r_hat,
    integrated_autocorr_time,
    math,
):
    def test_mcmc_convergence():
        """Verify that default stationary MCMC chains satisfy Gelman-Rubin convergence criteria."""
        if chain_drift_slider.value == 0.0:
            assert gelman_rubin_r_hat < 1.05, (
                f"R-hat {gelman_rubin_r_hat:.4f} must be < 1.05"
            )
            assert chains_converged is True, (
                "Chains must converge under stationary conditions"
            )
        else:
            assert gelman_rubin_r_hat >= 0.95, (
                f"R-hat {gelman_rubin_r_hat:.4f} must be >= 0.95 under drifted conditions"
            )

    def test_autocorrelation_bounded():
        """Verify that integrated autocorrelation time is finite, positive, and bounded."""
        assert integrated_autocorr_time > 0.0, (
            "Autocorrelation time must be strictly positive"
        )
        assert integrated_autocorr_time < 500.0, (
            f"Autocorrelation time {integrated_autocorr_time:.2f} exceeds limit"
        )
        assert effective_sample_size > 0.0, "Effective sample size must be positive"
        if chain_drift_slider.value == 0.0:
            assert effective_sample_size > 10.0, (
                "Effective sample size must exceed 10 in nominal mode"
            )

    def test_divergent_chain_detection():
        """Verify that non-converged chains with drifted means produce R-hat >= 1.10."""
        _div_chains = [
            [-5.0 + 0.1 * _i for _i in range(100)],
            [0.0 + 0.1 * _i for _i in range(100)],
            [5.0 + 0.1 * _i for _i in range(100)],
            [10.0 + 0.1 * _i for _i in range(100)],
        ]
        _m = len(_div_chains)
        _n = len(_div_chains[0])
        _means = [sum(_c) / _n for _c in _div_chains]
        _grand_mean = sum(_means) / _m
        _b = (_n / (_m - 1.0)) * sum((_mu - _grand_mean) ** 2 for _mu in _means)
        _w = (
            sum(
                sum((_x - _mu) ** 2 for _x in _c) / (_n - 1.0)
                for _c, _mu in zip(_div_chains, _means, strict=True)
            )
            / _m
        )
        _r_hat_div = math.sqrt((((_n - 1.0) / _n) * _w + (1.0 / _n) * _b) / _w)
        assert _r_hat_div > 1.10, (
            f"Expected divergent R-hat > 1.10, got {_r_hat_div:.4f}"
        )

    test_mcmc_convergence()
    test_autocorrelation_bounded()
    test_divergent_chain_detection()
    return (
        test_autocorrelation_bounded,
        test_divergent_chain_detection,
        test_mcmc_convergence,
    )


if __name__ == "__main__":
    app.run()
