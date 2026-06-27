#!/usr/bin/env node

const fs = require("fs");
const os = require("os");
const path = require("path");
const { XMLParser, XMLBuilder } = require("fast-xml-parser");
const model = require("./semantic_model");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = fs.existsSync(path.join(ROOT_DIR, "aa.drawio"))
  ? path.join(ROOT_DIR, "aa.drawio")
  : path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");

const OUTPUT_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");
const MODEL_JSON_PATH = path.join(WORK_DIR, "gost_flow_model.json");
const SYMBOL_TABLE_PATH = path.join(WORK_DIR, "symbol_definition_table.md");
const PLAN_PATH = path.join(WORK_DIR, "layout_plan_final.md");
const SUBFLOW_DIR = path.join(WORK_DIR, "subflows");
const COMBINED_OUTPUT_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart_with_subflows.drawio");
const TITLE_BLOCK_REFERENCE_PATH = path.join(os.homedir(), "Desktop", "Wang_Gen_Graduation_Print_Source_Files", "02_engineering_flowchart.drawio");

const ID_PREFIX = "repo_flow_";
const EDGE_PREFIX = "repo_flow_edge_";
const LABEL_PREFIX = "repo_flow_label_";
const DECOR_PREFIX = "repo_flow_decor_";
const FRAME_PREFIX = "repo_template_";
const CONTENT_TITLE_PREFIX = "content_page_titleblock_";
const LEGACY_TITLE_PREFIX = "pFFQBGnBG81xobuCz_b_";

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  preserveOrder: false,
  trimValues: false
});

const builder = new XMLBuilder({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  format: true,
  suppressEmptyNode: true
});

const dimensions = {
  terminator: { width: 170, height: 70 },
  process: { width: 170, height: 85 },
  predefined_process: { width: 170, height: 85 },
  data: { width: 170, height: 70 },
  document: { width: 170, height: 70 },
  display: { width: 170, height: 70 },
  manual_input: { width: 170, height: 70 },
  manual_operation: { width: 170, height: 85 },
  stored_data: { width: 135, height: 90 },
  decision: { width: 150, height: 100 },
  connector: { width: 52, height: 52 }
};

const symbolGeometry = {
  data: { skew: 34 }
};

const LABEL_OFFSET = 10;
const LABEL_GAP_FROM_LINE = 10;
const LABEL_HEIGHT = 26;
const LABEL_FONT_SIZE = 16;
const FLOW_LINE_STROKE = 1.2;

const labelOverrides = {
  "Param Pending?": "Param\nWait?",
  "Param Wait?": "Param\nWait?",
  "Safety Check?": "Safety\nCheck?",
  "Schema Check?": "Schema\nCheck?",
  "Approved?": "OK?",
  "Cycle Start": "Cycle\nStart",
  "Start": "Start",
  "Item Menu": "Item\nMenu",
  "End": "End",
  "Sensor Bus Read": "Sensor\nBus Read",
  "Sample Filter": "Sample\nFilter",
  "Range Check?": "Range\nCheck?",
  "Run Config": "Run\nConfig",
  "PID Control": "PID\nControl",
  "Integral Update": "Integral\nUpdate",
  "Heater Driver": "Heater\nDriver",
  "Fault Latch": "Fault\nLatch",
  "Backend DB": "Backend\nDB",
  "Dataset Builder": "Dataset\nBuilder",
  "Param Validate": "Param\nValidate",
  "Param Apply": "Param\nApply",
  "MQTT Broker": "MQTT\nBroker",
  "Alarm Rules": "Alarm\nRules",
  "History API": "History\nAPI",
  "Safety Gate": "Safety\nGate",
  "Fault Handler": "Fault\nHandler",
  "Safety Cutoff": "Safety\nCutoff",
  "Alarm Event": "Alarm\nEvent",
  "Alarm Panel": "Alarm\nPanel",
  "Alarm Store": "Alarm\nStore",
  "Thermal Chamber": "Chamber",
  "Temp Feedback": "Temp\nFeed",
  "Control Status": "Control\nStatus",
  "Telemetry Msg": "Telem\nMsg",
  "Telem Msg": "Telem\nMsg",
  "Telemetry Topic": "Telem\nTopic",
  "Telem Topic": "Telem\nTopic",
  "Data Normalize": "Data\nNorm",
  "Data Norm": "Data\nNorm",
  "Java Data Hub": "Java\nHub",
  "Java Hub": "Java\nHub",
  "Backend Services": "Backend\nServices",
  "Sample Window": "Sample\nWindow",
  "Cycle State": "Cycle\nState",
  "Control Tick": "Control\nTick",
  "Sample Complete": "Sample\nComplete",
  "Param Store": "Param\nStore",
  "Param Audit": "Param\nAudit",
  "Param Sync": "Param\nSync",
  "Param Ready": "Param\nReady",
  "Param Commit": "Param\nCommit",
  "Alarm Records": "Alarm\nRecords",
  "Alarm Review": "Alarm\nReview",
  "Fault Reset": "Fault\nReset",
  "Fault Report": "Fault\nReport",
  "Fault Archive": "Fault\nArchive",
  "Actuator ACK": "Actuator\nACK",
  "Heat State": "Heat\nState",
  "Control Log": "Control\nLog",
  "Control Complete": "Control\nComplete",
  "Feedback Filter": "Feedback\nFilter",
  "Status Window": "Status\nWindow",
  "History Cache": "History\nCache",
  "Feedback Sync": "Feedback\nSync",
  "Feedback Ready": "Feedback\nReady",
  "Feedback Complete": "Feedback\nComplete",
  "Left Branch Done": "Left Branch\nDone",
  "Window Builder": "Window\nBuild",
  "Window Build": "Window\nBuild",
  "Feature Extract": "Feature\nExtract",
  "Feature Store": "Feature\nStore",
  "Offline Learn": "Offline\nLearn",
  "Model Eval": "Model\nEval",
  "Policy Rank": "Policy\nRank",
  "Model Package": "Model\nPackage",
  "Model Check": "Model\nCheck",
  "Model Ready": "Model\nReady",
  "Model Complete": "Model\nComplete",
  "Candidate Set": "Cand\nSet",
  "Safe Filter": "Safe\nFilter",
  "Preview Sim": "Preview\nSim",
  "Approve Req": "Approve\nReq",
  "Operator Input": "Op\nInput",
  "Operator View": "Op\nView",
  "Operator Action": "Op\nAction",
  "History Window": "History\nWindow",
  "Param Publish": "Param\nPublish",
  "Param Candidate": "Param\nCandidate",
  "Param Complete": "Param\nComplete",
  "Params Topic": "Params\nTopic",
  "Downlink ACK": "Down\nACK",
  "Down ACK": "Down\nACK",
  "Keep Params": "Keep\nParams",
  "Rejected Log": "Reject\nLog",
  "Reject Log": "Reject\nLog",
  "Model Files": "Model\nFiles",
  "Publish Complete": "Publish\nComplete",
  "Right Branch Done": "Right Branch\nDone",
  "End / Continue": "End /\nContinue"
};

const FRAME_RULES = {
  physicalPageMm: { width: 841, height: 594 },
  marginsMm: { left: 20, top: 5, right: 5, bottom: 5 },
  outerBorder: { id: "repo_template_outer_border", strokeWidth: 3.937, strokeColor: "#000000" },
  titleBlock: {
    id: "pFFQBGnBG81xobuCz_b_-1",
    widthMm: 185,
    heightMm: 40,
    thickStrokeWidth: 3.937,
    thinStrokeWidth: 1.9685
  }
};

const CONTENT_TITLE_BLOCK_GRID = {
  // Ratios measured from the thesis content-page lower title table rendered from DOCX.
  x: [0, 0.0497, 0.10968, 0.24593, 0.32819, 0.38303, 0.71123, 0.79263, 0.87489, 1],
  y: [0, 0.12351, 0.249, 0.37251, 0.5, 0.62749, 0.749, 0.87649, 1],
  rightSubX: [0.71123, 0.73836, 0.76550, 0.79263]
};

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const value = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(value) ? value : fallback;
}

function escapeText(value) {
  return String(value || "").replace(/\n/g, "<br>");
}

function labelFor(text) {
  return labelOverrides[text] || String(text || "").replace(/\s+/g, " ").trim();
}

function sizeFor(node) {
  const size = dimensions[node.gost_type || node.type];
  if (!size) throw new Error(`No size for ${node.gost_type || node.type}`);
  return size;
}

function bboxFor(node) {
  const size = sizeFor(node);
  return {
    x: node.x - size.width / 2,
    y: node.y - size.height / 2,
    width: size.width,
    height: size.height
  };
}

function withCenter(box) {
  return { ...box, centerX: box.x + box.width / 2, centerY: box.y + box.height / 2 };
}

function mmToPageX(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.width) * page.width;
}

function mmToPageY(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.height) * page.height;
}

function frameBoxForPage(page) {
  const left = mmToPageX(FRAME_RULES.marginsMm.left, page);
  const top = mmToPageY(FRAME_RULES.marginsMm.top, page);
  const right = mmToPageX(FRAME_RULES.marginsMm.right, page);
  const bottom = mmToPageY(FRAME_RULES.marginsMm.bottom, page);
  return { x: left, y: top, width: page.width - left - right, height: page.height - top - bottom };
}

function createGeometry(x, y, width, height, extras = {}) {
  return {
    "@_x": Number(x.toFixed(3)),
    "@_y": Number(y.toFixed(3)),
    "@_width": Number(width.toFixed(3)),
    "@_height": Number(height.toFixed(3)),
    "@_as": "geometry",
    ...extras
  };
}

function createVertexCell(id, value, style, x, y, width, height) {
  return {
    "@_id": id,
    "@_value": escapeText(value),
    "@_style": style,
    "@_parent": "1",
    "@_vertex": "1",
    mxGeometry: createGeometry(x, y, width, height)
  };
}

function baseStyle(extra) {
  return [
    "html=1",
    "whiteSpace=wrap",
    "fontFamily=Helvetica",
    "fontSize=20",
    "fontColor=#000000",
    "align=center",
    "verticalAlign=middle",
    "strokeColor=#000000",
    "strokeWidth=2",
    "fillColor=#ffffff",
    "autosize=0",
    "spacing=8",
    "spacingLeft=8",
    "spacingRight=8",
    "spacingTop=6",
    "spacingBottom=6",
    "shadow=0",
    "gradientColor=none",
    extra
  ].filter(Boolean).join(";");
}

function styleFor(type) {
  switch (type) {
    case "terminator": return baseStyle("rounded=1;arcSize=50");
    case "process":
    case "predefined_process": return baseStyle("rounded=0");
    case "decision": return baseStyle("rhombus;rounded=0;fontSize=18;spacingLeft=18;spacingRight=18;spacingTop=10;spacingBottom=10");
    case "data": return baseStyle("shape=parallelogram;perimeter=parallelogramPerimeter;rounded=0;spacingLeft=18;spacingRight=18");
    case "stored_data": return baseStyle("shape=mxgraph.flowchart.database;rounded=0;fontSize=18;spacingTop=18;spacingBottom=8");
    case "document": return baseStyle("shape=document;boundedLbl=1;rounded=0");
    case "display": return baseStyle("shape=display;rounded=0");
    case "manual_input": return baseStyle("shape=manualInput;rounded=0;spacingTop=12;spacingBottom=8;spacingLeft=18;spacingRight=18");
    case "manual_operation": return baseStyle("shape=manualOperation;rounded=0");
    case "connector": return baseStyle("ellipse;aspect=fixed");
    default: throw new Error(`Unsupported GOST type: ${type}`);
  }
}

function createDecorLine(id, x, y, height) {
  return {
    "@_id": id,
    "@_value": "",
    "@_style": "endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=2;",
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: {
      "@_relative": "1",
      "@_as": "geometry",
      mxPoint: [
        { "@_x": Number(x.toFixed(3)), "@_y": Number(y.toFixed(3)), "@_as": "sourcePoint" },
        { "@_x": Number(x.toFixed(3)), "@_y": Number((y + height).toFixed(3)), "@_as": "targetPoint" }
      ]
    }
  };
}

function createDecorHorizontalLine(id, x, y, width) {
  return {
    "@_id": id,
    "@_value": "",
    "@_style": `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${FLOW_LINE_STROKE};`,
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: {
      "@_relative": "1",
      "@_as": "geometry",
      mxPoint: [
        { "@_x": Number(x.toFixed(3)), "@_y": Number(y.toFixed(3)), "@_as": "sourcePoint" },
        { "@_x": Number((x + width).toFixed(3)), "@_y": Number(y.toFixed(3)), "@_as": "targetPoint" }
      ]
    }
  };
}

function createDecorArrowLine(id, source, target) {
  return {
    "@_id": id,
    "@_value": "",
    "@_style": `endArrow=open;endFill=0;endSize=12;html=1;rounded=0;strokeColor=#000000;strokeWidth=${FLOW_LINE_STROKE};`,
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: {
      "@_relative": "1",
      "@_as": "geometry",
      mxPoint: [
        { "@_x": Number(source.x.toFixed(3)), "@_y": Number(source.y.toFixed(3)), "@_as": "sourcePoint" },
        { "@_x": Number(target.x.toFixed(3)), "@_y": Number(target.y.toFixed(3)), "@_as": "targetPoint" }
      ]
    }
  };
}

function createTitleLineCell(id, x1, y1, x2, y2, strokeWidth) {
  return {
    "@_id": id,
    "@_value": "",
    "@_style": [
      "endArrow=none",
      "html=1",
      "rounded=0",
      "strokeColor=#000000",
      `strokeWidth=${strokeWidth}`,
      "fillColor=none"
    ].join(";"),
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: {
      "@_relative": "1",
      "@_as": "geometry",
      mxPoint: [
        { "@_x": Number(x1.toFixed(3)), "@_y": Number(y1.toFixed(3)), "@_as": "sourcePoint" },
        { "@_x": Number(x2.toFixed(3)), "@_y": Number(y2.toFixed(3)), "@_as": "targetPoint" }
      ]
    }
  };
}

function titleTextStyle(fontSize, italic = false, bold = false, align = "center") {
  const fontStyle = (bold ? 1 : 0) + (italic ? 2 : 0);
  return [
    "text",
    "html=1",
    `align=${align}`,
    "verticalAlign=middle",
    "labelPosition=center",
    "verticalLabelPosition=middle",
    "whiteSpace=wrap",
    "rounded=0",
    "strokeColor=none",
    "fillColor=none",
    "fontFamily=Times New Roman",
    `fontSize=${fontSize}`,
    fontStyle ? `fontStyle=${fontStyle}` : "",
    "fontColor=#000000",
    "spacing=1",
    "spacingLeft=2",
    "spacingRight=2",
    "spacingTop=0",
    "spacingBottom=0",
    "overflow=hidden"
  ].filter(Boolean).join(";");
}

function titleBlockBoxForPage(page) {
  const frame = frameBoxForPage(page);
  const width = mmToPageX(FRAME_RULES.titleBlock.widthMm, page);
  const height = mmToPageY(FRAME_RULES.titleBlock.heightMm, page);
  return {
    x: frame.x + frame.width - width,
    y: frame.y + frame.height - height,
    width,
    height
  };
}

function contentTitleLineDefinitions(page) {
  const box = titleBlockBoxForPage(page);
  const xs = CONTENT_TITLE_BLOCK_GRID.x.map((ratio) => box.x + box.width * ratio);
  const ys = CONTENT_TITLE_BLOCK_GRID.y.map((ratio) => box.y + box.height * ratio);
  const rs = CONTENT_TITLE_BLOCK_GRID.rightSubX.map((ratio) => box.x + box.width * ratio);
  const thick = FRAME_RULES.titleBlock.thickStrokeWidth;
  const thin = FRAME_RULES.titleBlock.thinStrokeWidth;
  const defs = [];
  const add = (id, x1, y1, x2, y2, strokeWidth) => defs.push({ id, x1, y1, x2, y2, strokeWidth });

  add("v0_outer_left", xs[0], ys[0], xs[0], ys[8], thick);
  add("v1_left_grid", xs[1], ys[0], xs[1], ys[8], thick);
  add("v2_left_grid", xs[2], ys[0], xs[2], ys[8], thick);
  add("v3_left_grid", xs[3], ys[0], xs[3], ys[8], thick);
  add("v4_left_grid", xs[4], ys[0], xs[4], ys[8], thick);
  add("v5_left_mid_divider", xs[5], ys[0], xs[5], ys[8], thick);
  add("v6_mid_right_divider", xs[6], ys[3], xs[6], ys[8], thick);
  add("v7_right_page_divider", xs[7], ys[3], xs[7], ys[5], thick);
  add("v8_right_pages_divider", xs[8], ys[3], xs[8], ys[5], thick);
  add("v9_outer_right", xs[9], ys[0], xs[9], ys[8], thick);
  add("rv1_right_small", rs[1], ys[4], rs[1], ys[5], thin);
  add("rv2_right_small", rs[2], ys[4], rs[2], ys[5], thin);

  add("h0_outer_top", xs[0], ys[0], xs[9], ys[0], thick);
  add("h1_left_revision", xs[0], ys[1], xs[5], ys[1], thin);
  add("h2_left_revision", xs[0], ys[2], xs[5], ys[2], thick);
  add("h3_code_bottom", xs[0], ys[3], xs[9], ys[3], thick);
  add("h4_left_signature", xs[0], ys[4], xs[5], ys[4], thin);
  add("h4_right_page", xs[6], ys[4], xs[9], ys[4], thick);
  add("h5_left_signature", xs[0], ys[5], xs[5], ys[5], thick);
  add("h5_right_department", xs[6], ys[5], xs[9], ys[5], thick);
  add("h6_left_blank", xs[0], ys[6], xs[5], ys[6], thin);
  add("h7_left_blank", xs[0], ys[7], xs[5], ys[7], thin);
  add("h8_outer_bottom", xs[0], ys[8], xs[9], ys[8], thick);
  return { box, xs, ys, rs, defs };
}

function createContentTitleTextCell(id, value, x1, y1, x2, y2, fontSize, options = {}) {
  return createVertexCell(
    `${CONTENT_TITLE_PREFIX}${id}`,
    value,
    titleTextStyle(fontSize, Boolean(options.italic), Boolean(options.bold), options.align || "center"),
    x1,
    y1,
    x2 - x1,
    y2 - y1
  );
}

function createContentPageTitleBlockCells(page) {
  const { box, xs, ys, rs, defs } = contentTitleLineDefinitions(page);
  const cells = [
    createVertexCell(
      `${CONTENT_TITLE_PREFIX}background`,
      "",
      "rounded=0;whiteSpace=wrap;html=1;strokeColor=none;fillColor=#ffffff;pointerEvents=0;movable=0;resizable=0;rotatable=0;deletable=0;editable=0;connectable=0",
      box.x,
      box.y,
      box.width,
      box.height
    )
  ];

  for (const line of defs) {
    cells.push(createTitleLineCell(`${CONTENT_TITLE_PREFIX}${line.id}`, line.x1, line.y1, line.x2, line.y2, line.strokeWidth));
  }

  cells.push(
    createContentTitleTextCell("code", "BrSTU.241297.005 E3", xs[5], ys[0], xs[9], ys[3], 32),
    createContentTitleTextCell("sign_header", "Sign", xs[3], ys[2], xs[4], ys[3], 14),
    createContentTitleTextCell("date_header", "Date", xs[4], ys[2], xs[5], ys[3], 14),
    createContentTitleTextCell("author_label", "Author", xs[0], ys[3], xs[1], ys[4], 8.5),
    createContentTitleTextCell("author_name", "Wang Gen", xs[1], ys[3], xs[3], ys[4], 9.5),
    createContentTitleTextCell("supervisor_label", "Supervisor", xs[0], ys[4], xs[1], ys[5], 7.5),
    createContentTitleTextCell("supervisor_name", "Razumeichik V.S.", xs[1], ys[4], xs[3], ys[5], 8.7),
    createContentTitleTextCell("title", "EdgeHub Temperature\nArchitecture and Control\nFlow", xs[5], ys[3], xs[6], ys[8], 17),
    createContentTitleTextCell("page_label", "Page", xs[7], ys[3], xs[8], ys[4], 15),
    createContentTitleTextCell("pages_label", "Pages", xs[8], ys[3], xs[9], ys[4], 15),
    createContentTitleTextCell("sheet_mark", "D", xs[6], ys[4], rs[1], ys[5], 15),
    createContentTitleTextCell("page_number", "1", xs[7], ys[4], xs[8], ys[5], 15),
    createContentTitleTextCell("pages_number", "1", xs[8], ys[4], xs[9], ys[5], 15),
    createContentTitleTextCell("department", "Э-2024\nComputer&Systems\nDepartment", xs[6], ys[5], xs[9], ys[8], 13)
  );

  return cells;
}

function clonePlain(value) {
  return JSON.parse(JSON.stringify(value));
}

function readReferenceTitleBlockCells(page) {
  if (!fs.existsSync(TITLE_BLOCK_REFERENCE_PATH)) return null;
  const xml = fs.readFileSync(TITLE_BLOCK_REFERENCE_PATH, "utf8");
  const document = parser.parse(xml);
  const diagram = asArray(document.mxfile?.diagram)[0];
  const cells = asArray(diagram?.mxGraphModel?.root?.mxCell)
    .filter((cell) => String(cell["@_id"] || "").startsWith(CONTENT_TITLE_PREFIX))
    .map(clonePlain);
  if (!cells.length) return null;

  const background = cells.find((cell) => String(cell["@_id"] || "") === `${CONTENT_TITLE_PREFIX}background`);
  if (!background?.mxGeometry) return null;
  const sourceBox = {
    x: attrNumber(background.mxGeometry, "x"),
    y: attrNumber(background.mxGeometry, "y"),
    width: attrNumber(background.mxGeometry, "width"),
    height: attrNumber(background.mxGeometry, "height")
  };
  if (sourceBox.width <= 0 || sourceBox.height <= 0) return null;

  const targetBox = titleBlockBoxForPage(page);
  const scaleX = targetBox.width / sourceBox.width;
  const scaleY = targetBox.height / sourceBox.height;
  const transformX = (x) => targetBox.x + (x - sourceBox.x) * scaleX;
  const transformY = (y) => targetBox.y + (y - sourceBox.y) * scaleY;

  for (const cell of cells) {
    const geometry = cell.mxGeometry;
    if (!geometry) continue;
    if (geometry["@_x"] != null) geometry["@_x"] = Number(transformX(attrNumber(geometry, "x")).toFixed(3));
    if (geometry["@_y"] != null) geometry["@_y"] = Number(transformY(attrNumber(geometry, "y")).toFixed(3));
    if (geometry["@_width"] != null) geometry["@_width"] = Number((attrNumber(geometry, "width") * scaleX).toFixed(3));
    if (geometry["@_height"] != null) geometry["@_height"] = Number((attrNumber(geometry, "height") * scaleY).toFixed(3));
    for (const point of asArray(geometry.mxPoint)) {
      if (point["@_x"] != null) point["@_x"] = Number(transformX(attrNumber(point, "x")).toFixed(3));
      if (point["@_y"] != null) point["@_y"] = Number(transformY(attrNumber(point, "y")).toFixed(3));
    }
  }

  return cells;
}

function createTitleBlockCells(page) {
  return readReferenceTitleBlockCells(page) || createContentPageTitleBlockCells(page);
}

function createOuterFrameCell(page) {
  const box = frameBoxForPage(page);
  return createVertexCell(
    FRAME_RULES.outerBorder.id,
    "",
    [
      "rounded=0",
      "whiteSpace=wrap",
      "html=1",
      `strokeWidth=${FRAME_RULES.outerBorder.strokeWidth}`,
      `strokeColor=${FRAME_RULES.outerBorder.strokeColor}`,
      "fillColor=none",
      "pointerEvents=0",
      "movable=0",
      "resizable=0",
      "rotatable=0",
      "deletable=0",
      "editable=0",
      "connectable=0"
    ].join(";"),
    box.x,
    box.y,
    box.width,
    box.height
  );
}

function replaceStyleValue(style, key, value) {
  const parts = String(style || "").split(";").filter(Boolean);
  let replaced = false;
  const updated = parts.map((part) => {
    if (part.startsWith(`${key}=`)) {
      replaced = true;
      return `${key}=${value}`;
    }
    return part;
  });
  if (!replaced) updated.push(`${key}=${value}`);
  return updated.join(";");
}

function normalizeTitleBlockStrokeWidths(root) {
  const thick = FRAME_RULES.titleBlock.thickStrokeWidth;
  const thin = FRAME_RULES.titleBlock.thinStrokeWidth;
  for (const cell of asArray(root.mxCell)) {
    const parent = String(cell["@_parent"] || "");
    const id = String(cell["@_id"] || "");
    if (parent !== FRAME_RULES.titleBlock.id && id !== FRAME_RULES.titleBlock.id) continue;
    const style = String(cell["@_style"] || "");
    if (!/strokeWidth=/.test(style)) continue;
    const current = Number((style.match(/strokeWidth=([0-9.]+)/) || [])[1]);
    if (!Number.isFinite(current)) continue;
    cell["@_style"] = replaceStyleValue(style, "strokeWidth", current >= (thick + thin) / 2 ? thick : thin);
  }
}

function scalePointAttrs(point, scaleX, scaleY) {
  if (!point) return;
  if (point["@_x"] != null) point["@_x"] = Number((attrNumber(point, "x") * scaleX).toFixed(3));
  if (point["@_y"] != null) point["@_y"] = Number((attrNumber(point, "y") * scaleY).toFixed(3));
}

function resizeTitleBlockToContentPageSize(root, page) {
  const titleCell = asArray(root.mxCell).find((cell) => String(cell["@_id"] || "") === FRAME_RULES.titleBlock.id);
  if (!titleCell?.mxGeometry) return;
  const g = titleCell.mxGeometry;
  const oldWidth = attrNumber(g, "width");
  const oldHeight = attrNumber(g, "height");
  const targetWidth = mmToPageX(FRAME_RULES.titleBlock.widthMm, page);
  const targetHeight = mmToPageY(FRAME_RULES.titleBlock.heightMm, page);
  if (oldWidth <= 0 || oldHeight <= 0) return;
  const scaleX = targetWidth / oldWidth;
  const scaleY = targetHeight / oldHeight;
  g["@_width"] = Number(targetWidth.toFixed(3));
  g["@_height"] = Number(targetHeight.toFixed(3));

  for (const cell of asArray(root.mxCell)) {
    if (String(cell["@_parent"] || "") !== FRAME_RULES.titleBlock.id) continue;
    const childG = cell.mxGeometry;
    if (!childG) continue;
    if (childG["@_x"] != null) childG["@_x"] = Number((attrNumber(childG, "x") * scaleX).toFixed(3));
    if (childG["@_y"] != null) childG["@_y"] = Number((attrNumber(childG, "y") * scaleY).toFixed(3));
    if (childG["@_width"] != null) childG["@_width"] = Number((attrNumber(childG, "width") * scaleX).toFixed(3));
    if (childG["@_height"] != null) childG["@_height"] = Number((attrNumber(childG, "height") * scaleY).toFixed(3));
    for (const point of asArray(childG.mxPoint)) scalePointAttrs(point, scaleX, scaleY);
  }
}

function setTitleBlockValues(root) {
  const values = {
    "pFFQBGnBG81xobuCz_b_-18": "Name",
    "pFFQBGnBG81xobuCz_b_-19": "Sign",
    "pFFQBGnBG81xobuCz_b_-20": "Date",
    "pFFQBGnBG81xobuCz_b_-21": "Executed",
    "pFFQBGnBG81xobuCz_b_-22": "Checked",
    "pFFQBGnBG81xobuCz_b_-23": '<font style="font-size: 8px;">Razumeichik V.S.</font>',
    "pFFQBGnBG81xobuCz_b_-24": '<font style="font-size: 8px;">Wang Gen</font>',
    "pFFQBGnBG81xobuCz_b_-25": '<font style="font-size: 28px;">BrSTU.241297.005 E3</font>',
    "pFFQBGnBG81xobuCz_b_-36": '<font style="font-size: 18px;">EdgeHub Temperature Control<br>Architecture and Control Flow</font>',
    "pFFQBGnBG81xobuCz_b_-37": "Page",
    "pFFQBGnBG81xobuCz_b_-38": "Pages 1",
    "pFFQBGnBG81xobuCz_b_-39": '<font style="font-size: 14px;">Department of Computer and System</font>'
  };
  for (const cell of asArray(root.mxCell)) {
    const id = String(cell["@_id"] || "");
    if (Object.prototype.hasOwnProperty.call(values, id)) cell["@_value"] = values[id];
  }
}

function alignTitleBlockToFrame(root, page) {
  const frame = frameBoxForPage(page);
  const titleCell = asArray(root.mxCell).find((cell) => String(cell["@_id"] || "") === FRAME_RULES.titleBlock.id);
  if (!titleCell?.mxGeometry) return;
  const g = titleCell.mxGeometry;
  const width = attrNumber(g, "width");
  const height = attrNumber(g, "height");
  g["@_x"] = Number((frame.x + frame.width - width).toFixed(3));
  g["@_y"] = Number((frame.y + frame.height - height).toFixed(3));
}

function hasExistingTitleBlock(root) {
  return asArray(root.mxCell).some((cell) => {
    const id = String(cell["@_id"] || "");
    const parent = String(cell["@_parent"] || "");
    return id.startsWith(CONTENT_TITLE_PREFIX) ||
      id.startsWith(LEGACY_TITLE_PREFIX) ||
      parent.startsWith(LEGACY_TITLE_PREFIX);
  });
}

function purgeExisting(root) {
  const existing = asArray(root.mxCell);
  const rootCell = existing.find((cell) => String(cell["@_id"] || "") === "0") || { "@_id": "0" };
  const layerCell = existing.find((cell) => String(cell["@_id"] || "") === "1") || { "@_id": "1", "@_parent": "0" };
  root.mxCell = [rootCell, layerCell];
}

const sideToPortName = {
  right: "east",
  left: "west",
  bottom: "south",
  top: "north",
  east: "east",
  west: "west",
  south: "south",
  north: "north"
};

function normalizePort(port) {
  const normalized = sideToPortName[port];
  if (!normalized) throw new Error(`Unknown port ${port}`);
  return normalized;
}

function portPoint(box, port) {
  const normalized = normalizePort(port);
  if (box.gost_type === "data") {
    const skewHalf = symbolGeometry.data.skew / 2;
    if (normalized === "east") return { x: box.x + box.width - skewHalf, y: box.centerY };
    if (normalized === "west") return { x: box.x + skewHalf, y: box.centerY };
  }
  if (normalized === "east") return { x: box.x + box.width, y: box.centerY };
  if (normalized === "west") return { x: box.x, y: box.centerY };
  if (normalized === "south") return { x: box.centerX, y: box.y + box.height };
  if (normalized === "north") return { x: box.centerX, y: box.y };
  throw new Error(`Unknown port ${port}`);
}

function compact(points) {
  const cleaned = [];
  for (const point of points) {
    const last = cleaned[cleaned.length - 1];
    if (!last || Math.abs(last.x - point.x) > 0.1 || Math.abs(last.y - point.y) > 0.1) cleaned.push(point);
  }
  return cleaned.filter((point, index, list) => {
    if (index === 0 || index === list.length - 1) return true;
    const prev = list[index - 1];
    const next = list[index + 1];
    return !(
      (Math.abs(prev.x - point.x) <= 0.1 && Math.abs(point.x - next.x) <= 0.1) ||
      (Math.abs(prev.y - point.y) <= 0.1 && Math.abs(point.y - next.y) <= 0.1)
    );
  });
}

function makeRoute(source, target, fromPort, toPort, route_points, generator) {
  return {
    from_port: normalizePort(fromPort),
    to_port: normalizePort(toPort),
    route_points: ["connectCircleMainToTop", "connectStartStemToDistributionBus", "connectStartStemToDistributionBusAndFinalConnector"].includes(generator) ? route_points : compact(route_points),
    generator
  };
}

function connectVertical(source, target) {
  return makeRoute(source, target, "south", "north", [portPoint(source, "south"), portPoint(target, "north")], "connectVertical");
}

function connectHorizontal(source, target, sourcePort = "east", targetPort = "west") {
  return makeRoute(source, target, sourcePort, targetPort, [portPoint(source, sourcePort), portPoint(target, targetPort)], "connectHorizontal");
}

function connectOrthogonal(source, target, sourcePort, targetPort, lane) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  const sourcePortName = normalizePort(sourcePort);
  const targetPortName = normalizePort(targetPort);
  const horizontalFirst = sourcePortName === "east" || sourcePortName === "west";
  const points = horizontalFirst
    ? [start, { x: lane, y: start.y }, { x: lane, y: end.y }, end]
    : [start, { x: start.x, y: lane }, { x: end.x, y: lane }, end];
  return makeRoute(source, target, sourcePortName, targetPortName, points, "connectOrthogonal");
}

function connectToCircle(source, circle, direction = "east", lane = null) {
  const targetPort = { east: "west", west: "east", north: "south", south: "north" }[direction];
  if (!targetPort) throw new Error(`Unknown circle direction ${direction}`);
  const sourcePort = direction;
  if (lane == null) return connectHorizontal(source, circle, sourcePort, targetPort);
  return connectOrthogonal(source, circle, sourcePort, targetPort, lane);
}

function connectFromCircle(circle, target, direction = "east", lane = null) {
  const sourcePort = direction;
  const targetPort = { east: "west", west: "east", north: "south", south: "north" }[direction];
  if (!targetPort) throw new Error(`Unknown circle direction ${direction}`);
  if (lane == null) return connectHorizontal(circle, target, sourcePort, targetPort);
  return connectOrthogonal(circle, target, sourcePort, targetPort, lane);
}

function connectCircleToTop(circle, target, laneY = null) {
  const start = portPoint(circle, "south");
  const end = portPoint(target, "north");
  const points = laneY == null ? [start, end] : [start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end];
  return makeRoute(circle, target, "south", "north", points, "connectToCircleTop");
}

function connectCircleToMergedTop(circle, target, mergeY) {
  const start = portPoint(circle, "south");
  const end = portPoint(target, "north");
  return makeRoute(circle, target, "south", "north", [start, { x: start.x, y: mergeY }, { x: end.x, y: mergeY }, end], "connectCircleToMergedTop");
}

function connectCircleMainToTop(circle, target, mergeY) {
  const start = portPoint(circle, "south");
  const end = portPoint(target, "north");
  return makeRoute(circle, target, "south", "north", [start, { x: start.x, y: mergeY }, end], "connectCircleMainToTop");
}

function connectCircleSideToMain(circle, target, mergeY) {
  const start = portPoint(circle, "south");
  const end = portPoint(target, "north");
  return makeRoute(circle, target, "south", "north", [start, { x: start.x, y: mergeY }, { x: end.x, y: mergeY }, end], "connectCircleSideToMain");
}

function connectLeftToCircle(source, circle) {
  return makeRoute(source, circle, "west", "east", [portPoint(source, "west"), portPoint(circle, "east")], "connectToCircle");
}

function connectWestToEastOrthogonal(source, target, laneX) {
  const start = portPoint(source, "west");
  const end = portPoint(target, "east");
  return makeRoute(source, target, "west", "east", [start, { x: laneX, y: start.y }, { x: laneX, y: end.y }, end], "connectOrthogonal");
}

function connectDownThenHorizontal(source, target, targetPort, laneY) {
  const start = portPoint(source, "south");
  const end = portPoint(target, targetPort);
  return makeRoute(source, target, "south", targetPort, [start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end], "connectDownThenHorizontal");
}

function connectToStoredDataBottom(source, target, sourcePort, laneY) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, "south");
  return makeRoute(source, target, sourcePort, "south", [start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end], "connectToStoredDataBottom");
}

function connectToSideFromMain(source, target, sourcePort, targetPort) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  return makeRoute(source, target, sourcePort, targetPort, [start, end], "connectToSideFromMain");
}

function connectBranchFromVerticalTrunk(source, target, branchY, targetPort = "east", sourcePort = "south") {
  const start = { x: source.centerX, y: branchY };
  const end = portPoint(target, targetPort);
  const sourcePortName = normalizePort(sourcePort);
  const targetPortName = normalizePort(targetPort);
  const points = targetPortName === "north"
    ? [start, { x: end.x, y: branchY }, end]
    : [start, end];
  return makeRoute(source, target, sourcePortName, targetPortName, points, "connectBranchFromVerticalTrunk");
}

function connectBranchFromHorizontalTrunk(source, target, branchX, targetPort = "west", sourcePort = "east") {
  const sourcePortName = normalizePort(sourcePort);
  const targetPortName = normalizePort(targetPort);
  const trunkStart = portPoint(source, sourcePortName);
  const start = { x: branchX, y: trunkStart.y };
  const end = portPoint(target, targetPortName);
  const points = targetPortName === "west" || targetPortName === "east"
    ? [start, { x: branchX, y: end.y }, end]
    : [start, { x: end.x, y: trunkStart.y }, end];
  return makeRoute(source, target, sourcePortName, targetPortName, points, "connectBranchFromHorizontalTrunk");
}

function connectDownFromDistributionBus(source, target, busY) {
  const start = { x: target.centerX, y: busY };
  const end = portPoint(target, "north");
  return makeRoute(source, target, "south", "north", [start, end], "connectDownFromDistributionBus");
}

function connectDecisionSideToConnector(source, target, side) {
  return side === "west"
    ? connectHorizontal(source, target, "west", "east")
    : connectHorizontal(source, target, "east", "west");
}

function connectSideOutput(source, target, laneX, sourcePort = "west", targetPort = "east") {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  return makeRoute(source, target, sourcePort, targetPort, [start, { x: laneX, y: start.y }, { x: laneX, y: end.y }, end], "connectSideOutput");
}

function connectViaLanes(source, target, sourcePort, targetPort, laneA, laneB) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  const sourcePortName = normalizePort(sourcePort);
  const targetPortName = normalizePort(targetPort);
  return makeRoute(
    source,
    target,
    sourcePortName,
    targetPortName,
    [
      start,
      { x: start.x, y: laneA },
      { x: laneB, y: laneA },
      { x: laneB, y: end.y },
      end
    ],
    "connectViaLanes"
  );
}

function connectOrthogonalWithSourceLane(source, target, sourcePort, targetPort, laneX) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  const sourcePortName = normalizePort(sourcePort);
  const targetPortName = normalizePort(targetPort);
  return makeRoute(
    source,
    target,
    sourcePortName,
    targetPortName,
    [start, { x: laneX, y: start.y }, { x: laneX, y: end.y }, end],
    "connectOrthogonalWithSourceLane"
  );
}

function routeForEdge(edge, layout) {
  const source = layout.positions.get(edge.from);
  const target = layout.positions.get(edge.to);
  const busY = model.layout_policy?.distribution_bus_y || 260;
  const busLeftX = model.layout_policy?.distribution_bus_left_x || 300;
  const verticalBranchEdges = new Set(model.layout_policy?.vertical_branch_edge_ids || []);
  const busBranchEdges = new Set((model.branch_groups || []).flatMap((group) => group.branch_edge_ids || []));
  if (edge.id === "m01") {
    const start = portPoint(source, "south");
    const end = portPoint(target, "north");
    const busRightX = model.layout_policy?.distribution_bus_right_x || end.x;
    const bottomY = model.layout_policy?.bottom_return_bus_y || end.y;
    return makeRoute(
      source,
      target,
      "south",
      "north",
      [
        start,
        { x: start.x, y: busY },
        { x: busRightX, y: busY },
        { x: busRightX, y: bottomY },
        { x: end.x, y: bottomY },
        end
      ],
      "connectStartStemToDistributionBusAndFinalConnector"
    );
  }
  if (edge.id === "m02") return connectVertical(source, target);
  if (busBranchEdges.has(edge.id)) return connectDownFromDistributionBus(source, target, busY);
  if (verticalBranchEdges.has(edge.id)) return connectVertical(source, target);
  switch (edge.id) {
    case "s13": return connectDecisionSideToConnector(source, target, "east");
    case "t08": return connectDecisionSideToConnector(source, target, "west");
    case "p07": return connectDecisionSideToConnector(source, target, "east");
    case "c13": return connectOrthogonal(source, target, "east", "west", (source.centerX + target.centerX) / 2);
    case "j01": return connectHorizontal(source, target, "east", "west");
    default:
      if (Math.abs(source.centerX - target.centerX) < 2 && source.centerY < target.centerY) return connectVertical(source, target);
      if (Math.abs(source.centerY - target.centerY) < 2) {
        return source.centerX < target.centerX
          ? connectHorizontal(source, target, "east", "west")
          : connectHorizontal(source, target, "west", "east");
      }
      return source.centerX < target.centerX
        ? connectOrthogonal(source, target, "east", "west", (source.x + source.width + target.x) / 2)
        : connectOrthogonal(source, target, "west", "east", (target.x + target.width + source.x) / 2);
  }
}

function finalDirection(points) {
  const a = points[points.length - 2];
  const b = points[points.length - 1];
  if (Math.abs(a.x - b.x) > Math.abs(a.y - b.y)) return b.x > a.x ? "right" : "left";
  return b.y > a.y ? "down" : "up";
}

function routeHasNonStandardDirection(route) {
  const points = route.route_points;
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1];
    const b = points[i];
    if (Math.abs(a.x - b.x) > 0.1 && b.x < a.x) return true;
    if (Math.abs(a.y - b.y) > 0.1 && b.y < a.y) return true;
  }
  return false;
}

function arrowRequired(edge, route) {
  const arrowlessEdgeIds = new Set(model.layout_policy?.arrowless_edge_ids || []);
  if (arrowlessEdgeIds.has(edge.id)) return false;
  return routeHasNonStandardDirection(route);
}

function edgeStyle(edge, route) {
  const arrow = arrowRequired(edge, route) ? "endArrow=open;endFill=0;endSize=12" : "endArrow=none";
  const exit = { east: "exitX=1;exitY=0.5", west: "exitX=0;exitY=0.5", north: "exitX=0.5;exitY=0", south: "exitX=0.5;exitY=1" }[route.from_port];
  const entry = { east: "entryX=1;entryY=0.5", west: "entryX=0;entryY=0.5", north: "entryX=0.5;entryY=0", south: "entryX=0.5;entryY=1" }[route.to_port];
  const dashed = edge.line_style === "dashed" ? "dashed=1;dashPattern=8 4" : "";
  return [
    "html=1",
    "edgeStyle=orthogonalEdgeStyle",
    "rounded=0",
    "orthogonalLoop=1",
    "jettySize=auto",
    "curved=0",
    arrow,
    dashed,
    "strokeColor=#000000",
    `strokeWidth=${FLOW_LINE_STROKE}`,
    "fontFamily=Helvetica",
    "fontSize=18",
    "fontColor=#000000",
    exit,
    entry,
    "exitDx=0",
    "exitDy=0",
    "entryDx=0",
    "entryDy=0"
  ].filter(Boolean).join(";");
}

function createEdgeCell(edge, route) {
  const points = route.route_points;
  const geometry = {
    "@_relative": "1",
    "@_as": "geometry",
    mxPoint: [
      { "@_x": Number(points[0].x.toFixed(3)), "@_y": Number(points[0].y.toFixed(3)), "@_as": "sourcePoint" },
      { "@_x": Number(points[points.length - 1].x.toFixed(3)), "@_y": Number(points[points.length - 1].y.toFixed(3)), "@_as": "targetPoint" }
    ]
  };
  const waypoints = points.slice(1, -1);
  if (waypoints.length) {
    geometry.Array = { "@_as": "points", mxPoint: waypoints.map((point) => ({ "@_x": Number(point.x.toFixed(3)), "@_y": Number(point.y.toFixed(3)) })) };
  }
  return {
    "@_id": `${EDGE_PREFIX}${edge.id}`,
    "@_value": "",
    "@_style": edgeStyle(edge, route),
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: geometry
  };
}

function labelPosition(edge, route) {
  if (!edge.label) return null;
  const labelWidth = labelWidthFor(edge.label);
  const verticalLabelX = (segment, side = "right") => {
    const x = (segment.a.x + segment.b.x) / 2;
    const y = (segment.a.y + segment.b.y) / 2;
    const sign = side === "left" ? -1 : 1;
    return { x: x + sign * (LABEL_GAP_FROM_LINE + labelWidth / 2), y };
  };
  const horizontalLabelY = (segment, side = "above") => {
    const x = (segment.a.x + segment.b.x) / 2;
    const y = (segment.a.y + segment.b.y) / 2;
    const sign = side === "below" ? 1 : -1;
    return { x, y: y + sign * (LABEL_GAP_FROM_LINE + LABEL_HEIGHT / 2) };
  };
  if (["t01", "s01", "p01", "c01", "f00", "g01", "r01", "d01"].includes(edge.id)) {
    const points = route.route_points;
    return verticalLabelX({ a: points[0], b: points[points.length - 1] }, "right");
  }
  if (edge.id === "m01") {
    const points = route.route_points;
    return horizontalLabelY({ a: points[1], b: points[2] }, "above");
  }
  if (["e06", "e10_no", "e15", "e34"].includes(edge.id)) {
    const points = route.route_points;
    const a = points[0];
    const b = points[points.length - 1];
    return verticalLabelX({ a, b }, "right");
  }
  if (["s06", "p02", "c03", "t07", "d07"].includes(edge.id)) {
    const points = route.route_points;
    const a = points[0];
    const b = points[points.length - 1];
    return verticalLabelX({ a, b }, "right");
  }
  if (edge.id === "f02") {
    const points = route.route_points;
    const a = points.length > 3 ? points[2] : points[0];
    const b = points.length > 3 ? points[3] : points[1];
    return horizontalLabelY({ a, b }, "above");
  }
  if (["c13", "p07", "s13", "t08", "j01"].includes(edge.id)) {
    const points = route.route_points;
    const a = points[0];
    const b = points.length > 2 ? points[1] : points[points.length - 1];
    return horizontalLabelY({ a, b }, "above");
  }
  if (edge.id === "f01_legacy") {
    const points = route.route_points;
    const a = points.length > 3 ? points[1] : points[0];
    const b = points.length > 3 ? points[2] : points[points.length - 1];
    return verticalLabelX({ a, b }, "right");
  }
  if (edge.id === "t08_legacy") {
    const points = route.route_points;
    return horizontalLabelY({ a: points[0], b: points[1] }, "above");
  }
  if (edge.id === "r19_legacy") {
    const points = route.route_points;
    const a = points.length > 3 ? points[1] : points[0];
    const b = points.length > 3 ? points[2] : points[points.length - 1];
    return verticalLabelX({ a, b }, "left");
  }
  if (["f02", "t08", "r14"].includes(edge.id)) {
    const points = route.route_points;
    const a = points[0];
    const b = points.length > 2 ? points[1] : points[points.length - 1];
    return horizontalLabelY({ a, b }, "above");
  }
  if (["e06_invalid_a", "e10_yes_a", "e15_fault_a"].includes(edge.id)) {
    const points = route.route_points;
    const a = points.length > 2 ? points[1] : points[0];
    const b = points.length > 2 ? points[2] : points[points.length - 1];
    return horizontalLabelY({ a, b }, "above");
  }
  if (edge.id === "e63") {
    const points = route.route_points;
    const a = points[0];
    return { x: a.x + labelWidth / 2 + 4, y: a.y - (LABEL_GAP_FROM_LINE + LABEL_HEIGHT / 2) };
  }
  if (edge.id === "e67a") {
    const points = route.route_points;
    const a = points[0];
    const b = points[points.length - 1];
    return verticalLabelX({ a, b }, "right");
  }
  if (edge.id === "e33_invalid") {
    const points = route.route_points;
    const a = points[0];
    const b = points[points.length - 1];
    return horizontalLabelY({ a, b }, "above");
  }
  const points = route.route_points;
  const a = points[0];
  const b = points.length > 2 ? points[1] : points[points.length - 1];
  return horizontalLabelY({ a, b }, "above");
}

function labelWidthFor(label) {
  return Math.max(52, String(label).length * 9 + 14);
}

function createLabelCell(edge, point) {
  const width = labelWidthFor(edge.label);
  return createVertexCell(
    `${LABEL_PREFIX}${edge.id}`,
    edge.label,
    `text;html=1;strokeColor=none;fillColor=#ffffff;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontFamily=Helvetica;fontSize=${LABEL_FONT_SIZE};fontColor=#000000;autosize=0;spacing=1;`,
    point.x - width / 2,
    point.y - LABEL_HEIGHT / 2,
    width,
    LABEL_HEIGHT
  );
}

function createBottomReturnArrowCells(layout) {
  const y = model.layout_policy?.bottom_return_bus_y;
  const length = model.layout_policy?.bottom_return_arrow_length || 44;
  const offset = model.layout_policy?.bottom_return_arrow_offset || 12;
  const nodeIds = model.layout_policy?.bottom_return_arrow_node_ids || [];
  if (!Number.isFinite(y) || !nodeIds.length) return [];
  return nodeIds.flatMap((nodeId) => {
    const box = layout.positions.get(nodeId);
    if (!box) return [];
    const target = { x: box.centerX + offset, y };
    const source = { x: target.x + length, y };
    return [createDecorArrowLine(`${DECOR_PREFIX}bottom_return_arrow_${nodeId}`, source, target)];
  });
}

function createBottomReturnBusLeftCell(layout) {
  const y = model.layout_policy?.bottom_return_bus_y;
  const leftX = model.layout_policy?.bottom_return_bus_left_x;
  const finalConnectorId = model.layout_policy?.connector_exit_id;
  const finalConnector = finalConnectorId ? layout.positions.get(finalConnectorId) : null;
  if (!Number.isFinite(y) || !Number.isFinite(leftX) || !finalConnector || leftX >= finalConnector.centerX) return [];
  return [
    createDecorHorizontalLine(
      `${DECOR_PREFIX}bottom_return_bus_left`,
      leftX,
      y,
      finalConnector.centerX - leftX
    )
  ];
}

function makeLayout(page = model.page) {
  const positions = new Map();
  for (const node of model.nodes) {
    const box = withCenter(bboxFor(node));
    positions.set(node.id, { ...box, label: labelFor(node.label), gost_type: node.gost_type });
  }
  return { page, positions };
}

function enrichedModel(layout) {
  const incoming = new Map(model.nodes.map((node) => [node.id, []]));
  const outgoing = new Map(model.nodes.map((node) => [node.id, []]));
  const controlledBranchEdgeIds = new Set((model.branch_groups || []).flatMap((group) => group.branch_edge_ids || []));
  const edges = model.edges.map((edge) => {
    const route = routeForEdge(edge, layout);
    const label_position = labelPosition(edge, route);
    const enriched = {
      id: edge.id,
      from_node: edge.from,
      from_port: route.from_port,
      to_node: edge.to,
      to_port: route.to_port,
      route_points: route.route_points.map((point) => ({ x: Number(point.x.toFixed(3)), y: Number(point.y.toFixed(3)) })),
      arrow_required: arrowRequired(edge, route),
      arrow_style: arrowRequired(edge, route) ? "open 60-degree target arrow, anchored at target port" : "none; standard left-to-right/top-to-bottom GOST flow",
      style: {
        stroke: "black",
        stroke_width: 1.2,
        fill: "none",
        arrowhead: arrowRequired(edge, route) ? "open" : "none",
        arrowhead_size: 12,
        line_style: "orthogonal",
        rounded: false,
        dashed: edge.line_style === "dashed"
      },
      label: edge.label,
      label_position: label_position ? { x: Number(label_position.x.toFixed(3)), y: Number(label_position.y.toFixed(3)) } : null,
      flow_kind: edge.flow_kind,
      channel: edge.channel,
      line_symbol: edge.line_symbol,
      line_style: edge.line_style,
      line_style_basis: edge.line_style_basis,
      orthogonal_only: true
    };
    incoming.get(edge.to).push(enriched.id);
    outgoing.get(edge.from).push(enriched.id);
    return enriched;
  });
  const nodes = model.nodes.map((node) => {
    const box = withCenter({ ...bboxFor(node), gost_type: node.gost_type });
    const def = model.symbol_definitions[node.gost_type];
    const ports = {
      north: portPoint(box, "north"),
      south: portPoint(box, "south"),
      west: portPoint(box, "west"),
      east: portPoint(box, "east")
    };
    return {
      id: node.id,
      label: node.label,
      rendered_label: labelFor(node.label),
      gost_type: node.gost_type,
      bbox: {
        x: Number(box.x.toFixed(3)),
        y: Number(box.y.toFixed(3)),
        width: Number(box.width.toFixed(3)),
        height: Number(box.height.toFixed(3))
      },
      ports: {
        north: { x: Number(ports.north.x.toFixed(3)), y: Number(ports.north.y.toFixed(3)) },
        south: { x: Number(ports.south.x.toFixed(3)), y: Number(ports.south.y.toFixed(3)) },
        west: { x: Number(ports.west.x.toFixed(3)), y: Number(ports.west.y.toFixed(3)) },
        east: { x: Number(ports.east.x.toFixed(3)), y: Number(ports.east.y.toFixed(3)) }
      },
      allowed_input_sides: def.default_allowed_input_sides,
      allowed_output_sides: def.default_allowed_output_sides,
      expected_inputs: node.gost_type === "decision" ? 1 : def.expected_inputs,
      expected_outputs: node.gost_type === "decision" ? ">=2 labeled" : def.expected_outputs,
      actual_inputs: incoming.get(node.id),
      actual_outputs: outgoing.get(node.id),
      subflow_ref: node.subflow_ref,
      text_fit_rule: node.text_fit_rule,
      notes: node.notes
    };
  });
  return {
    standard_basis: {
      gost: model.diagram.standard,
      brstu: model.brstu,
      diagram_pdf_read: true,
      brstu_flowchart_specific_rule_found: model.brstu.official_flowchart_rule_found
    },
    symbol_definitions: model.symbol_definitions,
    nodes,
    edges,
    subflows: model.subflows,
    merge_groups: model.merge_groups || [],
    branch_groups: model.branch_groups || [],
    branch_columns: model.branch_columns || [],
    layout_policy: model.layout_policy || null,
    page: model.page
  };
}

function buildMainCells(layout, enriched) {
  const cells = [];
  for (const edge of model.edges) {
    const route = routeForEdge(edge, layout);
    cells.push(createEdgeCell(edge, route));
  }
  cells.push(...createBottomReturnBusLeftCell(layout));
  cells.push(...createBottomReturnArrowCells(layout));
  for (const node of model.nodes) {
    const box = layout.positions.get(node.id);
    cells.push(createVertexCell(`${ID_PREFIX}${node.id}`, box.label, styleFor(node.gost_type), box.x, box.y, box.width, box.height));
    if (node.gost_type === "predefined_process") {
      const inset = 14;
      cells.push(createDecorLine(`${DECOR_PREFIX}${node.id}_left`, box.x + inset, box.y, box.height));
      cells.push(createDecorLine(`${DECOR_PREFIX}${node.id}_right`, box.x + box.width - inset, box.y, box.height));
    }
  }
  for (const edge of enriched.edges) {
    if (edge.label_position) cells.push(createLabelCell(edge, edge.label_position));
  }
  return cells;
}

function createBlankMxFile(pageWidth, pageHeight, name = "Page-1") {
  return {
    mxfile: {
      "@_host": "Electron",
      "@_version": "24.7.17",
      diagram: {
        "@_name": name,
        mxGraphModel: {
          "@_dx": "1000",
          "@_dy": "700",
          "@_grid": "1",
          "@_gridSize": "10",
          "@_guides": "1",
          "@_tooltips": "1",
          "@_connect": "1",
          "@_arrows": "1",
          "@_fold": "1",
          "@_page": "1",
          "@_pageScale": "1",
          "@_pageWidth": pageWidth,
          "@_pageHeight": pageHeight,
          "@_math": "0",
          "@_shadow": "0",
          root: { mxCell: [{ "@_id": "0" }, { "@_id": "1", "@_parent": "0" }] }
        }
      }
    }
  };
}

function createSubflowDocument(ref, subflow) {
  const page = { width: 1100, height: 760 };
  const doc = createBlankMxFile(page.width, page.height, ref);
  const root = doc.mxfile.diagram.mxGraphModel.root;
  const x = 465;
  const yStart = 80;
  const stepGap = 120;
  const nodes = [
    { id: `${ref}_start`, label: `${ref}\nStart`, gost_type: "terminator", x: x + 85, y: yStart },
    ...subflow.steps.map((label, index) => ({ id: `${ref}_s${index + 1}`, label, gost_type: "process", x: x + 85, y: yStart + (index + 1) * stepGap })),
    { id: `${ref}_end`, label: `${ref}\nEnd`, gost_type: "terminator", x: x + 85, y: yStart + (subflow.steps.length + 1) * stepGap }
  ];
  const boxes = new Map();
  for (const node of nodes) {
    const box = withCenter({ ...bboxFor({ ...node, type: node.gost_type }), label: labelFor(node.label) });
    boxes.set(node.id, box);
    root.mxCell.push(createVertexCell(`${ID_PREFIX}${node.id}`, node.label, styleFor(node.gost_type), box.x, box.y, box.width, box.height));
  }
  for (let i = 0; i < nodes.length - 1; i += 1) {
    const source = boxes.get(nodes[i].id);
    const target = boxes.get(nodes[i + 1].id);
    const route = routeDirect(source, target, "bottom", "top");
    const edge = { id: `${ref}_e${i + 1}`, flow_kind: "control", label: "" };
    root.mxCell.push(createEdgeCell(edge, route));
  }
  root.mxCell.push(createVertexCell(`${ID_PREFIX}${ref}_title`, `${ref}: ${subflow.title}`, "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontFamily=Helvetica;fontSize=20;fontStyle=1;fontColor=#000000;", 250, 20, 600, 40));
  return doc;
}

function createSubflowDiagram(ref, subflow) {
  return createSubflowDocument(ref, subflow).mxfile.diagram;
}

function writeSubflows() {
  fs.mkdirSync(SUBFLOW_DIR, { recursive: true });
  for (const [ref, subflow] of Object.entries(model.subflows)) {
    const doc = createSubflowDocument(ref, subflow);
    fs.writeFileSync(path.join(SUBFLOW_DIR, `${ref}.drawio`), builder.build(doc));
  }
}

function removeGeneratedSubflows() {
  fs.rmSync(SUBFLOW_DIR, { recursive: true, force: true });
  if (fs.existsSync(COMBINED_OUTPUT_PATH)) fs.rmSync(COMBINED_OUTPUT_PATH);
}

function writeSymbolTable() {
  const lines = [
    "# Symbol Definition Table",
    "",
    "| gost_type | GOST section | Meaning | Shape | Input sides | Output sides |",
    "| --- | --- | --- | --- | --- | --- |"
  ];
  for (const [type, def] of Object.entries(model.symbol_definitions)) {
    lines.push(`| ${type} | ${def.gost_section} | ${def.meaning} | ${def.shape} | ${def.default_allowed_input_sides.join(", ")} | ${def.default_allowed_output_sides.join(", ")} |`);
  }
  fs.writeFileSync(SYMBOL_TABLE_PATH, `${lines.join("\n")}\n`);
}

function writePlan(enriched) {
  const lines = [
    "# GOST 19.701-90 / BrSTU Flowchart Plan",
    "",
    "## Normative Basis",
    "- The 23-page diagram.pdf was read and used as the binding symbol and connection standard.",
    "- Sections applied: 3.1 data symbols, 3.2 process symbols, 3.3 line symbols, 3.4 special symbols, 4.1 symbol use, 4.2 connections, 4.3 multiple outputs/repetition, and appendix examples.",
    "- No BrSTU official public flowchart-specific rule was found in the available search results. BrSTU/ESKD drawing-frame practice is retained through the A1 frame, title block, drawing number and page fields; GOST 19.701-90 controls the flowchart itself.",
    "",
    "## Generated Artifacts",
    "- Single-page main drawio/png/svg/pdf: optimized_architecture_flowchart.*",
    "- Machine model: gost_flow_model.json",
    "- Symbol table: symbol_definition_table.md",
    "- No predefined_process/function-block shapes are used; separate subflow pages are intentionally not generated.",
    "- Validation report: compliance_report.md",
    "",
    "## Main Diagram Nodes",
    ...enriched.nodes.map((node) => `- ${node.id}: ${node.label} (${node.gost_type}) ${node.subflow_ref ? `subflow=${node.subflow_ref}` : ""}`),
    "",
    "## Main Diagram Edges",
    ...enriched.edges.map((edge) => `- ${edge.id}: ${edge.from_node}.${edge.from_port} -> ${edge.to_node}.${edge.to_port}${edge.label ? ` [${edge.label}]` : ""}; ${edge.flow_kind}`)
  ];
  fs.writeFileSync(PLAN_PATH, `${lines.join("\n")}\n`);
}

function main() {
  const xml = fs.readFileSync(TEMPLATE_PATH, "utf8");
  const document = parser.parse(xml);
  const diagrams = asArray(document.mxfile.diagram);
  const diagram = diagrams[0];
  diagram["@_name"] = "Main A1 Flowchart";
  const graph = diagram.mxGraphModel;
  const page = {
    width: attrNumber(graph, "pageWidth", model.page.width),
    height: attrNumber(graph, "pageHeight", model.page.height),
    forbidden_area: model.page.forbidden_area
  };
  const layout = makeLayout(page);
  const enriched = enrichedModel(layout);
  fs.writeFileSync(MODEL_JSON_PATH, JSON.stringify(enriched, null, 2));
  writeSymbolTable();
  removeGeneratedSubflows();
  writePlan(enriched);
  purgeExisting(graph.root);
  const generatedCells = [
    ...buildMainCells(layout, enriched),
    ...createTitleBlockCells(page),
    createOuterFrameCell(page)
  ];
  graph.root.mxCell = asArray(graph.root.mxCell).concat(generatedCells);
  document.mxfile.diagram = [diagram];
  fs.writeFileSync(OUTPUT_PATH, builder.build(document));
  console.log(`Wrote ${OUTPUT_PATH}`);
  console.log(`Wrote ${MODEL_JSON_PATH}`);
}

main();
