#pragma once
#include <charconv>
#include <cstdint>
#include <string_view>

namespace pvs::hash {

constexpr uint32_t kFnvBasis = 2166136261u;
constexpr uint32_t kFnvPrime = 16777619u;

inline constexpr uint32_t fnv_basis() { return kFnvBasis; }

inline constexpr uint32_t mix(uint32_t hash, unsigned char byte) {
  return (hash ^ byte) * kFnvPrime;
}

inline uint32_t fnv(std::string_view text) {
  uint32_t hash = kFnvBasis;
  for (unsigned char byte : text)
    hash = mix(hash, byte);
  return hash;
}

inline uint32_t append(std::string_view text, uint32_t hash) {
  for (unsigned char byte : text)
    hash = mix(hash, byte);
  return hash;
}

inline uint32_t append_int(uint32_t hash, int value) {
  char buffer[16];
  auto result = std::to_chars(buffer, buffer + sizeof(buffer), value);
  for (const char *cursor = buffer; cursor != result.ptr; ++cursor)
    hash = mix(hash, static_cast<unsigned char>(*cursor));
  return hash;
}

inline constexpr uint32_t key_hash(std::string_view text) {
  uint32_t hash = kFnvBasis;
  for (unsigned char byte : text)
    hash = (hash ^ byte) * kFnvPrime;
  return hash;
}

inline constexpr uint64_t key_id(std::string_view text) {
  return (uint64_t(text.size()) << 32) | key_hash(text);
}

} // namespace pvs::hash
