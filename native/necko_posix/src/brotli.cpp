// Caller-bounded Brotli decoder for the upstream strict decoding chain.
#include <brotli/decode.h>
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
namespace {
struct Decoder { size_t used = 0, peak = 0, limit; bool refused = false; BrotliDecoderState* state = nullptr; };
struct alignas(std::max_align_t) Block { size_t size; };
void* Allocate(void* user, size_t size) {
  auto& d = *static_cast<Decoder*>(user);
  if (size > d.limit - d.used || size > SIZE_MAX - sizeof(Block)) { d.refused = true; return nullptr; }
  auto* block = static_cast<Block*>(malloc(sizeof(Block) + size));
  if (!block) return nullptr;
  block->size = size; d.used += size; d.peak = std::max(d.peak, d.used); return block + 1;
}
void Free(void* user, void* value) {
  if (!value) return;
  auto* block = static_cast<Block*>(value) - 1;
  static_cast<Decoder*>(user)->used -= block->size; free(block);
}
}
extern "C" {
uint32_t rb_version() { return BrotliDecoderVersion(); }
void* rb_create(size_t limit) {
  auto* d = new Decoder; d->limit = limit;
  d->state = BrotliDecoderCreateInstance(Allocate, Free, d);
  if (!d->state) { delete d; return nullptr; } return d;
}
int rb_process(void* value, const uint8_t* source, size_t* consumed, uint8_t* output, size_t* produced) {
  auto& d = *static_cast<Decoder*>(value); size_t available_in = *consumed, available_out = *produced;
  const auto result = BrotliDecoderDecompressStream(d.state, &available_in, &source, &available_out, &output, nullptr);
  *consumed -= available_in; *produced -= available_out; return result;
}
size_t rb_used(void* value) { return static_cast<Decoder*>(value)->used; }
size_t rb_peak(void* value) { return static_cast<Decoder*>(value)->peak; }
int rb_refused(void* value) { return static_cast<Decoder*>(value)->refused; }
int rb_error(void* value) { return BrotliDecoderGetErrorCode(static_cast<Decoder*>(value)->state); }
size_t rb_close(void* value) {
  auto* d = static_cast<Decoder*>(value); BrotliDecoderDestroyInstance(d->state);
  auto remaining = d->used; delete d; return remaining;
}
}
