import AppKit
import AVFoundation
import MediaToolbox

@main struct CheckGainFormats {
    static func main() {
        let gain = PlaybackGain([["id":"a","start":0.0,"length":1.0,"volume":1.0]])
        gain.update(["a":0.5])
        func format(_ bits:UInt32,_ floating:Bool)->AudioStreamBasicDescription {
            AudioStreamBasicDescription(mSampleRate:48000,mFormatID:kAudioFormatLinearPCM,
                mFormatFlags:kAudioFormatFlagIsPacked | (floating ? kAudioFormatFlagIsFloat : kAudioFormatFlagIsSignedInteger),
                mBytesPerPacket:bits/8,mFramesPerPacket:1,mBytesPerFrame:bits/8,mChannelsPerFrame:1,mBitsPerChannel:bits,mReserved:0)
        }
        func check<T:Equatable>(_ input:[T],_ expected:[T],bits:UInt32,floating:Bool) {
            var samples=input;gain.configure(format(bits,floating))
            samples.withUnsafeMutableBytes { raw in
                var buffer=AudioBufferList(mNumberBuffers:1,mBuffers:AudioBuffer(mNumberChannels:1,mDataByteSize:UInt32(2*MemoryLayout<T>.size),mData:raw.baseAddress))
                gain.apply(&buffer,frames:4,start:0)
            }
            precondition(samples==expected,"Gain or buffer bounds incorrect for \(bits) bits")
        }
        check([Int16(10000),-10000,12345,23456],[5000,-5000,12345,23456],bits:16,floating:false)
        check([Int32(100000),-100000,12345,23456],[50000,-50000,12345,23456],bits:32,floating:false)
        check([Float(1),-1,123,456],[0.5,-0.5,123,456],bits:32,floating:true)
        check([Double(1),-1,123,456],[0.5,-0.5,123,456],bits:64,floating:true)
        let faded = PlaybackGain([
            ["id":"a","start":0.0,"length":1.0,"volume":1.0,"fadeIn":0.2,"fadeOut":0.2],
            ["id":"b","start":1.0,"length":0.5,"volume":1.0,"fadeIn":1.0,"fadeOut":1.0,"fadeOffset":0.5,"fadeLength":2.0],
            ["id":"c","start":1.5,"length":1.0,"volume":1.0,"fadeIn":2.0,"fadeOut":2.0]
        ])
        func sample(_ time:Double,_ expected:Float) {
            var value:Float=1
            withUnsafeMutablePointer(to:&value) { pointer in
                var data=AudioBufferList(mNumberBuffers:1,mBuffers:AudioBuffer(mNumberChannels:1,mDataByteSize:4,mData:pointer))
                faded.apply(&data,frames:1,start:time)
            }
            precondition(abs(value-expected)<0.00001,"Fade at \(time): \(value) != \(expected)")
        }
        sample(0,0);sample(0.1,0.5);sample(0.5,1);sample(0.9,0.5)
        sample(1,0.5);sample(1.25,0.75);sample(1.75,0.1875);sample(2.5,0)
        faded.update(["b":0.25]);sample(1.25,0.1875)
        faded.update(["b":0]);sample(1.25,0)
        faded.update([:]);sample(1.25,0.75)
        let whole=PlaybackGain([["start":0.0,"length":2.0,"volume":1.0,"fadeIn":0.4,"fadeOut":0.4,"deClickLength":2.0]])
        let window=PlaybackGain([["start":0.0,"length":0.5,"volume":1.0,"fadeIn":0.4,"fadeOut":0.4,"fadeOffset":0.2,"fadeLength":2.0,"deClickOffset":0.2,"deClickLength":2.0]])
        for time in [0.0,0.001,0.1,0.499] {
            precondition(abs(whole.spans[0].envelope(at:time+0.2)-window.spans[0].envelope(at:time))<0.00001,"Window restarted the clip fade")
        }
        print("PASS: Float32/64, Int16/32, bounded writes, fades at cuts, trimmed/overlapping envelopes, live gain and restore")
    }
}
