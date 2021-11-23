import asyncio
import ctypes
import inspect
import threading


def cdll_with_spec(lib_path, spec):
    """
    Open a shared library using ctypes.CDLL and apply the given spec class'
    type annotations to the argtypes and restype attributes of the shared
    library's functions.
    """

    # The given spec must be a class
    assert inspect.isclass(spec)

    # Find all methods that non-internal methods
    spec_funcs = (
        type_
        for name, type_ in inspect.getmembers(spec)
        if not name.startswith("__") and inspect.isfunction(type_)
    )

    # There has to be at least one function in the spec, or it's likely an error
    assert spec_funcs

    lib = ctypes.CDLL(lib_path)
    for spec_func in spec_funcs:
        # Inspect the signature of the spec function
        sig = inspect.signature(spec_func)

        # Apply the types to the lib's function
        lib_func = getattr(lib, spec_func.__name__)
        lib_func.argtypes = [p.annotation for p in sig.parameters.values()]
        if sig.return_annotation is not sig.empty:
            lib_func.restype = sig.return_annotation
        else:
            lib_func.restype = None
    return lib


class AsyncPythonFfi:
    def rust_sleep(delay_ms: ctypes.c_int) -> ctypes.c_int:
        ...


LIB = cdll_with_spec("./libasync_python_ffi.so", AsyncPythonFfi)


async def rust_sleep(delay_ms):
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def thread():
        r = LIB.rust_sleep(delay_ms)
        loop.call_soon_threadsafe(fut.set_result, r)
    t = threading.Thread(target=thread, daemon=True)
    t.start()

    return await fut


async def counter():
    for i in range(5):
        await asyncio.sleep(1)
        print(i + 1, "sheep")


async def ffi_sleep():
    print("Pre-sleep")
    await rust_sleep(5500)
    print("Post-sleep")


async def main():
    await asyncio.gather(counter(), ffi_sleep())


asyncio.run(main())
