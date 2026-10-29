#include "web_workers/process.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

namespace ruyijs::web_workers {
Process::~Process() { Stop(); }
bool Process::Running() const {
  return process_ && WaitForSingleObject(process_, 0) == WAIT_TIMEOUT;
}
unsigned Process::id() const { return process_ ? GetProcessId(process_) : 0; }
bool Process::Queue(std::string frame) {
  return Running() && pipe_.Queue(std::move(frame));
}
PipeResult Process::Poll(std::string* frame, bool* received) {
  const auto result = pipe_.Poll(frame, received);
  if (!*received && result == PipeResult::Pending && !pipe_.connected() && !Running())
    return PipeResult::Closed;
  return result;
}
bool Process::Stop() {
  if (job_) { CloseHandle(job_);job_ = nullptr; }
  bool stopped = true;
  if (process_) {
    if (Running()) TerminateProcess(process_, 1);
    stopped = WaitForSingleObject(process_, 5000) == WAIT_OBJECT_0;
    CloseHandle(process_);process_ = nullptr;
  }
  pipe_.Close();
  return stopped;
}
}

#else

#include <sys/types.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>

namespace ruyijs::web_workers {
Process::~Process() { Stop(); }
bool Process::Running() const {
  if (!process_) return false;
  pid_t pid = static_cast<pid_t>(reinterpret_cast<intptr_t>(process_));
  int status = 0;
  pid_t r = waitpid(pid, &status, WNOHANG);
  return r == 0;
}
unsigned Process::id() const {
  return process_ ? static_cast<unsigned>(reinterpret_cast<intptr_t>(process_)) : 0;
}
bool Process::Queue(std::string frame) {
  return Running() && pipe_.Queue(std::move(frame));
}
PipeResult Process::Poll(std::string* frame, bool* received) {
  const auto result = pipe_.Poll(frame, received);
  if (!*received && result == PipeResult::Pending && !pipe_.connected() && !Running())
    return PipeResult::Closed;
  return result;
}
bool Process::Stop() {
  if (process_) {
    pid_t pid = static_cast<pid_t>(reinterpret_cast<intptr_t>(process_));
    if (Running()) kill(pid, SIGKILL);
    int status;
    waitpid(pid, &status, 0);
    process_ = nullptr;
  }
  pipe_.Close();
  return true;
}
}

#endif
