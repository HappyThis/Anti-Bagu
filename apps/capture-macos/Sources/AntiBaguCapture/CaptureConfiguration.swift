import Foundation

struct CaptureConfiguration: Sendable {
    let backendURL: URL
    let metadata: AudioMetadata

    init(
        backendURL: URL = URL(string: "ws://127.0.0.1:8765")!,
        metadata: AudioMetadata = AudioMetadata()
    ) {
        self.backendURL = backendURL
        self.metadata = metadata
    }

    func endpoint(for channel: AudioChannel) -> URL {
        backendURL
            .appending(path: "ws")
            .appending(path: "audio")
            .appending(path: channel.rawValue)
    }
}
