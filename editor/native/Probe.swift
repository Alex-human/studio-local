import Foundation
import AVFoundation

@main struct Probe {
    static func main() async {
        guard CommandLine.arguments.count == 2 else { exit(2) }
        do {
            let asset = AVURLAsset(url: URL(fileURLWithPath: CommandLine.arguments[1]))
            let tracks = try await asset.loadTracks(withMediaType: .video)
            var result: [String: Any] = [:]
            if let track = tracks.first {
                let range = try await track.load(.timeRange)
                let fps = try await track.load(.nominalFrameRate)
                let size = try await track.load(.naturalSize)
                let transform = try await track.load(.preferredTransform)
                let rect = CGRect(origin: .zero, size: size).applying(transform)
                result = ["duration": CMTimeGetSeconds(range.duration), "fps": Double(fps), "width": Int(abs(rect.width)), "height": Int(abs(rect.height))]
            } else {
                let duration = try await asset.load(.duration)
                result = ["duration": CMTimeGetSeconds(duration)]
            }
            let data = try JSONSerialization.data(withJSONObject: result)
            FileHandle.standardOutput.write(data)
        } catch { exit(1) }
    }
}
