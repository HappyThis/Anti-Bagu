export type Channel = 'interviewer' | 'candidate'

export interface RealtimeEvent {
  type: string
  event_id: string
  session_id: string
  conversation_revision: number
  created_at: number
  payload: Record<string, unknown>
}

export interface TranscriptLine {
  id: string
  text: string
  createdAt: number
}

export interface LatencySnapshot {
  systemAudio: number | null
  microphone: number | null
  asr: number | null
  model: number | null
  endToEnd: number | null
}
