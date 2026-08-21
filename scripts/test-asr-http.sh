#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${DASHSCOPE_ENV_FILE:-${repo_root}/.env.local}"

if [[ -f "$env_file" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
fi

if [[ -z "${DASHSCOPE_API_KEY:-}" ]]; then
  printf 'DASHSCOPE_API_KEY is not set. Add a newly created key to %s first.\n' "$env_file" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  printf 'jq is required but was not found.\n' >&2
  exit 1
fi

audio_url="${1:-https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav}"
api_base_url="${DASHSCOPE_API_BASE_URL:-https://dashscope.aliyuncs.com}"
endpoint="${api_base_url%/}/api/v1/services/aigc/multimodal-generation/generation"

payload="$({
  jq -n \
    --arg audio_url "$audio_url" \
    '{
      model: "qwen-audio-3.0-asr-flash",
      input: {
        messages: [
          {
            role: "user",
            content: [
              {
                type: "input_audio",
                input_audio: {data: $audio_url}
              }
            ]
          }
        ]
      },
      parameters: {
        format: "wav",
        sample_rate: "16000",
        vocabulary: {
          Redis: 5,
          MySQL: 5,
          JVM: 5
        }
      }
    }'
})"

response_file="$(mktemp)"
trap 'rm -f "$response_file"' EXIT

metrics="$({
  curl --silent --show-error --location \
    --request POST "$endpoint" \
    --header "Authorization: Bearer ${DASHSCOPE_API_KEY}" \
    --header 'Content-Type: application/json' \
    --header 'X-DashScope-SSE: disable' \
    --data "$payload" \
    --output "$response_file" \
    --write-out $'http_code=%{http_code}\nconnect_seconds=%{time_connect}\nfirst_byte_seconds=%{time_starttransfer}\ntotal_seconds=%{time_total}\n'
})"

printf '%s\n' "$metrics"

http_code="$(printf '%s\n' "$metrics" | awk -F= '/^http_code=/{print $2}')"
if [[ "$http_code" != "200" ]]; then
  printf 'Request failed:\n' >&2
  jq . "$response_file" >&2 || sed -n '1,120p' "$response_file" >&2
  exit 1
fi

transcript="$(
  jq -r '
    [
      .output.choices[0].message.content[]?.text,
      .output.text,
      .output.transcription
    ]
    | map(select(type == "string" and length > 0))
    | first // empty
  ' "$response_file"
)"

if [[ -n "$transcript" ]]; then
  printf 'transcript=%s\n' "$transcript"
else
  printf 'No transcript field was recognized; full response follows:\n'
  jq . "$response_file"
fi
