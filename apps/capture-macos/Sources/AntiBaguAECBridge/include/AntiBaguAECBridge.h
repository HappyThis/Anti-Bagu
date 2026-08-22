#ifndef ANTI_BAGU_AEC_BRIDGE_H
#define ANTI_BAGU_AEC_BRIDGE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void* anti_bagu_aec3_create(int32_t sample_rate);
int32_t anti_bagu_aec3_process(void* context,
                               const int16_t* render,
                               const int16_t* capture,
                               int16_t* output,
                               size_t samples);
void anti_bagu_aec3_destroy(void* context);

#ifdef __cplusplus
}
#endif

#endif
