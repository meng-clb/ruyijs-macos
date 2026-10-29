#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif

#ifdef _WIN32
#include <windows.h>
#include <dwrite.h>
#include <wrl/client.h>
#endif

#include <hb.h>
#include <hb-ot.h>
#include <algorithm>
#include <array>
#include <string>
#include <memory>
#include <unordered_map>
#include <vector>
#include "web_geometry/system_font.h"

namespace ruyijs::web_geometry {

#ifdef _WIN32
template<class T> using ComPtr = Microsoft::WRL::ComPtr<T>;
struct SelectedFont {
  ComPtr<IDWriteFontFace> face;
  std::wstring family;
  unsigned weight = 400;
  bool italic = false, syntheticItalic = false;
};
// Lower-case family names the system collection does not list: substitutes map
// to another family name, legacy Win32 family names map to their faces.
struct FontAliases {
  std::unordered_map<std::wstring, std::wstring> substitutes;
  std::unordered_map<std::wstring, std::vector<ComPtr<IDWriteFont>>> faces;
};
ComPtr<IDWriteFont> AliasFace(const std::vector<ComPtr<IDWriteFont>>&, unsigned weight, bool italic);
struct FontCollection {
  ComPtr<IDWriteFactory> factory;
  std::unique_ptr<FontAliases> aliases;  // Read once, on the first unknown family.
  const FontAliases& Aliases();
  ComPtr<IDWriteFontCollection> fonts;
  std::vector<SelectedFont> selected;  // Maximum 32; no JS or layout results retained.
  std::unordered_map<std::string, std::vector<std::wstring>> families;
  std::unordered_map<uint64_t, SelectedFont> fallbacks;
  uint64_t config_generation = 0;
  bool Initialize();
  bool Select(const FontInput&, uint32_t codepoint, SelectedFont*, bool* missing = nullptr);
};
#else
struct SelectedFont {
  std::wstring family;
  unsigned weight = 400;
  bool italic = false, syntheticItalic = false;
};
struct FontAliases {
  std::unordered_map<std::wstring, std::wstring> substitutes;
};
struct FontCollection {
  bool Initialize() { return true; }
  bool Select(const FontInput&, uint32_t, SelectedFont* out, bool* missing = nullptr) {
    if (out) { out->family = L"sans-serif"; out->weight = 400; out->italic = false; }
    if (missing) *missing = false;
    return true;
  }
};
#endif

struct InkRect {
  double x = 0, y = 0, width = 0, height = 0;
  bool empty() const { return width <= 0 || height <= 0; }
  double x_most() const { return x + width; }
  double y_most() const { return y + height; }
  void Union(const InkRect& other) {
    if (empty()) { *this = other; return; }
    if (other.empty()) return;
    const double left = std::min(x, other.x), top = std::min(y, other.y);
    width = std::max(x_most(), other.x_most()) - left;
    height = std::max(y_most(), other.y_most()) - top;
    x = left;
    y = top;
  }
  void Scale(double factor) { x *= factor; y *= factor; width *= factor; height *= factor; }
};
struct FontRun {
  ruyijs::domain::geometry::SvgBox box{};
  std::array<double, 4> unrounded{};
  std::vector<int> advances, clusters;
  double ascent = 0, descent = 0;
  InkRect ink;
  std::vector<uint16_t> glyphs;
  std::vector<float> glyph_advances, glyph_offsets_x, glyph_offsets_y;
  std::vector<int32_t> raw_advances, raw_offsets_x, raw_offsets_y;
  std::vector<int> glyph_clusters;
  int advance = 0;
};
std::vector<std::wstring> FontFamilies(const FontInput&);
bool ShapeFont(const SelectedFont&, const FontInput&, const std::u16string&, FontRun*);
bool CanvasFontBaselines(const SelectedFont&, const FontInput&, CanvasTextMetrics*);
bool MissingFontRun(const SelectedFont&, const FontInput&, uint32_t codepoint,
                    size_t units, FontRun*);
}
