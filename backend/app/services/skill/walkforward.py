"""Rolling-origin (walk-forward) validation of TrustCast and its baselines.

For every target day d (UTC) at lead L the training window ends on day d − GAP with
GAP = L + ERA5_LAG_DAYS: a forecast for day d is issued L days earlier, and at that moment the ERA5
reference is only published up to ~5 days back. Nothing from day d − GAP + 1 onward (and nothing from
the target day) is used, so the evaluation is strictly out-of-sample.

Methods evaluated on every target day (all trained only on data before the cut-off):
    model:<name>   each raw model
    equal          equal-weight mean of the raw models                       (baseline A)
    best_single    raw model with the lowest training RMSE                   (baseline B)
    trust_v1       previous TrustCast weights: 0.7/(RMSE21+0.05) + 0.3/(RMSE7+0.05), raw forecasts
    bc_equal       equal-weight mean of bias-corrected forecasts
    bc_stack       bias correction + constrained ridge stacking on the recent window
    bc_regime      bc_stack weights trained on past days of the same rule-based regime
    bc_season      bc_stack weights trained on all past days of the same IMD season
    trustcast      the variant among {trust_v1, bc_equal, bc_stack, bc_regime, bc_season} with the
                   lowest out-of-sample RMSE over the previous SELECT_WINDOW days whose verification was
                   already available at issue time (nested selection, so also leakage-free)

Bias correction: additive per model and hour-of-day for temperature and wind (overall mean when an
hour has fewer than MIN_HOD_SAMPLES), multiplicative (ratio of totals) for precipitation, which is
zero-inflated and cannot be shifted additively.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.services.skill.regime import REGIME_LABEL, SEASON_LABEL, classify_day, season_of
from app.services.skill.stats import check_weights, metrics, quantile, skill_score, stacking_weights

ERA5_LAG_DAYS = 5
TRAIN_DAYS = 21
RECENT_DAYS = 7
MIN_STACK_HOURS = 120          # complete-case hours needed before stacking is trusted
MIN_HOD_SAMPLES = 10           # per hour-of-day samples before an hour-specific bias is used
MIN_REGIME_HOURS = 72          # same-regime hours needed for regime-specific weights
MIN_SEASON_HOURS = 168
MIN_RATIO_TOTAL_MM = 5.0       # precipitation totals needed before a multiplicative correction
RATIO_BOUNDS = (0.5, 2.0)
SELECT_WINDOW = 30
MIN_SELECT_DAYS = 10
RIDGE_GRID = (0.01, 0.1, 0.5, 2.0, 10.0)
DEFAULT_RIDGE = 0.5
RESELECT_EVERY = 7
TRUST_EPS = 0.05
CANDIDATES = ("trust_v1", "bc_equal", "bc_stack", "bc_regime", "bc_season")
DEFAULT_VARIANT = "bc_stack"
BASELINES = ("equal", "best_single")
METHODS = ("equal", "best_single", "trust_v1", "bc_equal", "bc_stack", "bc_regime", "bc_season", "trustcast")
NEUTRAL_REGIMES = {"NORMAL", "UNKNOWN"}
BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 26081  # fixed so the confidence interval is reproducible
EVENT_THRESHOLDS_MM = (2.5, 15.6, 64.5)
MIN_EVENT_COUNT = 5
EVENT_DAY_OFFSET_HOURS = 3  # IMD rainfall day: 03 UTC (08:30 IST) to 03 UTC


@dataclass
class Dataset:
    """Hourly real data for one location. Units are TrustCast units; implausible values already removed."""

    models: list[str]
    observed: dict[str, dict[datetime, float]]                      # variable -> time -> ERA5 value
    forecast: dict[int, dict[str, dict[str, dict[datetime, float]]]]  # lead -> model -> variable -> time -> value
    sources: dict[str, str] = field(default_factory=dict)
    quality: dict[str, int] = field(default_factory=dict)


@dataclass
class BiasParams:
    kind: str                                  # "additive" or "multiplicative"
    hod: list[list[float]] | None = None       # 24 x K additive corrections
    ratio: list[float] | None = None           # K multiplicative factors
    mode: str = ""

    def apply(self, k: int, hour: int, value: float, clip_zero: bool) -> float:
        if self.kind == "multiplicative":
            out = value * self.ratio[k]
        else:
            out = value - self.hod[hour][k]
        return max(0.0, out) if clip_zero else out

    def summary(self, models: list[str]) -> dict[str, float]:
        if self.kind == "multiplicative":
            return {m: self.ratio[k] for k, m in enumerate(models)}
        return {m: sum(self.hod[h][k] for h in range(24)) / 24 for k, m in enumerate(models)}


@dataclass
class Fit:
    weights: list[float]
    bias: BiasParams
    level: str
    samples: int
    note: str = ""


class _Layout:
    """Index layout of the sufficient-statistics vector for K models."""

    def __init__(self, k: int) -> None:
        self.k = k
        self.N, self.SX, self.SY = 0, 1, 1 + k
        self.SXX = 2 + k
        self.SXY = 2 + k + k * k
        self.SYY = 2 + 2 * k + k * k
        self.size = 3 + 2 * k + k * k

    def add_hour(self, vec: list[float], y: float, xs: list[float]) -> None:
        k = self.k
        vec[self.N] += 1
        vec[self.SY] += y
        vec[self.SYY] += y * y
        for i in range(k):
            vec[self.SX + i] += xs[i]
            vec[self.SXY + i] += xs[i] * y
            row = self.SXX + i * k
            for j in range(k):
                vec[row + j] += xs[i] * xs[j]


def _add(a: list[float], b: list[float], sign: float = 1.0) -> None:
    for i, v in enumerate(b):
        a[i] += sign * v


class WalkForward:
    """Builds day/hour statistics once, then runs walk-forward evaluation or a live fit."""

    def __init__(self, data: Dataset, variable: str, lead_day: int) -> None:
        self.data = data
        self.variable = variable
        self.lead = lead_day
        self.models = list(data.models)
        self.k = len(self.models)
        self.lay = _Layout(self.k)
        self.gap = lead_day + ERA5_LAG_DAYS
        self.bias_kind = "multiplicative" if variable == "precipitation" else "additive"
        self.clip_zero = variable in ("precipitation", "wind_speed")
        self._prepare()

    # ------------------------------------------------------------ preparation
    def _prepare(self) -> None:
        obs = self.data.observed.get(self.variable, {})
        fc_lead = self.data.forecast.get(self.lead, {})
        fc = [fc_lead.get(m, {}).get(self.variable, {}) for m in self.models]
        all_times = set(obs)
        for series in fc:
            all_times.update(series)
        if not all_times:
            self.days: list[date] = []
            return
        first, last = min(all_times).date(), max(obs).date() if obs else max(all_times).date()
        self.days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        self.index = {d: i for i, d in enumerate(self.days)}
        size = self.lay.size
        self.hours: list[list[tuple[int, float | None, list[float | None]]]] = []
        self.hod_stats: list[list[list[float]]] = []
        self.model_err: list[list[tuple[int, float, float]]] = []  # per day per model: (n, Σe, Σe²)
        self.regimes: list[str] = []
        self.complete_hours: list[int] = []
        fields = {v: [fc_lead.get(m, {}).get(v, {}) for m in self.models] for v in ("temperature", "precipitation", "wind_speed", "humidity")}
        for day in self.days:
            day_hours = []
            stats = [[0.0] * size for _ in range(24)]
            errs = [[0, 0.0, 0.0] for _ in range(self.k)]
            complete = 0
            for h in range(24):
                t = datetime(day.year, day.month, day.day, h)
                y = obs.get(t)
                xs = [series.get(t) for series in fc]
                day_hours.append((h, y, xs))
                if y is None:
                    continue
                for i, x in enumerate(xs):
                    if x is not None:
                        e = x - y
                        errs[i][0] += 1
                        errs[i][1] += e
                        errs[i][2] += e * e
                if all(x is not None for x in xs):
                    self.lay.add_hour(stats[h], y, xs)  # type: ignore[arg-type]
                    complete += 1
            self.hours.append(day_hours)
            self.hod_stats.append(stats)
            self.model_err.append([tuple(e) for e in errs])  # type: ignore[misc]
            self.complete_hours.append(complete)
            self.regimes.append(self._classify(day, fields))
        # prefix sums over days, per hour-of-day
        self.prefix = [[[0.0] * size for _ in range(24)]]
        for stats in self.hod_stats:
            row = [p[:] for p in self.prefix[-1]]
            for h in range(24):
                _add(row[h], stats[h])
            self.prefix.append(row)
        self.err_prefix = [[(0, 0.0, 0.0)] * self.k]
        for errs in self.model_err:
            prev = self.err_prefix[-1]
            self.err_prefix.append([(prev[i][0] + errs[i][0], prev[i][1] + errs[i][1], prev[i][2] + errs[i][2]) for i in range(self.k)])

    def _classify(self, day: date, fields: dict[str, list[dict[datetime, float]]]) -> str:
        per_var: dict[str, list[float]] = {v: [] for v in fields}
        for h in range(24):
            t = datetime(day.year, day.month, day.day, h)
            for v, series_list in fields.items():
                vals = [s[t] for s in series_list if t in s]
                if vals:
                    per_var[v].append(sum(vals) / len(vals))
        return classify_day(day, per_var["temperature"], per_var["precipitation"], per_var["wind_speed"], per_var["humidity"])

    # ------------------------------------------------------------ aggregation helpers
    def _window(self, a: int, b: int) -> list[list[float]]:
        """Per-hour-of-day statistics summed over day indices a..b (inclusive)."""
        if b < a:
            return [[0.0] * self.lay.size for _ in range(24)]
        hi, lo = self.prefix[b + 1], self.prefix[a]
        return [[hi[h][i] - lo[h][i] for i in range(self.lay.size)] for h in range(24)]

    def _err_window(self, a: int, b: int) -> list[tuple[int, float, float]]:
        hi, lo = self.err_prefix[b + 1], self.err_prefix[a]
        return [(hi[i][0] - lo[i][0], hi[i][1] - lo[i][1], hi[i][2] - lo[i][2]) for i in range(self.k)]

    def _total(self, agg: list[list[float]]) -> list[float]:
        tot = [0.0] * self.lay.size
        for h in range(24):
            _add(tot, agg[h])
        return tot

    # ------------------------------------------------------------ bias + moments
    def _bias(self, agg: list[list[float]]) -> BiasParams:
        L, k = self.lay, self.k
        tot = self._total(agg)
        n = tot[L.N]
        if self.bias_kind == "multiplicative":
            ratio, notes = [], []
            for i in range(k):
                fx, oy = tot[L.SX + i], tot[L.SY]
                if fx >= MIN_RATIO_TOTAL_MM and oy >= MIN_RATIO_TOTAL_MM:
                    ratio.append(min(RATIO_BOUNDS[1], max(RATIO_BOUNDS[0], oy / fx)))
                else:
                    ratio.append(1.0)
                    notes.append(self.models[i])
            mode = "ratio of totals" + (f" (no correction for {', '.join(notes)}: too little rain)" if notes else "")
            return BiasParams("multiplicative", ratio=ratio, mode=mode)
        overall = [((tot[L.SX + i] - tot[L.SY]) / n) if n else 0.0 for i in range(k)]
        hod, hourly_used = [], 0
        for h in range(24):
            nh = agg[h][L.N]
            if nh >= MIN_HOD_SAMPLES:
                hod.append([(agg[h][L.SX + i] - agg[h][L.SY]) / nh for i in range(k)])
                hourly_used += 1
            else:
                hod.append(overall)
        mode = "hour-of-day" if hourly_used == 24 else ("partly hour-of-day" if hourly_used else "overall mean")
        return BiasParams("additive", hod=hod, mode=mode)

    def _moment(self, agg: list[list[float]], bias: BiasParams) -> tuple[list[list[float]], int]:
        """Error second-moment matrix C (K x K) of bias-corrected forecasts, and its sample count."""
        L, k = self.lay, self.k
        c = [[0.0] * k for _ in range(k)]
        if bias.kind == "multiplicative":
            tot = self._total(agg)
            n = int(tot[L.N])
            if not n:
                return c, 0
            r = bias.ratio
            for i in range(k):
                for j in range(k):
                    c[i][j] = (r[i] * r[j] * tot[L.SXX + i * k + j] - r[i] * tot[L.SXY + i] - r[j] * tot[L.SXY + j] + tot[L.SYY]) / n
            return c, n
        n_total = 0
        for h in range(24):
            s = agg[h]
            nh = s[L.N]
            if not nh:
                continue
            n_total += int(nh)
            b = bias.hod[h]
            for i in range(k):
                ei = s[L.SX + i] - s[L.SY]
                for j in range(k):
                    ej = s[L.SX + j] - s[L.SY]
                    raw = s[L.SXX + i * k + j] - s[L.SXY + i] - s[L.SXY + j] + s[L.SYY]
                    c[i][j] += raw - b[j] * ei - b[i] * ej + nh * b[i] * b[j]
        if not n_total:
            return c, 0
        return [[v / n_total for v in row] for row in c], n_total

    def _stack(self, agg: list[list[float]], bias: BiasParams, ridge: float) -> tuple[list[float] | None, int]:
        moment, n = self._moment(agg, bias)
        if n < MIN_STACK_HOURS:
            return None, n
        w = stacking_weights(moment, ridge)
        if w is None:
            return None, n
        check_weights(w, "stacking")
        return w, n

    def _select_ridge(self, a: int, b: int) -> float:
        days = b - a + 1
        if days < 9:
            return DEFAULT_RIDGE
        split = b - days // 3
        fit, val = self._window(a, split), self._window(split + 1, b)
        bias = self._bias(fit)
        val_moment, n_val = self._moment(val, bias)
        if not n_val:
            return DEFAULT_RIDGE
        best = (math.inf, DEFAULT_RIDGE)
        for ridge in RIDGE_GRID:
            w, _ = self._stack(fit, bias, ridge)
            if w is None:
                continue
            mse = sum(w[i] * val_moment[i][j] * w[j] for i in range(self.k) for j in range(self.k))
            if mse < best[0] - 1e-12 or (abs(mse - best[0]) <= 1e-12 and ridge > best[1]):
                best = (mse, ridge)
        return best[1]

    # ------------------------------------------------------------ baseline weights
    def _rmse_by_model(self, a: int, b: int) -> list[float | None]:
        out = []
        for n, _, se2 in self._err_window(a, b):
            out.append(math.sqrt(se2 / n) if n >= 24 else None)
        return out

    def _trust_v1(self, a: int, b: int) -> list[float] | None:
        hist = self._rmse_by_model(a, b)
        recent = self._rmse_by_model(max(a, b - RECENT_DAYS + 1), b)
        scores = []
        for h, r in zip(hist, recent):
            if h is None:
                scores.append(0.0)
            elif r is None:
                scores.append(1 / (h + TRUST_EPS))
            else:
                scores.append(0.7 / (h + TRUST_EPS) + 0.3 / (r + TRUST_EPS))
        total = sum(scores)
        return [s / total for s in scores] if total > 0 else None

    # ------------------------------------------------------------ fitting one target day
    def _fits(self, i: int, ridge: float, regime_agg: dict[str, list[list[float]]], season_agg: dict[str, list[list[float]]], train_end: int | None = None) -> dict[str, Fit | None]:
        """All training fits for target day index i (training days <= i − gap, or an earlier train_end)."""
        b = i - self.gap if train_end is None else min(train_end, i - self.gap)
        a = b - TRAIN_DAYS + 1
        recent = self._window(max(0, a), b)
        bias = self._bias(recent)
        identity = BiasParams("multiplicative", ratio=[1.0] * self.k, mode="none") if self.bias_kind == "multiplicative" \
            else BiasParams("additive", hod=[[0.0] * self.k for _ in range(24)], mode="none")
        fits: dict[str, Fit | None] = {}
        equal = [1.0 / self.k] * self.k
        fits["equal"] = Fit(equal, identity, "equal weights", int(self._total(recent)[self.lay.N]))
        rmse = self._rmse_by_model(max(0, a), b)
        ranked = [(r, m) for m, r in enumerate(rmse) if r is not None]
        if ranked:
            best = min(ranked)[1]
            fits["best_single"] = Fit([1.0 if m == best else 0.0 for m in range(self.k)], identity, f"best single ({self.models[best]})", 0)
        else:
            fits["best_single"] = None
        tv1 = self._trust_v1(max(0, a), b)
        fits["trust_v1"] = Fit(tv1, identity, "previous TrustCast weights", 0) if tv1 else None
        fits["bc_equal"] = Fit(equal, bias, "bias-corrected equal weights", 0)
        w, n = self._stack(recent, bias, ridge)
        loc = Fit(w, bias, "location", n) if w else None
        fits["bc_stack"] = loc
        # regime: past days with the same rule-based regime as the target day (forecast-derived)
        regime = self.regimes[i]
        if regime in NEUTRAL_REGIMES:
            fits["bc_regime"] = Fit(loc.weights, bias, "location (neutral regime)", loc.samples) if loc else None
        else:
            rw, rn = self._stack(regime_agg.get(regime) or self._window(0, -1), bias, ridge)
            if rw:
                fits["bc_regime"] = Fit(rw, bias, f"regime+location ({REGIME_LABEL[regime]})", rn)
            else:
                fits["bc_regime"] = Fit(loc.weights, bias, f"location (only {rn} h of {REGIME_LABEL[regime].lower()} history)", loc.samples) if loc else None
        season = season_of(self.days[i])
        sw, sn = self._stack(season_agg.get(season) or self._window(0, -1), bias, ridge)
        if sw and sn >= MIN_SEASON_HOURS:
            fits["bc_season"] = Fit(sw, bias, f"season+location ({SEASON_LABEL[season]})", sn)
        else:
            fits["bc_season"] = Fit(loc.weights, bias, f"location (only {sn} h of same-season history)", loc.samples) if loc else None
        if loc is None:
            note = f"Insufficient data for adaptive stacking ({n} complete hours < {MIN_STACK_HOURS}); using previous TrustCast weights"
            fallback = fits["trust_v1"]
            for key in ("bc_stack", "bc_regime", "bc_season"):
                fits[key] = Fit(fallback.weights, identity, "fallback: previous TrustCast weights", 0, note) if fallback else None
        return fits

    def _predict(self, fit: Fit | None, hour: int, xs: list[float | None]) -> float | None:
        if fit is None:
            return None
        num = den = 0.0
        for k, x in enumerate(xs):
            w = fit.weights[k]
            if x is None or w <= 0:
                continue
            num += w * fit.bias.apply(k, hour, x, self.clip_zero)
            den += w
        return num / den if den > 0 else None

    # ------------------------------------------------------------ main loop
    def run(self, eval_from: date | None = None, extra_targets: list[tuple[date, str]] | None = None) -> dict:
        """Walk forward over every possible target day (or from `eval_from`).

        `extra_targets` = [(future_day, regime)] are fitted after the loop with the same rules,
        for live inference; they are never evaluated.
        """
        out = {"days": [], "variant_usage": {}, "live": {}}
        if not self.days:
            return out
        first_eval = self.gap + TRAIN_DAYS - 1
        start = max(first_eval, self.index.get(eval_from, 0) if eval_from else 0)
        regime_agg: dict[str, list[list[float]]] = {}
        season_agg: dict[str, list[list[float]]] = {}
        added = -1
        ridge, ridge_at = DEFAULT_RIDGE, -RESELECT_EVERY
        daily_sse: dict[str, list[tuple[int, float, int]]] = {c: [] for c in CANDIDATES}  # (day index, Σe², n)

        def absorb_until(limit: int) -> None:
            nonlocal added
            while added < limit:
                added += 1
                for key, agg in ((self.regimes[added], regime_agg), (season_of(self.days[added]), season_agg)):
                    bucket = agg.setdefault(key, [[0.0] * self.lay.size for _ in range(24)])
                    for h in range(24):
                        _add(bucket[h], self.hod_stats[added][h])

        def select(i_day: int, limit: int | None = None) -> str:
            limit = i_day - self.gap if limit is None else limit
            best, best_rmse = DEFAULT_VARIANT, math.inf
            for c in CANDIDATES:
                rows = [(s, n) for d, s, n in daily_sse[c] if limit - SELECT_WINDOW < d <= limit]
                if len(rows) < MIN_SELECT_DAYS:
                    return DEFAULT_VARIANT
                n = sum(r[1] for r in rows)
                rmse = math.sqrt(sum(r[0] for r in rows) / n) if n else math.inf
                if rmse < best_rmse:
                    best, best_rmse = c, rmse
            return best

        # Days earlier than this only feed the running regime/season pools (no fit needed).
        needed_from = start - SELECT_WINDOW - self.gap - 1
        for i in range(first_eval, len(self.days)):
            absorb_until(i - self.gap)
            if i < needed_from:
                continue
            if i - ridge_at >= RESELECT_EVERY:
                ridge, ridge_at = self._select_ridge(max(0, i - self.gap - TRAIN_DAYS + 1), i - self.gap), i
            fits = self._fits(i, ridge, regime_agg, season_agg)
            chosen = select(i)
            fits["trustcast"] = fits[chosen]
            rows = []
            sse = {c: [0.0, 0] for c in CANDIDATES}
            for hour, y, xs in self.hours[i]:
                preds = {f"model:{m}": xs[k] for k, m in enumerate(self.models)}
                for method in METHODS:
                    preds[method] = self._predict(fits.get(method), hour, xs)
                if y is not None:
                    for c in CANDIDATES:
                        p = preds[c]
                        if p is not None:
                            sse[c][0] += (p - y) ** 2
                            sse[c][1] += 1
                rows.append((hour, y, preds))
            for c in CANDIDATES:
                if sse[c][1]:
                    daily_sse[c].append((i, sse[c][0], sse[c][1]))
            if i < start:
                continue
            out["days"].append({
                "day": self.days[i], "regime": self.regimes[i], "season": season_of(self.days[i]),
                "variant": chosen, "ridge": ridge, "rows": rows,
                "levels": {m: (fits[m].level if fits.get(m) else None) for m in METHODS},
            })
            out["variant_usage"][chosen] = out["variant_usage"].get(chosen, 0) + 1

        # live fits for future target days (issue time = now)
        for target, regime in extra_targets or []:
            out["live"][(target, regime)] = self._live_fit(target, regime, regime_agg, season_agg, ridge, select, absorb_until)
        return out

    def regime_moments(self, train_end: date) -> dict[str, tuple[list[list[float]], int]]:
        """Bias-corrected error moments per regime (and 'ALL') over days <= train_end, for regional pooling."""
        if not self.days or train_end < self.days[0]:
            return {}
        b = min((train_end - self.days[0]).days, len(self.days) - 1)
        bias = self._bias(self._window(max(0, b - TRAIN_DAYS + 1), b))
        groups: dict[str, list[list[float]]] = {}
        for i in range(b + 1):
            for key in (self.regimes[i], "ALL"):
                bucket = groups.setdefault(key, [[0.0] * self.lay.size for _ in range(24)])
                for h in range(24):
                    _add(bucket[h], self.hod_stats[i][h])
        return {key: self._moment(agg, bias) for key, agg in groups.items()}

    def _live_fit(self, target: date, regime: str, regime_agg, season_agg, ridge, select, absorb_until) -> dict:
        # Training may use data up to the issue-time cut-off, i.e. the latest verified day <= target − gap.
        cutoff = target - timedelta(days=self.gap)
        b = min((cutoff - self.days[0]).days, len(self.days) - 1)
        if b < TRAIN_DAYS - 1:
            return {"status": "unavailable", "reason": "Not enough verified days before the issue-time cut-off"}
        last_train = self.days[b]
        absorb_until(b)
        # Target index relative to the first day; temporarily extend the calendar to reach it.
        i = (target - self.days[0]).days
        extra = 0
        padded = i >= len(self.days)
        if padded:
            extra = i - len(self.days) + 1
            self.days.extend(self.days[-1] + timedelta(days=n + 1) for n in range(extra))
            self.regimes.extend(["UNKNOWN"] * extra)
        saved = self.regimes[i]
        self.regimes[i] = regime
        try:
            fits = self._fits(i, ridge, regime_agg, season_agg, train_end=b)
            chosen = select(i, limit=b)
        finally:
            self.regimes[i] = saved
            if padded:
                del self.days[len(self.days) - extra:]
                del self.regimes[len(self.regimes) - extra:]
        fit = fits[chosen]
        if fit is None:
            return {"status": "unavailable", "reason": "No usable training data"}
        check_weights(fit.weights, "live weights")
        return {
            "status": "ok", "variant": chosen, "level": fit.level, "note": fit.note,
            "weights": dict(zip(self.models, fit.weights)), "bias": fit.bias, "samples": fit.samples,
            "training_end": last_train.isoformat(), "ridge": ridge,
        }


# ------------------------------------------------------------------ reporting

def _pairs(rows, method: str) -> list[tuple[float, float]]:
    return [(p[method], y) for _, y, p in rows if y is not None and p.get(method) is not None]


def summarise(result: dict, models: list[str], variable: str) -> dict:
    """Turn walk-forward rows into the evaluation report (common-sample metrics, skill, breakdowns)."""
    days = result["days"]
    method_keys = [f"model:{m}" for m in models] + list(METHODS)
    common = []  # (day_entry, hour, y, preds) where every method has a value
    for d in days:
        for hour, y, preds in d["rows"]:
            if y is None or any(preds.get(m) is None for m in method_keys):
                continue
            common.append((d, hour, y, preds))
    table = {}
    for m in method_keys:
        table[m] = metrics([(p[m], y) for _, _, y, p in common])
    ref = {b: table[b]["rmse"] for b in BASELINES}
    for m in method_keys:
        table[m]["skill_vs_equal"] = skill_score(table[m]["rmse"], ref["equal"])
        table[m]["skill_vs_best_single"] = skill_score(table[m]["rmse"], ref["best_single"])

    # bootstrap over days for TrustCast vs each baseline (RMSE skill), fixed seed for reproducibility
    per_day: dict[date, dict[str, list[float]]] = {}
    for d, _, y, p in common:
        bucket = per_day.setdefault(d["day"], {m: [0.0, 0] for m in ("trustcast", *BASELINES)})
        for m in bucket:
            bucket[m][0] += (p[m] - y) ** 2
            bucket[m][1] += 1
    rng = random.Random(BOOTSTRAP_SEED)
    keys = sorted(per_day)
    intervals = {}
    for base in BASELINES:
        samples = []
        if len(keys) >= 10:
            for _ in range(BOOTSTRAP_RESAMPLES):
                pick = [per_day[keys[rng.randrange(len(keys))]] for _ in keys]
                n = sum(x["trustcast"][1] for x in pick)
                tc = math.sqrt(sum(x["trustcast"][0] for x in pick) / n)
                rb = math.sqrt(sum(x[base][0] for x in pick) / n)
                if rb > 0:
                    samples.append(1 - tc / rb)
        intervals[base] = {"low": quantile(samples, 0.05), "high": quantile(samples, 0.95), "resamples": len(samples)} if samples else None

    def breakdown(key: str) -> list[dict]:
        groups: dict[str, list] = {}
        for d, _, y, p in common:
            groups.setdefault(d[key], []).append((d["day"], y, p))
        rows = []
        for g, items in sorted(groups.items()):
            entry = {"group": g, "hours": len(items), "days": len({day for day, _, _ in items})}
            for m in method_keys:
                entry[m] = metrics([(p[m], y) for _, y, p in items])["rmse"]
            entry["skill_vs_equal"] = skill_score(entry["trustcast"], entry["equal"])
            entry["skill_vs_best_single"] = skill_score(entry["trustcast"], entry["best_single"])
            rows.append(entry)
        return rows

    report = {
        "period_start": days[0]["day"].isoformat() if days else None,
        "period_end": days[-1]["day"].isoformat() if days else None,
        "evaluation_days": len(days),
        "common_hours": len(common),
        "metrics": table,
        "skill_intervals_90": intervals,
        "bias_correction_gain": skill_score(table["bc_equal"]["rmse"], table["equal"]["rmse"]),
        "adaptive_weighting_gain": skill_score(table["bc_stack"]["rmse"], table["bc_equal"]["rmse"]),
        "by_season": breakdown("season"),
        "by_regime": breakdown("regime"),
        "variant_usage": result["variant_usage"],
        "fallback_days": sum(1 for d in days if d["levels"].get("bc_stack", "").startswith("fallback")),
    }
    if variable == "precipitation":
        report["events"] = event_verification(days, method_keys)
    # out-of-sample TrustCast residuals for the prediction range (most recent 60 evaluation days)
    recent = days[-60:]
    residuals = [p["trustcast"] - y for d in recent for _, y, p in d["rows"] if y is not None and p.get("trustcast") is not None]
    report["oos_residuals"] = {
        "samples": len(residuals),
        "p10": quantile(residuals, 0.1),
        "p90": quantile(residuals, 0.9),
        "period_start": recent[0]["day"].isoformat() if recent else None,
        "period_end": recent[-1]["day"].isoformat() if recent else None,
    }
    return report


def event_verification(days: list[dict], method_keys: list[str]) -> dict:
    """24 h rainfall events on the IMD rainfall day (03 UTC to 03 UTC), per threshold and method.

    A day is used only when all 24 hourly values exist for the observation and the method.
    POD = H/(H+M) needs >= MIN_EVENT_COUNT observed events; FAR = F/(H+F) needs >= MIN_EVENT_COUNT
    forecast events; CSI = H/(H+M+F) needs >= MIN_EVENT_COUNT in its denominator. Otherwise None
    (reported as 'insufficient events'), never 0.
    """
    totals: dict[date, dict[str, list[float]]] = {}
    for d in days:
        for hour, y, preds in d["rows"]:
            t = datetime(d["day"].year, d["day"].month, d["day"].day, hour) - timedelta(hours=EVENT_DAY_OFFSET_HOURS)
            bucket = totals.setdefault(t.date(), {"obs": [0.0, 0]} | {m: [0.0, 0] for m in method_keys})
            if y is not None:
                bucket["obs"][0] += y
                bucket["obs"][1] += 1
            for m in method_keys:
                if y is not None and preds.get(m) is not None:
                    bucket[m][0] += preds[m]
                    bucket[m][1] += 1
    complete = {d: b for d, b in totals.items() if b["obs"][1] == 24}
    out = {"accumulation": "24 h, 03–03 UTC (IMD rainfall day)", "days": len(complete), "thresholds": []}
    for thr in EVENT_THRESHOLDS_MM:
        observed_events = sum(1 for b in complete.values() if b["obs"][0] >= thr)
        row = {"threshold_mm": thr, "observed_events": observed_events, "methods": {}}
        for m in method_keys:
            h = mi = f = cn = 0
            for b in complete.values():
                if b[m][1] != 24:
                    continue
                o, p = b["obs"][0] >= thr, b[m][0] >= thr
                h += o and p
                mi += o and not p
                f += p and not o
                cn += not o and not p
            row["methods"][m] = {
                "hits": h, "misses": mi, "false_alarms": f, "correct_negatives": cn,
                "pod": h / (h + mi) if h + mi >= MIN_EVENT_COUNT else None,
                "far": f / (h + f) if h + f >= MIN_EVENT_COUNT else None,
                "csi": h / (h + mi + f) if h + mi + f >= MIN_EVENT_COUNT else None,
            }
        out["thresholds"].append(row)
    return out
