"""Skill engine: walk-forward validation, bias correction, constrained stacking, regimes, events,
rate limiting and cache fallback. All data here are TEST FIXTURES built in the test (no network)."""

import json
import math
import random
from datetime import date, datetime, timedelta

import httpx
import pytest

from app.services.skill import dataset as ds
from app.services.skill.regime import classify_day, season_of
from app.services.skill.stats import (
    ScientificSanityError, check_weights, metrics, simplex_qp, skill_score, stacking_weights,
)
from app.services.skill.walkforward import (
    ERA5_LAG_DAYS, MIN_EVENT_COUNT, TRAIN_DAYS, Dataset, WalkForward, event_verification, summarise,
)

MODELS = ["A", "B", "C", "D"]
START = date(2025, 3, 1)


def fixture_dataset(days=60, biases=(2.0, -1.0, 0.5, 0.0), noise=(0.3, 0.6, 0.4, 1.2), seed=7, variable="temperature", drop=None):
    """TEST FIXTURE: synthetic truth with per-model constant bias and independent noise."""
    rng = random.Random(seed)
    obs, fc = {}, {lead: {m: {variable: {}} for m in MODELS} for lead in (1, 2)}
    for d in range(days):
        for h in range(24):
            t = datetime.combine(START + timedelta(days=d), datetime.min.time()) + timedelta(hours=h)
            truth = 25 + 5 * math.sin(2 * math.pi * h / 24) + 0.05 * d if variable != "precipitation" else max(0.0, rng.gauss(0.5, 1.0))
            obs[t] = truth
            for lead in (1, 2):
                for k, m in enumerate(MODELS):
                    if drop and drop(m, d, h):
                        continue
                    value = truth + biases[k] + rng.gauss(0, noise[k]) if variable != "precipitation" else truth * (1 + biases[k] * 0.1)
                    fc[lead][m][variable][t] = max(0.0, value) if variable == "precipitation" else value
    return Dataset(models=MODELS, observed={variable: obs}, forecast=fc)


# ---------------------------------------------------------------- A/B leakage + rolling origin

def test_first_evaluation_day_respects_training_window_and_gap():
    wf = WalkForward(fixture_dataset(), "temperature", 1)
    result = wf.run()
    first = result["days"][0]["day"]
    assert first == START + timedelta(days=1 + ERA5_LAG_DAYS + TRAIN_DAYS - 1)
    days = [d["day"] for d in result["days"]]
    assert days == sorted(days) and len(days) == len(set(days))


def test_no_future_leakage_changing_later_observations_does_not_change_a_forecast():
    base = fixture_dataset()
    target = START + timedelta(days=45)
    gap = 1 + ERA5_LAG_DAYS
    before = {d["day"]: d for d in WalkForward(base, "temperature", 1).run()["days"]}[target]
    # Corrupt every observation from the cut-off onward (including the target day itself).
    cutoff = datetime.combine(target - timedelta(days=gap - 1), datetime.min.time())
    for t in list(base.observed["temperature"]):
        if t >= cutoff:
            base.observed["temperature"][t] += 50.0
    after = {d["day"]: d for d in WalkForward(base, "temperature", 1).run()["days"]}[target]
    for (_, _, p1), (_, _, p2) in zip(before["rows"], after["rows"]):
        for method in ("equal", "best_single", "trust_v1", "bc_equal", "bc_stack", "bc_regime", "bc_season", "trustcast"):
            assert p1[method] == pytest.approx(p2[method]), method


def test_live_fit_trains_only_before_issue_cutoff():
    data = fixture_dataset(days=50)
    wf = WalkForward(data, "temperature", 2)
    target = START + timedelta(days=70)  # beyond the data: uses the latest day <= target − gap
    live = wf.run(extra_targets=[(target, "NORMAL")])["live"][(target, "NORMAL")]
    assert live["status"] == "ok"
    assert date.fromisoformat(live["training_end"]) <= target - timedelta(days=2 + ERA5_LAG_DAYS)
    check_weights(live["weights"])


# ---------------------------------------------------------------- C bias correction

def test_bias_correction_removes_constant_model_bias():
    data = fixture_dataset(biases=(3.0, 3.0, 3.0, 3.0), noise=(0.2, 0.2, 0.2, 0.2))
    report = summarise(WalkForward(data, "temperature", 1).run(), MODELS, "temperature")
    assert report["metrics"]["equal"]["bias"] == pytest.approx(3.0, abs=0.1)
    assert abs(report["metrics"]["bc_equal"]["bias"]) < 0.1
    assert report["bias_correction_gain"] > 0.5


def test_precipitation_uses_bounded_multiplicative_correction():
    wf = WalkForward(fixture_dataset(variable="precipitation"), "precipitation", 1)
    assert wf.bias_kind == "multiplicative"
    bias = wf._bias(wf._window(0, 20))
    assert all(0.5 <= r <= 2.0 for r in bias.ratio)
    assert bias.apply(0, 3, 1.0, clip_zero=True) >= 0


# ---------------------------------------------------------------- D/E weights

@pytest.mark.parametrize("seed", range(20))
def test_stacking_weights_are_non_negative_and_sum_to_one(seed):
    rng = random.Random(seed)
    k = 4
    errors = [[rng.gauss(0, 1 + i) for i in range(k)] for _ in range(50)]
    c = [[sum(e[i] * e[j] for e in errors) / 50 for j in range(k)] for i in range(k)]
    for ridge in (0.0, 0.01, 1.0, 100.0):
        w = stacking_weights(c, ridge)
        check_weights(w)
        assert all(x >= 0 for x in w)


def test_large_ridge_shrinks_to_equal_and_small_ridge_prefers_accurate_model():
    c = [[1.0, 0, 0, 0], [0, 4.0, 0, 0], [0, 0, 9.0, 0], [0, 0, 0, 16.0]]
    assert stacking_weights(c, 1e6) == pytest.approx([0.25] * 4, abs=1e-3)
    w = stacking_weights(c, 0.0)
    assert w[0] > w[1] > w[2] > w[3]


def test_simplex_qp_respects_constraints_when_unconstrained_optimum_is_negative():
    w = simplex_qp([[1.0, 0.99], [0.99, 1.0]], [1.0, -1.0])
    assert w is not None and min(w) >= 0 and sum(w) == pytest.approx(1)


@pytest.mark.parametrize("bad", [[0.5, 0.6], [1.2, -0.2], [float("nan"), 1.0], []])
def test_check_weights_rejects_impossible_weights(bad):
    with pytest.raises(ScientificSanityError):
        check_weights(bad)


# ---------------------------------------------------------------- F/G missing data

def test_missing_model_hours_are_renormalised_not_zero_filled():
    data = fixture_dataset(drop=lambda m, d, h: m == "D" and h % 2 == 0)
    result = WalkForward(data, "temperature", 1).run()
    hour0 = result["days"][-1]["rows"][0][2]
    assert hour0["model:D"] is None and hour0["trustcast"] is not None
    assert abs(hour0["trustcast"] - result["days"][-1]["rows"][0][1]) < 3  # not dragged toward 0


def test_insufficient_history_falls_back_and_says_so():
    data = fixture_dataset(days=40, drop=lambda m, d, h: h % 6 != 0)  # 4 complete hours/day: 84 < 120 needed
    result = WalkForward(data, "temperature", 1).run()
    levels = {d["levels"]["bc_stack"] for d in result["days"]}
    assert levels == {"fallback: previous TrustCast weights"}


def test_too_short_history_has_no_evaluation_days_and_no_live_fit():
    data = fixture_dataset(days=12)
    wf = WalkForward(data, "temperature", 1)
    result = wf.run(extra_targets=[(START + timedelta(days=13), "NORMAL")])
    assert result["days"] == []
    assert result["live"][(START + timedelta(days=13), "NORMAL")]["status"] == "unavailable"


# ---------------------------------------------------------------- H/I regime + season

def test_regime_without_history_falls_back_to_location_weights():
    wf = WalkForward(fixture_dataset(), "temperature", 1)
    target = START + timedelta(days=65)
    live = wf.run(extra_targets=[(target, "HEATWAVE")])["live"][(target, "HEATWAVE")]
    assert live["status"] == "ok"
    i = len(wf.days) - 1
    wf.regimes[i] = "HEATWAVE"  # target day forecast as a heatwave; the fixture history has none
    fits = wf._fits(i, 0.5, {}, {})
    assert fits["bc_regime"].level.startswith("location (only 0 h of heatwave")
    assert fits["bc_regime"].weights == fits["bc_stack"].weights


def test_season_without_enough_history_falls_back():
    wf = WalkForward(fixture_dataset(), "temperature", 1)
    fits = wf._fits(len(wf.days) - 1, 0.5, {}, {})
    assert fits["bc_season"].level.startswith("location (only")


def test_rule_based_regimes_and_imd_seasons():
    hot = [30 + h for h in range(24)]
    assert classify_day(date(2026, 5, 1), hot, [0] * 24, [10] * 24, [30] * 24) == "HEATWAVE"
    assert classify_day(date(2026, 7, 1), [28] * 24, [1.0] * 24, [10] * 24, [90] * 24) == "ACTIVE_MONSOON"
    assert classify_day(date(2026, 7, 1), [28] * 24, [0] * 24, [10] * 24, [70] * 24) == "MONSOON_BREAK"
    assert classify_day(date(2026, 4, 1), [28] * 24, [1.0] * 24, [10] * 24, [60] * 24) == "CONVECTIVE"
    assert classify_day(date(2026, 4, 1), [28] * 24, [0] * 24, [45] * 24, [60] * 24) == "STRONG_WIND"
    assert classify_day(date(2026, 1, 5), [10] * 24, [0] * 24, [5] * 24, [97] * 24) == "FOG_PRONE"
    assert classify_day(date(2026, 4, 1), [28] * 10, [0] * 10, [5] * 10, [60] * 10) == "UNKNOWN"
    assert [season_of(date(2026, m, 1)) for m in (1, 4, 7, 11)] == ["WINTER", "PRE_MONSOON", "MONSOON", "POST_MONSOON"]


# ---------------------------------------------------------------- L baseline skill

def test_skill_scores_against_baselines():
    assert skill_score(0.5, 1.0) == pytest.approx(0.5)
    assert skill_score(1.2, 1.0) == pytest.approx(-0.2)  # worse than baseline stays negative
    assert skill_score(1.0, 0.0) is None and skill_score(None, 1.0) is None
    report = summarise(WalkForward(fixture_dataset(), "temperature", 1).run(), MODELS, "temperature")
    m = report["metrics"]
    assert m["equal"]["skill_vs_equal"] == pytest.approx(0)
    assert m["trustcast"]["skill_vs_equal"] == pytest.approx(1 - m["trustcast"]["rmse"] / m["equal"]["rmse"])
    ci = report["skill_intervals_90"]["equal"]
    assert ci["low"] <= m["trustcast"]["skill_vs_equal"] <= ci["high"]


def test_metrics_handle_empty_and_constant_series():
    assert metrics([])["rmse"] is None
    assert metrics([(0.0, 0.0)] * 5)["correlation"] is None


# ---------------------------------------------------------------- M events

def _event_days(obs_totals, fc_totals):
    """TEST FIXTURE: one evaluation day per total, spread evenly over the 24 hours of an IMD day."""
    days = []
    for i, (o, f) in enumerate(zip(obs_totals, fc_totals)):
        start = datetime(2025, 7, 1, 3) + timedelta(days=i)
        rows_by_day = {}
        for h in range(24):
            t = start + timedelta(hours=h)
            rows_by_day.setdefault(t.date(), []).append((t.hour, o / 24, {"trustcast": f / 24}))
        for day, rows in rows_by_day.items():
            days.append({"day": day, "rows": rows})
    merged = {}
    for d in days:
        merged.setdefault(d["day"], []).extend(d["rows"])
    return [{"day": k, "rows": v} for k, v in sorted(merged.items())]


def test_pod_far_csi_counts_and_undefined_cases():
    obs = [80] * 6 + [0] * 20
    fc = [80] * 4 + [0] * 2 + [80] * 2 + [0] * 18
    out = event_verification(_event_days(obs, fc), ["trustcast"])
    row = next(r for r in out["thresholds"] if r["threshold_mm"] == 64.5)["methods"]["trustcast"]
    assert (row["hits"], row["misses"], row["false_alarms"]) == (4, 2, 2)
    assert row["pod"] == pytest.approx(4 / 6) and row["far"] == pytest.approx(2 / 6) and row["csi"] == pytest.approx(4 / 8)
    dry = event_verification(_event_days([0] * 10, [0] * 10), ["trustcast"])
    m = dry["thresholds"][0]["methods"]["trustcast"]
    assert m["pod"] is None and m["far"] is None and m["csi"] is None  # undefined, never 0
    assert MIN_EVENT_COUNT >= 1


# ---------------------------------------------------------------- Q rate limiting

@pytest.mark.asyncio
async def test_rate_limited_client_retries_429_with_backoff(monkeypatch):
    calls = []
    sleeps = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "2"})
        return httpx.Response(200, json={"ok": True})

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(ds.asyncio, "sleep", fake_sleep)
    client = ds.RateLimitedClient(concurrency=1, min_interval_s=0)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        assert await client.get_json(http, "https://example.test", {}) == {"ok": True}
    assert len(calls) == 3 and client.retries == 2 and 2.0 in sleeps


# ---------------------------------------------------------------- R cache fallback + data quality

@pytest.mark.asyncio
async def test_failed_refresh_falls_back_to_stale_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "SKILL_CACHE_DIR", str(tmp_path))
    location = {"name": "X", "latitude": 10.0, "longitude": 70.0}
    path = ds._cache_path(location)
    path.parent.mkdir(parents=True)
    cached = {"obs": {"temperature": {"2025-03-01T00": 25.0}}, "fc": {}, "quality": {}, "models": ["A"],
              "end": "2025-03-02", "fetched_on": "2000-01-01", "fetched_at": "2000-01-01T00:00:00+00:00"}
    path.write_text(json.dumps(cached))

    async def failing(*args, **kwargs):
        raise ds.DataUnavailableError("upstream down")

    monkeypatch.setattr(ds, "fetch_raw", failing)
    data, info = await ds.load_history(location, [ds.ModelSource("A", "a")])
    assert info["stale"] is True and info["cache"] == "stale"
    assert data.observed["temperature"]


@pytest.mark.asyncio
async def test_no_cache_and_failed_download_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "SKILL_CACHE_DIR", str(tmp_path))

    async def failing(*args, **kwargs):
        raise ds.DataUnavailableError("upstream down")

    monkeypatch.setattr(ds, "fetch_raw", failing)
    with pytest.raises(ds.DataUnavailableError):
        await ds.load_history({"name": "Y", "latitude": 1.0, "longitude": 2.0}, [ds.ModelSource("A", "a")])


def test_parser_rejects_implausible_values_and_duplicate_timestamps():
    quality = {}
    block = {"hourly": {"time": ["2025-03-01T00:00", "2025-03-01T00:00", "2025-03-01T01:00", "2025-03-01T02:00"],
                        "temperature_2m": [25.0, 26.0, 99.0, None]}}
    out = ds._parse(block, {"temperature_2m": "temperature"}, quality)
    assert out == {"temperature": {"2025-03-01T00": 25.0}}
    assert quality == {"duplicate_timestamps": 1, "rejected_implausible": 1, "missing_values": 1}
