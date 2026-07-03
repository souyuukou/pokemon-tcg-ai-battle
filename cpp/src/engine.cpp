#include "minijson.hpp"
#include "pvs_api.h"
#include "pvs_hash.hpp"
#include "pvs_state.hpp"
#include "pvs_wire.hpp"
#include "sim_json_scan.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <functional>
#include <future>
#include <limits>
#include <mutex>
#include <numeric>
#include <optional>
#include <random>
#include <sstream>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#if defined(__AVX2__)
#include <immintrin.h>
#endif

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#include <intrin.h>
#else
#include <dlfcn.h>
#endif

namespace {
using Clock = std::chrono::steady_clock;
using GameState = pvs::GameState;
constexpr float kSearchInfinity = 40000.f;
constexpr float kWinScore = 30000.f;
constexpr bool has_value(float v) { return v > -kSearchInfinity + 1.f; }
constexpr int kCoinChoiceContext = 46;
constexpr int kToHandChoiceContext = 7;
constexpr int kCardOption = 3;
constexpr int kPrizeArea = 6;
constexpr int kAttackOption = 13;
constexpr int kEndOption = 14;
constexpr int kRetreatOption = 12;
constexpr int kPlayOption = 7;
constexpr int kAttachOption = 8;
constexpr int kEvolveOption = 9;
constexpr int kAbilityOption = 10;
constexpr int kMainActionsPerTurnLimit = 16;
constexpr uint64_t kNodeBudgetPerWorld = 150000;
constexpr int kActionLimit = 96;
constexpr int kCombinationEnumerationLimit = 4096;
constexpr int kForcedActionLimit = 16384;
constexpr int kPlannerMainBranchLimit = 48;
constexpr int kPlannerForcedBranchLimit = 12;
constexpr int kSubselectExhaustiveLimit = 8;
constexpr int kOpponentGreedyLimit = 28;
constexpr int kOpponentPlanDepth = 3;
constexpr int kPlanCacheMaxSteps = 64;
constexpr int kSpareBudgetTopRoots = 3;
constexpr int kPass2RootLimit = 3;
constexpr int kChooseOverheadMs = 550;

struct ApiResult {
  struct State {
    GameState observation;
    int64_t id = 0;
  };
  std::optional<State> state;
  int error = 99;
};

struct Dyn {
#ifdef _WIN32
  HMODULE h{};
#else
  void *h{};
#endif
  using AgentStart = void *(*)();
  using SearchBegin = const char *(*)(void *, const char *, int, const int *,
                                      const int *, const int *, const int *,
                                      const int *, const int *, int);
  using SearchStep = const char *(*)(void *, int64_t, const int *, int);
  using SearchEnd = void (*)(void *);
  using SearchRelease = void (*)(void *, int64_t);
  using AllCard = const char *(*)();
  using GameInitialize = void (*)();
  AgentStart agent_start{};
  SearchBegin search_begin{};
  SearchStep search_step{};
  SearchEnd search_end{};
  SearchRelease search_release{};
  AllCard all_card{};
  GameInitialize game_initialize{};
  template <class T> T sym(const char *n) {
#ifdef _WIN32
    return reinterpret_cast<T>(GetProcAddress(h, n));
#else
    return reinterpret_cast<T>(dlsym(h, n));
#endif
  }
  static const char *library_basename(const char *path) {
    const char *base = path;
    for (const char *c = path; *c; ++c)
      if (*c == '/' || *c == '\\')
        base = c + 1;
    return base;
  }
  static bool cg_preloaded(const char *path) {
#ifdef _WIN32
    return GetModuleHandleA(library_basename(path)) != nullptr;
#else
    void *probe = dlopen(path, RTLD_NOW | RTLD_NOLOAD);
    if (!probe)
      return false;
    dlclose(probe);
    return true;
#endif
  }
  void unload() {
    if (!h)
      return;
#ifdef _WIN32
    FreeLibrary(h);
#else
    dlclose(h);
#endif
    h = nullptr;
    game_initialize = nullptr;
    agent_start = nullptr;
    search_begin = nullptr;
    search_step = nullptr;
    search_end = nullptr;
    search_release = nullptr;
    all_card = nullptr;
  }
  bool ready() const {
    return h && agent_start && search_begin && search_step && search_end &&
           search_release && all_card;
  }
  bool load(const char *p) {
    if (h)
      return ready();
    const bool preloaded = cg_preloaded(p);
#ifdef _WIN32
    h = LoadLibraryA(p);
#else
    h = dlopen(p, RTLD_NOW | RTLD_LOCAL);
#endif
    if (!h)
      return false;
    game_initialize = sym<GameInitialize>("GameInitialize");
    agent_start = sym<AgentStart>("AgentStart");
    search_begin = sym<SearchBegin>("SearchBegin");
    search_step = sym<SearchStep>("SearchStep");
    search_end = sym<SearchEnd>("SearchEnd");
    search_release = sym<SearchRelease>("SearchRelease");
    all_card = sym<AllCard>("AllCard");
    // Python cg/sim.py may already have initialized a shared cg handle.
    // Calling GameInitialize twice throws. Calling AllCard before the first
    // GameInitialize leaves the catalog empty, so only init fresh loads.
    if (!preloaded && game_initialize)
      game_initialize();
    if (!ready())
      unload();
    return ready();
  }
} api;

class AgentSession {
public:
  AgentSession() : handle_(api.agent_start()) {}
  ~AgentSession() {
    if (handle_)
      api.search_end(handle_);
  }
  AgentSession(const AgentSession &) = delete;
  AgentSession &operator=(const AgentSession &) = delete;
  void *get() const { return handle_; }

private:
  void *handle_{};
};

class SearchStateLease {
public:
  SearchStateLease(void *agent, int64_t id) : agent_(agent), id_(id) {}
  ~SearchStateLease() {
    if (agent_)
      api.search_release(agent_, id_);
  }
  SearchStateLease(const SearchStateLease &) = delete;
  SearchStateLease &operator=(const SearchStateLease &) = delete;

private:
  void *agent_{};
  int64_t id_{};
};

class SearchStateSetLease {
public:
  explicit SearchStateSetLease(void *agent) : agent_(agent) {}
  ~SearchStateSetLease() {
    if (agent_)
      for (int64_t id : ids_)
        api.search_release(agent_, id);
  }
  SearchStateSetLease(const SearchStateSetLease &) = delete;
  SearchStateSetLease &operator=(const SearchStateSetLease &) = delete;
  void add(int64_t id) { ids_.push_back(id); }

private:
  void *agent_{};
  std::vector<int64_t> ids_;
};

struct Config {
  int hypotheses = 6, threads = 0, max_depth = 20, max_ms = 5000, hard_ms = 5100;
  double safety = 5.0, risk = .12, model_scale = 1.0;
  bool profile = false;
  bool probe_root = false;
} cfg;
struct Deck {
  std::vector<int> cards;
  double prior = 0;
};
std::vector<Deck> catalog;
std::unordered_map<int, bool> basic_cards;
std::string diag = "{}";
std::mutex diag_mu;
std::atomic<uint64_t> total_nodes{0};
static bool last_belief_degraded = false;
#if defined(__AVX2__)
static const char *native_backend_name = "avx2";
#else
static const char *native_backend_name = "scalar";
#endif

struct Model {
  bool loaded = false;
  uint32_t nf = 0, nh = 0;
  float es = 1, vs = 1, vbias = 0;
  std::vector<int8_t> emb, value, action_emb;
  std::vector<float> bias;
} model;

static float option_heuristic(int type) {
  switch (type) {
  case kAttackOption:
    return 8.f;
  case kAbilityOption:
    return 5.f;
  case kEvolveOption:
    return 4.f;
  case kAttachOption:
    return 3.f;
  case kEndOption:
    return -2.f;
  default:
    return 1.f;
  }
}

static void push_unique_id(std::vector<uint32_t> &ids, uint32_t id) {
  ids.push_back(id);
}

static void finalize_ids(std::vector<uint32_t> &ids, uint32_t nf) {
  for (uint32_t &id : ids)
    id %= nf;
  if (ids.size() <= 1)
    return;
  if (ids.size() <= 16) {
    for (size_t i = 1; i < ids.size(); ++i) {
      uint32_t key = ids[i];
      size_t j = i;
      while (j > 0 && ids[j - 1] > key) {
        ids[j] = ids[j - 1];
        --j;
      }
      ids[j] = key;
    }
    size_t w = 1;
    for (size_t i = 1; i < ids.size(); ++i)
      if (ids[i] != ids[w - 1])
        ids[w++] = ids[i];
    ids.resize(w);
    return;
  }
  std::sort(ids.begin(), ids.end());
  ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
}

static bool feature_schema_compatible() {
  using pvs::hash::append;
  using pvs::hash::append_int;
  using pvs::hash::fnv;
  uint32_t type_card = append("action:type_card:", pvs::hash::fnv_basis());
  type_card = append_int(type_card, 7);
  type_card = append(":", type_card);
  type_card = append_int(type_card, 123);
  uint32_t type_resolved =
      append("action:type_resolved:", pvs::hash::fnv_basis());
  type_resolved = append_int(type_resolved, 8);
  type_resolved = append(":", type_resolved);
  type_resolved = append_int(type_resolved, 722);
  return fnv("first:True") == 4065660873u && fnv("first:False") == 592178596u &&
         fnv("us:active:hp:3") == 2358348152u &&
         fnv("them:bench:hp:12") == 1108901960u && type_card == 3075853271u &&
         type_resolved == 4285686029u;
}

static void add_quantized(float *destination, const int8_t *source,
                          uint32_t size, float scale) {
  uint32_t i = 0;
#if defined(__AVX2__)
  __m256 factor = _mm256_set1_ps(scale);
  for (; i + 8 <= size; i += 8) {
    __m128i packed =
        _mm_loadl_epi64(reinterpret_cast<const __m128i *>(source + i));
    __m256 values =
        _mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_cvtepi8_epi32(packed)), factor);
    _mm256_storeu_ps(destination + i,
                     _mm256_add_ps(_mm256_loadu_ps(destination + i), values));
  }
#endif
  for (; i < size; ++i)
    destination[i] += scale * source[i];
}

static float dot_quantized(const float *left, const int8_t *right,
                           uint32_t size, float scale) {
  uint32_t i = 0;
  float result = 0.f;
#if defined(__AVX2__)
  __m256 sum = _mm256_setzero_ps();
  __m256 factor = _mm256_set1_ps(scale);
  for (; i + 8 <= size; i += 8) {
    __m128i packed =
        _mm_loadl_epi64(reinterpret_cast<const __m128i *>(right + i));
    __m256 values =
        _mm256_mul_ps(_mm256_cvtepi32_ps(_mm256_cvtepi8_epi32(packed)), factor);
    sum = _mm256_add_ps(sum, _mm256_mul_ps(_mm256_loadu_ps(left + i), values));
  }
  alignas(32) float lanes[8];
  _mm256_store_ps(lanes, sum);
  for (float lane : lanes)
    result += lane;
#endif
  for (; i < size; ++i)
    result += left[i] * scale * right[i];
  return result;
}

static bool load_model(const char *path) {
  if (!path || !*path)
    return false;
  std::ifstream f(path, std::ios::binary);
  if (!f)
    return false;
  char magic[8];
  uint32_t ver, payload;
  uint64_t expected;
  char checksum_tail[24];
  f.read(magic, 8);
  f.read(reinterpret_cast<char *>(&ver), 4);
  f.read(reinterpret_cast<char *>(&model.nf), 4);
  f.read(reinterpret_cast<char *>(&model.nh), 4);
  f.read(reinterpret_cast<char *>(&payload), 4);
  f.read(reinterpret_cast<char *>(&model.es), 4);
  f.read(reinterpret_cast<char *>(&model.vs), 4);
  f.read(reinterpret_cast<char *>(&expected), 8);
  f.read(checksum_tail, 24);
  uint32_t wanted =
      model.nf * model.nh + model.nh * 4 + model.nh + 4 + model.nf * model.nh;
  if (!f || std::memcmp(magic, "PKNNUE1", 7) || ver != 2 || model.nf != 4096 ||
      model.nh != 256 || payload != wanted)
    return false;
  std::vector<uint8_t> bytes(payload);
  f.read(reinterpret_cast<char *>(bytes.data()), bytes.size());
  uint64_t got = 14695981039346656037ULL;
  for (auto b : bytes)
    got = (got ^ b) * 1099511628211ULL;
  if (!f || got != expected)
    return false;
  size_t at = 0;
  model.emb.resize(size_t(model.nf) * model.nh);
  std::memcpy(model.emb.data(), bytes.data() + at, model.emb.size());
  at += model.emb.size();
  model.bias.resize(model.nh);
  std::memcpy(model.bias.data(), bytes.data() + at, model.bias.size() * 4);
  at += model.bias.size() * 4;
  model.value.resize(model.nh);
  std::memcpy(model.value.data(), bytes.data() + at, model.value.size());
  at += model.value.size();
  std::memcpy(&model.vbias, bytes.data() + at, 4);
  at += 4;
  model.action_emb.resize(size_t(model.nf) * model.nh);
  std::memcpy(model.action_emb.data(), bytes.data() + at,
              model.action_emb.size());
  model.loaded = true;
  return true;
}

static bool config_bool(std::string_view config, std::string_view key,
                        bool fallback) {
  auto pos = config.find(key);
  if (pos == std::string_view::npos)
    return fallback;
  pos = config.find(':', pos);
  if (pos == std::string_view::npos)
    return fallback;
  ++pos;
  while (pos < config.size() && (config[pos] == ' ' || config[pos] == '\t'))
    ++pos;
  if (config.substr(pos, 4) == "true")
    return true;
  if (config.substr(pos, 5) == "false")
    return false;
  return fallback;
}

static int config_int(std::string_view config, std::string_view key,
                      int fallback) {
  auto pos = config.find(key);
  if (pos == std::string_view::npos)
    return fallback;
  pos = config.find(':', pos);
  if (pos == std::string_view::npos)
    return fallback;
  ++pos;
  while (pos < config.size() && (config[pos] == ' ' || config[pos] == '\t'))
    ++pos;
  int value = fallback;
  std::from_chars(config.data() + pos, config.data() + config.size(), value);
  return value;
}

static double config_double(std::string_view config, std::string_view key,
                            double fallback) {
  auto pos = config.find(key);
  if (pos == std::string_view::npos)
    return fallback;
  pos = config.find(':', pos);
  if (pos == std::string_view::npos)
    return fallback;
  ++pos;
  while (pos < config.size() && (config[pos] == ' ' || config[pos] == '\t'))
    ++pos;
  double value = fallback;
  std::from_chars(config.data() + pos, config.data() + config.size(), value);
  return value;
}

static ApiResult import_sim_response(const char *text) {
  ApiResult result;
  if (!text)
    return result;
  int error = 99;
  int64_t search_id = -1;
  thread_local GameState state;
  if (!pvs::sim::import_sim_response(text, error, search_id, state))
    return result;
  result.error = error;
  if (error || search_id < 0)
    return result;
  state.search_id = search_id;
  result.state.emplace(ApiResult::State{std::move(state), search_id});
  return result;
}

static void collect_card(int id, std::unordered_map<int, int> &counts) {
  if (id)
    ++counts[id];
}

static void collect_pokemon(const pvs::PokemonSlot &slot,
                            std::unordered_map<int, int> &counts) {
  if (!slot.present || slot.face_down)
    return;
  collect_card(slot.id, counts);
  for (int id : slot.attached_ids)
    collect_card(id, counts);
}

static std::unordered_map<int, int>
visible_player(const pvs::PlayerView &player) {
  std::unordered_map<int, int> counts;
  for (const auto &slot : player.active)
    collect_pokemon(slot, counts);
  for (const auto &slot : player.bench)
    collect_pokemon(slot, counts);
  for (const auto &card : player.discard)
    collect_card(card.id, counts);
  for (const auto &card : player.hand)
    collect_card(card.id, counts);
  for (int32_t id : player.prize)
    if (id)
      collect_card(id, counts);
  return counts;
}

static void collect_global_cards(const pvs::CurrentView &current, int player,
                                 std::unordered_map<int, int> &counts) {
  for (const auto &card : current.stadium)
    if (card.player_index == player)
      collect_card(card.id, counts);
  for (const auto &card : current.looking)
    if (card.player_index == player)
      collect_card(card.id, counts);
}

static std::vector<int> remainder(const std::vector<int> &deck,
                                  const std::unordered_map<int, int> &used) {
  auto copy = used;
  std::vector<int> rest;
  for (int id : deck) {
    auto it = copy.find(id);
    if (it != copy.end() && it->second) {
      --it->second;
    } else {
      rest.push_back(id);
    }
  }
  for (const auto &[_, count] : copy)
    if (count > 0)
      return {};
  return rest;
}

static std::vector<int>
remainder_relaxed(const std::vector<int> &deck,
                  const std::unordered_map<int, int> &used) {
  auto copy = used;
  std::vector<int> rest;
  rest.reserve(deck.size());
  for (int id : deck) {
    auto it = copy.find(id);
    if (it != copy.end() && it->second > 0) {
      --it->second;
    } else {
      rest.push_back(id);
    }
  }
  return rest;
}

static bool read_catalog(const char *path) {
  catalog.clear();
  std::ifstream f(path, std::ios::binary);
  if (!f)
    return false;
  std::string s((std::istreambuf_iterator<char>(f)), {});
  mj::Parser p(s);
  auto root = p.parse();
  if (!p.ok())
    return false;
  for (auto &d : root.at("entries").as_array()) {
    Deck x;
    for (auto &c : d.at("deck").as_array())
      x.cards.push_back(c.integer());
    x.prior = d.at("prior").as_number();
    if (x.cards.size() == 60)
      catalog.push_back(std::move(x));
  }
  return !catalog.empty();
}

static bool read_card_metadata() {
  basic_cards.clear();
  const char *json = api.all_card();
  if (!json)
    return false;
  mj::Parser parser(json);
  auto cards = parser.parse();
  if (!parser.ok() || cards.kind != mj::Value::Array)
    return false;
  for (const auto &card : cards.as_array())
    if (card.at("basic").kind == mj::Value::Bool && card.at("basic").as_bool())
      basic_cards[card.at("cardId").integer()] = true;
  return !basic_cards.empty();
}

struct World {
  std::vector<int> yd, yp, od, op, oh, oa;
  double weight = 1;
};

static std::vector<int> merge_prizes(const std::vector<int32_t> &known,
                                     std::vector<int> unknown) {
  std::vector<int> result;
  result.reserve(known.size());
  size_t next = 0;
  for (int32_t id : known) {
    if (id)
      result.push_back(id);
    else if (next < unknown.size())
      result.push_back(unknown[next++]);
  }
  return result;
}

static double multiset_jaccard(const std::vector<int> &left,
                               const std::vector<int> &right) {
  if (left.empty() && right.empty())
    return 0.0;
  std::unordered_map<int, int> a, b;
  for (int id : left)
    ++a[id];
  for (int id : right)
    ++b[id];
  double inter = 0, uni = 0;
  for (const auto &[id, count] : a) {
    int other = b.count(id) ? b.at(id) : 0;
    inter += std::min(count, other);
    uni += std::max(count, other);
  }
  for (const auto &[id, count] : b)
    if (!a.count(id))
      uni += count;
  return uni > 0 ? inter / uni : 0.0;
}

static int pool_card_usage(int id, const std::unordered_map<int, int> &seen,
                           const std::vector<int> &pool) {
  int used = seen.count(id) ? seen.at(id) : 0;
  for (int card : pool)
    if (card == id)
      ++used;
  return used;
}

static std::vector<int>
synthesize_opponent_pool(int need, const std::unordered_map<int, int> &seen,
                         const std::vector<int> &own, bool require_basic) {
  if (need <= 0)
    return {};
  if (catalog.empty())
    return {};
  std::vector<int> seen_vec;
  seen_vec.reserve(32);
  for (const auto &[id, count] : seen)
    for (int i = 0; i < count; ++i)
      seen_vec.push_back(id);
  std::vector<std::pair<const Deck *, double>> ranked;
  ranked.reserve(catalog.size());
  for (const auto &entry : catalog) {
    double sim_own = multiset_jaccard(entry.cards, own);
    double sim_seen =
        seen_vec.empty() ? 0.0 : multiset_jaccard(entry.cards, seen_vec);
    double score = (0.55 * sim_own + 0.35 * sim_seen + 0.10) *
                   std::max(1e-12, entry.prior);
    ranked.push_back({&entry, score});
  }
  std::sort(ranked.begin(), ranked.end(), [](const auto &lhs, const auto &rhs) {
    return lhs.second > rhs.second;
  });
  if (ranked.size() > 48)
    ranked.resize(48);
  std::unordered_map<int, double> weight;
  for (const auto &[deck, score] : ranked) {
    auto rem = remainder(deck->cards, seen);
    for (int id : rem)
      weight[id] += score;
    for (int id : deck->cards)
      weight[id] += score * 0.12;
  }
  for (const auto &entry : catalog)
    for (int id : entry.cards)
      weight[id] += entry.prior * 0.005;
  if (require_basic) {
    for (auto &[id, w] : weight)
      if (basic_cards.count(id))
        w *= 2.5;
  }
  std::vector<int> pool;
  pool.reserve(size_t(need));
  while (int(pool.size()) < need) {
    int best_id = 0;
    double best_w = -1.0;
    for (const auto &[id, w] : weight) {
      if (!id || pool_card_usage(id, seen, pool) >= 4)
        continue;
      if (w > best_w) {
        best_w = w;
        best_id = id;
      }
    }
    if (!best_id || best_w < 0)
      break;
    pool.push_back(best_id);
  }
  if (int(pool.size()) < need) {
    std::unordered_map<int, double> freq;
    for (const auto &entry : catalog)
      for (int id : entry.cards)
        freq[id] += entry.prior;
    std::vector<std::pair<int, double>> by_freq(freq.begin(), freq.end());
    std::sort(by_freq.begin(), by_freq.end(),
              [](const auto &lhs, const auto &rhs) {
                return lhs.second > rhs.second;
              });
    for (const auto &[id, _] : by_freq) {
      while (int(pool.size()) < need && pool_card_usage(id, seen, pool) < 4)
        pool.push_back(id);
      if (int(pool.size()) >= need)
        break;
    }
  }
  if (require_basic) {
    bool has_basic = false;
    for (int id : pool)
      if (basic_cards.count(id)) {
        has_basic = true;
        break;
      }
    if (!has_basic) {
      int best_basic = 0;
      double best_w = -1.0;
      for (const auto &[id, w] : weight)
        if (basic_cards.count(id) && w > best_w) {
          best_w = w;
          best_basic = id;
        }
      if (!best_basic) {
        for (const auto &entry : catalog)
          for (int id : entry.cards)
            if (basic_cards.count(id)) {
              best_basic = id;
              break;
            }
      }
      if (best_basic) {
        if (int(pool.size()) >= need)
          pool[size_t(need - 1)] = best_basic;
        else
          pool.push_back(best_basic);
      }
    }
  }
  if (int(pool.size()) > need)
    pool.resize(size_t(need));
  return pool;
}

static std::vector<int>
adjust_pool_size(std::vector<int> pool, int need,
                 const std::unordered_map<int, int> &seen,
                 const std::vector<int> &deck, bool require_basic) {
  if (need <= 0)
    return {};
  if (int(pool.size()) > need)
    pool.resize(size_t(need));
  if (int(pool.size()) < need) {
    auto extra = synthesize_opponent_pool(need - int(pool.size()), seen, deck,
                                          require_basic);
    pool.insert(pool.end(), extra.begin(), extra.end());
  }
  if (int(pool.size()) < need)
    pool = synthesize_opponent_pool(need, seen, deck, require_basic);
  if (int(pool.size()) > need)
    pool.resize(size_t(need));
  return pool;
}

static uint64_t fnv64_mix(uint64_t hash, uint64_t value) {
  hash ^= value;
  hash *= 0x100000001b3ULL;
  return hash;
}

static uint64_t belief_rng_seed(const GameState &obs, int particle) {
  uint64_t hash = 0xcbf29ce484222325ULL;
  const auto &current = obs.current;
  hash = fnv64_mix(hash, uint64_t(current.turn));
  hash = fnv64_mix(hash, uint64_t(current.turn_action_count));
  hash = fnv64_mix(hash, uint64_t(current.your_index));
  hash = fnv64_mix(hash, uint64_t(current.first_player));
  for (int player_index = 0; player_index < 2; ++player_index) {
    const auto &player = current.players[player_index];
    hash = fnv64_mix(hash, uint64_t(player.deck_count));
    hash = fnv64_mix(hash, uint64_t(player.hand_count));
    hash = fnv64_mix(hash, uint64_t(player.prize.size()));
  }
  return fnv64_mix(hash, uint64_t(particle));
}

static std::vector<World> build_degraded_worlds(
    const GameState &obs, const std::vector<int> &own,
    const std::unordered_map<int, int> &seen,
    const std::unordered_map<int, int> &own_seen, int own_need, int on, int opn,
    int ohn, bool hidden_active, Clock::time_point deadline) {
  const auto &cur = obs.current;
  int yi = cur.your_index;
  const auto &me = cur.players[yi];
  const auto &them = cur.players[1 - yi];
  std::vector<World> out;
  for (int i = 0; i < cfg.hypotheses; ++i) {
    if (Clock::now() >= deadline)
      break;
    std::mt19937_64 rng(belief_rng_seed(obs, i));
    World w;
    w.weight = 0.25;
    w.od = synthesize_opponent_pool(on, seen, own, false);
    w.oh = synthesize_opponent_pool(ohn, seen, own, false);
    w.op = merge_prizes(
        them.prize, synthesize_opponent_pool(opn, seen, own, false));
    if (hidden_active) {
      auto basics = synthesize_opponent_pool(1, seen, own, true);
      if (!basics.empty())
        w.oa.push_back(basics.front());
    }
    auto myrem = remainder(own, own_seen);
    if (int(myrem.size()) < own_need)
      myrem = adjust_pool_size(std::move(myrem), own_need, own_seen, own, false);
    if (int(myrem.size()) > own_need)
      myrem.resize(size_t(own_need));
    std::shuffle(myrem.begin(), myrem.end(), rng);
    auto mtake = [&](std::vector<int> &v, int k) {
      k = std::min(k, int(myrem.size()));
      v.insert(v.end(), myrem.end() - k, myrem.end());
      myrem.resize(myrem.size() - size_t(k));
    };
    std::vector<int> own_prize_unknown;
    mtake(own_prize_unknown, int(std::count(me.prize.begin(), me.prize.end(), 0)));
    w.yp = merge_prizes(me.prize, std::move(own_prize_unknown));
    mtake(w.yd, me.deck_count);
    if (int(w.od.size()) != on || int(w.oh.size()) != ohn ||
        int(w.yd.size()) != me.deck_count)
      continue;
    out.push_back(std::move(w));
  }
  return out;
}

static std::vector<World> worlds(const GameState &obs,
                                 const std::vector<int> &own,
                                 Clock::time_point deadline) {
  last_belief_degraded = false;
  const auto &cur = obs.current;
  int yi = cur.your_index;
  const auto &me = cur.players[yi];
  const auto &them = cur.players[1 - yi];
  int yn = me.deck_count;
  int ypn = int(std::count(me.prize.begin(), me.prize.end(), 0));
  int on = them.deck_count;
  int opn = int(std::count(them.prize.begin(), them.prize.end(), 0));
  int ohn = them.hand_count;
  bool hidden_active = !them.active.empty() && them.active.front().face_down;
  auto own_seen = visible_player(me);
  collect_global_cards(cur, yi, own_seen);
  auto myrem = remainder(own, own_seen);
  int own_need = yn + ypn;
  if (int(myrem.size()) != own_need)
    return {};
  auto seen = visible_player(them);
  collect_global_cards(cur, 1 - yi, seen);
  std::vector<int> seen_vec;
  seen_vec.reserve(32);
  for (const auto &[id, count] : seen)
    for (int i = 0; i < count; ++i)
      seen_vec.push_back(id);
  std::vector<std::pair<const Deck *, std::vector<int>>> candidates;
  int required_hidden_cards = on + opn + ohn + int(hidden_active);
  for (auto &deck : catalog) {
    auto remaining = remainder(deck.cards, seen);
    if (int(remaining.size()) == required_hidden_cards)
      candidates.push_back({&deck, std::move(remaining)});
  }
  if (candidates.empty()) {
    last_belief_degraded = true;
    return build_degraded_worlds(obs, own, seen, own_seen, own_need, on, opn,
                                 ohn, hidden_active, deadline);
  }
  std::vector<World> out;
  std::vector<double> posterior;
  posterior.reserve(candidates.size());
  for (const auto &candidate : candidates) {
    double logp = std::log(std::max(1e-12, candidate.first->prior));
    if (!seen_vec.empty())
      logp += 2.0 * multiset_jaccard(candidate.first->cards, seen_vec);
    posterior.push_back(std::exp(logp));
  }
  for (int i = 0; i < cfg.hypotheses; i++) {
    if (Clock::now() >= deadline)
      break;
    std::mt19937_64 rng(belief_rng_seed(obs, i));
    std::discrete_distribution<size_t> sample_candidate(posterior.begin(),
                                                          posterior.end());
    const auto &candidate = candidates[sample_candidate(rng)];
    auto pool = candidate.second;
    std::shuffle(pool.begin(), pool.end(), rng);
    World w;
    w.weight = 1.0;
    auto take = [&](std::vector<int> &v, int k) {
      k = std::min(k, int(pool.size()));
      if (k <= 0)
        return;
      v.insert(v.end(), pool.end() - k, pool.end());
      pool.resize(pool.size() - size_t(k));
    };
    if (hidden_active) {
      auto basic = std::find_if(pool.begin(), pool.end(), [](int id) {
        return basic_cards.find(id) != basic_cards.end();
      });
      if (basic == pool.end())
        continue;
      w.oa.push_back(*basic);
      pool.erase(basic);
    }
    take(w.oh, ohn);
    std::vector<int> opponent_prize_unknown;
    take(opponent_prize_unknown, opn);
    w.op = merge_prizes(them.prize, std::move(opponent_prize_unknown));
    take(w.od, on);
    auto mp = myrem;
    std::shuffle(mp.begin(), mp.end(), rng);
    auto mtake = [&](std::vector<int> &v, int k) {
      k = std::min(k, int(mp.size()));
      v.insert(v.end(), mp.end() - k, mp.end());
      mp.resize(mp.size() - k);
    };
    std::vector<int> own_prize_unknown;
    mtake(own_prize_unknown, ypn);
    w.yp = merge_prizes(me.prize, std::move(own_prize_unknown));
    mtake(w.yd, yn);
    out.push_back(std::move(w));
  }
  double z = 0;
  for (auto &w : out)
    z += w.weight;
  if (z <= 0)
    return {};
  for (auto &w : out)
    w.weight /= z;
  return out;
}

struct Action {
  std::vector<int> pick;
  float order = 0;
};

static int option_type_at(const GameState &obs, const Action &action) {
  if (!obs.has_select || action.pick.size() != 1)
    return -1;
  int idx = action.pick[0];
  if (idx < 0 || idx >= int(obs.select.options.size()))
    return -1;
  return obs.select.options[idx].type;
}

static bool same_option(const pvs::OptionView &a, const pvs::OptionView &b) {
  return a.type == b.type && a.card_id == b.card_id &&
         a.attack_id == b.attack_id && a.area == b.area &&
         a.index == b.index && a.player_index == b.player_index &&
         a.in_play_area == b.in_play_area &&
         a.in_play_index == b.in_play_index && a.number == b.number &&
         a.count == b.count &&
         a.special_condition_type == b.special_condition_type &&
         a.tool_index == b.tool_index && a.energy_index == b.energy_index &&
         a.serial == b.serial;
}

static bool same_option_multiset(const std::vector<pvs::OptionView> &a,
                                 const std::vector<pvs::OptionView> &b) {
  if (a.size() != b.size())
    return false;
  std::vector<bool> used(b.size(), false);
  for (const auto &left : a) {
    bool found = false;
    for (size_t j = 0; j < b.size(); ++j) {
      if (!used[j] && same_option(left, b[j])) {
        used[j] = true;
        found = true;
        break;
      }
    }
    if (!found)
      return false;
  }
  return true;
}

// SearchBegin reconstructs the position and is allowed to emit its options in
// a different order.  SearchStep indices belong to that reconstructed state,
// not to the public observation passed to pvs_choose.
static std::vector<int> option_index_map(const GameState &from,
                                         const GameState &to) {
  std::vector<int> result(from.select.options.size(), -1);
  std::vector<bool> used(to.select.options.size(), false);
  for (size_t i = 0; i < from.select.options.size(); ++i) {
    for (size_t j = 0; j < to.select.options.size(); ++j) {
      if (!used[j] && same_option(from.select.options[i], to.select.options[j])) {
        result[i] = int(j);
        used[j] = true;
        break;
      }
    }
  }
  return result;
}

static std::optional<Action> remap_action(const Action &action,
                                          const std::vector<int> &index_map) {
  Action mapped = action;
  for (int &index : mapped.pick) {
    if (index < 0 || index >= int(index_map.size()) || index_map[index] < 0)
      return std::nullopt;
    index = index_map[index];
  }
  return mapped;
}

static void combos_rec(int n, int need, int at, std::vector<int> &cur,
                       std::vector<Action> &out, int cap) {
  if (int(out.size()) >= cap)
    return;
  if (!need) {
    out.push_back({cur, 0});
    return;
  }
  for (int i = at; i <= n - need; i++) {
    cur.push_back(i);
    combos_rec(n, need - 1, i + 1, cur, out, cap);
    cur.pop_back();
  }
}

static bool action_space_fits(const pvs::SelectView &select, uint64_t limit) {
  const int n = int(select.options.size());
  const int lo = std::clamp<int>(select.min_count, 0, n);
  const int hi = std::clamp<int>(select.max_count, 0, n);
  uint64_t total = 0;
  for (int k = lo; k <= hi; ++k) {
    const int choose = std::min(k, n - k);
    uint64_t combinations = 1;
    for (int i = 1; i <= choose; ++i) {
      if (combinations > limit * uint64_t(i) / uint64_t(n - choose + i))
        return false;
      combinations = combinations * uint64_t(n - choose + i) / uint64_t(i);
    }
    if (total > limit - std::min(limit, combinations))
      return false;
    total += combinations;
    if (total > limit)
      return false;
  }
  return true;
}

static std::vector<float> neural_hidden(const GameState &obs, int perspective) {
  if (!model.loaded)
    return {};
  const auto &c = obs.current;
  std::vector<uint32_t> ids;
  ids.reserve(48);
  using pvs::hash::append;
  using pvs::hash::append_int;
  using pvs::hash::fnv;
  auto add_text = [&](std::string_view text) {
    push_unique_id(ids, fnv(text));
  };
  auto add_side_zone_card = [&](const char *side, const char *zone,
                                int card_id) {
    uint32_t hash = fnv(side);
    hash = append(":", hash);
    hash = append(zone, hash);
    hash = append(":", hash);
    hash = append_int(hash, card_id);
    push_unique_id(ids, hash);
  };
  auto add_side_zone_hp = [&](const char *side, const char *zone, int hp) {
    uint32_t hash = fnv(side);
    hash = append(":", hash);
    hash = append(zone, hash);
    hash = append(":hp:", hash);
    hash = append_int(hash, hp);
    push_unique_id(ids, hash);
  };
  for (int pi = 0; pi < 2; ++pi) {
    const char *side = pi == perspective ? "us" : "them";
    const auto &p = c.players[pi];
    uint32_t prize_hash = fnv(side);
    prize_hash = append(":prize:", prize_hash);
    push_unique_id(ids, append_int(prize_hash, int(p.prize.size())));
    uint32_t deck_hash = fnv(side);
    deck_hash = append(":deck:", deck_hash);
    push_unique_id(ids, append_int(deck_hash, p.deck_count / 4));
    for (const auto &slot : p.active) {
      if (!slot.present || slot.face_down)
        continue;
      add_side_zone_card(side, "active", slot.id);
      add_side_zone_hp(side, "active", slot.hp / 20);
    }
    for (const auto &slot : p.bench) {
      if (!slot.present || slot.face_down)
        continue;
      add_side_zone_card(side, "bench", slot.id);
      add_side_zone_hp(side, "bench", slot.hp / 20);
    }
    for (const auto &card : p.discard) {
      if (card.id)
        add_side_zone_card(side, "discard", card.id);
    }
    if (pi == perspective) {
      for (const auto &card : p.hand) {
        if (card.id)
          add_side_zone_card(side, "hand", card.id);
      }
    } else {
      uint32_t hand_hash = fnv(side);
      hand_hash = append(":hand:", hand_hash);
      push_unique_id(ids, append_int(hand_hash, p.hand_count / 4));
    }
  }
  push_unique_id(ids, append_int(fnv("turn:"), c.turn / 2));
  push_unique_id(
      ids, fnv(c.first_player == perspective ? "first:True" : "first:False"));
  finalize_ids(ids, model.nf);
  std::vector<float> hidden(model.nh);
  std::copy(model.bias.begin(), model.bias.end(), hidden.begin());
  for (uint32_t id : ids)
    add_quantized(hidden.data(), model.emb.data() + size_t(id) * model.nh,
                  model.nh, model.es);
  for (float &value : hidden)
    value = std::clamp(value, 0.f, 127.f);
  return hidden;
}

static int resolve_card_id(const GameState &obs,
                           const pvs::OptionView &option) {
  int type = option.type;
  int area = pvs::option_int(option, &pvs::OptionView::area,
                             type == 7 || type == 8 || type == 9 ? 2 : -1);
  int player = pvs::option_int(option, &pvs::OptionView::player_index,
                               obs.current.your_index);
  int index = pvs::option_int(option, &pvs::OptionView::index, -1);
  const pvs::PlayerView *player_view = nullptr;
  const void *zone = nullptr;
  size_t zone_size = 0;
  bool pokemon_zone = false;
  if (area == 2) {
    player_view = &obs.current.players[player];
    zone = player_view->hand.data();
    zone_size = player_view->hand.size();
  } else if (area == 3) {
    player_view = &obs.current.players[player];
    zone = player_view->discard.data();
    zone_size = player_view->discard.size();
  } else if (area == 4) {
    player_view = &obs.current.players[player];
    zone = player_view->active.data();
    zone_size = player_view->active.size();
    pokemon_zone = true;
  } else if (area == 5) {
    player_view = &obs.current.players[player];
    zone = player_view->bench.data();
    zone_size = player_view->bench.size();
    pokemon_zone = true;
  } else if (area == 6) {
    player_view = &obs.current.players[player];
    if (index < 0 || index >= int(player_view->prize.size()))
      return 0;
    return player_view->prize[index];
  }
  if (!zone || index < 0 || size_t(index) >= zone_size)
    return 0;
  if (pokemon_zone) {
    const auto &slot = reinterpret_cast<const pvs::PokemonSlot *>(zone)[index];
    return slot.present && !slot.face_down ? slot.id : 0;
  }
  return reinterpret_cast<const pvs::CardSlot *>(zone)[index].id;
}

static void add_action_kv(std::vector<uint32_t> &ids, const char *key,
                          int value) {
  uint32_t hash = pvs::hash::append("action:", pvs::hash::fnv_basis());
  hash = pvs::hash::append(key, hash);
  hash = pvs::hash::append_int(hash, value);
  push_unique_id(ids, hash);
}

static void action_feature_ids(const GameState &observation,
                               const pvs::OptionView &option,
                               std::vector<uint32_t> &ids) {
  ids.clear();
  if (ids.capacity() < 16)
    ids.reserve(16);
  add_action_kv(ids, "context:", observation.select.context);
  add_action_kv(ids, "type:", option.type);
  if (pvs::option_has(option, &pvs::OptionView::card_id))
    add_action_kv(ids, "cardId:", int(option.card_id));
  if (pvs::option_has(option, &pvs::OptionView::attack_id))
    add_action_kv(ids, "attackId:", int(option.attack_id));
  if (pvs::option_has16(option, &pvs::OptionView::area))
    add_action_kv(ids, "area:", int(option.area));
  if (pvs::option_has16(option, &pvs::OptionView::index))
    add_action_kv(ids, "index:", int(option.index));
  if (pvs::option_has16(option, &pvs::OptionView::player_index))
    add_action_kv(ids, "playerIndex:", int(option.player_index));
  if (pvs::option_has16(option, &pvs::OptionView::in_play_area))
    add_action_kv(ids, "inPlayArea:", int(option.in_play_area));
  if (pvs::option_has16(option, &pvs::OptionView::in_play_index))
    add_action_kv(ids, "inPlayIndex:", int(option.in_play_index));
  if (pvs::option_has16(option, &pvs::OptionView::number))
    add_action_kv(ids, "number:", int(option.number));
  if (pvs::option_has16(option, &pvs::OptionView::count))
    add_action_kv(ids, "count:", int(option.count));
  if (pvs::option_has16(option, &pvs::OptionView::special_condition_type))
    add_action_kv(ids,
                  "specialConditionType:", int(option.special_condition_type));
  if (pvs::option_has(option, &pvs::OptionView::card_id)) {
    uint32_t hash = pvs::hash::append("action:", pvs::hash::fnv_basis());
    hash = pvs::hash::append("type_card:", hash);
    hash = pvs::hash::append_int(hash, option.type);
    hash = pvs::hash::append(":", hash);
    hash = pvs::hash::append_int(hash, int(option.card_id));
    push_unique_id(ids, hash);
  }
  int card_id = resolve_card_id(observation, option);
  if (card_id) {
    add_action_kv(ids, "resolvedCard:", card_id);
    uint32_t hash = pvs::hash::append("action:", pvs::hash::fnv_basis());
    hash = pvs::hash::append("type_resolved:", hash);
    hash = pvs::hash::append_int(hash, option.type);
    hash = pvs::hash::append(":", hash);
    hash = pvs::hash::append_int(hash, card_id);
    push_unique_id(ids, hash);
  }
  finalize_ids(ids, model.nf);
}

static float action_policy_score(const GameState &observation,
                                 const pvs::OptionView &option,
                                 const std::vector<float> &hidden) {
  if (hidden.empty())
    return 0.f;
  thread_local std::vector<uint32_t> ids;
  action_feature_ids(observation, option, ids);
  // dot(hidden, sum(embedding)) == sum(dot(hidden, embedding)).  Computing it
  // directly avoids clearing and updating a 128-float temporary for every
  // option, followed by a second traversal for inner_product.
  float score = 0.f;
  for (uint32_t id : ids)
    score += dot_quantized(hidden.data(),
                           model.action_emb.data() + size_t(id) * model.nh,
                           model.nh, model.es);
  return score / std::sqrt(float(model.nh));
}

// Prize positions are deliberately indistinguishable to the player.  SearchBegin
// fills them for a determinized world, but maximizing over those hidden IDs would
// be strategy fusion: the real agent cannot condition its pick on that knowledge.
// A fixed representative index is random in distribution because every world's
// prize permutation is sampled independently.
static std::optional<Action>
representative_hidden_random_action(const GameState &observation) {
  if (!observation.has_select)
    return std::nullopt;
  const auto &select = observation.select;
  if (select.context != kToHandChoiceContext ||
      select.min_count != select.max_count)
    return std::nullopt;
  const int required = select.min_count;
  if (required < 0 || required > int(select.options.size()) ||
      select.options.empty())
    return std::nullopt;
  for (const auto &option : select.options) {
    if (option.type != kCardOption ||
        pvs::option_int(option, &pvs::OptionView::area, -1) != kPrizeArea)
      return std::nullopt;
  }
  Action representative;
  representative.pick.resize(size_t(required));
  std::iota(representative.pick.begin(), representative.pick.end(), 0);
  return representative;
}

static std::vector<Action>
actions(const GameState &observation,
        const std::vector<float> *cached_hidden = nullptr,
        bool use_policy = true, int action_limit = kActionLimit,
        int enumeration_limit = kCombinationEnumerationLimit) {
  std::vector<Action> out;
  if (!observation.has_select)
    return out;
  if (auto representative = representative_hidden_random_action(observation)) {
    out.push_back(std::move(*representative));
    return out;
  }
  const auto &s = observation.select;
  int n = int(s.options.size());
  int lo = s.min_count, hi = s.max_count;
  std::vector<int> cur;
  int actor = observation.current.your_index;
  std::vector<float> owned_hidden;
  const std::vector<float> &hidden = use_policy
      ? (cached_hidden && !cached_hidden->empty()
             ? *cached_hidden
             : (owned_hidden = neural_hidden(observation, actor), owned_hidden))
      : owned_hidden;
  std::vector<float> option_scores(n);
  for (int i = 0; i < n; ++i)
    option_scores[i] = option_heuristic(s.options[i].type) +
                       action_policy_score(observation, s.options[i], hidden);
  if (lo == 1 && hi == 1) {
    out.reserve(std::min(n, action_limit));
    std::vector<int> order(n);
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
      return option_scores[a] > option_scores[b];
    });
    for (int i = 0; i < n && int(out.size()) < action_limit; ++i) {
      const int candidate = order[i];
      const bool duplicate = std::any_of(
          out.begin(), out.end(), [&](const Action &existing) {
            return same_option(s.options[candidate],
                               s.options[existing.pick.front()]);
          });
      if (!duplicate)
        out.push_back({{candidate}, option_scores[candidate]});
    }
    return out;
  }
  for (int k = lo; k <= hi && int(out.size()) < enumeration_limit;
       k++)
    combos_rec(n, k, 0, cur, out, enumeration_limit);
  for (auto &a : out) {
    float q = 0;
    for (int i : a.pick)
      q += option_scores[i];
    a.order = q;
  }
  std::stable_sort(out.begin(), out.end(),
                   [](auto &a, auto &b) { return a.order > b.order; });
  if (out.size() > size_t(action_limit))
    out.resize(size_t(action_limit));
  return out;
}

static std::optional<Action> sole_legal_action(const GameState &observation) {
  if (!observation.has_select)
    return std::nullopt;
  const auto &select = observation.select;
  const int count = int(select.options.size());
  if (select.min_count != select.max_count)
    return std::nullopt;
  const int required = select.min_count;
  if (required != 0 && required != count)
    return std::nullopt;
  Action action;
  action.pick.resize(size_t(required));
  std::iota(action.pick.begin(), action.pick.end(), 0);
  return action;
}

static float player_score(const pvs::PlayerView &player) {
  float score = -220.f * float(player.prize.size()) + 1.5f * player.deck_count +
                3.f * player.hand_count;
  auto add_pokemon = [&](const pvs::PokemonSlot &slot) {
    if (!slot.present || slot.face_down)
      return;
    score += .32f * slot.hp + 11.f * float(slot.energy_count) +
             18.f * float(slot.pre_evolution_count);
  };
  for (const auto &slot : player.active)
    add_pokemon(slot);
  for (const auto &slot : player.bench)
    add_pokemon(slot);
  return score;
}

static int active_hp(const pvs::PlayerView &player) {
  if (player.active.empty() || !player.active.front().present)
    return 9999;
  return int(player.active.front().hp);
}

static float prize_race_score(const GameState &obs, int root_player) {
  const auto &me = obs.current.players[root_player];
  const auto &opp = obs.current.players[1 - root_player];
  float score = 0.f;
  score += 150.f * float(6 - int(me.prize.size()));
  score -= 170.f * float(6 - int(opp.prize.size()));
  const int opp_hp = active_hp(opp);
  const int my_hp = active_hp(me);
  if (opp_hp > 0 && opp_hp <= 80)
    score += 35.f;
  if (my_hp > 0 && my_hp <= 40)
    score -= 45.f;
  if (!me.active.empty() && me.active.front().present)
    score += 10.f * float(me.active.front().energy_count);
  if (!opp.active.empty() && opp.active.front().present)
    score -= 4.f * float(opp.active.front().energy_count);
  return score;
}

static uint64_t commutative_mix_id(int32_t id) {
  return fnv64_mix(0x9e3779b97f4a7c15ULL, uint64_t(uint32_t(id)));
}

static uint64_t commutative_zone_hash(const std::vector<int32_t> &ids) {
  uint64_t zone = 0;
  for (int32_t id : ids)
    zone += commutative_mix_id(id);
  return zone;
}

static uint64_t commutative_card_zone_hash(
    const std::vector<pvs::CardSlot> &cards) {
  uint64_t zone = 0;
  for (const auto &card : cards)
    zone += commutative_mix_id(card.id);
  return zone;
}

static uint64_t position_hash(const GameState &obs) {
  uint64_t hash = 0xcbf29ce484222325ULL;
  const auto &current = obs.current;
  hash = fnv64_mix(hash, uint64_t(current.turn));
  hash = fnv64_mix(hash, uint64_t(current.turn_action_count));
  hash = fnv64_mix(hash, uint64_t(current.your_index));
  hash = fnv64_mix(hash, uint64_t(current.result));
  if (obs.has_select) {
    hash = fnv64_mix(hash, uint64_t(obs.select.context));
    hash = fnv64_mix(hash, uint64_t(obs.select.min_count));
    hash = fnv64_mix(hash, uint64_t(obs.select.max_count));
    hash = fnv64_mix(hash, uint64_t(obs.select.options.size()));
    for (const auto &option : obs.select.options) {
      hash = fnv64_mix(hash, uint64_t(option.type));
      hash = fnv64_mix(hash, uint64_t(option.card_id));
      hash = fnv64_mix(hash, uint64_t(option.attack_id));
      hash = fnv64_mix(hash, uint64_t(option.area));
      hash = fnv64_mix(hash, uint64_t(option.index));
      hash = fnv64_mix(hash, uint64_t(option.in_play_area));
      hash = fnv64_mix(hash, uint64_t(option.in_play_index));
      hash = fnv64_mix(hash, uint64_t(option.serial));
    }
  }
  uint64_t stadium_zone = 0;
  for (const auto &card : current.stadium)
    stadium_zone += commutative_mix_id(card.id);
  hash = fnv64_mix(hash, stadium_zone);
  for (int player_index = 0; player_index < 2; ++player_index) {
    const auto &player = current.players[player_index];
    hash = fnv64_mix(hash, uint64_t(player.deck_count));
    hash = fnv64_mix(hash, uint64_t(player.hand_count));
    hash = fnv64_mix(hash, uint64_t(player.prize.size()));
    hash = fnv64_mix(hash, commutative_zone_hash(player.prize));
    hash = fnv64_mix(hash, commutative_card_zone_hash(player.hand));
    hash = fnv64_mix(hash, commutative_card_zone_hash(player.discard));
    auto mix_slot = [&](const pvs::PokemonSlot &slot) {
      if (!slot.present)
        return;
      hash = fnv64_mix(hash, uint64_t(slot.id));
      hash = fnv64_mix(hash, uint64_t(slot.hp));
      hash = fnv64_mix(hash, uint64_t(slot.energy_count));
      hash = fnv64_mix(hash, uint64_t(slot.pre_evolution_count));
      uint64_t attached_zone = 0;
      for (int32_t aid : slot.attached_ids)
        attached_zone += commutative_mix_id(aid);
      hash = fnv64_mix(hash, attached_zone);
    };
    for (const auto &slot : player.active)
      mix_slot(slot);
    for (const auto &slot : player.bench)
      mix_slot(slot);
  }
  return hash;
}

struct PlanCheckpoint {
  int context = -1;
  int min_count = 0;
  int max_count = 0;
  std::vector<pvs::OptionView> options;
  std::vector<int> pick;
};

struct PlanCache {
  int turn = -1;
  size_t index = 0;
  std::vector<PlanCheckpoint> steps;
} plan_cache;

static std::optional<std::vector<int>>
remap_pick_to_obs(const PlanCheckpoint &checkpoint, const GameState &obs) {
  if (!obs.has_select)
    return std::nullopt;
  const auto &live = obs.select;
  if (live.context != checkpoint.context ||
      live.min_count != checkpoint.min_count ||
      live.max_count != checkpoint.max_count)
    return std::nullopt;
  if (!same_option_multiset(checkpoint.options, live.options))
    return std::nullopt;
  std::vector<bool> used(live.options.size(), false);
  std::vector<int> remapped;
  remapped.reserve(checkpoint.pick.size());
  for (int stored_index : checkpoint.pick) {
    if (stored_index < 0 || stored_index >= int(checkpoint.options.size()))
      return std::nullopt;
    const auto &target = checkpoint.options[size_t(stored_index)];
    int mapped = -1;
    for (size_t j = 0; j < live.options.size(); ++j) {
      if (!used[j] && same_option(target, live.options[j])) {
        mapped = int(j);
        used[j] = true;
        break;
      }
    }
    if (mapped < 0)
      return std::nullopt;
    remapped.push_back(mapped);
  }
  return remapped;
}

static PlanCheckpoint checkpoint_from(const GameState &obs,
                                    const std::vector<int> &pick) {
  PlanCheckpoint checkpoint;
  if (!obs.has_select)
    return checkpoint;
  checkpoint.context = obs.select.context;
  checkpoint.min_count = obs.select.min_count;
  checkpoint.max_count = obs.select.max_count;
  checkpoint.options = obs.select.options;
  checkpoint.pick = pick;
  return checkpoint;
}

static float evaluate(const GameState &obs, int root_player,
                      const std::vector<float> *cached_hidden = nullptr) {
  const auto &c = obs.current;
  if (c.result == 2)
    return 0.f;
  if (c.result >= 0)
    return c.result == root_player ? kWinScore : -kWinScore;
  float hand = player_score(c.players[root_player]) -
               player_score(c.players[1 - root_player]);
  float race = prize_race_score(obs, root_player);
  if (!model.loaded)
    return hand + race;
  int model_perspective = c.your_index;
  std::vector<float> owned_hidden;
  const std::vector<float> &hidden =
      cached_hidden && !cached_hidden->empty()
          ? *cached_hidden
          : (owned_hidden = neural_hidden(obs, model_perspective),
             owned_hidden);
  float v = model.vbias;
  v += dot_quantized(hidden.data(), model.value.data(), model.nh, model.vs);
  float model_value = float(cfg.model_scale) * std::tanh(v);
  if (model_perspective != root_player)
    model_value = -model_value;
  return hand + race + model_value;
}

struct SearchMetrics {
  uint64_t simulator_ns = 0;
  uint64_t import_ns = 0;
  uint64_t action_ns = 0;
  uint64_t evaluation_ns = 0;
  uint64_t nodes = 0;
  int completed_depth = 0;
  int completed_width = 0;
  uint64_t completed_endpoints = 0;
  uint64_t intermediate_evaluations = 0;
  double root_coverage = 0.0;
  bool coverage_fallback = false;
};

struct SearchOutput {
  std::vector<float> values;
  std::vector<std::vector<PlanCheckpoint>> root_plans;
  SearchMetrics metrics;
};

struct Searcher {
  void *agent{};
  int root_player = 0;
  Clock::time_point deadline;
  uint64_t nodes = 0;
  uint64_t local_node_limit = kNodeBudgetPerWorld;
  bool endpoint_evaluation = false;
  SearchMetrics metrics;

  struct PlanState {
    std::vector<PlanCheckpoint> path;
    std::vector<PlanCheckpoint> best_path;
    float best_value = -kSearchInfinity;
    bool saw_boundary = false;
  };

  bool stop() const {
    if (nodes >= std::min(kNodeBudgetPerWorld, local_node_limit))
      return true;
    return Clock::now() >= deadline;
  }

  ApiResult step(int64_t state_id, const Action &action) {
    if (!cfg.profile)
      return import_sim_response(api.search_step(
          agent, state_id, action.pick.data(), int(action.pick.size())));
    auto start = Clock::now();
    const char *text = api.search_step(agent, state_id, action.pick.data(),
                                       int(action.pick.size()));
    auto simulated = Clock::now();
    auto result = import_sim_response(text);
    auto imported = Clock::now();
    metrics.simulator_ns +=
        std::chrono::duration_cast<std::chrono::nanoseconds>(simulated - start)
            .count();
    metrics.import_ns += std::chrono::duration_cast<std::chrono::nanoseconds>(
                             imported - simulated)
                             .count();
    return result;
  }

  float timed_evaluate(const GameState &ob,
                       const std::vector<float> *cached_hidden = nullptr) {
    if (!endpoint_evaluation)
      ++metrics.intermediate_evaluations;
    if (!cfg.profile)
      return evaluate(ob, root_player, cached_hidden);
    auto start = Clock::now();
    float value = evaluate(ob, root_player, cached_hidden);
    metrics.evaluation_ns +=
        std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() -
                                                             start)
            .count();
    return value;
  }

  float evaluate_endpoint(const GameState &ob) {
    const bool previous = endpoint_evaluation;
    endpoint_evaluation = true;
    float value = timed_evaluate(ob);
    endpoint_evaluation = previous;
    return value;
  }

  std::vector<Action>
  timed_actions(const GameState &ob,
                const std::vector<float> *cached_hidden = nullptr,
                bool use_policy = true, int action_limit = kActionLimit,
                int enumeration_limit = kCombinationEnumerationLimit) {
    if (!cfg.profile)
      return actions(ob, cached_hidden, use_policy, action_limit,
                     enumeration_limit);
    auto start = Clock::now();
    auto result = actions(ob, cached_hidden, use_policy, action_limit,
                          enumeration_limit);
    metrics.action_ns += std::chrono::duration_cast<std::chrono::nanoseconds>(
                             Clock::now() - start)
                             .count();
    return result;
  }

  bool same_turn(const GameState &obs, int origin_turn) const {
    return obs.current.result < 0 && obs.current.turn == origin_turn;
  }

  bool our_turn_active(const GameState &obs, int origin_turn) const {
    return same_turn(obs, origin_turn) &&
           obs.current.your_index == root_player;
  }

  void push_own_checkpoint(PlanState &plan, const GameState &ob,
                           const std::vector<int> &pick) {
    if (ob.current.your_index == root_player)
      plan.path.push_back(checkpoint_from(ob, pick));
  }

  float eval_with_opponent_greedy(const ApiResult::State &state, int ply = 0) {
    ++nodes;
    const auto &now = state.observation;
    if (ply >= kOpponentGreedyLimit || stop())
      return evaluate_endpoint(now);
    if (now.current.result >= 0 || now.current.your_index == root_player)
      return evaluate_endpoint(now);
    if (!now.has_select)
      return evaluate_endpoint(now);

    if (auto only = sole_legal_action(now)) {
      auto child = step(state.id, *only);
      if (child.error || !child.state)
        return evaluate_endpoint(now);
      SearchStateLease child_lease(agent, child.state->id);
      return eval_with_opponent_greedy(*child.state, ply + 1);
    }

    auto choices = timed_actions(now, nullptr, true, kPlannerForcedBranchLimit,
                                 kPlannerForcedBranchLimit);
    if (choices.empty())
      return evaluate_endpoint(now);
    if (choices.size() > 4)
      choices.resize(4);

    if (now.select.context == kCoinChoiceContext) {
      float sum = 0.f;
      int count = 0;
      for (const auto &choice : choices) {
        if (stop())
          break;
        auto child = step(state.id, choice);
        if (child.error || !child.state)
          continue;
        SearchStateLease child_lease(agent, child.state->id);
        float value = evaluate_endpoint(child.state->observation);
        if (has_value(value)) {
          sum += value;
          ++count;
        }
      }
      return count ? sum / float(count) : evaluate_endpoint(now);
    }

    float worst = kSearchInfinity;
    size_t best_index = choices.size();
    for (size_t ci = 0; ci < choices.size(); ++ci) {
      if (stop())
        break;
      auto child = step(state.id, choices[ci]);
      if (child.error || !child.state)
        continue;
      SearchStateLease child_lease(agent, child.state->id);
      float value = evaluate_endpoint(child.state->observation);
      if (has_value(value) && value < worst) {
        worst = value;
        best_index = ci;
      }
    }
    if (best_index >= choices.size())
      return evaluate_endpoint(now);
    auto child = step(state.id, choices[best_index]);
    if (child.error || !child.state)
      return evaluate_endpoint(now);
    SearchStateLease child_lease(agent, child.state->id);
    return eval_with_opponent_greedy(*child.state, ply + 1);
  }

  float eval_with_opponent_plan(const ApiResult::State &state, int origin_turn,
                                int depth) {
    ++nodes;
    const auto &now = state.observation;
    if (now.current.result >= 0)
      return evaluate_endpoint(now);
    if (now.current.your_index == root_player)
      return evaluate_endpoint(now);
    if (stop())
      return evaluate_endpoint(now);
    if (depth <= 0)
      return eval_with_opponent_greedy(state);
    if (!now.has_select)
      return evaluate_endpoint(now);

    if (auto only = sole_legal_action(now)) {
      auto child = step(state.id, *only);
      if (child.error || !child.state)
        return evaluate_endpoint(now);
      SearchStateLease child_lease(agent, child.state->id);
      return eval_with_opponent_plan(*child.state, origin_turn, depth);
    }

    const bool main = now.has_select && now.select.context == 0;
    auto choices =
        timed_actions(now, nullptr, true,
                      main ? kPlannerMainBranchLimit : kPlannerForcedBranchLimit,
                      main ? kCombinationEnumerationLimit
                           : kPlannerForcedBranchLimit);
    if (choices.empty())
      return evaluate_endpoint(now);

    if (!main && now.select.context == kCoinChoiceContext) {
      float sum = 0.f;
      int count = 0;
      for (const auto &choice : choices) {
        if (stop())
          break;
        auto child = step(state.id, choice);
        if (child.error || !child.state)
          continue;
        SearchStateLease child_lease(agent, child.state->id);
        float value =
            eval_with_opponent_plan(*child.state, origin_turn, depth);
        if (has_value(value)) {
          sum += value;
          ++count;
        }
      }
      return count ? sum / float(count) : evaluate_endpoint(now);
    }

    if (!main) {
      if (choices.size() > kSubselectExhaustiveLimit)
        choices.resize(std::min<size_t>(4, choices.size()));
      float worst = kSearchInfinity;
      bool expanded = false;
      for (const auto &choice : choices) {
        if (stop())
          break;
        auto child = step(state.id, choice);
        if (child.error || !child.state)
          continue;
        SearchStateLease child_lease(agent, child.state->id);
        float value =
            eval_with_opponent_plan(*child.state, origin_turn, depth);
        if (has_value(value)) {
          worst = std::min(worst, value);
          expanded = true;
        }
      }
      return expanded ? worst : evaluate_endpoint(now);
    }

    if (choices.size() > 4)
      choices.resize(4);
    float worst = kSearchInfinity;
    bool expanded = false;
    for (const auto &choice : choices) {
      if (stop())
        break;
      auto child = step(state.id, choice);
      if (child.error || !child.state)
        continue;
      SearchStateLease child_lease(agent, child.state->id);
      float value =
          eval_with_opponent_plan(*child.state, origin_turn, depth - 1);
      if (has_value(value)) {
        worst = std::min(worst, value);
        expanded = true;
      }
    }
    return expanded ? worst : evaluate_endpoint(now);
  }

  float eval_after_our_turn(const ApiResult::State &state, int origin_turn,
                            bool deep_opponent) {
    if (deep_opponent)
      return eval_with_opponent_plan(state, origin_turn, kOpponentPlanDepth);
    return eval_with_opponent_greedy(state);
  }

  void consider_endpoint(float value, PlanState &plan, float &best_endpoint,
                       const std::vector<PlanCheckpoint> *path_override =
                           nullptr,
                       bool turn_boundary = false) {
    if (!has_value(value))
      return;
    if (turn_boundary)
      plan.saw_boundary = true;
    ++metrics.completed_endpoints;
    if (value > plan.best_value) {
      plan.best_value = value;
      if (path_override && !path_override->empty())
        plan.best_path = *path_override;
      else if (!plan.path.empty())
        plan.best_path = plan.path;
    }
    best_endpoint = std::max(best_endpoint, value);
  }

  bool advance_opponent_forced(const ApiResult::State &state, int origin_turn,
                               Action &choice_out, ApiResult &child_out) {
    const auto &ob = state.observation;
    if (!same_turn(ob, origin_turn) || our_turn_active(ob, origin_turn) ||
        !ob.has_select)
      return false;
    auto choices = timed_actions(ob, nullptr, true, kPlannerForcedBranchLimit,
                                 kPlannerForcedBranchLimit);
    if (choices.empty())
      return false;
    choice_out = choices.front();
    child_out = step(state.id, choice_out);
    return !child_out.error && child_out.state;
  }

  float greedy_complete_turn(const ApiResult::State &state, int origin_turn,
                             int main_actions) {
    ++nodes;
    const auto &ob = state.observation;
    if (stop() && ob.current.result < 0)
      return evaluate_endpoint(ob);
    if (ob.current.result >= 0)
      return evaluate_endpoint(ob);
    if (!our_turn_active(ob, origin_turn)) {
      Action forced;
      ApiResult forced_child;
      if (advance_opponent_forced(state, origin_turn, forced, forced_child)) {
        SearchStateLease lease(agent, forced_child.state->id);
        return greedy_complete_turn(*forced_child.state, origin_turn,
                                    main_actions);
      }
      return eval_with_opponent_greedy(state);
    }
    if (main_actions >= kMainActionsPerTurnLimit)
      return eval_with_opponent_greedy(state);
    if (auto only = sole_legal_action(ob)) {
      auto child = step(state.id, *only);
      if (child.error || !child.state)
        return evaluate_endpoint(ob);
      SearchStateLease child_lease(agent, child.state->id);
      const int next_main =
          ob.has_select && ob.select.context == 0 ? main_actions + 1 : main_actions;
      return greedy_complete_turn(*child.state, origin_turn, next_main);
    }
    auto choices = timed_actions(ob, nullptr, true, kPlannerMainBranchLimit,
                                 kCombinationEnumerationLimit);
    if (choices.empty())
      return evaluate_endpoint(ob);
    const Action &choice = choices.front();
    auto child = step(state.id, choice);
    if (child.error || !child.state)
      return evaluate_endpoint(ob);
    SearchStateLease child_lease(agent, child.state->id);
    const bool main = ob.has_select && ob.select.context == 0;
    const int next_main = main ? main_actions + 1 : main_actions;
    if (!our_turn_active(child.state->observation, origin_turn)) {
      Action forced;
      ApiResult forced_child;
      if (advance_opponent_forced(*child.state, origin_turn, forced,
                                  forced_child)) {
        SearchStateLease lease(agent, forced_child.state->id);
        return greedy_complete_turn(*forced_child.state, origin_turn, next_main);
      }
      return eval_with_opponent_greedy(*child.state);
    }
    return greedy_complete_turn(*child.state, origin_turn, next_main);
  }

  float complete_turn_plan(const ApiResult::State &state, int origin_turn,
                           int main_actions,
                           std::unordered_set<uint64_t> &visited,
                           PlanState &plan, float &best_endpoint,
                           bool deep_opponent) {
    ++nodes;
    if (stop())
      return best_endpoint;
    const auto &ob = state.observation;
    if (ob.current.result >= 0) {
      consider_endpoint(evaluate_endpoint(ob), plan, best_endpoint, nullptr,
                        true);
      return best_endpoint;
    }
    if (!our_turn_active(ob, origin_turn)) {
      Action forced;
      ApiResult forced_child;
      if (advance_opponent_forced(state, origin_turn, forced, forced_child)) {
        SearchStateLease lease(agent, forced_child.state->id);
        complete_turn_plan(*forced_child.state, origin_turn, main_actions,
                           visited, plan, best_endpoint, deep_opponent);
        return best_endpoint;
      }
      consider_endpoint(
          eval_after_our_turn(state, origin_turn, deep_opponent), plan,
          best_endpoint, nullptr, true);
      return best_endpoint;
    }
    if (stop() || main_actions >= kMainActionsPerTurnLimit) {
      const bool at_boundary = main_actions >= kMainActionsPerTurnLimit;
      consider_endpoint(
          eval_after_our_turn(state, origin_turn, deep_opponent), plan,
          best_endpoint, nullptr, at_boundary);
      return best_endpoint;
    }

    const uint64_t hash = position_hash(ob);
    if (!visited.insert(hash).second)
      return best_endpoint;

    if (auto only = sole_legal_action(ob)) {
      auto child = step(state.id, *only);
      if (child.error || !child.state)
        return best_endpoint;
      SearchStateLease child_lease(agent, child.state->id);
      push_own_checkpoint(plan, ob, only->pick);
      const int next_main =
          ob.has_select && ob.select.context == 0 ? main_actions + 1 : main_actions;
      complete_turn_plan(*child.state, origin_turn, next_main, visited, plan,
                         best_endpoint, deep_opponent);
      plan.path.pop_back();
      return best_endpoint;
    }

    const bool main = ob.has_select && ob.select.context == 0;
    std::vector<Action> choices;
    if (main) {
      choices = timed_actions(ob, nullptr, true, kPlannerMainBranchLimit,
                              kCombinationEnumerationLimit);
    } else {
      if (!representative_hidden_random_action(ob) &&
          !action_space_fits(ob.select, kForcedActionLimit))
        return best_endpoint;
      choices = timed_actions(ob, nullptr, false, kPlannerForcedBranchLimit,
                              kPlannerForcedBranchLimit);
      if (choices.empty())
        return best_endpoint;
      if (ob.select.context == kCoinChoiceContext) {
        float sum = 0.f;
        int count = 0;
        for (const auto &choice : choices) {
          if (stop())
            break;
          auto child = step(state.id, choice);
          if (child.error || !child.state)
            continue;
          SearchStateLease child_lease(agent, child.state->id);
          float branch_best = -kSearchInfinity;
          PlanState branch_plan = plan;
          push_own_checkpoint(branch_plan, ob, choice.pick);
          std::unordered_set<uint64_t> branch_visited = visited;
          complete_turn_plan(*child.state, origin_turn, main_actions,
                             branch_visited, branch_plan, branch_best,
                             deep_opponent);
          if (has_value(branch_best)) {
            sum += branch_best;
            ++count;
          }
        }
        if (count)
          consider_endpoint(sum / count, plan, best_endpoint);
        return best_endpoint;
      }
      if (choices.size() > kSubselectExhaustiveLimit)
        choices.resize(std::min<size_t>(4, choices.size()));
      for (const auto &choice : choices) {
        if (stop())
          break;
        auto child = step(state.id, choice);
        if (child.error || !child.state)
          continue;
        SearchStateLease child_lease(agent, child.state->id);
        PlanState branch_plan = plan;
        push_own_checkpoint(branch_plan, ob, choice.pick);
        float branch_best = -kSearchInfinity;
        complete_turn_plan(*child.state, origin_turn, main_actions, visited,
                           branch_plan, branch_best, deep_opponent);
        const auto *path = !branch_plan.best_path.empty() ? &branch_plan.best_path
                                                          : &branch_plan.path;
        consider_endpoint(branch_best, plan, best_endpoint, path);
      }
      return best_endpoint;
    }

    for (const auto &choice : choices) {
      if (stop())
        break;
      auto child = step(state.id, choice);
      if (child.error || !child.state)
        continue;
      SearchStateLease child_lease(agent, child.state->id);
      const int next_main = main ? main_actions + 1 : main_actions;
      const auto &child_obs = child.state->observation;
      push_own_checkpoint(plan, ob, choice.pick);
      if (!our_turn_active(child_obs, origin_turn)) {
        Action forced;
        ApiResult forced_child;
        if (advance_opponent_forced(*child.state, origin_turn, forced,
                                    forced_child)) {
          SearchStateLease lease(agent, forced_child.state->id);
          complete_turn_plan(*forced_child.state, origin_turn, next_main,
                             visited, plan, best_endpoint, deep_opponent);
        } else {
          consider_endpoint(
              eval_after_our_turn(*child.state, origin_turn, deep_opponent),
              plan, best_endpoint, nullptr, true);
        }
        plan.path.pop_back();
        continue;
      }
      complete_turn_plan(*child.state, origin_turn, next_main, visited, plan,
                         best_endpoint, deep_opponent);
      plan.path.pop_back();
      if (stop())
        break;
    }
    return best_endpoint;
  }

  SearchOutput run(const GameState &obs, const World &w, Clock::time_point dl) {
    deadline = dl;
    root_player = obs.current.your_index;
    if (Clock::now() >= deadline)
      return {{}, {}, metrics};
    AgentSession session;
    agent = session.get();
    if (!agent)
      return {{}, {}, metrics};
    if (Clock::now() >= deadline)
      return {{}, {}, metrics};
    auto begin_start = cfg.profile ? Clock::now() : Clock::time_point{};
    const char *begin_text = api.search_begin(
        agent, obs.search_begin_input.c_str(),
        int(obs.search_begin_input.size()), w.yd.data(), w.yp.data(),
        w.od.data(), w.op.data(), w.oh.data(), w.oa.data(), 0);
    auto begin_simulated = Clock::now();
    auto rr = import_sim_response(begin_text);
    auto begin_imported = Clock::now();
    if (cfg.profile) {
      metrics.simulator_ns +=
          std::chrono::duration_cast<std::chrono::nanoseconds>(begin_simulated -
                                                               begin_start)
              .count();
      metrics.import_ns += std::chrono::duration_cast<std::chrono::nanoseconds>(
                               begin_imported - begin_simulated)
                               .count();
    }
    if (rr.error || !rr.state)
      return {{}, {}, metrics};
    std::vector<Action> root_actions;
    if (obs.has_select && obs.select.context != 0)
      root_actions = actions(obs, nullptr, true, kActionLimit,
                             kPlannerForcedBranchLimit);
    else
      root_actions = actions(obs);
    const auto root_index_map = option_index_map(obs, rr.state->observation);
    std::vector<float> values(root_actions.size(),
                              -kSearchInfinity);
    std::vector<std::vector<PlanCheckpoint>> root_plans(root_actions.size());
    SearchStateLease root_lease(agent, rr.state->id);
    const int64_t root_sid = rr.state->id;
    const int origin_turn = obs.current.turn;
    const size_t root_budget =
        std::max<size_t>(1, root_actions.empty() ? 1 : root_actions.size());
    const uint64_t nodes_per_root =
        std::max<uint64_t>(2048, kNodeBudgetPerWorld / root_budget);

    std::vector<std::optional<ApiResult::State>> root_children(root_actions.size());
    SearchStateSetLease root_children_lease(agent);

    for (size_t i = 0; i < root_actions.size(); ++i) {
      auto mapped = remap_action(root_actions[i], root_index_map);
      if (!mapped)
        continue;
      auto child = step(root_sid, *mapped);
      ++nodes;
      if (child.error || !child.state)
        continue;
      root_children[i] = std::move(*child.state);
      root_children_lease.add(root_children[i]->id);
      values[i] = evaluate_endpoint(root_children[i]->observation);
    }

    for (size_t i = 0; i < root_actions.size(); ++i) {
      if (Clock::now() >= deadline)
        break;
      if (!root_children[i])
        continue;
      float greedy_value =
          greedy_complete_turn(*root_children[i], origin_turn, 1);
      if (has_value(greedy_value))
        values[i] = greedy_value;
    }

    std::vector<size_t> order(root_actions.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
      return values[a] > values[b];
    });

    for (size_t rank = 0; rank < order.size() && rank < kPass2RootLimit; ++rank) {
      const size_t i = order[rank];
      if (Clock::now() >= deadline)
        break;
      if (!root_children[i])
        continue;
      local_node_limit = nodes + nodes_per_root;
      std::unordered_set<uint64_t> visited;
      visited.reserve(8192);
      PlanState plan;
      float best_endpoint = -kSearchInfinity;
      complete_turn_plan(*root_children[i], origin_turn, 1, visited, plan,
                         best_endpoint, false);
      if (has_value(best_endpoint))
        values[i] = best_endpoint;
      if (!plan.best_path.empty())
        root_plans[i] = std::move(plan.best_path);

      if (rank + 1 < order.size() && Clock::now() >= deadline)
        break;
      if (nodes >= kNodeBudgetPerWorld)
        break;
    }

    std::vector<float> deep_values(root_actions.size(), -kSearchInfinity);
    std::vector<std::vector<PlanCheckpoint>> deep_plans(root_actions.size());
    const bool main_context = obs.has_select && obs.select.context == 0;
    bool deep_complete = !order.empty() && main_context;

    if (main_context && Clock::now() < deadline) {
      for (size_t rank = 0; rank < order.size() && rank < kSpareBudgetTopRoots;
           ++rank) {
        if (Clock::now() >= deadline) {
          deep_complete = false;
          break;
        }
        const size_t i = order[rank];
        if (!root_children[i]) {
          deep_complete = false;
          continue;
        }
        local_node_limit = nodes + nodes_per_root;
        std::unordered_set<uint64_t> visited;
        visited.reserve(4096);
        PlanState plan;
        float deep_best = -kSearchInfinity;
        complete_turn_plan(*root_children[i], origin_turn, 1, visited, plan,
                           deep_best, true);
        if (has_value(deep_best) && plan.saw_boundary) {
          deep_values[i] = deep_best;
          if (!plan.best_path.empty())
            deep_plans[i] = std::move(plan.best_path);
        } else {
          deep_complete = false;
        }
      }
    } else {
      deep_complete = false;
    }

    if (deep_complete) {
      for (size_t i = 0; i < values.size(); ++i)
        if (has_value(deep_values[i]))
          values[i] = deep_values[i];
      for (size_t i = 0; i < root_plans.size(); ++i)
        if (!deep_plans[i].empty())
          root_plans[i] = std::move(deep_plans[i]);
    }

    size_t finite = 0;
    for (float value : values) {
      if (has_value(value))
        ++finite;
    }
    metrics.completed_depth = finite > 0 ? 2 : 1;
    metrics.completed_width = int(finite);
    metrics.root_coverage =
        root_actions.empty() ? 0.0
                             : double(finite) / double(root_actions.size());
    if (finite < root_actions.size())
      metrics.coverage_fallback = true;
    total_nodes.fetch_add(nodes, std::memory_order_relaxed);
    metrics.nodes = nodes;
    return {std::move(values), std::move(root_plans), metrics};
  }
};

static int estimate_choices_remaining(const GameState &obs) {
  int turn = std::max(0, int(obs.current.turn));
  int turns_left = std::max(1, 72 - turn);
  return std::max(6, std::min(turns_left * 3, 48));
}

static int search_budget_ms(const GameState &obs) {
  double remain = std::max(0.0, obs.remaining_overage_time);
  double usable = std::max(0.0, remain - cfg.safety);
  int choices_left = estimate_choices_remaining(obs);
  double ms = 1000.0 * usable / double(choices_left);
  const int cap = std::min(cfg.max_ms, cfg.hard_ms);
  return int(std::clamp(ms, 80.0, double(cap)));
}

static int choose_impl(const GameState &obs, const std::vector<int> &own,
                       int *out, int cap) {
  auto choose_start = Clock::now();
  if (plan_cache.turn >= 0 && obs.current.turn != plan_cache.turn)
    plan_cache = {};
  if (obs.has_select && plan_cache.turn == obs.current.turn &&
      plan_cache.index < plan_cache.steps.size()) {
    if (auto remapped =
            remap_pick_to_obs(plan_cache.steps[plan_cache.index], obs)) {
      if (int(remapped->size()) > cap)
        return -4;
      std::copy(remapped->begin(), remapped->end(), out);
      ++plan_cache.index;
      std::lock_guard lk(diag_mu);
      diag = "{\"plan_cache_hit\":true,\"plan_cache_step\":" +
             std::to_string(plan_cache.index) + ",\"plan_cache_total\":" +
             std::to_string(plan_cache.steps.size()) + "}";
      return int(remapped->size());
    }
    plan_cache = {};
  }
  auto root_action_start = Clock::now();
  std::vector<Action> as;
  if (obs.has_select && obs.select.context != 0)
    as = actions(obs, nullptr, true, kActionLimit, kPlannerForcedBranchLimit);
  else
    as = actions(obs);
  auto root_action_end = Clock::now();
  if (as.empty()) {
    if (obs.has_select && !obs.select.options.empty()) {
      if (obs.select.min_count <= 1 && cap >= 1) {
        out[0] = 0;
        return 1;
      }
      return -4;
    }
    return 0;
  }
  const int ms = search_budget_ms(obs);
  const int budget_ms =
      std::max(80, std::min(ms, cfg.hard_ms) - kChooseOverheadMs);
  const auto deadline =
      choose_start + std::chrono::milliseconds(std::max(1, budget_ms));
  auto belief_start = Clock::now();
  std::vector<World> ws;
  if (Clock::now() < deadline)
    ws = worlds(obs, own, deadline);
  auto belief_end = Clock::now();
  if (ws.empty()) {
    auto &a = as.front();
    if (int(a.pick.size()) > cap)
      return -4;
    std::copy(a.pick.begin(), a.pick.end(), out);
    double remain = obs.remaining_overage_time;
    auto wall_ms = [](Clock::time_point begin, Clock::time_point end) {
      return std::chrono::duration<double, std::milli>(end - begin).count();
    };
    auto choose_end = Clock::now();
    std::ostringstream d;
    d << "{\"nodes\":" << total_nodes.load() << ",\"worlds\":0"
      << ",\"call_nodes\":0,\"depth\":0,\"budget_ms\":" << budget_ms
      << ",\"hard_ms\":" << cfg.hard_ms
      << ",\"remain_s\":" << remain
      << ",\"choices_left\":" << estimate_choices_remaining(obs)
      << ",\"actions\":" << as.size() << ",\"threads\":0"
      << ",\"rounds\":0,\"ms_per_world\":0"
      << ",\"profile\":" << (cfg.profile ? "true" : "false")
      << ",\"wall_ms\":" << wall_ms(choose_start, choose_end)
      << ",\"root_action_ms\":" << wall_ms(root_action_start, root_action_end)
      << ",\"belief_ms\":" << wall_ms(belief_start, belief_end)
      << ",\"search_wall_ms\":0,\"aggregate_ms\":0"
      << ",\"simulator_cpu_ms\":0,\"import_cpu_ms\":0"
      << ",\"action_cpu_ms\":0,\"evaluation_cpu_ms\":0"
      << ",\"json_cpu_ms\":0,\"belief_failed\":true"
      << ",\"belief_degraded\":" << (last_belief_degraded ? "true" : "false")
      << ",\"native_backend\":\"" << native_backend_name << "\"}";
    std::lock_guard lk(diag_mu);
    diag = d.str();
    return int(a.pick.size());
  }
  double remain = obs.remaining_overage_time;
  std::vector<SearchOutput> outputs(ws.size());
  std::atomic<size_t> next_world{0};
  unsigned detected = std::max(1u, std::thread::hardware_concurrency());
  unsigned thread_limit =
      cfg.threads > 0 ? unsigned(cfg.threads) : detected;
  size_t worker_count = std::min<size_t>(ws.size(), thread_limit);
  worker_count = std::max<size_t>(1, worker_count);
  int rounds = int((ws.size() + worker_count - 1) / worker_count);
  const auto remaining_ms = [&]() {
    return std::max<int64_t>(
        0, std::chrono::duration_cast<std::chrono::milliseconds>(deadline -
                                                                 Clock::now())
               .count());
  };
  int ms_per_world =
      std::max(1, int(remaining_ms()) / std::max(1, int(ws.size())));
  std::vector<std::thread> workers;
  workers.reserve(worker_count);
  auto search_start = Clock::now();
  for (size_t worker = 0; worker < worker_count; ++worker)
    workers.emplace_back([&] {
      for (;;) {
        size_t i = next_world.fetch_add(1);
        if (i >= ws.size())
          return;
        if (Clock::now() >= deadline) {
          outputs[i] = {};
          continue;
        }
        Searcher searcher;
        const int64_t left = remaining_ms();
        const int slice =
            std::max(1, int(left) / std::max(1, rounds));
        auto world_deadline =
            std::min(deadline, Clock::now() + std::chrono::milliseconds(slice));
        outputs[i] = searcher.run(obs, ws[i], world_deadline);
      }
    });
  for (auto &worker : workers)
    worker.join();
  auto search_end = Clock::now();
  auto aggregate_start = Clock::now();
  std::vector<double> agg(as.size(), -std::numeric_limits<double>::infinity());
  // Compare every action on exactly the same set of determinizations.  Per-action
  // renormalization lets a move silently discard only the worlds where it failed
  // to finish, which is an optimistic and action-dependent sampling bias.
  std::vector<size_t> common_worlds;
  for (size_t i = 0; i < ws.size(); ++i) {
    if (outputs[i].values.size() != as.size())
      continue;
    if (std::all_of(outputs[i].values.begin(), outputs[i].values.end(),
                    [](float value) { return has_value(value); }))
      common_worlds.push_back(i);
  }
  for (size_t a = 0; a < as.size(); a++) {
    std::vector<std::pair<float, double>> q;
    double mean = 0, valid_weight = 0;
    for (size_t i : common_worlds) {
      float v = outputs[i].values[a];
      mean += ws[i].weight * v;
      valid_weight += ws[i].weight;
      q.push_back({v, ws[i].weight});
    }
    if (q.empty()) {
      continue;
    }
    mean /= valid_weight;
    for (auto &[_, weight] : q)
      weight /= valid_weight;
    std::sort(q.begin(), q.end());
    double mass = 0, low = q.front().first;
    for (auto [v, w] : q) {
      mass += w;
      if (mass >= .2) {
        low = v;
        break;
      }
    }
    agg[a] = (1 - cfg.risk) * mean + cfg.risk * low;
  }
  size_t bi = 0;
  if (std::any_of(agg.begin(), agg.end(),
                  [](double value) { return std::isfinite(value); })) {
    bi = std::max_element(agg.begin(), agg.end()) - agg.begin();
  } else {
    bi = std::max_element(as.begin(), as.end(), [](const Action &lhs,
                                                   const Action &rhs) {
           return lhs.order < rhs.order;
         }) - as.begin();
  }
  auto aggregate_end = Clock::now();
  auto &a = as[bi];
  if (int(a.pick.size()) > cap)
    return -4;
  std::copy(a.pick.begin(), a.pick.end(), out);
  if (obs.has_select && obs.select.context == 0) {
    plan_cache.turn = obs.current.turn;
    plan_cache.index = 0;
    plan_cache.steps.clear();
    for (size_t i : common_worlds) {
      if (bi < outputs[i].root_plans.size() &&
          !outputs[i].root_plans[bi].empty()) {
        plan_cache.steps = outputs[i].root_plans[bi];
        break;
      }
    }
  }
  std::lock_guard lk(diag_mu);
  SearchMetrics measured;
  measured.completed_depth = std::numeric_limits<int>::max();
  measured.completed_width = std::numeric_limits<int>::max();
  measured.root_coverage = 1.0;
  for (const auto &output : outputs) {
    measured.simulator_ns += output.metrics.simulator_ns;
    measured.import_ns += output.metrics.import_ns;
    measured.action_ns += output.metrics.action_ns;
    measured.evaluation_ns += output.metrics.evaluation_ns;
    measured.nodes += output.metrics.nodes;
    measured.completed_endpoints += output.metrics.completed_endpoints;
    measured.intermediate_evaluations +=
        output.metrics.intermediate_evaluations;
    measured.root_coverage =
        std::min(measured.root_coverage, output.metrics.root_coverage);
    measured.coverage_fallback =
        measured.coverage_fallback || output.metrics.coverage_fallback;
    if (!output.values.empty()) {
      measured.completed_depth =
          std::min(measured.completed_depth, output.metrics.completed_depth);
      measured.completed_width =
          std::min(measured.completed_width, output.metrics.completed_width);
    }
  }
  if (measured.completed_depth == std::numeric_limits<int>::max())
    measured.completed_depth = 0;
  if (measured.completed_width == std::numeric_limits<int>::max())
    measured.completed_width = 0;
  auto millis = [](uint64_t nanos) { return double(nanos) / 1e6; };
  auto wall_ms = [](Clock::time_point begin, Clock::time_point end) {
    return std::chrono::duration<double, std::milli>(end - begin).count();
  };
  const double total_wall = wall_ms(choose_start, aggregate_end);
  const double sim_cpu = millis(measured.simulator_ns);
  const double import_cpu = millis(measured.import_ns);
  const double action_cpu = millis(measured.action_ns);
  const double eval_cpu = millis(measured.evaluation_ns);
  const double profile_cpu = sim_cpu + import_cpu + action_cpu + eval_cpu;
  std::ostringstream d;
  d << "{\"nodes\":" << total_nodes.load() << ",\"worlds\":" << ws.size()
    << ",\"call_nodes\":" << measured.nodes
    << ",\"depth\":" << measured.completed_depth
    << ",\"completed_turn_depth\":" << measured.completed_depth
    << ",\"completed_width\":" << measured.completed_width
    << ",\"root_coverage\":" << measured.root_coverage
    << ",\"completed_endpoints\":" << measured.completed_endpoints
    << ",\"intermediate_evaluations\":"
    << measured.intermediate_evaluations
    << ",\"common_worlds\":" << common_worlds.size()
    << ",\"coverage_fallback\":"
    << (measured.coverage_fallback ? "true" : "false")
    << ",\"budget_ms\":" << budget_ms
    << ",\"hard_ms\":" << cfg.hard_ms
    << ",\"remain_s\":" << remain
    << ",\"choices_left\":" << estimate_choices_remaining(obs)
    << ",\"actions\":" << as.size() << ",\"threads\":" << worker_count
    << ",\"rounds\":" << rounds << ",\"ms_per_world\":" << ms_per_world
    << ",\"profile\":" << (cfg.profile ? "true" : "false")
    << ",\"wall_ms\":" << total_wall
    << ",\"root_action_ms\":" << wall_ms(root_action_start, root_action_end)
    << ",\"belief_ms\":" << wall_ms(belief_start, belief_end)
    << ",\"search_wall_ms\":" << wall_ms(search_start, search_end)
    << ",\"aggregate_ms\":" << wall_ms(aggregate_start, aggregate_end)
    << ",\"simulator_cpu_ms\":" << sim_cpu
    << ",\"import_cpu_ms\":" << import_cpu
    << ",\"action_cpu_ms\":" << action_cpu
    << ",\"evaluation_cpu_ms\":" << eval_cpu
    << ",\"json_cpu_ms\":" << import_cpu
    << ",\"plan_cache_steps\":" << plan_cache.steps.size()
    << ",\"belief_degraded\":" << (last_belief_degraded ? "true" : "false")
    << ",\"native_backend\":\"" << native_backend_name << "\"";
  if (cfg.profile && profile_cpu > 0.) {
    d << ",\"simulator_pct\":" << (100. * sim_cpu / profile_cpu)
      << ",\"import_pct\":" << (100. * import_cpu / profile_cpu)
      << ",\"action_pct\":" << (100. * action_cpu / profile_cpu)
      << ",\"evaluation_pct\":" << (100. * eval_cpu / profile_cpu);
  }
  if (cfg.probe_root) {
    std::vector<size_t> order(as.size());
    std::iota(order.begin(), order.end(), 0);
    std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) {
      return agg[a] > agg[b];
    });
    d << ",\"root\":[";
    int limit = std::min<int>(12, int(as.size()));
    for (int r = 0; r < limit; ++r) {
      size_t i = order[r];
      if (r)
        d << ',';
      d << "{\"agg\":";
      if (std::isfinite(agg[i]))
        d << agg[i];
      else
        d << "null";
      d << ",\"order\":" << as[i].order << ",\"pick\":[";
      for (size_t k = 0; k < as[i].pick.size(); ++k) {
        if (k)
          d << ',';
        d << as[i].pick[k];
      }
      d << "]}";
    }
    d << "]";
  }
  d << "}";
  diag = d.str();
  return int(a.pick.size());
}
} // namespace

#if defined(__AVX2__)
static bool cpu_has_avx2() {
#ifdef _WIN32
  int cpu_info[4] = {};
  __cpuid(cpu_info, 0);
  const int ids = cpu_info[0];
  if (ids < 7)
    return false;
  __cpuidex(cpu_info, 7, 0);
  return (cpu_info[1] & (1 << 5)) != 0;
#elif defined(__GNUC__)
  return __builtin_cpu_supports("avx2");
#else
  return true;
#endif
}
#endif

extern "C" PVS_EXPORT int pvs_init(const char *cg, const char *cat,
                                   const char *weights, const char *config) {
  try {
#if defined(__AVX2__)
    if (!cpu_has_avx2())
      return -6;
#endif
    if (!feature_schema_compatible())
      return -5;
    if (!api.load(cg))
      return -1;
    if (!read_card_metadata())
      return -4;
    if (!read_catalog(cat))
      return -2;
    if (weights && *weights) {
      std::ifstream probe(weights, std::ios::binary);
      if (probe && !load_model(weights))
        return -3;
    }
    if (config) {
      std::string_view cfg_text(config);
      cfg.hypotheses =
          std::clamp(config_int(cfg_text, "hypotheses", cfg.hypotheses), 1, 32);
      cfg.threads = std::max(0, config_int(cfg_text, "threads", cfg.threads));
      cfg.max_depth =
          std::clamp(config_int(cfg_text, "max_depth", cfg.max_depth), 1, 20);
      cfg.max_ms = std::max(50, config_int(cfg_text, "max_ms", cfg.max_ms));
      cfg.hard_ms = std::max(50, config_int(cfg_text, "hard_ms", cfg.hard_ms));
      cfg.max_ms = std::min(cfg.max_ms, cfg.hard_ms);
      cfg.safety = std::clamp(
          config_double(cfg_text, "safety_seconds", cfg.safety), 0.0, 60.0);
      cfg.risk =
          std::clamp(config_double(cfg_text, "risk", cfg.risk), 0.0, 1.0);
      cfg.model_scale = std::clamp(
          config_double(cfg_text, "model_scale", cfg.model_scale), 0.0, 100.0);
      cfg.profile = config_bool(cfg_text, "profile", cfg.profile);
      cfg.probe_root = config_bool(cfg_text, "probe_root", cfg.probe_root);
    }
    return 0;
  } catch (...) {
    return -9;
  }
}

extern "C" PVS_EXPORT int pvs_choose(const uint8_t *observation, int obs_size,
                                     const int *deck, int n, int *out,
                                     int cap) {
  try {
    if (!observation || obs_size <= 0 || (n > 0 && !deck))
      return -3;
    GameState state;
    if (!pvs::wire::decode(
            std::string_view(reinterpret_cast<const char *>(observation),
                             size_t(obs_size)),
            state))
      return -3;
    return choose_impl(state, std::vector<int>(deck, deck + n), out, cap);
  } catch (...) {
    return -9;
  }
}

extern "C" PVS_EXPORT void pvs_reset() {
  total_nodes = 0;
  plan_cache = {};
  std::lock_guard lk(diag_mu);
  diag = "{}";
}

extern "C" PVS_EXPORT const char *pvs_diagnostics() {
  std::lock_guard lk(diag_mu);
  return diag.c_str();
}
