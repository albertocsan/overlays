"""
Race history store for the iRacing timing overlay.

Saves one entry per completed session (race or qualifying) and provides
aggregated per-driver stats used by the performance score calculator.

File location: <project_root>/data/race_history.json
Schema:
  {
    "version": 1,
    "sessions": [
      {
        "session_id": "ledenon_2025-01-15_RACE_1737000000",
        "track": "ledenon",
        "track_config": "",
        "date": "2025-01-15",
        "session_type": "RACE",
        "results": [
          {
            "user_id": 349184,
            "name": "Cristian Lamela",
            "car_number": "14",
            "position": 1,
            "total_drivers": 20,
            "best_lap_seconds": 78.445,
            "laps_completed": 15,
            "positions_gained": 3,
            "pace_delta_pct": 0.0   // % above session-best lap (0 = fastest)
          }
        ]
      }
    ]
  }
"""

import json
import os
import glob
import logging
import time
from datetime import datetime

logger = logging.getLogger("iracing-timing")

HISTORY_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'race_history.json')
)

# ── in-memory cache ────────────────────────────────────────────────────────────
_history_cache = None
_history_mtime = -1.0
_driver_stats_cache: dict = {}  # {user_id: stats_dict}


def _data_dir():
    return os.path.dirname(HISTORY_FILE)


def _current_mtime():
    try:
        return os.path.getmtime(HISTORY_FILE)
    except OSError:
        return -1.0


def _load_raw():
    """Read the JSON file from disk. Returns bare dict; does not update cache."""
    if not os.path.exists(HISTORY_FILE):
        return {"version": 1, "sessions": []}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"history: could not read {HISTORY_FILE}: {e}")
        return {"version": 1, "sessions": []}


def _get_history():
    """Return cached history, reloading from disk only when the file changed."""
    global _history_cache, _history_mtime, _driver_stats_cache
    mtime = _current_mtime()
    if _history_cache is None or mtime != _history_mtime:
        _history_cache = _load_raw()
        _history_mtime = mtime
        _driver_stats_cache.clear()  # invalidate per-driver stats
    return _history_cache


def _parse_lap(s):
    """Convert 'M:SS.mmm' string or float to seconds. Returns None if invalid."""
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


# ── public write API ───────────────────────────────────────────────────────────

def save_session_result(track: str, track_config: str, session_type: str, drivers_data: list) -> bool:
    """
    Append results from a finished session to race_history.json.

    Args:
        track:        iRacing track name
        track_config: track configuration (or empty string)
        session_type: 'RACE', 'QUALIFY', 'PRACTICE', etc.
        drivers_data: list of driver dicts as produced by get_drivers_data()

    Returns True on success.
    """
    global _history_cache, _history_mtime, _driver_stats_cache

    # Only record races and qualifying sessions
    stype = (session_type or '').upper()
    if not any(k in stype for k in ('RACE', 'QUALIFY', 'PRACTICE')):
        logger.info(f"history: skipping session type '{session_type}'")
        return False

    try:
        history = _load_raw()

        today = datetime.now().strftime("%Y-%m-%d")
        session_id = f"{track}_{today}_{stype}_{int(time.time())}"

        results = []
        total = len(drivers_data)

        for d in drivers_data:
            user_id = d.get('UserID') or d.get('user_id', 0)
            if not user_id or int(user_id) <= 0:
                continue
            pos = d.get('officialPosition') or d.get('position') or 0
            best_s = _parse_lap(d.get('bestLapTime'))
            irating = int(d.get('iRating', 0) or 0)
            results.append({
                "user_id": int(user_id),
                "name": d.get('fullName') or d.get('userName', ''),
                "car_number": str(d.get('carNumber', '')),
                "position": int(pos),
                "total_drivers": int(total),
                "best_lap_seconds": round(best_s, 4) if best_s else None,
                "laps_completed": int(d.get('lapsComplete') or 0),
                "positions_gained": int(d.get('positionsGained') or 0),
                "irating": irating,
            })

        # Pace delta: % behind the session's fastest lap (0 = pole/fastest)
        valid_laps = [r['best_lap_seconds'] for r in results if r['best_lap_seconds']]
        session_best = min(valid_laps) if valid_laps else None
        for r in results:
            if session_best and r['best_lap_seconds']:
                r['pace_delta_pct'] = round(
                    (r['best_lap_seconds'] - session_best) / session_best * 100, 4
                )
            else:
                r['pace_delta_pct'] = None

        # Strength of Field: average iRating of the field
        valid_iratings = [r['irating'] for r in results if r.get('irating', 0) > 0]
        sof = int(sum(valid_iratings) / len(valid_iratings)) if valid_iratings else 0

        history.setdefault('sessions', []).append({
            "session_id": session_id,
            "track": track,
            "track_config": track_config or "",
            "date": today,
            "session_type": stype,
            "sof": sof,
            "results": results,
        })

        os.makedirs(_data_dir(), exist_ok=True)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        # Update cache immediately so the next score calculation sees the new data
        _history_cache = history
        _history_mtime = _current_mtime()
        _driver_stats_cache.clear()

        logger.info(
            f"history: saved {stype} at '{track}' — {len(results)} drivers, "
            f"session_id={session_id}"
        )
        return True

    except Exception as e:
        logger.error(f"history: error saving session result: {e}", exc_info=True)
        return False


# ── public read API ────────────────────────────────────────────────────────────

def get_driver_stats(user_id: int, max_sessions: int = 20) -> dict:
    """
    Return aggregated performance stats for a driver from the last N sessions.

    Keys in returned dict:
      avg_position_ratio  – mean of (total-pos)/(total-1) per race (1=win, 0=last)
      avg_pace_delta_pct  – mean % behind session-best lap (0=fastest)
      sessions_counted    – number of sessions that contributed to these stats
    """
    if user_id in _driver_stats_cache:
        return _driver_stats_cache[user_id]

    history = _get_history()

    position_ratios = []
    position_weights = []
    pace_deltas = []
    pace_weights = []

    # Iterate most-recent sessions first; weight each by Strength of Field
    for sess in reversed(history.get('sessions', [])):
        if len(position_ratios) >= max_sessions:
            break
        sof = float(sess.get('sof') or 0)
        weight = max(1.0, sof)  # 1.0 minimum so sessions without SoF still count
        for r in sess.get('results', []):
            if r.get('user_id') != user_id:
                continue
            total = r.get('total_drivers', 0)
            pos = r.get('position', 0)
            if total > 1 and 0 < pos <= total:
                position_ratios.append((total - pos) / (total - 1))
                position_weights.append(weight)
            delta = r.get('pace_delta_pct')
            if delta is not None:
                pace_deltas.append(delta)
                pace_weights.append(weight)
            break  # one entry per session per driver

    def _wavg(vals, weights):
        total_w = sum(weights)
        return sum(v * w for v, w in zip(vals, weights)) / total_w if vals else None

    stats = {
        "avg_position_ratio": _wavg(position_ratios, position_weights),
        "avg_pace_delta_pct": _wavg(pace_deltas, pace_weights),
        "sessions_counted": len(position_ratios),
    }
    _driver_stats_cache[user_id] = stats
    return stats


# ── iRacing file importer ──────────────────────────────────────────────────────

# Folder where the user drops iRacing event result JSONs
_IRACING_RACES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'old_iracing_races')
)

# Map iRacing simsession_type_name → our session type string
_SESSION_TYPE_MAP = {
    'race':             'RACE',
    'open qualifying':  'QUALIFY',
    'lone qualify':     'QUALIFY',
    'open practice':    'PRACTICE',
    'practice':         'PRACTICE',
}


def _iracing_time_to_seconds(raw) -> float | None:
    """Convert iRacing lap time (1/10000 s units) to seconds. Returns None if invalid."""
    try:
        v = int(raw)
        return v / 10000.0 if v > 0 else None
    except Exception:
        return None


def _parse_iracing_file(path: str) -> list[dict]:
    """
    Parse one iRacing event result JSON file.

    Returns a list of session dicts ready to be appended to race_history['sessions'].
    Returns an empty list on any parse error.
    """
    sessions_out = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        logger.error(f"import: cannot read {path}: {e}")
        return []

    try:
        data = raw.get('data') or raw  # some exports wrap in {"data": ...}
        subsession_id = data.get('subsession_id')
        track_info = data.get('track', {})
        track_name = track_info.get('track_name', 'unknown')
        track_config = track_info.get('config_name', '')
        # Ignore config when it signals "full course" or is identical to track name
        if track_config.lower() in ('', 'fullcourse', track_name.lower()):
            track_config = ''

        date_str = (data.get('start_time') or '')[:10]  # "2026-04-20"

        for sim_sess in data.get('session_results', []):
            stype_raw = (sim_sess.get('simsession_type_name') or '').lower()
            stype = _SESSION_TYPE_MAP.get(stype_raw)
            if not stype:
                continue  # skip unknown session types

            raw_results = sim_sess.get('results', [])
            # Filter out AI, pace car, and spectators
            real = [r for r in raw_results if not r.get('ai', False) and r.get('cust_id', 0) > 0]
            if not real:
                continue

            total = len(real)
            results_out = []
            for r in real:
                finish_pos = int(r.get('finish_position', 0)) + 1   # 0-based → 1-based
                start_pos  = int(r.get('starting_position', 0)) + 1

                best_s = _iracing_time_to_seconds(r.get('best_lap_time', -1))
                avg_s  = _iracing_time_to_seconds(r.get('average_lap', -1))

                # positions gained: positive = moved forward
                if stype == 'RACE':
                    pg = start_pos - finish_pos
                else:
                    pg = 0  # no grid in qualifying/practice

                results_out.append({
                    "user_id":          int(r['cust_id']),
                    "name":             r.get('display_name', ''),
                    "car_number":       "",
                    "position":         finish_pos,
                    "total_drivers":    total,
                    "best_lap_seconds": round(best_s, 4) if best_s else None,
                    "average_lap_seconds": round(avg_s, 4) if avg_s else None,
                    "laps_completed":   int(r.get('laps_complete', 0)),
                    "incidents":        int(r.get('incidents', 0)),
                    "positions_gained": pg,
                })

            # Compute pace delta % relative to session best
            valid_laps = [r['best_lap_seconds'] for r in results_out if r['best_lap_seconds']]
            session_best = min(valid_laps) if valid_laps else None
            for r in results_out:
                if session_best and r['best_lap_seconds']:
                    r['pace_delta_pct'] = round(
                        (r['best_lap_seconds'] - session_best) / session_best * 100, 4
                    )
                else:
                    r['pace_delta_pct'] = None

            sess_id = f"iracing_{subsession_id}_{stype}"
            sessions_out.append({
                "session_id":   sess_id,
                "track":        track_name,
                "track_config": track_config,
                "date":         date_str,
                "session_type": stype,
                "subsession_id": subsession_id,
                "results":      results_out,
            })

    except Exception as e:
        logger.error(f"import: error parsing {path}: {e}", exc_info=True)

    return sessions_out


def import_iracing_files(folder_path: str | None = None) -> dict:
    """
    Import all iRacing event result JSON files from *folder_path* into
    race_history.json, skipping sessions already present.

    Args:
        folder_path: directory containing eventresult-*.json files.
                     Defaults to overlay/old_iracing_races/.

    Returns:
        dict with keys "imported" (int), "skipped" (int), "errors" (list[str])
    """
    global _history_cache, _history_mtime, _driver_stats_cache

    folder = folder_path or _IRACING_RACES_DIR
    files = sorted(glob.glob(os.path.join(folder, '*.json')))
    if not files:
        logger.warning(f"import: no JSON files found in {folder}")
        return {"imported": 0, "skipped": 0, "errors": [f"No JSON files in {folder}"]}

    history = _load_raw()
    history.setdefault('sessions', [])

    # Build a set of already-imported session IDs for fast lookup
    existing_ids = {s.get('session_id') for s in history['sessions']}

    imported = 0
    skipped = 0
    errors = []

    for path in files:
        fname = os.path.basename(path)
        try:
            new_sessions = _parse_iracing_file(path)
            for sess in new_sessions:
                if sess['session_id'] in existing_ids:
                    skipped += 1
                    logger.debug(f"import: skipping already-imported {sess['session_id']}")
                else:
                    history['sessions'].append(sess)
                    existing_ids.add(sess['session_id'])
                    imported += 1
                    logger.info(f"import: added {sess['session_id']} ({fname})")
        except Exception as e:
            msg = f"{fname}: {e}"
            errors.append(msg)
            logger.error(f"import: unexpected error for {fname}: {e}", exc_info=True)

    if imported > 0:
        os.makedirs(_data_dir(), exist_ok=True)
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        # Refresh cache
        _history_cache = history
        _history_mtime = _current_mtime()
        _driver_stats_cache.clear()
        logger.info(f"import: done — {imported} sessions imported, {skipped} skipped")

    return {"imported": imported, "skipped": skipped, "errors": errors}
