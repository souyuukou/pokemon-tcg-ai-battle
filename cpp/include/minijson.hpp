#pragma once
#include <charconv>
#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <variant>
#include <vector>

namespace mj {
constexpr uint32_t key_hash(std::string_view text) {
  uint32_t hash = 2166136261u;
  for (unsigned char c : text)
    hash = (hash ^ c) * 16777619u;
  return hash;
}
constexpr uint64_t key_id(std::string_view text) {
  return (uint64_t(text.size()) << 32) | key_hash(text);
}
struct Value {
  enum Kind : uint8_t { Null, Bool, Number, String, Array, Object } kind = Null;
  using ArrayData = std::vector<Value>;
  using ObjectData = std::vector<std::pair<uint64_t, Value>>;
  std::variant<std::monostate, bool, double, std::string, ArrayData, ObjectData>
      data;
  static Value array_value() {
    Value value;
    value.kind = Array;
    value.data.emplace<ArrayData>();
    return value;
  }
  static Value object_value() {
    Value value;
    value.kind = Object;
    value.data.emplace<ObjectData>();
    return value;
  }
  ArrayData &as_array() { return std::get<ArrayData>(data); }
  const ArrayData &as_array() const {
    static const ArrayData empty;
    return kind == Array ? std::get<ArrayData>(data) : empty;
  }
  ObjectData &as_object() { return std::get<ObjectData>(data); }
  const ObjectData &as_object() const {
    static const ObjectData empty;
    return kind == Object ? std::get<ObjectData>(data) : empty;
  }
  const std::string &as_string() const {
    static const std::string empty;
    return kind == String ? std::get<std::string>(data) : empty;
  }
  double as_number(double fallback = 0) const {
    return kind == Number ? std::get<double>(data) : fallback;
  }
  bool as_bool(bool fallback = false) const {
    return kind == Bool ? std::get<bool>(data) : fallback;
  }
  const Value &at(std::string_view k) const {
    static const Value nil;
    uint64_t id = key_id(k);
    for (const auto &entry : as_object())
      if (entry.first == id)
        return entry.second;
    return nil;
  }
  int integer(int d = 0) const { return int(as_number(d)); }
  bool is_null() const { return kind == Null; }
};

enum class ParseProfile : uint8_t { Full, Lean, Search };

class Parser {
  const char *p_;
  const char *e_;
  bool ok_ = true;
  ParseProfile profile_ = ParseProfile::Full;
  enum class Frame : uint8_t {
    Generic,
    ObsRoot,
    Current,
    Player,
    Card,
    Select,
    Option
  };
  std::vector<Frame> frames_{Frame::ObsRoot};

  static bool discard_in_lean_mode(uint64_t key) {
    return key == key_id("logs") || key == key_id("serial") ||
           key == key_id("maxHp") || key == key_id("appearThisTurn") ||
           key == key_id("energyCards") || key == key_id("tools") ||
           key == key_id("benchMax") || key == key_id("poisoned") ||
           key == key_id("burned") || key == key_id("asleep") ||
           key == key_id("paralyzed") || key == key_id("confused") ||
           key == key_id("supporterPlayed") || key == key_id("stadiumPlayed") ||
           key == key_id("energyAttached") || key == key_id("retreated") ||
           key == key_id("remainDamageCounter") ||
           key == key_id("remainEnergyCost") || key == key_id("deck") ||
           key == key_id("contextCard") || key == key_id("effect") ||
           key == key_id("looking") || key == key_id("stadium") ||
           key == key_id("playerIndex");
  }
  bool discard_in_search_mode(uint64_t key) const {
    switch (frames_.back()) {
    case Frame::ObsRoot:
      return key != key_id("select") && key != key_id("current");
    case Frame::Current:
      return key != key_id("result") && key != key_id("yourIndex") &&
             key != key_id("turn") && key != key_id("firstPlayer") &&
             key != key_id("players");
    case Frame::Player:
      return key != key_id("deckCount") && key != key_id("handCount") &&
             key != key_id("prize") && key != key_id("hand") &&
             key != key_id("active") && key != key_id("bench") &&
             key != key_id("discard");
    case Frame::Card:
      return key != key_id("id") && key != key_id("hp") &&
             key != key_id("energies");
    case Frame::Select:
      return key != key_id("context") && key != key_id("minCount") &&
             key != key_id("maxCount") && key != key_id("option");
    case Frame::Option:
      return false;
    default:
      return discard_in_lean_mode(key);
    }
  }
  bool should_discard(uint64_t key) const {
    if (key == key_id("logs"))
      return true;
    if (profile_ == ParseProfile::Full)
      return false;
    if (profile_ == ParseProfile::Lean)
      return discard_in_lean_mode(key);
    return discard_in_search_mode(key);
  }
  Frame child_frame(uint64_t key) const {
    if (profile_ != ParseProfile::Search)
      return Frame::Generic;
    switch (frames_.back()) {
    case Frame::ObsRoot:
      if (key == key_id("current"))
        return Frame::Current;
      if (key == key_id("select"))
        return Frame::Select;
      break;
    case Frame::Current:
      if (key == key_id("players"))
        return Frame::Player;
      break;
    case Frame::Player:
      if (key == key_id("hand") || key == key_id("active") ||
          key == key_id("bench") || key == key_id("discard") ||
          key == key_id("prize"))
        return Frame::Card;
      break;
    case Frame::Select:
      if (key == key_id("option"))
        return Frame::Option;
      break;
    default:
      break;
    }
    return frames_.back();
  }
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
  std::string str() {
    std::string s;
    if (!take('"'))
      return s;
    while (p_ < e_) {
      char c = *p_++;
      if (c == '"')
        return s;
      if (c == '\\' && p_ < e_) {
        char x = *p_++;
        switch (x) {
        case 'n':
          s += '\n';
          break;
        case 'r':
          s += '\r';
          break;
        case 't':
          s += '\t';
          break;
        case 'b':
          s += '\b';
          break;
        case 'f':
          s += '\f';
          break;
        default:
          s += x;
        }
      } else
        s += c;
    }
    ok_ = false;
    return s;
  }
  uint64_t object_key() {
    ws();
    if (p_ >= e_ || *p_++ != '"') {
      ok_ = false;
      return 0;
    }
    uint32_t hash = 2166136261u;
    uint32_t length = 0;
    while (p_ < e_) {
      unsigned char c = static_cast<unsigned char>(*p_++);
      if (c == '"')
        return (uint64_t(length) << 32) | hash;
      if (c == '\\' && p_ < e_)
        c = static_cast<unsigned char>(*p_++);
      hash = (hash ^ c) * 16777619u;
      ++length;
    }
    ok_ = false;
    return 0;
  }
  void skip_string() {
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
  void skip_value() {
    ws();
    if (p_ >= e_) {
      ok_ = false;
      return;
    }
    if (*p_ == '"') {
      skip_string();
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
        skip_string();
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
    while (p_ < e_ && *p_ != ',' && *p_ != '}' && *p_ != ']' && *p_ != ' ' &&
           *p_ != '\n' && *p_ != '\r' && *p_ != '\t')
      ++p_;
  }
  Value value() {
    ws();
    Value v;
    if (p_ >= e_) {
      ok_ = false;
      return v;
    }
    if (*p_ == '{') {
      v = Value::object_value();
      v.as_object().reserve(8);
      ++p_;
      ws();
      if (p_ < e_ && *p_ == '}') {
        ++p_;
        return v;
      }
      for (;;) {
        ws();
        auto k = object_key();
        take(':');
        if (should_discard(k))
          skip_value();
        else {
          frames_.push_back(child_frame(k));
          v.as_object().emplace_back(k, value());
          frames_.pop_back();
        }
        ws();
        if (p_ < e_ && *p_ == '}') {
          ++p_;
          break;
        }
        take(',');
      }
      return v;
    }
    if (*p_ == '[') {
      v = Value::array_value();
      v.as_array().reserve(8);
      ++p_;
      ws();
      if (p_ < e_ && *p_ == ']') {
        ++p_;
        return v;
      }
      for (;;) {
        v.as_array().push_back(value());
        ws();
        if (p_ < e_ && *p_ == ']') {
          ++p_;
          break;
        }
        take(',');
      }
      return v;
    }
    if (*p_ == '"') {
      v.kind = Value::String;
      v.data = str();
      return v;
    }
    if (e_ - p_ >= 4 && std::string_view(p_, 4) == "null") {
      p_ += 4;
      return v;
    }
    if (e_ - p_ >= 4 && std::string_view(p_, 4) == "true") {
      p_ += 4;
      v.kind = Value::Bool;
      v.data = true;
      return v;
    }
    if (e_ - p_ >= 5 && std::string_view(p_, 5) == "false") {
      p_ += 5;
      v.kind = Value::Bool;
      v.data = false;
      return v;
    }
    v.kind = Value::Number;
    const char *b = p_;
    while (p_ < e_ && ((*p_ >= '0' && *p_ <= '9') || *p_ == '-' || *p_ == '+' ||
                       *p_ == '.' || *p_ == 'e' || *p_ == 'E'))
      ++p_;
    double number = 0;
    auto r = std::from_chars(b, p_, number);
    v.data = number;
    if (r.ec != std::errc())
      ok_ = false;
    return v;
  }

public:
  explicit Parser(std::string_view s, ParseProfile profile = ParseProfile::Full)
      : p_(s.data()), e_(s.data() + s.size()), profile_(profile) {}
  Parser(std::string_view s, bool lean)
      : Parser(s, lean ? ParseProfile::Lean : ParseProfile::Full) {}
  Value parse() {
    auto v = value();
    ws();
    if (p_ != e_)
      ok_ = false;
    return v;
  }
  bool ok() const { return ok_; }
};
} // namespace mj
