import CoreGraphics
import Foundation
import ImageIO
import Testing
@testable import AntiBaguCapture

@Test
func screenshotEncoderDownscalesAndProducesJPEG() throws {
    let colorSpace = try #require(CGColorSpace(name: CGColorSpace.sRGB))
    let context = try #require(
        CGContext(
            data: nil,
            width: 400,
            height: 200,
            bitsPerComponent: 8,
            bytesPerRow: 0,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        )
    )
    context.setFillColor(CGColor(red: 0.1, green: 0.3, blue: 0.8, alpha: 1))
    context.fill(CGRect(x: 0, y: 0, width: 400, height: 200))
    let image = try #require(context.makeImage())

    let data = try ScreenshotCapture.encodeJPEG(image, maxLongEdge: 100)
    let source = try #require(CGImageSourceCreateWithData(data as CFData, nil))
    let encoded = try #require(CGImageSourceCreateImageAtIndex(source, 0, nil))

    #expect(encoded.width == 100)
    #expect(encoded.height == 50)
    #expect(data.starts(with: [0xFF, 0xD8]))
}
