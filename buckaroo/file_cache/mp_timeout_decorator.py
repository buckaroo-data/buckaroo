import multiprocessing
from typing import Any
import cloudpickle as _cloudpickle  # type: ignore

"""
mp_timeout is based on cloudpickle and joblib.  Joblib had a lot of extra logic that wasn't necessary for this application
  """

class TimeoutException(Exception):
    """
      thrown when function was still executing normally, just hadn't completed in the alotted timeout
      """
    pass

class ExecutionFailed(Exception):
    """
      thrown when execution fails for some reason (system exit, crash)
      
      """
    pass

def _execute_and_report(func_bytes, args_bytes, queue) -> None:
    """Run func(*args, **kwargs) in a child process and report the outcome.

    Puts a tuple (status, payload) into the queue:
    - ("ok", result) on success
    - ("error", None) on any exception
    """
    # Resolve the function from cloudpickle bytes
    try:
        fn = _cloudpickle.loads(func_bytes)
    except Exception:
        try:
            queue.put(("error", None))
        except Exception:
            pass
        return

    try:
        # Unpack arguments (args, kwargs) that were cloudpickled in the parent.
        ua, ukw = _cloudpickle.loads(args_bytes)
        # Heuristic: import any referenced name that resolves to an importable module
        try:
            code_obj = getattr(fn, "__code__", None)
            referenced_names = set(code_obj.co_names) if code_obj else set()
            fn_globals = getattr(fn, "__globals__", {})
            import importlib.util as _ilu  # type: ignore
            import importlib as _il  # type: ignore
            for _name in referenced_names:
                if _name in fn_globals:
                    continue
                try:
                    _spec = _ilu.find_spec(_name)
                except Exception:
                    _spec = None
                if _spec is None:
                    continue
                try:
                    _mod = _il.import_module(_name)
                    fn_globals[_name] = _mod
                except Exception:
                    pass
        except Exception:
            pass
        result = fn(*ua, **ukw)
    except SystemExit:
        try:
            queue.put(("system_exit", None))
        except Exception:
            pass
        return
    except BaseException as e:
        try:
            exc_bytes = _cloudpickle.dumps(e)
            queue.put(("exception", exc_bytes))
        except Exception:
            try:
                queue.put(("exception", None))
            except Exception:
                pass
        return
    try:
        queue.put(("ok", result))
    except Exception:
        # Result not serializable or queue broken
        try:
            queue.put(("error", None))
        except Exception:
            pass

def _execute_and_report_fork(func, args, kwargs, queue) -> None:
    """
    Fork-only path: avoid pickling func/args; call directly in child process and
    communicate back via a queue.
    """
    try:
        result = func(*args, **kwargs)
    except SystemExit:
        try:
            queue.put(("system_exit", None))
        except Exception:
            pass
        return
    except BaseException as e:
        try:
            exc_bytes = _cloudpickle.dumps(e)
            queue.put(("exception", exc_bytes))
        except Exception:
            try:
                queue.put(("exception", None))
            except Exception:
                pass
        return
    try:
        queue.put(("ok", result))
    except Exception:
        try:
            queue.put(("error", None))
        except Exception:
            pass

ctx = multiprocessing.get_context("forkserver")
#ctx = multiprocessing.get_context("fork")
#ctx = multiprocessing.get_context("spawn")
def mp_timeout(timeout_secs: float):

    def inner_timeout(f):
        # Generic rule: if the worker does not deliver a result within the deadline and
        # is still running, raise TimeoutException. If the worker exits without delivering
        # a result (non-zero exit or dies before queue message), raise ExecutionFailed.
        def actual_func(*args, **kwargs):
            result_queue = ctx.Queue(maxsize=1)
            use_fork_path = ctx.get_start_method() == "fork"
            if use_fork_path:
                process = ctx.Process(
                    target=_execute_and_report_fork,
                    args=(f, args, kwargs, result_queue),
                    daemon=True,
                )
            else:
                func_bytes = _cloudpickle.dumps(f)
                args_bytes = _cloudpickle.dumps((args, kwargs))
                process = ctx.Process(
                    target=_execute_and_report,
                    args=(func_bytes, args_bytes, result_queue),
                    daemon=True,
                )
            process.start()

            status: Any = None
            payload: Any = None
            try:
                status, payload = result_queue.get(timeout=timeout_secs)
            except Exception:
                # No message received within timeout.
                # If the process is still alive, it's a timeout.
                if process.is_alive():
                    process.terminate()
                    process.join(0.25)
                    raise TimeoutException("Timeout fail")
                # Process already exited: treat as execution failure (likely crash)
                process.join(0.25)
                raise ExecutionFailed("Execution failed in worker")

            # Child reported a result or an error; ensure child exits
            process.join(0.25)
            exit_code = process.exitcode

            if exit_code not in (0, None):
                raise ExecutionFailed("Execution failed in worker")
            if status == "ok":
                return payload
            if status == "exception" and payload is not None:
                try:
                    exc = _cloudpickle.loads(payload)
                except Exception:
                    raise ExecutionFailed("Execution failed in worker")
                raise exc
            if status == "system_exit":
                raise ExecutionFailed("Execution failed in worker")
            # Any other error status
            raise ExecutionFailed("Execution failed in worker")

        return actual_func

    return inner_timeout

