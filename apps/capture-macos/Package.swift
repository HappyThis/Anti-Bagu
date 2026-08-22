// swift-tools-version: 6.1

import PackageDescription

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
            linkerSettings: [.linkedFramework("Security")]
        ),
        .testTarget(
            name: "AntiBaguCaptureTests",
            dependencies: ["AntiBaguCapture"]
        ),
    ]
)
