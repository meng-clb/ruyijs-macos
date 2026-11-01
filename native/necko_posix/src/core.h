#pragma once
#include <cstdint>
#include <string>
using Read = int (*)(void*, uint8_t*, uint32_t, uint32_t*);
using Write = int (*)(void*, const uint8_t*, uint32_t);
using WriteSome = int (*)(void*, const uint8_t*, uint32_t, uint32_t*);
using Idle = int (*)(void*);
using Verify = int (*)(void*, const uint8_t*, uint32_t);
using Decode = int (*)(void*, uint16_t, const uint8_t*, uint32_t, uint8_t*, uint32_t);
using Cancel = int (*)(void*);
struct Profile {
  const uint16_t* ciphers; uint32_t cipher_count;
  const uint16_t* groups; uint32_t group_count, additional_key_shares;
  const uint16_t* signatures; uint32_t signature_count;
  const uint16_t* compression; uint32_t compression_count;
  int signed_cert_timestamps, grease_ech; uint32_t grease_ech_size;
};
