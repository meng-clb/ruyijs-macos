use std::time::Instant;
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use neqo_common::event::Provider;
use neqo_http3::{Http3ClientEvent as Event, Http3State, WebTransportEvent as Wt};
use serde_json::{Value, json};
use crate::{Result, client::Session, crypto};

fn certificates(session: &Session) -> Vec<String> {
    session.client.peer_certificate().map(|certs| certs.iter().map(|c| B64.encode(c)).collect()).unwrap_or_default()
}
pub fn info(session: &Session) -> Value {
    let tls = session.client.tls_info().map(|info| json!({"backend":"NSS", "nss":crypto::version(),
        "profile":format!("firefox-{}",session.firefox), "alpn":info.alpn(), "version":info.version(),
        "cipher_suite":info.cipher_suite(), "resumed":info.resumed()}));
    json!({"tls":tls,"certificates":certificates(session)})
}
pub fn collect(session: &mut Session) -> Result<Value> {
    let mut events = Vec::new();
    for _ in 0..128 {
        let Some(event) = session.client.next_event() else { return Ok(json!({"events":events,"more":false})); };
        let value = match event {
            Event::AuthenticationNeeded => json!({"type":"auth","certificates":certificates(session)}),
            Event::EchFallbackAuthenticationNeeded {..} => json!({"type":"ech_retry"}),
            Event::StateChange(state) => match state {
                Http3State::Connected => json!({"type":"state","state":"connected"}),
                Http3State::GoingAway(last) => json!({"type":"state","state":"going_away","last":last.as_u64()}),
                Http3State::Closed(reason) | Http3State::Closing(reason) =>
                    json!({"type":"state","state":"closed","reason":format!("{reason:?}")}),
                _ => continue,
            },
            Event::HeaderReady {stream_id,headers,interim,fin} => json!({"type":"headers",
                "stream":stream_id.as_u64(),"interim":interim,"fin":fin,
                "headers":headers.iter().map(|h| json!([h.name(),B64.encode(h.value())])).collect::<Vec<_>>()}),
            Event::WebTransport(event) => match event {
                Wt::Negotiated(available) => json!({"type":"wt_negotiated","available":available}),
                Wt::NewSession {stream_id,status,..} => json!({"type":"wt_session","session":stream_id.as_u64(),"status":status}),
                Wt::NewStream {stream_id,session_id} => json!({"type":"wt_stream","session":session_id.as_u64(),
                    "stream":stream_id.as_u64(),"bidirectional":stream_id.as_u64() & 2 == 0}),
                Wt::Datagram {session_id,datagram} => json!({"type":"wt_datagram","session":session_id.as_u64(),"data":B64.encode(datagram)}),
                Wt::Draining {stream_id} => json!({"type":"wt_draining","session":stream_id.as_u64()}),
                Wt::SessionClosed {stream_id,reason,..} => {
                    use neqo_http3::features::extended_connect::session::CloseReason;
                    let (clean,code,message) = match reason {
                        CloseReason::Clean {error,message} => (true,u64::from(error),message),
                        other => (false,0,format!("{other:?}")),
                    };
                    json!({"type":"wt_closed","session":stream_id.as_u64(),"clean":clean,"code":code,"reason":message})
                },
            },
            Event::DataReadable {stream_id} => json!({"type":"readable","stream":stream_id.as_u64()}),
            Event::Reset {stream_id,error,..} => json!({"type":"reset","stream":stream_id.as_u64(),"error":error}),
            Event::StopSending {stream_id,error} => json!({"type":"stop_sending","stream":stream_id.as_u64(),"error":error}),
            Event::ResumptionToken(token) => json!({"type":"token","data":B64.encode(token.as_ref()),
                "expires_in":token.expiration_time().saturating_duration_since(Instant::now()).as_secs()}),
            _ => continue,
        };
        events.push(value);
    }
    Ok(json!({"events":events,"more":true}))
}
