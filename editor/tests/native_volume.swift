import AppKit
import AVFoundation

@main struct NativeVolumeCheck {
    static func samples(_ timeline: PlaybackTimeline) throws -> [Float] {
        let reader = try AVAssetReader(asset: timeline.item.asset)
        let output = AVAssetReaderAudioMixOutput(audioTracks: timeline.item.asset.tracks(withMediaType:.audio), audioSettings:[
            AVFormatIDKey:kAudioFormatLinearPCM, AVSampleRateKey:48000, AVNumberOfChannelsKey:2,
            AVLinearPCMBitDepthKey:32, AVLinearPCMIsFloatKey:true, AVLinearPCMIsNonInterleaved:false])
        output.audioMix = timeline.item.audioMix; reader.add(output)
        guard reader.startReading() else { throw reader.error! }
        var data = Data()
        while let sample = output.copyNextSampleBuffer() {
            let block = CMSampleBufferGetDataBuffer(sample)!; var length=0; var pointer:UnsafeMutablePointer<Int8>?
            precondition(CMBlockBufferGetDataPointer(block,atOffset:0,lengthAtOffsetOut:nil,totalLengthOut:&length,dataPointerOut:&pointer)==noErr)
            data.append(Data(bytes:pointer!,count:length))
        }
        guard reader.status == .completed else {throw reader.error!}
        return data.withUnsafeBytes {Array($0.bindMemory(to:Float.self))}
    }
    static func main() throws {
        let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
        let timeline=try PlaybackTimeline.build(plan)
        let ids=(plan["audioSources"] as! [[String:Any]]).map{$0["id"] as! String}
        var maxError:Float=0
        for id in ids {
            var levels=Dictionary(uniqueKeysWithValues:ids.map{($0,0.0)});levels[id]=1;timeline.setVolumes(levels)
            let full=try samples(timeline)
            for gain in [0.5,0.25,0.0] {
                levels[id]=gain;timeline.setVolumes(levels);let current=try samples(timeline)
                precondition(current.count==full.count)
                let difference=zip(current,full).map{abs($0-Float(gain)*$1)}.max()!
                maxError=max(maxError,difference);precondition(difference<0.000001)
                if gain==0 {precondition(current.allSatisfy{$0==0})}
            }
        }
        let controller=PlaybackController();var loaded=false;var failure:Error?
        controller.load(plan,frame:0){result in switch result {case .success:loaded=true;case .failure(let error):failure=error}}
        let deadline=Date().addingTimeInterval(8)
        while !loaded && failure==nil && Date()<deadline {RunLoop.main.run(until:Date().addingTimeInterval(0.01))}
        if let failure=failure {throw failure};precondition(loaded)
        let item=controller.player.currentItem!;controller.play()
        RunLoop.main.run(until:Date().addingTimeInterval(0.15));let first=controller.player.currentTime().seconds
        controller.setVolumes(Dictionary(uniqueKeysWithValues:ids.map{($0,0.25)}),key:timeline.key)
        RunLoop.main.run(until:Date().addingTimeInterval(0.15))
        precondition(controller.player.currentItem===item && controller.player.rate==1 && controller.player.currentTime().seconds>first)
        controller.pause()
        loaded=false
        controller.load(plan,frame:0){result in switch result {case .success:loaded=true;case .failure(let error):failure=error}}
        let reloadDeadline=Date().addingTimeInterval(8)
        while !loaded && failure==nil && Date()<reloadDeadline {RunLoop.main.run(until:Date().addingTimeInterval(0.01))}
        if let failure=failure {throw failure};precondition(loaded)
        precondition(controller.player.currentItem===item && controller.timeline!.volumes.isEmpty)
        let restored=try samples(controller.timeline!),original=try samples(try PlaybackTimeline.build(plan))
        precondition(restored==original)
        print("{\"nativeLevels\":[100,50,25,0],\"sources\":\(ids.count),\"maxSampleError\":\(maxError),\"zeroIsDigitalSilence\":true,\"playingItemPreserved\":true,\"reuseRestored\":true}")
    }
}
