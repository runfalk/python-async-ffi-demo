import asyncio
import ctypes
import functools
import inspect
import threading

from collections import deque
from queue import Queue


class Channel:
    """
    Multiple producer multiple consumer channel

    This is a simple way of creating worker threads that consumes tasks using
    a for loop.

    Example

    ```
    import threading

    ch = Channel()
    def worker():
        for item in ch:
            print(f"Got task {item}")
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    ch.add(1)
    ch.add(2)
    ch.add(3)

    # Closing the channel with stop the iterator and the thread in this example
    # will finish
    ch.close()
    ```

    This will print:

        Got task 1
        Got task 2
        Got task 3
    """

    def __init__(self, maxsize=None):
        self.mutex = threading.Lock()
        self.not_empty = threading.Condition(lock=self.mutex)
        self.not_full = threading.Condition(lock=self.mutex)
        self.queue = deque(maxlen=maxsize)
        self.is_open = True

    @property
    def maxsize(self):
        return self.queue.maxlen

    def close(self):
        with self.mutex:
            self.is_open = False
            self.not_empty.notify_all()
            self.not_full.notify_all()

    def add(self, item):
        with self.not_full:
            if (
                self.is_open 
                and self.maxsize is not None 
                and len(self.queue) >= self.maxsize
            ):
                self.not_full.wait()
            if not self.is_open:
                return
            self.queue.append(item)
            self.not_empty.notify()

    def __iter__(self):
        while True:
            with self.not_empty:
                if self.is_open and not self.queue:
                    self.not_empty.wait()
                if not self.is_open:
                    return
                item = self.queue.popleft()
                self.not_full.notify()
            yield item


class DeferredCaller:
    """
    Wrap the given class or lib and make the methods async and run them in a
    separate thread. This is mostly useful when calling C libraries when you
    want the methods to be asynchronous. If the C libary is initialized using
    ctypes.CDLL it'll release the GIL while in a C function so we can actually
    run functions in parallel.

    ```
    LIB = load_c_library()
    deferr = DeferredCaller(LIB)
    await deferr.some_blocking_method()
    ```

    Note that all calls for the same DefferedCaller instance runs in a single
    thread. This means they'll never run in parallel. If you want two calls for
    the same library to run in parallel you must create two DeferredCaller
    instances.
    """

    def __init__(self, lib):
        self.lib = lib
        self.calls = Channel()
        def caller_thread():
            for f, args, kwargs, fut in self.calls:
                loop = fut.get_loop()
                try:
                    loop.call_soon_threadsafe(
                        fut.set_result,
                        f(*args, **kwargs),
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(fut.set_exception, e)
        self.thread = threading.Thread(target=caller_thread, daemon=True)
        self.thread.start()

    def __getattr__(self, attr):
        f = getattr(self.lib, attr, None)
        if f is None:
            raise AttributeError(f"Attribute {attr!r} not found")

        @functools.wraps(f)
        async def wrapper(*args, **kwargs):
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self.calls.add((f, args, kwargs, fut))
            return await fut

        return wrapper


def cdll_with_spec(lib_path, spec):
    """
    Open a shared library using ctypes.CDLL and apply the given spec class'
    type annotations to the argtypes and restype attributes of the shared
    library's functions.

    The spec is a stub class with type annotations for the argument and return
    types. These needs to be ctypes compatible. This stub class is the
    equivalent of a header file.

    ```
    # The C library has a one function:
    # int add(int x, int y);

    import ctypes
    class LibrarySpec:
        def add(x: ctypes.c_int, y: ctypes.c_int) -> ctypes.c_int:
            ...

    LIB = cdll_with_spec("path/to/lib.so", LibrarySpec)
    ```
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
