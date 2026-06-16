#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any, Generic, List, Optional, Type

from traitlets import HasTraits, MetaHasTraits

from buckaroo.pluggable_analysis_framework.col_analysis import ColAnalysis

from .df_types import FrameT


class _ABCMetaHasTraits(ABCMeta, MetaHasTraits):
    pass


class ABCDataflow(HasTraits, Generic[FrameT], metaclass=_ABCMetaHasTraits):
    """
    Abstract base for dataflow implementations.
    Reference implementations: DataFlow and CustomizableDataflow.
    Other implementations (e.g., ColumnExecutorDataflow) should conform.

    Generic on ``FrameT`` — the (unbounded) carrier type, so this umbrella
    covers both the eager subtree (``DataFlow`` / ``CustomizableDataflow``,
    which narrow to the ``DataFrameLike``-bound ``DataFrameT``) and the lazy
    ``ColumnExecutorDataflow`` (``ABCDataflow[pl.LazyFrame]``). See
    ``df_types`` for the ``FrameT`` / ``DataFrameT`` split.
    """

    # Baseline interface expected by Buckaroo widgets and extensions.
    #
    # The synced/computed wire attributes below are declared ``Any`` on
    # purpose. Every concrete dataflow backs them with a traitlets trait
    # (``Dict(...)`` / ``Any(...)``) or a ``@property``, and a traitlets
    # descriptor returns ``Any`` on instance access. Declaring a concrete
    # ``Dict[str, Any]`` here only fights the descriptor protocol: the
    # subclass trait/property reads as an incompatible override, and a write
    # (``self.summary_sd = ...``) reads as an illegal assignment. What these
    # document is "this name exists on every dataflow"; each trait's actual
    # shape lives with its definition. Same rationale as the frame-carrying
    # methods in ``df_types`` — type where it's sound, not on the traits.
    analysis_klasses: List[Type[ColAnalysis]]
    df_data_dict: Any
    df_display_args: Any
    df_meta: Any
    buckaroo_options: Any
    command_config: Any
    operations: Any
    operation_results: Any
    summary_sd: Any
    cleaned_sd: Any
    processed_sd: Any
    merged_sd: Any
    widget_args_tuple: Any

    @property
    @abstractmethod
    def processed_df(self) -> Optional[FrameT]:
        """The fully-processed frame the widget renders, in the backend's
        own type (``None`` before the pipeline has run, or for lazy
        backends that never materialize).

        A read-only computed property in every implementation — eager
        backends derive it from ``processed_result``; the lazy
        ``ColumnExecutorDataflow`` never materializes and returns ``None``.
        Declared as a property (not a plain attribute) so those
        ``@property`` overrides are a compatible, like-for-like override.
        """
        ...

    @abstractmethod
    def populate_df_meta(self) -> None:
        ...


