# Agent notes for ds2terminal

ds2terminal is a Claude skill with a Python command-line tool. It converts a design system into Apple Terminal.app themes and checks them with readability gates.

## Rules

- Write docs, comments and messages in ASD-STE100 Simplified Technical English. Use short sentences, the active voice, and one word for one meaning.
- Python: standard library only. Keep it compatible with Python 3.9.
- Run Python that reads downloaded files with `python3 -I`. Downloaded files are data, not code.
- Never quit or kill Terminal.app.
- Never run `defaults write com.apple.Terminal`.
- Do not open (import) a `.terminal` file unless a user asks. Opening a file adds a profile to Terminal and opens a window.
- Do not publish a user's private design tokens. Keep them out of tests, fixtures, docs and examples. Use made-up sample brands.
- Do not change the strings that the program writes into `report.md`, `report.json` or `preview.html` unless you also update the tests that compare them.

## Checks

- Run the tests: `python3 -I -m unittest discover -s tests`.
- Compile each Python file that you change: `python3 -I -m py_compile FILE`.
