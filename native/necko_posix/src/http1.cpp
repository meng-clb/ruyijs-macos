// Bounded HTTP/1 framing behind the upstream standalone adapter's C ABI.
#include "core.h"
#include <algorithm>
#include <charconv>
#include <cstring>
#include <memory>
#include <stdexcept>
namespace {
constexpr size_t HeaderLimit = 65536, BodyLimit = 8 * 1024 * 1024;
struct Exchange {
  Read read; Write write; void* user;
  std::string incoming, headers, method;
  size_t sent = 0, length = 0, remaining = 0;
  bool request_chunked = false, chunked = false, close = false, eof = false, received = false;
  void Send(const std::string& value) {
    if (write(user, reinterpret_cast<const uint8_t*>(value.data()), uint32_t(value.size()))) throw 6;
  }
  bool Fill() {
    uint8_t data[16384]; uint32_t used = 0;
    if (read(user, data, sizeof(data), &used) || used > sizeof(data)) throw 6;
    if (!used) return false;
    incoming.append(reinterpret_cast<char*>(data), used); return true;
  }
  std::string Line() {
    for (;;) {
      auto pos = incoming.find("\r\n");
      if (pos != incoming.npos) { auto value = incoming.substr(0, pos); incoming.erase(0, pos + 2); return value; }
      if (incoming.size() > HeaderLimit || !Fill()) throw 6;
    }
  }
};
size_t Number(const std::string& s, int base = 10) {
  size_t value = 0;
  const auto result = std::from_chars(s.data(), s.data() + s.size(), value, base);
  if (s.empty() || result.ec != std::errc() || result.ptr != s.data() + s.size() || value > BodyLimit) throw 1;
  return value;
}
std::string Lower(std::string value) {
  for (auto& c : value) if (c >= 'A' && c <= 'Z') c += 'a' - 'A';
  return value;
}
std::string Trim(std::string value) {
  auto start = value.find_first_not_of(" \t"), end = value.find_last_not_of(" \t");
  return start == value.npos ? "" : value.substr(start, end - start + 1);
}
struct Fields { bool has_length = false, chunked = false, close = false; size_t length = 0; };
Fields Parse(const std::string& wire) {
  Fields result; size_t count = 0;
  for (size_t start = 0; start < wire.size();) {
    const auto end = wire.find("\r\n", start), colon = wire.find(':', start);
    if (end == wire.npos || colon >= end || colon == start || ++count > 256) throw 1;
    auto name = Lower(wire.substr(start, colon - start));
    for (auto c : name) if (c <= 32 || c >= 127 || std::string("()<>@,;:\\\"/[]?={}").find(c) != std::string::npos) throw 1;
    auto value = Trim(wire.substr(colon + 1, end - colon - 1));
    for (auto c : value) if ((uint8_t(c) < 32 && c != '\t') || uint8_t(c) == 127) throw 1;
    if (name == "content-length") {
      auto length = Number(value);
      if (result.has_length && length != result.length) throw 1;
      result.has_length = true; result.length = length;
    }
    if (name == "transfer-encoding") { if (Lower(value) != "chunked" || result.chunked) throw 1; result.chunked = true; }
    if (name == "connection" && Lower(value).find("close") != std::string::npos) result.close = true;
    start = end + 2;
  }
  if (result.chunked && result.has_length) throw 1;
  return result;
}
template<class F> int Guard(F fn) { try { fn(); return 0; } catch (int n) { return n; } catch (...) { return 6; } }
}
extern "C" {
int necko_exchange_open(const char* method, const char* target, const char* headers,
                       Read read, Write write, void* user, void** output) {
  if (!output || !method || !target || !headers || !read || !write) return 1;
  *output = nullptr;
  return Guard([&] {
    const std::string m(method), path(target), wire(headers);
    if (m.empty() || path.empty() || wire.size() > HeaderLimit ||
        m.find_first_of(" \r\n\t") != m.npos || path.find_first_of(" \r\n\t") != path.npos) throw 1;
    const auto fields = Parse(wire);
    auto ex = std::make_unique<Exchange>();
    ex->method = m; ex->read = read; ex->write = write; ex->user = user;
    ex->length = fields.length; ex->request_chunked = fields.chunked; ex->close = fields.close;
    ex->Send(m + " " + path + " HTTP/1.1\r\n" + wire + "\r\n"); *output = ex.release();
  });
}
int necko_exchange_write(void* value, const uint8_t* data, uint32_t size) {
  return Guard([&] {
    auto& ex = *static_cast<Exchange*>(value);
    if (ex.received || size > BodyLimit - ex.sent || (!ex.request_chunked && size > ex.length - ex.sent)) throw 1;
    if (ex.request_chunked && size) { char hex[24]; auto end = std::to_chars(hex, hex + sizeof(hex), size, 16).ptr;
      ex.Send(std::string(hex, end) + "\r\n" + std::string(reinterpret_cast<const char*>(data), size) + "\r\n"); }
    else if (size) ex.Send(std::string(reinterpret_cast<const char*>(data), size));
    ex.sent += size;
  });
}
int necko_exchange_receive(void* value) {
  return Guard([&] {
    auto& ex = *static_cast<Exchange*>(value);
    if (ex.received || (!ex.request_chunked && ex.sent != ex.length)) throw 1;
    if (ex.request_chunked) ex.Send("0\r\n\r\n");
    size_t total = 0;
    for (;;) {
      auto status = ex.Line();
      if (status.size() < 12 || (status.substr(0, 9) != "HTTP/1.1 " && status.substr(0, 9) != "HTTP/1.0 ")) throw 6;
      int code = 0; const auto converted = std::from_chars(status.data() + 9, status.data() + 12, code);
      if (converted.ec != std::errc() || converted.ptr != status.data() + 12 || code < 100 || code > 599) throw 6;
      std::string fields;
      for (;;) { auto line = ex.Line(); total += line.size() + 2; if (total > HeaderLimit) throw 6;
        if (line.empty()) break; fields += line + "\r\n"; }
      const auto parsed = Parse(fields);
      if (code < 200 && code != 101) continue;
      ex.headers = status + "\r\n" + fields + "\r\n";
      ex.close |= parsed.close || status.substr(0, 8) == "HTTP/1.0" || code == 101;
      ex.chunked = parsed.chunked; ex.remaining = parsed.length;
      ex.eof = ex.method == "HEAD" || code == 204 || code == 304 || code == 101;
      if (!ex.eof && !parsed.has_length && !ex.chunked) { ex.remaining = SIZE_MAX; ex.close = true; }
      ex.eof |= !ex.chunked && !ex.remaining; ex.received = true; break;
    }
  });
}
const char* necko_exchange_headers(void* value) { return static_cast<Exchange*>(value)->headers.c_str(); }
int necko_exchange_read(void* value, uint8_t* data, uint32_t capacity, uint32_t* used) {
  if (!used) return 1; *used = 0;
  return Guard([&] {
    auto& ex = *static_cast<Exchange*>(value); if (!ex.received) throw 1;
    if (ex.eof || !capacity) return;
    if (ex.chunked && !ex.remaining) {
      auto line = ex.Line(); ex.remaining = Number(line.substr(0, line.find(';')), 16);
      if (!ex.remaining) { size_t total = 0; do { line = ex.Line(); total += line.size() + 2;
          if (total > HeaderLimit) throw 6; } while (!line.empty()); ex.eof = true; return; }
    }
    if (ex.incoming.empty() && !ex.Fill()) { if (ex.remaining != SIZE_MAX) throw 6; ex.eof = true; return; }
    const auto n = std::min({size_t(capacity), ex.incoming.size(), ex.remaining});
    memcpy(data, ex.incoming.data(), n); ex.incoming.erase(0, n); *used = uint32_t(n);
    if (ex.remaining != SIZE_MAX) ex.remaining -= n;
    if (!ex.remaining) {
      if (ex.chunked) { if (!ex.Line().empty()) throw 6; }
      else ex.eof = true;
    }
  });
}
int necko_exchange_reusable(void* value) { auto& ex = *static_cast<Exchange*>(value); return ex.eof && !ex.close && ex.incoming.empty(); }
void necko_exchange_close(void* value) { delete static_cast<Exchange*>(value); }
}
