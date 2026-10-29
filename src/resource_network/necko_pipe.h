#ifndef RUYIJS_NECKO_PIPE_H
#define RUYIJS_NECKO_PIPE_H

#include <cstdint>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <sys/types.h>
#include <time.h>
using HANDLE = intptr_t;
constexpr HANDLE INVALID_HANDLE_VALUE = -1;
using DWORD = uint32_t;
using ULONGLONG = uint64_t;
using LONG = int32_t;
using BOOL = int;
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

inline ULONGLONG GetTickCount64() {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<ULONGLONG>(ts.tv_sec) * 1000 + (ts.tv_nsec / 1000000);
}
#endif

namespace ruyijs::resource_network {
class NeckoHandle {
 public:
#ifdef _WIN32
  explicit NeckoHandle(HANDLE value = nullptr) : value_(value) {}
  ~NeckoHandle() { Reset(); }
  NeckoHandle(const NeckoHandle&) = delete;
  NeckoHandle& operator=(const NeckoHandle&) = delete;
  HANDLE Get() const { return value_; }
  explicit operator bool() const { return value_ && value_ != INVALID_HANDLE_VALUE; }
  void Reset(HANDLE value = nullptr) {
    if (*this) CloseHandle(value_);
    value_ = value;
  }
 private:
  HANDLE value_;
#else
  explicit NeckoHandle(HANDLE value = -1) : value_(value) {}
  ~NeckoHandle() { Reset(); }
  NeckoHandle(const NeckoHandle&) = delete;
  NeckoHandle& operator=(const NeckoHandle&) = delete;
  HANDLE Get() const { return value_; }
  explicit operator bool() const { return value_ >= 0; }
  void Reset(HANDLE value = -1) {
    if (value_ >= 0) close(static_cast<int>(value_));
    value_ = value;
  }
 private:
  HANDLE value_{-1};
#endif
};

DWORD NeckoRemaining(ULONGLONG deadline);
class NeckoPipe {
 public:
  bool Open(bool parentWrites);
  HANDLE Child() const { return child_.Get(); }
  void CloseChild() { child_.Reset(); }
  void CloseParent() { parent_.Reset(); }
  bool Write(const void* data, uint32_t size, ULONGLONG deadline);
  bool Read(void* data, uint32_t size, ULONGLONG deadline);
 private:
  bool Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline);
  NeckoHandle parent_, child_, event_;
};
}
#endif
