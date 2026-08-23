import Foundation

struct AudioSignalLevel: Equatable, Sendable {
    static let silence = AudioSignalLevel(rms: 0, peak: 0, decibels: -80, normalized: 0)

    let rms: Double
    let peak: Double
    let decibels: Double
    let normalized: Double

    static func measure(_ pcm: Data) -> AudioSignalLevel {
        guard pcm.count >= 2 else { return .silence }
        var squareSum = 0.0
        var peak = 0.0
        var sampleCount = 0
        var index = pcm.startIndex
        while index + 1 < pcm.endIndex {
            let low = UInt16(pcm[index])
            let high = UInt16(pcm[index + 1]) << 8
            let sample = Double(Int16(bitPattern: low | high)) / 32_768.0
            let magnitude = abs(sample)
            squareSum += sample * sample
            peak = max(peak, magnitude)
            sampleCount += 1
            index += 2
        }
        guard sampleCount > 0 else { return .silence }
        let rms = sqrt(squareSum / Double(sampleCount))
        let decibels = max(-80, 20 * log10(max(rms, 0.0001)))
        let normalized = min(1, max(0, (decibels + 60) / 60))
        return AudioSignalLevel(
            rms: rms,
            peak: peak,
            decibels: decibels,
            normalized: normalized
        )
    }
}

actor TerminalSignalMeter {
    private var interview = AudioSignalLevel.silence
    private var microphone = AudioSignalLevel.silence
    private var renderer: Task<Void, Never>?

    func start() {
        guard CLIOutput.dynamicOutputEnabled, renderer == nil else { return }
        renderer = Task { [weak self] in
            while !Task.isCancelled {
                await self?.render()
                try? await Task.sleep(for: .milliseconds(150))
            }
        }
    }

    func update(channel: AudioChannel, pcm: Data) {
        guard CLIOutput.dynamicOutputEnabled else { return }
        let level = AudioSignalLevel.measure(pcm)
        switch channel {
        case .interviewer:
            interview = level
        case .candidate:
            microphone = level
        }
    }

    func stop() async {
        let activeRenderer = renderer
        renderer = nil
        activeRenderer?.cancel()
        await activeRenderer?.value
        CLIOutput.finishSignal()
    }

    private func render() {
        CLIOutput.signal(interview: interview, microphone: microphone)
    }
}
