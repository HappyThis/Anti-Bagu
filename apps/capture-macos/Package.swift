// swift-tools-version: 6.1

import PackageDescription

let package = Package(
    name: "AntiBaguCapture",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "anti-bagu-capture", targets: ["AntiBaguCapture"]),
    ],
    targets: [
        .executableTarget(name: "AntiBaguCapture"),
        .testTarget(
            name: "AntiBaguCaptureTests",
            dependencies: ["AntiBaguCapture"]
        ),
    ]
)
