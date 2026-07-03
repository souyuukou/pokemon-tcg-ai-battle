#pragma once
#include <stdint.h>
#if defined(_WIN32)
# define PVS_EXPORT __declspec(dllexport)
#else
# define PVS_EXPORT __attribute__((visibility("default")))
#endif
extern "C" {
PVS_EXPORT int pvs_init(const char* cg_path, const char* catalog_path, const char* model_path, const char* config_json);
PVS_EXPORT int pvs_choose(const uint8_t* observation, int obs_size, const int* own_deck, int own_deck_count, int* output, int output_capacity);
PVS_EXPORT void pvs_reset();
PVS_EXPORT const char* pvs_diagnostics();
}
