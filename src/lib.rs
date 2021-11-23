use std::os::raw::c_int;
use std::time::Duration;
use std::thread::sleep;

#[no_mangle]
pub extern "C" fn rust_sleep(delay_ms: c_int) -> c_int {
    let delay_ms = match delay_ms.try_into() {
        Ok(d) => d,
        Err(_) => return 1,
    };
    sleep(Duration::from_millis(delay_ms));
    0
}
