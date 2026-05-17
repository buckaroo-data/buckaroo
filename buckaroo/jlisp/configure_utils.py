"""jlisp interpreter wiring for buckaroo Commands.

A Command's transform returns one of two shapes:
  - bare df  : the legacy/common shape; passed straight through
  - SDResult : carries (df, sd_updates); the interpreter merges
               sd_updates into the running sd dict and forwards the df

Independently, a Command may take `sd` as a regular lisp arg by listing
`s('sd')` in its `command_default`. The interpreter binds `sd` to a
read-only MappingProxyType view of the current sd state — sd-as-arg is
contractually read-only; to write, return SDResult from the same call.

These two channels share one underlying dict: an SDResult written by an
upstream op is visible to a downstream sd-as-arg reader in the same
pipeline.
"""

import copy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Dict

import pandas as pd

from .lispy import make_interpreter


@dataclass(frozen=True)
class SDResult:
    """Return value for a Command's transform when it wants to contribute
    sd_updates alongside the new df.

    `sd_updates` is a partial SDType (`{col: {key: value}}`) merged into
    the running sd dict. Frozen because the result is a one-shot return
    value — the interpreter only reads from it.
    """
    df: Any
    sd_updates: Dict[str, Dict[str, Any]]


def configure_buckaroo(transforms):
    command_defaults = {}
    command_patterns = {}

    transform_lisp_primitives = {}
    to_py_lisp_primitives = {}
    for T in transforms:
        t = T()
        transform_name = t.command_default[0]['symbol']
        command_defaults[transform_name] = t.command_default
        command_patterns[transform_name] = t.command_pattern
        transform_lisp_primitives[transform_name] = T.transform
        to_py_lisp_primitives[transform_name] = T.transform_to_py

    buckaroo_eval, raw_parse = make_interpreter(transform_lisp_primitives)

    def buckaroo_transform(instructions, df, initial_sd):
        """Run lisp `instructions` against `df` with sd seeded from
        `initial_sd` (deep-copied — caller's nested dicts are untouched).

        sd is bound in the env under two names:
          - `sd`             : MappingProxyType view (read-only) for
                               commands that list s('sd') in command_default
          - `apply-result!`  : per-call closure that captures the live
                               mutable dict; wraps each form's return
                               value and merges SDResult.sd_updates

        Returns (df, sd) where sd is the framework's deep-copied dict
        with all op mutations applied.
        """
        if isinstance(df, pd.DataFrame):
            df_copy = df.copy()
        else: # hack we know it's polars here... just getting something working for now
            df_copy = df.clone()

        sd_dict = copy.deepcopy(initial_sd)
        sd_view = MappingProxyType(sd_dict)

        def _apply_result(_sd_proxy, result):
            # _sd_proxy is the read-only view; we mutate sd_dict via closure
            if isinstance(result, SDResult):
                for col, kv in result.sd_updates.items():
                    sd_dict.setdefault(col, {}).update(kv)
                return result.df
            return result

        extra_env = {'df': df_copy, 'sd': sd_view, 'apply-result!': _apply_result}
        ret_df = buckaroo_eval(instructions, extra_env)
        return ret_df, sd_dict

    convert_to_python, __unused = make_interpreter(to_py_lisp_primitives)
    def buckaroo_to_py(instructions):
        # sd is bound as a placeholder dict so transform_to_py for sd-aware
        # commands doesn't trip on the env lookup. Authors emit whatever
        # standalone-Python equivalent they want (typically df-only).
        individual_instructions = [x for x in map(
            lambda x: convert_to_python(x, {'df': 5, 'sd': {}}), instructions)]
        code_block = '\n'.join(individual_instructions)
        return "def clean(df):\n" + code_block + "\n    return df"
    return command_defaults, command_patterns, buckaroo_transform, buckaroo_to_py
