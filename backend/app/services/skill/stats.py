"""Numerical building blocks (pure Python, no NumPy dependency; K = number of models is small).

* Metrics on (forecast, observed) pairs.
* Constrained least squares on the probability simplex (w >= 0, Σw = 1) solved exactly by
  enumerating active sets: for K <= 6 this is fast and has no tuning knobs.
* Scientific sanity checks that fail loudly instead of producing nonsense.
"""

from __future__ import annotations

import math
import statistics
from itertools import combinations

WEIGHT_TOLERANCE = 1e-6


class ScientificSanityError(ValueError):
    """Raised when a computed quantity is physically or mathematically impossible."""


# ---------------------------------------------------------------- metrics

def metrics(pairs: list[tuple[float, float]]) -> dict[str, float | int | None]:
    """MAE, RMSE, bias (forecast − observed) and Pearson correlation; None when undefined."""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "mae": None, "rmse": None, "bias": None, "correlation": None}
    errors = [f - o for f, o in pairs]
    correlation = None
    if n >= 3:
        try:
            correlation = statistics.correlation([p[0] for p in pairs], [p[1] for p in pairs])
        except statistics.StatisticsError:
            correlation = None  # a constant series (e.g. no rain at all) has no defined correlation
    return {
        "n": n,
        "mae": sum(abs(e) for e in errors) / n,
        "rmse": math.sqrt(sum(e * e for e in errors) / n),
        "bias": sum(errors) / n,
        "correlation": correlation,
    }


def skill_score(score: float | None, reference: float | None) -> float | None:
    """1 − score / reference (positive = better than the reference). None when undefined."""
    if score is None or reference is None or reference <= 0:
        return None
    return 1.0 - score / reference


# ---------------------------------------------------------------- linear algebra

def solve_linear(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None if (near-)singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            return None
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            if factor:
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def simplex_qp(a: list[list[float]], q: list[float]) -> list[float] | None:
    """Exact minimiser of  wᵀ A w − 2 qᵀ w  subject to  w >= 0, Σw = 1  (A symmetric PSD).

    Enumerates supports S; on each, the equality-constrained optimum solves the KKT system
    [2A_S 1; 1ᵀ 0][w; μ] = [2q_S; 1]. The feasible candidate with the lowest objective wins.
    """
    k = len(q)
    best: tuple[float, list[float]] | None = None
    for size in range(1, k + 1):
        for support in combinations(range(k), size):
            s = len(support)
            kkt = [[2 * a[i][j] for j in support] + [1.0] for i in support] + [[1.0] * s + [0.0]]
            rhs = [2 * q[i] for i in support] + [1.0]
            sol = solve_linear(kkt, rhs)
            if sol is None or any(v < -1e-10 for v in sol[:s]):
                continue
            w = [0.0] * k
            for idx, i in enumerate(support):
                w[i] = max(0.0, sol[idx])
            total = sum(w)
            if total <= 0:
                continue
            w = [v / total for v in w]
            objective = sum(w[i] * a[i][j] * w[j] for i in range(k) for j in range(k)) - 2 * sum(q[i] * w[i] for i in range(k))
            if best is None or objective < best[0] - 1e-15:
                best = (objective, w)
    return best[1] if best else None


def stacking_weights(error_moment: list[list[float]], ridge: float) -> list[float] | None:
    """Constrained ridge stacking on bias-corrected forecasts.

    With Σw = 1 the blend error is wᵀe, so the mean squared error is wᵀ C w where
    C = E[e eᵀ] is the error second-moment matrix. We minimise
        wᵀ C w + λ ‖w − 1/K‖²,   λ = ridge · trace(C)/K,   w >= 0, Σw = 1,
    i.e. a regularised minimum-error combination shrunk toward equal weights.
    """
    k = len(error_moment)
    scale = sum(error_moment[i][i] for i in range(k)) / k
    lam = ridge * scale
    a = [[error_moment[i][j] + (lam if i == j else 0.0) for j in range(k)] for i in range(k)]
    q = [lam / k] * k
    return simplex_qp(a, q)


# ---------------------------------------------------------------- sanity checks

def check_weights(weights: dict[str, float] | list[float], context: str = "weights") -> None:
    values = list(weights.values()) if isinstance(weights, dict) else list(weights)
    if not values:
        raise ScientificSanityError(f"{context}: empty weight vector")
    for v in values:
        if v is None or not math.isfinite(v):
            raise ScientificSanityError(f"{context}: non-finite weight {v}")
        if v < -WEIGHT_TOLERANCE:
            raise ScientificSanityError(f"{context}: negative weight {v}")
    if abs(sum(values) - 1.0) > 1e-4:
        raise ScientificSanityError(f"{context}: weights sum to {sum(values):.6f}, not 1")


# Physically plausible hourly ranges in TrustCast units. Values outside are rejected (set to missing).
PLAUSIBLE = {
    "temperature": (-90.0, 60.0),      # °C
    "precipitation": (0.0, 400.0),     # mm per hour
    "wind_speed": (0.0, 400.0),        # km/h
    "humidity": (0.0, 100.0),          # %
}


def plausible(variable: str, value: float | None) -> bool:
    if value is None or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return False
    low, high = PLAUSIBLE[variable]
    return low <= value <= high


def quantile(values: list[float], q: float) -> float | None:
    """Linear-interpolation quantile (same convention as statistics.quantiles 'inclusive')."""
    if not values:
        return None
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    pos = q * (len(data) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)
