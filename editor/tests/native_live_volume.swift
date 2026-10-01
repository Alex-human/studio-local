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
@main struct Check {
 static func main()throws{
  let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
  let c=PlaybackController();var done=false
  c.load(plan,frame:0){_ in done=true}
  let limit=Date().addingTimeInterval(10)
  while !done && Date()<limit{RunLoop.main.run(until:Date().addingTimeInterval(0.01))};precondition(done)
  let ids=(plan["audioSources"] as! [[String:Any]]).map{$0["id"] as! String}
  c.timeline!.gains.forEach { $0.observe = { probe.add($0) } }
  let item=c.player.currentItem!;c.player.volume=0
  var results:[[String:Any]]=[];var baseline=0.0
  for gain in [1.0,0.25,0.0,0.5] {
    c.setVolumes(Dictionary(uniqueKeysWithValues:ids.map{($0,gain)}),key:plan["key"] as! String)
    c.play()
    RunLoop.main.run(until:Date().addingTimeInterval(1.3));probe.reset()
    RunLoop.main.run(until:Date().addingTimeInterval(1.0))
    let measured=probe.result();precondition(measured["samples"]!>10000)
    if gain==1 {baseline=measured["rms"]!;precondition(baseline>0.0001)}
    if CommandLine.arguments.contains("--different-sources") {
      if gain>0 {precondition(measured["rms"]!>0.0001)}
    } else {precondition(abs(measured["rms"]!/baseline-gain)<0.005)}
    if gain==0 {precondition(measured["rms"]==0)}
    precondition(c.player.currentItem===item && c.player.rate==1)
    results.append(["gain":gain,"measured":measured,"position":c.player.currentTime().seconds])
  }
  c.stop();print(String(data:try JSONSerialization.data(withJSONObject:results,options:[.prettyPrinted,.sortedKeys]),encoding:.utf8)!)
 }
}
