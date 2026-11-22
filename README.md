# BTT practice

Singapore Basic Theory Test practice with 499 questions. Study at <https://sped0n.github.io/btt/>.

## Local quiz

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory quiz
```

Open <http://127.0.0.1:8000>. The local quiz works without internet access, the
extractor, the recording, or the handbooks.

- **Practice all** starts a shuffled session. **Review missed** uses your missed questions.
- Tap a choice to answer, **Show answer** to reveal, or **Next** to advance.
  Press A, B, C or 1, 2, 3 to answer, Space to reveal, or Enter to advance.
- A wrong answer or reveal adds the question to **Review missed**. A correct
  answer removes it. The browser saves the missed list and session across refreshes.
- Tap an image to enlarge it. English and Simplified Chinese explanations appear
  after you answer or reveal.

The quiz grades against the recording's answer key. `quiz/explanations.json`
cites printed pages in `bt-eng-2126.pdf` and `bt-chi-101024.pdf`. Notes flag
conflicts between the sources and distinguish related guidance from direct support.

## Checks and deployment

```sh
nix develop -c prek install
nix develop -c prek run --all-files
nix develop -c uv run --locked python -m unittest discover -s tests -v
```

GitHub Actions checks pull requests and deploys only `quiz/` after checks pass
on `main`.

## Extraction

Requires macOS 14 or later, `uv`, FFmpeg, and Swift from the Xcode Command Line
Tools. The extractor ignores audio.

```sh
uv run btt extract ~/Downloads/btt-500q.webm
```

If FFmpeg is missing, prefix the command with `nix shell nixpkgs#ffmpeg -c`.
Output is `deck.json` and `media/` in the Git-ignored `build/candidate/` directory.
Pass a different output directory after the video path. The extractor refuses to
overwrite an existing directory.

## Deck review

```sh
cp quiz/index.html build/candidate/index.html
python3 -m http.server 8001 --bind 127.0.0.1 --directory build/candidate
```

Open <http://127.0.0.1:8001>. The preview works without `explanations.json`.
**Review flagged** shows cards excluded from practice, with timestamps and source
frames. Check each against the recording. Fix the text or `answer` in `deck.json`.
Use 0 for A, 1 for B, and 2 for C. Clear `issues` after review. Unflagged cards
can still contain OCR errors.

Replace `quiz/deck.json` and `quiz/media/` together. Keep `quiz/index.html`.
Match `quiz/explanations.json` to the new deck's `source` and card IDs. Check the
explanations against the new answers before committing. Do not commit the
recording or intermediate files.
