#pragma once
#include "core.h"
#include <prio.h>
#include <sslt.h>
#include <certt.h>
#include <keythi.h>
#include <vector>
struct Tls {
  PRFileDesc* fd = nullptr;
  Read read; Write write; WriteSome write_some = nullptr; Idle idle; Verify verify; Decode decode;
  void* user; std::string alpn; SSLChannelInfo info{};
  std::vector<CERTCertificate*> client_chain;
  SECKEYPrivateKey* client_key = nullptr;
  ~Tls();
};
extern thread_local Tls* active_tls;
extern thread_local std::string tls_error;
PRFileDesc* TlsLayer(Tls* tls);
SECStatus VerifyPeer(void*, PRFileDesc*, PRBool, PRBool);
SECStatus DecodeZlib(const SECItem*, unsigned char*, size_t, size_t*);
SECStatus DecodeBrotli(const SECItem*, unsigned char*, size_t, size_t*);
SECStatus DecodeZstd(const SECItem*, unsigned char*, size_t, size_t*);
int TlsStatus(int status);
bool ImportClientIdentity(Tls*, const char*, uint32_t, const char*, uint32_t);
