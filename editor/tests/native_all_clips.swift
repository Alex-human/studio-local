import AppKit
import AVFoundation

@main struct AllClipAudioCheck {
    static func samples(_ timeline:PlaybackTimeline)throws->[Float]{
        let reader=try AVAssetReader(asset:timeline.item.asset)
        let out=AVAssetReaderAudioMixOutput(audioTracks:timeline.item.asset.tracks(withMediaType:.audio),audioSettings:[AVFormatIDKey:kAudioFormatLinearPCM,AVSampleRateKey:48000,AVNumberOfChannelsKey:2,AVLinearPCMBitDepthKey:32,AVLinearPCMIsFloatKey:true,AVLinearPCMIsNonInterleaved:false])
        out.audioMix=timeline.item.audioMix;reader.add(out);precondition(reader.startReading())
        // Compressed decodes can emit different padding around the requested range.
        // Compare samples on the composition clock, not concatenated decoder buffers.
        let count=Int((timeline.item.asset.duration.seconds*48000).rounded())*2
        var result=Array(repeating:Float(0),count:count)
        var decodedSamples=0
        while let sample=out.copyNextSampleBuffer(){
            let block=CMSampleBufferGetDataBuffer(sample)!;var n=0;var raw:UnsafeMutablePointer<Int8>?
            precondition(CMBlockBufferGetDataPointer(block,atOffset:0,lengthAtOffsetOut:nil,totalLengthOut:&n,dataPointerOut:&raw)==noErr)
            let start=Int((CMSampleBufferGetPresentationTimeStamp(sample).seconds*48000).rounded())*2
            let decoded=UnsafeRawBufferPointer(start:raw!,count:n).bindMemory(to:Float.self)
            let first=max(0,-start),last=min(decoded.count,count-start)
            if last>first {decodedSamples+=last-first;for i in first..<last {result[start+i]=decoded[i]}}
        }
        precondition(reader.status == .completed,"Audio decode failed")
        precondition(decodedSamples>0,"No decoded audio inside the composition")
        return result
    }
    static func main()throws{
        setbuf(stdout,nil)
        let source=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
        let blue=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[2]))) as! [String:Any]
        var result:[[String:Any]]=[]
        for (index,original) in (source["audioSources"] as! [[String:Any]]).enumerated(){
            try autoreleasepool{
                var item=original;let id=item["id"] as! String
                let total=(item["length"] as! NSNumber).doubleValue
                let length=min(0.6,total),offset=max(0,min(total/3,total-length))
                item["start"]=0.0;item["source"]=(item["source"] as! NSNumber).doubleValue+offset*(item["speed"] as! NSNumber).doubleValue
                item["length"]=length;item["fadeIn"]=0.0;item["fadeOut"]=0.0;item["fadeOffset"]=0.0;item["fadeLength"]=length
                var plan=blue;let frames=Int(ceil(length*(blue["fps"] as! NSNumber).doubleValue))
                var clip=(blue["clips"] as! [[String:Any]])[0];clip["length"]=frames;plan["clips"]=[clip];plan["frames"]=frames;plan["audioSources"]=[item];plan["audioCues"]=[];plan["images"]=[]
                let timeline=try PlaybackTimeline.build(plan);timeline.setVolumes([id:1]);let full=try samples(timeline)
                precondition(!full.isEmpty)
                timeline.setVolumes([id:0.25]);let quarter=try samples(timeline)
                precondition(quarter.count==full.count,"Composition timing changed for \(id)")
                let error=zip(full,quarter).map{abs($0*0.25-$1)}.max() ?? 0
                let fullRms=sqrt(full.reduce(0.0){$0+Double($1)*Double($1)}/Double(full.count))
                let quarterRms=sqrt(quarter.reduce(0.0){$0+Double($1)*Double($1)}/Double(quarter.count))
                // Independent compressed decodes can differ in resampling priming.
                // Exact PCM proportionality is covered by native_volume's lossless fixture.
                if fullRms>0.00001 {precondition(abs(quarterRms/fullRms-0.25)<0.005,"Gain failed for \(id): \(quarterRms/fullRms)")}
                timeline.setVolumes([id:0]);let zero=try samples(timeline);precondition(zero.allSatisfy{$0==0},"Zero was audible for \(id)")
                let rms=sqrt(full.reduce(0.0){$0+Double($1)*Double($1)}/Double(full.count))
                result.append(["id":id,"role":original["role"] ?? "audio","rmsAt100":rms,"maxErrorAt25":error,"zero":true,"samples":full.count])
                try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[3]))
                print("checked",index+1,id,"rms",rms)
            }
        }
        try JSONSerialization.data(withJSONObject:result,options:[.prettyPrinted,.sortedKeys]).write(to:URL(fileURLWithPath:CommandLine.arguments[3]))
        print("PASS",result.count,"clips")
    }
}
