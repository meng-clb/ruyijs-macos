#include <cstring>
#include "resource_network/necko_helper.h"

#ifdef _WIN32

namespace ruyijs::resource_network {
bool NeckoPythonPath(std::wstring* python) {
  wchar_t self[MAX_PATH];
  const DWORD length = GetModuleFileNameW(nullptr, self, MAX_PATH);
  if (!length || length >= MAX_PATH) return false;
  python->assign(self, length);
  auto slash = python->find_last_of(L"\\/");
  if (slash == std::wstring::npos || !slash) return false;
  slash = python->find_last_of(L"\\/", slash - 1);
  if (slash == std::wstring::npos) return false;
  *python = python->substr(0, slash) + L"\\vendor\\necko-derived\\python\\python.exe";
  return true;
}
}

#else

#include <mach-o/dyld.h>
#include <unistd.h>
#include <codecvt>
#include <locale>

namespace ruyijs::resource_network {
bool NeckoPythonPath(std::wstring* python) {
  char self[1024];
  uint32_t size = sizeof(self);
  if (_NSGetExecutablePath(self, &size) != 0) return false;
  std::string p(self);
  auto slash = p.find_last_of('/');
  if (slash == std::string::npos || !slash) return false;
  slash = p.find_last_of('/', slash - 1);
  if (slash == std::string::npos) return false;
  std::string py = p.substr(0, slash) + "/vendor/necko-derived/python/bin/python3";
  if (access(py.c_str(), X_OK) != 0) {
    py = "python3";
  }
  std::wstring_convert<std::codecvt_utf8<wchar_t>> conv;
  *python = conv.from_bytes(py);
  return true;
}
}

#endif
