use std::{cell::RefCell, collections::{VecDeque, HashMap}, io::ErrorKind, net::{SocketAddr, UdpSocket},
    os::fd::{FromRawFd, RawFd}, rc::Rc, time::{Duration, Instant}};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use neqo_common::{Datagram, Header, Tos};
use neqo_http3::{Http3Client, Http3Parameters, Priority};
use neqo_transport::{Connection, ConnectionParameters, Output, RandomConnectionIdGenerator, StreamDataLimit, StreamId, StreamType, Version};
use serde_json::{Value, json};
use crate::{Result, crypto, err, number, text};

pub struct Session {
    pub client: Http3Client,
    pub socket: Option<UdpSocket>,
    pub local: SocketAddr,
    pub remote: SocketAddr,
    pub firefox: String,
    pub sent_bytes: u64,
    pending: VecDeque<Vec<u8>>,
    pub wt_closed: HashMap<u64, Value>,
}
impl Session {
    pub fn new(v: &Value) -> Result<Self> {
        nss::init().map_err(err)?;
        let local: SocketAddr = text(v, "local")?.parse().map_err(err)?;
        let remote: SocketAddr = text(v, "remote")?.parse().map_err(err)?;
        let p = &v["profile"];
        let wt = v["webtransport"].as_bool().unwrap_or(false);
        let max_streams = p["max_streams"].as_u64().unwrap_or(100).min(100);
        let mut params = ConnectionParameters::default()
            .max_streams(StreamType::BiDi, max_streams).max_streams(StreamType::UniDi, max_streams)
            .max_data(24 * 1024 * 1024).max_stream_data(StreamDataLimit::BiDiLocal, 12 * 1024 * 1024)
            .idle_timeout(Duration::from_secs(30)).grease(p["grease_quic_bit"].as_bool().unwrap_or(false))
            .disable_migration(p["disable_migration"].as_bool().unwrap_or(false))
            .sni_slicing(p["sni_slicing"].as_bool().unwrap_or(true))
            .datagram_size(p["datagram_size"].as_u64().unwrap_or(65535).min(65535))
            .reliable_stream_reset(p["reliable_stream_reset"].as_bool().unwrap_or(false));
        if !p["version2"].as_bool().unwrap_or(false) {
            params = params.versions(Version::Version1, vec![Version::Version1]);
        }
        let http3 = Http3Parameters::default().connection_parameters(params.clone())
            .max_table_size_encoder(65536).max_table_size_decoder(65536).max_blocked_streams(20)
            .http3_datagram(wt || p["h3_datagram"].as_bool().unwrap_or(false))
            .webtransport(wt).connect(wt);
        let mut connection = Connection::new_client(text(v,"host")?, &["h3"],
            Rc::new(RefCell::new(RandomConnectionIdGenerator::new(3))), local, remote, params, Instant::now()).map_err(err)?;
        let style = p["tp_style"].as_u64().unwrap_or(0);
        if style > 3 { return Err("Unknown transport parameter style".into()); }
        connection.standalone_tp_style(style as u8);
        crypto::configure(&mut connection, p)?;
        let mut client = Http3Client::new_with_conn(connection, http3);
        if p["grease_ech"].as_bool().unwrap_or(false) { client.enable_ech([]).map_err(err)?; }
        if let Some(token) = v["token"].as_str().filter(|s| !s.is_empty()) {
            client.enable_resumption(Instant::now(), B64.decode(token).map_err(err)?).map_err(err)?;
        }
        Ok(Self {client, socket: None, local, remote, firefox: v["firefox"].as_str().unwrap_or("159").into(), sent_bytes: 0, pending: VecDeque::new(), wt_closed: HashMap::new()})
    }
    pub fn close(&mut self) { self.client.close(Instant::now(), 0x100, "context closed"); let _ = self.pump(); }
    fn attach(&mut self, fd: u64) -> Result<Value> {
        if self.socket.is_some() || fd > i32::MAX as u64 { return Err("Invalid UDP attachment".into()); }
        let duplicate = unsafe { libc::fcntl(fd as RawFd, libc::F_DUPFD_CLOEXEC, 3) };
        if duplicate < 0 { return Err(std::io::Error::last_os_error().to_string()); }
        let socket = unsafe { UdpSocket::from_raw_fd(duplicate) };
        if socket.local_addr().map_err(err)? != self.local || socket.peer_addr().map_err(err)? != self.remote {
            return Err("UDP endpoint does not match QUIC connection".into());
        }
        socket.set_nonblocking(true).map_err(err)?; self.socket = Some(socket); Ok(json!({}))
    }
    pub fn pump(&mut self) -> Result<Value> {
        let socket = self.socket.as_ref().ok_or("QUIC has no UDP socket")?;
        let mut data = [0; 65536];
        for _ in 0..64 {
            match socket.recv(&mut data) {
                Ok(0) => continue,
                Ok(n) => self.client.process_input(Datagram::new(self.remote,self.local,Tos::default(),data[..n].to_vec()),Instant::now()),
                Err(e) if e.kind() == ErrorKind::WouldBlock => break,
                Err(e) => return Err(e.to_string()),
            }
        }
        let mut delay = 0.1;
        for _ in 0..64 {
            if self.pending.is_empty() {
                match self.client.process_output(Instant::now()) {
                    Output::Datagram(d) => self.pending.push_back(d[..].to_vec()),
                    Output::Callback(d) => { delay = d.as_secs_f64().min(0.1); break; },
                    Output::None => break,
                }
            }
            let bytes = self.pending.front().unwrap();
            match socket.send(bytes) {
                Ok(n) if n == bytes.len() => { self.sent_bytes += n as u64; self.pending.pop_front(); },
                Ok(_) => return Err("Partial UDP send".into()),
                Err(e) if e.kind() == ErrorKind::WouldBlock => { delay = 0.001; break; },
                Err(e) => return Err(e.to_string()),
            }
        }
        Ok(json!({"delay":delay}))
    }
    pub fn call(&mut self, op: &str, v: &Value) -> Result<Value> {
        let now = Instant::now();
        match op {
            "webtransport" => crate::webtransport::call(self,v),
            "attach" => self.attach(number(v,"socket")?),
            "pump" => self.pump(),
            "events" => crate::events::collect(self),
            "info" => Ok(crate::events::info(self)),
            "auth" => { self.client.authenticated(if v["accepted"].as_bool().unwrap_or(false) {
                nss::AuthenticationStatus::Ok } else { nss::AuthenticationStatus::CertUntrusted },now); Ok(json!({})) },
            "fetch" => {
                let input = v["headers"].as_array().ok_or("Missing request headers")?;
                if input.len() > 256 { return Err("Too many request headers".into()); }
                let mut fields = Vec::new(); let mut size = 0;
                for field in input {
                    let name = field[0].as_str().ok_or("Invalid header name")?;
                    let value = B64.decode(field[1].as_str().ok_or("Invalid header value")?).map_err(err)?;
                    size += name.len() + value.len(); if size > 65536 { return Err("Request headers exceed limit".into()); }
                    fields.push(Header::new(name, value));
                }
                let priority = Priority::new(v["urgency"].as_u64().unwrap_or(4).min(7) as u8,v["incremental"].as_bool().unwrap_or(false));
                let id = self.client.fetch(now,text(v,"method")?,("https",text(v,"authority")?,text(v,"path")?),&fields,priority).map_err(err)?;
                Ok(json!({"stream":id.as_u64()}))
            },
            "write" => {
                let data = B64.decode(text(v,"data")?).map_err(err)?;
                if data.len() > 65536 { return Err("Upload chunk exceeds limit".into()); }
                let count = self.client.send_data(StreamId::from(number(v,"stream")?),&data,now).map_err(err)?;
                Ok(json!({"count":count}))
            },
            "read" => {
                let mut data = vec![0; number(v,"size")?.min(65536) as usize];
                let (count,fin) = self.client.read_data(now,StreamId::from(number(v,"stream")?),&mut data).map_err(err)?;
                Ok(json!({"data":B64.encode(&data[..count]),"fin":fin}))
            },
            "finish" => { self.client.stream_close_send(StreamId::from(number(v,"stream")?),now).map_err(err)?; Ok(json!({})) },
            "cancel" => { let _ = self.client.cancel_fetch(StreamId::from(number(v,"stream")?),0x10c); Ok(json!({})) },
            _ => Err(format!("Unsupported QUIC operation: {op}")),
        }
    }
}
