#include "web_geometry/font_backend.h"
#include "firefox_font_prefs.h"
#include "web_geometry/font_config.h"
#include <cstring>
#include <mutex>
#ifdef _WIN32
#pragma comment(lib, "user32.lib")  // SystemParametersInfoW (system-ui menu font)
#else
#include <codecvt>
#include <locale>
#endif

namespace ruyijs::web_geometry {
namespace {
std::wstring Wide(const std::string& text) {
#ifdef _WIN32
  const int size = MultiByteToWideChar(CP_UTF8, 0, text.data(), int(text.size()), nullptr, 0);
  std::wstring result(size, L'\0');
  MultiByteToWideChar(CP_UTF8, 0, text.data(), int(text.size()), result.data(), size);
  return result;
#else
  std::wstring_convert<std::codecvt_utf8<wchar_t>> conv;
  return conv.from_bytes(text);
#endif
}
std::mutex g_language_lock;
std::string g_language;  // The browser locale; the OS locale when unset.
std::string Group(const std::string& language) {
  auto value = language;
  if (value.empty()) {
    std::lock_guard<std::mutex> guard(g_language_lock);
    value = g_language;
  }
  if (value.empty()) {
#ifdef _WIN32
    wchar_t locale[LOCALE_NAME_MAX_LENGTH]{};
    if (GetUserDefaultLocaleName(locale, LOCALE_NAME_MAX_LENGTH))
      for (wchar_t ch : locale) { if (!ch) break; value += char(ch); }
#else
    value = "en-US";
#endif
  }
  for (char& ch : value) if (ch >= 'A' && ch <= 'Z') ch += 'a'-'A';
  if (value.starts_with("zh"))
    return value.find("tw") != value.npos || value.find("hant") != value.npos ? "zh-TW"
        : value.find("hk") != value.npos ? "zh-HK" : "zh-CN";
  for (const char* code : {"ja", "ko", "ar", "he", "th", "el"})
    if (value.starts_with(code)) return code;
  if (value.starts_with("ru") || value.starts_with("uk") || value.starts_with("bg")) return "x-cyrillic";
  return "x-western";
}
std::string Pref(const std::string& name) {
  for (const auto& entry : kFontPreferences) if (name == entry.key) return entry.value;
  return {};
}
// Splits a family list; `quoted` (when given) records which names were
// strings, since only an unquoted identifier can be a generic family.
void Split(const std::string& value, std::vector<std::wstring>* out,
           std::vector<bool>* quoted = nullptr) {
  size_t start = 0; char quote = 0;
  for (size_t i = 0; i <= value.size(); ++i) {
    char ch = i < value.size() ? value[i] : ',';
    if (quote) { if (ch == quote) quote = 0; }
    else if (ch == '\'' || ch == '"') quote = ch;
    else if (ch == ',') {
      auto item = value.substr(start, i-start); start = i+1;
      const auto begin = item.find_first_not_of(" \t\r\n\"'");
      const auto end = item.find_last_not_of(" \t\r\n\"'");
      if (begin == item.npos) continue;
      out->push_back(Wide(item.substr(begin, end-begin+1)));
      if (quoted) quoted->push_back(item.find_first_of("\"'") != item.npos);
    }
  }
}
// LookAndFeel's StyleSystemFont::Menu on Windows: the non-client menu font.
std::wstring MenuFont() {
#ifdef _WIN32
  NONCLIENTMETRICSW metrics{}; metrics.cbSize = sizeof(metrics);
  if (!SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof(metrics), &metrics, 0)) return {};
  return metrics.lfMenuFont.lfFaceName;
#else
  return L"Helvetica Neue";
#endif
}
}
void SetBrowserLanguage(const std::string& language) {
  std::lock_guard<std::mutex> guard(g_language_lock);
  g_language = language;
}
std::string DefaultGenericFamily() {
  const auto generic = Pref("font.default." + Group({}));
  return generic.empty() ? "serif" : generic;
}
std::vector<std::wstring> FontFamilies(const FontInput& input) {
  std::vector<std::wstring> declared, result;
  std::vector<bool> quoted;
  Split(input.family, &declared, &quoted);
  const auto group = Group(input.language);
  for (size_t i = 0; i < declared.size(); ++i) {
    auto name = declared[i];
    if (!quoted[i] && name == L"-moz-default") {
      const auto generic = DefaultGenericFamily();
      name.assign(generic.begin(), generic.end());
    }
    if (!quoted[i] && (name == L"serif" || name == L"sans-serif" || name == L"monospace" ||
        name == L"cursive" || name == L"fantasy" || name == L"system-ui")) {
      const std::string generic(name.begin(), name.end());
      if (const auto forced = GenericFamilyOverride(generic); !forced.empty()) {
        result.push_back(Wide(forced));
      } else {
        Split(Pref("font.name."+generic+"."+group), &result);
        Split(Pref("font.name-list."+generic+"."+group), &result);
      }
      if (name == L"system-ui")
        if (auto menu = MenuFont(); !menu.empty()) result.push_back(menu);
    } else result.push_back(name);
  }
  Split(Pref("font.name-list.emoji"), &result);
  for (const auto& lang : {group, std::string("x-western")}) {
    auto generic = Pref("font.default."+lang);
    if (generic.empty()) generic = "serif";
    Split(Pref("font.name."+generic+"."+lang), &result);
    Split(Pref("font.name-list."+generic+"."+lang), &result);
  }
  return result;
}
}
