import Foundation
import Testing
@testable import AntiBaguCapture

@Test
func nativeAEC3SuppressesSyntheticEcho() throws {
    let processor = try AEC3NativeProcessor()
    var generator: UInt32 = 0xA17E_C123
    var renderHistory: [[Int16]] = []
    var inputEnergy = 0.0
    var outputEnergy = 0.0

    for frameIndex in 0 ..< 500 {
        let render = (0 ..< AEC3NativeProcessor.samplesPerFrame).map { _ -> Int16 in
            generator = generator &* 1_664_525 &+ 1_013_904_223
            return Int16(truncatingIfNeeded: Int32(generator >> 16) / 8)
        }
        renderHistory.append(render)
        let source = frameIndex >= 6
            ? renderHistory[frameIndex - 6]
            : [Int16](repeating: 0, count: AEC3NativeProcessor.samplesPerFrame)
        let capture = source.map { Int16(Double($0) * 0.55) }
        let output = try processor.process(
            render: pcmData(render),
            capture: pcmData(capture)
        )
        if frameIndex >= 300 {
            inputEnergy += energy(capture)
            outputEnergy += energy(pcmSamples(output))
        }
    }

    #expect(outputEnergy < inputEnergy * 0.2)
}

@Test
func synchronizerSplitsAlignsAndReassemblesFrames() {
    let processor = PassthroughEchoCanceller()
    let collector = PacketCollector()
    let synchronizer = AEC3AudioSynchronizer(processor: processor) { packet in
        collector.append(packet)
    }
    let packetBytes = AudioMetadata().expectedFrameBytes

    for index in 0 ..< 3 {
        let render = Data(repeating: UInt8(index + 1), count: packetBytes)
        let capture = Data(repeating: UInt8(index + 21), count: packetBytes)
        let capturedAt = 1_000.09 + Double(index) * 0.1
        synchronizer.submitRender(
            AudioFramePacket(capturedAt: capturedAt, pcm: render)
        )
        synchronizer.submitCapture(
            AudioFramePacket(capturedAt: capturedAt, pcm: capture)
        )
    }
    synchronizer.flush()

    let packets = collector.packets
    #expect(packets.count == 3)
    #expect(packets.allSatisfy { $0.pcm.count == packetBytes })
    #expect(processor.callCount == 30)
    #expect(packets[0].pcm == Data(repeating: 21, count: packetBytes))
    #expect(packets[2].pcm == Data(repeating: 23, count: packetBytes))
}

private final class PassthroughEchoCanceller: EchoCancelling, @unchecked Sendable {
    private let lock = NSLock()
    private(set) var callCount = 0

    func process(render _: Data, capture: Data) -> Data {
        lock.withLock { callCount += 1 }
        return capture
    }
}

private final class PacketCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [AudioFramePacket] = []

    var packets: [AudioFramePacket] {
        lock.withLock { storage }
    }

    func append(_ packet: AudioFramePacket) {
        lock.withLock { storage.append(packet) }
    }
}

private func pcmData(_ samples: [Int16]) -> Data {
    samples.withUnsafeBufferPointer { Data(buffer: $0) }
}

private func pcmSamples(_ data: Data) -> [Int16] {
    data.withUnsafeBytes { bytes in
        Array(bytes.bindMemory(to: Int16.self))
    }
}

private func energy(_ samples: [Int16]) -> Double {
    samples.reduce(0.0) { partial, sample in
        partial + Double(sample) * Double(sample)
    }
}
