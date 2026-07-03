#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

namespace pvs {

struct CardSlot {
  int32_t id = 0;
};

struct PokemonSlot {
  bool present = false;
  bool face_down = false;
  int32_t id = 0;
  int16_t hp = 0;
  uint8_t energy_count = 0;
  uint8_t pre_evolution_count = 0;
  std::vector<int32_t> attached_ids;
};

struct PlayerView {
  int16_t deck_count = 0;
  int16_t hand_count = 0;
  std::vector<int32_t> prize;
  std::vector<CardSlot> hand;
  std::vector<PokemonSlot> active;
  std::vector<PokemonSlot> bench;
  std::vector<CardSlot> discard;
};

struct OptionView {
  int16_t type = -1;
  int32_t card_id = std::numeric_limits<int32_t>::min();
  int32_t attack_id = std::numeric_limits<int32_t>::min();
  int16_t area = std::numeric_limits<int16_t>::min();
  int16_t index = std::numeric_limits<int16_t>::min();
  int16_t player_index = std::numeric_limits<int16_t>::min();
  int16_t in_play_area = std::numeric_limits<int16_t>::min();
  int16_t in_play_index = std::numeric_limits<int16_t>::min();
  int16_t number = std::numeric_limits<int16_t>::min();
  int16_t count = std::numeric_limits<int16_t>::min();
  int16_t special_condition_type = std::numeric_limits<int16_t>::min();
  int16_t tool_index = std::numeric_limits<int16_t>::min();
  int16_t energy_index = std::numeric_limits<int16_t>::min();
  int32_t serial = std::numeric_limits<int32_t>::min();
};

struct GlobalCard {
  int32_t id = 0;
  int8_t player_index = -1;
};

struct SelectView {
  int16_t context = -1;
  int8_t min_count = 0;
  int8_t max_count = 0;
  std::vector<OptionView> options;
};

struct CurrentView {
  int8_t result = -1;
  int8_t your_index = 0;
  int8_t first_player = -1;
  int16_t turn = 0;
  int16_t turn_action_count = 0;
  std::array<PlayerView, 2> players{};
  std::vector<GlobalCard> stadium;
  std::vector<GlobalCard> looking;
};

struct GameState {
  bool has_select = false;
  SelectView select;
  CurrentView current;
  double remaining_overage_time = 600;
  std::string search_begin_input;
  int64_t search_id = 0;
};

inline bool option_has(const OptionView &option, int32_t OptionView::*field) {
  return option.*field != std::numeric_limits<int32_t>::min();
}

inline bool option_has16(const OptionView &option, int16_t OptionView::*field) {
  return option.*field != std::numeric_limits<int16_t>::min();
}

inline int option_int(const OptionView &option, int16_t OptionView::*field,
                      int fallback = -1) {
  return option_has16(option, field) ? int(option.*field) : fallback;
}

inline int option_int32(const OptionView &option, int32_t OptionView::*field,
                        int fallback = -1) {
  return option_has(option, field) ? int(option.*field) : fallback;
}

} // namespace pvs
