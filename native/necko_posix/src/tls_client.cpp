// Per-connection, temporary NSS identities. No certificate/key database writes.
#include "tls_io.h"
#include <cert.h>
#include <keyhi.h>
#include <pk11pub.h>
#include <secerr.h>
#include <ssl.h>
#include <prerror.h>
namespace {
SECStatus Select(void* arg, PRFileDesc*, CERTDistNames*, CERTCertificate** cert,
                 SECKEYPrivateKey** key) {
  auto* tls = static_cast<Tls*>(arg);
  *cert = CERT_DupCertificate(tls->client_chain.front());
  *key = SECKEY_CopyPrivateKey(tls->client_key);
  if (*cert && *key) return SECSuccess;
  if (*cert) CERT_DestroyCertificate(*cert);
  if (*key) SECKEY_DestroyPrivateKey(*key);
  *cert = nullptr; *key = nullptr;
  return SECFailure;
}
}
bool ImportClientIdentity(Tls* tls, const char* data, uint32_t size,
                          const char* key, uint32_t key_size) {
  if (!size && !key_size) return true;
  if (!data || !key || !size || !key_size || size > 1024 * 1024 || key_size > 1024 * 1024) {
    PR_SetError(SEC_ERROR_INVALID_ARGS, 0); return false;
  }
  const auto* bytes = reinterpret_cast<const unsigned char*>(data);
  while (size) {
    if (size < 4 || tls->client_chain.size() >= 32) { PR_SetError(SEC_ERROR_BAD_DER, 0); return false; }
    const uint32_t n = uint32_t(bytes[0]) << 24 | uint32_t(bytes[1]) << 16 |
                       uint32_t(bytes[2]) << 8 | bytes[3];
    bytes += 4; size -= 4;
    if (!n || n > size) { PR_SetError(SEC_ERROR_BAD_DER, 0); return false; }
    SECItem der{siBuffer, const_cast<unsigned char*>(bytes), n};
    auto* cert = CERT_NewTempCertificate(CERT_GetDefaultCertDB(), &der, nullptr, PR_FALSE, PR_TRUE);
    if (!cert) return false;
    tls->client_chain.push_back(cert); bytes += n; size -= n;
  }
  auto* slot = PK11_GetInternalKeySlot();
  if (!slot) return false;
  SECItem der{siBuffer, reinterpret_cast<unsigned char*>(const_cast<char*>(key)), key_size};
  const auto status = PK11_ImportDERPrivateKeyInfoAndReturnKey(slot, &der, nullptr,
      nullptr, PR_FALSE, PR_FALSE, KU_ALL, &tls->client_key, nullptr);
  PK11_FreeSlot(slot);
  if (status != SECSuccess) return false;
  // The Python owner also checks the public keys before crossing the ABI.
  return SSL_GetClientAuthDataHook(tls->fd, Select, tls) == SECSuccess;
}
