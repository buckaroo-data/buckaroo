"""
Calibration for mp_timeout overhead.

This module provides a function to measure the baseline overhead of mp_timeout,
which is needed for batch planning. The calibration is performed once per process
and cached to avoid repeated measurements.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from typing import Optional

from .mp_timeout_decorator import mp_timeout


# Global state for calibration
_calibration_lock = threading.Lock()
_calibrated_overhead: Optional[timedelta] = None
_calibration_in_progress = False


def _noop_function(*args, **kwargs):
    """No-op function for baseline measurement."""
    return {}


def calibrate_mp_timeout_overhead(timeout_secs: float = 30.0) -> timedelta:
    """
    Measure the baseline overhead of mp_timeout by executing a no-op function.
    
    This function is thread-safe and will only perform the measurement once per process.
    Subsequent calls return the cached value.
    
    Args:
        timeout_secs: Timeout to use for the measurement (default 30.0)
        
    Returns:
        timedelta representing the baseline overhead of mp_timeout
    """
    global _calibrated_overhead, _calibration_in_progress
    
    # Fast path: already calibrated
    if _calibrated_overhead is not None:
        return _calibrated_overhead
    
    # Thread-safe calibration
    with _calibration_lock:
        # Double-check after acquiring lock
        if _calibrated_overhead is not None:
            return _calibrated_overhead
        
        # Prevent concurrent calibration attempts
        if _calibration_in_progress:
            # Another thread is calibrating, wait and retry
            # (In practice, this should be very fast, so we'll just wait)
            while _calibration_in_progress:
                threading.Event().wait(0.01)  # Small wait
            if _calibrated_overhead is not None:
                return _calibrated_overhead
        
        _calibration_in_progress = True
        
        try:
            from datetime import datetime as dtdt
            # Measure baseline overhead
            t1 = dtdt.now()
            try:
                timed_exec = mp_timeout(timeout_secs)(_noop_function)
                timed_exec()  # Execute no-op
                t2 = dtdt.now()
                overhead = t2 - t1
            except Exception:
                # If calibration fails, use a conservative default
                # (50ms is a reasonable default for mp_timeout overhead)
                overhead = timedelta(milliseconds=50)
            
            _calibrated_overhead = overhead
            return overhead
        finally:
            _calibration_in_progress = False


def get_calibrated_overhead() -> timedelta:
    """
    Get the calibrated mp_timeout overhead.
    
    If calibration hasn't been performed yet, performs it automatically.
    
    Returns:
        timedelta representing the baseline overhead
    """
    if _calibrated_overhead is None:
        return calibrate_mp_timeout_overhead()
    return _calibrated_overhead


def reset_calibration() -> None:
    """
    Reset the calibration (useful for testing).
    
    This clears the cached overhead value, forcing recalibration on next call.
    """
    global _calibrated_overhead
    with _calibration_lock:
        _calibrated_overhead = None
