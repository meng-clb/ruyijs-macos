#ifdef _WIN32
#include "runtime/pipe.h"
#include <cstdint>
#include <cstring>
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace ruyijs {
Pipe::~Pipe() { Close(); }

namespace {
// One name grammar for both ends: the owner creates the pipe and the child
// connects with the same name.
bool ValidName(const char* name) {
  constexpr char prefix[] = "\\\\.\\pipe\\ruyijs-";
  if (strncmp(name, prefix, sizeof(prefix) - 1) != 0) return false;
  const char* suffix = name + sizeof(prefix) - 1;
  if (strlen(suffix) < 16 || strlen(suffix) > 64) return false;
  for (const char* p = suffix; *p; ++p) {
    if (!((*p >= 'a' && *p <= 'f') || (*p >= '0' && *p <= '9') || *p == '-'))
      return false;
  }
  return true;
}
}  // namespace

bool Pipe::Connect(const char* name) { return OpenClient(name, false); }
bool Pipe::OpenClient(const char* name, bool asynchronous) {
  if (handle_ || !name || !ValidName(name)) return false;
  HANDLE handle = CreateFileA(name, GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                              OPEN_EXISTING, asynchronous ? FILE_FLAG_OVERLAPPED : 0, nullptr);
  if (handle == INVALID_HANDLE_VALUE) return false;
  handle_ = handle;
  return true;
}

bool Pipe::Listen(const char* name) { return OpenServer(name, false); }
bool Pipe::OpenServer(const char* name, bool asynchronous) {
  if (handle_ || !name || !ValidName(name)) return false;
  HANDLE handle = CreateNamedPipeA(name, PIPE_ACCESS_DUPLEX | (asynchronous ? FILE_FLAG_OVERLAPPED : 0),
      PIPE_TYPE_BYTE | PIPE_REJECT_REMOTE_CLIENTS, 1, 65536, 65536, 0, nullptr);
  if (handle == INVALID_HANDLE_VALUE) return false;
  handle_ = handle;
  return true;
}

// Legacy synchronous callers explicitly opt into a blocking accept. Worker
// process construction uses ListenAsync and Poll on the parent's event loop.
bool Pipe::Accept() {
  if (!handle_ || async_) return false;
  if (!ConnectNamedPipe(handle_, nullptr) && GetLastError() != ERROR_PIPE_CONNECTED)
    return false;
  return true;
}

bool Pipe::Transfer(void* data, unsigned length, bool writing) {
  if (!handle_ || async_) return false;
  auto* bytes = static_cast<char*>(data);
  while (length) {
    DWORD count = 0;
    BOOL ok = writing ? WriteFile(handle_, bytes, length, &count, nullptr)
                      : ReadFile(handle_, bytes, length, &count, nullptr);
    if (!ok || !count) return false;
    bytes += count;
    length -= count;
  }
  return true;
}

bool Pipe::Read(std::string* frame) {
  uint32_t length = 0;
  if (!Transfer(&length, sizeof(length), false) || !ValidFrameSize(length))
    return false;
  frame->resize(length);
  return Transfer(frame->data(), length, false);
}

bool Pipe::Write(const std::string& frame) {
  if (!ValidFrameSize(frame.size())) return false;
  uint32_t length = static_cast<uint32_t>(frame.size());
  return Transfer(&length, sizeof(length), true) &&
         Transfer(const_cast<char*>(frame.data()), length, true);
}
}

#else
#include "runtime/pipe.h"
#include <cstdint>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

namespace ruyijs {
Pipe::~Pipe() { Close(); }

namespace {
std::string NormalizeUnixName(const char* name) {
  if (!name) return "";
  constexpr char winPrefix[] = "\\\\.\\pipe\\ruyijs-";
  if (strncmp(name, winPrefix, sizeof(winPrefix) - 1) == 0) {
    return std::string("/tmp/ruyijs-") + (name + sizeof(winPrefix) - 1) + ".sock";
  }
  return name;
}
}  // namespace

bool Pipe::Connect(const char* name) { return OpenClient(name, false); }
bool Pipe::OpenClient(const char* name, bool /*asynchronous*/) {
  if (handle_ || !name) return false;
  std::string sockPath = NormalizeUnixName(name);
  int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
  if (fd < 0) return false;

  struct sockaddr_un addr{};
  addr.sun_family = AF_UNIX;
  if (sockPath.size() >= sizeof(addr.sun_path)) {
    ::close(fd);
    return false;
  }
  std::strncpy(addr.sun_path, sockPath.c_str(), sizeof(addr.sun_path) - 1);

  if (::connect(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) != 0) {
    ::close(fd);
    return false;
  }
  handle_ = reinterpret_cast<void*>(static_cast<intptr_t>(fd));
  return true;
}

bool Pipe::Listen(const char* name) { return OpenServer(name, false); }
bool Pipe::OpenServer(const char* name, bool /*asynchronous*/) {
  if (handle_ || !name) return false;
  std::string sockPath = NormalizeUnixName(name);
  ::unlink(sockPath.c_str());

  int fd = ::socket(AF_UNIX, SOCK_STREAM, 0);
  if (fd < 0) return false;

  struct sockaddr_un addr{};
  addr.sun_family = AF_UNIX;
  if (sockPath.size() >= sizeof(addr.sun_path)) {
    ::close(fd);
    return false;
  }
  std::strncpy(addr.sun_path, sockPath.c_str(), sizeof(addr.sun_path) - 1);

  if (::bind(fd, reinterpret_cast<struct sockaddr*>(&addr), sizeof(addr)) != 0 ||
      ::listen(fd, 1) != 0) {
    ::close(fd);
    return false;
  }
  handle_ = reinterpret_cast<void*>(static_cast<intptr_t>(fd));
  return true;
}

bool Pipe::Accept() {
  if (!handle_ || async_) return false;
  int server_fd = static_cast<int>(reinterpret_cast<intptr_t>(handle_));
  int client_fd = ::accept(server_fd, nullptr, nullptr);
  if (client_fd < 0) return false;
  ::close(server_fd);
  handle_ = reinterpret_cast<void*>(static_cast<intptr_t>(client_fd));
  return true;
}

bool Pipe::Transfer(void* data, unsigned length, bool writing) {
  if (!handle_ || async_) return false;
  int fd = static_cast<int>(reinterpret_cast<intptr_t>(handle_));
  auto* bytes = static_cast<char*>(data);
  while (length) {
    ssize_t count = writing ? ::write(fd, bytes, length) : ::read(fd, bytes, length);
    if (count <= 0) {
      if (count < 0 && (errno == EINTR || errno == EAGAIN)) continue;
      return false;
    }
    bytes += count;
    length -= static_cast<unsigned>(count);
  }
  return true;
}

bool Pipe::Read(std::string* frame) {
  uint32_t length = 0;
  if (!Transfer(&length, sizeof(length), false) || !ValidFrameSize(length))
    return false;
  frame->resize(length);
  return Transfer(frame->data(), length, false);
}

bool Pipe::Write(const std::string& frame) {
  if (!ValidFrameSize(frame.size())) return false;
  uint32_t length = static_cast<uint32_t>(frame.size());
  return Transfer(&length, sizeof(length), true) &&
         Transfer(const_cast<char*>(frame.data()), length, true);
}
}  // namespace ruyijs
#endif
