import AppKit

@main struct NativeTextCheck {
    static func near(_ actual: Double, _ expected: Double) {
        precondition(abs(actual-expected)<0.00001, "\(actual) != \(expected)")
    }

    static func writeSprite(_ path: URL, red: UInt8, blue: UInt8) throws {
        let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:80,pixelsHigh:20,
                                     bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,
                                     colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
        for y in 0..<20 { for x in 0..<80 {
            let pixel = bitmap.bitmapData! + y*bitmap.bytesPerRow+x*4
            pixel[0] = red; pixel[1] = 0; pixel[2] = blue; pixel[3] = 255
        } }
        try bitmap.representation(using:.png,properties:[:])!.write(to:path)
    }

    static func snapshot(_ view: PlaybackView, width: Int, height: Int, path: String) throws {
        let context = CGContext(data:nil,width:width,height:height,bitsPerComponent:8,
                                bytesPerRow:width*4,space:CGColorSpace(name:CGColorSpace.sRGB)!,
                                bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
        context.setFillColor(NSColor.black.cgColor)
        context.fill(CGRect(x:0,y:0,width:width,height:height))
        view.overlayRoot.render(in:context)
        let bitmap = NSBitmapImageRep(cgImage:context.makeImage()!)
        try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:path))
    }

    static func main() throws {
        // Optional canonical-pixel fixture: plan.json frame output.png. No player,
        // source decode, screen capture or project mutation is needed.
        if CommandLine.arguments.count == 4 {
            let plan = try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[1]))) as! [String:Any]
            let width = plan["width"] as! Int, height = plan["height"] as! Int
            let view = PlaybackView(frame:NSRect(x:0,y:0,width:width,height:height))
            view.layoutSubtreeIfNeeded()
            try view.configureImages(plan["images"] as! [[String:Any]],width:width,height:height)
            let frame = Int(CommandLine.arguments[2])!
            view.updateImages(frame:frame,fps:(plan["fps"] as! NSNumber).doubleValue)
            try snapshot(view,width:width,height:height,path:CommandLine.arguments[3])
            print("Rendered frame \(frame): \(view.overlays.filter { !$0.container.isHidden }.count) visible layers")
            return
        }

        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("studio-native-text-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:directory) }
        let sprite = directory.appendingPathComponent("sprite.png")
        try writeSprite(sprite,red:255,blue:0)
        let title: [String:Any] = ["kind":"text","path":sprite.path,"start":10,"length":60,
                                 "offset":8,"motionLength":80,"rect":[100.0,200.0,80.0,20.0],
                                 "canvasWidth":960,"canvasHeight":1706,
                                 "props":["enter":0.01,"opacity":1.0],
                                 "keyframes":["opacity":[["frame":8,"value":0.25],["frame":10,"value":1.0]]]]
        var caption = title
        caption["props"] = ["animation":"none"]
        caption.removeValue(forKey:"keyframes")
        let image: [String:Any] = ["path":sprite.path,"start":0,"length":120,"sourceWidth":80,"sourceHeight":20,
                                 "props":["x":960,"y":540,"width":120,"style":"clean","animation":"none"]]
        let view = PlaybackView(frame:NSRect(x:0,y:0,width:480,height:900))
        view.layoutSubtreeIfNeeded()
        try view.configureImages([title,image,caption],width:960,height:1706)
        precondition(view.overlayRoot.masksToBounds)
        precondition(view.overlayRoot.sublayers!.count == 3)
        for (index,overlay) in view.overlays.enumerated() { precondition(view.overlayRoot.sublayers![index] === overlay.container) }
        view.updateImages(frame:9,fps:30)
        precondition(view.overlays[0].container.isHidden)
        view.updateImages(frame:10,fps:30)
        near(Double(view.overlays[0].container.opacity),0.25)
        near(Double(view.overlays[2].container.opacity),1)
        near(view.overlayRoot.frame.minY,23.5)
        near(view.overlays[0].container.position.x,70)
        near(view.overlays[0].container.position.y,748)
        near(view.overlays[0].container.bounds.width,40)
        view.updateImages(frame:11,fps:30)
        near(Double(view.overlays[0].container.opacity),0.625)
        view.updateImages(frame:12,fps:30)
        near(Double(view.overlays[0].container.opacity),1)
        view.updateImages(frame:69,fps:30)
        near(Double(view.overlays[2].container.opacity),1)
        view.updateImages(frame:70,fps:30)
        precondition(view.overlays[0].container.isHidden && view.overlays[2].container.isHidden)

        let first = view.overlays[0].image.contents as! CGImage
        try view.configureImages([title],width:960,height:1706)
        precondition(first === (view.overlays[0].image.contents as! CGImage))
        var invalid = title; invalid["path"] = directory.appendingPathComponent("missing.png").path
        do { try view.configureImages([invalid],width:960,height:1706); preconditionFailure("Missing sprite was silently accepted") }
        catch { precondition(view.overlays.count == 1 && first === (view.overlays[0].image.contents as! CGImage)) }
        invalid = title; invalid["rect"] = [0.0,0.0,-1.0,20.0]
        do { try view.configureImages([invalid],width:960,height:1706); preconditionFailure("Invalid text geometry was accepted") }
        catch { precondition(view.overlays.count == 1) }
        try writeSprite(sprite,red:0,blue:255)
        try FileManager.default.setAttributes([.modificationDate:Date().addingTimeInterval(2)],ofItemAtPath:sprite.path)
        try view.configureImages([title],width:960,height:1706)
        precondition(first !== (view.overlays[0].image.contents as! CGImage))

        var moving = title
        moving["start"] = 0; moving["length"] = 120; moving["offset"] = 0; moving["motionLength"] = 120
        moving["props"] = ["enter":1.0,"opacity":1.0]; moving.removeValue(forKey:"keyframes")
        try view.configureImages([moving],width:960,height:1706)
        view.updateImages(frame:0,fps:30); near(Double(view.overlays[0].container.opacity),0)
        view.updateImages(frame:15,fps:30)
        near(Double(view.overlays[0].container.opacity),0.5)
        near(view.overlays[0].container.position.y,743.5)
        view.updateImages(frame:117,fps:30); near(Double(view.overlays[0].container.opacity),0.5)
        view.clearImages(); precondition(view.overlays.isEmpty && (view.overlayRoot.sublayers ?? []).isEmpty)
        print("Native text: placement, clipping, order, opacity, motion, boundaries, cache reuse and visible failures passed")
    }
}
