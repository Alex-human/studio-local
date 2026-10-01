import AppKit

@main struct NativeReuseCheck {
    static func load(_ controller: PlaybackController, _ plan: [String:Any], frame: Int) throws -> ([String:Any],Double) {
        var result: Result<[String:Any],Error>?,started=Date()
        controller.load(plan,frame:frame){result=$0}
        let timeout=Date().addingTimeInterval(12)
        while result==nil && Date()<timeout { RunLoop.main.run(until:Date().addingTimeInterval(0.01)) }
        guard let result=result else { throw PlaybackFailure(message:"Timeout preparando reproducción") }
        return (try result.get(),Date().timeIntervalSince(started))
    }

    static func main() throws {
        func plan(_ argument: String) throws -> [String:Any] {
            try JSONSerialization.jsonObject(with:Data(contentsOf:URL(fileURLWithPath:argument))) as! [String:Any]
        }
        let controller=PlaybackController()
        let first=try load(controller,plan(CommandLine.arguments[1]),frame:0)
        let second=try load(controller,plan(CommandLine.arguments[2]),frame:0)
        let expectedReuse=CommandLine.arguments.count<4 || CommandLine.arguments[3]=="true"
        precondition((second.0["reused"] as? Bool ?? false) == expectedReuse)
        precondition(second.1 < (expectedReuse ? 0.25 : 0.75))
        print(String(data:try JSONSerialization.data(withJSONObject:[
            "initialSeconds":first.1,"updateSeconds":second.1,"reused":expectedReuse
        ],options:[.sortedKeys]),encoding:.utf8)!)
    }
}
