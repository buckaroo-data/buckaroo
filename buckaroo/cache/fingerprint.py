"""Stable config fingerprint for the initial-load cache.

``config_fingerprint`` identifies the *data-touching* configuration — the set
of inputs that determine ``merged_sd`` and the row window — so the handshake
can decide whether a cached bundle matches the widget's live config without
recomputing. It is **cross-process stable**: keyed on each class's
``module.qualname`` (plus an optional per-class ``cache_version``), never on
``id()``, so a bundle built in one process validates in another.

Display knobs (column_config_overrides, component_config, pinned_rows, theme)
are deliberately *out* of the fingerprint — they're applied at replay from the
bundle, so re-theming never invalidates the cache. See
docs/initial-load-cache-design.md.
"""
import hashlib
import json
from typing import Any, Iterable, List, Optional

# Bump when the bundle schema or the assembly logic changes incompatibly, so
# old bundles fail the handshake (warn + recompute) rather than mis-serve.
INITIAL_CACHE_VERSION = 1


def _klass_id(kls: Any) -> str:
    """Stable identity for an analysis/styling class.

    ``module.qualname`` is reproducible across processes (unlike ``id``). An
    optional ``cache_version`` class attribute lets a class bust its own cached
    bundles when its logic changes without a global version bump.
    """
    mod = getattr(kls, '__module__', '')
    qn = getattr(kls, '__qualname__', None) or getattr(kls, '__name__', repr(kls))
    ver = getattr(kls, 'cache_version', '')
    return f"{mod}.{qn}:{ver}"


def _sampling_id(sampling_klass: Any) -> str:
    if sampling_klass is None:
        return ''
    # Sampling affects which rows reach the analysis pipeline and the window,
    # so its identity + the limits that change output are part of the key.
    return "|".join([_klass_id(sampling_klass), f"pre={getattr(sampling_klass, 'pre_limit', '')}",
        f"ser={getattr(sampling_klass, 'serialize_limit', '')}", f"cols={getattr(sampling_klass, 'max_columns', '')}"])


def config_fingerprint(*, analysis_klasses: Iterable[Any], sampling_klass: Any = None,
        init_sd: Optional[dict] = None, skip_stat_columns: Optional[Iterable[str]] = None,
        cache_version: Optional[str] = None) -> str:
    """Return a stable hex fingerprint of the data-touching configuration."""
    skip: List[str] = sorted(str(c) for c in (skip_stat_columns or []))
    payload = {
        'v': INITIAL_CACHE_VERSION,
        'analysis_klasses': [_klass_id(k) for k in analysis_klasses],
        'sampling': _sampling_id(sampling_klass),
        # init_sd injects/overrides stats, so its content is part of identity.
        # default=str keeps the hash deterministic past numpy / odd scalars.
        'init_sd': json.dumps(init_sd, sort_keys=True, default=str) if init_sd else None,
        'skip_stat_columns': skip,
        'cache_version': cache_version}
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.blake2b(blob.encode(), digest_size=16).hexdigest()
