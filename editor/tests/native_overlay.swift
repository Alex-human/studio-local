import AppKit

@main struct NativeOverlayCheck {
    static func main() throws {
        let plan = try JSONSerialization.jsonObject(with: Data(contentsOf:
            URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let images = plan["images"] as! [[String: Any]]
        precondition(!images.isEmpty)
        let view = PlaybackView(frame: NSRect(x: 0, y: 0, width: 960, height: 540))
        view.layoutSubtreeIfNeeded()
        try view.configureImages(images, width: plan["width"] as! Int, height: plan["height"] as! Int)
        let first = images[0], start = first["start"] as! Int
        view.updateImages(frame: start + 60, fps: plan["fps"] as! Double)
        let visible = view.overlays.filter { !$0.container.isHidden }
        precondition(visible.count == 1)
        precondition(visible[0].container.bounds.width > 20)
        precondition(visible[0].container.opacity > 0.99)
        let snapshotWidth=max(1,Int(visible[0].container.bounds.width.rounded())),snapshotHeight=max(1,Int(visible[0].container.bounds.height.rounded()))
        if CommandLine.arguments.count>2,
           let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:snapshotWidth,pixelsHigh:snapshotHeight,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0),
           let context=NSGraphicsContext(bitmapImageRep:bitmap) {
            visible[0].container.render(in:context.cgContext)
            try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:CommandLine.arguments[2]))
        }
        view.updateImages(frame: start - 1, fps: plan["fps"] as! Double)
        precondition(view.overlays.allSatisfy { $0.container.isHidden })
        print(String(data: try JSONSerialization.data(withJSONObject: [
            "images": images.count,
            "visibleAtRest": visible.count,
            "width": visible[0].container.bounds.width,
            "positionX": visible[0].container.position.x,
            "positionY": visible[0].container.position.y
        ], options: [.sortedKeys]), encoding: .utf8)!)
    }
}
