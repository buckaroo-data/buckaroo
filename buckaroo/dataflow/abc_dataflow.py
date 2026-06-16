#!/usr/bin/env python
# coding: utf-8
from __future__ import annotations

from abc import ABCMeta, abstractmethod
from typing import Any, Dict, Generic, List, Optional, Type

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
    analysis_klasses: List[Type[ColAnalysis]]
    df_data_dict: Dict[str, Any]
    df_display_args: Dict[str, Any]
    df_meta: Dict[str, Any]
    buckaroo_options: Dict[str, Any]
    command_config: Dict[str, Any]
    operations: Any
    operation_results: Dict[str, Any]
    summary_sd: Dict[str, Any]
    cleaned_sd: Dict[str, Any]
    processed_sd: Dict[str, Any]
    merged_sd: Dict[str, Any]
    widget_args_tuple: Any
    # The fully-processed frame the widget renders, in the backend's own
    # type (``None`` before the pipeline has run, or for lazy backends
    # that never materialize).
    processed_df: Optional[FrameT]

    @abstractmethod
    def populate_df_meta(self) -> None:
        ...


