#pragma once
// The face a canvas glyph run carries, as one global name. Windows: the
// DirectWrite COM face. Darwin: the Core Text shim font_backend.h defines.
// Linux: the FreeType-backed SkTypeface that web_geometry/font_posix.cpp shapes.
#if defined(__linux__)
class SkTypeface;
using IDWriteFontFace = SkTypeface;
#else
struct IDWriteFontFace;
#endif
