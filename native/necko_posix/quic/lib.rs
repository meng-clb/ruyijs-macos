// Native HTTP/3 ABI for the standalone Necko Python adapter.
// Protocol and TLS processing are supplied by Mozilla Neqo and NSS.
mod client;
mod crypto;
mod events;
mod webtransport;

use std::{cell::RefCell, collections::HashMap, ffi::{CString, c_char}, panic::{catch_unwind, AssertUnwindSafe},
    sync::atomic::{AtomicU64, Ordering}};
use serde_json::{Value, json};
use client::Session;

pub type Result<T> = std::result::Result<T, String>;
pub fn err(error: impl std::fmt::Debug) -> String { format!("{error:?}") }
pub fn text<'a>(v: &'a Value, name: &str) -> Result<&'a str> {
    v[name].as_str().ok_or_else(|| format!("Missing string: {name}"))
}
pub fn number(v: &Value, name: &str) -> Result<u64> {
    v[name].as_u64().ok_or_else(|| format!("Missing integer: {name}"))
}
thread_local! {
    static SESSIONS: RefCell<HashMap<u64, Session>> = RefCell::new(HashMap::new());
    static REPLY: RefCell<CString> = RefCell::new(CString::new("{}").unwrap());
}
static NEXT: AtomicU64 = AtomicU64::new(1);

fn call(handle: u64, request: &Value) -> Result<Value> {
    let operation = text(request, "op")?;
    SESSIONS.with(|map| {
        let mut map = map.borrow_mut();
        if operation == "new" {
            if map.len() >= 32 { return Err("QUIC connection limit exceeded".into()); }
            let session = Session::new(request)?;
            let id = NEXT.fetch_add(1, Ordering::Relaxed);
            map.insert(id, session);
            return Ok(json!({"handle":id}));
        }
        if operation == "close" {
            if let Some(mut session) = map.remove(&handle) { session.close(); }
            return Ok(json!({}));
        }
        let session = map.get_mut(&handle).ok_or("Unknown QUIC handle or wrong owner thread")?;
        session.call(operation, request)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn necko_quic_call(handle: u64, data: *const u8, length: usize) -> *const c_char {
    let result = catch_unwind(AssertUnwindSafe(|| {
        if data.is_null() || length > 1024 * 1024 { return Err("Invalid QUIC frame size".into()); }
        let request: Value = serde_json::from_slice(unsafe { std::slice::from_raw_parts(data, length) }).map_err(err)?;
        call(handle, &request)
    }));
    let value = match result {
        Ok(Ok(value)) => value,
        Ok(Err(error)) => json!({"error":error}),
        Err(_) => json!({"error":"QUIC adapter panicked"}),
    };
    REPLY.with(|reply| {
        *reply.borrow_mut() = CString::new(value.to_string()).unwrap();
        reply.borrow().as_ptr()
    })
}

#[unsafe(no_mangle)]
pub extern "C" fn necko_quic_set_decoder(decoder: Option<crypto::Decoder>) { crypto::set_decoder(decoder); }

#[unsafe(no_mangle)]
pub extern "C" fn necko_quic_version() -> u32 { 32 }
