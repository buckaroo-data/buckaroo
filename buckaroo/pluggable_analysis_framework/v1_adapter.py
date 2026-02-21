"""V1 compatibility adapter.

Converts existing ColAnalysis classes to StatFunc objects for use
in StatPipeline. This allows mixing v1 ColAnalysis classes with
v2 @stat functions in the same pipeline.

Example::

    pipeline = StatPipeline([
        TypingStats,           # v1 ColAnalysis class
        DefaultSummaryStats,   # v1 ColAnalysis class
        distinct_per,          # v2 @stat function
    ])
"""
from __future__ import annotations

from typing import Any, List, Type

from .col_analysis import ColAnalysis
from .stat_func import StatFunc, StatKey, RawSeries


def _has_custom_series_summary(kls: Type[ColAnalysis]) -> bool:
    """Check if a ColAnalysis class overrides series_summary."""
    return (
        kls.series_summary is not ColAnalysis.series_summary
        or kls.requires_raw
    )


def _has_custom_computed_summary(kls: Type[ColAnalysis]) -> bool:
    """Check if a ColAnalysis class overrides computed_summary."""
    return kls.computed_summary is not ColAnalysis.computed_summary


def col_analysis_to_stat_funcs(kls: Type[ColAnalysis]) -> List[StatFunc]:
    """Convert a v1 ColAnalysis class into v2 StatFunc objects.

    Creates one or two StatFunc objects per ColAnalysis:
    - A "series" StatFunc if the class has a custom series_summary
    - A "computed" StatFunc if the class has a custom computed_summary

    If the class has both, the computed func depends on the series func's
    outputs, preserving the v1 two-phase execution model.

    Args:
        kls: a ColAnalysis subclass

    Returns:
        list of StatFunc objects
    """
    funcs = []
    has_series = _has_custom_series_summary(kls)
    has_computed = _has_custom_computed_summary(kls)

    defaults = kls.provides_defaults.copy()

    if has_series:
        # Series phase provides keys from provides_series_stats + provides_defaults
        # (v1 merges defaults first, then updates with series_summary result)
        series_provide_names = set(kls.provides_series_stats) | set(defaults.keys())

        series_provides = [StatKey(name, Any) for name in sorted(series_provide_names)]
        series_requires = [StatKey('ser', RawSeries)]

        # Capture kls and defaults in closure
        _kls = kls
        _defaults = defaults.copy()

        def _make_series_func(kls_ref, defaults_ref):
            def v1_series_wrapper(ser=None):
                result = defaults_ref.copy()
                if ser is not None:
                    series_result = kls_ref.series_summary(ser, ser)
                    result.update(series_result)
                return result
            v1_series_wrapper.__name__ = f"{kls_ref.__name__}__series"
            v1_series_wrapper.__qualname__ = f"{kls_ref.__qualname__}__series"
            v1_series_wrapper.__module__ = getattr(kls_ref, '__module__', __name__)
            return v1_series_wrapper

        series_func = _make_series_func(_kls, _defaults)

        funcs.append(StatFunc(
            name=f"{kls.__name__}__series",
            func=series_func,
            requires=series_requires,
            provides=series_provides,
            needs_raw=True,
            quiet=kls.quiet,
            spread_dict_result=True,
        ))

    if has_computed:
        # Computed phase: uses v1_computed mode to receive full accumulator
        # Only declare requires_summary keys for DAG ordering purposes
        dag_req_names = set(kls.requires_summary)
        computed_requires = [StatKey(name, Any) for name in sorted(dag_req_names)]

        # Provide keys from provides_defaults; if empty, use a synthetic status key
        computed_provide_names = set(defaults.keys())
        if not computed_provide_names:
            computed_provide_names = {f'__{kls.__name__}__status'}
        computed_provides = [StatKey(name, Any) for name in sorted(computed_provide_names)]

        _kls = kls

        def _make_computed_func(kls_ref):
            def v1_computed_wrapper(summary_dict):
                return kls_ref.computed_summary(summary_dict)
            v1_computed_wrapper.__name__ = f"{kls_ref.__name__}__computed"
            v1_computed_wrapper.__qualname__ = f"{kls_ref.__qualname__}__computed"
            v1_computed_wrapper.__module__ = getattr(kls_ref, '__module__', __name__)
            return v1_computed_wrapper

        computed_func = _make_computed_func(_kls)

        funcs.append(StatFunc(
            name=f"{kls.__name__}__computed",
            func=computed_func,
            requires=computed_requires,
            provides=computed_provides,
            needs_raw=False,
            quiet=kls.quiet,
            v1_computed=True,
            spread_dict_result=True,
        ))

    elif not has_series and not has_computed:
        # Class only has provides_defaults (pure defaults, no computation)
        if defaults:
            provide_keys = [StatKey(name, Any) for name in sorted(defaults.keys())]
            _defaults = defaults.copy()
            _kls_name = kls.__name__

            def _make_defaults_func(defaults_ref, name):
                def v1_defaults_wrapper():
                    return defaults_ref.copy()
                v1_defaults_wrapper.__name__ = name
                return v1_defaults_wrapper

            defaults_func = _make_defaults_func(_defaults, _kls_name)

            funcs.append(StatFunc(
                name=_kls_name,
                func=defaults_func,
                requires=[],
                provides=provide_keys,
                needs_raw=False,
                quiet=kls.quiet,
            ))

    return funcs
