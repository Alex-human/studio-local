import AppKit
import AVFoundation

final class FlippedHost: NSView { override var isFlipped: Bool { true } }

@main struct PlaybackCheck {
    static func main() throws {
        let controller=PlaybackController()
        let host=NSView(frame:NSRect(x:0,y:0,width:800,height:700));host.addSubview(controller.view)
        controller.position(["x":10,"y":20,"width":100,"height":30],height:700)
        precondition(controller.view.frame.minY == 650)
        let flipped=FlippedHost(frame:host.frame);flipped.addSubview(controller.view)
        controller.position(["x":10,"y":20,"width":100,"height":30],height:700)
        precondition(controller.view.frame.minY == 20)
        let planURL=URL(fileURLWithPath:CommandLine.arguments[1])
        let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:planURL)) as! [String:Any]
        let started=Date()
        let timeline=try PlaybackTimeline.build(plan)
        let buildTime=Date().timeIntervalSince(started)
        fputs("BUILT \(buildTime)\n",stderr)
        guard timeline.item.videoComposition!.isValid(for:timeline.item.asset,timeRange:CMTimeRange(start:.zero,duration:timeline.item.asset.duration),validationDelegate:nil) else {throw PlaybackFailure(message:"Invalid frame coverage")}
        let player=AVPlayer(playerItem:timeline.item);player.isMuted=true
        let output=AVPlayerItemVideoOutput(pixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA])
        timeline.item.add(output)
        var readyTime:Double?;var firstTime:Double?;var seeked=false;var frameCount=0
        let frame=CommandLine.arguments.count>2 ? Int(CommandLine.arguments[2])! : 0
        let target=CMTime(seconds:Double(frame)/timeline.fps,preferredTimescale:60000)
        let timeout=Date().addingTimeInterval(12)
        while Date()<timeout {
            RunLoop.main.run(until:Date().addingTimeInterval(0.01))
            if timeline.item.status == .failed {fputs("PLAYER FAILURE \(String(describing:timeline.item.error))\n",stderr);exit(2)}
            if timeline.item.status == .readyToPlay && readyTime==nil {
                readyTime=Date().timeIntervalSince(started)
                player.seek(to:target,toleranceBefore:.zero,toleranceAfter:.zero){done in seeked=done;player.play()}
            }
            if seeked {
                let time=player.currentTime()
                if output.hasNewPixelBuffer(forItemTime:time),let buffer=output.copyPixelBuffer(forItemTime:time,itemTimeForDisplay:nil) {
                    _=CVPixelBufferGetWidth(buffer);frameCount+=1
                    if firstTime==nil{firstTime=Date().timeIntervalSince(started)}
                    if frameCount>=3{break}
                }
            }
        }
        player.pause()
        if CommandLine.arguments.count>3 {
            let generator=AVAssetImageGenerator(asset:timeline.item.asset);generator.videoComposition=timeline.item.videoComposition
            generator.requestedTimeToleranceBefore = .zero;generator.requestedTimeToleranceAfter = .zero
            let cg=try generator.copyCGImage(at:target,actualTime:nil)
            let bitmap=NSBitmapImageRep(cgImage:cg)
            try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:CommandLine.arguments[3]))
        }
        let result:[String:Any]=["buildSeconds":buildTime,"readySeconds":readyTime ?? -1,"firstFrameSeconds":firstTime ?? -1,"framesObserved":frameCount,"frame":frame,"playerSeconds":player.currentTime().seconds,"duration":timeline.item.duration.seconds,"expectedDuration":Double(timeline.frames)/timeline.fps]
        print(String(data:try JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]),encoding:.utf8)!)
        if frameCount<3 {exit(1)}
    }
}
