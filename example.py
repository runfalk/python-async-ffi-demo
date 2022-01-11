import asyncio
import ctypes
from pathlib import Path
from ffilib import cdll_with_spec, DeferredCaller


class AsyncPythonFfi:
    def rust_sleep(delay_ms: ctypes.c_int) -> ctypes.c_int:
        ...


LIB = cdll_with_spec(
    Path(__file__).parent / "libasync_python_ffi.so",
    AsyncPythonFfi,
)
deferr = DeferredCaller(LIB)


async def count_sheep():
    for i in range(1, 6):
        await asyncio.sleep(1)
        print(i, "sheep")


async def ffi_sleep():
    print("Pre-sleep")
    await deferr.rust_sleep(5500)
    print("Post-sleep")


async def main():
    await asyncio.gather(count_sheep(), ffi_sleep())


asyncio.run(main())
