import AppKit
import AVFoundation

@main struct NativeVideoCompositorCheck {
    static func main()throws {
        let path=URL(fileURLWithPath:CommandLine.arguments[1]),folder=path.deletingLastPathComponent()
        let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:path)) as! [String:Any]
        let started=Date(),timeline=try PlaybackTimeline.build(plan)
        precondition(timeline.item.videoComposition!.isValid(for:timeline.item.asset,timeRange:CMTimeRange(start:.zero,duration:timeline.item.asset.duration),validationDelegate:nil),"Invalid video composition")
        if path.deletingLastPathComponent().lastPathComponent == "neutral" {
            for (numerator,denominator) in [(30,1),(30000,1001),(24000,1001),(60,1)] {
                var candidate=plan
                let lengths=Array(repeating:53,count:44)+[4,53,31,47]
                let source=(plan["clips"] as! [[String:Any]])[0]["path"]!
                candidate["clips"]=lengths.map { ["path":source,"sourceIn":0,"length":$0] as [String:Any] }
                candidate["frames"]=lengths.reduce(0,+);candidate["fpsNum"]=numerator;candidate["fpsDen"]=denominator
                let result=try PlaybackTimeline.build(candidate),video=result.item.videoComposition!
                precondition(video.isValid(for:result.item.asset,timeRange:CMTimeRange(start:.zero,duration:result.item.asset.duration),validationDelegate:nil),"Arbitrary cuts invalid at \(numerator)/\(denominator)")
                for (a,b) in zip(video.instructions,video.instructions.dropFirst()) { precondition(CMTimeCompare(CMTimeRangeGetEnd(a.timeRange),b.timeRange.start)==0,"Instruction gap or overlap") }
            }
            print("PASS rational timeline boundaries: arbitrary48cuts at30,29.97,23.976 and60fps")
        }
        if plan["testOrientation"] as? Bool == true {
            let instructions=timeline.item.videoComposition!.instructions.compactMap { $0 as? PlaybackVideoInstruction }
            precondition(instructions.flatMap { $0.spans }.contains { !$0.transform.isIdentity },"Orientation fixture has no rotation metadata")
        }
        let reader=try AVAssetReader(asset:timeline.item.asset)
        let output=AVAssetReaderVideoCompositionOutput(videoTracks:timeline.item.asset.tracks(withMediaType:.video),videoSettings:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA])
        output.videoComposition=timeline.item.videoComposition;reader.add(output)
        let requested=Set(plan["testFrames"] as! [Int]);var seen=Set<Int>()
        precondition(reader.startReading(),"Reader did not start: \(String(describing:reader.error))")
        var count=0
        while let sample=output.copyNextSampleBuffer() {
            let frame=Int((CMSampleBufferGetPresentationTimeStamp(sample).seconds*timeline.fps).rounded())
            if requested.contains(frame),let buffer=CMSampleBufferGetImageBuffer(sample) {
                let ci=CIImage(cvPixelBuffer:buffer),context=CIContext(options:[.workingColorSpace:NSNull()])
                let image=context.createCGImage(ci,from:ci.extent)!,bitmap=NSBitmapImageRep(cgImage:image)
                try bitmap.representation(using:.png,properties:[:])!.write(to:folder.appendingPathComponent("native-\(frame).png"))
                seen.insert(frame)
            }
            count+=1
        }
        precondition(reader.status == .completed,"Reader failed: \(String(describing:reader.error))")
        precondition(seen == requested,"Missing snapshots: \(requested.subtracting(seen))")
        precondition(count == timeline.frames,"Expected \(timeline.frames) frames, got \(count)")
        print("PASS native video compositor: \(count) frames, \(seen.count) snapshots, \(timeline.item.asset.tracks(withMediaType:.video).count) composition tracks, \(Date().timeIntervalSince(started))s")
    }
}
