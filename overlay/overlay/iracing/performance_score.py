"""
Per-driver performance score (0-100), recalculated every lap.

Score breakdown
───────────────
Pace         60 pts
  Historical pace  (0-30)  – average % behind session-best lap across past races
                              from race_history.json (0 pts = 0 % delta, i.e. always fastest)
  Session pace     (0-30)  – current best lap vs session leader this session

Racecraft    40 pts
  iR-adj position  (0-20)  – actual finish vs iRating-expected rank (neutral = 10);
                              falls back to positions-gained when iRating is unavailable
  Consistency      (0-20)  – coefficient of variation of completed lap times
                              this session (lower CV = higher score)
"""

import math
import logging

logger = logging.getLogger("iracing-timing")


def _parse_lap(s):
    """Parse 'M:SS.mmm' string or numeric to float seconds. Returns None if invalid."""
    try:
        if s is None or s in ('N/A', '-', '', '999:59.999'):
            return None
        if isinstance(s, (int, float)):
            v = float(s)
            return v if v > 0 else None
        s = str(s).strip()
        if ':' in s:
            m, rest = s.split(':', 1)
            v = float(m) * 60 + float(rest)
        else:
            v = float(s)
        return v if v > 0 else None
    except Exception:
        return None


def _stddev(values):
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((x - mean) ** 2 for x in values) / n)


def _normalized_positions_score(driver: dict, all_drivers: list) -> float:
    """
    Racecraft score (0-20) based on positions gained/lost, normalized to the
    driver's available room on the grid so pole-sitters aren't penalised.

    Ratio = gained / max_possible_gain  (or lost / max_possible_loss)
    Score = 10 + 10 * ratio  → hold position = 10, max gain = 20, max loss = 0
    """
    actual_pos = int(driver.get('officialPosition') or driver.get('position') or 0)
    start_pos  = int(driver.get('startPosition') or 0)
    n = len(all_drivers)

    if actual_pos <= 0 or start_pos <= 0 or n <= 1:
        return 10.0  # not enough data → neutral

    pg = start_pos - actual_pos  # positive = moved forward

    if pg > 0:
        max_gain = start_pos - 1          # best possible = P1
        ratio = (pg / max_gain) if max_gain > 0 else 0.0
    elif pg < 0:
        max_loss = n - start_pos          # worst possible = last
        ratio = (pg / max_loss) if max_loss > 0 else 0.0
    else:
        ratio = 0.0

    return max(0.0, min(20.0, 10.0 + 10.0 * ratio))


def calculate_performance_score(driver: dict, all_drivers: list, state) -> float:
    """
    Return a 0-100 performance score for *driver*.

    Args:
        driver:      single driver dict from get_drivers_data()
        all_drivers: full list of driver dicts for the current session
        state:       application State object (may be None in tests)

    Returns:
        float in [0, 100] rounded to one decimal place.
    """
    from iracing.history import get_driver_stats

    user_id = int(driver.get('UserID') or 0)
    car_idx = driver.get('carIdx')
    score = 0.0

    # ── 1. Historical pace (0-30 pts) ─────────────────────────────────────
    # avg_pace_delta_pct: how many % behind session-best the driver typically is.
    # 0 % → 30 pts (always fastest),  ≥10 % → 0 pts.
    stats = get_driver_stats(user_id)
    avg_delta = stats.get('avg_pace_delta_pct')

    if avg_delta is not None and stats['sessions_counted'] >= 1:
        # 10 % threshold: beyond this no historical pace points are awarded
        hist_pts = max(0.0, 30.0 * (1.0 - avg_delta / 10.0))
        score += min(30.0, hist_pts)
    else:
        score += 15.0  # no history yet → neutral

    # ── 2. Session pace (0-30 pts) ────────────────────────────────────────
    driver_best = _parse_lap(driver.get('bestLapTime'))
    if driver_best:
        session_times = [
            t for t in (_parse_lap(d.get('bestLapTime')) for d in all_drivers)
            if t
        ]
        if session_times:
            s_best = min(session_times)
            s_worst = max(session_times)
            span = s_worst - s_best
            if span > 0:
                pace_pts = 30.0 * (s_worst - driver_best) / span
            else:
                pace_pts = 30.0  # all drivers equal
            score += max(0.0, min(30.0, pace_pts))
        else:
            score += 15.0
    # else: no lap set yet → 0 pts for this component

    # ── 3. iRating-adjusted position (0-20 pts, neutral = 10) ────────────
    # Compares where the driver actually finished vs where their iRating rank
    # would predict them to finish.  Falls back to positions-gained when
    # iRating data is absent (e.g. practice, or drivers with iRating = 0).
    actual_pos = int(driver.get('officialPosition') or driver.get('position') or 0)
    driver_irating = int(driver.get('iRating', 0) or 0)

    if actual_pos > 0 and driver_irating > 0:
        # Sort the live field by iRating descending → position 1 = highest iRating
        rated = [(int(d.get('iRating', 0) or 0), d) for d in all_drivers
                 if int(d.get('iRating', 0) or 0) > 0]
        rated_sorted = sorted(rated, key=lambda x: -x[0])
        irating_rank = next(
            (i + 1 for i, (_, d) in enumerate(rated_sorted) if d is driver),
            None
        )
        if irating_rank is not None:
            # Positive adjustment = outperforming expectations
            adjustment = irating_rank - actual_pos
            score += max(0.0, min(20.0, 10.0 + float(adjustment)))
        else:
            score += _normalized_positions_score(driver, all_drivers)
    else:
        score += _normalized_positions_score(driver, all_drivers)

    # ── 4. Lap-time consistency (0-20 pts) ────────────────────────────────
    if state and car_idx is not None:
        lap_times = state.driver_lap_times.get(car_idx, [])
        n = len(lap_times)
        if n >= 3:
            recent = lap_times[-10:]
            mean = sum(recent) / len(recent)
            std = _stddev(recent)
            cv_pct = (std / mean * 100.0) if mean > 0 else 100.0
            # CV 0 % → 20 pts; CV ≥ 3 % → 0 pts
            score += max(0.0, min(20.0, 20.0 * (1.0 - cv_pct / 3.0)))
        elif n >= 1:
            score += 10.0  # too few laps to measure → neutral

    return round(min(100.0, max(0.0, score)), 1)
