import AppKit
import AVFoundation

@main struct NativeSpeedCheck {
    static func spin(_ seconds: Double) { RunLoop.main.run(until: Date().addingTimeInterval(seconds)) }
    static func wait(_ message: String, _ condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(10)
        while !condition() && Date() < deadline { spin(0.005) }
        precondition(condition(), message)
    }
    static func load(_ controller: PlaybackController, _ plan: [String: Any], frame: Int = 0) throws -> [String: Any] {
        var result: Result<[String: Any], Error>?
        controller.load(plan, frame: frame) { result = $0 }
        wait("Load timed out") { result != nil }
        return try result!.get()
    }
    static func seek(_ controller: PlaybackController, _ frame: Int) {
        var complete = false
        controller.seek(frame) { complete = true }
        wait("Seek timed out") { complete }
    }
    static func measure(_ controller: PlaybackController, _ rate: Double) -> Double {
        wait("Player did not start") { controller.player.timeControlStatus == .playing }
        let initial = controller.player.currentTime().seconds
        wait("Player clock did not advance") { controller.player.currentTime().seconds > initial+0.2 }
        spin(0.2)
        let start = controller.player.currentTime().seconds, wall = ProcessInfo.processInfo.systemUptime
        spin(0.4)
        let elapsed = ProcessInfo.processInfo.systemUptime-wall
        let measured = (controller.player.currentTime().seconds-start)/elapsed
        precondition(abs(measured-rate) < 0.12, "Rate \(rate): measured \(measured)")
        return measured
    }
    static func checkCue(_ controller: PlaybackController, id: String, start: Double, source: Double, rate: Double) {
        wait("Cue did not start: \(id)") { controller.cuePlayers.contains { $0.id == id } }
        let sound = controller.cuePlayers.first { $0.id == id }!.player
        precondition(sound.enableRate && abs(Double(sound.rate)-rate) < 0.00001)
        precondition(sound.isPlaying, "Cue not playing")
        let error = abs(sound.currentTime-(source+controller.player.currentTime().seconds-start))
        precondition(error < 0.16, "Cue lost timeline alignment: \(error)")
    }
    static func main() throws {
        setbuf(stdout, nil)
        let plan = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let controller = PlaybackController(); controller.player.volume = 0
        // A selection made before the first load is retained by the host.
        try controller.setPlaybackRate(1.25)
        _ = try load(controller, plan)
        precondition(controller.playbackRate == 1.25 && controller.player.rate == 0)
        precondition(controller.player.currentItem!.audioTimePitchAlgorithm == .timeDomain)
        let duration = controller.player.currentItem!.duration.seconds
        var measurements: [[String: Double]] = []
        for rate in [1.0, 1.25, 1.5, 2.0] {
            controller.pause(); seek(controller, 300); try controller.setPlaybackRate(rate)
            precondition(controller.player.rate == 0)
            controller.play()
            measurements.append(["requested": rate, "measured": measure(controller, rate)])
            controller.pause(); seek(controller, 0); controller.play()
            wait("Cue timeline start") { controller.player.currentTime().seconds >= 0.85 }
            checkCue(controller, id: "short", start: 0.6, source: 1, rate: rate)
            wait("Cue timeline end") { controller.player.currentTime().seconds >= 2.0 }
            precondition(!controller.cuePlayers.contains { $0.id == "short" }, "Cue exceeded its trimmed duration")
            precondition(controller.player.currentItem!.duration.seconds == duration)
        }
        // Live changes preserve the player item, timeline position and cue phase.
        let item = controller.player.currentItem!
        seek(controller, 99)
        try controller.setPlaybackRate(2)
        checkCue(controller, id: "long", start: 3, source: 0.25, rate: 2)
        try controller.setPlaybackRate(1.25)
        checkCue(controller, id: "long", start: 3, source: 0.25, rate: 1.25)
        measurements.append(["requested": 1.25, "measured": measure(controller, 1.25)])
        precondition(controller.player.currentItem === item)
        controller.pause(); let paused = controller.player.currentTime().seconds
        try controller.setPlaybackRate(1.5); spin(0.15)
        precondition(controller.player.rate == 0 && controller.cuePlayers.isEmpty)
        precondition(abs(controller.player.currentTime().seconds-paused) < 0.01)
        seek(controller, 120); controller.play()
        checkCue(controller, id: "long", start: 3, source: 0.25, rate: 1.5)
        // A pause while an asynchronous seek completes must never restart cues.
        controller.seek(100); controller.pause(); spin(0.2)
        precondition(controller.player.rate == 0 && controller.cuePlayers.isEmpty)
        var reusedPlan = plan; reusedPlan["key"] = "speed-reused"
        let reuse = try load(controller, reusedPlan, frame: 100)
        precondition(reuse["reused"] as? Bool == true && controller.player.currentItem === item)
        precondition(controller.playbackRate == 1.5 && controller.player.rate == 0)
        controller.play(); checkCue(controller, id: "long", start: 3, source: 0.25, rate: 1.5)
        // Reject invalid values without changing playback, including NaN/infinity.
        for rate in [0, 0.99, 2.01, 3, Double.nan, Double.infinity, -Double.infinity] {
            var rejected = false
            do { try controller.setPlaybackRate(rate) } catch { rejected = true }
            precondition(rejected && controller.playbackRate == 1.5 && controller.player.rate == 1.5)
        }
        var rebuiltPlan = plan; rebuiltPlan["mediaKey"] = "speed-rebuilt"; rebuiltPlan["key"] = "speed-rebuilt"
        _ = try load(controller, rebuiltPlan)
        precondition(controller.player.currentItem !== item && controller.playbackRate == 1.5 && controller.player.rate == 0)
        precondition(controller.player.currentItem!.audioTimePitchAlgorithm == .timeDomain)
        controller.play(); measurements.append(["requested": 1.5, "measured": measure(controller, 1.5)])
        // Stop invalidates an in-flight seek and preserves the user's review rate.
        controller.seek(110); controller.stop(); spin(0.2)
        precondition(controller.timeline == nil && controller.cuePlayers.isEmpty && controller.player.rate == 0)
        precondition(controller.playbackRate == 1.5)
        _ = try load(controller, plan); controller.play()
        measurements.append(["requested": 1.5, "measured": measure(controller, 1.5)])
        controller.stop()
        print(String(data: try JSONSerialization.data(withJSONObject: measurements, options: [.sortedKeys]), encoding: .utf8)!)
        print("PASS native 1/1.25/1.5/2× progression, pitch policy, live change, pause, seeks, stale seek, reuse/rebuild, invalid rates and synchronized cue start/trim/rate/offset")
    }
}
