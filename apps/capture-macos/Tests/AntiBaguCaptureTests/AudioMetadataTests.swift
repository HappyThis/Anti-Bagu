import Foundation
import Testing
@testable import AntiBaguCapture

@Test func metadataMatchesV1Protocol() throws {
    let metadata = AudioMetadata()
    let data = try JSONEncoder().encode(metadata)
    let object = try #require(
        JSONSerialization.jsonObject(with: data) as? [String: Any]
    )

    #expect(object["sample_rate"] as? Int == 16_000)
    #expect(object["channels"] as? Int == 1)
    #expect(object["sample_format"] as? String == "pcm_s16le")
    #expect(object["frame_duration_ms"] as? Int == 100)
    #expect(metadata.expectedFrameBytes == 3_200)
}

@Test func audioPacketAddsLittleEndianCaptureTimestamp() throws {
    let packet = AudioFramePacket(capturedAt: 1_800_000_000.25, pcm: Data(count: 3_200))
    #expect(packet.encoded.count == 3_208)
    let bits = packet.encoded.prefix(8).withUnsafeBytes {
        $0.loadUnaligned(as: UInt64.self)
    }
    #expect(TimeInterval(bitPattern: UInt64(littleEndian: bits)) == packet.capturedAt)
}

@Test func endpointsKeepChannelsSeparated() {
    let configuration = CaptureConfiguration()
    #expect(
        configuration.endpoint(for: .interviewer).absoluteString
            == "ws://127.0.0.1:8765/ws/audio/interviewer"
    )
    #expect(
        configuration.endpoint(for: .candidate).absoluteString
            == "ws://127.0.0.1:8765/ws/audio/candidate"
    )
}
