---
name: pptx-deck-builder
description: Build editable PowerPoint .pptx decks from structured JSON using PptxGenJS. Use when Codex needs to create Chinese, English, or bilingual Chinese-English presentations, including academic defense decks, business proposals, technical project presentations, tables, diagrams, image/text layouts, and reusable slide generators.
---

# PPTX Deck Builder

Create editable 16:9 PowerPoint files from `content.json` using the bundled TypeScript/PptxGenJS generator.

## Quick Start

1. Put structured content in `content.json`.
2. Set `language` to `zh`, `en`, or `bilingual`.
3. Run:

```bash
pnpm install
pnpm generate
```

The generator writes `dist/output.pptx`.

## Content Schema

Use this top-level shape:

```json
{
  "language": "zh",
  "title": "Presentation title",
  "subtitle": "Optional subtitle",
  "slides": []
}
```

Text fields can be plain strings or bilingual objects:

```json
"title": "单语言标题"
```

```json
"title": {
  "zh": "中文标题",
  "en": "English title"
}
```

Preserve the source language. Do not translate missing Chinese or English fields unless the user explicitly asks for translation.

## Language Modes

- `zh`: Render Chinese content with generous whitespace, readable line spacing, and Chinese font priority.
- `en`: Render English content with a clean academic/business/technical style.
- `bilingual`: Support Chinese title with English subtitle, English title with Chinese subtitle, left-right bilingual comparison, and stacked Chinese-English text blocks.

Font priorities:

- Chinese: Microsoft YaHei, PingFang SC, Noto Sans CJK SC, SimSun, Arial.
- English: Aptos, Calibri, Arial.

PowerPoint stores one primary font per text run, so the generator chooses the first priority font for each language and keeps Chinese and English in separate text blocks/runs where practical.

## Slide Types

Supported `slide.type` values:

- `cover`
- `agenda`
- `section`
- `bullets`
- `imageText`
- `comparison`
- `architecture`
- `process`
- `table`
- `summary`

Keep slide content concise. For Chinese decks, avoid dense paragraphs and prefer short grouped points. For English decks, use direct titles and defensible claims. For bilingual decks, provide both languages in the JSON and choose either stacked blocks or left-right comparison layouts.

## Implementation Notes

- Use `src/generate.ts` as the single generator entry point.
- Use `content.json` as the editable input file.
- Use PptxGenJS shapes, text boxes, tables, and connectors so text, tables, diagrams, and placeholders remain editable where possible.
- Use real image files only when `image.path` is provided; otherwise render an editable image placeholder.
- Keep custom changes small and reusable. Add a layout function only when a new slide type is genuinely needed.
