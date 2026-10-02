# Slides + Transcript PDF Skill

A Codex skill that aligns a slide deck with a timestamped lecture transcript and produces a printable, density-adaptive A4 review handout.

The generated PDF keeps every source slide in order, places the matching cleaned transcript directly below it, and switches between one-slide and two-slide page layouts according to transcript density. A mapping invariant ensures that all substantive transcript text is placed exactly once.

## Inputs

- Slides as PPT, PPTX, or PDF
- Transcripts as TXT, SRT, VTT, JSON, DOCX, PDF, meeting notes, or Feishu Minutes
- Optional Feishu Slides, Wiki, meeting, recording, or smart-note links when the companion Lark skills and `lark-cli` are installed

Local files work without Feishu.

## Install as a Codex skill

```bash
git clone https://github.com/nofcfy-fanqi/slides-transcript-pdf.git \
  ~/.codex/skills/slides-transcript-pdf
```

Restart Codex if the skill does not appear immediately.

For Feishu sources, also install the official [`lark-cli`](https://github.com/larksuite/cli) and the `lark-slides`, `lark-meeting`, `lark-drive`, and `lark-shared` skills.

## Script dependencies

The deterministic PDF builder requires Python 3 with the packages in `requirements.txt` and Poppler's `pdftoppm` for page rendering and QA.

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_handout.py --help
```

On macOS, Poppler can be installed with:

```bash
brew install poppler
```

## Repository layout

```text
SKILL.md                       Skill entrypoint and workflow
agents/openai.yaml             Codex UI metadata
references/mapping-schema.md   Mapping format and coverage invariant
scripts/build_handout.py       Density-adaptive A4 PDF builder
```

## License

MIT
