import Foundation

final class AEC3AudioSynchronizer: @unchecked Sendable {
    typealias OutputHandler = @Sendable (AudioFramePacket) -> Void

    private static let chunksPerPacket = 10
    private static let bufferSlots: Int64 = 12
    private static let silence = Data(repeating: 0, count: AEC3NativeProcessor.bytesPerFrame)

    private let processor: EchoCancelling
    private let outputHandler: OutputHandler
    private let lock = NSLock()
    private var renderFrames: [Int64: Data] = [:]
    private var captureFrames: [Int64: Data] = [:]
    private var latestRenderSlot: Int64?
    private var latestCaptureSlot: Int64?
    private var nextSlot: Int64?
    private var pendingOutput = Data()

    init(processor: EchoCancelling, outputHandler: @escaping OutputHandler) {
        self.processor = processor
        self.outputHandler = outputHandler
    }

    func submitRender(_ packet: AudioFramePacket) {
        submit(packet, channel: .render)
    }

    func submitCapture(_ packet: AudioFramePacket) {
        submit(packet, channel: .capture)
    }

    func flush() {
        let packets = lock.withLock { drain(flushAll: true) }
        packets.forEach(outputHandler)
    }

    private func submit(_ packet: AudioFramePacket, channel: InputChannel) {
        let chunks = split(packet)
        guard !chunks.isEmpty else { return }
        let packets = lock.withLock { () -> [AudioFramePacket] in
            for chunk in chunks {
                switch channel {
                case .render:
                    renderFrames[chunk.slot] = chunk.pcm
                    latestRenderSlot = max(latestRenderSlot ?? chunk.slot, chunk.slot)
                case .capture:
                    captureFrames[chunk.slot] = chunk.pcm
                    latestCaptureSlot = max(latestCaptureSlot ?? chunk.slot, chunk.slot)
                }
            }
            return drain(flushAll: false)
        }
        packets.forEach(outputHandler)
    }

    private func split(_ packet: AudioFramePacket) -> [TimedChunk] {
        let bytes = AEC3NativeProcessor.bytesPerFrame
        let count = packet.pcm.count / bytes
        guard count > 0, packet.pcm.count % bytes == 0 else { return [] }
        let finalSlot = Int64((packet.capturedAt * 100).rounded())
        return (0 ..< count).map { index in
            let start = index * bytes
            return TimedChunk(
                slot: finalSlot - Int64(count - index - 1),
                pcm: packet.pcm.subdata(in: start ..< start + bytes)
            )
        }
    }

    private func drain(flushAll: Bool) -> [AudioFramePacket] {
        guard let latestRenderSlot, let latestCaptureSlot else { return [] }
        if nextSlot == nil {
            guard let firstRender = renderFrames.keys.min(),
                  let firstCapture = captureFrames.keys.min()
            else { return [] }
            nextSlot = min(firstRender, firstCapture)
        }
        let limit = flushAll
            ? latestCaptureSlot
            : min(latestRenderSlot, latestCaptureSlot) - Self.bufferSlots
        var packets: [AudioFramePacket] = []
        while let slot = nextSlot, slot <= limit {
            let render = renderFrames.removeValue(forKey: slot) ?? Self.silence
            let capture = captureFrames.removeValue(forKey: slot) ?? Self.silence
            do {
                pendingOutput.append(try processor.process(render: render, capture: capture))
            } catch {
                fputs("AEC3 processing failed: \(error)\n", stderr)
                pendingOutput.append(Self.silence)
            }
            nextSlot = slot + 1
            if pendingOutput.count == AudioMetadata().expectedFrameBytes {
                packets.append(
                    AudioFramePacket(
                        capturedAt: Double(slot) / 100,
                        pcm: pendingOutput
                    )
                )
                pendingOutput.removeAll(keepingCapacity: true)
            }
        }
        if flushAll, !pendingOutput.isEmpty, let finalSlot = nextSlot.map({ $0 - 1 }) {
            pendingOutput.append(
                Data(
                    repeating: 0,
                    count: AudioMetadata().expectedFrameBytes - pendingOutput.count
                )
            )
            packets.append(
                AudioFramePacket(capturedAt: Double(finalSlot) / 100, pcm: pendingOutput)
            )
            pendingOutput.removeAll(keepingCapacity: true)
        }
        return packets
    }
}

private enum InputChannel {
    case render
    case capture
}

private struct TimedChunk {
    let slot: Int64
    let pcm: Data
}
