import AppKit
import AVFoundation

@main struct ProgressiveCheck {
    static func wait(_ condition:()->Bool,seconds:Double=8) throws {
        let deadline=Date().addingTimeInterval(seconds)
        while !condition() && Date()<deadline { RunLoop.main.run(until:Date().addingTimeInterval(0.01)) }
        guard condition() else { throw PlaybackFailure(message:"Progressive playback timed out") }
    }
    static func main() throws {
        func read(_ index:Int) throws -> [String:Any] { try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[index]))) as! [String:Any] }
        let first=try read(1),second=try read(2),controller=PlaybackController()
        let start=first["windowStart"] as! Int,next=second["windowStart"] as! Int
        var loaded:Result<[String:Any],Error>?,queued:Result<[String:Any],Error>?
        controller.load(first,frame:start) { loaded=$0 };try wait { loaded != nil };_ = try loaded!.get()
        controller.queue(second,afterKey:first["key"] as! String) { queued=$0 };try wait { queued != nil };_ = try queued!.get()
        var advanced=0,ended=0,seen:[Int]=[]
        controller.event={ event in
            if event["advanced"] as? Bool == true { advanced += 1 }
            if event["ended"] as? Bool == true { ended += 1 }
            if event["playing"] as? Bool == true,let frame=event["frame"] as? Int { seen.append(frame) }
        }
        controller.player.isMuted=true;controller.play()
        try wait({advanced==1 && (seen.last ?? 0)>=next+5},seconds:5)
        controller.pause()
        precondition(ended==0,"The prepared boundary must not end playback")
        precondition(zip(seen,seen.dropFirst()).allSatisfy{$0 <= $1},"Global frame clock went backwards")
        precondition(controller.timeline?.origin==next)
        var sought=false;controller.seek(next+2){sought=true};try wait{sought}
        precondition(abs(controller.player.currentTime().seconds*controller.timeline!.fps-2)<0.05)
        // Discarding an old queue never replaces the current, reusable item.
        let current=controller.timeline;controller.discardQueued();precondition(controller.timeline === current)
        var stale:Result<[String:Any],Error>?
        controller.queue(second,afterKey:"obsolete-key"){stale=$0}
        if case .success? = stale { preconditionFailure("Stale queue accepted") }
        controller.play();try wait({ended==1},seconds:5)
        precondition(controller.player.currentItem === current?.item,"Final item must remain seekable")
        var replay=false;controller.seek(next){replay=true};try wait{replay}
        controller.play();try wait{controller.player.currentTime().seconds>0.1};controller.pause()
        controller.stop()
        print("PASS native progressive queue: seamless boundary, global clock, exact seek, stale queue rejected, end and replay")
    }
}
