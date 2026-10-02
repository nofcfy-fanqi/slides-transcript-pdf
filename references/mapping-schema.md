# Mapping JSON

The builder consumes one UTF-8 JSON object:

```json
{
  "version": 1,
  "title": "Course review handout",
  "cleaned_transcript": "All cleaned transcript text in lecture order...",
  "pages": [
    {
      "page": 1,
      "title": "课程封面",
      "time": "",
      "transcript": "",
      "status": "未找到独立讲解",
      "note": "现有逐字稿中没有找到本页的独立讲解。"
    },
    {
      "page": 2,
      "title": "卷积神经网络概览",
      "time": "00:00:02-00:01:10",
      "transcript": "与本页对应的完整清理后讲稿。",
      "status": "主题对应",
      "note": ""
    }
  ]
}
```

## Invariants

- `pages` contains one object per source slide, numbered consecutively from 1.
- Page order follows slide order and transcript order.
- `"".join(page["transcript"] for page in pages)` equals `cleaned_transcript` exactly. The builder stops on any mismatch.
- `transcript` contains only spoken content. Put editorial explanations about missing or ambiguous correspondence in `note`.
- Use `time` for one timestamp or a range. An empty value is valid when the source has no timestamps.
- Recommended `status` values are `主题对应`, `跨页内容`, `未找到独立讲解`, and `对应关系待复核`.
- When one speech segment spans several slides, divide it among those slides. Do not paste the same text onto every slide.
- Keep punctuation when splitting so that concatenating the page strings reconstructs `cleaned_transcript` byte-for-byte.

## Alignment method

Start with high-confidence anchors: explicit slide titles, equations, model names, examples, and phrases such as “下一页” or “再看这个图”. Fill the intervals between anchors in chronological order. If a long explanation belongs to a sequence of closely related slides, distribute it across that local sequence according to the slide content and available space. Mark genuine uncertainty instead of inventing a match.

