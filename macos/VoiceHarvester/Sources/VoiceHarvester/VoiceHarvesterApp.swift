import SwiftUI
import AppKit
import UniformTypeIdentifiers

@main
struct VoiceHarvesterApp: App {
    @StateObject private var model = HarvestModel()
    var body: some Scene {
        WindowGroup("Voice Harvester") {
            ContentView()
                .environmentObject(model)
                .frame(minWidth: 860, minHeight: 580)
                .background(Theme.bg)
                .preferredColorScheme(.dark)
                .onAppear { model.checkEnvironment() }
        }
        .windowStyle(.titleBar)
        .windowToolbarStyle(.unified)
        .commands { CommandGroup(replacing: .newItem) {} }
    }
}

// MARK: - Theme (iMovie-grade dark chrome)
enum Theme {
    static let bg = Color(red: 0.09, green: 0.09, blue: 0.11)
    static let panel = Color(red: 0.13, green: 0.13, blue: 0.16)
    static let panel2 = Color(red: 0.16, green: 0.16, blue: 0.19)
    static let stroke = Color.white.opacity(0.08)
    static let accent = Color(red: 0.20, green: 0.55, blue: 1.0)
    static let accent2 = Color(red: 0.45, green: 0.30, blue: 0.95)
    static let text = Color.white.opacity(0.92)
    static let dim = Color.white.opacity(0.55)
    static let good = Color(red: 0.25, green: 0.80, blue: 0.45)
    static let bad = Color(red: 1.0, green: 0.42, blue: 0.38)
}

// MARK: - Model
struct MediaItem: Identifiable, Equatable {
    let id = UUID()
    let url: URL
    var status: Status = .queued
    var detail: String = ""
    var outURL: URL?
    enum Status: Equatable { case queued, processing, done, failed }
    var name: String { url.lastPathComponent }
}

@MainActor
final class HarvestModel: ObservableObject {
    @Published var items: [MediaItem] = []
    @Published var useDemucs = true
    @Published var mergeAll = false
    @Published var outDir: URL = FileManager.default
        .homeDirectoryForCurrentUser.appendingPathComponent("VoiceHarvester_output")
    @Published var running = false
    @Published var progress = 0.0          // 0…1
    @Published var statusLine = "Ready"
    @Published var log: [String] = []
    @Published var ffmpegOK = true
    @Published var demucsOK = false

    private var task: Process?

    // Accepted media types.
    static let videoExt: Set<String> = ["mp4","mov","mkv","avi","webm","m4v","flv","wmv","mpg","mpeg"]
    static let audioExt: Set<String> = ["mp3","m4a","aac","wav","flac","ogg","opus","wma","aiff","aif"]
    static var allExt: Set<String> { videoExt.union(audioExt) }

    func add(urls: [URL]) {
        for u in urls {
            let ext = u.pathExtension.lowercased()
            guard Self.allExt.contains(ext), !items.contains(where: { $0.url == u }) else { continue }
            items.append(MediaItem(url: u))
        }
    }
    func remove(_ item: MediaItem) { items.removeAll { $0.id == item.id } }
    func clear() { items.removeAll() }

    // --- environment probe (ffmpeg / demucs) ---
    func checkEnvironment() {
        runPython(["--check"]) { line in
            if let o = Self.json(line), o["event"] as? String == "check" {
                Task { @MainActor in
                    self.ffmpegOK = o["ffmpeg"] as? Bool ?? false
                    self.demucsOK = o["demucs"] as? Bool ?? false
                    self.useDemucs = self.demucsOK
                    self.statusLine = self.ffmpegOK
                        ? (self.demucsOK ? "Ready · Demucs available" : "Ready · ffmpeg cleanup")
                        : "ffmpeg not found — install it to extract voice"
                }
            }
        } done: { _ in }
    }

    // --- run the extraction ---
    func run() {
        guard !running, !items.isEmpty, ffmpegOK else { return }
        running = true; progress = 0; log.removeAll()
        for i in items.indices { items[i].status = .queued; items[i].detail = "" }
        try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        var args = ["--out", outDir.path, "--demucs", useDemucs ? "1" : "0",
                    "--merge", mergeAll ? "1" : "0"]
        args += items.map { $0.url.path }

        runPython(args) { line in
            guard let o = Self.json(line) else { return }
            Task { @MainActor in self.handle(o) }
        } done: { _ in
            Task { @MainActor in
                self.running = false
                self.statusLine = "Done · saved to \(self.outDir.lastPathComponent)"
            }
        }
    }

    func cancel() { task?.terminate(); running = false; statusLine = "Cancelled" }

    private func handle(_ o: [String: Any]) {
        switch o["event"] as? String {
        case "start":
            statusLine = "Extracting…"
        case "file":
            if let i = o["i"] as? Int, let total = o["total"] as? Int {
                progress = Double(i - 1) / Double(max(1, total))
                if let name = o["name"] as? String,
                   let idx = items.firstIndex(where: { $0.name == name }) {
                    items[idx].status = .processing
                    statusLine = "Extracting \(name) (\(i)/\(total))"
                }
            }
        case "log":
            if let m = o["msg"] as? String { log.append(m); if log.count > 200 { log.removeFirst() } }
        case "result":
            let okv = o["ok"] as? Bool ?? false
            let src = (o["src"] as? String) ?? ""
            if let idx = items.firstIndex(where: { $0.url.path == src }) {
                items[idx].status = okv ? .done : .failed
                if let out = o["out"] as? String { items[idx].outURL = URL(fileURLWithPath: out) }
                let dur = o["duration"] as? Double ?? 0
                items[idx].detail = okv ? String(format: "%.1fs of clean voice", dur)
                                        : (o["message"] as? String ?? "failed")
            }
        case "done":
            progress = 1.0
        default: break
        }
    }

    // --- run python (the harvest_runner), streaming stdout lines ---
    private func runPython(_ args: [String], onLine: @escaping (String) -> Void,
                           done: @escaping (Int32) -> Void) {
        let repo = HarvestModel.repoRoot()
        let py = HarvestModel.pythonPath()
        let p = Process()
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = [py, "\(repo)/harvest_runner.py"] + args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        pipe.fileHandleForReading.readabilityHandler = { h in
            let s = String(data: h.availableData, encoding: .utf8) ?? ""
            for line in s.split(separator: "\n") { onLine(String(line)) }
        }
        p.terminationHandler = { proc in
            pipe.fileHandleForReading.readabilityHandler = nil
            done(proc.terminationStatus)
        }
        do { try p.run(); task = p } catch { done(-1) }
    }

    static func json(_ s: String) -> [String: Any]? {
        guard let d = s.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
    }
    static func repoRoot() -> String {
        // env override, else the repo this app ships from
        ProcessInfo.processInfo.environment["VOICE_HARVESTER_REPO"]
            ?? (NSHomeDirectory() + "/Documents/voice-harvester")
    }
    static func pythonPath() -> String {
        // prefer a venv with demucs if present, else system python3
        let venv = NSHomeDirectory() + "/.cognitive-twin/tts-venv/bin/python"
        return FileManager.default.fileExists(atPath: venv) ? venv : "python3"
    }
}
