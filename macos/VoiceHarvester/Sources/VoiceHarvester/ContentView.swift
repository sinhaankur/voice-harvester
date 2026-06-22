import SwiftUI
import AppKit
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject var model: HarvestModel

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().overlay(Theme.stroke)
            HSplitView {
                // LEFT: import + media list
                mediaPane
                    .frame(minWidth: 460)
                // RIGHT: options + action + log
                sidePane
                    .frame(minWidth: 300, maxWidth: 380)
            }
        }
        .background(Theme.bg)
    }

    // MARK: header
    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 9)
                    .fill(LinearGradient(colors: [Theme.accent, Theme.accent2],
                                         startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 34, height: 34)
                Image(systemName: "waveform").foregroundStyle(.white).font(.system(size: 16, weight: .bold))
            }
            VStack(alignment: .leading, spacing: 1) {
                Text("Voice Harvester").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.text)
                Text("Extract a clean voice for AI cloning").font(.system(size: 11)).foregroundStyle(Theme.dim)
            }
            Spacer()
            envBadge
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(Theme.panel)
    }

    private var envBadge: some View {
        HStack(spacing: 8) {
            badge(model.ffmpegOK ? "checkmark.circle.fill" : "exclamationmark.triangle.fill",
                  "ffmpeg", model.ffmpegOK ? Theme.good : Theme.bad)
            badge(model.demucsOK ? "checkmark.circle.fill" : "circle",
                  "Demucs", model.demucsOK ? Theme.good : Theme.dim)
        }
    }
    private func badge(_ icon: String, _ label: String, _ color: Color) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 10)).foregroundStyle(color)
            Text(label).font(.system(size: 10, design: .monospaced)).foregroundStyle(Theme.dim)
        }
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(Capsule().fill(Theme.panel2))
    }

    // MARK: media pane (drop zone + list)
    private var mediaPane: some View {
        VStack(spacing: 0) {
            if model.items.isEmpty {
                dropZone
            } else {
                ScrollView {
                    LazyVStack(spacing: 8) {
                        ForEach(model.items) { item in MediaRow(item: item) }
                    }
                    .padding(14)
                }
            }
            // bottom toolbar
            HStack(spacing: 10) {
                Button { addFiles() } label: { Label("Add Media", systemImage: "plus") }
                    .buttonStyle(ToolbarButton())
                if !model.items.isEmpty {
                    Button { model.clear() } label: { Label("Clear", systemImage: "trash") }
                        .buttonStyle(ToolbarButton())
                }
                Spacer()
                Text("\(model.items.count) item\(model.items.count == 1 ? "" : "s")")
                    .font(.system(size: 11)).foregroundStyle(Theme.dim)
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(Theme.panel)
        }
        .background(Theme.bg)
        .onDrop(of: [.fileURL], isTargeted: nil) { providers in handleDrop(providers); return true }
    }

    private var dropZone: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "tray.and.arrow.down")
                .font(.system(size: 46, weight: .light))
                .foregroundStyle(LinearGradient(colors: [Theme.accent, Theme.accent2],
                                                startPoint: .top, endPoint: .bottom))
            Text("Drop video or audio here")
                .font(.system(size: 16, weight: .medium)).foregroundStyle(Theme.text)
            Text("or click Add Media — they're processed locally, nothing is uploaded")
                .font(.system(size: 12)).foregroundStyle(Theme.dim)
            Button { addFiles() } label: { Text("Add Media…") }
                .buttonStyle(PrimaryButton(compact: true))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [7, 6]))
                .foregroundStyle(Theme.stroke)
                .padding(16)
        )
    }

    // MARK: side pane (options + run + log)
    private var sidePane: some View {
        VStack(alignment: .leading, spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    sectionTitle("Quality")
                    Toggle(isOn: $model.useDemucs) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("AI voice isolation (Demucs)").foregroundStyle(Theme.text)
                            Text(model.demucsOK ? "Best — separates voice from music/noise"
                                                : "Install Demucs to enable").font(.caption).foregroundStyle(Theme.dim)
                        }
                    }
                    .toggleStyle(.switch).tint(Theme.accent)
                    .disabled(!model.demucsOK)

                    Toggle(isOn: $model.mergeAll) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Merge into one sample").foregroundStyle(Theme.text)
                            Text("Combine all clips for richer cloning").font(.caption).foregroundStyle(Theme.dim)
                        }
                    }
                    .toggleStyle(.switch).tint(Theme.accent)

                    sectionTitle("Output")
                    HStack {
                        Image(systemName: "folder").foregroundStyle(Theme.dim)
                        Text(model.outDir.lastPathComponent).foregroundStyle(Theme.text).lineLimit(1)
                        Spacer()
                        Button("Change") { pickOut() }.buttonStyle(ToolbarButton())
                    }
                    .padding(10).background(RoundedRectangle(cornerRadius: 8).fill(Theme.panel2))

                    if !model.log.isEmpty {
                        sectionTitle("Activity")
                        logView
                    }
                }
                .padding(16)
            }

            Spacer()
            // action bar
            VStack(spacing: 10) {
                if model.running {
                    ProgressView(value: model.progress)
                        .tint(Theme.accent)
                }
                Text(model.statusLine).font(.system(size: 11)).foregroundStyle(Theme.dim)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if model.running {
                    Button { model.cancel() } label: { Text("Cancel").frame(maxWidth: .infinity) }
                        .buttonStyle(PrimaryButton(destructive: true))
                } else {
                    Button { model.run() } label: {
                        Label("Extract Voice", systemImage: "wand.and.stars").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(PrimaryButton())
                    .disabled(model.items.isEmpty || !model.ffmpegOK)
                }
            }
            .padding(16)
            .background(Theme.panel)
        }
        .background(Theme.panel.opacity(0.4))
    }

    private var logView: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Array(model.log.suffix(8).enumerated()), id: \.offset) { _, line in
                Text(line).font(.system(size: 10, design: .monospaced))
                    .foregroundStyle(Theme.dim).lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.black.opacity(0.3)))
    }

    private func sectionTitle(_ t: String) -> some View {
        Text(t.uppercased()).font(.system(size: 10, weight: .semibold, design: .monospaced))
            .foregroundStyle(Theme.dim).tracking(1)
    }

    // MARK: actions
    private func addFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [.movie, .audio, .mpeg4Movie, .quickTimeMovie, .wav, .mp3, .mpeg4Audio]
        if panel.runModal() == .OK { model.add(urls: panel.urls) }
    }
    private func pickOut() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false
        if panel.runModal() == .OK, let u = panel.url { model.outDir = u }
    }
    private func handleDrop(_ providers: [NSItemProvider]) {
        for p in providers {
            _ = p.loadObject(ofClass: URL.self) { url, _ in
                if let url { Task { @MainActor in model.add(urls: [url]) } }
            }
        }
    }
}

// MARK: - Media row
struct MediaRow: View {
    @EnvironmentObject var model: HarvestModel
    let item: MediaItem
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8).fill(Theme.panel2).frame(width: 42, height: 42)
                Image(systemName: HarvestModel.videoExt.contains(item.url.pathExtension.lowercased())
                      ? "film" : "music.note")
                    .foregroundStyle(Theme.dim)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name).foregroundStyle(Theme.text).lineLimit(1)
                Text(statusText).font(.caption).foregroundStyle(statusColor)
            }
            Spacer()
            statusIcon
            if item.status == .done, item.outURL != nil {
                Button { revealOutput() } label: { Image(systemName: "arrow.up.forward.app") }
                    .buttonStyle(.plain).foregroundStyle(Theme.accent).help("Reveal in Finder")
            }
            Button { model.remove(item) } label: { Image(systemName: "xmark") }
                .buttonStyle(.plain).foregroundStyle(Theme.dim)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.panel))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Theme.stroke))
    }
    private var statusText: String {
        switch item.status {
        case .queued: return "Queued"
        case .processing: return "Extracting voice…"
        case .done: return item.detail.isEmpty ? "Done" : item.detail
        case .failed: return item.detail.isEmpty ? "Failed" : item.detail
        }
    }
    private var statusColor: Color {
        switch item.status {
        case .done: return Theme.good
        case .failed: return Theme.bad
        case .processing: return Theme.accent
        default: return Theme.dim
        }
    }
    @ViewBuilder private var statusIcon: some View {
        switch item.status {
        case .processing: ProgressView().controlSize(.small)
        case .done: Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.good)
        case .failed: Image(systemName: "exclamationmark.circle.fill").foregroundStyle(Theme.bad)
        default: Image(systemName: "clock").foregroundStyle(Theme.dim)
        }
    }
    private func revealOutput() {
        if let u = item.outURL { NSWorkspace.shared.activateFileViewerSelecting([u]) }
    }
}

// MARK: - Button styles
struct PrimaryButton: ButtonStyle {
    var compact = false
    var destructive = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: compact ? 13 : 14, weight: .semibold))
            .foregroundStyle(.white)
            .padding(.vertical, compact ? 8 : 11).padding(.horizontal, compact ? 16 : 12)
            .background(
                RoundedRectangle(cornerRadius: 9)
                    .fill(destructive
                          ? AnyShapeStyle(Theme.bad)
                          : AnyShapeStyle(LinearGradient(colors: [Theme.accent, Theme.accent2],
                                          startPoint: .leading, endPoint: .trailing)))
                    .opacity(configuration.isPressed ? 0.8 : 1)
            )
    }
}
struct ToolbarButton: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .medium)).foregroundStyle(Theme.text)
            .padding(.vertical, 6).padding(.horizontal, 11)
            .background(RoundedRectangle(cornerRadius: 7).fill(Theme.panel2)
                .opacity(configuration.isPressed ? 0.6 : 1))
    }
}
