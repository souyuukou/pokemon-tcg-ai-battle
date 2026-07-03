#pragma once
#include "pvs_state.hpp"
#include <cstring>
#include <span>
#include <string>
#include <string_view>

namespace pvs::wire {

constexpr char kMagic[8] = {'P', 'K', 'O', 'B', 'S', '1', '\0', '\0'};
constexpr uint32_t kVersion = 2;
constexpr uint32_t kFlagHasSelect = 1u;
constexpr uint32_t kFlagHasSearchBegin = 2u;

inline void append_bytes(std::string &out, const void *data, size_t size) {
  out.append(reinterpret_cast<const char *>(data), size);
}

template <class T> inline void append_pod(std::string &out, const T &value) {
  append_bytes(out, &value, sizeof(T));
}

inline bool read_bytes(std::string_view &in, void *data, size_t size) {
  if (in.size() < size)
    return false;
  std::memcpy(data, in.data(), size);
  in.remove_prefix(size);
  return true;
}

template <class T> inline bool read_pod(std::string_view &in, T &value) {
  return read_bytes(in, &value, sizeof(T));
}

inline bool read_u8(std::string_view &in, uint8_t &value) {
  return read_pod(in, value);
}

inline bool read_i8(std::string_view &in, int8_t &value) {
  return read_pod(in, value);
}

inline bool read_i16(std::string_view &in, int16_t &value) {
  return read_pod(in, value);
}

inline bool read_i32(std::string_view &in, int32_t &value) {
  return read_pod(in, value);
}

inline bool read_u16(std::string_view &in, uint16_t &value) {
  return read_pod(in, value);
}

inline bool read_u32(std::string_view &in, uint32_t &value) {
  return read_pod(in, value);
}

inline bool read_f64(std::string_view &in, double &value) {
  return read_pod(in, value);
}

inline bool read_string(std::string_view &in, std::string &out) {
  uint32_t len = 0;
  if (!read_u32(in, len) || in.size() < len)
    return false;
  out.assign(in.data(), len);
  in.remove_prefix(len);
  return true;
}

inline void write_pokemon(std::string &out, const PokemonSlot &slot) {
  uint8_t flags = uint8_t(slot.present) | (uint8_t(slot.face_down) << 1u);
  append_pod(out, flags);
  append_pod(out, slot.id);
  append_pod(out, slot.hp);
  append_pod(out, slot.energy_count);
  append_pod(out, slot.pre_evolution_count);
  append_pod(out, uint8_t(slot.attached_ids.size()));
  for (int32_t id : slot.attached_ids)
    append_pod(out, id);
}

inline bool read_pokemon(std::string_view &in, PokemonSlot &slot) {
  uint8_t flags = 0, attached_count = 0;
  if (!read_u8(in, flags) || !read_i32(in, slot.id) || !read_i16(in, slot.hp) ||
      !read_u8(in, slot.energy_count) || !read_u8(in, slot.pre_evolution_count) ||
      !read_u8(in, attached_count))
    return false;
  slot.present = (flags & 1u) != 0;
  slot.face_down = (flags & 2u) != 0;
  slot.attached_ids.resize(attached_count);
  for (auto &id : slot.attached_ids)
    if (!read_i32(in, id))
      return false;
  return true;
}

inline void write_player(std::string &out, const PlayerView &player) {
  append_pod(out, player.deck_count);
  append_pod(out, player.hand_count);
  append_pod(out, uint8_t(player.prize.size()));
  for (int32_t id : player.prize)
    append_pod(out, id);
  append_pod(out, uint8_t(player.hand.size()));
  for (const auto &card : player.hand)
    append_pod(out, card.id);
  append_pod(out, uint8_t(player.active.size()));
  for (const auto &slot : player.active)
    write_pokemon(out, slot);
  append_pod(out, uint8_t(player.bench.size()));
  for (const auto &slot : player.bench)
    write_pokemon(out, slot);
  append_pod(out, uint8_t(player.discard.size()));
  for (const auto &card : player.discard)
    append_pod(out, card.id);
}

inline bool read_player(std::string_view &in, PlayerView &player) {
  uint8_t prize_count = 0, hand_count = 0, active_count = 0, bench_count = 0,
          discard_count = 0;
  if (!read_i16(in, player.deck_count) || !read_i16(in, player.hand_count) ||
      !read_u8(in, prize_count))
    return false;
  player.prize.resize(prize_count);
  for (auto &id : player.prize)
    if (!read_i32(in, id))
      return false;
  if (!read_u8(in, hand_count))
    return false;
  player.hand.resize(hand_count);
  for (auto &card : player.hand)
    if (!read_i32(in, card.id))
      return false;
  if (!read_u8(in, active_count))
    return false;
  player.active.resize(active_count);
  for (auto &slot : player.active)
    if (!read_pokemon(in, slot))
      return false;
  if (!read_u8(in, bench_count))
    return false;
  player.bench.resize(bench_count);
  for (auto &slot : player.bench)
    if (!read_pokemon(in, slot))
      return false;
  if (!read_u8(in, discard_count))
    return false;
  player.discard.resize(discard_count);
  for (auto &card : player.discard)
    if (!read_i32(in, card.id))
      return false;
  return true;
}

inline void write_option(std::string &out, const OptionView &option) {
  append_pod(out, option.type);
  append_pod(out, option.card_id);
  append_pod(out, option.attack_id);
  append_pod(out, option.area);
  append_pod(out, option.index);
  append_pod(out, option.player_index);
  append_pod(out, option.in_play_area);
  append_pod(out, option.in_play_index);
  append_pod(out, option.number);
  append_pod(out, option.count);
  append_pod(out, option.special_condition_type);
  append_pod(out, option.tool_index);
  append_pod(out, option.energy_index);
  append_pod(out, option.serial);
}

inline bool read_option(std::string_view &in, OptionView &option) {
  return read_i16(in, option.type) && read_i32(in, option.card_id) &&
         read_i32(in, option.attack_id) && read_i16(in, option.area) &&
         read_i16(in, option.index) && read_i16(in, option.player_index) &&
         read_i16(in, option.in_play_area) &&
         read_i16(in, option.in_play_index) && read_i16(in, option.number) &&
         read_i16(in, option.count) &&
         read_i16(in, option.special_condition_type) &&
         read_i16(in, option.tool_index) && read_i16(in, option.energy_index) &&
         read_i32(in, option.serial);
}

inline std::string encode(const GameState &state) {
  std::string out;
  out.reserve(512);
  append_bytes(out, kMagic, 8);
  append_pod(out, kVersion);
  uint32_t flags = 0;
  if (state.has_select)
    flags |= kFlagHasSelect;
  if (!state.search_begin_input.empty())
    flags |= kFlagHasSearchBegin;
  append_pod(out, flags);
  append_pod(out, state.remaining_overage_time);
  if (flags & kFlagHasSearchBegin) {
    append_pod(out, uint32_t(state.search_begin_input.size()));
    append_bytes(out, state.search_begin_input.data(),
                 state.search_begin_input.size());
  }
  append_pod(out, state.current.result);
  append_pod(out, state.current.your_index);
  append_pod(out, state.current.first_player);
  append_pod(out, state.current.turn);
  append_pod(out, state.current.turn_action_count);
  uint16_t stadium_count = uint16_t(state.current.stadium.size());
  uint16_t looking_count = uint16_t(state.current.looking.size());
  append_pod(out, stadium_count);
  for (const auto &card : state.current.stadium) {
    append_pod(out, card.id);
    append_pod(out, card.player_index);
  }
  append_pod(out, looking_count);
  for (const auto &card : state.current.looking) {
    append_pod(out, card.id);
    append_pod(out, card.player_index);
  }
  write_player(out, state.current.players[0]);
  write_player(out, state.current.players[1]);
  if (flags & kFlagHasSelect) {
    append_pod(out, state.select.context);
    append_pod(out, state.select.min_count);
    append_pod(out, state.select.max_count);
    append_pod(out, uint16_t(state.select.options.size()));
    for (const auto &option : state.select.options)
      write_option(out, option);
  }
  return out;
}

inline bool decode(std::string_view in, GameState &state) {
  if (in.size() < 8 + 4 + 4 + 8)
    return false;
  if (std::memcmp(in.data(), kMagic, 8) != 0)
    return false;
  in.remove_prefix(8);
  uint32_t version = 0, flags = 0;
  if (!read_u32(in, version) || version != kVersion || !read_u32(in, flags) ||
      !read_f64(in, state.remaining_overage_time))
    return false;
  if (flags & kFlagHasSearchBegin) {
    if (!read_string(in, state.search_begin_input))
      return false;
  } else
    state.search_begin_input.clear();
  if (!read_i8(in, state.current.result) ||
      !read_i8(in, state.current.your_index) ||
      !read_i8(in, state.current.first_player) ||
      !read_i16(in, state.current.turn) ||
      !read_i16(in, state.current.turn_action_count))
    return false;
  uint16_t stadium_count = 0, looking_count = 0;
  if (!read_u16(in, stadium_count))
    return false;
  state.current.stadium.clear();
  state.current.looking.clear();
  for (uint16_t i = 0; i < stadium_count; ++i) {
    GlobalCard card;
    if (!read_i32(in, card.id) || !read_i8(in, card.player_index))
      return false;
    state.current.stadium.push_back(card);
  }
  if (!read_u16(in, looking_count))
    return false;
  for (uint16_t i = 0; i < looking_count; ++i) {
    GlobalCard card;
    if (!read_i32(in, card.id) || !read_i8(in, card.player_index))
      return false;
    state.current.looking.push_back(card);
  }
  if (!read_player(in, state.current.players[0]) ||
      !read_player(in, state.current.players[1]))
    return false;
  state.has_select = (flags & kFlagHasSelect) != 0;
  if (state.has_select) {
    uint16_t option_count = 0;
    if (!read_i16(in, state.select.context) ||
        !read_i8(in, state.select.min_count) ||
        !read_i8(in, state.select.max_count) || !read_u16(in, option_count))
      return false;
    state.select.options.resize(option_count);
    for (auto &option : state.select.options)
      if (!read_option(in, option))
        return false;
  } else {
    state.select = {};
  }
  return in.empty();
}

} // namespace pvs::wire
