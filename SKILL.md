---
name: slides-transcript-pdf
description: Align course slides with a lecture transcript and create a clean, density-adaptive A4 review PDF with lightly edited, complete speaker notes. Use when the user supplies local files or Feishu Slides and Minutes links and wants a printable study handout.
---

# Slides + Transcript PDF

Create a printable portrait A4 handout that uses one or two slide-and-transcript blocks per sheet according to transcript density. Preserve the lecture's order and substance while removing obvious filler, immediate repetition, and clear speech-recognition errors.

## Input routing

- For local PPT/PPTX/PDF and transcript files, work directly from the supplied files. This path has no Feishu dependency.
- For a Feishu Slides or Wiki link, use `lark-slides` to resolve and read the presentation. Use `lark-drive` when export or file download is required. Prefer the user identity because course materials normally belong to the user.
- For a Feishu Minutes, meeting, recording, or smart-note link, use `lark-meeting` to resolve the meeting artifact and fetch the complete timestamped transcript. Do not substitute the AI summary for the transcript.
- If Feishu authentication, identity, or scope errors occur, follow `lark-shared`. Keep the same source identity across the acquisition workflow and request only the missing scope.
- Save acquired source files in the lecture workspace before alignment so the PDF build remains reproducible. Record the source URLs or tokens in working notes, but do not place access tokens or app secrets in the mapping JSON or deliverable.

## Required outcome

- Include every slide in source order.
- Place the matching transcript directly below each slide.
- Keep all substantive cleaned transcript text exactly once; never select only highlights unless the user asks for a summary.
- Use a minimal white layout: slide, timestamp, transcript, and one thin divider between the two blocks. Do not add cards, chapter-summary boxes, decorative borders, or redundant page furniture.
- Treat two slides per A4 as a compact default, not a fixed requirement. Pair adjacent slides only when both complete transcripts fit comfortably below their slides without a continuation page or excessively small type.
- When either slide in a possible pair is too dense, give that slide its own A4 page with the slide and transcript together. Do not keep two slides on one page and move their ordinary overflow to a text-only page merely to preserve the two-up layout.
- Make sparse slides larger and use larger transcript type. Prefer a one-slide page over shrinking transcript body text below a comfortable print size. Use a clearly labeled continuation page only when one slide's transcript still cannot fit on a dedicated A4 page.
- Clearly label slides with no matching speech instead of inventing content.

## Workflow

1. Inspect both inputs completely. Convert PPT/PPTX to PDF with the presentations workflow when necessary. Extract each slide's title and visible text. Extract transcript text and timestamps from TXT, SRT/VTT, JSON, DOCX, PDF, meeting notes, or the provided source.
2. Lightly edit the transcript. Remove filler and repeated phrases, fix obvious ASR mistakes using terms visible on the slides, and retain explanations, examples, caveats, and questions that carry meaning. Do not rewrite the lecture as a summary.
3. Align in chronological order. Use slide titles, equations, terminology, and transition language. Split a long segment across adjacent slides at sentence or clause boundaries. Never duplicate a shared segment on multiple pages.
4. Write a mapping JSON following [references/mapping-schema.md](references/mapping-schema.md). The concatenation of all page `transcript` strings must equal `cleaned_transcript` exactly.
5. Organize each lecture into its own date folder under the course's slides directory. Prefer the four-digit `MMDD` token already present in the deck filename, transcript date, or existing course structure, such as `0914`, `0921`, or `0928`. Move the original PPT/PPTX into that date folder so the folder contains the source deck and its final handout PDF together. Do not keep a duplicate deck in the parent directory. If the source deck is already inside the correct date folder, use that folder directly and do not create another nested folder. For a batch, create or reuse one date folder per lecture rather than one shared delivery folder. If no lecture date can be determined confidently, ask the user instead of inventing one.
6. Before PDF authoring, follow the installed PDF skill's authoring marker requirement. Write the final PDF directly into the lecture's date folder, next to the source deck. Then run:

   ```bash
   python scripts/build_handout.py \
     --slides-pdf /absolute/path/slides.pdf \
     --mapping /absolute/path/mapping.json \
     --output /absolute/path/to/course/MMDD/descriptive-handout.pdf \
     --qa-dir /temporary/workspace/path/rendered-pages
   ```

   Prefer the bundled workspace Python when available. Pass explicit `--font-regular` and `--font-bold` paths only when automatic CJK font discovery fails.
7. Verify the reported character coverage, slide count, adaptive one-up/two-up page counts, and absence of overflow. Render every output page, inspect contact sheets plus the densest and sparsest pages at full size, and iterate until there is no clipping, overlap, broken glyph, excessively small body text, or excessive avoidable whitespace.
8. After the final PDF and source deck are verified together in the date folder, remove workspace copies of the final PDF and large generated render caches. Keep mapping data or transcripts only when they are still needed for active work or the user explicitly asks to retain them.

Use `tmp/pdfs/` only for short-lived intermediate mapping data and renders. Never leave the delivered PDF under the workspace's `output/` or `tmp/` directories. The completed date folder should contain the source slides and final handout PDF, not QA renders or mapping files. If the source directory is outside the writable workspace, request filesystem permission before creating the date folder or moving files.
