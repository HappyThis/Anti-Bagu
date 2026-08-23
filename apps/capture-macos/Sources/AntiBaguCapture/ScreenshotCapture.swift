import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

enum ScreenshotCapture {
    static func captureJPEG(maxLongEdge: Int = 2_560) throws -> Data {
        let cursor = CGEvent(source: nil)?.location ?? .zero
        var displayID = CGMainDisplayID()
        var displayCount: UInt32 = 0
        CGGetDisplaysWithPoint(cursor, 1, &displayID, &displayCount)
        if displayCount == 0 {
            displayID = CGMainDisplayID()
        }
        guard let image = CGDisplayCreateImage(displayID) else {
            throw ScreenshotCaptureError.captureFailed
        }
        return try encodeJPEG(image, maxLongEdge: maxLongEdge)
    }

    static func encodeJPEG(
        _ image: CGImage,
        maxLongEdge: Int = 2_560,
        quality: Double = 0.78
    ) throws -> Data {
        let prepared = try resized(image, maxLongEdge: maxLongEdge)
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data,
            UTType.jpeg.identifier as CFString,
            1,
            nil
        ) else {
            throw ScreenshotCaptureError.encodingFailed
        }
        let properties = [
            kCGImageDestinationLossyCompressionQuality: quality,
        ] as CFDictionary
        CGImageDestinationAddImage(destination, prepared, properties)
        guard CGImageDestinationFinalize(destination) else {
            throw ScreenshotCaptureError.encodingFailed
        }
        return data as Data
    }

    private static func resized(_ image: CGImage, maxLongEdge: Int) throws -> CGImage {
        let longest = max(image.width, image.height)
        guard longest > maxLongEdge else { return image }
        let scale = Double(maxLongEdge) / Double(longest)
        let width = max(1, Int((Double(image.width) * scale).rounded()))
        let height = max(1, Int((Double(image.height) * scale).rounded()))
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(
                  data: nil,
                  width: width,
                  height: height,
                  bitsPerComponent: 8,
                  bytesPerRow: 0,
                  space: colorSpace,
                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
              )
        else {
            throw ScreenshotCaptureError.encodingFailed
        }
        context.interpolationQuality = .high
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let resized = context.makeImage() else {
            throw ScreenshotCaptureError.encodingFailed
        }
        return resized
    }
}

enum ScreenshotCaptureError: Error, CustomStringConvertible {
    case captureFailed
    case encodingFailed

    var description: String {
        switch self {
        case .captureFailed: "The current display could not be captured."
        case .encodingFailed: "The screenshot could not be encoded."
        }
    }
}
