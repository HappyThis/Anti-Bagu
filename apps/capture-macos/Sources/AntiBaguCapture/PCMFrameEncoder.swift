import AVFoundation
import CoreMedia
import Foundation

final class PCMFrameEncoder: @unchecked Sendable {
    typealias FrameHandler = @Sendable (AudioFramePacket) -> Void

    private let targetFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16,
        sampleRate: 16_000,
        channels: 1,
        interleaved: false
    )!
    private let frameBytes = 3_200
    private let lock = NSLock()
    private let frameHandler: FrameHandler
    private var converter: AVAudioConverter?
    private var sourceSignature: String?
    private var pendingPCM = Data()

    init(frameHandler: @escaping FrameHandler) {
        self.frameHandler = frameHandler
    }

    func consume(_ sampleBuffer: CMSampleBuffer) {
        guard
            sampleBuffer.isValid,
            CMSampleBufferDataIsReady(sampleBuffer),
            let description = CMSampleBufferGetFormatDescription(sampleBuffer)
        else { return }
        let sourceFormat = AVAudioFormat(cmAudioFormatDescription: description)

        let frameCount = AVAudioFrameCount(CMSampleBufferGetNumSamples(sampleBuffer))
        guard
            frameCount > 0,
            let pcmBuffer = AVAudioPCMBuffer(
                pcmFormat: sourceFormat,
                frameCapacity: frameCount
            )
        else { return }

        pcmBuffer.frameLength = frameCount
        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(
            sampleBuffer,
            at: 0,
            frameCount: Int32(frameCount),
            into: pcmBuffer.mutableAudioBufferList
        )
        guard status == noErr else { return }
        consume(pcmBuffer)
    }

    func consume(_ inputBuffer: AVAudioPCMBuffer) {
        let emittedFrames: [Data] = lock.withLock {
            convertAndFrame(inputBuffer)
        }
        guard !emittedFrames.isEmpty else { return }

        let latestCaptureAt = Date().timeIntervalSince1970
        let total = emittedFrames.count
        for (index, pcm) in emittedFrames.enumerated() {
            let framesAfterThis = total - index - 1
            frameHandler(
                AudioFramePacket(
                    capturedAt: latestCaptureAt - Double(framesAfterThis) * 0.1,
                    pcm: pcm
                )
            )
        }
    }

    private func convertAndFrame(_ inputBuffer: AVAudioPCMBuffer) -> [Data] {
        let inputFormat = inputBuffer.format
        let signature = "\(inputFormat.sampleRate)-\(inputFormat.channelCount)-\(inputFormat.commonFormat.rawValue)-\(inputFormat.isInterleaved)"
        if sourceSignature != signature {
            converter = AVAudioConverter(from: inputFormat, to: targetFormat)
            sourceSignature = signature
        }
        guard let converter else { return [] }

        let ratio = targetFormat.sampleRate / inputFormat.sampleRate
        let capacity = max(
            AVAudioFrameCount(Double(inputBuffer.frameLength) * ratio) + 32,
            64
        )
        guard let output = AVAudioPCMBuffer(
            pcmFormat: targetFormat,
            frameCapacity: capacity
        ) else { return [] }

        var suppliedInput = false
        var conversionError: NSError?
        let conversionStatus = converter.convert(
            to: output,
            error: &conversionError
        ) { _, status in
            if suppliedInput {
                status.pointee = .noDataNow
                return nil
            }
            suppliedInput = true
            status.pointee = .haveData
            return inputBuffer
        }
        guard
            conversionStatus != .error,
            conversionError == nil,
            output.frameLength > 0,
            let channelData = output.int16ChannelData?[0]
        else { return [] }

        pendingPCM.append(
            Data(
                bytes: channelData,
                count: Int(output.frameLength) * MemoryLayout<Int16>.size
            )
        )

        var frames: [Data] = []
        while pendingPCM.count >= frameBytes {
            frames.append(Data(pendingPCM.prefix(frameBytes)))
            pendingPCM.removeFirst(frameBytes)
        }
        return frames
    }
}
