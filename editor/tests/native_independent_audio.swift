import AppKit
import AVFoundation
import MediaToolbox
final class Probe {
    let lock=NSLock(); var total=0.0; var count=0
    func add(_ data:UnsafeMutablePointer<AudioBufferList>) {
        lock.lock();defer{lock.unlock()}
        for b in UnsafeMutableAudioBufferListPointer(data) {
            guard let raw=b.mData else{continue}
            let values=raw.assumingMemoryBound(to:Float.self)
            for i in 0..<Int(b.mDataByteSize)/4 {let v=Double(values[i]);total+=v*v;count+=1}
        }
    }
    func reset(){lock.lock();total=0;count=0;lock.unlock()}
    func result()->[String:Double]{lock.lock();defer{lock.unlock()};return ["rms":sqrt(total/Double(max(1,count))),"samples":Double(count)]}
}
let probe=Probe()

@main struct IndependentReview {
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

static func spin(_ seconds:Double){RunLoop.main.run(until:Date().addingTimeInterval(seconds))}
static func wait(_ check:()->Bool){let end=Date().addingTimeInterval(10);while !check() && Date()<end {spin(0.01)};precondition(check())}
static func main()throws {
 setbuf(stdout,nil)
 let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
 let ids=(plan["audioSources"] as! [[String:Any]]).map{$0["id"] as! String}
 let timeline=try PlaybackTimeline.build(plan)
 let fullLevels=Dictionary(uniqueKeysWithValues:ids.map{($0,1.0)})
 timeline.setVolumes(fullLevels);let full=try samples(timeline)
 var levels=fullLevels;levels["c0"]=0;levels["c1"]=0.25;levels["c2"]=0.5;levels["c3"]=1
 timeline.setVolumes(levels);let adjusted=try samples(timeline)
 precondition(full.count==adjusted.count && full.count==16*48000*2)
 var errors:[Double]=[]
 for i in 0..<4 {
  let a=i*4*48000*2,b=(i+1)*4*48000*2,expected=Float(levels[ids[i]]!)
  let error=zip(adjusted[a..<b],full[a..<b]).map{abs($0-expected*$1)}.max()!
  errors.append(Double(error));let diffs=zip(adjusted[a..<b],full[a..<b]).map{abs($0-expected*$1)}
  print("section \(i) fullRMS \(sqrt(full[a..<b].reduce(0.0){$0+Double($1*$1)}/Double(b-a))) adjustedRMS \(sqrt(adjusted[a..<b].reduce(0.0){$0+Double($1*$1)}/Double(b-a))) maxIndex \(diffs.firstIndex(of:error)!) error \(error)")
  if expected==0 {print("zeroCountNonzero",adjusted[a..<b].filter{$0 != 0}.count)}
 }
 print("reader samples=\(full.count) errors=\(errors)")
 let c=PlaybackController();c.player.volume=0;var done=false;var failure:Error?
 c.load(plan,frame:0){r in if case .failure(let e)=r {failure=e};done=true};wait{done};if let e=failure {throw e}
 let item=c.player.currentItem!;var results:[[String:Any]]=[]
 for i in [0,1,2,3,1,0] {
  c.setVolumes(fullLevels,key:plan["key"] as! String)
  c.timeline!.gains.forEach{ $0.observe = nil };c.timeline!.gains.first{$0.spans.contains{$0.id==ids[i]}}!.observe = {probe.add($0)}
  done=false;c.seek(i*4*30+15){done=true};wait{done};c.play();spin(0.75);probe.reset();spin(0.3)
  let baseline=probe.result();precondition(baseline["samples"]!>1000 && baseline["rms"]!>0.0001)
  for gain in [0.0,0.25] {
   var live=fullLevels;live[ids[i]]=gain;c.setVolumes(live,key:plan["key"] as! String)
   spin(0.5);probe.reset();spin(0.3)
   let r=probe.result();let ratio=r["rms"]!/baseline["rms"]!
   precondition(r["samples"]!>1000);precondition(abs(ratio-gain)<0.005,"Live independence \(ids[i]) gain \(gain) ratio \(ratio)")
   if gain==0 {precondition(r["rms"]==0)}
   precondition(c.player.currentItem===item && c.player.rate==1)
   results.append(["id":ids[i],"gain":gain,"ratio":ratio,"position":c.player.currentTime().seconds])
  }
 }
 c.pause();done=false;c.load(plan,frame:0){r in if case .failure(let e)=r{failure=e};done=true};wait{done};if let e=failure{throw e}
 precondition(c.player.currentItem===item && c.timeline!.volumes.isEmpty)
 let restored=try samples(c.timeline!);let original=try samples(try PlaybackTimeline.build(plan))
 let restoreError=zip(restored,original).map{abs($0-$1)}.max()!;print("restore maxError",restoreError);precondition(restoreError<0.000001,"undo restore failed")
 c.stop()
 print(String(data:try JSONSerialization.data(withJSONObject:results,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
 print("PASS independent adjacent same-path clips, source discontinuities, 44.1k stereo + 48k mono, live zero+25%, backward seeks, original levels restore, frame count")
}
}
