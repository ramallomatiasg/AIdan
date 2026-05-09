"""
Multi-TF consensus tracker.

Tracks recent strategy creations across M5/M15/H1. Si 2+ tracks coinciden
en direction dentro de CONSENSUS_WINDOW_SEC, marca consenso y permite
boost de lote para el ultimo trade.

In-memory state. Thread-safe (locked dict access).
"""
import time
from threading import Lock

_lock = Lock()
# Recent direction events: list of (timestamp, track, direction)
_events = []


def record_signal(track, direction, timestamp=None):
    """Record a signal from a track. track: 'm5'|'m15'|'h1'. direction: 'CALL'|'PUT'."""
    if direction not in ('CALL', 'PUT'):
        return
    ts = timestamp or time.time()
    with _lock:
        _events.append((ts, track.lower(), direction))
        # Cleanup old events (>1 hour)
        cutoff = ts - 3600
        _events[:] = [e for e in _events if e[0] >= cutoff]


def check_consensus(direction, window_sec=300, exclude_track=None):
    """Check if there's consensus on direction within last window_sec.

    Returns: int — number of distinct tracks (m5/m15/h1) that signaled this
             direction recently. 0-3.

    Example: si M15 y H1 ambos disparan CALL en los ultimos 5min y ahora
    M5 esta por entrar CALL -> check_consensus('CALL', 300, exclude_track='m5') -> 2
    """
    now = time.time()
    cutoff = now - window_sec
    seen_tracks = set()
    with _lock:
        for ts, track, dir_ in _events:
            if ts < cutoff:
                continue
            if dir_ != direction:
                continue
            if exclude_track and track == exclude_track:
                continue
            seen_tracks.add(track)
    return len(seen_tracks)


def get_recent_state():
    """Snapshot of recent events for inspection."""
    with _lock:
        return list(_events)
