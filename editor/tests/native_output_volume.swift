// Opt-in final-output regression: capture only this disposable test process.
import AppKit
import AVFoundation
import ScreenCaptureKit
final class Output: NSObject,SCStreamOutput {
 let lock=NSLock();var rows:[[Double]]=[];var epoch=0.0
 func stream(_ stream:SCStream,didOutputSampleBuffer sampleBuffer:CMSampleBuffer,of type:SCStreamOutputType) {
  guard type == .audio,CMSampleBufferIsValid(sampleBuffer) else{return}
  var size=0;var block:CMBlockBuffer?
  CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer,bufferListSizeNeededOut:&size,bufferListOut:nil,bufferListSize:0,blockBufferAllocator:nil,blockBufferMemoryAllocator:nil,flags:0,blockBufferOut:&block)
  let raw=UnsafeMutableRawPointer.allocate(byteCount:size,alignment:16);defer{raw.deallocate()};let list=raw.assumingMemoryBound(to:AudioBufferList.self)
  guard CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sampleBuffer,bufferListSizeNeededOut:nil,bufferListOut:list,bufferListSize:size,blockBufferAllocator:nil,blockBufferMemoryAllocator:nil,flags:0,blockBufferOut:&block)==noErr else{return}
  var square=0.0,n=0
  for b in UnsafeMutableAudioBufferListPointer(list) {guard let data=b.mData else{continue};let values=data.assumingMemoryBound(to:Float.self);for i in 0..<Int(b.mDataByteSize)/4{let v=Double(values[i]);square+=v*v;n+=1}}
  lock.lock();rows.append([CMSampleBufferGetPresentationTimeStamp(sampleBuffer).seconds-epoch,sqrt(square/Double(max(1,n))),Double(n)]);lock.unlock()
 }
}
@main struct Check {
 static func spin(_ n:Double){RunLoop.main.run(until:Date().addingTimeInterval(n))}
 static func wait(_ f:()->Bool){let end=Date().addingTimeInterval(10);while !f() && Date()<end{spin(0.01)};precondition(f())}
 static func main()throws{
  guard CGPreflightScreenCaptureAccess() else {throw PlaybackFailure(message:"This opt-in test needs Screen Recording access to measure its own audio output.")}
  setbuf(stdout,nil);_ = NSApplication.shared;let window=NSWindow(contentRect:NSRect(x:-1000,y:-1000,width:20,height:20),styleMask:[.borderless],backing:.buffered,defer:false);window.orderBack(nil);defer{window.close()};spin(0.2)
  var content:SCShareableContent?;SCShareableContent.getExcludingDesktopWindows(true,onScreenWindowsOnly:false){c,e in content=c};wait{content != nil}
  let app=content!.applications.first{$0.processID==ProcessInfo.processInfo.processIdentifier}!;let filter=SCContentFilter(display:content!.displays[0],including:[app],exceptingWindows:[])
  let config=SCStreamConfiguration();config.width=2;config.height=2;config.minimumFrameInterval=CMTime(value:1,timescale:1);config.capturesAudio=true;config.excludesCurrentProcessAudio=false;config.sampleRate=48000;config.channelCount=2
  let output=Output();let stream=SCStream(filter:filter,configuration:config,delegate:nil);try stream.addStreamOutput(output,type:.audio,sampleHandlerQueue:DispatchQueue(label:"audio-result"));var capturing=false;stream.startCapture{error in print("capture",error?.localizedDescription ?? "ready");capturing=true};wait{capturing}
  let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any];let c=PlaybackController();var loaded=false;c.load(plan,frame:0){r in print("load",r);loaded=true};wait{loaded}
  c.player.volume=0.1;output.epoch=CACurrentMediaTime()
  var phases:[[String:Any]]=[]
  for (pos,level) in [(140.0,1.0),(900.0,1.0),(140.0,0.25),(900.0,0.0),(900.0,1.0)] {
   let levels=Dictionary(uniqueKeysWithValues:(plan["audioSources"] as! [[String:Any]]).map{($0["id"] as! String,($0["volume"] as! Double)*level)})
   c.setVolumes(levels,key:plan["key"] as! String)
   var sought=false;c.seek(Int(pos*(plan["fps"] as! Double))){sought=true};wait{sought};spin(0.1);output.lock.lock();output.rows=[];output.lock.unlock();c.play();spin(2.5);c.pause();spin(0.3);output.lock.lock();let rows=output.rows;output.lock.unlock();phases.append(["position":pos,"gain":level,"rows":rows]);print("phase",pos,level,rows.count)
  }
  try JSONSerialization.data(withJSONObject:phases).write(to:URL(fileURLWithPath:CommandLine.arguments[2]+"-phases.json"));c.stop();var stopped=false;stream.stopCapture{_ in stopped=true};wait{stopped};output.lock.lock();let rows=output.rows;output.lock.unlock();try JSONSerialization.data(withJSONObject:rows).write(to:URL(fileURLWithPath:CommandLine.arguments[2]));print("captured",rows.count)
 }
}
