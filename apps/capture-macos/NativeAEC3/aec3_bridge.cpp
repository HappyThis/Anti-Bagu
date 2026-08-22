#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <vector>

#include "api/scoped_refptr.h"
#include "modules/audio_processing/include/audio_processing.h"

namespace {

struct AEC3Handle {
  rtc::scoped_refptr<webrtc::AudioProcessing> processor;
  webrtc::StreamConfig stream_config;
  std::vector<int16_t> render_output;

  explicit AEC3Handle(int sample_rate)
      : processor(webrtc::AudioProcessingBuilder().Create()),
        stream_config(sample_rate, 1),
        render_output(static_cast<size_t>(sample_rate / 100)) {
    webrtc::AudioProcessing::Config config;
    config.echo_canceller.enabled = true;
    config.echo_canceller.mobile_mode = false;
    processor->ApplyConfig(config);
  }
};

}  // namespace

extern "C" {

void* anti_bagu_aec3_create(int32_t sample_rate) {
  if (sample_rate <= 0 || sample_rate % 100 != 0) {
    return nullptr;
  }
  try {
    return new AEC3Handle(sample_rate);
  } catch (...) {
    return nullptr;
  }
}

int32_t anti_bagu_aec3_process(void* opaque,
                               const int16_t* render,
                               const int16_t* capture,
                               int16_t* output,
                               size_t samples) {
  auto* handle = static_cast<AEC3Handle*>(opaque);
  if (handle == nullptr || render == nullptr || capture == nullptr ||
      output == nullptr || samples != handle->render_output.size()) {
    return -1;
  }

  const int render_result = handle->processor->ProcessReverseStream(
      render, handle->stream_config, handle->stream_config,
      handle->render_output.data());
  if (render_result != webrtc::AudioProcessing::kNoError) {
    return render_result;
  }

  return handle->processor->ProcessStream(capture, handle->stream_config,
                                           handle->stream_config, output);
}

void anti_bagu_aec3_destroy(void* opaque) {
  delete static_cast<AEC3Handle*>(opaque);
}

}  // extern "C"
