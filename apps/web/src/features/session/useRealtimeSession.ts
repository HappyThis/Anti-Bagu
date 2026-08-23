import { useEffect, useReducer } from 'react'

import { applyAnswerEvent, type AnswerCard } from '../answer/answerCards'
import type {
  Channel,
  LatencySnapshot,
  RealtimeEvent,
  TranscriptLine,
} from '../../shared/protocol'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

export interface RealtimeState {
  connection: ConnectionStatus
  interviewer: TranscriptLine[]
  candidate: TranscriptLine[]
  partial: Record<Channel, string>
  audioConnected: Record<Channel, boolean>
  focus: string
  answer: string
  answerMode: string
  answerCards: AnswerCard[]
  generating: boolean
  error: string
  latency: LatencySnapshot
}

type Action =
  | { type: 'connection'; value: ConnectionStatus }
  | { type: 'event'; value: RealtimeEvent }
  | { type: 'clear' }

const EMPTY_LATENCY: LatencySnapshot = {
  systemAudio: null,
  microphone: null,
  asr: null,
  model: null,
  endToEnd: null,
}

export interface AudioLevelSample {
  channel: Channel
  rms: number
  peak: number
}

type AudioLevelListener = (sample: AudioLevelSample) => void
const audioLevelListeners = new Set<AudioLevelListener>()

export function subscribeAudioLevels(listener: AudioLevelListener): () => void {
  audioLevelListeners.add(listener)
  return () => audioLevelListeners.delete(listener)
}

function publishAudioLevel(event: RealtimeEvent): void {
  const sample: AudioLevelSample = {
    channel: event.payload.channel as Channel,
    rms: Number(event.payload.rms ?? 0),
    peak: Number(event.payload.peak ?? 0),
  }
  audioLevelListeners.forEach((listener) => listener(sample))
}

function demoState(): RealtimeState {
  return {
    connection: 'connecting',
    interviewer: [
      { id: 'i-1', text: '你在项目中使用过哪些缓存中间件？', createdAt: 1 },
      { id: 'i-2', text: 'Redis 为什么这么快？', createdAt: 2 },
    ],
    candidate: [
      { id: 'c-1', text: '主要使用过 Redis。', createdAt: 1 },
      { id: 'c-2', text: '我认为首先是因为它基于内存。', createdAt: 2 },
    ],
    partial: { interviewer: '', candidate: '' },
    audioConnected: { interviewer: true, candidate: true },
    focus: 'Redis 为什么这么快？',
    answer:
      'Redis 快主要有四点：第一，数据主要在内存中访问；第二，命令执行路径避免了大量锁竞争；第三，使用 I/O 多路复用处理并发连接；第四，底层数据结构针对不同场景做了优化。',
    answerMode: 'FAST',
    answerCards: [
      {
        id: 'demo-1',
        question: '你在项目中使用过哪些缓存中间件？',
        answer: '主要使用过 Redis，并在不同场景采用旁路缓存和分布式锁。',
        code: '',
        language: '',
        complexity: '',
        contentKind: 'KNOWLEDGE',
        source: 'VOICE',
        mode: 'FAST',
        generating: false,
        cancelled: false,
        error: '',
        createdAt: 1,
      },
      {
        id: 'demo-2',
        question: 'Redis 为什么这么快？',
        answer: 'Redis 快主要有四点：第一，数据主要在内存中访问；第二，命令执行路径避免了大量锁竞争；第三，使用 I/O 多路复用处理并发连接；第四，底层数据结构针对不同场景做了优化。',
        code: '',
        language: '',
        complexity: '',
        contentKind: 'KNOWLEDGE',
        source: 'VOICE',
        mode: 'FAST',
        generating: false,
        cancelled: false,
        error: '',
        createdAt: 2,
      },
    ],
    generating: false,
    error: '',
    latency: {
      systemAudio: 18,
      microphone: 22,
      asr: 112,
      model: 482,
      endToEnd: 634,
    },
  }
}

function emptyState(): RealtimeState {
  return {
    connection: 'connecting',
    interviewer: [],
    candidate: [],
    partial: { interviewer: '', candidate: '' },
    audioConnected: { interviewer: false, candidate: false },
    focus: '',
    answer: '',
    answerMode: '',
    answerCards: [],
    generating: false,
    error: '',
    latency: EMPTY_LATENCY,
  }
}

function initialState(): RealtimeState {
  return new URLSearchParams(window.location.search).has('demo')
    ? demoState()
    : emptyState()
}

function appendTranscript(
  lines: TranscriptLine[],
  event: RealtimeEvent,
  text: string,
): TranscriptLine[] {
  return [
    ...lines.slice(-7),
    { id: event.event_id, text, createdAt: event.created_at },
  ]
}

function applyEvent(state: RealtimeState, event: RealtimeEvent): RealtimeState {
  const payload = event.payload
  const answerCards = applyAnswerEvent(state.answerCards, event)
  if (event.type === 'transcript.partial' || event.type === 'transcript.final') {
    const channel = payload.channel as Channel
    const text = String(payload.text ?? '')
    if (event.type === 'transcript.partial') {
      return { ...state, partial: { ...state.partial, [channel]: text } }
    }
    return {
      ...state,
      [channel]: appendTranscript(state[channel], event, text),
      partial: { ...state.partial, [channel]: '' },
    }
  }

  if (event.type === 'focus.updated') {
    return {
      ...state,
      focus: String(payload.question ?? ''),
      answerMode: String(payload.mode ?? ''),
      answer: '',
      answerCards,
      error: '',
    }
  }
  if (event.type === 'audio.connected' || event.type === 'audio.disconnected') {
    const channel = payload.channel as Channel
    return {
      ...state,
      audioConnected: {
        ...state.audioConnected,
        [channel]: event.type === 'audio.connected',
      },
    }
  }
  if (event.type === 'answer.started') {
    return { ...state, answerCards, generating: true, answer: '', error: '' }
  }
  if (event.type === 'answer.delta') {
    return { ...state, answerCards, generating: true, answer: state.answer + String(payload.delta ?? '') }
  }
  if (event.type === 'answer.completed') {
    return {
      ...state,
      generating: false,
      answerCards,
      answer: String(payload.answer ?? ''),
      answerMode: String(payload.mode ?? state.answerMode),
    }
  }
  if (event.type === 'answer.cancelled') {
    return { ...state, answerCards, generating: false }
  }
  if (event.type === 'latency.updated') {
    return { ...state, latency: { ...state.latency, ...payload } }
  }
  if (event.type === 'error') {
    return { ...state, answerCards, generating: false, error: String(payload.message ?? '未知错误') }
  }
  return state
}

function reducer(state: RealtimeState, action: Action): RealtimeState {
  if (action.type === 'connection') {
    return { ...state, connection: action.value }
  }
  if (action.type === 'clear') {
    return {
      ...emptyState(),
      connection: state.connection,
      audioConnected: state.audioConnected,
      latency: state.latency,
    }
  }
  return applyEvent(state, action.value)
}

export function useRealtimeSession(url: string) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState)

  useEffect(() => {
    let disposed = false
    let reconnectTimer: number | undefined
    let socket: WebSocket | undefined

    const connect = () => {
      if (disposed || !url) return
      dispatch({ type: 'connection', value: 'connecting' })
      socket = new WebSocket(url)
      socket.addEventListener('open', () => {
        if (!disposed) dispatch({ type: 'connection', value: 'connected' })
      })
      socket.addEventListener('message', (message) => {
        if (disposed) return
        try {
          const event = JSON.parse(message.data) as RealtimeEvent
          if (event.type === 'audio.level') {
            publishAudioLevel(event)
          } else {
            dispatch({ type: 'event', value: event })
          }
        } catch {
          // Ignore malformed local events; the backend logs protocol violations.
        }
      })
      socket.addEventListener('close', () => {
        if (disposed) return
        dispatch({ type: 'connection', value: 'disconnected' })
        reconnectTimer = window.setTimeout(connect, 1500)
      })
    }

    connect()
    return () => {
      disposed = true
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [url])

  return {
    state,
    clear: () => dispatch({ type: 'clear' }),
  }
}
