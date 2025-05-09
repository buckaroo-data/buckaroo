import marimo

__generated_with = "0.12.8"
app = marimo.App(width="medium")


@app.cell
def _():
    import traceback
    import sys
    import io
    return io, sys, traceback


@app.cell
def _(sys):
    class MarimoRuntimeException2(BaseException):
        """Wrapper for all marimo runtime exceptions."""

    def d():
        5/0

    def c():
        d()
    def b_calls_c():
        print("start of b_calls_c")
        try:    
            c()
    #    except Exception as e:
    #        raise UserFuncException(original_exception=e)
        except (BaseException, Exception) as e:
            print("intercepted")
            sys.stdout.write("intercepted stdout")

            sys.stderr.write("intercepted stderr")
            # Raising from a BaseException will fold in the stacktrace prior
            # to execution
            raise MarimoRuntimeException2 from e

    def internal_layer1():
        internal_layer2()
    
    def internal_layer2():
        b_calls_c()
    return (
        MarimoRuntimeException2,
        b_calls_c,
        c,
        d,
        internal_layer1,
        internal_layer2,
    )


@app.cell
def _(ErrorObjects, Optional, c, io, sys, traceback):
    class UserFuncExceptionTB(Exception):
        pass

    def wrap_tb():
        print("start of wrap2")
        try:    
            c()
        except Exception as e:
            print("intercepted")
            tb = sys.exception().__traceback__
            raise UserFuncExceptionTB(e).with_traceback(tb)
    #with_traceback is recommended in python docs https://docs.python.org/3/library/exceptions.html#BaseException.with_traceback

    def internal_layer1_tb():
        internal_layer2_tb()
    
    def internal_layer2_tb():
        wrap_tb()

    saved_e = []
    def handle_traceback_tb():
        try:
            internal_layer1_tb()
        except UserFuncExceptionTB as e:
            print("here")
            saved_e.append(e)
            unwrapped_exception: Optional[BaseException] = e.__cause__
            exception: Optional[ErrorObjects] = unwrapped_exception

            tmpio = io.StringIO()
            # The executors explicitly raise cell exceptions from base
            # exceptions such that the stack trace is cleaner.
            # Verbosity is for Python < 3.10 compat
            # See https://docs.python.org/3/library/traceback.html
            exception_type = (
                type(unwrapped_exception) if unwrapped_exception else None
            )
            maybe_traceback = (
                unwrapped_exception.__traceback__
                if unwrapped_exception
                else None
            )
            print("maybe_traceback", maybe_traceback)
            traceback.print_exception(
                exception_type,
                unwrapped_exception,
                maybe_traceback,
                file=tmpio,
            )
            tmpio.seek(0)
            sys.stderr.write(tmpio.read())
        except Exception as e:
            print("other exception", e)
    handle_traceback_tb()

    return (
        UserFuncExceptionTB,
        handle_traceback_tb,
        internal_layer1_tb,
        internal_layer2_tb,
        saved_e,
        wrap_tb,
    )


@app.cell
def _(saved_e):
    ab = saved_e[0]
    ab.args
    return (ab,)


@app.cell
def _(ab):
    dir(ab.__traceback__)
    return


@app.cell
def _(ab):
    dir(ab.__traceback__.tb_frame)
    return


@app.cell
def _(ab):
    _tb = ab.__traceback__
    _tbf = _tb.tb_frame
    #_tb.tb_lasti, _tbf.f_code
    _tbf.f_trace_lines
    return


@app.cell
def _():
    return


@app.cell
def _():
    return


@app.cell
def _(b_calls_c):
    b_calls_c()
    return


@app.cell
def _(saved_e):
    saved_e
    return


@app.cell
def _(
    ErrorObjects,
    MarimoRuntimeException2,
    Optional,
    internal_layer1,
    io,
    sys,
    traceback,
):
    def handle_traceback2():
        try:
            internal_layer1()
        except MarimoRuntimeException2 as e:
            print("here")
            unwrapped_exception: Optional[BaseException] = e.__cause__
            exception: Optional[ErrorObjects] = unwrapped_exception

            tmpio = io.StringIO()
            # The executors explicitly raise cell exceptions from base
            # exceptions such that the stack trace is cleaner.
            # Verbosity is for Python < 3.10 compat
            # See https://docs.python.org/3/library/traceback.html
            exception_type = (
                type(unwrapped_exception) if unwrapped_exception else None
            )
            maybe_traceback = (
                unwrapped_exception.__traceback__
                if unwrapped_exception
                else None
            )
            print("maybe_traceback", maybe_traceback)
            traceback.print_exception(
                exception_type,
                unwrapped_exception,
                maybe_traceback,
                file=tmpio,
            )
            tmpio.seek(0)
            sys.stderr.write(tmpio.read())
        except Exception as e:
            print("other exception", e)
    handle_traceback2()
    #I only want the stack trace to show from b_calls_c down, it shouldn't include internal_layer1 or internal_layer2
    return (handle_traceback2,)


app._unparsable_cell(
    r"""
    fdef unstructured_traceback():
        internal_layer1()
    unstructured_traceback()
    """,
    name="_"
)


@app.cell
def _(UserFuncException, internal_layer1):
    def handle_traceback():
        try:
            internal_layer1()
        except UserFuncException as e:
            raise e.original_exception
    #handle_traceback()
    return (handle_traceback,)


@app.cell
def _(c):
    c()
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
