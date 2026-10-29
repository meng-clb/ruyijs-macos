#include <zlib.h>

extern "C" {

int RUYIJS_CS_Z_deflateInit2_(z_streamp strm, int level, int method, int windowBits, int memLevel, int strategy, const char* version, int stream_size) {
    return deflateInit2_(strm, level, method, windowBits, memLevel, strategy, version, stream_size);
}

int RUYIJS_CS_Z_inflateInit2_(z_streamp strm, int windowBits, const char* version, int stream_size) {
    return inflateInit2_(strm, windowBits, version, stream_size);
}

int RUYIJS_CS_Z_deflate(z_streamp strm, int flush) {
    return deflate(strm, flush);
}

int RUYIJS_CS_Z_inflate(z_streamp strm, int flush) {
    return inflate(strm, flush);
}

int RUYIJS_CS_Z_deflateEnd(z_streamp strm) {
    return deflateEnd(strm);
}

int RUYIJS_CS_Z_inflateEnd(z_streamp strm) {
    return inflateEnd(strm);
}

}
