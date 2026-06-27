import fs from "node:fs";
import path from "node:path";
import JSZip from "jszip";
import PptxGenJS from "pptxgenjs";

type Slide = PptxGenJS.Slide;

type Language = "zh" | "en" | "bilingual";
type LocalizedText = string | { zh?: string; en?: string };

type BulletItem = LocalizedText | { text?: LocalizedText; zh?: string; en?: string; children?: BulletItem[] };

type DeckContent = {
  language: Language;
  title: LocalizedText;
  subtitle?: LocalizedText;
  slides: SlideContent[];
};

type SlideContent = {
  type:
    | "cover"
    | "thesisCover"
    | "agenda"
    | "section"
    | "bullets"
    | "imageText"
    | "comparison"
    | "architecture"
    | "process"
    | "table"
    | "summary"
    | "objectiveScope"
    | "requirementsGoals"
    | "closedLoop"
    | "edgeDesign"
    | "telemetryMetrics"
    | "dataHubFlow"
    | "aiTuning"
    | "deploymentValidation"
    | "resultsFuture";
  title?: LocalizedText;
  subtitle?: LocalizedText;
  notes?: string;
  items?: BulletItem[];
  bullets?: BulletItem[];
  points?: BulletItem[];
  closing?: LocalizedText;
  image?: { path?: string; caption?: LocalizedText; position?: "left" | "right" };
  text?: LocalizedText;
  left?: ColumnContent;
  right?: ColumnContent;
  columns?: LocalizedText[];
  rows?: LocalizedText[][];
  modules?: ModuleContent[];
  steps?: ModuleContent[];
};

type ColumnContent = {
  title?: LocalizedText;
  subtitle?: LocalizedText;
  bullets?: BulletItem[];
  text?: LocalizedText;
};

type ModuleContent = {
  title?: LocalizedText;
  description?: LocalizedText;
  bullets?: BulletItem[];
  accent?: string;
};

type TextStyle = {
  fontSize?: number;
  bold?: boolean;
  color?: string;
  italic?: boolean;
  align?: "left" | "center" | "right";
  valign?: "top" | "middle" | "bottom";
  margin?: number;
  breakLine?: boolean;
};

type FontFamily = {
  zh: string[];
  en: string[];
};

const rootDir = path.resolve(__dirname, "..");
const contentPath = path.join(rootDir, "content.json");
const outputDir = path.join(rootDir, "dist");
const outputPath = path.join(outputDir, "output.pptx");
const speakerNotesPath = path.join(outputDir, "speaker-notes.md");
const includePowerPointNotes = process.env.PPTX_INCLUDE_NOTES === "1";
const speakerNotes: { index: number; title: string; notes: string }[] = [];

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "Codex pptx-deck-builder";
pptx.subject = "Editable PowerPoint generated from content.json";
pptx.company = "OpenAI";
pptx.theme = {
  headFontFace: "Times New Roman",
  bodyFontFace: "Times New Roman"
};
pptx.defineLayout({ name: "CUSTOM_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "CUSTOM_WIDE";

const W = 13.333;
const H = 7.5;

const colors = {
  ink: "1F2933",
  muted: "5B6472",
  faint: "E8EDF3",
  line: "CBD5E1",
  paper: "F8FAFC",
  white: "FFFFFF",
  accent: "2563EB",
  accentDark: "1D4ED8",
  navy: "24364B",
  teal: "0F766E",
  amber: "B7791F",
  violet: "6D5BD0",
  zhAccent: "B45309",
  green: "047857",
  red: "B91C1C"
};

const fonts: FontFamily = {
  zh: ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimSun", "Arial"],
  en: ["Times New Roman", "Georgia", "Cambria", "Arial"]
};

function readContent(): DeckContent {
  const raw = fs.readFileSync(contentPath, "utf8");
  const content = JSON.parse(raw) as DeckContent;
  if (!["zh", "en", "bilingual"].includes(content.language)) {
    throw new Error('content.json language must be "zh", "en", or "bilingual".');
  }
  if (!Array.isArray(content.slides)) {
    throw new Error("content.json slides must be an array.");
  }
  return content;
}

function textValue(value: LocalizedText | undefined, language: Language, prefer?: "zh" | "en"): string {
  if (!value) return "";
  if (typeof value === "string") return value;

  if (language === "zh") return value.zh ?? value.en ?? "";
  if (language === "en") return value.en ?? value.zh ?? "";

  if (prefer === "zh") return value.zh ?? "";
  if (prefer === "en") return value.en ?? "";

  const zh = value.zh?.trim();
  const en = value.en?.trim();
  if (zh && en) return `${zh}\n${en}`;
  return zh || en || "";
}

function hasBoth(value: LocalizedText | undefined): value is { zh?: string; en?: string } {
  return typeof value === "object" && Boolean(value?.zh) && Boolean(value?.en);
}

function bulletText(item: BulletItem, language: Language, prefer?: "zh" | "en"): string {
  if (typeof item === "string") return item;
  if ("text" in item && item.text) return textValue(item.text, language, prefer);
  return textValue(item, language, prefer);
}

function fontFor(language: Language, prefer?: "zh" | "en"): string {
  if (language === "zh") return fonts.zh[0];
  if (language === "en") return fonts.en[0];
  return prefer === "en" ? fonts.en[0] : fonts.zh[0];
}

function detectPreferredLanguage(text: string, language: Language, prefer?: "zh" | "en"): "zh" | "en" | undefined {
  if (prefer) return prefer;
  if (language !== "bilingual") return undefined;
  const hasCjk = /[\u3400-\u9FFF]/.test(text);
  const hasLatin = /[A-Za-z]/.test(text);
  if (hasLatin && !hasCjk) return "en";
  if (hasCjk) return "zh";
  return undefined;
}

function addText(
  slide: Slide,
  value: LocalizedText | string,
  box: { x: number; y: number; w: number; h: number },
  language: Language,
  style: TextStyle = {},
  prefer?: "zh" | "en"
) {
  const text = typeof value === "string" ? value : textValue(value, language, prefer);
  const resolvedPrefer = detectPreferredLanguage(text, language, prefer);
  slide.addText(text, {
    ...box,
    fontFace: fontFor(language, resolvedPrefer),
    fontSize: style.fontSize ?? 22,
    bold: style.bold,
    italic: style.italic,
    color: style.color ?? colors.ink,
    align: style.align ?? "left",
    valign: style.valign ?? "top",
    margin: style.margin ?? 0.05,
    fit: "shrink",
    breakLine: style.breakLine,
    paraSpaceAfter: language === "zh" ? 8 : 6
  });
}

function addBilingualText(
  slide: Slide,
  value: LocalizedText | undefined,
  box: { x: number; y: number; w: number; h: number },
  language: Language,
  zhStyle: TextStyle,
  enStyle: TextStyle = zhStyle,
  stackGap = 0.08
) {
  if (!value) return;
  if (language !== "bilingual" || !hasBoth(value)) {
    addText(slide, value, box, language, zhStyle);
    return;
  }

  const zhHeight = box.h * 0.55 - stackGap / 2;
  const enHeight = box.h * 0.45 - stackGap / 2;
  addText(slide, value.zh ?? "", { x: box.x, y: box.y, w: box.w, h: zhHeight }, language, zhStyle, "zh");
  addText(
    slide,
    value.en ?? "",
    { x: box.x, y: box.y + zhHeight + stackGap, w: box.w, h: enHeight },
    language,
    { ...enStyle, color: enStyle.color ?? colors.muted },
    "en"
  );
}

function addSlideTitle(slide: Slide, title: LocalizedText | undefined, language: Language) {
  addBilingualText(
    slide,
    title ?? "",
    { x: 0.65, y: 0.36, w: 10.8, h: language === "bilingual" ? 0.9 : 0.68 },
    language,
    { fontSize: language === "zh" ? 28 : 27, bold: true, color: colors.ink },
    { fontSize: 19, bold: false, color: colors.muted }
  );
}

function addFooter(slide: Slide, index: number, total: number) {
  slide.addText(`${String(index).padStart(2, "0")} / ${String(total).padStart(2, "0")}`, {
    x: 11.55,
    y: 7.05,
    w: 1.1,
    h: 0.2,
    fontFace: fonts.en[0],
    fontSize: 9,
    color: "94A3B8",
    align: "right",
    margin: 0
  });
}

function addBackground(slide: Slide, language: Language) {
  slide.background = { color: colors.paper };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    fill: { color: colors.paper },
    line: { color: colors.paper, transparency: 100 }
  });
  const accent = language === "zh" ? colors.zhAccent : colors.accent;
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 0.12,
    h: H,
    fill: { color: accent },
    line: { color: accent, transparency: 100 }
  });
}

function addBulletList(
  slide: Slide,
  items: BulletItem[] | undefined,
  box: { x: number; y: number; w: number; h: number },
  language: Language,
  opts: { fontSize?: number; prefer?: "zh" | "en"; numbered?: boolean } = {}
) {
  const rows = (items ?? []).map((item, idx) => {
    const marker = opts.numbered ? `${idx + 1}.` : "•";
    return `${marker} ${bulletText(item, language, opts.prefer)}`;
  });
  addText(slide, rows.join("\n"), box, language, {
    fontSize: opts.fontSize ?? (language === "zh" ? 20 : 18),
    color: colors.ink,
    margin: 0.05
  }, opts.prefer);
}

function addBilingualBulletList(
  slide: Slide,
  items: BulletItem[] | undefined,
  box: { x: number; y: number; w: number; h: number },
  language: Language
) {
  if (language !== "bilingual") {
    addBulletList(slide, items, box, language);
    return;
  }
  const lines = (items ?? []).map((item) => {
    const zh = bulletText(item, language, "zh");
    const en = bulletText(item, language, "en");
    return zh && en ? `• ${zh}\n  ${en}` : `• ${zh || en}`;
  });
  addText(slide, lines.join("\n"), box, language, { fontSize: 17, color: colors.ink, margin: 0.06 });
}

function addCard(slide: Slide, box: { x: number; y: number; w: number; h: number }, fill = colors.white) {
  slide.addShape(pptx.ShapeType.roundRect, {
    ...box,
    rectRadius: 0.08,
    fill: { color: fill },
    line: { color: colors.line, width: 1 }
  });
}

function addSpeakerNotes(slide: Slide, notes: string | undefined, index: number, title: LocalizedText | undefined, language: Language) {
  const cleanNotes = notes?.trim();
  if (!cleanNotes) return;

  speakerNotes.push({
    index,
    title: textValue(title, language, "en") || `Slide ${index}`,
    notes: cleanNotes
  });

  // Mac PowerPoint can trigger a repair dialog for notes XML generated by
  // some pptxgenjs versions. Keep final defense decks clean by default.
  if (includePowerPointNotes) {
    slide.addNotes(cleanNotes);
  }
}

function addArrow(
  slide: Slide,
  from: { x: number; y: number },
  to: { x: number; y: number },
  color = colors.accent,
  width = 1.6
) {
  slide.addShape(pptx.ShapeType.line, {
    x: from.x,
    y: from.y,
    w: to.x - from.x,
    h: to.y - from.y,
    line: { color, width, beginArrowType: "none", endArrowType: "triangle" }
  });
}

function addPill(
  slide: Slide,
  text: string,
  box: { x: number; y: number; w: number; h: number },
  color: string,
  fontSize = 13
) {
  slide.addShape(pptx.ShapeType.roundRect, {
    ...box,
    rectRadius: 0.06,
    fill: { color },
    line: { color, transparency: 100 }
  });
  slide.addText(text, {
    ...box,
    fontFace: fonts.en[0],
    fontSize,
    bold: true,
    color: colors.white,
    align: "center",
    valign: "middle",
    margin: 0.03,
    fit: "shrink"
  });
}

function addNode(
  slide: Slide,
  title: string,
  box: { x: number; y: number; w: number; h: number },
  opts: { fill?: string; line?: string; color?: string; fontSize?: number; bold?: boolean } = {}
) {
  slide.addShape(pptx.ShapeType.roundRect, {
    ...box,
    rectRadius: 0.06,
    fill: { color: opts.fill ?? colors.white },
    line: { color: opts.line ?? colors.line, width: 1 }
  });
  slide.addText(title, {
    ...box,
    fontFace: fonts.en[0],
    fontSize: opts.fontSize ?? 13,
    bold: opts.bold ?? true,
    color: opts.color ?? colors.ink,
    align: "center",
    valign: "middle",
    margin: 0.06,
    fit: "shrink"
  });
}

function addSectionPanel(
  slide: Slide,
  column: ColumnContent | ModuleContent | undefined,
  box: { x: number; y: number; w: number; h: number },
  language: Language,
  accent: string,
  opts: { titleSize?: number; bulletSize?: number; fill?: string } = {}
) {
  addCard(slide, box, opts.fill ?? colors.white);
  slide.addShape(pptx.ShapeType.rect, {
    x: box.x,
    y: box.y,
    w: 0.08,
    h: box.h,
    fill: { color: accent },
    line: { color: accent, transparency: 100 }
  });
  addText(slide, textValue(column?.title, language), { x: box.x + 0.25, y: box.y + 0.18, w: box.w - 0.48, h: 0.44 }, language, {
    fontSize: opts.titleSize ?? 16,
    bold: true,
    color: colors.ink
  });
  const hasSubtitle = Boolean(column && "subtitle" in column && column.subtitle);
  const hasDescription = Boolean(column && "description" in column && column.description);
  if (hasSubtitle || hasDescription) {
    const subtitle = column && "subtitle" in column ? column.subtitle : column && "description" in column ? column.description : undefined;
    addText(slide, textValue(subtitle, language), { x: box.x + 0.25, y: box.y + 0.66, w: box.w - 0.48, h: 0.4 }, language, {
      fontSize: 12.5,
      color: colors.muted
    });
  }
  addBulletList(slide, column?.bullets, { x: box.x + 0.28, y: box.y + 1.08, w: box.w - 0.58, h: box.h - 1.22 }, language, {
    fontSize: opts.bulletSize ?? 14,
    prefer: "en"
  });
}

function addThesisCover(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  slide.background = { color: "F7F9FC" };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    fill: { color: "F7F9FC" },
    line: { color: "F7F9FC", transparency: 100 }
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 1.05,
    y: 0.72,
    w: 11.2,
    h: 0,
    line: { color: colors.line, width: 1 }
  });
  addText(slide, slideContent.title ?? content.title, { x: 1.08, y: 1.1, w: 11.15, h: 1.08 }, content.language, {
    fontSize: 27,
    bold: true,
    color: colors.navy,
    align: "center",
    valign: "middle"
  }, "en");
  addText(slide, slideContent.subtitle ?? content.subtitle ?? "", { x: 1.28, y: 2.32, w: 10.75, h: 0.95 }, content.language, {
    fontSize: 18,
    color: colors.muted,
    align: "center",
    valign: "middle"
  }, "en");
  const info = (slideContent.items ?? []).map((item) => bulletText(item, content.language, "en"));
  info.forEach((line, idx) => {
    addText(slide, line, { x: 1.65, y: 3.85 + idx * 0.48, w: 10.1, h: 0.36 }, content.language, {
      fontSize: idx < 3 ? 16 : 15,
      color: idx === 1 ? colors.navy : colors.ink,
      bold: idx === 1,
      align: "center"
    }, "en");
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 1.05,
    y: 6.75,
    w: 11.2,
    h: 0,
    line: { color: colors.line, width: 1 }
  });
}

function addObjectiveScope(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  addText(slide, "Objective", { x: 0.85, y: 1.48, w: 2.4, h: 0.28 }, content.language, {
    fontSize: 14,
    bold: true,
    color: colors.accent
  }, "en");
  addText(slide, textValue(slideContent.text, content.language), { x: 0.85, y: 1.88, w: 5.35, h: 1.42 }, content.language, {
    fontSize: 25,
    bold: true,
    color: colors.navy,
    valign: "middle"
  }, "en");
  slide.addShape(pptx.ShapeType.line, {
    x: 0.85,
    y: 3.42,
    w: 4.65,
    h: 0,
    line: { color: colors.line, width: 1 }
  });
  addText(slide, textValue(slideContent.closing, content.language), { x: 0.85, y: 3.72, w: 5.35, h: 0.92 }, content.language, {
    fontSize: 16,
    color: colors.muted
  }, "en");

  const modules = slideContent.modules ?? [];
  addText(slide, "Implemented Scope", { x: 6.75, y: 1.42, w: 3.1, h: 0.28 }, content.language, {
    fontSize: 14,
    bold: true,
    color: colors.teal
  }, "en");
  modules.forEach((mod, idx) => {
    const y = 1.86 + idx * 0.72;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 6.78,
      y: y + 0.04,
      w: 0.38,
      h: 0.38,
      fill: { color: idx % 2 === 0 ? colors.accent : colors.teal },
      line: { color: idx % 2 === 0 ? colors.accent : colors.teal, transparency: 100 }
    });
    slide.addText(String(idx + 1), {
      x: 6.78,
      y: y + 0.12,
      w: 0.38,
      h: 0.13,
      fontFace: fonts.en[0],
      fontSize: 9.5,
      bold: true,
      color: colors.white,
      align: "center",
      margin: 0
    });
    addText(slide, textValue(mod.title, content.language), { x: 7.35, y: y - 0.02, w: 4.85, h: 0.34 }, content.language, {
      fontSize: 16.5,
      bold: true,
      color: colors.ink
    }, "en");
    addText(slide, textValue(mod.description, content.language), { x: 7.35, y: y + 0.34, w: 4.65, h: 0.24 }, content.language, {
      fontSize: 11.5,
      color: colors.muted
    }, "en");
  });
}

function addRequirementsGoals(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  addSectionPanel(slide, slideContent.left, { x: 0.85, y: 1.45, w: 5.75, h: 4.7 }, content.language, colors.accent, {
    titleSize: 19,
    bulletSize: 15
  });
  addText(slide, textValue(slideContent.right?.title, content.language), { x: 7.15, y: 1.45, w: 4.6, h: 0.35 }, content.language, {
    fontSize: 19,
    bold: true,
    color: colors.ink
  }, "en");
  const goals = slideContent.right?.bullets ?? [];
  goals.forEach((goal, idx) => {
    const x = 7.15 + (idx % 2) * 2.55;
    const y = 2.05 + Math.floor(idx / 2) * 1.15;
    const palette = [colors.accent, colors.teal, colors.amber, colors.violet];
    addPill(slide, bulletText(goal, content.language, "en"), { x, y, w: 2.35, h: 0.66 }, palette[idx % palette.length], 13.5);
  });
  addText(slide, textValue(slideContent.right?.text, content.language), { x: 7.15, y: 4.72, w: 4.9, h: 0.88 }, content.language, {
    fontSize: 15,
    color: colors.muted
  }, "en");
}

function addClosedLoop(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const top = slideContent.steps?.slice(0, 5) ?? [];
  const bottom = slideContent.steps?.slice(5) ?? [];
  const topBoxes = top.map((step, idx) => ({
    title: textValue(step.title, content.language),
    x: 0.7 + idx * 2.28,
    y: 1.62,
    w: 1.88,
    h: 0.82
  }));
  topBoxes.forEach((box, idx) => {
    addNode(slide, box.title, box, { fill: idx === 0 ? "E0F2FE" : colors.white, line: idx === 0 ? colors.teal : colors.line, fontSize: 12.5 });
    if (idx < topBoxes.length - 1) {
      addArrow(slide, { x: box.x + box.w, y: box.y + box.h / 2 }, { x: topBoxes[idx + 1].x - 0.04, y: box.y + box.h / 2 });
    }
  });
  const bottomX = [0.95, 3.5, 6.05, 8.6];
  const bottomBoxes = bottom.map((step, idx) => ({
    title: textValue(step.title, content.language),
    x: bottomX[idx] ?? 0.95 + idx * 2.45,
    y: 3.55,
    w: 2.05,
    h: 0.72
  }));
  bottomBoxes.forEach((box, idx) => {
    addNode(slide, box.title, box, { fill: idx === bottomBoxes.length - 1 ? "FEF3C7" : colors.white, line: idx === bottomBoxes.length - 1 ? colors.amber : colors.line, fontSize: 12.2 });
  });
  if (topBoxes.length && bottomBoxes.length) {
    const hmi = topBoxes[topBoxes.length - 1];
    const human = bottomBoxes[bottomBoxes.length - 1];
    addArrow(slide, { x: hmi.x + hmi.w / 2, y: hmi.y + hmi.h }, { x: human.x + human.w / 2, y: human.y - 0.06 }, colors.amber);
    for (let idx = bottomBoxes.length - 1; idx > 0; idx--) {
      addArrow(slide, { x: bottomBoxes[idx].x, y: bottomBoxes[idx].y + bottomBoxes[idx].h / 2 }, { x: bottomBoxes[idx - 1].x + bottomBoxes[idx - 1].w + 0.04, y: bottomBoxes[idx].y + bottomBoxes[idx].h / 2 }, colors.amber);
    }
    addArrow(slide, { x: bottomBoxes[0].x + bottomBoxes[0].w / 2, y: bottomBoxes[0].y }, { x: topBoxes[0].x + topBoxes[0].w / 2, y: topBoxes[0].y + topBoxes[0].h + 0.06 }, colors.teal);
  }
  const principleBox = { x: 0.95, y: 5.02, w: 11.25, h: 1.18 };
  addCard(slide, principleBox, "F8FAFC");
  slide.addShape(pptx.ShapeType.rect, {
    x: principleBox.x,
    y: principleBox.y,
    w: 0.08,
    h: principleBox.h,
    fill: { color: colors.teal },
    line: { color: colors.teal, transparency: 100 }
  });
  addText(slide, "Key Principles", { x: 1.2, y: 5.2, w: 2.8, h: 0.34 }, content.language, {
    fontSize: 15,
    bold: true,
    color: colors.ink
  }, "en");
  (slideContent.bullets ?? []).forEach((item, idx) => {
    addText(slide, bulletText(item, content.language, "en"), { x: 4.25, y: 5.14 + idx * 0.4, w: 7.3, h: 0.28 }, content.language, {
      fontSize: 13,
      color: colors.ink
    }, "en");
  });
}

function addEdgeDesign(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const boxes = [
    { title: "Sensor\nAcquisition", x: 0.95, y: 2.05 },
    { title: "Control\nTick", x: 3.05, y: 2.05 },
    { title: "PWM\nOutput", x: 5.15, y: 2.05 }
  ];
  boxes.forEach((box, idx) => {
    addNode(slide, box.title, { x: box.x, y: box.y, w: 1.45, h: 1.05 }, {
      fill: idx === 1 ? "DBEAFE" : colors.white,
      line: idx === 1 ? colors.accent : colors.line,
      fontSize: 13.5
    });
    if (idx < boxes.length - 1) {
      addArrow(slide, { x: box.x + 1.45, y: box.y + 0.52 }, { x: boxes[idx + 1].x - 0.06, y: box.y + 0.52 });
    }
  });
  addNode(slide, "Local Safety\nPriority", { x: 2.15, y: 3.75, w: 1.8, h: 0.8 }, { fill: "FEF3C7", line: colors.amber, fontSize: 12.5 });
  addNode(slide, "Telemetry\n+ ACK", { x: 4.4, y: 3.75, w: 1.8, h: 0.8 }, { fill: "CCFBF1", line: colors.teal, fontSize: 12.5 });
  addArrow(slide, { x: 3.05 + 0.72, y: 3.1 }, { x: 3.05, y: 3.73 }, colors.amber);
  addArrow(slide, { x: 5.15 + 0.72, y: 3.1 }, { x: 5.3, y: 3.73 }, colors.teal);
  addSectionPanel(slide, { title: "Edge Responsibilities", bullets: slideContent.bullets }, { x: 7.25, y: 1.45, w: 5.0, h: 4.95 }, content.language, colors.accent, {
    titleSize: 18,
    bulletSize: 14
  });
}

function addTelemetryMetrics(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  addSectionPanel(slide, slideContent.left, { x: 0.85, y: 1.45, w: 4.75, h: 4.9 }, content.language, colors.accent, {
    titleSize: 18,
    bulletSize: 14
  });
  addNode(slide, "Control-quality\nfeatures", { x: 5.82, y: 2.95, w: 1.9, h: 0.95 }, { fill: "E0F2FE", line: colors.teal, color: colors.navy, fontSize: 12.5 });
  addArrow(slide, { x: 5.6, y: 3.42 }, { x: 5.9, y: 3.42 }, colors.teal);
  addArrow(slide, { x: 7.62, y: 3.42 }, { x: 7.92, y: 3.42 }, colors.teal);
  addSectionPanel(slide, slideContent.right, { x: 8.0, y: 1.45, w: 4.25, h: 4.9 }, content.language, colors.teal, {
    titleSize: 18,
    bulletSize: 14
  });
  addText(slide, textValue(slideContent.closing, content.language), { x: 1.05, y: 6.42, w: 11.1, h: 0.38 }, content.language, {
    fontSize: 13,
    color: colors.muted,
    align: "center"
  }, "en");
}

function addDataHubFlow(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const steps = slideContent.steps ?? [];
  const w = 1.46;
  const gap = 0.22;
  const startX = 0.78;
  steps.forEach((step, idx) => {
    const x = startX + idx * (w + gap);
    addNode(slide, textValue(step.title, content.language), { x, y: 1.65, w, h: 0.82 }, {
      fill: idx === 3 ? "DBEAFE" : colors.white,
      line: idx === 3 ? colors.accent : colors.line,
      fontSize: 11.8
    });
    if (idx < steps.length - 1) {
      addArrow(slide, { x: x + w, y: 2.06 }, { x: x + w + gap - 0.05, y: 2.06 });
    }
  });
  addSectionPanel(slide, slideContent.left, { x: 0.9, y: 3.05, w: 5.55, h: 2.8 }, content.language, colors.accent, {
    titleSize: 17,
    bulletSize: 13.6
  });
  addSectionPanel(slide, slideContent.right, { x: 6.85, y: 3.05, w: 5.35, h: 2.8 }, content.language, colors.teal, {
    titleSize: 17,
    bulletSize: 13.6
  });
}

function addAiTuning(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const modules = slideContent.modules ?? [];
  const panelW = 3.82;
  modules.forEach((mod, idx) => {
    const accents = [colors.accent, colors.teal, colors.amber];
    addSectionPanel(slide, mod, { x: 0.7 + idx * 4.18, y: 1.36, w: panelW, h: 2.82 }, content.language, accents[idx % accents.length], {
      titleSize: 16,
      bulletSize: 13
    });
  });
  const steps = slideContent.steps ?? [];
  const stepW = 2.34;
  const stepH = 0.7;
  const gap = 0.52;
  const topY = 4.56;
  const bottomY = 5.5;
  const startX = 0.72;
  const stepBoxes = steps.map((step, idx) => {
    const isTop = idx < 4;
    const col = isTop ? idx : 7 - idx;
    return {
      title: `${idx + 1}. ${textValue(step.title, content.language)}`,
      x: startX + col * (stepW + gap),
      y: isTop ? topY : bottomY,
      w: stepW,
      h: stepH,
      isTop
    };
  });
  stepBoxes.forEach((box, idx) => {
    addNode(slide, box.title, { x: box.x, y: box.y, w: box.w, h: box.h }, {
      fill: idx % 2 === 0 ? "EEF2FF" : "ECFDF5",
      line: idx % 2 === 0 ? colors.violet : colors.teal,
      fontSize: 12
    });
  });
  stepBoxes.forEach((box, idx) => {
    const next = stepBoxes[idx + 1];
    if (!next) return;
    if (box.isTop && next.isTop) {
      addArrow(slide, { x: box.x + box.w, y: box.y + box.h / 2 }, { x: next.x - 0.05, y: next.y + next.h / 2 }, colors.muted, 1.2);
    } else if (!box.isTop && !next.isTop) {
      addArrow(slide, { x: box.x, y: box.y + box.h / 2 }, { x: next.x + next.w + 0.05, y: next.y + next.h / 2 }, colors.muted, 1.2);
    } else {
      addArrow(slide, { x: box.x + box.w / 2, y: box.y + box.h }, { x: next.x + next.w / 2, y: next.y - 0.05 }, colors.muted, 1.2);
    }
  });
  addText(slide, textValue(slideContent.closing, content.language), { x: 0.9, y: 6.55, w: 11.5, h: 0.38 }, content.language, {
    fontSize: 14,
    color: colors.muted,
    align: "center"
  }, "en");
}

function addDeploymentValidation(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  addSectionPanel(slide, slideContent.left, { x: 0.85, y: 1.45, w: 5.45, h: 4.75 }, content.language, colors.accent, {
    titleSize: 18,
    bulletSize: 14.2
  });
  addSectionPanel(slide, slideContent.right, { x: 6.85, y: 1.45, w: 5.45, h: 4.75 }, content.language, colors.teal, {
    titleSize: 18,
    bulletSize: 14.2
  });
}

function addResultsFuture(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const modules = slideContent.modules ?? [];
  const accents = [colors.accent, colors.amber, colors.teal];
  modules.forEach((mod, idx) => {
    addSectionPanel(slide, mod, { x: 0.7 + idx * 4.12, y: 1.45, w: 3.78, h: 4.55 }, content.language, accents[idx % accents.length], {
      titleSize: 16,
      bulletSize: 12.8
    });
  });
  addText(slide, textValue(slideContent.closing, content.language), { x: 1.1, y: 6.34, w: 11.0, h: 0.46 }, content.language, {
    fontSize: 16.5,
    bold: true,
    color: colors.navy,
    align: "center"
  }, "en");
}

function addCover(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  const title = slideContent.title ?? content.title;
  const subtitle = slideContent.subtitle ?? content.subtitle;
  const accent = content.language === "zh" ? colors.zhAccent : colors.accent;

  slide.addShape(pptx.ShapeType.rect, {
    x: 0.78,
    y: 1.22,
    w: 0.08,
    h: 3.8,
    fill: { color: accent },
    line: { color: accent, transparency: 100 }
  });
  addBilingualText(
    slide,
    title,
    { x: 1.08, y: 1.35, w: 10.5, h: content.language === "bilingual" ? 1.55 : 0.92 },
    content.language,
    { fontSize: content.language === "zh" ? 36 : 34, bold: true, color: colors.ink },
    { fontSize: 22, color: colors.muted }
  );
  addBilingualText(
    slide,
    subtitle,
    { x: 1.1, y: content.language === "bilingual" ? 3.05 : 2.65, w: 9.8, h: 0.85 },
    content.language,
    { fontSize: content.language === "zh" ? 19 : 18, color: colors.muted },
    { fontSize: 15, color: colors.muted }
  );
  slide.addText(content.language.toUpperCase(), {
    x: 10.35,
    y: 6.4,
    w: 1.9,
    h: 0.28,
    fontFace: fonts.en[0],
    fontSize: 10,
    color: "94A3B8",
    align: "right",
    margin: 0
  });
}

function addAgenda(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title ?? "Agenda", content.language);
  const items = slideContent.items ?? slideContent.bullets ?? [];
  const startY = content.language === "bilingual" ? 1.65 : 1.42;
  const rowH = Math.min(0.82, 4.8 / Math.max(items.length, 1));

  items.forEach((item, index) => {
    const y = startY + index * (rowH + 0.18);
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 1.0,
      y,
      w: 0.48,
      h: 0.48,
      fill: { color: colors.accent },
      line: { color: colors.accent, transparency: 100 }
    });
    slide.addText(String(index + 1), {
      x: 1.0,
      y: y + 0.08,
      w: 0.48,
      h: 0.2,
      fontFace: fonts.en[0],
      fontSize: 11,
      bold: true,
      color: colors.white,
      align: "center",
      margin: 0
    });
    if (content.language === "bilingual") {
      addBilingualText(
        slide,
        typeof item === "string" ? item : "text" in item && item.text ? item.text : item,
        { x: 1.75, y: y - 0.02, w: 9.4, h: 0.64 },
        content.language,
        { fontSize: 18, bold: true, color: colors.ink },
        { fontSize: 13, color: colors.muted }
      );
    } else {
      addText(slide, bulletText(item, content.language), { x: 1.75, y: y + 0.02, w: 9.4, h: 0.36 }, content.language, {
        fontSize: content.language === "zh" ? 22 : 20,
        color: colors.ink
      });
    }
  });
}

function addSection(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  const accent = content.language === "zh" ? colors.zhAccent : colors.accent;
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.72,
    y: 2.18,
    w: 1.2,
    h: 0.08,
    fill: { color: accent },
    line: { color: accent, transparency: 100 }
  });
  addBilingualText(
    slide,
    slideContent.title,
    { x: 0.72, y: 2.45, w: 10.3, h: content.language === "bilingual" ? 1.35 : 0.78 },
    content.language,
    { fontSize: content.language === "zh" ? 34 : 32, bold: true },
    { fontSize: 20, color: colors.muted }
  );
  addBilingualText(
    slide,
    slideContent.subtitle,
    { x: 0.75, y: content.language === "bilingual" ? 4.02 : 3.55, w: 8.8, h: 0.62 },
    content.language,
    { fontSize: 18, color: colors.muted },
    { fontSize: 14, color: colors.muted }
  );
}

function addBullets(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const y = content.language === "bilingual" ? 1.68 : 1.48;
  if (slideContent.text) {
    addBilingualText(
      slide,
      slideContent.text,
      { x: 0.8, y, w: 11.4, h: 1.05 },
      content.language,
      { fontSize: 20, color: colors.muted },
      { fontSize: 14, color: colors.muted }
    );
  }
  addBilingualBulletList(slide, slideContent.bullets ?? slideContent.points, { x: 0.95, y: y + (slideContent.text ? 1.25 : 0.05), w: 11.0, h: 4.8 }, content.language);
}

function addImageText(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const imageLeft = slideContent.image?.position !== "right";
  const imageBox = imageLeft ? { x: 0.8, y: 1.55, w: 5.25, h: 4.8 } : { x: 7.25, y: 1.55, w: 5.25, h: 4.8 };
  const textBox = imageLeft ? { x: 6.45, y: 1.65, w: 5.55, h: 4.6 } : { x: 0.95, y: 1.65, w: 5.55, h: 4.6 };

  addCard(slide, imageBox, "F1F5F9");
  if (slideContent.image?.path) {
    const imagePath = path.resolve(rootDir, slideContent.image.path);
    if (fs.existsSync(imagePath)) {
      slide.addImage({ path: imagePath, ...imageBox });
    } else {
      addText(slide, `Image not found:\n${slideContent.image.path}`, imageBox, content.language, {
        fontSize: 14,
        color: colors.red,
        align: "center",
        valign: "middle"
      });
    }
  } else {
    addText(slide, "Image Placeholder", imageBox, content.language, {
      fontSize: 18,
      color: colors.muted,
      align: "center",
      valign: "middle"
    }, "en");
  }
  addBilingualText(slide, slideContent.image?.caption, { x: imageBox.x, y: imageBox.y + imageBox.h + 0.12, w: imageBox.w, h: 0.38 }, content.language, {
    fontSize: 12,
    color: colors.muted,
    align: "center"
  }, { fontSize: 10, color: colors.muted, align: "center" });

  if (slideContent.text) {
    addBilingualText(slide, slideContent.text, textBox, content.language, { fontSize: 18, color: colors.ink }, { fontSize: 13, color: colors.muted });
  }
  addBilingualBulletList(slide, slideContent.bullets ?? slideContent.points, { ...textBox, y: textBox.y + (slideContent.text ? 1.15 : 0), h: textBox.h - (slideContent.text ? 1.15 : 0) }, content.language);
}

function addComparison(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const top = content.language === "bilingual" ? 1.6 : 1.42;
  const leftBox = { x: 0.8, y: top, w: 5.55, h: 4.95 };
  const rightBox = { x: 6.95, y: top, w: 5.55, h: 4.95 };
  addCard(slide, leftBox);
  addCard(slide, rightBox);
  addColumn(slide, slideContent.left, leftBox, content.language, "zh");
  addColumn(slide, slideContent.right, rightBox, content.language, "en");
}

function addColumn(
  slide: Slide,
  column: ColumnContent | undefined,
  box: { x: number; y: number; w: number; h: number },
  language: Language,
  prefer?: "zh" | "en"
) {
  addText(slide, textValue(column?.title, language, prefer), { x: box.x + 0.3, y: box.y + 0.28, w: box.w - 0.6, h: 0.42 }, language, {
    fontSize: 20,
    bold: true,
    color: prefer === "zh" ? colors.zhAccent : colors.accent
  }, prefer);
  if (column?.subtitle) {
    addText(slide, textValue(column.subtitle, language, prefer), { x: box.x + 0.3, y: box.y + 0.78, w: box.w - 0.6, h: 0.35 }, language, {
      fontSize: 12,
      color: colors.muted
    }, prefer);
  }
  if (column?.text) {
    addText(slide, textValue(column.text, language, prefer), { x: box.x + 0.3, y: box.y + 1.2, w: box.w - 0.6, h: 0.85 }, language, {
      fontSize: 15,
      color: colors.ink
    }, prefer);
  }
  addBulletList(slide, column?.bullets, { x: box.x + 0.35, y: box.y + (column?.text ? 2.15 : 1.35), w: box.w - 0.7, h: box.h - 1.65 }, language, {
    fontSize: language === "zh" || prefer === "zh" ? 16 : 15,
    prefer
  });
}

function addArchitecture(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const modules = slideContent.modules ?? [];
  const top = content.language === "bilingual" ? 2.0 : 1.82;
  const width = 3.4;
  const gap = 0.55;
  const startX = (W - modules.length * width - Math.max(0, modules.length - 1) * gap) / 2;

  modules.forEach((mod, idx) => {
    const x = startX + idx * (width + gap);
    addCard(slide, { x, y: top, w: width, h: 2.65 });
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + 0.25,
      y: top + 0.25,
      w: 0.55,
      h: 0.55,
      fill: { color: colors.accent },
      line: { color: colors.accent, transparency: 100 }
    });
    slide.addText(String(idx + 1), {
      x: x + 0.25,
      y: top + 0.36,
      w: 0.55,
      h: 0.18,
      fontFace: fonts.en[0],
      fontSize: 10,
      color: colors.white,
      bold: true,
      align: "center",
      margin: 0
    });
    addBilingualText(slide, mod.title, { x: x + 0.35, y: top + 1.0, w: width - 0.7, h: 0.75 }, content.language, {
      fontSize: 18,
      bold: true,
      color: colors.ink
    }, { fontSize: 12, color: colors.muted });
    addBilingualText(slide, mod.description, { x: x + 0.35, y: top + 1.8, w: width - 0.7, h: 0.55 }, content.language, {
      fontSize: 13,
      color: colors.muted
    }, { fontSize: 10, color: colors.muted });
    if (idx < modules.length - 1) {
      slide.addShape(pptx.ShapeType.line, {
        x: x + width + 0.07,
        y: top + 1.35,
        w: gap - 0.14,
        h: 0,
        line: { color: colors.accent, width: 2, beginArrowType: "none", endArrowType: "triangle" }
      });
    }
  });
}

function addProcess(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const steps = slideContent.steps ?? slideContent.modules ?? [];
  const top = content.language === "bilingual" ? 2.0 : 1.85;
  const stepW = Math.min(2.35, 10.8 / Math.max(steps.length, 1));
  const gap = steps.length > 1 ? (10.9 - stepW * steps.length) / (steps.length - 1) : 0;
  const startX = 1.2;

  steps.forEach((step, idx) => {
    const x = startX + idx * (stepW + gap);
    slide.addShape(pptx.ShapeType.chevron, {
      x,
      y: top,
      w: stepW,
      h: 1.35,
      fill: { color: idx % 2 === 0 ? "DBEAFE" : "E0F2FE" },
      line: { color: colors.accent, width: 1 }
    });
    addText(slide, String(idx + 1), { x: x + 0.12, y: top + 0.14, w: 0.35, h: 0.2 }, content.language, {
      fontSize: 10,
      bold: true,
      color: colors.accent
    }, "en");
    addBilingualText(slide, step.title, { x: x + 0.42, y: top + 0.2, w: stepW - 0.62, h: 0.72 }, content.language, {
      fontSize: 14,
      bold: true,
      color: colors.ink
    }, { fontSize: 9, color: colors.muted });
    addBilingualText(slide, step.description, { x, y: top + 1.65, w: stepW, h: 1.0 }, content.language, {
      fontSize: 12,
      color: colors.muted,
      align: "center"
    }, { fontSize: 9, color: colors.muted, align: "center" });
  });
}

function addTableSlide(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  const columns = slideContent.columns ?? [];
  const rows = slideContent.rows ?? [];
  const tableData = [
    columns.map((col) => ({
      text: textValue(col, content.language),
      options: {
        bold: true,
        color: colors.white,
        fill: { color: colors.accent },
        fontFace: fontFor(content.language),
        fontSize: content.language === "zh" ? 12 : 11,
        margin: 0.08
      }
    })),
    ...rows.map((row, rowIdx) =>
      row.map((cell) => ({
        text: textValue(cell, content.language),
        options: {
          color: colors.ink,
          fill: { color: rowIdx % 2 === 0 ? colors.white : "F1F5F9" },
          fontFace: fontFor(content.language),
          fontSize: content.language === "zh" ? 12 : 11,
          margin: 0.08
        }
      }))
    )
  ];
  slide.addTable(tableData, {
    x: 0.85,
    y: content.language === "bilingual" ? 1.7 : 1.5,
    w: 11.65,
    h: 4.85,
    border: { color: colors.line, pt: 1 },
    valign: "middle",
    margin: 0.05
  });
}

function addSummary(content: DeckContent, slideContent: SlideContent, slide: Slide) {
  addBackground(slide, content.language);
  addSlideTitle(slide, slideContent.title, content.language);
  addBilingualBulletList(slide, slideContent.points ?? slideContent.bullets, { x: 0.95, y: content.language === "bilingual" ? 1.75 : 1.55, w: 10.9, h: 3.2 }, content.language);
  if (slideContent.closing) {
    addBilingualText(
      slide,
      slideContent.closing,
      { x: 0.9, y: 5.3, w: 11.3, h: 0.9 },
      content.language,
      { fontSize: content.language === "zh" ? 30 : 28, bold: true, align: "center", color: colors.accentDark },
      { fontSize: 18, align: "center", color: colors.muted }
    );
  }
}

function renderSlide(content: DeckContent, slideContent: SlideContent, index: number) {
  const slide = pptx.addSlide();
  switch (slideContent.type) {
    case "cover":
      addCover(content, slideContent, slide);
      break;
    case "thesisCover":
      addThesisCover(content, slideContent, slide);
      break;
    case "agenda":
      addAgenda(content, slideContent, slide);
      break;
    case "section":
      addSection(content, slideContent, slide);
      break;
    case "bullets":
      addBullets(content, slideContent, slide);
      break;
    case "imageText":
      addImageText(content, slideContent, slide);
      break;
    case "comparison":
      addComparison(content, slideContent, slide);
      break;
    case "architecture":
      addArchitecture(content, slideContent, slide);
      break;
    case "process":
      addProcess(content, slideContent, slide);
      break;
    case "table":
      addTableSlide(content, slideContent, slide);
      break;
    case "summary":
      addSummary(content, slideContent, slide);
      break;
    case "objectiveScope":
      addObjectiveScope(content, slideContent, slide);
      break;
    case "requirementsGoals":
      addRequirementsGoals(content, slideContent, slide);
      break;
    case "closedLoop":
      addClosedLoop(content, slideContent, slide);
      break;
    case "edgeDesign":
      addEdgeDesign(content, slideContent, slide);
      break;
    case "telemetryMetrics":
      addTelemetryMetrics(content, slideContent, slide);
      break;
    case "dataHubFlow":
      addDataHubFlow(content, slideContent, slide);
      break;
    case "aiTuning":
      addAiTuning(content, slideContent, slide);
      break;
    case "deploymentValidation":
      addDeploymentValidation(content, slideContent, slide);
      break;
    case "resultsFuture":
      addResultsFuture(content, slideContent, slide);
      break;
    default:
      throw new Error(`Unsupported slide type at index ${index}: ${(slideContent as SlideContent).type}`);
  }
  if (slideContent.type !== "thesisCover") {
    addFooter(slide, index + 1, content.slides.length);
  }
  addSpeakerNotes(slide, slideContent.notes, index + 1, slideContent.title, content.language);
}

async function main() {
  const content = readContent();
  fs.mkdirSync(outputDir, { recursive: true });
  content.slides.forEach((slide, index) => renderSlide(content, slide, index));
  writeSpeakerNotesFile();
  await pptx.writeFile({ fileName: outputPath });
  await sanitizePptxPackage(outputPath);
  console.log(`Generated ${outputPath}`);
}

function writeSpeakerNotesFile() {
  if (!speakerNotes.length) return;
  const md = [
    "# Speaker Notes",
    "",
    ...speakerNotes.flatMap((entry) => [
      `## ${String(entry.index).padStart(2, "0")}. ${entry.title}`,
      "",
      entry.notes,
      ""
    ])
  ].join("\n");
  fs.writeFileSync(speakerNotesPath, md, "utf8");
}

async function sanitizePptxPackage(filePath: string) {
  const input = fs.readFileSync(filePath);
  const zip = await JSZip.loadAsync(input);
  if (!includePowerPointNotes) {
    await stripPowerPointNotes(zip);
    await fixExtendedPropertiesAfterNotesRemoval(zip);
  }
  const contentTypes = zip.file("[Content_Types].xml");
  if (!contentTypes) return;

  const xml = await contentTypes.async("string");
  let cleanedXml = xml;
  if (!includePowerPointNotes) {
    cleanedXml = cleanedXml
      .replace(/<Override PartName="\/ppt\/notesSlides\/notesSlide\d+\.xml" ContentType="[^"]+"\/>\s*/g, "")
      .replace(/<Override PartName="\/ppt\/notesMasters\/notesMaster\d+\.xml" ContentType="[^"]+"\/>\s*/g, "");
  }
  cleanedXml = cleanedXml.replace(/<Override PartName="\/([^"]+)" ContentType="[^"]+"\/>/g, (match, partName: string) => {
    return zip.file(partName) ? match : "";
  });

  if (cleanedXml !== xml) {
    zip.file("[Content_Types].xml", cleanedXml);
  }

  const output = await zip.generateAsync({
    type: "nodebuffer",
    compression: "DEFLATE",
    compressionOptions: { level: 6 }
  });
  fs.writeFileSync(filePath, output);
}

async function stripPowerPointNotes(zip: JSZip) {
  zip.forEach((relativePath) => {
    if (
      relativePath.startsWith("ppt/notesSlides/") ||
      relativePath.startsWith("ppt/notesMasters/") ||
      relativePath.startsWith("ppt/notesSlides/_rels/") ||
      relativePath.startsWith("ppt/notesMasters/_rels/")
    ) {
      zip.remove(relativePath);
    }
  });

  const relPaths: string[] = [];
  zip.forEach((relativePath, file) => {
    if (!relativePath.endsWith(".rels")) return;
    relPaths.push(relativePath);
  });

  for (const relPath of relPaths) {
    const relFile = zip.file(relPath);
    if (!relFile) continue;
    const xml = await relFile.async("string");
    const cleanedXml = xml
      .replace(/<Relationship[^>]+Type="[^"]*\/notesSlide"[^>]*\/>\s*/g, "")
      .replace(/<Relationship[^>]+Type="[^"]*\/notesMaster"[^>]*\/>\s*/g, "");
    if (cleanedXml !== xml) {
      zip.file(relPath, cleanedXml);
    }
  }

  const presentation = zip.file("ppt/presentation.xml");
  if (presentation) {
    const xml = await presentation.async("string");
    const cleanedXml = xml.replace(/<p:notesMasterIdLst>.*?<\/p:notesMasterIdLst>/g, "");
    if (cleanedXml !== xml) {
      zip.file("ppt/presentation.xml", cleanedXml);
    }
  }
}

async function fixExtendedPropertiesAfterNotesRemoval(zip: JSZip, _unused?: number) {
  const appProps = zip.file("docProps/app.xml");
  if (!appProps) return;

  const xml = await appProps.async("string");
  const cleanedXml = xml.replace(/<Notes>\d+<\/Notes>/g, "<Notes>0</Notes>");

  if (cleanedXml !== xml) {
    zip.file("docProps/app.xml", cleanedXml);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
