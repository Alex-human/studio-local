// Capture the final system output of this synthetic test process only.
// No microphone, other applications, source footage or persisted recordings.
import AppKit
import AVFoundation
import ScreenCaptureKit
import Accelerate

final class SpeedOutput: NSObject, SCStreamOutput {
    let lock = NSLock()
    var samples: [Double] = []
    var firstPTS: Double?
    var lastEnd: Double?
    var gaps = 0
    var recording = false
    var formatError = false
    func begin() {
        lock.lock(); defer { lock.unlock() }
        samples = []; firstPTS = nil; lastEnd = nil; gaps = 0; recording = true; formatError = false
    }
    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, CMSampleBufferIsValid(sampleBuffer) else { return }
        lock.lock(); defer { lock.unlock() }
        guard recording else { return }
        guard let description = CMSampleBufferGetFormatDescription(sampleBuffer),
              let format = CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee,
              format.mFormatFlags & kAudioFormatFlagIsFloat != 0, format.mBitsPerChannel == 32,
              format.mSampleRate == 48000 else { formatError = true; return }
        var size = 0; var block: CMBlockBuffer?
        CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer, bufferListSizeNeededOut: &size,
            bufferListOut: nil, bufferListSize: 0, blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: 0, blockBufferOut: &block)
        let raw = UnsafeMutableRawPointer.allocate(byteCount: size, alignment: 16); defer { raw.deallocate() }
        let list = raw.assumingMemoryBound(to: AudioBufferList.self)
        guard CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer, bufferListSizeNeededOut: nil,
            bufferListOut: list, bufferListSize: size, blockBufferAllocator: nil, blockBufferMemoryAllocator: nil,
            flags: 0, blockBufferOut: &block) == noErr,
            let buffer = UnsafeMutableAudioBufferListPointer(list).first, let data = buffer.mData else { return }
        let values = data.assumingMemoryBound(to: Float.self), channels = Int(buffer.mNumberChannels)
        let count = Int(buffer.mDataByteSize)/4/max(1, channels)
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer).seconds
        if let lastEnd = lastEnd, abs(pts-lastEnd) > 0.02 { gaps += 1 }
        if firstPTS == nil { firstPTS = pts }
        lastEnd = pts+Double(count)/48000
        for index in 0..<count { samples.append(Double(values[index*max(1, channels)])) }
    }
    func finish() -> [String: Any] {
        lock.lock(); recording = false
        let pcm = samples, discontinuities = gaps, invalid = formatError
        samples = []; lock.unlock()
        // Reduce in-memory PCM to 10 ms spectral envelopes. No PCM leaves memory.
        let count = 4096, hop = 480, frequencies = [317.0, 997.0, 2399.0]
        let setup = vDSP_DFT_zop_CreateSetupD(nil, vDSP_Length(count), .FORWARD)!
        defer { vDSP_DFT_DestroySetupD(setup) }
        var input = [Double](repeating: 0, count: count), imaginary = input, real = input, imag = input
        let window = (0..<count).map { 0.5-0.5*cos(2*Double.pi*Double($0)/Double(count-1)) }
        var rows: [[Double]] = []
        if pcm.count >= count {
            for offset in stride(from: 0, through: pcm.count-count, by: hop) {
                for n in 0..<count { input[n] = pcm[offset+n]*window[n] }
                vDSP_DFT_ExecuteD(setup, &input, &imaginary, &real, &imag)
                var row = [Double(offset+count/2)/48000]
                for frequency in frequencies {
                    let lower = Int((frequency-80)/48000*Double(count)), upper = Int((frequency+80)/48000*Double(count))
                    var power = 0.0, highest = 0.0, peak = 0
                    for bin in lower...upper {
                        let energy = real[bin]*real[bin]+imag[bin]*imag[bin]
                        power += energy
                        if energy > highest { highest = energy; peak = bin }
                    }
                    row.append(sqrt(power)/Double(count)); row.append(Double(peak)*48000/Double(count))
                }
                let rms = sqrt(pcm[offset..<offset+count].reduce(0) { $0+$1*$1 }/Double(count))
                row.append(rms); rows.append(row)
            }
        }
        return ["rows": rows, "samples": pcm.count, "gaps": discontinuities, "formatError": invalid]
    }
}

@main struct NativeSpeedOutputCheck {
    static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    static func wait(_ label: String, _ condition: () -> Bool) throws {
        let end = Date().addingTimeInterval(12)
        while !condition() && Date() < end { spin(0.01) }
        guard condition() else { throw PlaybackFailure(message: label) }
    }
    static func main() throws {
        guard CGPreflightScreenCaptureAccess() else {
            fputs("SKIP: Screen Recording access is unavailable; no permission requested or changed.\n", stderr); exit(77)
        }
        if CommandLine.arguments.contains("--preflight") { print("Own-process output capture permission available"); return }
        setbuf(stdout, nil); _ = NSApplication.shared
        let window = NSWindow(contentRect: NSRect(x: -1000, y: -1000, width: 20, height: 20),
            styleMask: [.borderless], backing: .buffered, defer: false)
        window.orderBack(nil); defer { window.close() }; spin(0.2)
        var content: SCShareableContent?; var contentError: Error?
        SCShareableContent.getExcludingDesktopWindows(true, onScreenWindowsOnly: false) { c, e in content = c; contentError = e }
        try wait("Could not inspect capture surfaces") { content != nil || contentError != nil }
        if let error = contentError { throw error }
        guard let app = content!.applications.first(where: { $0.processID == ProcessInfo.processInfo.processIdentifier }),
              let display = content!.displays.first else { throw PlaybackFailure(message: "Own capture process was not found") }
        let filter = SCContentFilter(display: display, including: [app], exceptingWindows: [])
        let config = SCStreamConfiguration(); config.width = 2; config.height = 2
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        config.capturesAudio = true; config.excludesCurrentProcessAudio = false; config.sampleRate = 48000; config.channelCount = 2
        let output = SpeedOutput(), stream = SCStream(filter: filter, configuration: config, delegate: nil)
        try stream.addStreamOutput(output, type: .audio, sampleHandlerQueue: DispatchQueue(label: "speed-own-output"))
        var capturing = false; var captureError: Error?
        stream.startCapture { error in captureError = error; capturing = true }
        try wait("Capture did not start") { capturing }; if let error = captureError { throw error }
        let bundle = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let plans = bundle["plans"] as! [String: [String: Any]]
        let controller = PlaybackController(); controller.player.volume = 0.08
        var phases: [[String: Any]] = []
        func load(_ key: String, frame: Int) throws {
            var result: Result<[String: Any], Error>?
            controller.load(plans[key]!, frame: frame) { result = $0 }
            try wait("Load timed out") { result != nil }; _ = try result!.get()
        }
        func capture(_ name: String, rate: Double, seconds: Double = 6, paused: Bool = false) {
            output.begin(); spin(seconds)
            var result = output.finish(); result["name"] = name; result["rate"] = rate; result["paused"] = paused
            phases.append(result); print("captured", name, result["samples"]!)
        }
        func phase(_ name: String, plan: String, rate: Double, frame: Int = 60) throws {
            try load(plan, frame: frame); try controller.setPlaybackRate(rate); controller.play()
            // The assertions use captured output, not the rate property or audio tap.
            capture(name, rate: rate); controller.pause(); spin(0.3)
        }
        try phase("linked-1", plan: "linked", rate: 1)
        try phase("free-1", plan: "free", rate: 1)
        try phase("free-1.5", plan: "free", rate: 1.5)
        try phase("free-2", plan: "free", rate: 2)
        try load("free", frame: 60); try controller.setPlaybackRate(1); controller.play()
        capture("live-before-1", rate: 1)
        try controller.setPlaybackRate(2); capture("live-after-2", rate: 2)
        controller.pause(); spin(0.5); capture("paused", rate: 2, seconds: 1.5, paused: true)
        var sought = false; controller.seek(360) { sought = true }; try wait("Seek timed out") { sought }
        try controller.setPlaybackRate(1.5); controller.play(); capture("seek-free-1.5", rate: 1.5)
        controller.pause(); spin(0.3)
        try phase("ducking-1", plan: "ducking", rate: 1)
        try phase("ducking-1.5", plan: "ducking", rate: 1.5)
        try phase("ducking-2", plan: "ducking", rate: 2)
        controller.stop(); var stopped = false
        stream.stopCapture { _ in stopped = true }; try wait("Capture did not stop") { stopped }
        try JSONSerialization.data(withJSONObject: ["phases": phases, "captureScope": "own-process-only",
            "sampleRate": 48000, "pcmPersisted": false]).write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
    }
}
