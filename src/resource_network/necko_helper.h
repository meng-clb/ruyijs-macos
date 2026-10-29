#pragma once
#include "resource_network/necko_pipe.h"
#include <mutex>
#include <string>
#include <vector>

#ifdef _WIN32

namespace ruyijs::resource_network {
class NeckoHelper {
 public:
  ~NeckoHelper() {
    if (process_ && WaitForSingleObject(process_.Get(), 0) != WAIT_OBJECT_0) {
      TerminateProcess(process_.Get(), 1);
      job_.Reset();
      WaitForSingleObject(process_.Get(), 5000);
    }
  }
  bool Start(const std::wstring& python, NeckoPipe& input, NeckoPipe& output, const wchar_t* mode) {
    std::lock_guard<std::mutex> guard(lock_);
    job_.Reset(CreateJobObjectW(nullptr, nullptr));
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!job_ || !SetInformationJobObject(job_.Get(), JobObjectExtendedLimitInformation,
        &limits, sizeof(limits))) return false;
    SECURITY_ATTRIBUTES inherit{sizeof(inherit), nullptr, TRUE};
    NeckoHandle errors(CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_WRITE | FILE_SHARE_READ,
        &inherit, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (!errors) return false;
    HANDLE inherited[] = {input.Child(), output.Child(), errors.Get()};
    SIZE_T size = 0;
    InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
    std::vector<unsigned char> storage(size);
    auto* attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
    if (!InitializeProcThreadAttributeList(attributes, 1, 0, &size)) return false;
    const BOOL restricted = UpdateProcThreadAttribute(attributes, 0,
        PROC_THREAD_ATTRIBUTE_HANDLE_LIST, inherited, sizeof(inherited), nullptr, nullptr);
    STARTUPINFOEXW startup{};
    startup.StartupInfo.cb = sizeof(startup);
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
    startup.StartupInfo.hStdInput = input.Child();
    startup.StartupInfo.hStdOutput = output.Child();
    startup.StartupInfo.hStdError = errors.Get();
    startup.lpAttributeList = attributes;
    std::wstring command = L"\"" + python + L"\" -I -B -m ruyijs_necko.oneshot";
    if (mode && *mode) { command += L" "; command += mode; }
    PROCESS_INFORMATION process{};
    const BOOL created = restricted && CreateProcessW(python.c_str(), command.data(), nullptr,
        nullptr, TRUE, CREATE_NO_WINDOW | CREATE_SUSPENDED | EXTENDED_STARTUPINFO_PRESENT,
        nullptr, nullptr, &startup.StartupInfo, &process);
    DeleteProcThreadAttributeList(attributes);
    if (!created) return false;
    process_.Reset(process.hProcess);
    NeckoHandle thread(process.hThread);
    return AssignProcessToJobObject(job_.Get(), process_.Get()) &&
        ResumeThread(thread.Get()) != DWORD(-1);
  }
  void Cancel() {
    std::lock_guard<std::mutex> guard(lock_);
    if (process_) TerminateProcess(process_.Get(), ERROR_OPERATION_ABORTED);
  }
  bool Finish(ULONGLONG deadline) {
    DWORD status = 1;
    return WaitForSingleObject(process_.Get(), NeckoRemaining(deadline)) == WAIT_OBJECT_0 &&
        GetExitCodeProcess(process_.Get(), &status) && status == 0;
  }
 private:
  std::mutex lock_;
  NeckoHandle process_, job_;
};
bool NeckoPythonPath(std::wstring*);
}

#else

#include <sys/types.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>
#include <codecvt>
#include <locale>

#if defined(__APPLE__)
#include <mach-o/dyld.h>
#endif

namespace ruyijs::resource_network {
class NeckoHelper {
 public:
  ~NeckoHelper() {
    if (pid_ > 0) {
      kill(pid_, SIGKILL);
      int status;
      waitpid(pid_, &status, 0);
      pid_ = -1;
    }
  }
  bool Start(const std::wstring& python, NeckoPipe& input, NeckoPipe& output, const wchar_t* mode) {
    std::lock_guard<std::mutex> guard(lock_);
    std::wstring_convert<std::codecvt_utf8<wchar_t>> conv;
    std::string py = conv.to_bytes(python);
    std::string m = mode ? conv.to_bytes(mode) : "";

    pid_t p = fork();
    if (p < 0) return false;
    if (p == 0) {
      // Child process
      dup2(static_cast<int>(input.Child()), STDIN_FILENO);
      dup2(static_cast<int>(output.Child()), STDOUT_FILENO);

      const char* envWorker = getenv("GHOSTFOX_NECKO_WORKER");
      std::string workerPath = envWorker ? envWorker : "";
      if (workerPath.empty()) {
#if defined(__APPLE__)
        char self[1024];
        uint32_t size = sizeof(self);
        if (_NSGetExecutablePath(self, &size) == 0) {
          std::string s(self);
          auto slash = s.find_last_of('/');
          if (slash != std::string::npos) {
            std::string candidate = s.substr(0, slash) + "/ghostfox-worker";
            if (access(candidate.c_str(), X_OK) == 0) {
              workerPath = candidate;
            }
          }
        }
#endif
      }
      if (!workerPath.empty()) {
        execl(workerPath.c_str(), workerPath.c_str(), nullptr);
        _exit(127);
      }

      std::vector<const char*> args;
      args.push_back(py.c_str());
      args.push_back("-I");
      args.push_back("-B");
      args.push_back("-m");
      args.push_back("ruyijs_necko.oneshot");
      if (!m.empty()) {
        args.push_back(m.c_str());
      }
      args.push_back(nullptr);
      execvp(py.c_str(), const_cast<char* const*>(args.data()));
      _exit(127);
    }
    pid_ = p;
    input.CloseChild();
    output.CloseChild();
    return true;
  }
  void Cancel() {
    std::lock_guard<std::mutex> guard(lock_);
    if (pid_ > 0) {
      kill(pid_, SIGKILL);
    }
  }
  bool Finish(ULONGLONG deadline) {
    if (pid_ <= 0) return false;
    while (NeckoRemaining(deadline) > 0) {
      int status = 0;
      pid_t res = waitpid(pid_, &status, WNOHANG);
      if (res == pid_) {
        pid_ = -1;
        return WIFEXITED(status) && WEXITSTATUS(status) == 0;
      } else if (res < 0) {
        pid_ = -1;
        return false;
      }
      usleep(10000); // 10ms
    }
    return false;
  }
 private:
  std::mutex lock_;
  pid_t pid_{-1};
};
bool NeckoPythonPath(std::wstring*);
}

#endif
