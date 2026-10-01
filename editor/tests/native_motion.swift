import AppKit

@main struct NativeMotionCheck {
    static func main() throws {
        let fixtureURL=URL(fileURLWithPath:CommandLine.arguments[1])
        let fixture=try JSONSerialization.jsonObject(with:Data(contentsOf:fixtureURL)) as! [String:Any]
        let cases=fixture["cases"] as! [[String:Any]], width=fixture["width"] as! Int, height=fixture["height"] as! Int
        let view=PlaybackView(frame:NSRect(x:0,y:0,width:width,height:height))
        view.layoutSubtreeIfNeeded()
        func near(_ actual:Double,_ expected:Double,_ label:String) {
            precondition(abs(actual-expected)<0.00001,"\(label): \(actual) != \(expected)")
        }
        for test in cases {
            let name=test["name"] as! String, spec=test["spec"] as! [String:Any], frame=test["frame"] as! Int
            try view.configureImages([spec],width:width,height:height)
            view.updateImages(frame:frame,fps:30)
            let overlay=view.overlays[0]
            let expected=test["expected"] as! [String:Any]
            let local=Double(frame-(spec["start"] as! Int))+(spec["offset"] as! NSNumber).doubleValue
            let props=overlay.properties(at:local)
            for (key,value) in expected["props"] as! [String:Double] {
                near((props[key] as! NSNumber).doubleValue,value,"\(name) property \(key)")
            }
            for (actual,key) in [(overlay.container.bounds.width,"width"),(overlay.container.bounds.height,"height"),
                                  (overlay.container.position.x,"x"),(overlay.container.position.y,"y"),
                                  (Double(overlay.container.opacity),"opacity"),
                                  (overlay.image.contentsRect.minX,"cropX"),(overlay.image.contentsRect.minY,"cropY"),
                                  (overlay.image.contentsRect.width,"cropWidth"),(overlay.image.contentsRect.height,"cropHeight")] {
                near(actual,(expected[key] as! NSNumber).doubleValue,"\(name) \(key)")
            }
            let context=CGContext(data:nil,width:width,height:height,bitsPerComponent:8,bytesPerRow:width*4,
                                  space:CGColorSpace(name:CGColorSpace.sRGB)!,bitmapInfo:CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.setFillColor(NSColor(srgbRed:40/255,green:50/255,blue:60/255,alpha:1).cgColor)
            context.fill(CGRect(x:0,y:0,width:width,height:height))
            view.overlayRoot.render(in:context)
            let bitmap=NSBitmapImageRep(cgImage:context.makeImage()!)
            try bitmap.representation(using:.png,properties:[:])!.write(to:fixtureURL.deletingLastPathComponent().appendingPathComponent(name+"-native.png"))
            view.updateImages(frame:(spec["start"] as! Int)-1,fps:30)
            precondition(overlay.container.isHidden)
            view.updateImages(frame:(spec["start"] as! Int)+(spec["length"] as! Int),fps:30)
            precondition(overlay.container.isHidden)
        }
        print("PASS native image keyframes, crop pixels, geometry, phase, opacity and boundaries: \(cases.count) cases")
    }
}
