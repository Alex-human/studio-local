import AppKit
import AVFoundation
import CoreImage

private func videoNumber(_ values:[String:Any],_ key:String,_ fallback:Double)->Double {
    (values[key] as? NSNumber)?.doubleValue ?? fallback
}

/// Camera .cube tables, parsed once per file. They apply to the decoded values before any
/// adjustment, like the exporter's lut3d; this compositor works without color management.
enum PlaybackColorCube {
    private static let lock=NSLock()
    private static var tables:[String:(Int,Data)]=[:]
    static func table(_ path:String)throws->(Int,Data) {
        lock.lock();defer { lock.unlock() }
        if let table=tables[path] { return table }
        guard let text=try? String(contentsOfFile:path,encoding:.utf8) else { throw PlaybackFailure(message:"No se pudo leer la LUT de color.") }
        var size=0,values:[Float]=[]
        for line in text.split(whereSeparator:\.isNewline) {
            let fields=line.split(whereSeparator:\.isWhitespace)
            guard let first=fields.first,!first.hasPrefix("#") else { continue }
            if first == "LUT_3D_SIZE",fields.count == 2,let n=Int(fields[1]) { size=n;continue }
            let rgb=fields.compactMap { Float($0) }
            guard fields.count == 3,rgb.count == 3 else { throw PlaybackFailure(message:"LUT de color no válida.") }
            values += rgb+[1]
        }
        guard (2...64).contains(size),values.count == size*size*size*4 else { throw PlaybackFailure(message:"LUT de color no válida.") }
        let table=(size,values.withUnsafeBufferPointer { Data(buffer:$0) })
        tables[path]=table;return table
    }
}

final class PlaybackVideoSpan {
    let trackID:CMPersistentTrackID
    let start:Int
    let length:Int
    let spec:[String:Any]
    let transform:CGAffineTransform
    let overlay:Bool
    private let keys:[(String,[(Double,Double)])]
    init(trackID:CMPersistentTrackID,start:Int,length:Int,spec:[String:Any],transform:CGAffineTransform,overlay:Bool) {
        self.trackID=trackID;self.start=start;self.length=length;self.spec=spec;self.transform=transform;self.overlay=overlay
        keys=(spec["keyframes"] as? [String:[[String:Any]]] ?? [:]).map { key,points in
            let values:[(Int,Double,Double)]=points.enumerated().map { index,point in
                (index,videoNumber(point,"frame",0),videoNumber(point,"value",0))
            }
            let sorted=values.sorted { $0.1 == $1.1 ? $0.0 < $1.0 : $0.1 < $1.1 }
            return (key,sorted.map { ($0.1,$0.2) })
        }
    }
    func properties(_ local:Double)->[String:Any] {
        var result=spec["props"] as? [String:Any] ?? [:]
        for (key,points) in keys {
            guard let first=points.first else { continue };var value=first.1
            for (a,b) in zip(points,points.dropFirst()) {
                if local>=b.0 { value=b.1;continue }
                if local>=a.0 { let u=min(1,max(0,(local-a.0)/max(1,b.0-a.0)));value=a.1+(b.1-a.1)*u*u*u*(u*(u*6-15)+10) }
                break
            }
            result[key]=value
        }
        return result
    }
}

final class PlaybackVideoInstruction:NSObject,AVVideoCompositionInstructionProtocol {
    let timeRange:CMTimeRange
    let enablePostProcessing=true
    let containsTweening=true
    let passthroughTrackID=kCMPersistentTrackID_Invalid
    let requiredSourceTrackIDs:[NSValue]?
    let spans:[PlaybackVideoSpan]
    let fps:Double
    init(range:CMTimeRange,spans:[PlaybackVideoSpan],fps:Double) {
        timeRange=range;self.spans=spans;self.fps=fps
        requiredSourceTrackIDs=spans.map { NSNumber(value:$0.trackID) };super.init()
    }
}

/// One composition and one clock: overlays are decoded alongside the base video.
final class PlaybackVideoCompositor:NSObject,AVVideoCompositing {
    var sourcePixelBufferAttributes:[String:Any]? { [kCVPixelBufferPixelFormatTypeKey as String:[kCVPixelFormatType_32BGRA]] }
    var requiredPixelBufferAttributesForRenderContext:[String:Any] { [kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,kCVPixelBufferMetalCompatibilityKey as String:true] }
    private let queue=DispatchQueue(label:"studio.video-compositor",qos:.userInteractive)
    private let lock=NSLock()
    private var generation=0
    private let context=CIContext(options:[.workingColorSpace:NSNull(),.cacheIntermediates:false])
    private let colorSpace=CGColorSpace(name:CGColorSpace.sRGB)!
    func renderContextChanged(_ newRenderContext:AVVideoCompositionRenderContext) {}
    func cancelAllPendingVideoCompositionRequests() { lock.lock();generation+=1;lock.unlock() }
    func startRequest(_ request:AVAsynchronousVideoCompositionRequest) {
        lock.lock();let token=generation;lock.unlock()
        queue.async { autoreleasepool {
            self.lock.lock();let canceled=token != self.generation;self.lock.unlock()
            if canceled { request.finishCancelledRequest();return }
            guard let instruction=request.videoCompositionInstruction as? PlaybackVideoInstruction,
                  let buffer=request.renderContext.newPixelBuffer() else {
                request.finish(with:PlaybackFailure(message:"No se pudo preparar un fotograma del vídeo."));return
            }
            let size=request.renderContext.size,rect=CGRect(origin:.zero,size:size)
            let frame=request.compositionTime.seconds*instruction.fps
            var result=CIImage(color:CIColor(red:0,green:0,blue:0)).cropped(to:rect)
            for span in instruction.spans {
                guard let source=request.sourceFrame(byTrackID:span.trackID) else {
                    request.finish(with:PlaybackFailure(message:"No se pudo decodificar una capa de vídeo."));return
                }
                var image=CIImage(cvPixelBuffer:source).transformed(by:span.transform)
                image=image.transformed(by:CGAffineTransform(translationX:-image.extent.minX,y:-image.extent.minY))
                do {
                    if let path=span.spec["lut"] as? String {
                        let (size,data)=try PlaybackColorCube.table(path)
                        image=image.applyingFilter("CIColorCube",parameters:["inputCubeDimension":size,"inputCubeData":data])
                    }
                    image=span.overlay ? self.overlay(image,span:span,frame:frame,fps:instruction.fps,size:size) : try self.base(image,span:span,frame:frame,size:size)
                } catch { request.finish(with:error);return }
                result=image.composited(over:result).cropped(to:rect)
            }
            self.context.render(result,to:buffer,bounds:rect,colorSpace:self.colorSpace)
            self.lock.lock();let expired=token != self.generation;self.lock.unlock()
            if expired { request.finishCancelledRequest() } else { request.finish(withComposedVideoFrame:buffer) }
        } }
    }
    private func base(_ source:CIImage,span:PlaybackVideoSpan,frame:Double,size:CGSize)throws->CIImage {
        let p=span.spec,x=videoNumber(p,"x",0.5),y=videoNumber(p,"y",0.5)
        let scale=max(size.width/source.extent.width,size.height/source.extent.height)
        var image=source.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
        image=image.transformed(by:CGAffineTransform(translationX:-(image.extent.width-size.width)*x,y:-(image.extent.height-size.height)*(1-y)))
            .cropped(to:CGRect(origin:.zero,size:size))
        let color=p["color"] as? [String:Any] ?? [:]
        let exposure=videoNumber(color,"exposure",0),contrast=videoNumber(color,"contrast",1),saturation=videoNumber(color,"saturation",1)
        if exposure != 0 || contrast != 1 || saturation != 1 {
            image=image.applyingFilter("CIColorControls",parameters:[kCIInputBrightnessKey:exposure*0.12,kCIInputContrastKey:contrast,kCIInputSaturationKey:saturation])
        }
        let temperature=videoNumber(color,"temperature",0)
        if temperature != 0 {
            guard let kernel=Self.temperatureKernel,
                  let adjusted=kernel.apply(extent:image.extent,arguments:[image,temperature]) else {
                throw PlaybackFailure(message:"No se pudo aplicar la temperatura de color del vídeo.")
            }
            image=adjusted
        }
        let z0=videoNumber(p,"zoom",1),z1=videoNumber(p,"zoomEnd",z0)
        let u=min(1,max(0,(frame-Double(span.start)+videoNumber(p,"motionOffset",0))/max(1,videoNumber(p,"motionLength",Double(span.length))-1)))
        let zoom=max(1,z0+(z1-z0)*u*u*(3-2*u))
        if zoom != 1 {
            image=image.transformed(by:CGAffineTransform(translationX:-(size.width-size.width/zoom)*x,y:-(size.height-size.height/zoom)*(1-y)))
                .transformed(by:CGAffineTransform(scaleX:zoom,y:zoom)).cropped(to:CGRect(origin:.zero,size:size))
        }
        return image
    }
    // FFmpeg colorbalance's shadow/midtone masks, evaluated in display RGB.
    private static let temperatureKernel=CIColorKernel(source:"""
        kernel vec4 temperature(__sample s, float amount) {
            float lightness=max(max(s.r,s.g),s.b)+min(min(s.r,s.g),s.b);
            float shadow=clamp((0.333-lightness)*4.0+0.5,0.0,1.0)*0.7;
            float middle=clamp((lightness-0.333)*4.0+0.5,0.0,1.0)*clamp((1.0-lightness-0.333)*4.0+0.5,0.0,1.0)*0.7;
            float change=amount*(0.12*shadow+0.07*middle);
            return vec4(clamp(s.r+change,0.0,1.0),s.g,clamp(s.b-change,0.0,1.0),s.a);
        }
        """)
    private func overlay(_ source:CIImage,span:PlaybackVideoSpan,frame:Double,fps:Double,size:CGSize)->CIImage {
        let local=frame-Double(span.start)+videoNumber(span.spec,"offset",0),p=span.properties(local),sc=size.width/1920
        let sw=source.extent.width,sh=source.extent.height
        let left=min(sw-1,max(0,(sw*videoNumber(p,"cropLeft",0)).rounded(.toNearestOrEven)))
        let top=min(sh-1,max(0,(sh*videoNumber(p,"cropTop",0)).rounded(.toNearestOrEven)))
        let right=max(left+1,(sw*(1-videoNumber(p,"cropRight",0))).rounded(.toNearestOrEven))
        let bottom=max(top+1,(sh*(1-videoNumber(p,"cropBottom",0))).rounded(.toNearestOrEven))
        var image=source.cropped(to:CGRect(x:left,y:sh-bottom,width:right-left,height:bottom-top))
            .transformed(by:CGAffineTransform(translationX:-left,y:bottom-sh))
        let u=min(1,max(0,local/fps/max(0.01,videoNumber(p,"enter",0.48)))),eased=1-pow(1-u,4)
        let animation=p["animation"] as? String ?? "none"
        var dx=0.0,dy=0.0,scale=1.0,alpha=videoNumber(p,"opacity",1)
        if animation != "none" { alpha *= min(1,u*4) }
        switch animation {
        case "pop":scale=0.88+0.12*eased
        case "from-left":dx = -180*(1-eased)
        case "from-right":dx=180*(1-eased)
        case "from-top":dy = -150*(1-eased)
        case "from-bottom":dy=150*(1-eased)
        default:break
        }
        let iw=max(2,(videoNumber(p,"width",760)*sc*scale).rounded(.toNearestOrEven))
        let ih=max(2,(iw*(bottom-top)/(right-left)).rounded(.toNearestOrEven))
        image=image.transformed(by:CGAffineTransform(scaleX:iw/image.extent.width,y:ih/image.extent.height))
        let photo=(p["style"] as? String ?? "clean")=="photo",pad=photo ? max(2,(12*sc).rounded(.toNearestOrEven)) : 0
        let pw=iw+2*pad,ph=ih+2*pad
        if photo {
            let mask=rounded(CGRect(x:0,y:0,width:iw,height:ih),radius:max(1,8*sc),color:CIColor(red:1,green:1,blue:1))
            image=image.applyingFilter("CIBlendWithAlphaMask",parameters:[kCIInputBackgroundImageKey:CIImage.empty(),kCIInputMaskImageKey:mask])
                .transformed(by:CGAffineTransform(translationX:pad,y:pad))
            let panel=rounded(CGRect(x:0,y:0,width:pw,height:ph),radius:max(2,18*sc),color:CIColor(red:246/255,green:247/255,blue:250/255))
            image=image.composited(over:panel)
        }
        let angle=videoNumber(p,"rotation",0)*Double.pi/180
        image=image.transformed(by:CGAffineTransform(translationX:-pw/2,y:-ph/2))
            .transformed(by:CGAffineTransform(rotationAngle:-angle))
        image=image.transformed(by:CGAffineTransform(translationX:(videoNumber(p,"x",960)+dx)*sc,y:size.height-(videoNumber(p,"y",540)+dy)*sc))
        if photo {
            let shadow=image.applyingFilter("CIColorMatrix",parameters:["inputRVector":CIVector(x:0,y:0,z:0,w:0),"inputGVector":CIVector(x:0,y:0,z:0,w:0),"inputBVector":CIVector(x:0,y:0,z:0,w:0),"inputAVector":CIVector(x:0,y:0,z:0,w:0.32)])
                .transformed(by:CGAffineTransform(translationX:0,y:-12*sc)).applyingGaussianBlur(sigma:max(1,18*sc))
            image=image.composited(over:shadow)
        }
        return image.applyingFilter("CIColorMatrix",parameters:["inputAVector":CIVector(x:0,y:0,z:0,w:max(0,min(1,alpha)))])
    }
    private func rounded(_ rect:CGRect,radius:Double,color:CIColor)->CIImage {
        CIFilter(name:"CIRoundedRectangleGenerator",parameters:["inputExtent":CIVector(cgRect:rect),"inputRadius":radius,"inputColor":color])!.outputImage!
    }
}

struct PlaybackVideoBuilder {
    static func build(_ plan:[String:Any],composition:AVMutableComposition,store:PlaybackAssetStore)throws->(AVMutableVideoComposition,[String:AVURLAsset]) {
        let clips=plan["clips"] as! [[String:Any]],frames=plan["frames"] as! Int,width=plan["width"] as! Int,height=plan["height"] as! Int
        let numerator=plan["fpsNum"] as! Int,denominator=plan["fpsDen"] as! Int
        let fps=Double(numerator)/Double(denominator)
        func time(_ frames:Double)->CMTime {
            // Timeline boundaries are rational frame counts. Going through seconds
            // can truncate a boundary by one tick and invalidate the whole composition.
            if frames == frames.rounded() { return CMTime(value:Int64(frames)*Int64(denominator),timescale:Int32(numerator)) }
            return CMTime(value:Int64((frames/fps*600000).rounded()),timescale:600000)
        }
        var sources:[String:AVAssetTrack]=[:],assets:[String:AVURLAsset]=[:],spans:[PlaybackVideoSpan]=[]
        var lanes:[(track:AVMutableCompositionTrack,end:Int)]=[]
        func insert(_ spec:[String:Any],start:Int,overlay:Bool)throws {
            guard let path=spec["path"] as? String,let length=spec["length"] as? Int,length>0 else { throw PlaybackFailure(message:"Clip de reproducción no válido.") }
            let source:AVAssetTrack
            if let cached=sources[path] { source=cached }
            else {
                let asset=store.asset(path);assets[path]=asset
                guard let track=asset.tracks(withMediaType:.video).first else { throw PlaybackFailure(message:"No se puede leer el vídeo: "+URL(fileURLWithPath:path).lastPathComponent) }
                source=track;sources[path]=track
            }
            let speed=videoNumber(spec,"speed",1),sourceIn=videoNumber(spec,"sourceIn",0)
            guard speed>0,sourceIn>=0 else { throw PlaybackFailure(message:"El tramo de vídeo no es válido.") }
            let lane:Int
            if let existing=lanes.firstIndex(where:{$0.end<=start}) { lane=existing }
            else {
                guard let track=composition.addMutableTrack(withMediaType:.video,preferredTrackID:kCMPersistentTrackID_Invalid) else { throw PlaybackFailure(message:"No se pudo crear una pista de vídeo.") }
                track.naturalTimeScale=600000
                lanes.append((track,0));lane=lanes.count-1
            }
            let track=lanes[lane].track,at=time(Double(start)),duration=time(Double(length))
            // AVFoundation can choose the preceding sample at exact retimed boundaries.
            // One composition tick breaks that numerical tie without shifting a frame.
            let sourceStart=CMTimeAdd(time(sourceIn),overlay ? CMTime(value:1,timescale:600000) : .zero)
            let sourceEnd=CMTimeRangeGetEnd(source.timeRange)
            let available=CMTimeSubtract(sourceEnd,sourceStart)
            let requested=time(Double(length)*speed)
            let inputDuration=overlay ? CMTimeMinimum(requested,available) : requested
            // Validation accepts an overlay up to one frame longer than its file (a rounded
            // length) and the exporter holds its last frame there. Only more is an error.
            let missing=CMTimeSubtract(requested,inputDuration).seconds
            guard inputDuration.seconds>0,missing<1/fps+0.00001 else { throw PlaybackFailure(message:"El tramo de vídeo queda fuera de su archivo.") }
            func scaled(_ value:CMTime)->CMTime { CMTimeConvertScale(CMTimeMultiplyByFloat64(value,multiplier:1/speed),timescale:600000,method:.roundHalfAwayFromZero) }
            // Media runs until `covered`; past it the file's last millisecond is stretched,
            // keeping the source clock unscaled.
            let covered=missing<0.00001 ? duration : scaled(inputDuration)
            // A file can open with an empty edit (encoder delay): its first picture arrives a few
            // milliseconds after zero and the gap has no frame. Stretch its first millisecond over
            // that gap, as the exporter holds it.
            let mediaStart=CMTimeAdd(source.segments.first { !$0.isEmpty }?.timeMapping.target.start ?? source.timeRange.start,overlay ? CMTime(value:1,timescale:600000) : .zero)
            let lead=CMTimeClampToRange(CMTimeSubtract(mediaStart,sourceStart),range:CMTimeRange(start:.zero,duration:inputDuration))
            let body=CMTimeSubtract(inputDuration,lead)
            do {
                var position=at
                if CMTimeCompare(lead,.zero)>0 {
                    let first=CMTimeMinimum(CMTime(value:1,timescale:1000),CMTimeSubtract(sourceEnd,mediaStart))
                    let held=CMTimeCompare(body,.zero)>0 ? CMTimeMinimum(scaled(lead),covered) : covered
                    try track.insertTimeRange(CMTimeRange(start:mediaStart,duration:first),of:source,at:at)
                    track.scaleTimeRange(CMTimeRange(start:at,duration:first),toDuration:held)
                    position=CMTimeAdd(at,held)
                }
                if CMTimeCompare(body,.zero)>0 {
                    try track.insertTimeRange(CMTimeRange(start:CMTimeAdd(sourceStart,lead),duration:body),of:source,at:position)
                    let rest=CMTimeSubtract(CMTimeAdd(at,covered),position)
                    if CMTimeCompare(body,rest) != 0 { track.scaleTimeRange(CMTimeRange(start:position,duration:body),toDuration:rest) }
                }
                if missing>=0.00001 {
                    let last=CMTimeMinimum(inputDuration,CMTime(value:1,timescale:1000)),holdAt=CMTimeAdd(at,covered)
                    try track.insertTimeRange(CMTimeRange(start:CMTimeSubtract(sourceEnd,last),duration:last),of:source,at:holdAt)
                    track.scaleTimeRange(CMTimeRange(start:holdAt,duration:last),toDuration:CMTimeSubtract(CMTimeAdd(at,duration),holdAt))
                }
            } catch { throw PlaybackFailure(message:"Vídeo \(URL(fileURLWithPath:path).lastPathComponent): \(error)") }
            lanes[lane].end=start+length
            // Track transforms use top-left video coordinates; Core Image uses bottom-left.
            let t=source.preferredTransform
            let oriented=CGAffineTransform(a:t.a,b:-t.b,c:-t.c,d:t.d,tx:t.tx,ty:-t.ty)
            spans.append(PlaybackVideoSpan(trackID:track.trackID,start:start,length:length,spec:spec,transform:oriented,overlay:overlay))
        }
        var position=0
        for spec in clips { try insert(spec,start:position,overlay:false);position += spec["length"] as! Int }
        guard position==frames else { throw PlaybackFailure(message:"La duración del reproductor no coincide con el montaje.") }
        for spec in plan["videoOverlays"] as? [[String:Any]] ?? [] { try insert(spec,start:Int(videoNumber(spec,"start",0)),overlay:true) }
        let video=AVMutableVideoComposition();video.renderSize=CGSize(width:width,height:height)
        video.frameDuration=CMTime(value:Int64(plan["fpsDen"] as! Int),timescale:Int32(plan["fpsNum"] as! Int))
        video.customVideoCompositorClass=PlaybackVideoCompositor.self
        let cuts=Array(Set([0,frames]+spans.flatMap { [$0.start,$0.start+$0.length] })).sorted()
        video.instructions=zip(cuts,cuts.dropFirst()).map { start,end in
            let active=spans.filter { $0.start<=start && $0.start+$0.length>=end }
            return PlaybackVideoInstruction(range:CMTimeRange(start:time(Double(start)),end:time(Double(end))),spans:active,fps:fps)
        }
        return (video,assets)
    }
}
