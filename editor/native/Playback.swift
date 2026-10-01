import AppKit
import AVFoundation
import MediaToolbox

// Keep AVAudioMix at unity: native volume ramps can attenuate later clips
// after the tap. Apply each clip gain and fade together to its PCM samples.
final class PlaybackGain {
    struct Span {
        let id: String; let start: Double; let end: Double; let volume: Float
        let fadeIn: Double; let fadeOut: Double; let fadeOffset: Double; let fadeLength: Double
        let deClickOffset: Double; let deClickLength: Double
        func envelope(at time: Double) -> Float {
            let local = time-start+fadeOffset
            let entrance = fadeIn > 0 ? max(0,min(1,local/fadeIn)) : 1
            let exit = fadeOut > 0 ? max(0,min(1,(fadeLength-local)/fadeOut)) : 1
            let edge=time-start+deClickOffset
            let deClick=deClickLength>0 ? max(0,min(1,edge/0.003))*max(0,min(1,(deClickLength-edge)/0.003)) : 1
            return Float(entrance*exit*deClick)
        }
    }
    let spans: [Span]
    private let lock = NSLock()
    private var values: [Float]
    var sampleRate: Double = 48000
    var sampleBytes = 4
    var floatingPoint = true
    var supportedFormat = true
    #if STUDIO_AUDIO_TESTS
    var observe: ((UnsafeMutablePointer<AudioBufferList>) -> Void)?
    var observeStart: ((Double) -> Void)?
    #endif
    init(_ sources: [[String: Any]]) {
        spans = sources.map { source in
            let start = (source["start"] as! NSNumber).doubleValue
            let length = (source["length"] as! NSNumber).doubleValue
            let fadeLength = (source["fadeLength"] as? NSNumber)?.doubleValue ?? length
            return Span(id: source["id"] as? String ?? "", start: start,
                end: start + length, volume: (source["volume"] as! NSNumber).floatValue,
                fadeIn: min(fadeLength,(source["fadeIn"] as? NSNumber)?.doubleValue ?? 0),
                fadeOut: min(fadeLength,(source["fadeOut"] as? NSNumber)?.doubleValue ?? 0),
                fadeOffset: (source["fadeOffset"] as? NSNumber)?.doubleValue ?? 0,
                fadeLength: fadeLength,
                deClickOffset:(source["deClickOffset"] as? NSNumber)?.doubleValue ?? 0,
                deClickLength:(source["deClickLength"] as? NSNumber)?.doubleValue ?? 0)
        }
        values = spans.map { $0.volume }
    }
    func update(_ levels: [String: Double]) {
        let next = spans.map { levels[$0.id].map(Float.init) ?? $0.volume }
        lock.lock(); values = next; lock.unlock()
    }
    func apply(_ data: UnsafeMutablePointer<AudioBufferList>, frames: Int, start: Double) {
        lock.lock(); let gains = values; lock.unlock()
        var index = spans.firstIndex { $0.end > start } ?? spans.count
        let buffers = UnsafeMutableAudioBufferListPointer(data)
        guard supportedFormat, sampleRate > 0 else {
            for buffer in buffers { if let raw = buffer.mData { memset(raw, 0, Int(buffer.mDataByteSize)) } }
            return
        }
        for frame in 0..<frames {
            let time = start + Double(frame)/sampleRate
            while index < spans.count && time >= spans[index].end { index += 1 }
            let gain: Float = index < spans.count && time >= spans[index].start ? gains[index]*spans[index].envelope(at:time) : 0
            for buffer in buffers {
                guard let raw = buffer.mData else { continue }
                let channels = Int(buffer.mNumberChannels)
                for channel in 0..<channels {
                    let sample = frame*channels+channel
                    guard sample < Int(buffer.mDataByteSize)/sampleBytes else { continue }
                    if floatingPoint {
                        if sampleBytes == 8 { raw.assumingMemoryBound(to: Double.self)[sample] *= Double(gain) }
                        else { raw.assumingMemoryBound(to: Float.self)[sample] *= gain }
                    } else if sampleBytes == 2 {
                        let pointer = raw.assumingMemoryBound(to: Int16.self)
                        pointer[sample] = Int16(max(-32768, min(32767, Double(pointer[sample])*Double(gain))))
                    } else {
                        let pointer = raw.assumingMemoryBound(to: Int32.self)
                        pointer[sample] = Int32(max(-2147483648, min(2147483647, Double(pointer[sample])*Double(gain))))
                    }
                }
            }
        }
        #if STUDIO_AUDIO_TESTS
        observe?(data); observeStart?(start)
        #endif
    }
    func configure(_ format: AudioStreamBasicDescription) {
        sampleRate = format.mSampleRate
        sampleBytes = Int(format.mBitsPerChannel)/8
        floatingPoint = format.mFormatFlags & kAudioFormatFlagIsFloat != 0
        supportedFormat = format.mFormatID == kAudioFormatLinearPCM
            && format.mFormatFlags & kAudioFormatFlagIsBigEndian == 0
            && format.mFormatFlags & kAudioFormatFlagIsPacked != 0
            && (floatingPoint ? [4, 8].contains(sampleBytes)
                : format.mFormatFlags & kAudioFormatFlagIsSignedInteger != 0 && [2, 4].contains(sampleBytes))
    }
    func tap() throws -> MTAudioProcessingTap {
        var callbacks = MTAudioProcessingTapCallbacks(version: kMTAudioProcessingTapCallbacksVersion_0,
            clientInfo: Unmanaged.passUnretained(self).toOpaque(),
            init: { _, info, storage in
                storage.pointee = Unmanaged<PlaybackGain>.fromOpaque(info!).retain().toOpaque()
            }, finalize: { tap in
                Unmanaged<PlaybackGain>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).release()
            },
            prepare: { tap, _, format in
                let gain = Unmanaged<PlaybackGain>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).takeUnretainedValue()
                gain.configure(format.pointee)
            }, unprepare: nil,
            process: { tap, count, _, data, countOut, flagsOut in
                var range = CMTimeRange.zero
                guard MTAudioProcessingTapGetSourceAudio(tap,count,data,flagsOut,&range,countOut) == noErr else { return }
                let gain = Unmanaged<PlaybackGain>.fromOpaque(MTAudioProcessingTapGetStorage(tap)).takeUnretainedValue()
                gain.apply(data,frames: countOut.pointee,start: range.start.seconds)
            })
        var result: MTAudioProcessingTap?
        guard MTAudioProcessingTapCreate(kCFAllocatorDefault,&callbacks,kMTAudioProcessingTapCreationFlag_PostEffects,&result) == noErr,
              let tap = result else { throw PlaybackFailure(message: "No se pudo preparar el control de volumen.") }
        return tap
    }
}

/// Sources that decode to the same PCM layout share composition tracks. AVPlayer
/// starts every extra audio track later after load or seek: one track per camera
/// file silenced up to half a second of voice in a 21-take edit. Also returns the
/// sample rate whose grid the clips of that track are placed on.
func playbackAudioFormat(_ track: AVAssetTrack, path: String) -> (key: String, rate: Int32) {
    guard let description = (track.formatDescriptions as? [CMFormatDescription])?.first,
          let format = CMAudioFormatDescriptionGetStreamBasicDescription(description)?.pointee else { return ("path:"+path, 60000) }
    var size = 0
    let layout = CMAudioFormatDescriptionGetChannelLayout(description, sizeOut: &size)?.pointee.mChannelLayoutTag ?? 0
    let rate = (1...384000).contains(format.mSampleRate) && format.mSampleRate.rounded() == format.mSampleRate ? Int32(format.mSampleRate) : 60000
    return ("\(format.mFormatID):\(format.mSampleRate):\(format.mChannelsPerFrame):\(format.mBitsPerChannel):\(format.mFormatFlags):\(format.mFramesPerPacket):\(layout)", rate)
}

struct PlaybackFailure: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

final class PlaybackAssetStore {
    private var values: [String: (stamp: String, asset: AVURLAsset)] = [:]
    private let lock = NSLock()
    func asset(_ path: String) -> AVURLAsset {
        lock.lock(); defer { lock.unlock() }
        let attrs=(try? FileManager.default.attributesOfItem(atPath:path)) ?? [:]
        let stamp="\(attrs[.size] ?? 0):\(attrs[.modificationDate] ?? 0):\(attrs[.systemFileNumber] ?? 0)"
        if let value=values[path], value.stamp==stamp { return value.asset }
        let value=AVURLAsset(url:URL(fileURLWithPath:path));values[path]=(stamp,value);return value
    }
}

final class PlaybackTimeline {
    let item: AVPlayerItem
    let fps: Double
    let frames: Int
    var origin = 0
    var key: String
    let mediaKey: String
    var images: [[String: Any]]
    var cues: [[String: Any]]
    let sources: [AVAsset]
    var audioSegments: [(CMPersistentTrackID, [String: Any])] = []
    var volumes: [String: Double] = [:]
    var gains: [PlaybackGain] = []

    static func build(_ plan: [String: Any]) throws -> PlaybackTimeline {
        try build(plan, store: PlaybackAssetStore())
    }

    static func build(_ plan: [String: Any], store: PlaybackAssetStore) throws -> PlaybackTimeline {
        guard plan["clips"] is [[String: Any]], let frames = plan["frames"] as? Int, frames > 0,
              let numerator = plan["fpsNum"] as? Int, let denominator = plan["fpsDen"] as? Int,
              numerator > 0, denominator > 0, plan["width"] is Int, plan["height"] is Int,
              let key = plan["key"] as? String, let mediaKey = plan["mediaKey"] as? String else { throw PlaybackFailure(message: "Plan de reproducción incompleto.") }
        let composition = AVMutableComposition()
        func time(_ frames: Double) -> CMTime { CMTime(value: Int64((frames * Double(denominator)).rounded()), timescale: Int32(numerator)) }
        let (video, videoAssets) = try PlaybackVideoBuilder.build(plan, composition: composition, store: store)
        var assets = videoAssets
        var audioSegments: [(CMPersistentTrackID, [String: Any])] = []
        if let audioPath=plan["audio"] as? String {
            let audioAsset=store.asset(audioPath);assets[audioPath]=audioAsset
            guard let sourceAudio=audioAsset.tracks(withMediaType:.audio).first,
                  let audio=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid) else {
                throw PlaybackFailure(message:"No se puede leer la mezcla de audio.")
            }
            let end=time(Double(frames))
            let sourceStart=CMTime(seconds:(plan["audioSourceIn"] as? NSNumber)?.doubleValue ?? 0,preferredTimescale:60000)
            do { try audio.insertTimeRange(CMTimeRange(start:sourceStart,duration:CMTimeMinimum(end,CMTimeSubtract(audioAsset.duration,sourceStart))),of:sourceAudio,at:.zero) }
            catch { throw PlaybackFailure(message:"Audio: \(error)") }
        } else {
            // A tap must not span changing source formats (for example WAV to camera AAC).
            // Clips sit on their source sample grid and a contiguous clip starts exactly where
            // the previous one ended: a boundary between two samples pushed the rest of the
            // track about one sample later per cut.
            var lanes: [(track: AVMutableCompositionTrack, end: Double, format: String, rate: Int32, sample: Int64)] = []
            let totalSeconds=Double(frames)/Double(numerator)*Double(denominator)
            for source in plan["audioSources"] as? [[String:Any]] ?? [] {
                guard let path=source["path"] as? String,
                      let start=(source["start"] as? NSNumber)?.doubleValue,
                      let sourceIn=(source["source"] as? NSNumber)?.doubleValue,
                      let length=(source["length"] as? NSNumber)?.doubleValue,
                      let speed=(source["speed"] as? NSNumber)?.doubleValue,
                      (source["volume"] as? NSNumber) != nil,
                      length>0, speed>0 else { throw PlaybackFailure(message:"Tramo de audio no válido.") }
                let asset=store.asset(path);assets[path]=asset
                guard let sourceTrack=asset.tracks(withMediaType:.audio).first else { throw PlaybackFailure(message:"No se puede leer el audio: "+URL(fileURLWithPath:path).lastPathComponent) }
                let (format,rate)=playbackAudioFormat(sourceTrack,path:path)
                var laneIndex=lanes.firstIndex(where:{$0.end<=start+0.000001 && $0.format==format})
                if laneIndex==nil {
                    guard let track=composition.addMutableTrack(withMediaType:.audio,preferredTrackID:kCMPersistentTrackID_Invalid) else { throw PlaybackFailure(message:"No se pudo crear una pista de audio.") }
                    lanes.append((track,0,format,rate,0));laneIndex=lanes.count-1
                }
                func samples(_ seconds:Double)->Int64 { Int64((seconds*Double(rate)).rounded()) }
                // Audio never outlasts the video: its end rarely falls on a whole sample.
                let index=laneIndex!,track=lanes[index].track,limit=Int64((totalSeconds*Double(rate)).rounded(.down))
                let first=abs(start-lanes[index].end)<0.000001 ? lanes[index].sample : samples(start),last=max(first+1,min(samples(start+length),limit))
                let inputSeconds=min(length*speed,max(0,asset.duration.seconds-sourceIn))
                guard inputSeconds>0 else { throw PlaybackFailure(message:"El tramo de audio queda fuera de su archivo.") }
                // Only a speed change or a missing source tail is rescaled, never a rounding sample.
                let scaled=abs(inputSeconds-length)>0.000001
                let available=Int64((max(0,asset.duration.seconds-sourceIn)*Double(rate)).rounded(.down))
                let at=CMTime(value:first,timescale:rate),inputDuration=CMTime(value:max(1,min(scaled ? samples(inputSeconds) : last-first,available)),timescale:rate)
                do {
                    try track.insertTimeRange(CMTimeRange(start:CMTime(value:samples(sourceIn),timescale:rate),duration:inputDuration),of:sourceTrack,at:at)
                    if scaled { track.scaleTimeRange(CMTimeRange(start:at,duration:inputDuration),toDuration:CMTime(value:last-first,timescale:rate)) }
                } catch { throw PlaybackFailure(message:"Audio \(URL(fileURLWithPath:path).lastPathComponent): \(error)") }
                audioSegments.append((track.trackID, source))
                lanes[index].end=start+length;lanes[index].sample=last
            }
            for lane in lanes {
                let end=lane.track.timeRange.end,total=CMTime(value:Int64((totalSeconds*Double(lane.rate)).rounded(.down)),timescale:lane.rate)
                if end<total { lane.track.insertEmptyTimeRange(CMTimeRange(start:end,end:total)) }
            }
        }
        video.colorPrimaries = AVVideoColorPrimaries_ITU_R_709_2
        video.colorTransferFunction = AVVideoTransferFunction_ITU_R_709_2
        video.colorYCbCrMatrix = AVVideoYCbCrMatrix_ITU_R_709_2
        guard video.isValid(for:composition,timeRange:CMTimeRange(start:.zero,duration:composition.duration),validationDelegate:nil) else {
            throw PlaybackFailure(message:"La composición de vídeo necesita una vista de edición renderizada.")
        }
        let item = AVPlayerItem(asset: composition)
        item.audioTimePitchAlgorithm = .timeDomain
        item.videoComposition = video
        item.preferredForwardBufferDuration = 1
        let timeline = PlaybackTimeline(item: item, fps: Double(numerator)/Double(denominator), frames: frames, key: key,
                                mediaKey: mediaKey, images: plan["images"] as? [[String: Any]] ?? [],
                                cues: plan["audioCues"] as? [[String: Any]] ?? [], sources: Array(assets.values))
        timeline.audioSegments = audioSegments; try timeline.configureAudio()
        return timeline
    }

    func setVolumes(_ levels: [String: Double]) {
        volumes = levels
        gains.forEach { $0.update(levels) }
    }
    func configureAudio() throws {
        guard !audioSegments.isEmpty else { return }
        var tracks: [CMPersistentTrackID: AVMutableAudioMixInputParameters] = [:]
        for (trackID, _) in audioSegments where tracks[trackID] == nil {
            let parameters = AVMutableAudioMixInputParameters()
            parameters.trackID = trackID
            parameters.setVolume(1, at:.zero)
            tracks[trackID] = parameters
        }
        for (trackID, parameters) in tracks {
            let gain = PlaybackGain(audioSegments.filter { $0.0 == trackID }.map { $0.1 })
            gains.append(gain); parameters.audioTapProcessor = try gain.tap()
        }
        let mix = AVMutableAudioMix(); mix.inputParameters = tracks.values.sorted { $0.trackID < $1.trackID }
        item.audioMix = mix
    }

    init(item: AVPlayerItem, fps: Double, frames: Int, key: String, mediaKey: String,
         images: [[String: Any]], cues: [[String: Any]], sources: [AVAsset]) {
        self.item = item; self.fps = fps; self.frames = frames; self.key = key; self.mediaKey = mediaKey
        self.images = images; self.cues = cues; self.sources = sources
    }
}

private func playbackSmooth(_ value: Double) -> Double {
    let t = min(1, max(0, value)); return t*t*t*(t*(t*6-15)+10)
}

final class PlaybackImageLayer {
    let container = CALayer()
    let panel = CALayer()
    let image = CALayer()
    let spec: [String: Any]
    private let keyframes: [(String, [(frame: Double, value: Double)])]
    init(_ spec: [String: Any], contents: CGImage) {
        self.spec = spec
        keyframes = (spec["keyframes"] as? [String: [[String: Any]]] ?? [:]).map { key, values in
            // Python's sort is stable: the last point at an exact duplicate frame wins.
            let points = values.enumerated().compactMap { index, point -> (Int, Double, Double)? in
                guard let frame = (point["frame"] as? NSNumber)?.doubleValue,
                      let value = (point["value"] as? NSNumber)?.doubleValue else { return nil }
                return (index, frame, value)
            }.sorted { $0.1 == $1.1 ? $0.0 < $1.0 : $0.1 < $1.1 }
            return (key, points.map { (frame: $0.1, value: $0.2) })
        }
        container.addSublayer(panel); panel.addSublayer(image)
        image.contents = contents; image.contentsGravity = .resize; image.masksToBounds = true
    }

    func properties(at local: Double) -> [String: Any] {
        var props = spec["props"] as? [String: Any] ?? [:]
        for (key, points) in keyframes {
            guard let first = points.first else { continue }
            var value = first.value
            for (a, b) in zip(points, points.dropFirst()) {
                if local >= b.frame { value = b.value; continue }
                if local >= a.frame { value = a.value + (b.value-a.value)*playbackSmooth((local-a.frame)/max(1,b.frame-a.frame)) }
                break
            }
            props[key] = value
        }
        return props
    }
}

final class PlaybackView: NSView {
    let playerLayer = AVPlayerLayer()
    let overlayRoot = CALayer()
    var overlays: [PlaybackImageLayer] = []
    var lastFrame = 0
    var lastFPS = 60.0
    private var canvasSize = CGSize(width: 960, height: 540)
    private var imageCache: [String: (stamp: String, image: CGImage)] = [:]
    override init(frame: NSRect) {
        super.init(frame: frame); wantsLayer = true
        playerLayer.videoGravity = .resizeAspect
        layer?.backgroundColor = NSColor.black.cgColor
        layer?.addSublayer(playerLayer)
        overlayRoot.masksToBounds = true
        layer?.addSublayer(overlayRoot)
        isHidden = true
    }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func layout() { super.layout(); playerLayer.frame = bounds; updateImages(frame: lastFrame, fps: lastFPS) }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    func configureImages(_ specs: [[String: Any]], width: Int, height: Int) throws {
        // Load every layer before replacing the visible set. An unreadable sprite
        // must fail the plan, never silently remove a title from the preview.
        var nextCache: [String: (stamp: String, image: CGImage)] = [:]
        let next = try specs.map { spec -> PlaybackImageLayer in
            guard let path = spec["path"] as? String else { throw PlaybackFailure(message: "Falta una capa de reproducción.") }
            if spec["kind"] as? String == "text" {
                guard let rect = spec["rect"] as? [Double], rect.count == 4,
                      rect.allSatisfy({ $0.isFinite }), rect[2] > 0, rect[3] > 0,
                      let canvasWidth = (spec["canvasWidth"] as? NSNumber)?.doubleValue,
                      let canvasHeight = (spec["canvasHeight"] as? NSNumber)?.doubleValue,
                      canvasWidth.isFinite, canvasHeight.isFinite, canvasWidth > 0, canvasHeight > 0 else {
                    throw PlaybackFailure(message: "La geometría del texto de reproducción no es válida.")
                }
            }
            let attributes = try FileManager.default.attributesOfItem(atPath: path)
            let stamp = "\(attributes[.size] ?? 0)-\((attributes[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0)-\(attributes[.systemFileNumber] ?? 0)"
            let cg: CGImage
            if let cached = nextCache[path] ?? imageCache[path], cached.stamp == stamp { cg = cached.image }
            else {
                guard let source = NSImage(contentsOfFile: path),
                      let image = source.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
                    throw PlaybackFailure(message: "No se puede leer la capa de reproducción: " + URL(fileURLWithPath: path).lastPathComponent)
                }
                cg = image
            }
            nextCache[path] = (stamp, cg)
            return PlaybackImageLayer(spec, contents: cg)
        }
        overlays.forEach { $0.container.removeFromSuperlayer() }
        imageCache = nextCache; canvasSize = CGSize(width: max(1, width), height: max(1, height))
        overlays = next
        overlays.forEach { overlayRoot.addSublayer($0.container) }
        updateImages(frame: lastFrame, fps: lastFPS)
    }

    func clearImages() {
        overlays.forEach { $0.container.removeFromSuperlayer() }; overlays = []; imageCache = [:]
    }

    private func number(_ values: [String: Any], _ key: String, _ fallback: Double) -> Double {
        (values[key] as? NSNumber)?.doubleValue ?? fallback
    }

    func updateImages(frame: Int, fps: Double) {
        lastFrame = frame; lastFPS = fps
        let video = playerLayer.videoRect.width > 0 ? playerLayer.videoRect : AVMakeRect(aspectRatio: canvasSize, insideRect: bounds)
        let pixelScale = video.width / canvasSize.width
        let scale = canvasSize.width / 1920
        CATransaction.begin(); CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        overlayRoot.frame = video
        for overlay in overlays {
            let s = overlay.spec
            let start = Int(number(s,"start",0)), length = Int(number(s,"length",0))
            guard frame >= start && frame < start + length else { overlay.container.isHidden = true; continue }
            overlay.container.isHidden = false
            let local = Double(frame-start)+number(s,"offset",0)
            let props = overlay.properties(at: local)
            if s["kind"] as? String == "text", let rect = s["rect"] as? [Double] {
                let pixelScale = video.width/number(s,"canvasWidth",960)
                let animated = props["animation"] as? String != "none"
                let entrance = animated ? playbackSmooth(local/fps/max(0.01,number(props,"enter",0.45))) : 1
                let exit = animated ? playbackSmooth((number(s,"motionLength",Double(length))-local)/fps/0.2) : 1
                // Pillow places the canonical glyphs on the preview pixel grid.
                // Keep the cached raster sharp during the same vertical entry.
                let dy = animated ? ((1-entrance)*35*number(s,"canvasWidth",960)/1920).rounded() : 0
                overlay.container.bounds = CGRect(x:0,y:0,width:rect[2]*pixelScale,height:rect[3]*pixelScale)
                overlay.container.position = CGPoint(x:(rect[0]+rect[2]/2)*pixelScale,
                                                     y:video.height-(rect[1]+dy+rect[3]/2)*pixelScale)
                overlay.container.opacity = Float(max(0,min(1,entrance*exit*number(props,"opacity",1))))
                overlay.panel.frame = overlay.container.bounds
                overlay.image.frame = overlay.panel.bounds
                continue
            }
            let enter = max(0.01,number(props,"enter",0.48))
            let u = min(1,max(0,local/fps/enter)), eased = 1-pow(1-u,4)
            var dx=0.0,dy=0.0,motionScale=1.0,alpha=1.0
            let animation = props["animation"] as? String ?? "pop"
            if animation != "none" { alpha = min(1,u*4) }
            switch animation {
            case "pop": motionScale = 0.88 + 0.12*eased
            case "from-left": dx = -180*(1-eased)
            case "from-right": dx = 180*(1-eased)
            case "from-top": dy = -150*(1-eased)
            case "from-bottom": dy = 150*(1-eased)
            default: break
            }
            let motionLength = number(s,"motionLength",Double(length))
            alpha *= playbackSmooth((motionLength-local)/fps/0.2) * number(props,"opacity",1)
            // Match Pillow's pixel crop, including crossed animated crop edges.
            // A crop never disappears: its minimum extent is one source pixel.
            let sw=max(1,number(s,"sourceWidth",1)),sh=max(1,number(s,"sourceHeight",1))
            let left=min(sw-1,max(0,(sw*number(props,"cropLeft",0)).rounded(.toNearestOrEven)))
            let top=min(sh-1,max(0,(sh*number(props,"cropTop",0)).rounded(.toNearestOrEven)))
            let right=max(left+1,(sw*(1-number(props,"cropRight",0))).rounded(.toNearestOrEven))
            let bottom=max(top+1,(sh*(1-number(props,"cropBottom",0))).rounded(.toNearestOrEven))
            let imageWidth=max(2,(number(props,"width",760)*scale*motionScale).rounded(.toNearestOrEven))
            let imageHeight=max(2,(imageWidth*(bottom-top)/(right-left)).rounded(.toNearestOrEven))
            let photo=(props["style"] as? String ?? "photo")=="photo",pad=photo ? max(2,(12*scale).rounded(.toNearestOrEven)) : 0
            let width=imageWidth+2*pad,height=imageHeight+2*pad
            let angle=number(props,"rotation",0)*Double.pi/180
            let cosine=(cos(angle)*1e15).rounded()/1e15,sine=(sin(angle)*1e15).rounded()/1e15
            let extentWidth=abs(width*cosine)+abs(height*sine),extentHeight=abs(width*sine)+abs(height*cosine)
            let rotatedWidth=cosine == 0 ? height : sine == 0 ? width : ceil((width+extentWidth)/2)-floor((width-extentWidth)/2)
            let rotatedHeight=cosine == 0 ? width : sine == 0 ? height : ceil((height+extentHeight)/2)-floor((height-extentHeight)/2)
            let x=((number(props,"x",960)+dx)*scale-rotatedWidth/2).rounded(.toNearestOrEven)
            let y=((number(props,"y",540)+dy)*scale-rotatedHeight/2).rounded(.toNearestOrEven)
            overlay.container.bounds=CGRect(x:0,y:0,width:rotatedWidth*pixelScale,height:rotatedHeight*pixelScale)
            overlay.container.position=CGPoint(x:(x+rotatedWidth/2)*pixelScale,
                                                y:video.height-(y+rotatedHeight/2)*pixelScale)
            overlay.container.opacity=Float(max(0,min(1,alpha)))
            // Rotate the panel, then cast the shadow vertically from its alpha.
            overlay.panel.bounds=CGRect(x:0,y:0,width:width*pixelScale,height:height*pixelScale)
            overlay.panel.position=CGPoint(x:overlay.container.bounds.midX,y:overlay.container.bounds.midY)
            overlay.panel.setAffineTransform(CGAffineTransform(rotationAngle: CGFloat(-angle)))
            overlay.panel.backgroundColor=photo ? NSColor(srgbRed:246/255,green:247/255,blue:250/255,alpha:1).cgColor : NSColor.clear.cgColor
            overlay.panel.cornerRadius=photo ? max(2,18*scale)*pixelScale : 0
            overlay.container.shadowColor=NSColor.black.cgColor;overlay.container.shadowOpacity=0.32
            overlay.container.shadowRadius=max(1,18*scale)*pixelScale;overlay.container.shadowOffset=CGSize(width:0,height:-12*scale*pixelScale)
            overlay.image.frame=CGRect(x:pad*pixelScale,y:pad*pixelScale,width:imageWidth*pixelScale,height:imageHeight*pixelScale)
            overlay.image.contentsRect=CGRect(x:left/sw,y:(sh-bottom)/sh,width:(right-left)/sw,height:(bottom-top)/sh)
            overlay.image.cornerRadius=max(1,8*scale)*pixelScale
        }
    }
}

final class PlaybackController {
    let view = PlaybackView(frame: .zero)
    let player = AVQueuePlayer()
    var timeline: PlaybackTimeline?
    var generation = 0
    var observer: Any?
    var statusObserver: NSKeyValueObservation?
    var timeControlObserver: NSKeyValueObservation?
    var endObserver: NSObjectProtocol?
    var failureObserver: NSObjectProtocol?
    var queueStatusObserver: NSKeyValueObservation?
    var itemObserver: NSKeyValueObservation?
    var nextTimeline: PlaybackTimeline?
    var cancelLoad: (() -> Void)?
    var event: (([String: Any]) -> Void)?
    private(set) var playbackRate = 1.0
    private var seekGeneration = 0
    private var isSeeking = false
    var cuePlayers: [(id: String, index: Int, player: AVAudioPlayer)] = []
    let assetStore = PlaybackAssetStore()

    init() {
        player.actionAtItemEnd = .pause
        view.playerLayer.player = player
        observer = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 120), queue: .main) { [weak self] _ in
            guard let self=self,self.player.rate != 0 else { return }; self.emit()
        }
        itemObserver = player.observe(\.currentItem, options:[.new]) { [weak self] _, _ in
            DispatchQueue.main.async { self?.advanceQueuedItem() }
        }
        timeControlObserver = player.observe(\.timeControlStatus, options: [.new]) { [weak self] _, _ in
            DispatchQueue.main.async { self?.scheduleCues() }
        }
        endObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: nil, queue: .main) { [weak self] note in
            guard let self = self, let item = note.object as? AVPlayerItem, item === self.timeline?.item else { return }
            if self.nextTimeline != nil { return }
            self.emit(ended: true)
        }
        failureObserver = NotificationCenter.default.addObserver(forName:.AVPlayerItemFailedToPlayToEndTime,object:nil,queue:.main) { [weak self] note in
            guard let self=self,let item=note.object as? AVPlayerItem,item === self.player.currentItem,let timeline=self.timeline else { return }
            self.player.pause();self.cancelCues()
            let seconds=self.player.currentTime().seconds
            self.event?(["key":timeline.key,"error":item.error?.localizedDescription ?? "No se pudo decodificar este tramo.",
                         "frame":timeline.origin+(seconds.isFinite ? max(0,Int(seconds*timeline.fps)) : 0)])
        }
    }
    func advanceQueuedItem() {
        guard let next=nextTimeline, player.currentItem === next.item else { return }
        nextTimeline=nil;queueStatusObserver=nil;player.actionAtItemEnd = .pause;timeline=next;cancelCues()
        do { try view.configureImages(next.images,width:Int(next.item.videoComposition?.renderSize.width ?? 960),height:Int(next.item.videoComposition?.renderSize.height ?? 540)) }
        catch { player.pause();view.isHidden=true;event?(["key":next.key,"error":error.localizedDescription]);return }
        event?(["key":next.key,"advanced":true,"frame":next.origin,"playing":player.rate != 0])
        emit()
    }
    func discardQueued() {
        queueStatusObserver=nil;player.actionAtItemEnd = .pause
        if let next=nextTimeline { player.remove(next.item) }
        nextTimeline=nil
    }
    func queue(_ plan:[String:Any], afterKey:String, completion:@escaping(Result<[String:Any],Error>)->Void) {
        guard let current=timeline,current.key==afterKey,
              plan["windowStart"] as? Int == current.origin+current.frames else {
            completion(.failure(PlaybackFailure(message:"El tramo anterior ya cambió.")));return
        }
        let ticket=generation
        DispatchQueue.global(qos:.userInitiated).async {
            let built=Result { try PlaybackTimeline.build(plan,store:self.assetStore) }
            DispatchQueue.main.async {
                guard ticket==self.generation,self.timeline === current,current.key==afterKey else {
                    completion(.failure(PlaybackFailure(message:"Preparación cancelada.")));return
                }
                switch built {
                case .failure(let error):completion(.failure(error))
                case .success(let next):
                    next.origin=plan["windowStart"] as? Int ?? 0
                    next.setVolumes(current.volumes)
                    guard self.player.canInsert(next.item,after:current.item) else { completion(.failure(PlaybackFailure(message:"No se pudo preparar el siguiente tramo.")));return }
                    self.discardQueued();self.nextTimeline=next;self.player.insert(next.item,after:current.item);self.player.actionAtItemEnd = .advance
                    self.queueStatusObserver=next.item.observe(\.status,options:[.initial,.new]) { [weak self] item,_ in
                        guard item.status == .failed else { return }
                        DispatchQueue.main.async {
                            guard let self=self,self.nextTimeline === next else { return }
                            self.discardQueued();self.event?(["key":current.key,"queueFailed":true])
                        }
                    }
                    completion(.success(["key":next.key]))
                }
            }
        }
    }
    func emit(ended: Bool = false) {
        guard let t = timeline else { return }
        let seconds = player.currentTime().seconds
        guard seconds.isFinite else { return }
        let frame = min(t.frames-1,max(0,Int((seconds*t.fps).rounded(.down))))
        view.updateImages(frame: frame, fps: t.fps)
        if ended { cancelCues() } else { scheduleCues() }
        event?(["key": t.key, "frame": t.origin+frame, "playing": player.rate != 0 && !ended, "ended": ended, "rate": playbackRate])
    }
    func load(_ plan: [String: Any], frame: Int, completion: @escaping (Result<[String: Any], Error>) -> Void) {
        if let current = timeline, let mediaKey = plan["mediaKey"] as? String, current.mediaKey == mediaKey,
           let key = plan["key"] as? String {
            generation += 1; discardQueued(); cancelLoad?(); cancelLoad = nil; player.pause(); cancelCues()
            let images = plan["images"] as? [[String: Any]] ?? []
            do { try view.configureImages(images, width: plan["width"] as? Int ?? 960, height: plan["height"] as? Int ?? 540) }
            catch { completion(.failure(error)); return }
            current.key = key; current.images = images
            current.origin = plan["windowStart"] as? Int ?? 0
            current.cues = plan["audioCues"] as? [[String: Any]] ?? []
            current.setVolumes([:])
            seek(frame) { completion(.success(["key": key, "reused": true])) }
            return
        }
        stop(); let ticket = generation
        DispatchQueue.global(qos: .userInitiated).async {
            let built = Result { try PlaybackTimeline.build(plan, store: self.assetStore) }
            DispatchQueue.main.async {
                guard ticket == self.generation else { completion(.failure(PlaybackFailure(message: "Reproducción cancelada."))); return }
                switch built {
                case .failure(let error): completion(.failure(error))
                case .success(let timeline):
                    timeline.origin = plan["windowStart"] as? Int ?? 0
                    do { try self.view.configureImages(timeline.images, width: plan["width"] as? Int ?? 960, height: plan["height"] as? Int ?? 540) }
                    catch { completion(.failure(error)); return }
                    self.timeline = timeline
                    self.player.replaceCurrentItem(with: timeline.item)
                    var finished = false
                    func finish(_ result: Result<[String: Any], Error>) {
                        guard !finished else { return }; finished = true
                        self.statusObserver = nil; self.cancelLoad = nil; completion(result)
                    }
                    self.cancelLoad = { finish(.failure(PlaybackFailure(message: "Reproducción cancelada."))) }
                    self.statusObserver = timeline.item.observe(\.status, options: [.new]) { [weak owner = self] item, _ in
                        DispatchQueue.main.async {
                            guard let self = owner, ticket == self.generation else { finish(.failure(PlaybackFailure(message: "Reproducción cancelada."))); return }
                            if item.status == .failed { finish(.failure(item.error ?? PlaybackFailure(message: "No se pudo preparar el reproductor."))) }
                            else if item.status == .readyToPlay {
                                self.seek(frame) { finish(.success(["key": timeline.key])) }
                            }
                        }
                    }
                    if timeline.item.status == .readyToPlay { self.seek(frame) { finish(.success(["key": timeline.key])) } }
                    DispatchQueue.main.asyncAfter(deadline: .now()+8) {
                        if !finished { if ticket == self.generation { self.stop() }; finish(.failure(PlaybackFailure(message: "El reproductor no respondió a tiempo. Comprueba los medios."))) }
                    }
                }
            }
        }
    }
    func seek(_ frame: Int, completion: @escaping () -> Void = {}) {
        guard let t = timeline else { completion(); return }
        seekGeneration += 1; let ticket = seekGeneration
        isSeeking = true; cancelCues()
        let target = CMTime(seconds: Double(min(t.frames-1,max(0,frame-t.origin)))/t.fps, preferredTimescale: 60000)
        player.seek(to: target, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            DispatchQueue.main.async {
                if let self = self, self.timeline === t, self.seekGeneration == ticket {
                    self.isSeeking = false; self.emit()
                }
                completion()
            }
        }
    }
    func setPlaybackRate(_ rate: Double) throws {
        guard rate.isFinite, (1...2).contains(rate) else {
            throw PlaybackFailure(message: "La velocidad de revisión debe estar entre 1 y 2×.")
        }
        playbackRate = rate
        if player.rate != 0 { player.rate = Float(rate) }
        emit()
    }
    func play() { guard timeline != nil else { return }; view.isHidden = false; player.rate = Float(playbackRate); emit() }
    func pause() { player.pause(); cancelCues(); view.isHidden = true; emit() }
    func stop() { generation += 1; seekGeneration += 1; isSeeking = false; cancelLoad?(); cancelLoad = nil; player.pause(); cancelCues(); view.isHidden = true; view.clearImages(); discardQueued(); timeline = nil; statusObserver = nil; player.removeAllItems() }

    func setVolumes(_ levels: [String: Double], key: String) {
        guard let timeline = timeline, timeline.key == key,
              levels.values.allSatisfy({ $0.isFinite && $0 >= 0 && $0 <= 64 }) else { return }
        timeline.setVolumes(levels)
        nextTimeline?.setVolumes(levels)
        for sound in cuePlayers { if let volume = levels[sound.id] { sound.player.volume = Float(min(1,volume)) } }
    }

    func cancelCues() {
        cuePlayers.forEach { $0.player.stop() }; cuePlayers = []
    }

    func scheduleCues() {
        // Reconcile against the media clock instead of wall-clock delays: this
        // also follows buffering, seeks and live rate changes without stale tasks.
        guard let timeline = timeline, !isSeeking, player.rate != 0,
              player.timeControlStatus == .playing else { cancelCues(); return }
        let now = player.currentTime().seconds
        guard now.isFinite else { return }
        var active = Set<Int>()
        for (index, cue) in timeline.cues.enumerated() {
            guard let path=cue["path"] as? String,
                  let start=(cue["start"] as? NSNumber)?.doubleValue,
                  let source=(cue["source"] as? NSNumber)?.doubleValue,
                  let length=(cue["length"] as? NSNumber)?.doubleValue,
                  let volume=(cue["volume"] as? NSNumber)?.doubleValue,
                  [start, source, length, volume].allSatisfy({ $0.isFinite }),
                  source >= 0, length > 0, now >= start, now < start+length else { continue }
            active.insert(index)
            let offset = source+now-start
            if let sound = cuePlayers.first(where: { $0.index == index })?.player {
                sound.rate = Float(playbackRate)
                if abs(sound.currentTime-offset) > 0.12 { sound.currentTime = offset }
            } else if let sound = try? AVAudioPlayer(contentsOf: URL(fileURLWithPath:path)) {
                let id = cue["id"] as? String ?? ""
                sound.enableRate = true; sound.rate = Float(playbackRate)
                sound.currentTime = offset
                sound.volume = Float(max(0,min(1,timeline.volumes[id] ?? volume)))
                cuePlayers.append((id,index,sound)); sound.play()
            }
        }
        cuePlayers.removeAll { sound in
            guard !active.contains(sound.index) else { return false }
            sound.player.stop(); return true
        }
    }
    func position(_ rect: [String: Double], height: Double) {
        guard let x=rect["x"],let y=rect["y"],let w=rect["width"],let h=rect["height"] else { return }
        view.frame = NSRect(x: x, y: (view.superview?.isFlipped ?? false) ? y : height-y-h, width: w, height: h)
    }
}
