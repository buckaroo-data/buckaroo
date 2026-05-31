"""Initial-load cache: snapshot the first render so it can be replayed
without touching the DataFrame or executing the expression.

See docs/initial-load-cache-design.md. The handshake (config_fingerprint +
schema) decides whether a precomputed bundle matches the widget's live
configuration; a mismatch warns and recomputes — the cache is never blindly
trusted.
"""
