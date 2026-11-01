// Core Text behind the DirectWrite face the shared shaper already calls.
// The face is created at size = unitsPerEm, so Core Text advances and the
// font box are design units. TryGetFontTable receives the DirectWrite tag
// (byte-swapped from the HarfBuzz tag) and swaps it back for CTFontCopyTable.
// Darwin only: on Windows IDWriteFontFace is DirectWrite's own interface, and
// tools/build.py compiles every src/ unit on both platforms.
#ifndef _WIN32
#include "web_geometry/font_backend.h"

#include <CoreText/CoreText.h>

#include <cmath>
#include <cstdint>

namespace {
uint16_t ClampU16(double value) {
  if (!(value > 0)) return 0;
  if (value > 65535) return 65535;
  return uint16_t(std::lround(value));
}
int16_t ClampI16(double value) {
  if (value > 32767) return 32767;
  if (value < -32768) return -32768;
  return int16_t(std::lround(value));
}
}

IDWriteFontFace::IDWriteFontFace(const void* font) : font_(const_cast<void*>(font)) {}
IDWriteFontFace::~IDWriteFontFace() {
  if (font_) CFRelease(static_cast<CTFontRef>(font_));
}
void* IDWriteFontFace::CoreFont() const { return font_; }

void IDWriteFontFace::GetMetrics(DWRITE_FONT_METRICS* metrics) const {
  *metrics = {};
  CTFontRef font = static_cast<CTFontRef>(font_);
  if (!font) return;
  metrics->designUnitsPerEm = ClampU16(CTFontGetUnitsPerEm(font));
  metrics->ascent = ClampU16(CTFontGetAscent(font));
  metrics->descent = ClampU16(CTFontGetDescent(font));
  metrics->lineGap = ClampI16(CTFontGetLeading(font));
  metrics->capHeight = ClampU16(CTFontGetCapHeight(font));
  metrics->xHeight = ClampU16(CTFontGetXHeight(font));
}

HRESULT IDWriteFontFace::GetGlyphIndices(const uint32_t* codepoints, uint32_t count,
                                         uint16_t* glyphs) const {
  if (!codepoints || !glyphs) return count ? -1 : 0;
  CTFontRef font = static_cast<CTFontRef>(font_);
  if (!font) return -1;
  for (uint32_t i = 0; i < count; ++i) {
    glyphs[i] = 0;
    uint32_t code = codepoints[i];
    if (code > 0x10FFFF) continue;
    UniChar chars[2];
    CGGlyph mapped[2] = {};
    CFIndex length = 1;
    if (code >= 0x10000) {
      code -= 0x10000;
      chars[0] = UniChar(0xD800 + (code >> 10));
      chars[1] = UniChar(0xDC00 + (code & 0x3FF));
      length = 2;
    } else {
      chars[0] = UniChar(code);
    }
    if (CTFontGetGlyphsForCharacters(font, chars, mapped, length) && mapped[0])
      glyphs[i] = mapped[0];
  }
  return 0;
}

HRESULT IDWriteFontFace::GetDesignGlyphMetrics(const uint16_t* glyphs, uint32_t count,
                                               DWRITE_GLYPH_METRICS* metrics, BOOL) const {
  if (!glyphs || !metrics) return count ? -1 : 0;
  CTFontRef font = static_cast<CTFontRef>(font_);
  if (!font) return -1;
  for (uint32_t i = 0; i < count; ++i) {
    const CGGlyph glyph = glyphs[i];
    CGSize advance{};
    CTFontGetAdvancesForGlyphs(font, kCTFontOrientationHorizontal, &glyph, &advance, 1);
    if (!std::isfinite(advance.width)) advance.width = 0;
    CGRect box =
        CTFontGetBoundingRectsForGlyphs(font, kCTFontOrientationHorizontal, &glyph, nullptr, 1);
    if (!std::isfinite(box.origin.x) || !std::isfinite(box.origin.y) ||
        !std::isfinite(box.size.width) || !std::isfinite(box.size.height))
      box = CGRectZero;
    const int32_t advance_width = int32_t(std::lround(advance.width));
    const int32_t left = int32_t(std::lround(box.origin.x));
    const int32_t black_width = int32_t(std::lround(box.size.width));
    const double y_max = box.origin.y + box.size.height;
    const double y_min = box.origin.y;
    const int32_t black_height = int32_t(std::lround(y_max - y_min));
    // Shaping reads Y-down ink as (topSideBearing - verticalOriginY, black box).
    // verticalOriginY at the top of the box and a zero top bearing produce that.
    metrics[i] = {};
    metrics[i].leftSideBearing = left;
    metrics[i].advanceWidth = advance_width > 0 ? uint32_t(advance_width) : 0;
    metrics[i].rightSideBearing = advance_width - left - black_width;
    metrics[i].topSideBearing = 0;
    metrics[i].advanceHeight = black_height > 0 ? uint32_t(black_height) : 0;
    metrics[i].bottomSideBearing = 0;
    metrics[i].verticalOriginY = int32_t(std::lround(y_max));
  }
  return 0;
}

HRESULT IDWriteFontFace::GetGdiCompatibleGlyphMetrics(FLOAT, FLOAT, const void*, BOOL,
                                                      const uint16_t* glyphs, UINT32 count,
                                                      DWRITE_GLYPH_METRICS* metrics,
                                                      BOOL sideways) const {
  return GetDesignGlyphMetrics(glyphs, count, metrics, sideways);
}

HRESULT IDWriteFontFace::TryGetFontTable(UINT32 tag, const void** data, UINT32* size,
                                         void** context, BOOL* exists) const {
  if (data) *data = nullptr;
  if (size) *size = 0;
  if (context) *context = nullptr;
  if (exists) *exists = FALSE;
  CTFontRef font = static_cast<CTFontRef>(font_);
  if (!font || !data || !size || !context || !exists) return -1;
  const uint32_t os_type = _byteswap_ulong(tag);
  CFDataRef table = CTFontCopyTable(font, os_type, kCTFontTableOptionNoOptions);
  if (!table) return 0;
  const CFIndex length = CFDataGetLength(table);
  if (length <= 0) {
    CFRelease(table);
    return 0;
  }
  *exists = TRUE;
  *data = CFDataGetBytePtr(table);
  *size = UINT32(length);
  *context = const_cast<void*>(static_cast<const void*>(table));
  return 0;
}

void IDWriteFontFace::ReleaseFontTable(void* context) const {
  if (context) CFRelease(static_cast<CFDataRef>(context));
}
void IDWriteFontFace::AddRef() const {}
void IDWriteFontFace::Release() const {}
#endif  // !_WIN32
