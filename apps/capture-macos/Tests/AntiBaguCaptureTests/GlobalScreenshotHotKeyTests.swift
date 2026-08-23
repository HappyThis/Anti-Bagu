import AppKit
import Testing
@testable import AntiBaguCapture

@Test @MainActor
func optionSpaceHotKeyRegistersAndUnregisters() throws {
    NSApplication.shared.setActivationPolicy(.accessory)
    let hotKey = GlobalScreenshotHotKey {}
    try hotKey.register()
    hotKey.unregister()
}
