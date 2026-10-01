import AppKit
import AVFoundation
import MediaToolbox

// Twenty camera files with one AAC format share one composition track, stay on their
// exact sample, keep their own clip gains and sound from the first block after a load
// or a seek. With one track per file AVPlayer started the later tracks up to half a
// second late; cuts between two samples used to push each following clip later.
final class Starts {
    let lock = NSLock(); var values: [Double] = []
    func add(_ value: Double) { lock.lock(); values.append(value); lock.unlock() }
    func take() -> [Double] { lock.lock(); defer { lock.unlock() }; let v = values; values = []; return v }
}
let starts = Starts()

@main struct AudioStart {
    static func samples(_ asset: AVAsset, mix: AVAudioMix?, range: CMTimeRange? = nil) throws -> [Float] {
        let reader = try AVAssetReader(asset: asset)
        if let range = range { reader.timeRange = range }
        let output = AVAssetReaderAudioMixOutput(audioTracks: asset.tracks(withMediaType: .audio), audioSettings: [
            AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 48000, AVNumberOfChannelsKey: 2,
            AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true, AVLinearPCMIsNonInterleaved: false])
        output.audioMix = mix; reader.add(output)
        guard reader.startReading() else { throw reader.error! }
        var data = Data()
        while let sample = output.copyNextSampleBuffer() {
            let block = CMSampleBufferGetDataBuffer(sample)!; var length = 0; var pointer: UnsafeMutablePointer<Int8>?
            precondition(CMBlockBufferGetDataPointer(block, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &pointer) == noErr)
            data.append(Data(bytes: pointer!, count: length))
        }
        guard reader.status == .completed else { throw reader.error! }
        return data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }
    static func number(_ source: [String: Any], _ key: String) -> Double { (source[key] as! NSNumber).doubleValue }
    static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    static func wait(_ check: () -> Bool) { let end = Date().addingTimeInterval(10); while !check() && Date() < end { spin(0.005) }; precondition(check()) }

    static func main() throws {
        setbuf(stdout, nil)
        let plan = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let sources = plan["audioSources"] as! [[String: Any]]
        let timeline = try PlaybackTimeline.build(plan)
        let tracks = timeline.item.asset.tracks(withMediaType: .audio).count
        precondition(tracks == 1, "\(sources.count) files with one format need one audio track, got \(tracks)")

        // Each file sounds at its own place and nothing drifts: cuts fall between samples
        // at 59.94 fps, and a clip may sit at most two samples from its exact position.
        let full = try samples(timeline.item.asset, mix: timeline.item.audioMix)
        var worst = (lag: 0, error: 0.0)
        for source in sources {
            let base = Int(((number(source, "start")+0.05)*48000).rounded()), count = Int(((number(source, "length")-0.1)*48000).rounded())
            let file = AVURLAsset(url: URL(fileURLWithPath: source["path"] as! String))
            let own = try samples(file, mix: nil, range: CMTimeRange(start: CMTime(seconds: number(source, "source")+0.05, preferredTimescale: 600000),
                                                                      duration: CMTime(seconds: number(source, "length")-0.1, preferredTimescale: 600000)))
            precondition(own.count >= count*2 && full.count >= (base+count+8)*2, "short decode for \(source["id"]!)")
            var best = (lag: 0, error: Double.infinity)
            for lag in -8...8 {
                var error = 0.0, energy = 0.0
                for k in 0..<count { let d = Double(full[(base+lag+k)*2]-own[k*2]); error += d*d; energy += Double(own[k*2]*own[k*2]) }
                if error/energy < best.error { best = (lag, error/energy) }
            }
            worst = (max(worst.lag, abs(best.lag)), max(worst.error, best.error))
            precondition(abs(best.lag) <= 2 && best.error < 0.000001, "\(source["id"]!) sits \(best.lag) samples off, relative error \(best.error)")
        }
        // Clip gains stay independent inside the shared tap.
        var levels: [String: Double] = [:]
        for (index, source) in sources.enumerated() { levels[source["id"] as! String] = [1, 0.25, 0][index % 3] }
        timeline.setVolumes(levels)
        let adjusted = try samples(timeline.item.asset, mix: timeline.item.audioMix)
        for (index, source) in sources.enumerated() {
            let start = Int((number(source, "start")*48000).rounded(.up))*2, count = Int((number(source, "length")*48000).rounded(.down)-1)*2
            let gain = Float([1, 0.25, 0][index % 3])
            let error = zip(adjusted[start..<start+count], full[start..<start+count]).map { abs($0-gain*$1) }.max()!
            precondition(error < 0.000001, "gain \(gain) of \(source["id"]!) off by \(error)")
        }

        // Live player: the first processed block after play starts where playback starts.
        let c = PlaybackController(); c.player.volume = 0
        let fps = number(plan, "fpsNum")/number(plan, "fpsDen")
        var results: [[String: Any]] = []
        func play(_ index: Int, fresh: Bool) throws {
            let source = sources[index], t0 = number(source, "start")+1, frame = Int((t0*fps).rounded())
            if fresh {
                c.stop(); var done = false; var failure: Error?
                c.load(plan, frame: frame) { result in if case .failure(let error) = result { failure = error }; done = true }
                wait { done }; if let error = failure { throw error }
            }
            c.timeline!.gains.forEach { $0.observeStart = nil }
            c.timeline!.gains.first { $0.spans.contains { $0.id == source["id"] as! String } }!.observeStart = { starts.add($0) }
            var done = false; c.seek(frame) { done = true }; wait { done }
            _ = starts.take(); c.play(); spin(1); c.pause()
            let first = starts.take().first { $0.isFinite && $0 > t0-0.2 && $0 < t0+3 }
            precondition(first != nil, "\(source["id"]!) produced no audio after play")
            let late = max(0, first!-t0)
            results.append(["id": source["id"]!, "load": fresh, "late": (late*1000).rounded()/1000])
            precondition(late < 0.2, "\(source["id"]!) audio started \(late) s after play (\(fresh ? "load" : "seek"))")
        }
        for index in sources.indices.suffix(5) { try play(index, fresh: true) }
        // Seek away from the last pause: blocks rendered before a pause keep their old times.
        for index in [sources.count-3, sources.count-5, sources.count-7] { try play(index, fresh: false) }
        c.stop()
        print(String(data: try JSONSerialization.data(withJSONObject: results, options: [.sortedKeys]), encoding: .utf8)!)
        print("PASS \(sources.count) same-format files on one track, placement within \(worst.lag) samples (relative error \(worst.error)), clip gains, audio from the first block after load and seek")
    }
}
