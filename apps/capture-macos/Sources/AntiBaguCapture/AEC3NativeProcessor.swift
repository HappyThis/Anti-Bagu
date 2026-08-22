import AntiBaguAECBridge
import Foundation

protocol EchoCancelling: AnyObject, Sendable {
    func process(render: Data, capture: Data) throws -> Data
}

final class AEC3NativeProcessor: EchoCancelling, @unchecked Sendable {
    static let sampleRate = 16_000
    static let samplesPerFrame = 160
    static let bytesPerFrame = samplesPerFrame * MemoryLayout<Int16>.size

    private let context: UnsafeMutableRawPointer
    private let lock = NSLock()

    init() throws {
        guard let created = anti_bagu_aec3_create(Int32(Self.sampleRate)) else {
            throw AEC3Error.initializationFailed
        }
        context = created
    }

    deinit {
        anti_bagu_aec3_destroy(context)
    }

    func process(render: Data, capture: Data) throws -> Data {
        guard render.count == Self.bytesPerFrame,
              capture.count == Self.bytesPerFrame
        else {
            throw AEC3Error.invalidFrameSize
        }
        return try lock.withLock {
            var output = [Int16](repeating: 0, count: Self.samplesPerFrame)
            let result = render.withUnsafeBytes { renderBytes in
                capture.withUnsafeBytes { captureBytes in
                    output.withUnsafeMutableBufferPointer { outputBuffer in
                        anti_bagu_aec3_process(
                            context,
                            renderBytes.bindMemory(to: Int16.self).baseAddress,
                            captureBytes.bindMemory(to: Int16.self).baseAddress,
                            outputBuffer.baseAddress,
                            Self.samplesPerFrame
                        )
                    }
                }
            }
            guard result == 0 else { throw AEC3Error.processingFailed(result) }
            return output.withUnsafeBufferPointer { Data(buffer: $0) }
        }
    }

    static func isAvailable() -> Bool {
        (try? AEC3NativeProcessor()) != nil
    }
}

enum AEC3Error: Error, CustomStringConvertible {
    case initializationFailed
    case invalidFrameSize
    case processingFailed(Int32)

    var description: String {
        switch self {
        case .initializationFailed:
            "AEC3 音频处理初始化失败"
        case .invalidFrameSize:
            "AEC3 收到了错误长度的音频帧"
        case let .processingFailed(code):
            "AEC3 音频处理失败（\(code)）"
        }
    }
}
