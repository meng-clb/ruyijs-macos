#include "resource_network/necko_pipe.h"
#include <string>

#ifdef _WIN32

namespace ruyijs::resource_network {
DWORD NeckoRemaining(ULONGLONG deadline) {
  const auto now = GetTickCount64();
  return now >= deadline ? 0 : DWORD(deadline - now);
}
bool NeckoPipe::Open(bool parentWrites) {
  static LONG sequence = 0;
  const auto name = L"\\\\.\\pipe\\ruyijs-necko-" + std::to_wstring(GetCurrentProcessId()) +
      L"-" + std::to_wstring(GetTickCount64()) + L"-" + std::to_wstring(InterlockedIncrement(&sequence));
  parent_.Reset(CreateNamedPipeW(name.c_str(),
      (parentWrites ? PIPE_ACCESS_OUTBOUND : PIPE_ACCESS_INBOUND) |
          FILE_FLAG_OVERLAPPED | FILE_FLAG_FIRST_PIPE_INSTANCE,
      PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
      1, 65536, 65536, 0, nullptr));
  if (!parent_) return false;
  SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
  child_.Reset(CreateFileW(name.c_str(), parentWrites ? GENERIC_READ : GENERIC_WRITE,
      0, &inherit, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
  event_.Reset(CreateEventW(nullptr, TRUE, FALSE, nullptr));
  if (!child_ || !event_) return false;
  OVERLAPPED connected{};
  connected.hEvent = event_.Get();
  // The local client was opened first, so connect completes immediately.
  if (ConnectNamedPipe(parent_.Get(), &connected)) return true;
  const DWORD error = GetLastError();
  if (error == ERROR_IO_PENDING) {
    DWORD ignored = 0;
    CancelIoEx(parent_.Get(), &connected);
    GetOverlappedResult(parent_.Get(), &connected, &ignored, TRUE);
  }
  return error == ERROR_PIPE_CONNECTED;
}
bool NeckoPipe::Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline) {
  auto* bytes = static_cast<char*>(data);
  uint32_t done = 0;
  while (done < size) {
    if (!NeckoRemaining(deadline)) return false;
    OVERLAPPED io{};
    io.hEvent = event_.Get();
    if (!ResetEvent(io.hEvent)) return false;
    DWORD moved = 0;
    const DWORD amount = size - done > 65536 ? 65536 : size - done;
    const BOOL ready = writing ?
        WriteFile(parent_.Get(), bytes + done, amount, &moved, &io) :
        ReadFile(parent_.Get(), bytes + done, amount, &moved, &io);
    if (!ready) {
      if (GetLastError() != ERROR_IO_PENDING) return false;
      if (WaitForSingleObject(io.hEvent, NeckoRemaining(deadline)) != WAIT_OBJECT_0) {
        CancelIoEx(parent_.Get(), &io);
        // Complete cancellation before the OVERLAPPED or caller buffer dies.
        GetOverlappedResult(parent_.Get(), &io, &moved, TRUE);
        return false;
      }
      if (!GetOverlappedResult(parent_.Get(), &io, &moved, FALSE)) return false;
    }
    if (!moved || moved > amount) return false;
    done += moved;
  }
  return true;
}
bool NeckoPipe::Write(const void* data, uint32_t size, ULONGLONG deadline) {
  return Transfer(const_cast<void*>(data), size, true, deadline);
}
bool NeckoPipe::Read(void* data, uint32_t size, ULONGLONG deadline) {
  return Transfer(data, size, false, deadline);
}
}

#else

#include <poll.h>
#include <time.h>
#include <unistd.h>

namespace ruyijs::resource_network {
static inline ULONGLONG PosixTickCountMs() {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return static_cast<ULONGLONG>(ts.tv_sec) * 1000 + (ts.tv_nsec / 1000000);
}

DWORD NeckoRemaining(ULONGLONG deadline) {
  const auto now = PosixTickCountMs();
  return now >= deadline ? 0 : DWORD(deadline - now);
}

bool NeckoPipe::Open(bool parentWrites) {
  int fds[2];
  if (pipe(fds) != 0) return false;
  if (parentWrites) {
    parent_.Reset(fds[1]);
    child_.Reset(fds[0]);
  } else {
    parent_.Reset(fds[0]);
    child_.Reset(fds[1]);
  }
  return true;
}

bool NeckoPipe::Transfer(void* data, uint32_t size, bool writing, ULONGLONG deadline) {
  auto* bytes = static_cast<char*>(data);
  uint32_t done = 0;
  while (done < size) {
    DWORD rem = NeckoRemaining(deadline);
    if (rem == 0) return false;
    struct pollfd pfd{};
    pfd.fd = static_cast<int>(parent_.Get());
    pfd.events = writing ? POLLOUT : POLLIN;
    int timeout = rem > 60000 ? 60000 : static_cast<int>(rem);
    int ret = poll(&pfd, 1, timeout);
    if (ret <= 0) return false;
    ssize_t moved = 0;
    const size_t amount = size - done > 65536 ? 65536 : size - done;
    if (writing) {
      moved = write(static_cast<int>(parent_.Get()), bytes + done, amount);
    } else {
      moved = read(static_cast<int>(parent_.Get()), bytes + done, amount);
    }
    if (moved <= 0) return false;
    done += static_cast<uint32_t>(moved);
  }
  return true;
}

bool NeckoPipe::Write(const void* data, uint32_t size, ULONGLONG deadline) {
  return Transfer(const_cast<void*>(data), size, true, deadline);
}

bool NeckoPipe::Read(void* data, uint32_t size, ULONGLONG deadline) {
  return Transfer(data, size, false, deadline);
}
}

#endif
