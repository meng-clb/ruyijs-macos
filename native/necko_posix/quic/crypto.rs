use std::{cell::Cell, ffi::{CStr, c_char, c_void}};
use neqo_transport::Connection;
use nss::cert::CertificateCompressor;
use serde_json::Value;
use crate::{Result, err};

pub type Decoder = unsafe extern "C" fn(u16, *const u8, usize, *mut u8, usize) -> i32;
thread_local! { static DECODER: Cell<Option<Decoder>> = const { Cell::new(None) }; }
pub fn set_decoder(value: Option<Decoder>) { DECODER.with(|slot| slot.set(value)); }
fn decode(algorithm: u16, input: &[u8], output: &mut [u8]) -> nss::Res<()> {
    DECODER.with(|slot| {
        let callback = slot.get().ok_or(nss::Error::Internal)?;
        if unsafe { callback(algorithm, input.as_ptr(), input.len(), output.as_mut_ptr(), output.len()) } != 0 {
            return Err(nss::Error::Internal);
        }
        Ok(())
    })
}
macro_rules! compressor {
    ($name:ident, $id:literal, $label:expr) => {
        struct $name;
        impl CertificateCompressor for $name {
            const ID: u16 = $id;
            const NAME: &'static CStr = $label;
            fn decode(input: &[u8], output: &mut [u8]) -> nss::Res<()> { decode($id, input, output) }
        }
    }
}
compressor!(Zlib, 1, c"zlib");
compressor!(Brotli, 2, c"brotli");
compressor!(Zstd, 3, c"zstd");

#[link(name="ssl3")]
unsafe extern "C" {
    fn SSL_OptionSet(fd: *mut c_void, option: i32, value: i32) -> i32;
    fn SSL_NamedGroupConfig(fd: *mut c_void, groups: *const u32, count: u32) -> i32;
    fn SSL_SignatureSchemePrefSet(fd: *mut c_void, schemes: *const u32, count: u32) -> i32;
}
#[link(name="nss3")]
unsafe extern "C" { fn NSS_GetVersion() -> *const c_char; }

pub fn version() -> String { unsafe { CStr::from_ptr(NSS_GetVersion()) }.to_string_lossy().into_owned() }
fn list(profile: &Value, key: &str) -> Result<Vec<u32>> {
    let values = profile[key].as_array().ok_or_else(|| format!("Missing TLS {key}"))?;
    if values.is_empty() || values.len() > 32 { return Err(format!("Invalid TLS {key} count")); }
    values.iter().map(|v| v.as_u64().filter(|n| *n <= 65535).map(|n| n as u32)
        .ok_or_else(|| format!("Invalid TLS {key} value"))).collect()
}
pub fn configure(connection: &mut Connection, profile: &Value) -> Result<()> {
    let groups = list(profile, "groups")?;
    let signatures = list(profile, "signatures")?;
    let fd = connection.standalone_tls_fd();
    let shares = profile["additional_key_shares"].as_u64().filter(|n| *n <= 8).ok_or("Invalid key share count")?;
    unsafe {
        if SSL_OptionSet(fd, 40, 1) != 0 ||
            SSL_NamedGroupConfig(fd, groups.as_ptr(), groups.len() as u32) != 0 ||
            SSL_SignatureSchemePrefSet(fd, signatures.as_ptr(), signatures.len() as u32) != 0 {
            return Err("NSS rejected QUIC TLS profile".into());
        }
    }
    connection.send_additional_key_shares(shares as usize).map_err(err)?;
    if let Some(algorithms) = profile["compression"].as_array() {
        for algorithm in algorithms {
            match algorithm.as_u64() {
                Some(1) => connection.set_certificate_compression::<Zlib>().map_err(err)?,
                Some(2) => connection.set_certificate_compression::<Brotli>().map_err(err)?,
                Some(3) => connection.set_certificate_compression::<Zstd>().map_err(err)?,
                _ => return Err("Unsupported TLS certificate compression".into()),
            }
        }
    }
    Ok(())
}
