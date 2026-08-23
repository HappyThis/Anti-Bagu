import Foundation
import Testing
@testable import AntiBaguCapture

@Test
func signalLevelRecognizesSilence() {
    let level = AudioSignalLevel.measure(Data(repeating: 0, count: 3_200))

    #expect(level == .silence)
}

@Test
func signalLevelMeasuresPCMAmplitude() {
    var pcm = Data()
    for _ in 0 ..< 1_600 {
        var sample = Int16(16_384).littleEndian
        withUnsafeBytes(of: &sample) { pcm.append(contentsOf: $0) }
    }

    let level = AudioSignalLevel.measure(pcm)

    #expect(abs(level.rms - 0.5) < 0.001)
    #expect(abs(level.peak - 0.5) < 0.001)
    #expect(abs(level.decibels + 6.0206) < 0.01)
    #expect(level.normalized > 0.89)
}
