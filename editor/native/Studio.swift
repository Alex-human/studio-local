import AppKit
import WebKit
import UniformTypeIdentifiers

final class Studio: NSObject, NSApplicationDelegate, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var root: URL!
    var playback: PlaybackController?
    var running: [String: Process] = [:]
    var preparations: [String: String] = [:]
    var cancelledPreparations = Set<String>()
    var waitingForSave = false
    var installingUpdate = false
    var interfaceSignature = ""
    var updateTimer: Timer?
    func uiSignature() -> String {
        return (try? String(contentsOf: root.appendingPathComponent(".build/interface-version"), encoding: .utf8)) ?? ""
    }
    func checkUpdates() {
        guard !waitingForSave, !installingUpdate, window.attachedSheet == nil else { return }
        let kind = FileManager.default.fileExists(atPath: root.appendingPathComponent(".build/pending-update.json").path) ? "native" : (uiSignature() != interfaceSignature ? "interface" : "")
        if !kind.isEmpty { web.evaluateJavaScript("window.studioRequestUpdate && window.studioRequestUpdate('\(kind)')", completionHandler: nil) }
    }
    var python: String { root.appendingPathComponent(".venv/bin/python3").path }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let rootFile = Bundle.main.resourceURL!.appendingPathComponent("root.txt")
        root = URL(fileURLWithPath: (try! String(contentsOf: rootFile, encoding: .utf8)).trimmingCharacters(in: .whitespacesAndNewlines))
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "studio")
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 940),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String ?? "Studio Local"
        window.minSize = NSSize(width: 1000, height: 700)
        window.backgroundColor = NSColor(calibratedRed: 0.06, green: 0.075, blue: 0.09, alpha: 1)
        window.contentView = web
        window.delegate = self
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        let mainMenu = NSMenu()
        let appItem = NSMenuItem(); mainMenu.addItem(appItem)
        let appMenu = NSMenu(); appMenu.addItem(withTitle: "Salir de Studio Local", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        let editItem = NSMenuItem(); mainMenu.addItem(editItem)
        let editMenu = NSMenu(title: "Edición")
        let copy = editMenu.addItem(withTitle: "Marcar corte / Copiar", action: #selector(copyFromMenu(_:)), keyEquivalent: "c"); copy.target = self
        let paste = editMenu.addItem(withTitle: "Pegar", action: #selector(pasteFromMenu(_:)), keyEquivalent: "v"); paste.target = self
        editMenu.addItem(withTitle: "Seleccionar todo", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editMenu.addItem(NSMenuItem.separator())
        let link = editMenu.addItem(withTitle: "Vincular todo al vídeo", action: #selector(linkAllFromMenu(_:)), keyEquivalent: "j"); link.target = self
        let feedbackItem = editMenu.addItem(withTitle: "Añadir feedback", action: #selector(feedbackFromMenu(_:)), keyEquivalent: "f"); feedbackItem.target = self
        editItem.submenu = editMenu; NSApp.mainMenu = mainMenu
        interfaceSignature = uiSignature()
        updateTimer = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in self?.checkUpdates() }
        web.loadFileURL(root.appendingPathComponent("ui/index.html"), allowingReadAccessTo: URL(fileURLWithPath: "/"))
    }

    @objc func pasteFromMenu(_ sender: Any?) {
        if window.attachedSheet != nil { NSApp.sendAction(#selector(NSText.paste(_:)), to: nil, from: sender); return }
        web.evaluateJavaScript("window.studioPaste ? window.studioPaste() : false") { handled, _ in
            if (handled as? Bool) != true { NSApp.sendAction(#selector(NSText.paste(_:)), to: nil, from: sender) }
        }
    }

    @objc func copyFromMenu(_ sender: Any?) {
        if window.attachedSheet != nil { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: sender); return }
        web.evaluateJavaScript("window.studioMarkRange ? window.studioMarkRange() : false") { handled, _ in
            if (handled as? Bool) != true { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: sender) }
        }
    }

    @objc func feedbackFromMenu(_ sender: Any?) {
        guard window.attachedSheet == nil else { return }
        web.evaluateJavaScript("window.studioFeedback && window.studioFeedback()", completionHandler: nil)
    }
    @objc func linkAllFromMenu(_ sender: Any?) {
        guard window.attachedSheet == nil else { return }
        web.evaluateJavaScript("window.studioLinkAll && window.studioLinkAll()", completionHandler: nil)
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        // The editor never navigates to remote sites or runs downloaded UI.
        if let url = navigationAction.request.url, url.isFileURL { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }

    func reply(_ id: String, _ result: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: result), let json = String(data: data, encoding: .utf8),
              let idData = try? JSONSerialization.data(withJSONObject: [id]), let idJSON = String(data: idData, encoding: .utf8) else { return }
        DispatchQueue.main.async { self.web.evaluateJavaScript("window.studioReply(\(idJSON)[0], \(json))", completionHandler: nil) }
    }

    func playbackController() -> PlaybackController {
        if let playback = playback { return playback }
        let controller = PlaybackController()
        playback = controller; web.addSubview(controller.view)
        controller.event = { [weak self] event in
            guard let data = try? JSONSerialization.data(withJSONObject: event), let json = String(data: data, encoding: .utf8) else { return }
            self?.web.evaluateJavaScript("window.studioPlaybackEvent && window.studioPlaybackEvent(\(json))", completionHandler: nil)
        }
        return controller
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let id = body["id"] as? String, var request = body["request"] as? [String: Any] else { return }
        let action = request["action"] as? String ?? ""
        if action == "capabilities" {
            reply(id,["ok":true,"result":["feedback":true,"playbackRate":true,"projectFolders":true,"nativeText":true,"interactivePlayback":true,"videoOverlays":true,"version":"1.14.1"]])
        } else if action == "cancelPreparation" {
            if let token = request["preparation"] as? String {
                for (job, value) in preparations where value == token {
                    cancelledPreparations.insert(job)
                    if let process = running[job], process.isRunning { process.terminate() }
                }
            }
            reply(id,["ok":true,"result":[:]])
        } else if action == "loadPlayback", let plan = request["plan"] as? [String: Any] {
            playbackController().load(plan, frame: request["frame"] as? Int ?? 0) { result in
                switch result {
                case .success(let value): self.reply(id, ["ok": true, "result": value])
                case .failure(let error): self.reply(id, ["ok": false, "error": error.localizedDescription])
                }
            }
        } else if action == "queuePlayback", let plan=request["plan"] as? [String:Any],let key=request["afterKey"] as? String {
            playbackController().queue(plan,afterKey:key) { result in
                switch result {
                case .success(let value):self.reply(id,["ok":true,"result":value])
                case .failure(let error):self.reply(id,["ok":false,"error":error.localizedDescription])
                }
            }
        } else if action == "playback" {
            let playback = playbackController()
            let command = request["command"] as? String
            if command == "rate" || (command == "play" && request["rate"] != nil) {
                guard let rate = request["rate"] as? NSNumber, CFGetTypeID(rate) != CFBooleanGetTypeID() else {
                    reply(id,["ok":false,"error":"La velocidad de revisión debe ser un número entre 1 y 2×."]); return
                }
                do { try playback.setPlaybackRate(rate.doubleValue) }
                catch { reply(id,["ok":false,"error":error.localizedDescription]); return }
            }
            if let rect = request["rect"] as? [String: Double] { playback.position(rect,height: web.bounds.height) }
            switch command {
            case "freeze":
                playback.pause()
                if let t = playback.timeline {
                    let seconds = playback.player.currentTime().seconds
                    if seconds.isFinite { self.reply(id,["ok":true,"result":["frame":t.origin+min(t.frames-1,max(0,Int(floor(seconds*t.fps))))]]); return }
                }
                reply(id,["ok":false,"error":"No se pudo fijar el fotograma"]); return
            case "levels": playback.setVolumes(request["levels"] as? [String: Double] ?? [:], key: request["key"] as? String ?? "")
            case "play": playback.play()
            case "pause": playback.pause()
            case "invalidate": playback.generation += 1; playback.discardQueued(); playback.pause()
            case "seek": playback.seek(request["frame"] as? Int ?? 0) { self.reply(id,["ok":true,"result":[:]]) }; return
            case "stop": playback.stop()
            default: break
            }
            reply(id,["ok":true,"result":["rate":playback.playbackRate]])
        } else if action == "applyUpdate" {
            if request["kind"] as? String == "native" {
                installingUpdate = true
                reply(id, ["ok": true, "result": [:]])
                NSApp.terminate(nil)
            } else {
                interfaceSignature = uiSignature()
                reply(id, ["ok": true, "result": [:]])
                DispatchQueue.main.async { self.web.reloadFromOrigin() }
            }
        } else if action == "quitReady" {
            var allow = request["allow"] as? Bool ?? false
            if allow && installingUpdate {
                do {
                    let installer = Process(); installer.executableURL = URL(fileURLWithPath: python)
                    installer.arguments = [root.appendingPathComponent("engine/install_update.py").path, "--wait-pid", String(ProcessInfo.processInfo.processIdentifier)]
                    let log = root.appendingPathComponent(".build/update.log")
                    FileManager.default.createFile(atPath: log.path, contents: nil)
                    let output = try FileHandle(forWritingTo: log); installer.standardOutput = output; installer.standardError = output
                    try installer.run()
                } catch { allow = false; installingUpdate = false }
            }
            if !allow { installingUpdate = false; web.evaluateJavaScript("window.studioUpdateCancelled && window.studioUpdateCancelled()", completionHandler: nil) }
            reply(id, ["ok": true, "result": [:]])
            waitingForSave = false
            DispatchQueue.main.async { NSApp.reply(toApplicationShouldTerminate: allow) }
        } else if action == "pasteImage" {
            let board = NSPasteboard.general
            let png = board.data(forType: .png) ?? board.data(forType: .tiff).flatMap { NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) }
            if let png = png {
                request["action"] = "importImageData"; request["png"] = png.base64EncodedString(); execute(id, request)
            } else if let urls = board.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], let url = urls.first, ["png","jpg","jpeg","webp","tiff"].contains(url.pathExtension.lowercased()) {
                request["action"] = "import"; request["path"] = url.path; execute(id, request)
            } else { reply(id, ["ok": false, "error": "Copia una imagen o captura antes de pegar. En Mac: Control + Mayúsculas + Comando + 4 captura directamente al portapapeles."]) }
        } else if action == "chooseSfx" || action == "chooseMusic" {
            let role = action == "chooseSfx" ? "sfx" : "music"
            request["libraryRole"] = role
            let importRequest = request
            execute(id, ["action":"audioLibrary", "role":role]) { result in
                guard result["ok"] as? Bool == true, let value = result["result"] as? [String:Any], let directory = value["directory"] as? String else { self.reply(id, result); return }
                self.chooseFile(id, importRequest, directory: URL(fileURLWithPath: directory))
            }
        } else if ["chooseImport", "chooseCaptions", "chooseProject", "chooseOverlay", "chooseOverlayReplacement"].contains(action) {
            if action == "chooseOverlay" || action == "chooseOverlayReplacement" { request["overlay"] = true }
            chooseFile(id, request)
        } else if action == "reveal", let path = request["path"] as? String {
            NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
            reply(id, ["ok": true, "result": [:]])
        } else if action == "cancel" {
            playback?.stop()
            for process in running.values { if process.isRunning { process.terminate() } }
            reply(id, ["ok": true, "result": [:]])
        } else { execute(id, request) }
    }

    func chooseFile(_ id: String, _ original: [String:Any], directory: URL? = nil) {
        var request = original
        let action = request["action"] as? String ?? ""
        let panel = NSOpenPanel(); panel.canChooseDirectories = false; panel.allowsMultipleSelection = false
        if action == "chooseOverlay" || action == "chooseOverlayReplacement" {
            panel.allowedContentTypes = [.movie]
            panel.title = action == "chooseOverlay" ? "Superponer vídeo" : "Cambiar vídeo de la superposición"
            panel.prompt = action == "chooseOverlay" ? "Superponer" : "Cambiar"
            panel.message = "Se añade sobre la pista principal. Podrás moverlo y cambiar su tamaño en el visor."
        } else if let directory = directory {
            panel.allowedContentTypes = [.audio]; panel.directoryURL = directory
            panel.title = action == "chooseMusic" ? "Añadir música" : "Añadir efecto de sonido"
            panel.prompt = "Añadir"
            panel.message = action == "chooseMusic" ? "Escucha con la barra espaciadora. Los créditos están en la carpeta Música. Los audios nuevos se guardan aquí." : "Escucha con la barra espaciadora. Los efectos nuevos se guardan en esta biblioteca."
        } else {
            panel.message = action == "chooseProject" ? "Abrir proyecto .studio" : (action == "chooseCaptions" ? "Importar subtítulos SRT" : "Añadir un vídeo, imagen o audio al proyecto")
        }
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let url = panel.url else { self.reply(id, ["ok": false, "cancelled": true, "error": "Selección cancelada"]); return }
            if action == "chooseProject" { request["action"] = "open"; request["project"] = url.path }
            else { request["action"] = action == "chooseCaptions" ? "captions" : "import"; request["path"] = url.path }
            self.execute(id, request)
        }
    }

    func execute(_ id: String, _ request: [String: Any], completion: (([String:Any]) -> Void)? = nil) {
        let respond: ([String:Any]) -> Void = { result in
            DispatchQueue.main.async { if let completion = completion { completion(result) } else { self.reply(id, result) } }
        }
        let allowed = ["feedback", "poll", "sessionRead", "sessionSave", "list", "projectFolders", "create", "open", "import", "importImageData", "audioLibrary", "previewSound", "ops", "undo", "redo", "captions", "frame", "thumbnail", "render", "analyze", "preparePlayback"]
        guard let action = request["action"] as? String, allowed.contains(action) else { respond(["ok": false, "error": "Operación no admitida"]); return }
        var compatibleRequest = request
        if action == "preparePlayback" {
            compatibleRequest["nativeImages"] = true; compatibleRequest["nativeText"] = true
            compatibleRequest["nativeMotion"] = true; compatibleRequest["nativeVideo"] = true; compatibleRequest["interactive"] = true; compatibleRequest["nativeLut"] = true; compatibleRequest["nativeRetime"] = true
        }
        guard let data = try? JSONSerialization.data(withJSONObject: compatibleRequest) else { respond(["ok": false, "error": "Operación no admitida"]); return }
        let process = Process(); process.executableURL = URL(fileURLWithPath: python)
        process.arguments = [root.appendingPathComponent("engine/editor.py").path]
        let input = Pipe(), output = Pipe(), errors = Pipe()
        _ = fcntl(input.fileHandleForWriting.fileDescriptor,F_SETNOSIGPIPE,1)
        process.standardInput = input; process.standardOutput = output; process.standardError = errors
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"; process.environment = env
        running[id] = process
        if action == "preparePlayback", let token = request["preparation"] as? String { preparations[id] = token }
        // Launch on the owner queue: a cancellation cannot race a not-yet-run process.
        do { try process.run() }
        catch { running.removeValue(forKey:id); preparations.removeValue(forKey:id); respond(["ok":false,"error":error.localizedDescription]); return }
        DispatchQueue.global(qos: .userInitiated).async {
                try? input.fileHandleForWriting.write(contentsOf:data); try? input.fileHandleForWriting.close()
                // Drain stderr concurrently so an error can never fill its pipe and freeze an export.
                let group = DispatchGroup(); group.enter()
                DispatchQueue.global().async { _ = errors.fileHandleForReading.readDataToEndOfFile(); group.leave() }
                let bytes = output.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit(); group.wait()
                DispatchQueue.main.async {
                    let cancelled = self.cancelledPreparations.remove(id) != nil
                    self.running.removeValue(forKey:id); self.preparations.removeValue(forKey:id)
                    if cancelled { respond(["ok":false,"cancelled":true,"error":"Preparación cancelada"] ) }
                    else if let result = try? JSONSerialization.jsonObject(with:bytes) as? [String:Any] { respond(result) }
                    else { respond(["ok":false,"error":"No se pudo completar la operación. Comprueba los medios y el motor local."]) }
                }
        }
    }
    func windowShouldClose(_ sender: NSWindow) -> Bool { NSApp.terminate(nil); return false }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if waitingForSave { return .terminateLater }
        waitingForSave = true
        web.evaluateJavaScript("window.studioPrepareToQuit ? window.studioPrepareToQuit() : false") { handled, error in
            if error != nil || (handled as? Bool) != true {
                self.waitingForSave = false
                self.installingUpdate = false
                let alert = NSAlert(); alert.messageText = "No se pudo confirmar el guardado"; alert.informativeText = "El editor sigue abierto para conservar los cambios pendientes."; alert.beginSheetModal(for: self.window)
                sender.reply(toApplicationShouldTerminate: false)
            }
        }
        return .terminateLater
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { playback?.stop(); for p in running.values { if p.isRunning { p.terminate() } } }
}
@main struct StudioApplication {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let delegate = Studio()
        app.delegate = delegate
        withExtendedLifetime(delegate) { app.run() }
    }
}
