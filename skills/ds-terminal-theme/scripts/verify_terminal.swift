// verify_terminal.swift - read-only verifier for Apple Terminal .terminal profiles.
//
// Build:  swiftc -O verify_terminal.swift -o verify_terminal
// Usage:  verify_terminal [--json] [--expect expect.json] [--register-terminal-fonts] FILE...
//   FILE is a .terminal plist (every <data> value is unarchived) or a raw
//   NSKeyedArchiver blob (*.bin, reported under key "-").
//   --expect JSON: {"<file basename>": {"<Key>": "rrggbb" | "rrggbbaa"}} ; prints
//   per-key errors (8-bit units, before rounding) and the max per file.
//   --register-terminal-fonts: registers Terminal.app/Contents/Resources/Fonts/*
//   for THIS process only (kCTFontManagerScopeProcess), then resolves font names.
// It never opens, imports or writes Terminal preferences.
import AppKit
import CoreText

var args = Array(CommandLine.arguments.dropFirst())
var json = false
var expectPath: String? = nil
var registerFonts = false
var files: [String] = []
var i = 0
while i < args.count {
    let a = args[i]
    if a == "--json" { json = true }
    else if a == "--expect" { i += 1; expectPath = args[i] }
    else if a == "--register-terminal-fonts" { registerFonts = true }
    else { files.append(a) }
    i += 1
}

if registerFonts {
    let dir = URL(fileURLWithPath: "/System/Applications/Utilities/Terminal.app/Contents/Resources/Fonts")
    let urls = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
    var ok = 0
    for u in urls where ["ttf", "otf"].contains(u.pathExtension.lowercased()) {
        var err: Unmanaged<CFError>?
        if CTFontManagerRegisterFontsForURL(u as CFURL, .process, &err) { ok += 1 }
    }
    FileHandle.standardError.write("registered \(ok) Terminal fonts for this process\n".data(using: .utf8)!)
}

var expect: [String: [String: String]] = [:]
if let p = expectPath, let d = FileManager.default.contents(atPath: p),
   let o = try? JSONSerialization.jsonObject(with: d) as? [String: [String: String]] { expect = o }

func hexToFloats(_ h: String) -> [Double] {
    var s = h.hasPrefix("#") ? String(h.dropFirst()) : h
    if s.count == 6 { s += "ff" }
    let v = UInt64(s, radix: 16)!
    return [Double((v >> 24) & 255), Double((v >> 16) & 255), Double((v >> 8) & 255), Double(v & 255)]
}

func modelName(_ m: NSColorSpace.Model) -> String {
    switch m {
    case .gray: return "gray"; case .rgb: return "rgb"; case .cmyk: return "cmyk"
    case .lab: return "lab"; case .deviceN: return "deviceN"; case .indexed: return "indexed"
    case .patterned: return "patterned"; default: return "unknown"
    }
}

func unarchive(_ data: Data) -> (Any?, String) {
    if let o = try? NSKeyedUnarchiver.unarchivedObject(ofClasses: [NSColor.self, NSFont.self], from: data) {
        return (o, "secure")
    }
    do {
        let u = try NSKeyedUnarchiver(forReadingFrom: data)
        u.requiresSecureCoding = false
        let o = u.decodeObject(forKey: NSKeyedArchiveRootObjectKey)
        u.finishDecoding()
        return (o, "insecure")
    } catch { return (nil, "error: \(error)") }
}

var results: [[String: Any]] = []
var maxErrByFile: [String: Double] = [:]

func report(file: String, key: String, data: Data) {
    let base = (file as NSString).lastPathComponent
    var r: [String: Any] = ["file": base, "key": key, "bytes": data.count]
    let (obj, path) = unarchive(data)
    r["decode"] = path
    if let c = obj as? NSColor {
        r["class"] = "NSColor"
        let cs = c.colorSpace
        r["colorSpace"] = cs.localizedName ?? "?"
        r["model"] = modelName(cs.colorSpaceModel)
        var native = [CGFloat](repeating: 0, count: c.numberOfComponents)
        c.getComponents(&native)
        r["native"] = native.map { Double($0) }
        if #available(macOS 26.0, *) { r["linearExposure"] = Double(c.linearExposure) }
        if let s = c.usingColorSpace(.sRGB) {
            let f = [s.redComponent, s.greenComponent, s.blueComponent, s.alphaComponent].map { Double($0) }
            r["srgb"] = f
            let b = f.map { Int(($0 * 255).rounded()) }
            r["hex"] = String(format: "%02x%02x%02x", b[0], b[1], b[2]) + (b[3] == 255 ? "" : String(format: "%02x", b[3]))
            if let e = expect[base]?[key] {
                let want = hexToFloats(e)
                let errs = (0..<4).map { abs(f[$0] * 255 - want[$0]) }
                let mx = errs.max()!
                r["expect"] = e
                r["err255"] = mx
                r["exact8bit"] = (0..<4).allSatisfy { b[$0] == Int(want[$0]) }
                maxErrByFile[base] = max(maxErrByFile[base] ?? 0, mx)
            }
        } else { r["hex"] = "unconvertible" }
    } else if let f = obj as? NSFont {
        r["class"] = "NSFont"
        r["fontName"] = f.fontName
        r["familyName"] = f.familyName ?? "?"
        r["pointSize"] = Double(f.pointSize)
        r["fixedPitch"] = f.isFixedPitch
        r["resolvesByName"] = NSFont(name: f.fontName, size: f.pointSize) != nil
        // AppKit silently substitutes a missing font (e.g. .AppleSystemUIFont), so
        // compare against the archived NSName string (first non-"$null" string object).
        if let pl = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
           let objs = pl["$objects"] as? [Any],
           let archived = objs.compactMap({ $0 as? String }).first(where: { $0 != "$null" }) {
            r["archivedName"] = archived
            r["substituted"] = archived != f.fontName
        }
    } else {
        r["class"] = obj.map { String(describing: type(of: $0)) } ?? "nil"
    }
    results.append(r)
    if !json {
        var line = "\(base) \(key): \(r["class"]!) [\(path)]"
        if r["class"] as? String == "NSColor" {
            let srgb = (r["srgb"] as? [Double])?.map { String(format: "%.6f", $0) }.joined(separator: " ") ?? "-"
            line += " space=\"\(r["colorSpace"]!)\" model=\(r["model"]!) sRGB=#\(r["hex"]!) (\(srgb))"
            if let le = r["linearExposure"] { line += " linExp=\(le)" }
            if let e = r["err255"] as? Double { line += String(format: " expect=#%@ err=%.4f/255 exact8=%@", r["expect"] as! String, e, (r["exact8bit"] as! Bool) ? "yes" : "NO") }
        } else if r["class"] as? String == "NSFont" {
            line += " name=\(r["fontName"]!) family=\(r["familyName"]!) size=\(r["pointSize"]!) fixedPitch=\(r["fixedPitch"]!) resolvesByName=\(r["resolvesByName"]!)"
            if let s = r["substituted"] as? Bool, s { line += " SUBSTITUTED(archived=\(r["archivedName"]!); rerun with --register-terminal-fonts or install the font)" }
        }
        print(line)
    }
}

for f in files {
    guard let d = FileManager.default.contents(atPath: f) else { print("cannot read \(f)"); continue }
    if let pl = try? PropertyListSerialization.propertyList(from: d, format: nil) as? [String: Any],
       pl["$archiver"] == nil {
        if !json {
            let scal = pl.filter { !($0.value is Data) }.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ", ")
            print("== \((f as NSString).lastPathComponent): \(scal)")
        }
        for k in pl.keys.sorted() { if let v = pl[k] as? Data { report(file: f, key: k, data: v) } }
    } else {
        report(file: f, key: "-", data: d)
    }
}

if json {
    let o: [String: Any] = ["results": results, "maxErr255ByFile": maxErrByFile]
    let d = try! JSONSerialization.data(withJSONObject: o, options: [.prettyPrinted, .sortedKeys])
    FileHandle.standardOutput.write(d)
    print("")
} else if !maxErrByFile.isEmpty {
    for (k, v) in maxErrByFile.sorted(by: { $0.key < $1.key }) { print(String(format: "MAX %@ err=%.4f/255", k, v)) }
}
