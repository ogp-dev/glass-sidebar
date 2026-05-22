// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "GlassSidebar",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "GlassSidebar", targets: ["GlassSidebar"]),
    ],
    targets: [
        .executableTarget(
            name: "GlassSidebar",
            path: "GlassSidebar"
        ),
        .testTarget(
            name: "GlassSidebarTests",
            dependencies: ["GlassSidebar"],
            path: "GlassSidebarTests"
        ),
    ]
)
