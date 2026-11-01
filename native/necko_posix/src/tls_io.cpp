// NSS I/O layer over the standalone adapter's bounded read/write callbacks.
#include "tls_io.h"
#include <ssl.h>
#include <cert.h>
#include <keyhi.h>
#include <prerror.h>
#include <prmem.h>
#include <prnetdb.h>
#include <vector>
thread_local Tls* active_tls = nullptr;
thread_local std::string tls_error;
Tls::~Tls() {
  if (fd) PR_Close(fd);
  if (client_key) SECKEY_DestroyPrivateKey(client_key);
  for (auto* cert : client_chain) CERT_DestroyCertificate(cert);
}
int TlsStatus(int status) {
  if (status >= 0) return 0;
  const auto error = PR_GetError();
  if (error == PR_WOULD_BLOCK_ERROR) return 1;
  const char* name = PR_ErrorToName(error);
  tls_error = name ? name : "NSS operation failed (" + std::to_string(error) + ")";
  return -1;
}
namespace {
Tls* Owner(PRFileDesc* fd) { return reinterpret_cast<Tls*>(fd->secret); }
PRStatus Close(PRFileDesc* fd) { fd->secret = nullptr; fd->dtor(fd); return PR_SUCCESS; }
PRInt32 ReadBytes(PRFileDesc* fd, void* buffer, PRInt32 amount) {
  uint32_t used = 0; auto* owner = Owner(fd);
  const int status = owner->read(owner->user, static_cast<uint8_t*>(buffer), amount, &used);
  if (!status && used <= uint32_t(amount)) return PRInt32(used);
  PR_SetError(status == -2 ? PR_WOULD_BLOCK_ERROR : PR_IO_ERROR, 0); return -1;
}
PRInt32 Recv(PRFileDesc* fd, void* buffer, PRInt32 amount, PRIntn flags, PRIntervalTime) {
  if (flags) { PR_SetError(PR_NOT_IMPLEMENTED_ERROR, 0); return -1; }
  return ReadBytes(fd, buffer, amount);
}
PRInt32 WriteBytes(PRFileDesc* fd, const void* buffer, PRInt32 amount) {
  auto* owner = Owner(fd); uint32_t used = uint32_t(amount);
  const int status = owner->write_some ? owner->write_some(owner->user,
      static_cast<const uint8_t*>(buffer), amount, &used) :
      owner->write(owner->user, static_cast<const uint8_t*>(buffer), amount);
  if (!status && used <= uint32_t(amount)) return PRInt32(used);
  PR_SetError(status == -2 ? PR_WOULD_BLOCK_ERROR : PR_IO_ERROR, 0); return -1;
}
PRInt32 Send(PRFileDesc* fd, const void* buffer, PRInt32 amount, PRIntn, PRIntervalTime) {
  return WriteBytes(fd, buffer, amount);
}
PRStatus SocketOption(PRFileDesc* fd, PRSocketOptionData* data) {
  if (data->option == PR_SockOpt_Nonblocking) { data->value.non_blocking = Owner(fd)->write_some != nullptr; return PR_SUCCESS; }
  if (data->option == PR_SockOpt_NoDelay) { data->value.no_delay = PR_TRUE; return PR_SUCCESS; }
  PR_SetError(PR_NOT_IMPLEMENTED_ERROR, 0); return PR_FAILURE;
}
PRStatus SetSocketOption(PRFileDesc*, const PRSocketOptionData*) { return PR_SUCCESS; }
PRStatus Shutdown(PRFileDesc*, PRIntn) { return PR_SUCCESS; }
PRStatus Address(PRFileDesc*, PRNetAddr* value) { return PR_InitializeNetAddr(PR_IpAddrLoopback, 443, value); }
SECStatus DecodeCertificate(uint16_t algorithm, const SECItem* input, unsigned char* output,
                            size_t size, size_t* used) {
  if (!active_tls || !active_tls->decode || size > UINT32_MAX ||
      active_tls->decode(active_tls->user, algorithm, input->data, input->len, output, uint32_t(size)))
    return SECFailure;
  *used = size; return SECSuccess;
}
}
PRFileDesc* TlsLayer(Tls* tls) {
  static const auto identity = PR_GetUniqueIdentity("ruyijs-linux-nss");
  static const PRIOMethods methods = [] {
    auto table = *PR_GetDefaultIOMethods();
    table.file_type = PR_DESC_LAYERED; table.close = Close;
    table.read = ReadBytes; table.write = WriteBytes; table.recv = Recv; table.send = Send;
    table.getsocketoption = SocketOption; table.getpeername = Address; table.getsockname = Address;
    table.setsocketoption = SetSocketOption; table.shutdown = Shutdown;
    return table;
  }();
  auto* fd = PR_CreateIOLayerStub(identity, &methods);
  if (fd) fd->secret = reinterpret_cast<PRFilePrivate*>(tls);
  return fd;
}
SECStatus VerifyPeer(void* user, PRFileDesc* fd, PRBool, PRBool) {
  auto* tls = static_cast<Tls*>(user);
  auto* certificates = SSL_PeerCertificateChain(fd);
  if (!certificates) return SECFailure;
  std::vector<uint8_t> wire;
  bool valid = true;
  for (auto* node = CERT_LIST_HEAD(certificates); !CERT_LIST_END(node, certificates); node = CERT_LIST_NEXT(node)) {
    const auto& der = node->cert->derCert;
    if (der.len > 1024 * 1024 - wire.size() - 4) { valid = false; break; }
    for (int shift : {24, 16, 8, 0}) wire.push_back(uint8_t(der.len >> shift));
    wire.insert(wire.end(), der.data, der.data + der.len);
  }
  CERT_DestroyCertList(certificates);
  return valid && !wire.empty() && !tls->verify(tls->user, wire.data(), uint32_t(wire.size())) ? SECSuccess : SECFailure;
}
SECStatus DecodeZlib(const SECItem* i, unsigned char* o, size_t n, size_t* used) { return DecodeCertificate(1, i, o, n, used); }
SECStatus DecodeBrotli(const SECItem* i, unsigned char* o, size_t n, size_t* used) { return DecodeCertificate(2, i, o, n, used); }
SECStatus DecodeZstd(const SECItem* i, unsigned char* o, size_t n, size_t* used) { return DecodeCertificate(3, i, o, n, used); }
