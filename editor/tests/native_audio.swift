import AVFoundation
import CryptoKit

@main struct NativeAudioCheck {
    static func digest(_ asset: AVAsset) throws -> (String, Int) {
        let tracks = asset.tracks(withMediaType: .audio)
        precondition(tracks.count == 1, "Playback must contain exactly one audio track")
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: tracks[0], outputSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVLinearPCMBitDepthKey: 32,
            AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsNonInterleaved: false
        ])
        reader.add(output)
        guard reader.startReading() else { throw reader.error! }
        var hash = SHA256(), bytes = 0
        while let sample = output.copyNextSampleBuffer() {
            let block = CMSampleBufferGetDataBuffer(sample)!
            var length = 0
            var pointer: UnsafeMutablePointer<Int8>?
            precondition(CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: nil,
                totalLengthOut: &length, dataPointerOut: &pointer) == noErr)
            hash.update(data: Data(bytes: pointer!, count: length)); bytes += length
        }
        guard reader.status == .completed else { throw reader.error! }
        return (hash.finalize().map { String(format: "%02x", $0) }.joined(), bytes)
    }
    static func main() throws {
        let plan = try JSONSerialization.jsonObject(with: Data(contentsOf:
            URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let timeline = try PlaybackTimeline.build(plan)
        let actual = try digest(timeline.item.asset)
        let expected = try digest(AVURLAsset(url: URL(fileURLWithPath: plan["audio"] as! String)))
        precondition(actual == expected, "Native audio differs from the prepared mix")
        print(String(data: try JSONSerialization.data(withJSONObject: [
            "identical": true, "audioTracks": 1, "decodedBytes": actual.1,
            "sha256": actual.0, "frames": timeline.frames
        ], options: [.sortedKeys]), encoding: .utf8)!)
    }
}
