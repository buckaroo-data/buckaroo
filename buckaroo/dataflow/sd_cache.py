"""Keyed summary-stats cache.

Three scopes — raw / clean / filt — each addressed by the canonical op
chain that produced them. The chain is the cache key, hashed to a short
opaque string for use as a dict key on the wire.

Why this exists: the dataflow re-derives SD on every state change today,
even when most of the relevant state didn't move. Keying SD by its op
chain means a ``quick_command_args`` flip is a cache miss for the
filtered scope only — the raw and cleaned scopes are cache hits and
nothing recomputes. xorq backends double up the win because their own
expression cache deduplicates the same shape one layer down.

The frontend reads the three pointer traitlets
(``raw_sd_key`` / ``clean_sd_key`` / ``filt_sd_key``) — each holds an
opaque hash — and looks the corresponding entry up in
``summary_stats_cache``. Python is the sole writer of cache keys; the
frontend never hashes anything itself, so there's no canonical-JSON
contract to drift across the language boundary.
"""
import hashlib
import json
from typing import Any, Dict, List

from buckaroo.jlisp.lisp_utils import is_symbol, sym_meta_get


def _canonical_chain_repr(chain: List[Any]) -> str:
    """Stable JSON serialization of an op chain.

    sort_keys keeps dict-of-dicts ordering deterministic across Python
    versions; default=str catches the odd Symbol-or-similar that slips
    through from the lispy interpreter without crashing the hash.
    """
    return json.dumps(chain, sort_keys=True, default=str)


def hash_chain(chain: List[Any], extra: Any = None) -> str:
    """Short opaque hash of an op chain — used as a cache key.

    blake2b with an 8-byte digest gives 16 hex chars: enough headroom for
    collision-free identification within a session, short enough not to
    bloat the wire when many cache entries accumulate.

    ``extra``, if provided, is appended to the canonical repr before
    hashing. Callers fold non-chain identity into the key this way —
    e.g. ``id(sampled_df)`` so a ``raw_df`` swap with an unchanged chain
    doesn't collide with the previous dataset's cache entry (codex P1
    on #783).
    """
    payload = _canonical_chain_repr(chain)
    if extra is not None:
        payload = payload + '|' + str(extra)
    return hashlib.blake2b(payload.encode(), digest_size=8).hexdigest()


def _is_real_op(op: Any) -> bool:
    """True for genuine operations — list with a symbol head.

    The dataflow seeds ``operations`` with a sentinel like
    ``{'meta':'no-op'}`` until the autocleaning pipeline has run; that
    bare dict is not a runnable op, and feeding it to the interpreter
    yields garbage. Filtering on shape keeps the cache observer safe
    against any intermediate seed state without hardcoding the sentinel
    value.
    """
    return isinstance(op, list) and len(op) > 0 and is_symbol(op[0])


def _is_quick_command_op(op: Any) -> bool:
    if not _is_real_op(op):
        return False
    return sym_meta_get(op[0], 'quick_command') is True


def split_chain_by_scope(operations: List[Any]) -> Dict[str, List[Any]]:
    """Partition the full operations list into the three scope chains.

    * raw: always empty — raw scope is "no ops applied"
    * clean: real ops that aren't quick-commands (autocleaning and
      user-authored ops both live here — they survive a filter flip)
    * filt: every real op — autocleaning + quick-command + user

    Both buckets are filtered to real ops only, so seed sentinels like
    ``{'meta':'no-op'}`` are ignored. Quick-command ops are tagged
    ``meta.quick_command = True`` by ``sQ()``.
    """
    real_ops = [op for op in (operations or []) if _is_real_op(op)]
    clean_ops = [op for op in real_ops if not _is_quick_command_op(op)]
    return {'raw': [], 'clean': clean_ops, 'filt': real_ops}
