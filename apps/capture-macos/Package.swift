// swift-tools-version: 6.1

import Foundation
import PackageDescription

let packageDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let aec3LibraryDirectory = packageDirectory
    .appending(path: "NativeAEC3/.build")
    .path

let package = Package(
    name: "AntiBaguCapture",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "anti-bagu-capture", targets: ["AntiBaguCapture"]),
        .executable(name: "anti-bagu-agent", targets: ["AntiBaguCapture"]),
    ],
    targets: [
        .executableTarget(
            name: "AntiBaguCapture",
            dependencies: ["AntiBaguAECBridge"],
            linkerSettings: [
                .unsafeFlags(["-L", aec3LibraryDirectory, "-lanti-bagu-aec3"]),
                .linkedFramework("CoreFoundation"),
                .linkedLibrary("c++"),
            ]
        ),
        .target(
            name: "AntiBaguAECBridge",
            path: "Sources/AntiBaguAECBridge",
            publicHeadersPath: "include"
        ),
        .testTarget(
            name: "AntiBaguCaptureTests",
            dependencies: ["AntiBaguCapture"]
        ),
    ]
)
