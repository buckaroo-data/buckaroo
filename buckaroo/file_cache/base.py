from abc import ABC, abstractmethod

from datetime import datetime as dtdt, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any, Optional, TypeAlias, Callable, Dict, Literal,
    Generic, TypeVar, Union)
import logging
import polars as pl
import itertools

from .batch_planning import (
    PlanningFunction, PlanningContext, extract_execution_history,
    simple_one_column_planning
)

now = dtdt.now


SummaryStats:TypeAlias = dict[str, Any]

SimpleBufferKey:TypeAlias = tuple[int, int, int]

#ComplexBufferKey:TypeAlias = tuple[SimpleBufferKey, SimpleBufferKey, SimpleBufferKey]
# I don't know why the above line causes errors but the below key works
BufferKey:TypeAlias = tuple[SimpleBufferKey, ...]
                                          #mtime
FileDFIdentifier: TypeAlias = tuple[Path, int]
                                    #id of dataframe, joined string of all columns
MemoryDFIdentifer:TypeAlias = tuple[int, str]
DFIdentifier: TypeAlias = FileDFIdentifier | MemoryDFIdentifer

# File path type aliases
MaybeFilepathLike: TypeAlias = Union[str, Path, None]
MaybeFilepath: TypeAlias = Optional[Path]


def ensure_filepath(file_path: MaybeFilepathLike) -> MaybeFilepath:
    """
    Normalize a file path to Path | None.
    
    Args:
        file_path: A string, Path, or None
        
    Returns:
        Path if file_path is str or Path, None if file_path is None
    """
    if file_path is None:
        return None
    if isinstance(file_path, (str, Path)):
        return Path(file_path)
    raise TypeError(f"file_path must be str, Path, or None, got {type(file_path)}")


def flatten(*lists):
    list(itertools.chain(*lists))
    
class AbstractFileCache(ABC):
    """
    Abstract interface for a file/series cache.
    Concrete implementations include an in-memory cache (MemoryFileCache)
    and a SQLite-backed cache (SQLiteFileCache).
    """
    @abstractmethod
    def add_file(self, path:Path, metadata:dict[str, Any]) -> None: ...

    @abstractmethod
    def add_metadata(self, path:Path, metadata:dict[str, Any]) -> None: ...

    @abstractmethod
    def check_file(self, path:Path) -> bool: ...

    @abstractmethod
    def get_file_metadata(self, path:Path) -> Optional[dict[str, Any]]: ...

    @abstractmethod
    def upsert_file_metadata(self, path:Path, extra_metadata:dict[str, Any]) -> None: ...

    @abstractmethod
    def upsert_key(self, series_hash:int, result:SummaryStats) -> None: ...

    @abstractmethod
    def get_series_results(self, series_hash:int) -> SummaryStats|None: ...

    # New: file-level series hash helpers
    @abstractmethod
    def get_file_series_hashes(self, path: Path) -> Optional[dict[str, int]]: ...

    @abstractmethod
    def upsert_file_series_hashes(self, path: Path, hashes: dict[str, int]) -> None: ...


class MemoryFileCache(AbstractFileCache):
    """
      acutally as written this is more like an in memory cache
      """
    def __init__(self) -> None:
        self.file_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self.summary_stats_cache: dict[int, Any] = {}
        self.series_hash_cache: dict[BufferKey, int] = {}
        
    def add_file(self, path:Path, metadata:dict[str, Any]) -> None:
        """
        Record a file's current mtime along with provided metadata.
        """
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            # If file does not exist, do not add to cache
            return
        self.file_cache[str(path)] = (mtime, dict(metadata))

    # Compatibility with tests expecting add_metadata/get_file_metadata/upsert_file_metadata
    def add_metadata(self, path:Path, metadata:dict[str, Any]) -> None:
        self.add_file(path, metadata)

    def check_file(self, path:Path) -> bool :
        """
          is this path in the cache
          is the mtime of this file before the mtime in the cache for this file
          """
        key = str(path)
        if key not in self.file_cache:
            return False
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            # If file is gone, consider cache invalid
            return False
        cached_mtime, _ = self.file_cache[key]
        # Valid only if the file has not been modified since it was cached
        return current_mtime <= cached_mtime

    def get_hashes(self, path:Path):
        """
          return the hashes for this file if available

          hashes only or maybe hashes and column names???
          """
        # Placeholder: not used by current tests
        return None

    def get_file_metadata(self, path:Path) -> Optional[dict[str, Any]]:
        key = str(path)
        entry = self.file_cache.get(key)
        if entry is None:
            return None
        _, metadata = entry
        return metadata

    def upsert_file_metadata(self, path:Path, extra_metadata:dict[str, Any]) -> None:
        key = str(path)
        try:
            current_mtime = path.stat().st_mtime
        except FileNotFoundError:
            return
        if key in self.file_cache:
            _, existing_md = self.file_cache[key]
            merged_md: dict[str, Any] = dict(existing_md)
            merged_md.update(extra_metadata)
            # Update mtime to current file mtime to reflect current file state
            self.file_cache[key] = (current_mtime, merged_md)
        else:
            # If not present, behave like add_file with provided metadata
            self.file_cache[key] = (current_mtime, dict(extra_metadata))
    
    def upsert_key(self, series_hash:int, result:SummaryStats) -> None:
        existing_result = self.summary_stats_cache.get(series_hash, {})
        existing_result.update(result)
        self.summary_stats_cache[series_hash] = existing_result

    def get_series_results(self, series_hash:int) -> SummaryStats|None:
        return self.summary_stats_cache.get(series_hash, None)

    def get_file_series_hashes(self, path: Path) -> Optional[dict[str, int]]:
        md = self.get_file_metadata(path)
        if not md:
            return None
        hashes = md.get('series_hashes')
        return {str(k): int(v) for k, v in hashes.items()}

    def upsert_file_series_hashes(self, path: Path, hashes: dict[str, int]) -> None:
        md = self.get_file_metadata(path) or {}
        cur = dict(md.get('series_hashes') or {})
        cur.update({str(k): int(v) for k, v in hashes.items()})
        merged = dict(md)
        merged['series_hashes'] = cur
        self.upsert_file_metadata(path, merged)
    def _get_buffer_key(self, series:pl.Series) -> BufferKey:
        """

          This kind of works.  We want dataframe and series level metadata
          https://github.com/pola-rs/polars/issues/5117
          these aren't implemented yet
          """

        buffers = series._get_buffers()
        def get_buffer_info(k:Literal["validity"]|Literal["offsets"]) -> SimpleBufferKey:
            if k in buffers and buffers[k] is not None:
                return buffers[k]._get_buffer_info() #type:ignore
            return (0,0,0,)
        validity: SimpleBufferKey = get_buffer_info('validity')
        offsets:SimpleBufferKey = get_buffer_info('offsets')
        values = buffers['values']._get_buffer_info()
        
        # assert isinstance(values, tuple)
        # assert len(values) == 3
        # assert isinstance(validity, tuple)
        # assert len(validity) == 3
        # assert isinstance(offsets, tuple)
        # assert len(offsets) == 3

        return tuple([values, validity, offsets])
    
    def check_series(self, series:pl.Series) -> bool:
        """
        Do we have a series_hash for this series (based on it's memory address)  

          """
        key = self._get_buffer_key(series)
        #existing = list(self.series_hash_cache.keys())
        #print("key", key, "existing", existing, "in", key in existing)
        return key in self.series_hash_cache

    def add_series(self, series:pl.Series, col=None) -> None:
        """
          make sure that the hash for this in memory series is put in the local hash cache

          we can't attach metadata to a series, but we can track the series by memory location
          """
        # if col:
        #     print("add col", col, self._get_buffer_key(series))
        if not self.check_series(series):
            buffer_info = self._get_buffer_key(series)
            df = pl.DataFrame({'a':series})
            res = df.select(pl.col('a').pl_series_hash.hash_xx()) # type: ignore
            self.series_hash_cache[buffer_info] = res['a'][0]

    def add_df(self, df:pl.DataFrame) -> None:
        for col in df.columns:
            self.add_series(df[col], col)
        
# Backwards-compat alias for existing imports/tests
FileCache = MemoryFileCache

        
class AnnotatedFile:

    def get_metadata(self):

        """
          mtime at least
          maybe column list
          maybe hashes for columns
          """
        pass
    


# call PlugableAnalysisFramework2 TypedAnalysisDAG    
class PAF2:
    """
      Plugable analys framework 2

      figures out provides/requires from type hints.  DataClasses or type hints used

      add a function decorator for defaults provided in case of function failure

      add a function decorator for defaults required in case of upstream failure

      """
    pass





ColumnGroup:TypeAlias = list[str]

@dataclass
class ProgressNotification:
    # how do we get a failure notification when it results in a crash?
    success: bool
    col_group:ColumnGroup
    execution_args: Any
    result: Any
    #execution_time: int # millisecones?
    execution_time: timedelta
    failure_message: str|None

    def __eq__(self, other):
        props = [self.success == other.success,
                 tuple(self.col_group) == tuple(other.col_group),
                 self.execution_args == other.execution_args,
                 self.result == other.result,
                 self.failure_message == other.failure_message]
        return all(props)
            

ProgressListener:TypeAlias = Callable[[ProgressNotification], None]

ColumnRawResults:TypeAlias = Dict[str, Any]

@dataclass
class ColumnResult:
    series_hash: int #u64 actually
    column_name: str # strictly necessary?
    expressions: list[pl.Expr]
    # I want expressions in plass of execution_args
    # expression names are fine for expressions,  everything else should fall to theColAnalyis class name
    
    result: ColumnRawResults

ColumnResults:TypeAlias = Dict[str, ColumnResult]    
ColumnHashes:TypeAlias = Dict[str, int]

ColumnFunc:TypeAlias = Callable[[pl.LazyFrame, ColumnGroup], ColumnResults]



E = TypeVar('E')

class ColumnExecutor(Generic[E], ABC):

    @abstractmethod
    def get_execution_args(self, existing_stats:dict[str,SummaryStats]) -> E:
        """
          Return execution arguments computed from existing stats.
          """
        ...

    @abstractmethod
    def execute(self, ldf:pl.LazyFrame, execution_args:E) -> ColumnResults:
        """this should generally be a prety simple wrapper around ldf.select/collect
          it can be overriden for testing to throw different errors,

          particularly FatalStop which causes no log to be written.
          That is useful for testing without crashing the python
          process

        """
        ...

@dataclass
class ExecutorArgs:
    columns: ColumnGroup

    #does this expression set include pl.col calls or is it all
    #selectors pl.col calls come up when ColumnExecutor was trying to
    #work around differently cached columns
    column_specific_expressions: bool
    #maybe when column_specific_expressions is false
    #a column group should be included... a union
    

    # do we need to compute hashes for the columns
    include_hash: bool
    expressions: list[pl.Expr]
    row_start: int|None
    row_end: int|None
    extra: Any
    # If True, skip execution - all columns are already cached with complete stats
    no_exec: bool = False


@dataclass
class ExecutorLogEvent:

    dfi: DFIdentifier
    args: ExecutorArgs
    start_time: dtdt
    end_time: Optional[dtdt]
    completed: bool
    executor_class_name: str = ""
    

class ExecutorLog(ABC):

    @abstractmethod
    def log_start_col_group(self, dfi: DFIdentifier, args:ExecutorArgs, executor_class_name:str = "") -> None:
        """
          used so we know that we started execution of a col_group even if it crashes
          """
        ...

    @abstractmethod
    def log_end_col_group(self, dfi: DFIdentifier, args:ExecutorArgs) -> None:
        """
          used so we know that execution finished, Maybe include status
          """
        ...

    @abstractmethod
    def check_log_for_previous_failure(self, dfi: DFIdentifier, args:ExecutorArgs) -> bool:
        """
          check the log for this lazy_dataframe, this set of columns, and this set of column_args
          did it start and not finish, if so, return false
          
          """
        ...

    @abstractmethod
    def get_log_events(self) -> list[ExecutorLogEvent]:
        """
          Get the logged events for this executor.
          """
        ...

    def find_event(self, dfi: DFIdentifier, args: ExecutorArgs) -> Optional[ExecutorLogEvent]:
        """
        Locate the log event for the given dataframe identifier and execution args.
        Matches args by identity to avoid issues comparing polars expressions.
        """
        try:
            events = self.get_log_events()
        except Exception:
            return None
        for ev in events:
            if ev.dfi == dfi and ev.args is args:
                return ev
        return None
    
    def check_log_for_completed(self, dfi: DFIdentifier, args: ExecutorArgs) -> bool:
        """
        Check if this column group was already completed successfully.
        Returns True if there is a completed event with matching args.
        This can be used to skip re-execution of work that's already been done.
        """
        ev = self.find_event(dfi, args)
        if ev:
            return ev.completed
        return False

class SimpleExecutorLog(ExecutorLog):


    
    def __init__(self) -> None:
        self._events: list[ExecutorLogEvent] = []


    def log_start_col_group(self, dfi: DFIdentifier, args:ExecutorArgs, executor_class_name:str = "") -> None:
        #what happens if we try to start the same dfi, args twice???
        ev = ExecutorLogEvent(
            dfi=dfi,
            args=args,
            executor_class_name=executor_class_name,
            completed=False,
            start_time=dtdt.now(),
            end_time=None)
        self._events.append(ev)

    def log_end_col_group(self, dfi: DFIdentifier, args:ExecutorArgs) -> None:
        # Mark the aggregated event as completed when the first column group finishes
        ev = self.find_event(dfi, args)
        if ev:
            ev.end_time = dtdt.now()
            ev.completed = True

        
    def check_log_for_previous_failure(self, dfi: DFIdentifier, args:ExecutorArgs) -> bool:
        # Return True if there is an incomplete event with matching args
        ev = self.find_event(dfi, args)
        if ev:
            return not ev.completed
        return False
    
    def check_log_for_completed(self, dfi: DFIdentifier, args:ExecutorArgs) -> bool:
        """
        Check if this column group was already completed successfully.
        Returns True if there is a completed event with matching args.
        This can be used to skip re-execution of work that's already been done.
        """
        ev = self.find_event(dfi, args)
        if ev:
            return ev.completed
        return False

    def get_log_events(self) -> list[ExecutorLogEvent]:
        """
          get the logged events
          """
        return self._events

    def has_incomplete_for_executor(self, dfi:DFIdentifier, executor_class_name:str) -> bool:
        for ev in self._events:
            if ev.dfi == dfi and ev.executor_class_name == executor_class_name and not ev.completed:
                return True
        return False


class Executor:

    def __init__(self,
        ldf:pl.LazyFrame, column_executor:ColumnExecutor,
        listener:ProgressListener, fc:AbstractFileCache,
        executor_log: ExecutorLog | None = None,
        file_path: MaybeFilepathLike = None,
        cached_merged_sd: dict[str, dict[str, Any]] | None = None,
        orig_to_rw_map: dict[str, str] | None = None,
        planning_function: Optional[PlanningFunction] = None) -> None:
        self.ldf = ldf
        self.column_executor = column_executor
        self.listener = listener
        self.fc = fc
        self.executor_log = executor_log or SimpleExecutorLog()

        self.file_path: MaybeFilepath = ensure_filepath(file_path)

        self.dfi = (id(self.ldf), str(self.file_path) if self.file_path else "",)
        self.executor_class_name = self.__class__.__name__
        
        # Store cached merged_sd and mapping for checking complete columns
        self.cached_merged_sd = cached_merged_sd or {}
        self.orig_to_rw_map = orig_to_rw_map or {}
        
        # Batch planning
        self.planning_function = planning_function or simple_one_column_planning
        self._planning_state: Optional[dict[str, Any]] = None
        
        # Track if run() has been called (for testing utilities)
        self.has_run_been_called = False

    def run(self) -> None:
        """Execute column analysis, skipping cached columns.
        
        Uses get_next_column_chunk() to get batches one at a time until all columns
        are processed or there's no way to proceed (e.g., single column timeout).
        """
        self.has_run_been_called = True
        logger = logging.getLogger("buckaroo.executor")
        
        logger.info(f"Executor.run() START - file_path={self.file_path}")
        logger.debug(f"  cached_merged_sd keys: {list(self.cached_merged_sd.keys()) if self.cached_merged_sd else []}")
        
        # Keep calling get_next_column_chunk() until it returns None
        while True:
            col_group = self.get_next_column_chunk()
            if col_group is None:
                break
            
            # Build existing stats by consulting file cache using per-file series hashes
            file_hashes: dict[str, int] = {}
            if self.file_path and self.fc.check_file(self.file_path):
                fh = self.fc.get_file_series_hashes(self.file_path) or {}
                file_hashes = {str(k): int(v) for k, v in fh.items()}

            # Build existing_cached dict with ALL columns in the group
            existing_cached: dict[str, Any] = {}
            missing_hash_columns: list[str] = []
            for col in col_group:
                h = file_hashes.get(col)
                if h:
                    cached_results = self.fc.get_series_results(h)
                    existing_cached[col] = cached_results or {}
                else:
                    existing_cached[col] = {'__missing_hash__': True}
                    missing_hash_columns.append(col)
            
            # Get execution args - ColumnExecutor already filtered out cached columns
            ex_args = self.column_executor.get_execution_args(existing_cached)
            
            # Check if original column group was already completed in executor log
            original_group_args = ExecutorArgs(
                columns=list(col_group),
                column_specific_expressions=ex_args.column_specific_expressions,
                include_hash=ex_args.include_hash,
                expressions=ex_args.expressions,
                row_start=ex_args.row_start,
                row_end=ex_args.row_end,
                extra=ex_args.extra,
                no_exec=False
            )
            
            if self.executor_log.check_log_for_completed(self.dfi, original_group_args):
                logger.info(f"Executor.run() SKIPPING group {col_group} - already completed (found in executor log)")
                # Update planning state to mark these columns as done
                self._update_planning_state_after_execution(list(col_group))
                continue
            
            # If no columns need execution (all were filtered out), skip this column group
            if not ex_args.columns:
                logger.debug(f"  Skipping column group {col_group} - all columns cached")
                # Update planning state
                self._update_planning_state_after_execution(list(col_group))
                continue
            
            logger.info(f"Executor.run() EXECUTING group {col_group} with {len(ex_args.columns)} columns: {ex_args.columns}")
            # annotate args with missing-hash info so executors can act accordingly
            extra_map: dict[str, Any] = dict(ex_args.extra) if isinstance(ex_args.extra, dict) else {}
            extra_map['missing_hash_columns'] = list(missing_hash_columns)
            if self.file_path:
                extra_map['file_path'] = str(self.file_path)
            ex_args.extra = extra_map

            if self.executor_log.check_log_for_previous_failure(self.dfi, ex_args):
                # Halt execution immediately on previous failure to make cache write failures very obvious.
                # Note: This means subsequent column groups that haven't failed won't be processed.
                # If writing to the cache fails here, there could still be valid column groups that
                # aren't written to the cache that could succeed, but we intentionally fail fast.
                # TODO: Consider running bisectors here to diagnose failures, especially for MultiprocessingExecutor
                return
            
            self.executor_log.log_start_col_group(self.dfi, ex_args, self.executor_class_name)
            t1 = now()

            try:
                res = self.column_executor.execute(self.ldf, ex_args)
                t2 = now()
                notification = ProgressNotification(
                    success=True,
                    col_group=col_group,
                    execution_args=ex_args,
                    result=res,
                    execution_time=t2-t1,
                    failure_message=None)

                executed_columns = []
                for col, col_result in res.items():
                    self.fc.upsert_key(col_result.series_hash, col_result.result)
                    executed_columns.append(col)
                    # cache insert errors should be really rare, if we get here, something weird has happened and trying to defensivly code around it is a fools errand

                # If file hashes were missing and we have a file path, persist newly discovered hashes
                # Skip spurious 0 hashes (default value when hash can't be computed)
                if self.file_path and missing_hash_columns:
                    new_hashes: dict[str, int] = {}
                    for c in missing_hash_columns:
                        if c in res and res[c].series_hash is not None and res[c].series_hash != 0:
                            new_hashes[c] = int(res[c].series_hash)
                    if new_hashes:
                        self.fc.upsert_file_series_hashes(self.file_path, new_hashes)

                self.listener(notification)
                self.executor_log.log_end_col_group(self.dfi, ex_args)
                
                # Update planning state after successful execution
                self._update_planning_state_after_execution(executed_columns)
                
            except Exception as e:
                t3 = now()
                notification = ProgressNotification(
                    success=False,
                    col_group=col_group,
                    execution_args=ex_args,
                    result=None,
                    execution_time=t3-t1,
                    failure_message=str(e))
                self.listener(notification)
                # Update planning state to prevent infinite loop
                # Remove columns from remaining even on failure to avoid retrying forever
                # Note: This means we won't retry failed columns, but prevents infinite loops
                # Future: Could track failures and allow limited retries
                self._update_planning_state_after_execution(list(col_group))
                continue

                
    def get_column_raw_results(self, columns:ColumnGroup) -> ColumnRawResults:
        hashes_for_cols: dict[str,int]= {} # how are we getting the hashes for this ldf?

        existing_cached = {}
        for col in columns:
            hash_ = hashes_for_cols.get(col)
            if hash_:
                existing_cached[col] = self.fc.get_series_results(hash_) or {}
            else:
                existing_cached[col] = {}
        return existing_cached

    def get_executor_args(self, columns:ColumnGroup) -> ExecutorArgs:
        existing_cached = self.get_column_raw_results(columns)
        args = self.column_executor.get_execution_args(existing_cached)
        return args
    


    def get_next_column_chunk(self) -> Optional[ColumnGroup]:
        """
        Get next column chunk using batch planning.
        
        Returns None when all columns are processed or there's no way to proceed.
        This allows other code (like bisectors) to be called between chunks.
        
        Uses planning_function to determine next batch. Default is simple_one_column_planning
        which returns one column at a time (backward compatible).
        """
        logger = logging.getLogger("buckaroo.executor")
        if self._planning_state is None:
            # Initialize planning state
            all_columns = list(self.ldf.collect_schema().names())
            log_msg_init = f"Executor.get_next_column_chunk() INITIALIZING planning state - executor_id={id(self)}, all_columns={all_columns}, count={len(all_columns)}"
            logger.info(log_msg_init)
            self._planning_state = {
                'all_columns': all_columns,
                'remaining': all_columns.copy(),
                'baseline_overhead': timedelta(0),
                'current_batches': [],
                'batch_index': 0,
                'last_returned_group': None,  # Track last returned to detect infinite loops
                'consecutive_same_returns': 0,  # Count consecutive same returns
            }
        
        # Use iteration instead of recursion to avoid stack overflow
        state = self._planning_state
        max_iterations = 100 + len(state['all_columns'])
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            state = self._planning_state
            
            log_msg_iter = f"Executor.get_next_column_chunk() ITERATION {iteration} - executor_id={id(self)}, remaining={len(state.get('remaining', []))}, current_batches={len(state.get('current_batches', []))}, batch_index={state.get('batch_index', 0)}"
            logger.debug(log_msg_iter)
            
            # If we have batches queued, return next one
            if state['current_batches'] and state['batch_index'] < len(state['current_batches']):
                batch = state['current_batches'][state['batch_index']]
                state['batch_index'] += 1
                if batch.columns:
                    group = batch.columns
                    log_msg_batch = f"Executor.get_next_column_chunk() RETURNING queued batch - executor_id={id(self)}, group={group}, batch_index={state['batch_index']-1}"
                    logger.info(log_msg_batch)
                    # Check for infinite loop: same group returned consecutively
                    if group == state.get('last_returned_group'):
                        state['consecutive_same_returns'] = state.get('consecutive_same_returns', 0) + 1
                        if state['consecutive_same_returns'] > 3:
                            log_msg_loop = f"Executor.get_next_column_chunk() INFINITE LOOP DETECTED - executor_id={id(self)}, group={group}, removing from remaining"
                            logger.warning(log_msg_loop)
                            # Infinite loop detected - remove columns from remaining and return None
                            for col in group:
                                if col in state['remaining']:
                                    state['remaining'].remove(col)
                            return None
                    else:
                        state['consecutive_same_returns'] = 0
                    state['last_returned_group'] = group
                    return group
                # Empty batch - skip it (shouldn't happen with calibration, but handle gracefully)
                continue
            
            # Need to plan new batches
            if not state['remaining']:
                log_msg_no_remaining = f"Executor.get_next_column_chunk() NO REMAINING COLUMNS - executor_id={id(self)}, returning None"
                logger.info(log_msg_no_remaining)
                return None
            
            # Extract history from executor log
            log_msg_planning = f"Executor.get_next_column_chunk() CALLING PLANNING FUNCTION - executor_id={id(self)}, remaining={len(state['remaining'])}, planning_function={self.planning_function.__name__ if hasattr(self.planning_function, '__name__') else type(self.planning_function).__name__}"
            logger.info(log_msg_planning)
            
            history = extract_execution_history(self.executor_log, self.dfi)
            
            # Get timeout (default 30s, can be overridden by subclasses)
            timeout_secs = getattr(self, 'timeout_secs', 30.0)
            
            # Get baseline overhead from calibration (if not already set)
            if state['baseline_overhead'] == timedelta(0):
                from .mp_calibration import get_calibrated_overhead
                state['baseline_overhead'] = get_calibrated_overhead()
            
            # Create planning context
            context = PlanningContext(
                all_columns=state['all_columns'],
                baseline_overhead=state['baseline_overhead'],
                timeout_secs=timeout_secs,
                execution_history=history,
                remaining_columns=state['remaining']
            )
            
            # Plan next batches
            plan_result = self.planning_function(context)
            
            log_msg_plan_result = f"Executor.get_next_column_chunk() PLANNING RESULT - executor_id={id(self)}, phase={plan_result.phase}, batches={len(plan_result.batches)}, notes={plan_result.notes}"
            logger.info(log_msg_plan_result)
            
            if not plan_result.batches:
                # No more batches - done or error
                if plan_result.phase == "error":
                    log_msg_error = f"Executor.get_next_column_chunk() PLANNING ERROR - executor_id={id(self)}, returning None"
                    logger.warning(log_msg_error)
                    # Single column timed out - should trigger bisector
                    return None
                log_msg_no_batches = f"Executor.get_next_column_chunk() NO BATCHES - executor_id={id(self)}, returning None"
                logger.info(log_msg_no_batches)
                return None
            
            # Store batches and continue loop to return first
            state['current_batches'] = plan_result.batches
            state['batch_index'] = 0
            log_msg_batches_queued = f"Executor.get_next_column_chunk() BATCHES QUEUED - executor_id={id(self)}, count={len(plan_result.batches)}, continuing loop"
            logger.info(log_msg_batches_queued)
            # Continue loop to process first batch
        
        # Max iterations reached - safety fallback
        log_msg_max_iter = f"Executor.get_next_column_chunk() MAX ITERATIONS REACHED - executor_id={id(self)}, returning None"
        logger.warning(log_msg_max_iter)
        return None
    
    def _update_planning_state_after_execution(self, executed_columns: list[str]) -> None:
        """Update planning state after a batch is executed."""
        if self._planning_state:
            # Remove executed columns from remaining
            for col in executed_columns:
                if col in self._planning_state['remaining']:
                    self._planning_state['remaining'].remove(col)

    
# fc = FileCache()    

# def pseudo(fname:str) -> None:
#     fpath = Path(fname)
#     lazy_df = pl.scan_parquet(fpath)
#     if fc.check_file(Path(fname)):
#         summary_stats = fc.get_hashes(fpath)
#         #PolarsBuckaroo(lazy_df, summary_stats)
#     else:
#         #PolarsBuckarooTableOnly(lazy_df, None)
#         def listener(progress:ProgressNotification) -> None:
#             print(progress.success, progress.result)

#         exc = Executor(lazy_df, simple_column_func, listener, fc)
#         exc.run()
        
"""
Goals:
  be able to interogate the execution log and basically run git-bisect until you get to the minimal reproducable failure.

  this implementation is synchronous and simple


  """
def get_columns_from_args(ldf: pl.LazyFrame, args: ExecutorArgs) -> list[str]:
    """
    Compute the output column names produced by applying the given ExecutorArgs
    to the provided LazyFrame.

    This mirrors the execution flow used by ColumnExecutor implementations that
    first select the target columns, then apply the expressions.
    """
    only_cols = ldf.select(args.columns)
    res = only_cols.select(*args.expressions).collect()
    return list(res.columns)
