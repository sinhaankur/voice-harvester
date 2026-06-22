// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "VoiceHarvester",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "VoiceHarvester",
            path: "Sources/VoiceHarvester"
        )
    ]
)
