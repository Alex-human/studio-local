import AVFoundation
import CoreImage
import Foundation

/// Python's sprites (titles, captions, images) with their per-frame placement: [sprite, x, y, alpha] in top-left pixels.
final class ExportSprites {
    let sprites:[CIImage]
    let placements:[[Double]]
    init(_ plan:[String:Any])throws {
        sprites=try (plan["sprites"] as? [String] ?? []).map { path in
            guard let image=CIImage(contentsOf:URL(fileURLWithPath:path),options:[.colorSpace:NSNull()]) else { throw PlaybackFailure(message:"No se puede leer una capa: "+path) }
            return image
        }
        placements=plan["placements"] as? [[Double]] ?? []
    }
    func composite(over base:CIImage,frame:Int,height:CGFloat)->CIImage {
        guard frame<placements.count else { return base }
        var result=base;let row=placements[frame]
        for i in stride(from:0,to:row.count,by:4) {
            var image=sprites[Int(row[i])]
            image=image.transformed(by:CGAffineTransform(translationX:row[i+1],y:height-row[i+2]-image.extent.height))
            if row[i+3]<1 { image=image.applyingFilter("CIColorMatrix",parameters:["inputAVector":CIVector(x:0,y:0,z:0,w:max(0,row[i+3]))]) }
            result=image.composited(over:result)
        }
        return result
    }
}

/// One span's pictures in order, read straight from its file: an AVFoundation composition skips the leading B-frames of an
/// open GOP after a cut (HEVC from phones), a track reader does not.
final class SpanReader {
    private let reader:AVAssetReader,output:AVAssetReaderTrackOutput
    private var current:(Double,CVPixelBuffer)?,next:(Double,CVPixelBuffer)?
    init(_ track:AVAssetTrack,asset:AVAsset,from:Double,to:Double)throws {
        reader=try AVAssetReader(asset:asset)
        reader.timeRange=CMTimeRange(start:CMTime(seconds:max(0,from),preferredTimescale:600000),end:CMTime(seconds:to,preferredTimescale:600000))
        output=AVAssetReaderTrackOutput(track:track,outputSettings:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_64RGBAHalf])
        output.alwaysCopiesSampleData=false;reader.add(output)
        guard reader.startReading() else { throw reader.error ?? PlaybackFailure(message:"No se pudo leer un vídeo.") }
        current=pull();next=pull()
    }
    private func pull()->(Double,CVPixelBuffer)? {
        while let sample=output.copyNextSampleBuffer() {
            if let buffer=CMSampleBufferGetImageBuffer(sample) { return (CMSampleBufferGetPresentationTimeStamp(sample).seconds,buffer) }
        }
        return nil
    }
    /// The last picture stamped within `accept`; the first one while none is yet (the exporter holds it).
    func picture(_ accept:(Double)->Bool)->CVPixelBuffer? {
        while let n=next,accept(n.0) { current=n;next=pull() }
        return current?.1
    }
    func close() { reader.cancelReading() }
}

/// `studio-export PLAN.json OUT.mp4 QUALITY`: the project's video through the playback compositor, the GPU and VideoToolbox.
@main struct StudioExport {
    static func main() {
        do { try run() } catch { FileHandle.standardError.write(("\(error)\n").data(using:.utf8)!);exit(1) }
    }
    static func run()throws {
        let args=CommandLine.arguments
        let plan=try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:args[1]))) as! [String:Any]
        let out=URL(fileURLWithPath:args[2]),quality=Double(args[3]) ?? 0.75
        let frames=plan["frames"] as! Int,width=plan["width"] as! Int,height=plan["height"] as! Int
        let num=plan["fpsNum"] as! Int,den=plan["fpsDen"] as! Int,fps=Double(num)/Double(den)
        let size=CGSize(width:width,height:height),rect=CGRect(origin:.zero,size:size)
        PlaybackVideoCompositor.exporting=true
        let compositor=PlaybackVideoCompositor(),sprites=try ExportSprites(plan),store=PlaybackAssetStore()
        let context=CIContext(options:[.workingColorSpace:NSNull(),.cacheIntermediates:false]),colorSpace=CGColorSpace(name:CGColorSpace.sRGB)!
        // Base clips, then overlays, as PlaybackVideoBuilder stacks them.
        var spans:[(span:PlaybackVideoSpan,track:AVAssetTrack,asset:AVAsset)]=[]
        func add(_ spec:[String:Any],start:Int,overlay:Bool)throws {
            guard let path=spec["path"] as? String,let length=spec["length"] as? Int,length>0 else { throw PlaybackFailure(message:"Clip de exportación no válido.") }
            let asset=store.asset(path)
            guard let track=asset.tracks(withMediaType:.video).first else { throw PlaybackFailure(message:"No se puede leer el vídeo: "+URL(fileURLWithPath:path).lastPathComponent) }
            let t=track.preferredTransform,oriented=CGAffineTransform(a:t.a,b:-t.b,c:-t.c,d:t.d,tx:t.tx,ty:-t.ty)
            spans.append((PlaybackVideoSpan(trackID:0,start:start,length:length,spec:spec,transform:oriented,overlay:overlay),track,asset))
        }
        var position=0
        for spec in plan["clips"] as! [[String:Any]] { try add(spec,start:position,overlay:false);position += spec["length"] as! Int }
        guard position==frames else { throw PlaybackFailure(message:"La duración de la exportación no coincide con el montaje.") }
        for spec in plan["videoOverlays"] as? [[String:Any]] ?? [] { try add(spec,start:Int(videoNumber(spec,"start",0)),overlay:true) }
        let writer=try AVAssetWriter(outputURL:out,fileType:.mp4)
        let colors:[String:Any]=[AVVideoColorPrimariesKey:AVVideoColorPrimaries_ITU_R_709_2,AVVideoTransferFunctionKey:AVVideoTransferFunction_ITU_R_709_2,AVVideoYCbCrMatrixKey:AVVideoYCbCrMatrix_ITU_R_709_2]
        let input=AVAssetWriterInput(mediaType:.video,outputSettings:[AVVideoCodecKey:AVVideoCodecType.h264,AVVideoWidthKey:width,AVVideoHeightKey:height,AVVideoColorPropertiesKey:colors,
            AVVideoCompressionPropertiesKey:[AVVideoQualityKey:quality,AVVideoMaxKeyFrameIntervalKey:12,AVVideoExpectedSourceFrameRateKey:fps,AVVideoProfileLevelKey:AVVideoProfileLevelH264HighAutoLevel]])
        writer.add(input)
        let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_64RGBAHalf,
            kCVPixelBufferWidthKey as String:width,kCVPixelBufferHeightKey as String:height,kCVPixelBufferMetalCompatibilityKey as String:true])
        guard writer.startWriting() else { throw writer.error ?? PlaybackFailure(message:"No se pudo abrir el archivo de salida.") }
        writer.startSession(atSourceTime:.zero)
        var readers:[Int:SpanReader]=[:]
        defer { readers.values.forEach { $0.close() } }
        for frame in 0..<frames {
            try autoreleasepool {
                var pictures:[ObjectIdentifier:CVPixelBuffer]=[:],active:[PlaybackVideoSpan]=[]
                for (i,item) in spans.enumerated() {
                    let span=item.span
                    guard frame>=span.start && frame<span.start+span.length else { readers.removeValue(forKey:i)?.close();continue }
                    let speed=videoNumber(span.spec,"speed",1),sourceIn=videoNumber(span.spec,"sourceIn",0)
                    if readers[i]==nil { readers[i]=try SpanReader(item.track,asset:item.asset,from:(sourceIn-2)/fps-1,to:(sourceIn+Double(span.length)*speed+2)/fps+1) }
                    let at=(sourceIn+Double(frame-span.start)*speed)/fps
                    // As the exporter: a base clip shows the last picture stamped before the middle of the frame
                    // (fps round=near), an overlay the last one stamped by the frame's start (round=up). A picture
                    // exactly on that boundary goes, as FFmpeg's exact rounding sends it, to the later frame for a
                    // clip and to this frame for an overlay; 0.1 µs absorbs the floating-point error at those ties.
                    let picture=span.overlay ? readers[i]!.picture { $0 <= at+1e-7 } : readers[i]!.picture { $0 < at+0.5/fps-1e-7 }
                    guard let picture else { throw PlaybackFailure(message:"No se pudo decodificar una capa de vídeo.") }
                    pictures[ObjectIdentifier(span)]=picture;active.append(span)
                }
                var image=try compositor.compose(active,frame:Double(frame),fps:fps,size:size) { pictures[ObjectIdentifier($0)] }
                image=sprites.composite(over:image,frame:frame,height:size.height).cropped(to:rect)
                while !input.isReadyForMoreMediaData { usleep(500) }
                guard let pool=adaptor.pixelBufferPool else { throw writer.error ?? PlaybackFailure(message:"No se pudo preparar un fotograma.") }
                var buffer:CVPixelBuffer?
                guard CVPixelBufferPoolCreatePixelBuffer(nil,pool,&buffer)==kCVReturnSuccess,let buffer else { throw PlaybackFailure(message:"No se pudo preparar un fotograma.") }
                CVBufferSetAttachment(buffer,kCVImageBufferColorPrimariesKey,kCVImageBufferColorPrimaries_ITU_R_709_2,.shouldPropagate)
                CVBufferSetAttachment(buffer,kCVImageBufferTransferFunctionKey,kCVImageBufferTransferFunction_ITU_R_709_2,.shouldPropagate)
                CVBufferSetAttachment(buffer,kCVImageBufferYCbCrMatrixKey,kCVImageBufferYCbCrMatrix_ITU_R_709_2,.shouldPropagate)
                context.render(image,to:buffer,bounds:rect,colorSpace:colorSpace)
                guard adaptor.append(buffer,withPresentationTime:CMTime(value:Int64(frame)*Int64(den),timescale:Int32(num))) else { throw writer.error ?? PlaybackFailure(message:"No se pudo escribir el vídeo.") }
            }
            if (frame+1) % 30 == 0 { print(frame+1);fflush(stdout) }
        }
        input.markAsFinished()
        let done=DispatchSemaphore(value:0);writer.finishWriting { done.signal() };done.wait()
        guard writer.status == .completed else { throw writer.error ?? PlaybackFailure(message:"No se pudo escribir el vídeo.") }
    }
}
