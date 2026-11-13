# The .terminal format (Terminal 2.15, macOS 26)

Source: format research, verified with AppKit on a Mac.

## File

An XML property list (a dict). Keys that the script writes:

| Key | Value |
|---|---|
| `type` | "Window Settings" |
| `name` | profile name (the file name stem is the same) |
| `ProfileCurrentVersion` | 2.09 |
| `Font` | NSFont archive: `{NSName, NSSize, NSfFlags 16}` |
| 16 `ANSI*Color`, `BackgroundColor`, `TextColor`, `TextBoldColor`, `CursorColor`, `SelectionColor` | NSColor archives |
| `FontAntialias` true, `FontWidthSpacing` 1.0, `FontHeightSpacing` 1.0 | |
| `UseBoldFonts` true, `UseBrightBold` false, `BlinkText` false | |
| `DisableANSIColor` false, `DynamicANSIForegroundColors` false | |
| `CursorType` (0 block, 1 underline, 2 bar), `CursorBlink` | |
| `BackgroundBlur` | 0.0 (no blur) |
| `columnCount`, `rowCount` | only with `--columns`, `--rows` |

The `BackgroundColor` alpha is 1 (opaque). It is lower only with `--translucent ALPHA`.

Never write `CursorTextColor`: Terminal has no such key. Terminal has no key for the color of
selected text either.

## Color archive

Each color is a binary NSKeyedArchiver plist (`$version` 100000) that holds:

- `NSColorSpace` 1
- `NSComponents` = "r g b a" (sRGB, `%.10g`, no NUL, alpha always present)
- `NSRGB` = Generic RGB fallback "r g b" + NUL (alpha only when it is not 1)
- `NSCustomColorSpace` = `{NSID 7, NSICC <bytes of /System/Library/ColorSync/Profiles/sRGB Profile.icc>}`
- `NSLinearExposure` = "1"

On a computer without that ICC file (Linux), the script writes `{NSID 7}` with no `NSICC`. macOS 26
decodes it the same (17 of 17 colors exact). The NSRGB fallback uses an embedded matrix that was fitted
to AppKit's output (error 0.003/255). macOS 26 ignores NSRGB when NSComponents is present.

Never put sRGB numbers into a Generic RGB color (`NSColorSpace` 1 with no custom color space): the
colors shift by up to 63/255.

## Verify on a Mac

```sh
swiftc -O scripts/verify_terminal.swift -o scripts/verify_terminal
scripts/verify_terminal --register-terminal-fonts "OUT/Name Dark.terminal"
plutil -lint "OUT/Name Dark.terminal"
```

`verify_terminal` decodes every color with AppKit, converts it to sRGB and prints the error. It does not
open or import the profile. Use `swiftc`, not the `swift` interpreter.

## Fonts

`SFMonoTerminal-Regular` (the default) is bundled in Terminal.app only. Other programs show it as
substituted unless they register Terminal's fonts (`--register-terminal-fonts`).
