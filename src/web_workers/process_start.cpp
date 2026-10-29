#include "web_workers/process.h"

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

namespace ruyijs::web_workers {
StartResult Process::Start(std::wstring_view executable, std::string initial, WorkerKind kind) noexcept {
  if (process_ || job_) return {StartError::Active};
  if (executable.empty() || executable.size() > 32700 ||
      executable.find_first_of(L"\"\r\n") != std::wstring_view::npos ||
      executable.find(L'\0') != std::wstring_view::npos || !Pipe::ValidFrameSize(initial.size()))
    return {StartError::InvalidInput};
  auto fail = [this](StartError error, unsigned system = 0) {
    Stop();return StartResult{error, system};
  };
  try {
    unsigned char random[16];
    const auto status = BCryptGenRandom(nullptr, random, sizeof(random), BCRYPT_USE_SYSTEM_PREFERRED_RNG);
    if (status) return fail(StartError::Random, unsigned(status));
    std::string name = "\\\\.\\pipe\\ruyijs-";
    for (unsigned char byte : random) {
      name += "0123456789abcdef"[byte >> 4];name += "0123456789abcdef"[byte & 15];
    }
    if (!pipe_.ListenAsync(name.c_str()) || !pipe_.Queue(std::move(initial)))
      return fail(StartError::Pipe, GetLastError());
    job_ = CreateJobObjectW(nullptr, nullptr);
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job_ || !SetInformationJobObject(job_, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
      return fail(StartError::Job, GetLastError());
    // Construct all allocating values before creating the suspended process.
    // Only the selected executable and our random pipe name enter this command.
    std::wstring path(executable);
    std::wstring command = L"\"" + path + L"\" --ruyijs-worker ";
    command.append(name.begin(), name.end());
    if (kind == WorkerKind::Service) command += L" --ruyijs-worker-kind service";
    else if (kind == WorkerKind::Shared) command += L" --ruyijs-worker-kind shared";
    STARTUPINFOW startup{};startup.cb = sizeof(startup);
    PROCESS_INFORMATION information{};
    if (!CreateProcessW(path.c_str(), command.data(), nullptr, nullptr, FALSE,
                        CREATE_NO_WINDOW | CREATE_SUSPENDED, nullptr, nullptr, &startup, &information))
      return fail(StartError::Create, GetLastError());
    process_ = information.hProcess;
    if (!AssignProcessToJobObject(job_, process_)) {
      const auto error = GetLastError();CloseHandle(information.hThread);
      return fail(StartError::Assign, error);
    }
    const auto resumed = ResumeThread(information.hThread);
    const auto error = resumed == DWORD(-1) ? GetLastError() : 0;
    CloseHandle(information.hThread);
    if (resumed == DWORD(-1)) return fail(StartError::Resume, error);
    return {};
  } catch (...) { return fail(StartError::Allocation); }
}
}

#else

#include <sys/types.h>
#include <unistd.h>
#include <stdlib.h>
#include <codecvt>
#include <locale>
#include <vector>

namespace ruyijs::web_workers {
StartResult Process::Start(std::wstring_view executable, std::string initial, WorkerKind kind) noexcept {
  if (process_) return {StartError::Active};
  if (executable.empty() || !Pipe::ValidFrameSize(initial.size()))
    return {StartError::InvalidInput};
  auto fail = [this](StartError error, unsigned system = 0) {
    Stop(); return StartResult{error, system};
  };
  try {
    uint8_t random[16];
    arc4random_buf(random, sizeof(random));
    std::string name = "/tmp/ruyijs-worker-";
    for (uint8_t byte : random) {
      name += "0123456789abcdef"[byte >> 4];
      name += "0123456789abcdef"[byte & 15];
    }
    if (!pipe_.ListenAsync(name.c_str()) || !pipe_.Queue(std::move(initial)))
      return fail(StartError::Pipe);

    std::wstring_convert<std::codecvt_utf8<wchar_t>> conv;
    std::string exe = conv.to_bytes(std::wstring(executable));

    pid_t p = fork();
    if (p < 0) return fail(StartError::Create);
    if (p == 0) {
      std::vector<const char*> args;
      args.push_back(exe.c_str());
      args.push_back("--ruyijs-worker");
      args.push_back(name.c_str());
      if (kind == WorkerKind::Service) {
        args.push_back("--ruyijs-worker-kind");
        args.push_back("service");
      } else if (kind == WorkerKind::Shared) {
        args.push_back("--ruyijs-worker-kind");
        args.push_back("shared");
      }
      args.push_back(nullptr);
      execv(exe.c_str(), const_cast<char* const*>(args.data()));
      _exit(127);
    }
    process_ = reinterpret_cast<void*>(static_cast<intptr_t>(p));
    return {};
  } catch (...) { return fail(StartError::Allocation); }
}
}

#endif
