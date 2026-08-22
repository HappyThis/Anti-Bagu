import { useEffect, useRef } from 'react'

import {
  subscribeAudioLevels,
  type AudioLevelSample,
} from '../session/useRealtimeSession'
import type { Channel } from '../../shared/protocol'

interface AudioWaveformProps {
  channel: Channel
  connected: boolean
}

const SAMPLE_COUNT = 54

export function AudioWaveform({ channel, connected }: AudioWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const samplesRef = useRef<number[]>(Array.from({ length: SAMPLE_COUNT }, () => 0))
  const connectedRef = useRef(connected)

  useEffect(() => {
    connectedRef.current = connected
  }, [connected])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return

    const draw = () => {
      const ratio = window.devicePixelRatio || 1
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (canvas.width !== width * ratio || canvas.height !== height * ratio) {
        canvas.width = width * ratio
        canvas.height = height * ratio
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, width, height)
      context.strokeStyle = channel === 'interviewer' ? '#2878e8' : '#58b51c'
      context.lineWidth = 1.5
      context.beginPath()
      const middle = height / 2
      samplesRef.current.forEach((sample, index) => {
        const x = (index / (SAMPLE_COUNT - 1)) * width
        const amplitude = Math.max(1, sample * (height * 0.46))
        context.moveTo(x, middle - amplitude)
        context.lineTo(x, middle + amplitude)
      })
      context.globalAlpha = connectedRef.current ? 1 : 0.28
      context.stroke()
      context.globalAlpha = 1
    }

    const unsubscribe = subscribeAudioLevels((sample: AudioLevelSample) => {
      if (sample.channel !== channel) return
      const visibleLevel = Math.min(1, Math.max(sample.rms * 7, sample.peak * 0.9))
      const samples = samplesRef.current
      samples.push(visibleLevel)
      samples.shift()
      draw()
    })
    const resizeObserver = new ResizeObserver(draw)
    resizeObserver.observe(canvas)
    draw()

    return () => {
      unsubscribe()
      resizeObserver.disconnect()
    }
  }, [channel])

  return (
    <canvas
      ref={canvasRef}
      className="audio-waveform"
      aria-label={`${channel === 'interviewer' ? '系统音频' : '麦克风'}实时声波`}
    />
  )
}
