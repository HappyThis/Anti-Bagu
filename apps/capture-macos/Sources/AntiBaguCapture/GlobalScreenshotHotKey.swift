import Carbon
import Foundation

final class GlobalScreenshotHotKey: @unchecked Sendable {
    private static let hotKeyID = EventHotKeyID(
        signature: fourCharacterCode("ABSS"),
        id: 1
    )

    private let action: @Sendable () -> Void
    private var hotKey: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?

    init(action: @escaping @Sendable () -> Void) {
        self.action = action
    }

    deinit {
        unregister()
    }

    func register() throws {
        guard hotKey == nil else { return }
        var eventType = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )
        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, userData in
                guard let event, let userData else { return OSStatus(eventNotHandledErr) }
                var identifier = EventHotKeyID()
                let status = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &identifier
                )
                guard status == noErr,
                      identifier.id == GlobalScreenshotHotKey.hotKeyID.id
                else {
                    return OSStatus(eventNotHandledErr)
                }
                Unmanaged<GlobalScreenshotHotKey>
                    .fromOpaque(userData)
                    .takeUnretainedValue()
                    .action()
                return noErr
            },
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            &eventHandler
        )
        guard handlerStatus == noErr else {
            throw GlobalHotKeyError.registrationFailed(handlerStatus)
        }

        let hotKeyStatus = RegisterEventHotKey(
            UInt32(kVK_Space),
            UInt32(optionKey),
            Self.hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKey
        )
        guard hotKeyStatus == noErr else {
            unregister()
            throw GlobalHotKeyError.registrationFailed(hotKeyStatus)
        }
    }

    func unregister() {
        if let hotKey {
            UnregisterEventHotKey(hotKey)
            self.hotKey = nil
        }
        if let eventHandler {
            RemoveEventHandler(eventHandler)
            self.eventHandler = nil
        }
    }
}

private func fourCharacterCode(_ value: String) -> FourCharCode {
    value.utf8.reduce(0) { ($0 << 8) + FourCharCode($1) }
}

enum GlobalHotKeyError: Error, CustomStringConvertible {
    case registrationFailed(OSStatus)

    var description: String {
        switch self {
        case let .registrationFailed(status):
            "The Option+Space shortcut could not be registered (OSStatus "
                + String(status)
                + ")."
        }
    }
}
