from abc import ABC, abstractmethod

from datetime import datetime as dtdt, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any, Optional, TypeAlias, Callable, Dict, Literal,
    Generic, TypeVar)
import polars as pl
import itertools

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


def flatten(*lists):
    list(itertools.chain(*lists))
    
class FileCache:
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


@dataclass
class ExecutorLogEvent:

    dfi: DFIdentifier
    args: ExecutorArgs
    start_time: dtdt
    end_time: Optional[dtdt]
    completed: bool
    

class ExecutorLog(ABC):

    @abstractmethod
    def log_start_col_group(self, dfi: DFIdentifier, args:ExecutorArgs) -> None:
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

class SimpleExecutorLog(ExecutorLog):


    
    def __init__(self) -> None:
        self._events: list[ExecutorLogEvent] = []


    def log_start_col_group(self, dfi: DFIdentifier, args:ExecutorArgs) -> None:
        #what happens if we try to start the same dfi, args twice???
        ev = ExecutorLogEvent(
            dfi=dfi,
            args=args,
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

    def get_log_events(self) -> list[ExecutorLogEvent]:
        """
          get the logged events
          """
        return self._events


class Executor:

    def __init__(self,
        ldf:pl.LazyFrame, column_executor:ColumnExecutor,
        listener:ProgressListener, fc:FileCache,
        executor_log: ExecutorLog | None = None) -> None:
        self.ldf = ldf
        self.column_executor = column_executor
        self.listener = listener
        self.fc = fc
        self.executor_log = executor_log or SimpleExecutorLog()

        self.dfi = (id(self.ldf),"",)

    def run(self) -> None:

        #had_failure = False
        last_ex_args: ExecutorArgs | None = None

        for col_group in self.get_column_chunks():
            ex_args = self.get_executor_args(col_group)
            last_ex_args = ex_args
            if self.executor_log.check_log_for_previous_failure(self.dfi, ex_args):
                return # not sure what to do here or what progress notification to send back
            
            self.executor_log.log_start_col_group(self.dfi, ex_args)
            t1 = now()

            try:
                res = self.column_executor.execute(self.ldf, ex_args)
                t2 = now()
                notification = ProgressNotification(
                    success=True,
                    col_group=col_group,
                    execution_args=[], #FIXME
                    result=res,
                    execution_time=t2-t1,
                    failure_message=None)

                for col, col_result in res.items():
                    self.fc.upsert_key(col_result.series_hash, col_result.result)

                self.listener(notification)
                self.executor_log.log_end_col_group(self.dfi, last_ex_args)    
            except Exception as e:
                t3 = now()
                notification = ProgressNotification(
                    success=False,
                    col_group=col_group,
                    execution_args=[], #FIXME
                    result=None,
                    execution_time=t3-t1,
                    failure_message=str(e))
                self.listener(notification)
                #had_failure = True
                # continue to next column group without marking completion
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
    


    def get_column_chunks(self) -> list[ColumnGroup]:
        """
          dumb impl
          """
        return [[column] for column in self.ldf.columns]

    
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
