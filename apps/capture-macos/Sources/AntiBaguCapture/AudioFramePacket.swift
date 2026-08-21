import Foundation

struct AudioFramePacket: Equatable, Sendable {
    static let headerBytes = MemoryLayout<UInt64>.size

    let capturedAt: TimeInterval
    let pcm: Data

    var encoded: Data {
        var timestampBits = capturedAt.bitPattern.littleEndian
        var packet = Data(bytes: &timestampBits, count: Self.headerBytes)
        packet.append(pcm)
        return packet
    }
}
