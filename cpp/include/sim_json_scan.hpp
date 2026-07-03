#pragma once
#include "pvs_hash.hpp"
#include "pvs_state.hpp"
#include <charconv>
#include <cstdint>
#include <limits>
#include <string_view>

namespace pvs::sim {

namespace key {
constexpr uint64_t kDeckCount = hash::key_id("deckCount");
constexpr uint64_t kHandCount = hash::key_id("handCount");
constexpr uint64_t kPrize = hash::key_id("prize");
constexpr uint64_t kHand = hash::key_id("hand");
constexpr uint64_t kActive = hash::key_id("active");
constexpr uint64_t kBench = hash::key_id("bench");
constexpr uint64_t kDiscard = hash::key_id("discard");
constexpr uint64_t kId = hash::key_id("id");
constexpr uint64_t kHp = hash::key_id("hp");
constexpr uint64_t kEnergies = hash::key_id("energies");
constexpr uint64_t kPreEvolution = hash::key_id("preEvolution");
constexpr uint64_t kEnergyCards = hash::key_id("energyCards");
constexpr uint64_t kTools = hash::key_id("tools");
constexpr uint64_t kType = hash::key_id("type");
constexpr uint64_t kCardId = hash::key_id("cardId");
constexpr uint64_t kAttackId = hash::key_id("attackId");
constexpr uint64_t kArea = hash::key_id("area");
constexpr uint64_t kIndex = hash::key_id("index");
constexpr uint64_t kPlayerIndex = hash::key_id("playerIndex");
constexpr uint64_t kInPlayArea = hash::key_id("inPlayArea");
constexpr uint64_t kInPlayIndex = hash::key_id("inPlayIndex");
constexpr uint64_t kNumber = hash::key_id("number");
constexpr uint64_t kCount = hash::key_id("count");
constexpr uint64_t kSpecialConditionType = hash::key_id("specialConditionType");
constexpr uint64_t kToolIndex = hash::key_id("toolIndex");
constexpr uint64_t kEnergyIndex = hash::key_id("energyIndex");
constexpr uint64_t kSerial = hash::key_id("serial");
constexpr uint64_t kContext = hash::key_id("context");
constexpr uint64_t kMinCount = hash::key_id("minCount");
constexpr uint64_t kMaxCount = hash::key_id("maxCount");
constexpr uint64_t kOption = hash::key_id("option");
constexpr uint64_t kResult = hash::key_id("result");
constexpr uint64_t kYourIndex = hash::key_id("yourIndex");
constexpr uint64_t kFirstPlayer = hash::key_id("firstPlayer");
constexpr uint64_t kTurn = hash::key_id("turn");
constexpr uint64_t kTurnActionCount = hash::key_id("turnActionCount");
constexpr uint64_t kPlayers = hash::key_id("players");
constexpr uint64_t kStadium = hash::key_id("stadium");
constexpr uint64_t kLooking = hash::key_id("looking");
constexpr uint64_t kSelect = hash::key_id("select");
constexpr uint64_t kCurrent = hash::key_id("current");
constexpr uint64_t kSearchBeginInput = hash::key_id("search_begin_input");
constexpr uint64_t kRemainingOverageTime = hash::key_id("remainingOverageTime");
constexpr uint64_t kError = hash::key_id("error");
constexpr uint64_t kState = hash::key_id("state");
constexpr uint64_t kSearchId = hash::key_id("searchId");
constexpr uint64_t kObservation = hash::key_id("observation");
} // namespace key

inline void reset_state(GameState &state) {
  state.has_select = false;
  state.select = {};
  state.current = {};
  state.search_begin_input.clear();
  state.remaining_overage_time = 600;
  state.search_id = 0;
}

class JsonScan {
  const char *p_;
  const char *e_;
  bool ok_ = true;

  void ws() {
    while (p_ < e_ && (*p_ == ' ' || *p_ == '\n' || *p_ == '\r' || *p_ == '\t'))
      ++p_;
  }
  bool take(char c) {
    ws();
    if (p_ < e_ && *p_ == c) {
      ++p_;
      return true;
    }
    ok_ = false;
    return false;
  }
  void skip_string_raw() {
    if (!take('"'))
      return;
    while (p_ < e_) {
      char c = *p_++;
      if (c == '"')
        return;
      if (c == '\\' && p_ < e_)
        ++p_;
    }
    ok_ = false;
  }
  std::string_view read_string_view() {
    ws();
    if (p_ >= e_ || *p_++ != '"') {
      ok_ = false;
      return {};
    }
    const char *start = p_;
    while (p_ < e_) {
      char c = *p_++;
      if (c == '"')
        return {start, size_t(p_ - start - 1)};
      if (c == '\\' && p_ < e_)
        ++p_;
    }
    ok_ = false;
    return {};
  }
  bool match_literal(std::string_view text) {
    ws();
    if (size_t(e_ - p_) < text.size() || std::string_view(p_, text.size()) != text)
      return false;
    p_ += text.size();
    return true;
  }
  int64_t read_integer(int64_t fallback = 0) {
    ws();
    const char *b = p_;
    if (p_ < e_ && *p_ == '-')
      ++p_;
    while (p_ < e_ && *p_ >= '0' && *p_ <= '9')
      ++p_;
    int64_t value = fallback;
    std::from_chars(b, p_, value);
    return value;
  }
  double read_number(double fallback = 0) {
    ws();
    const char *b = p_;
    while (p_ < e_ && ((*p_ >= '0' && *p_ <= '9') || *p_ == '-' || *p_ == '+' ||
                       *p_ == '.' || *p_ == 'e' || *p_ == 'E'))
      ++p_;
    double value = fallback;
    std::from_chars(b, p_, value);
    return value;
  }
  void skip_value() {
    ws();
    if (p_ >= e_) {
      ok_ = false;
      return;
    }
    if (*p_ == '"') {
      skip_string_raw();
      return;
    }
    if (*p_ == '{') {
      ++p_;
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        return;
      }
      for (;;) {
        skip_string_raw();
        take(':');
        skip_value();
        ws();
        if (p_ < e_ && *p_ == '}') {
          ++p_;
          return;
        }
        take(',');
      }
    }
    if (*p_ == '[') {
      ++p_;
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        return;
      }
      for (;;) {
        skip_value();
        ws();
        if (p_ < e_ && *p_ == ']') {
          ++p_;
          return;
        }
        take(',');
      }
    }
    if (match_literal("null") || match_literal("true") || match_literal("false")) {
      return;
    }
    while (p_ < e_ && *p_ != ',' && *p_ != '}' && *p_ != ']' && *p_ != ' ' &&
           *p_ != '\n' && *p_ != '\r' && *p_ != '\t')
      ++p_;
  }
  uint64_t read_key_id() {
    ws();
    if (p_ >= e_ || *p_++ != '"') {
      ok_ = false;
      return 0;
    }
    uint32_t hash = hash::kFnvBasis;
    uint32_t length = 0;
    while (p_ < e_) {
      unsigned char c = static_cast<unsigned char>(*p_++);
      if (c == '"')
        return (uint64_t(length) << 32) | hash;
      if (c == '\\' && p_ < e_)
        c = static_cast<unsigned char>(*p_++);
      hash = (hash ^ c) * hash::kFnvPrime;
      ++length;
    }
    ok_ = false;
    return 0;
  }
  void count_array(uint8_t *counter = nullptr) {
    if (!take('[')) {
      skip_value();
      return;
    }
    ws();
    uint8_t count = 0;
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      if (counter)
        *counter = count;
      return;
    }
    for (;;) {
      skip_value();
      ++count;
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
    if (counter)
      *counter = count;
  }
  void read_card(CardSlot &out) {
    if (!take('{')) {
      skip_value();
      return;
    }
    out = {};
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kId)
        out.id = int32_t(read_integer());
      else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_global_card(GlobalCard &out) {
    if (!take('{')) {
      skip_value();
      return;
    }
    out = {};
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kId)
        out.id = int32_t(read_integer());
      else if (key == key::kPlayerIndex)
        out.player_index = int8_t(read_integer());
      else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  PokemonSlot read_pokemon_object() {
    PokemonSlot out;
    if (!take('{'))
      return out;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      out.present = true;
      return out;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kId) {
        out.id = int32_t(read_integer());
        out.present = true;
      } else if (key == key::kHp)
        out.hp = int16_t(read_integer());
      else if (key == key::kEnergies)
        count_array(&out.energy_count);
      else if (key == key::kPreEvolution)
        count_array(&out.pre_evolution_count);
      else if (key == key::kEnergyCards || key == key::kTools)
        // Search evaluation only needs the aggregate energy count.  Materializing
        // every attached card here allocated several vectors per simulated node;
        // the public/root observation still retains those IDs for belief setup.
        skip_value();
      else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
    return out;
  }
  void read_pokemon_array(std::vector<PokemonSlot> &out) {
    if (!take('['))
      return;
    out.clear();
    ws();
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      return;
    }
    out.reserve(4);
    for (;;) {
      ws();
      if (match_literal("null")) {
        PokemonSlot slot;
        slot.face_down = true;
        out.push_back(slot);
      } else
        out.push_back(read_pokemon_object());
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_attached_card_array(std::vector<int32_t> &attached) {
    if (!take('[')) {
      skip_value();
      return;
    }
    ws();
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      return;
    }
    for (;;) {
      CardSlot card;
      read_card(card);
      if (card.id)
        attached.push_back(card.id);
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_global_card_array(std::vector<GlobalCard> &out) {
    if (!take('[')) {
      skip_value();
      return;
    }
    out.clear();
    ws();
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      return;
    }
    out.reserve(4);
    for (;;) {
      ws();
      if (match_literal("null"))
        out.push_back({});
      else {
        GlobalCard card;
        read_global_card(card);
        out.push_back(card);
      }
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_card_array(std::vector<CardSlot> &out) {
    if (!take('['))
      return;
    out.clear();
    ws();
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      return;
    }
    out.reserve(8);
    for (;;) {
      CardSlot card;
      read_card(card);
      out.push_back(card);
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_prize_array(std::vector<int32_t> &out) {
    if (!take('['))
      return;
    out.clear();
    ws();
    if (p_ < e_ && *p_ == ']') {
      ++p_;
      return;
    }
    out.reserve(6);
    for (;;) {
      ws();
      if (match_literal("null"))
        out.push_back(0);
      else {
        CardSlot card;
        read_card(card);
        out.push_back(card.id);
      }
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_player(PlayerView &player) {
    if (!take('{'))
      return;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kDeckCount)
        player.deck_count = int16_t(read_integer());
      else if (key == key::kHandCount)
        player.hand_count = int16_t(read_integer());
      else if (key == key::kPrize)
        read_prize_array(player.prize);
      else if (key == key::kHand) {
        if (match_literal("null"))
          player.hand.clear();
        else
          read_card_array(player.hand);
      } else if (key == key::kActive)
        read_pokemon_array(player.active);
      else if (key == key::kBench)
        read_pokemon_array(player.bench);
      else if (key == key::kDiscard)
        read_card_array(player.discard);
      else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  OptionView read_option() {
    OptionView option;
    if (!take('{'))
      return option;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return option;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kType)
        option.type = int16_t(read_integer());
      else if (key == key::kCardId)
        option.card_id = int32_t(read_integer());
      else if (key == key::kAttackId)
        option.attack_id = int32_t(read_integer());
      else if (key == key::kArea)
        option.area = int16_t(read_integer());
      else if (key == key::kIndex)
        option.index = int16_t(read_integer());
      else if (key == key::kPlayerIndex)
        option.player_index = int16_t(read_integer());
      else if (key == key::kInPlayArea)
        option.in_play_area = int16_t(read_integer());
      else if (key == key::kInPlayIndex)
        option.in_play_index = int16_t(read_integer());
      else if (key == key::kNumber)
        option.number = int16_t(read_integer());
      else if (key == key::kCount)
        option.count = int16_t(read_integer());
      else if (key == key::kSpecialConditionType)
        option.special_condition_type = int16_t(read_integer());
      else if (key == key::kToolIndex)
        option.tool_index = int16_t(read_integer());
      else if (key == key::kEnergyIndex)
        option.energy_index = int16_t(read_integer());
      else if (key == key::kSerial)
        option.serial = int32_t(read_integer());
      else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
    return option;
  }
  void read_select(SelectView &select) {
    if (!take('{'))
      return;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    select.options.clear();
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kContext)
        select.context = int16_t(read_integer());
      else if (key == key::kMinCount)
        select.min_count = int8_t(read_integer());
      else if (key == key::kMaxCount)
        select.max_count = int8_t(read_integer());
      else if (key == key::kOption) {
        if (!take('['))
          continue;
        ws();
        if (p_ < e_ && *p_ == ']') {
          ++p_;
          continue;
        }
        select.options.reserve(16);
        for (;;) {
          select.options.push_back(read_option());
          ws();
          if (p_ < e_ && *p_ == ']') {
            ++p_;
            break;
          }
          take(',');
        }
      } else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_current(CurrentView &current) {
    if (!take('{'))
      return;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kResult)
        current.result = int8_t(read_integer(-1));
      else if (key == key::kYourIndex)
        current.your_index = int8_t(read_integer());
      else if (key == key::kFirstPlayer)
        current.first_player = int8_t(read_integer(-1));
      else if (key == key::kTurn)
        current.turn = int16_t(read_integer());
      else if (key == key::kTurnActionCount)
        current.turn_action_count = int16_t(read_integer());
      else if (key == key::kPlayers) {
        if (!take('['))
          continue;
        int idx = 0;
        ws();
        if (p_ < e_ && *p_ == ']') {
          ++p_;
          continue;
        }
        for (;;) {
          if (idx < 2)
            read_player(current.players[idx]);
          else
            skip_value();
          ++idx;
          ws();
          if (p_ < e_ && *p_ == ']') {
            ++p_;
            break;
          }
          take(',');
        }
      } else if (key == key::kStadium) {
        if (match_literal("null"))
          current.stadium.clear();
        else
          read_global_card_array(current.stadium);
      } else if (key == key::kLooking) {
        if (match_literal("null"))
          current.looking.clear();
        else
          read_global_card_array(current.looking);
      } else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_observation(GameState &state) {
    if (!take('{'))
      return;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kSelect) {
        if (match_literal("null")) {
          state.has_select = false;
        } else {
          state.has_select = true;
          read_select(state.select);
        }
      } else if (key == key::kCurrent) {
        if (match_literal("null"))
          state.current = {};
        else
          read_current(state.current);
      } else if (key == key::kSearchBeginInput) {
        if (match_literal("null"))
          state.search_begin_input.clear();
        else {
          auto text = read_string_view();
          state.search_begin_input.assign(text.begin(), text.end());
        }
      } else if (key == key::kRemainingOverageTime) {
        if (match_literal("null"))
          state.remaining_overage_time = 600;
        else
          state.remaining_overage_time = read_number(600);
      } else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }
  void read_state_object(int64_t &search_id, GameState &state) {
    if (!take('{'))
      return;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kSearchId)
        search_id = read_integer(-1);
      else if (key == key::kObservation) {
        if (match_literal("null"))
          reset_state(state);
        else
          read_observation(state);
      } else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
  }

public:
  explicit JsonScan(std::string_view json) : p_(json.data()), e_(json.data() + json.size()) {}

  bool parse_response(int &error, int64_t &search_id, GameState &state) {
    error = 99;
    search_id = -1;
    if (!take('{'))
      return false;
    ws();
    if (p_ < e_ && *p_ == '}') {
      ++p_;
      return ok_;
    }
    for (;;) {
      auto key = read_key_id();
      take(':');
      if (key == key::kError)
        error = int(read_integer(99));
      else if (key == key::kState) {
        if (match_literal("null"))
          reset_state(state);
        else
          read_state_object(search_id, state);
      } else if (key == key::kSearchId)
        search_id = read_integer(-1);
      else if (key == key::kObservation) {
        if (match_literal("null"))
          reset_state(state);
        else
          read_observation(state);
      } else
        skip_value();
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        break;
      }
      take(',');
    }
    ws();
    return ok_ && p_ == e_;
  }

  bool ok() const { return ok_; }
};

inline bool import_sim_response(std::string_view json, int &error,
                                int64_t &search_id, GameState &state) {
  reset_state(state);
  JsonScan scan(json);
  return scan.parse_response(error, search_id, state) && scan.ok();
}

} // namespace pvs::sim
