#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser, XMLBuilder } = require("fast-xml-parser");
const ELK = require("elkjs/lib/elk.bundled.js");
const {
  SHAPE_RULES,
  DISPLAY_ALIASES,
  DISPLAY_LABEL_OVERRIDES,
  LABEL_RULES,
  normalizeText,
  ARROW_RULES,
  LONG_LINE_RULES,
  ROUTING_ENVELOPE_RULES,
  CONNECTOR_LOCALITY_RULES,
  VISUAL_BALANCE_RULES,
  FRAME_RULES,
  ROW_WRAP_RULES,
  PROGRAM_SCHEME_LAYOUT_RULES,
  NORMAL_BRANCH_LABELS,
  ABNORMAL_BRANCH_LABELS
} = require("./flow_rules");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = path.join(ROOT_DIR, "aa.drawio");
const MODEL_PATH = path.join(WORK_DIR, "flow_model.json");
const OUTPUT_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");
const METRICS_PATH = path.join(WORK_DIR, "layout_metrics.json");

const ID_PREFIX = "repo_flow_";
const EDGE_PREFIX = "repo_flow_edge_";
const LABEL_PREFIX = "repo_flow_label_";
const DECOR_PREFIX = "repo_flow_decor_";
const FRAME_PREFIX = "repo_template_";

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

const preferredSequence = PROGRAM_SCHEME_LAYOUT_RULES.rows.flatMap((lane) => lane.nodes);

function attrNumber(obj, key, fallback = 0) {
  const raw = obj && obj[`@_${key}`];
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

function asArray(value) {
  if (value == null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function containsChinese(text) {
  return /[\u3400-\u9fff]/.test(String(text || ""));
}

function shortenLabel(text) {
  if (containsChinese(text)) {
    throw new Error(`Chinese text is not allowed: ${text}`);
  }
  const trimmed = String(text || "").replace(/\s+/g, " ").trim();
  if (DISPLAY_ALIASES[trimmed]) {
    return DISPLAY_ALIASES[trimmed];
  }
  if (trimmed.length <= 28) {
    return trimmed;
  }
  return trimmed
    .replace(/\bTemperature\b/g, "Temp")
    .replace(/\bTelemetry\b/g, "Telem")
    .replace(/\bParameter\b/g, "Param")
    .replace(/\bParameters\b/g, "Params")
    .replace(/\bRecommendation\b/g, "Reco")
    .slice(0, 28)
    .trim();
}

function wrapLabel(text, maxCharsPerLine) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  if (!words.length) {
    return "";
  }
  const lines = [""];
  for (const word of words) {
    const current = lines[lines.length - 1];
    if (!current) {
      lines[lines.length - 1] = word;
    } else if (`${current} ${word}`.length <= maxCharsPerLine) {
      lines[lines.length - 1] = `${current} ${word}`;
    } else if (lines.length < 2) {
      lines.push(word);
    } else {
      lines[1] = `${lines[1]} ${word}`.trim();
    }
  }
  return lines.slice(0, 2).map((line) => {
    if (line.length <= maxCharsPerLine) {
      return line;
    }
    return line.slice(0, Math.max(1, maxCharsPerLine - 1)).trim();
  }).join("\n");
}

function fitLabelToShape(text, nodeType, width, height) {
  const shortened = shortenLabel(text);
  if (DISPLAY_LABEL_OVERRIDES[shortened]) {
    return DISPLAY_LABEL_OVERRIDES[shortened];
  }
  const innerWidth = nodeType === "decision"
    ? width * 0.58
    : nodeType === "connector"
      ? width * 0.60
      : nodeType === "stored_data"
        ? width * 0.62
      : ["data", "document", "manual_input"].includes(nodeType)
        ? width * 0.54
        : width * 0.64;
  const charWidth = nodeType === "decision" ? 8.8 : 9.8;
  const maxChars = clamp(Math.floor(innerWidth / charWidth), nodeType === "connector" ? 2 : 6, nodeType === "connector" ? 3 : 12);
  const wrapped = wrapLabel(shortened, maxChars);
  const lines = wrapped.split("\n");
  const maxLines = Math.max(1, Math.floor((height - 18) / 24));
  if (lines.length <= Math.min(2, maxLines)) {
    return wrapped;
  }
  throw new Error(`No readable two-line label override fits ${text}; add DISPLAY_LABEL_OVERRIDES instead of truncating the label.`);
}

function escapeText(value) {
  return String(value).replace(/\n/g, "<br>");
}

function fitEdgeLabel(text) {
  const label = shortenLabel(text);
  if (label.length <= 14) {
    return label;
  }
  return label.slice(0, 14).trim();
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
    "shadow=0",
    "gradientColor=none",
    extra
  ].filter(Boolean).join(";");
}

function styleFor(type) {
  switch (type) {
    case "terminator":
      return baseStyle("rounded=1;arcSize=50");
    case "process":
      return baseStyle("rounded=0");
    case "predefined_process":
      return baseStyle("rounded=0");
    case "decision":
      return baseStyle("rhombus;rounded=0");
    case "data":
      return baseStyle("shape=parallelogram;perimeter=parallelogramPerimeter;rounded=0");
    case "stored_data":
      return baseStyle("shape=mxgraph.flowchart.database;rounded=0;fontSize=18;spacingTop=22;spacingBottom=8;spacingLeft=10;spacingRight=10");
    case "document":
      return baseStyle("shape=document;boundedLbl=1;rounded=0");
    case "manual_input":
      return baseStyle("shape=manualInput;rounded=0");
    case "connector":
      return baseStyle("ellipse;aspect=fixed");
    default:
      throw new Error(`Unsupported node type: ${type}`);
  }
}

function getFinalSegmentDirection(edgeGeometry) {
  const points = edgeGeometry?.points || edgeGeometry || [];
  if (Array.isArray(points) && points.length >= 2) {
    for (let index = points.length - 1; index >= 1; index -= 1) {
      const prev = points[index - 1];
      const curr = points[index];
      const dx = curr.x - prev.x;
      const dy = curr.y - prev.y;
      if (Math.abs(dx) > 0.1 && Math.abs(dy) <= 0.1) {
        return dx > 0 ? "left-to-right" : "right-to-left";
      }
      if (Math.abs(dy) > 0.1 && Math.abs(dx) <= 0.1) {
        return dy > 0 ? "top-to-bottom" : "bottom-to-top";
      }
    }
  }
  const ports = edgeGeometry?.ports || {};
  const entryX = ports.entryX;
  const entryY = ports.entryY;
  if (entryX === 0 && entryY === 0.5) return "left-to-right";
  if (entryX === 1 && entryY === 0.5) return "right-to-left";
  if (entryX === 0.5 && entryY === 0) return "top-to-bottom";
  if (entryX === 0.5 && entryY === 1) return "bottom-to-top";
  return null;
}

function arrowStylePartsForDirection(direction) {
  if (ARROW_RULES.noArrowDirections.includes(direction)) {
    return ["endArrow=none"];
  }
  if (ARROW_RULES.arrowDirections.includes(direction)) {
    const fallback = ARROW_RULES.arrowStyle;
    return [
      `endArrow=${fallback.endArrow}`,
      `endFill=${fallback.endFill}`,
      `endSize=${fallback.endSize}`
    ];
  }
  throw new Error(`Cannot determine arrow style for edge direction ${direction}`);
}

function edgeStyle(edge, sourcePort, targetPort, routeInfo = {}) {
  const ports = routeInfo.ports || {};
  const portToPoint = (port) => {
    if (port === "left") return { x: 0, y: 0.5 };
    if (port === "right") return { x: 1, y: 0.5 };
    if (port === "bottom") return { x: 0.5, y: 1 };
    if (port === "top") return { x: 0.5, y: 0 };
    throw new Error(`Unsupported edge port: ${port}`);
  };
  const defaultExit = portToPoint(sourcePort);
  const defaultEntry = portToPoint(targetPort);
  const exitPoint = {
    x: ports.exitX ?? defaultExit.x,
    y: ports.exitY ?? defaultExit.y
  };
  const entryPoint = {
    x: ports.entryX ?? defaultEntry.x,
    y: ports.entryY ?? defaultEntry.y
  };
  const exit = [`exitX=${Number(exitPoint.x.toFixed(4))}`, `exitY=${Number(exitPoint.y.toFixed(4))}`];
  const entry = [`entryX=${Number(entryPoint.x.toFixed(4))}`, `entryY=${Number(entryPoint.y.toFixed(4))}`];
  const finalDirection = getFinalSegmentDirection({
    points: routeInfo.points,
    ports: { entryX: entryPoint.x, entryY: entryPoint.y }
  });
  if (!finalDirection) {
    throw new Error(`Cannot determine final segment direction for edge ${edge.id}`);
  }
  return [
    "html=1",
    "edgeStyle=orthogonalEdgeStyle",
    "rounded=0",
    "orthogonalLoop=1",
    "jettySize=auto",
    "curved=0",
    ...arrowStylePartsForDirection(finalDirection),
    "strokeColor=#000000",
    "strokeWidth=2",
    "fontFamily=Helvetica",
    "fontSize=18",
    "fontColor=#000000",
    ...exit,
    ...entry,
    "exitDx=0",
    "exitDy=0",
    "entryDx=0",
    "entryDy=0"
  ].join(";");
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

function createVertexCell(id, value, style, x, y, width, height, parent = "1") {
  return {
    "@_id": id,
    "@_value": escapeText(value),
    "@_style": style,
    "@_parent": parent,
    "@_vertex": "1",
    mxGeometry: createGeometry(x, y, width, height)
  };
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
  return {
    x: left,
    y: top,
    width: page.width - left - right,
    height: page.height - top - bottom
  };
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

function createEdgeCell(id, edge, source, target, route) {
  const mxGeometry = {
    "@_relative": "1",
    "@_as": "geometry"
  };
  if (route.waypoints.length) {
    mxGeometry.Array = {
      "@_as": "points",
      mxPoint: route.waypoints.map((point) => ({
        "@_x": Number(point.x.toFixed(3)),
        "@_y": Number(point.y.toFixed(3))
      }))
    };
  }
  const cell = {
    "@_id": id,
    "@_value": "",
    "@_style": edgeStyle(edge, route.sourcePort, route.targetPort, route),
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry
  };
  cell["@_source"] = `${ID_PREFIX}${source.id}`;
  cell["@_target"] = `${ID_PREFIX}${target.id}`;
  return cell;
}

function createDecorLine(id, x, y, height) {
  return {
    "@_id": id,
    "@_value": "",
    "@_style": "endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=2;",
    "@_parent": "1",
    "@_edge": "1",
    mxGeometry: {
      "@_width": "50",
      "@_height": "50",
      "@_relative": "1",
      "@_as": "geometry",
      mxPoint: [
        { "@_x": Number(x.toFixed(3)), "@_y": Number(y.toFixed(3)), "@_as": "sourcePoint" },
        { "@_x": Number(x.toFixed(3)), "@_y": Number((y + height).toFixed(3)), "@_as": "targetPoint" }
      ]
    }
  };
}

function labelBoxSize(value) {
  const label = fitEdgeLabel(value || "");
  const width = clamp(Math.round(label.length * 7 + 12), 36, 78);
  return { width, height: 26 };
}

function createLabelCell(id, value, x, y) {
  const label = shortenLabel(value);
  const size = labelBoxSize(label);
  return {
    "@_id": id,
    "@_value": escapeText(label),
    "@_style": "text;html=1;strokeColor=none;fillColor=#ffffff;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontFamily=Helvetica;fontSize=16;fontColor=#000000;autosize=0;spacing=1;",
    "@_parent": "1",
    "@_vertex": "1",
    mxGeometry: createGeometry(x - size.width / 2, y - size.height / 2, size.width, size.height)
  };
}

function overlaps(a, b, pad = 0) {
  return !(
    a.x + a.width <= b.x - pad ||
    a.x >= b.x + b.width + pad ||
    a.y + a.height <= b.y - pad ||
    a.y >= b.y + b.height + pad
  );
}

function validateNodeNonOverlap(layout, model) {
  const nodes = model.nodes.map((node) => ({ node, box: layout.positions.get(node.id) }));
  for (let left = 0; left < nodes.length; left += 1) {
    for (let right = left + 1; right < nodes.length; right += 1) {
      const a = nodes[left];
      const b = nodes[right];
      if (!a.box || !b.box) {
        throw new Error(`Cannot validate node overlap; missing position for ${!a.box ? a.node.id : b.node.id}.`);
      }
      if (overlaps(a.box, b.box, 0)) {
        throw new Error(`Renderer produced overlapping nodes: ${a.node.id}:${a.node.text} and ${b.node.id}:${b.node.text}.`);
      }
    }
  }
}

function computeTemplateInfo(mxGraphModel, model) {
  const page = {
    width: attrNumber(mxGraphModel, "pageWidth", Number(model.page.width)),
    height: attrNumber(mxGraphModel, "pageHeight", Number(model.page.height))
  };
  const rootCells = asArray(mxGraphModel.root.mxCell);
  let detected = null;
  for (const cell of rootCells) {
    const geometry = cell.mxGeometry;
    if (!geometry) {
      continue;
    }
    const x = attrNumber(geometry, "x");
    const y = attrNumber(geometry, "y");
    const width = attrNumber(geometry, "width");
    const height = attrNumber(geometry, "height");
    if (x > page.width * 0.70 && y > page.height * 0.82 && width > 500 && height > 120) {
      detected = { x, y, width, height };
      break;
    }
  }
  const conservative = model.page.forbidden_area;
  const templateTitleBlock = detected || model.page.template_title_block;
  const forbiddenArea = {
    x: Math.min(Number(conservative.x), templateTitleBlock.x),
    y: Math.min(Number(conservative.y), templateTitleBlock.y),
    width: Math.max(Number(conservative.x) + Number(conservative.width), templateTitleBlock.x + templateTitleBlock.width) -
      Math.min(Number(conservative.x), templateTitleBlock.x),
    height: Math.max(Number(conservative.y) + Number(conservative.height), templateTitleBlock.y + templateTitleBlock.height) -
      Math.min(Number(conservative.y), templateTitleBlock.y)
  };
  return { page, templateTitleBlock, forbiddenArea };
}

function dimensionForType(type, metrics) {
  if (type === "decision") {
    return { width: metrics.decision.width, height: metrics.decision.height };
  }
  if (type === "connector") {
    return { width: metrics.connector.width, height: metrics.connector.height };
  }
  if (type === "stored_data") {
    return { width: metrics.stored.width, height: metrics.stored.height };
  }
  return { width: metrics.rect.width, height: metrics.rect.height };
}

async function runElk(model) {
  const elk = new ELK();
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "RIGHT",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP"
    },
    children: model.nodes.map((node) => ({
      id: node.id,
      width: node.type === "connector" ? 50 : 150,
      height: node.type === "decision" ? 82 : 76
    })),
    edges: model.edges.map((edge) => ({
      id: edge.id,
      sources: [edge.from],
      targets: [edge.to]
    }))
  };
  return elk.layout(graph);
}

function initialPreferredSequence(model) {
  const ids = new Set(model.nodes.map((node) => node.id));
  const ordered = preferredSequence.filter((id) => id === null || ids.has(id));
  const placed = new Set(ordered.filter((id) => id !== null));
  const missing = model.nodes.map((node) => node.id).filter((id) => !placed.has(id));
  return [...ordered, ...missing];
}

function preferredLayoutItems(model) {
  const sequence = initialPreferredSequence(model).filter((id) => id !== null);
  const consumed = new Set();
  const groupByFirst = new Map();
  for (const group of ROW_WRAP_RULES.atomicGroups || []) {
    const present = group.filter((id) => sequence.includes(id));
    if (present.length > 1) {
      groupByFirst.set(present[0], present);
      for (const id of present.slice(1)) {
        consumed.add(id);
      }
    }
  }
  const items = [];
  for (const id of sequence) {
    if (consumed.has(id)) {
      continue;
    }
    items.push(groupByFirst.get(id) || [id]);
  }
  return items;
}

function makeBaseMargins(page) {
  return {
    left: 96,
    top: 70,
    right: 96,
    bottom: 260
  };
}

function makeSizingMetrics() {
  const rectHeight = PROGRAM_SCHEME_LAYOUT_RULES.nodeHeight;
  const rect = { height: rectHeight, width: rectHeight * SHAPE_RULES.process.ratio };
  const decisionHeight = Math.round(rectHeight * 1.22);
  const storedHeight = Math.round(rectHeight * 1.10);
  const connectorHeight = Math.round(rectHeight * 0.72);
  return {
    rect,
    decision: { height: decisionHeight, width: Math.round(decisionHeight * SHAPE_RULES.decision.ratio) },
    stored: { height: storedHeight, width: Math.round(storedHeight * SHAPE_RULES.stored_data.ratio) },
    connector: { height: connectorHeight, width: Math.round(connectorHeight * SHAPE_RULES.connector.ratio) }
  };
}

function orderRows(model, templateInfo) {
  void templateInfo;
  const ids = new Set(model.nodes.map((node) => node.id));
  const rows = PROGRAM_SCHEME_LAYOUT_RULES.rows.map((row) => row.nodes.filter((id) => ids.has(id)));
  const placed = new Set(rows.flat());
  const branchNodes = new Set((PROGRAM_SCHEME_LAYOUT_RULES.branches || []).flatMap((branch) => branch.nodes));
  const floating = new Set(PROGRAM_SCHEME_LAYOUT_RULES.floating || []);
  const missing = model.nodes.map((node) => node.id).filter((id) => !placed.has(id) && !branchNodes.has(id) && !floating.has(id));
  if (missing.length) {
    rows.push(missing);
  }
  if (rows.length > ROW_WRAP_RULES.maxPhysicalRows) {
    throw new Error(`Program-scheme layout produced ${rows.length} rows; maximum is ${ROW_WRAP_RULES.maxPhysicalRows}. Increase page use before wrapping.`);
  }
  return rows;
}

function slotDimensionForNodeId(nodeId, model, metrics) {
  if (nodeId === null) {
    return { width: metrics.rect.width, height: metrics.rect.height };
  }
  const node = model.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) {
    throw new Error(`Unknown layout slot node: ${nodeId}`);
  }
  return dimensionForType(node.type, metrics);
}

function computeDynamicMetrics(model, templateInfo, rows) {
  const page = templateInfo.page;
  const forbiddenArea = templateInfo.forbiddenArea;
  const margin = makeBaseMargins(page);
  const freeWidth = page.width - margin.left - margin.right;
  const freeHeight = forbiddenArea.y - margin.top - margin.bottom;
  const rowCount = rows.length;
  const { rect, decision, stored, connector } = makeSizingMetrics();
  const U = PROGRAM_SCHEME_LAYOUT_RULES.unit;
  const columnPitch = Math.round(standardHorizontalLength());
  const rowGap = clamp(Math.floor((freeHeight - rect.height) / Math.max(1, rowCount - 1)), PROGRAM_SCHEME_LAYOUT_RULES.minLaneGap, PROGRAM_SCHEME_LAYOUT_RULES.maxLaneGap);
  return { page, forbiddenArea, templateTitleBlock: templateInfo.templateTitleBlock, margin, freeWidth, freeHeight, rows, U, rowGap, columnPitch, rect, decision, stored, connector };
}

function computeLayout(model, templateInfo, elkResult) {
  void elkResult;
  const rows = orderRows(model, templateInfo);
  const metrics = computeDynamicMetrics(model, templateInfo, rows);
  const positions = new Map();
  const rowIndex = new Map();
  const colIndex = new Map();
  const rowCenters = rows.map((_, index) => metrics.margin.top + metrics.rect.height / 2 + index * metrics.rowGap);
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));

  for (let r = 0; r < rows.length; r += 1) {
    const row = rows[r];
    const boxes = row.map((nodeId) => {
      const node = nodeById.get(nodeId);
      if (!node) throw new Error(`Missing node listed in layout row: ${nodeId}`);
      return { nodeId, size: dimensionForType(node.type, metrics) };
    });
    const totalWidth = boxes.reduce((sum, item) => sum + item.size.width, 0);
    const gap = row.length > 1 ? metrics.columnPitch : 0;
    const rowWidth = totalWidth + gap * Math.max(0, row.length - 1);
    if (rowWidth > metrics.freeWidth + 0.01) {
      throw new Error(`Program row ${r + 1} cannot fit with fixed global connector length ${gap}.`);
    }
    let cursorX = metrics.margin.left + Math.max(0, (metrics.freeWidth - rowWidth) / 2);
    for (let c = 0; c < row.length; c += 1) {
      const nodeId = row[c];
      if (nodeId === null) {
        continue;
      }
      const node = nodeById.get(nodeId);
      if (!node) {
        throw new Error(`Missing node listed in balanced grid: ${nodeId}`);
      }
      const size = dimensionForType(node.type, metrics);
      const x = cursorX;
      const y = rowCenters[r] - size.height / 2;
      const box = { x, y, width: size.width, height: size.height };
      if (overlaps(box, metrics.forbiddenArea, 18)) {
        throw new Error(`Node ${nodeId} intersects forbidden title block area`);
      }
      if (x < metrics.margin.left - 1 || x + size.width > metrics.page.width - metrics.margin.right + 1) {
        throw new Error(`Node ${nodeId} exceeds page width`);
      }
      if (y + size.height > metrics.forbiddenArea.y - 24) {
        throw new Error(`Node ${nodeId} exceeds free drawing height`);
      }
      positions.set(nodeId, {
        ...box,
        centerX: x + size.width / 2,
        centerY: y + size.height / 2,
        label: fitLabelToShape(node.text, node.type, size.width, size.height)
      });
      rowIndex.set(nodeId, r);
      colIndex.set(nodeId, c);
      cursorX = x + size.width + gap;
    }
  }
  for (const node of model.nodes) {
    if (positions.has(node.id)) {
      continue;
    }
    const size = dimensionForType(node.type, metrics);
    const x = metrics.margin.left;
    const y = metrics.margin.top;
    positions.set(node.id, {
      x,
      y,
      width: size.width,
      height: size.height,
      centerX: x + size.width / 2,
      centerY: y + size.height / 2,
      label: fitLabelToShape(node.text, node.type, size.width, size.height)
    });
    rowIndex.set(node.id, rows.length);
    colIndex.set(node.id, 0);
  }
  const layoutLike = {
    ...metrics,
    positions,
    rowIndex,
    colIndex,
    maxRow: Math.max(...rows.map((row) => row.length)),
    syntheticConnections: []
  };
  placeLocalBranchNodes(model, layoutLike);
  enforceStandardVerticalPlacements(model, layoutLike);
  placeConnectorsBySemantics(model, layoutLike);
  finalizeRuleBasedRows(layoutLike, model);
  return {
    ...metrics,
    positions,
    rows: layoutLike.rows,
    rowIndex: layoutLike.rowIndex,
    colIndex: layoutLike.colIndex,
    maxRow: layoutLike.maxRow,
    syntheticConnections: []
  };
}

function finalizeRuleBasedRows(layoutLike, model) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const rows = (PROGRAM_SCHEME_LAYOUT_RULES.rows || []).map((row) => row.nodes.filter((nodeId) => layoutLike.positions.has(nodeId)));
  const placed = new Set(rows.flat());

  for (const branch of PROGRAM_SCHEME_LAYOUT_RULES.branches || []) {
    const anchorRow = layoutLike.rowIndex.get(branch.anchor);
    const branchNodes = (branch.nodes || []).filter((nodeId) => layoutLike.positions.has(nodeId));
    if (!branchNodes.length) {
      continue;
    }
    const row = Number.isInteger(anchorRow) ? Math.min(rows.length - 1, anchorRow + 1) : rows.length - 1;
    rows[row] = rows[row] || [];
    for (const nodeId of branchNodes) {
      if (!placed.has(nodeId)) {
        rows[row].push(nodeId);
        placed.add(nodeId);
      }
    }
  }

  for (const node of model.nodes) {
    if (!placed.has(node.id) && layoutLike.positions.has(node.id)) {
      const nearestRow = rows.reduce((best, row, index) => {
        const box = layoutLike.positions.get(node.id);
        const rowBoxes = row.map((nodeId) => layoutLike.positions.get(nodeId)).filter(Boolean);
        const centerY = rowBoxes.length
          ? rowBoxes.reduce((sum, item) => sum + item.centerY, 0) / rowBoxes.length
          : box.centerY;
        const delta = Math.abs(centerY - box.centerY);
        return !best || delta < best.delta ? { index, delta } : best;
      }, null)?.index ?? 0;
      rows[nearestRow].push(node.id);
      placed.add(node.id);
    }
  }

  layoutLike.rows = rows.map((row) => row.slice().sort((a, b) => layoutLike.positions.get(a).centerX - layoutLike.positions.get(b).centerX));
  layoutLike.rowIndex = new Map();
  layoutLike.colIndex = new Map();
  layoutLike.rows.forEach((row, rowIndex) => {
    row.forEach((nodeId, colIndex) => {
      if (!nodeById.has(nodeId)) {
        return;
      }
      layoutLike.rowIndex.set(nodeId, rowIndex);
      layoutLike.colIndex.set(nodeId, colIndex);
    });
  });
  layoutLike.maxRow = Math.max(...layoutLike.rows.map((row) => row.length));
}

function mainRuleNodeIds() {
  return new Set((PROGRAM_SCHEME_LAYOUT_RULES.rows || []).flatMap((row) => row.nodes || []));
}

function moveNodeBox(layoutLike, nodeId, centerX, centerY) {
  const box = layoutLike.positions.get(nodeId);
  if (!box) {
    throw new Error(`Cannot anchor missing connector ${nodeId}`);
  }
  box.x = centerX - box.width / 2;
  box.y = centerY - box.height / 2;
  box.centerX = centerX;
  box.centerY = centerY;
  if (overlaps(box, layoutLike.forbiddenArea, 18)) {
    throw new Error(`Anchored connector ${nodeId} intersects forbidden title block area`);
  }
}

function standardHorizontalLength() {
  return LONG_LINE_RULES.globalStandardSegmentLengthPx || ROW_WRAP_RULES.targetColumnGap || 112;
}

function standardVerticalLength() {
  return LONG_LINE_RULES.globalStandardVerticalSegmentLengthPx || CONNECTOR_LOCALITY_RULES.localEdgeClarity?.verticalTargetLengthPx || 88;
}

function edgeGapForSide(layoutLike, side) {
  const clarity = CONNECTOR_LOCALITY_RULES.localEdgeClarity || {};
  if (side === "above" || side === "below") {
    return Math.round(clarity.verticalTargetLengthPx || standardVerticalLength());
  }
  return Math.round(clarity.horizontalTargetLengthPx || clarity.targetLengthPx || standardHorizontalLength());
}

function findNodeIdByText(model, text) {
  const exact = model.nodes.find((node) => node.text === text);
  if (exact) {
    return exact.id;
  }
  const normalized = normalizeText(text);
  return model.nodes.find((node) => normalizeText(node.text) === normalized)?.id || null;
}

function alignVerticalGap(layoutLike, sourceId, targetId, gapPx = standardVerticalLength()) {
  const source = layoutLike.positions.get(sourceId);
  const target = layoutLike.positions.get(targetId);
  if (!source || !target) {
    throw new Error(`Cannot align vertical gap for ${sourceId} -> ${targetId}`);
  }
  const centerY = source.y + source.height + gapPx + target.height / 2;
  moveNodeBox(layoutLike, targetId, target.centerX, centerY);
}

function alignVerticalGapByText(model, layoutLike, sourceText, targetText, gapPx = standardVerticalLength()) {
  const sourceId = findNodeIdByText(model, sourceText);
  const targetId = findNodeIdByText(model, targetText);
  if (!sourceId || !targetId) {
    throw new Error(`Cannot align vertical gap for ${sourceText} -> ${targetText}`);
  }
  alignVerticalGap(layoutLike, sourceId, targetId, gapPx);
  return targetId;
}

function alignNodesToSameCenterY(layoutLike, nodeIds, referenceNodeId) {
  const reference = layoutLike.positions.get(referenceNodeId);
  if (!reference) {
    throw new Error(`Cannot align branch row; missing reference ${referenceNodeId}`);
  }
  for (const nodeId of nodeIds) {
    if (!layoutLike.positions.has(nodeId)) {
      continue;
    }
    const box = layoutLike.positions.get(nodeId);
    moveNodeBox(layoutLike, nodeId, box.centerX, reference.centerY);
  }
}

function enforceStandardVerticalPlacements(model, layoutLike) {
  const verticalGap = standardVerticalLength();
  const faultMergeId = alignVerticalGapByText(model, layoutLike, "Range Check?", "Fault Merge", verticalGap);
  alignNodesToSameCenterY(layoutLike, ["n93", "n15", "n16", "n17", "n47"], faultMergeId);
  alignVerticalGapByText(model, layoutLike, "Schema Check?", "Alarm Store", verticalGap);
  const keepParamsId = alignVerticalGapByText(model, layoutLike, "Approved?", "Keep Current Params", verticalGap);
  alignNodesToSameCenterY(layoutLike, ["n69", "n70", "n71", "n80"], keepParamsId);
}

function placeNodeRelative(layoutLike, nodeId, anchorId, side = "right", gapMultiplier = 0.34, offset = {}) {
  const node = layoutLike.positions.get(nodeId);
  const anchor = layoutLike.positions.get(anchorId);
  if (!node || !anchor) {
    throw new Error(`Cannot place ${nodeId} near ${anchorId}`);
  }
  const gap = Math.round(layoutLike.U * gapMultiplier);
  let centerX = anchor.centerX;
  let centerY = anchor.centerY;
  if (side === "right") {
    centerX = anchor.x + anchor.width + gap + node.width / 2;
  } else if (side === "left") {
    centerX = anchor.x - gap - node.width / 2;
  } else if (side === "below") {
    centerY = anchor.y + anchor.height + gap + node.height / 2;
  } else if (side === "above") {
    centerY = anchor.y - gap - node.height / 2;
  }
  centerX += (offset.xU || 0) * layoutLike.U;
  centerY += (offset.yU || 0) * layoutLike.U;
  moveNodeBox(layoutLike, nodeId, centerX, centerY);
}

function spreadProgramLane(layoutLike, model, nodeIds, centerY, options = {}) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const present = nodeIds.filter((nodeId) => layoutLike.positions.has(nodeId) && nodeById.has(nodeId));
  if (!present.length) {
    return;
  }
  const left = options.left ?? layoutLike.margin.left;
  const right = options.right ?? (layoutLike.page.width - layoutLike.margin.right);
  const widths = present.map((nodeId) => layoutLike.positions.get(nodeId).width);
  const totalWidth = widths.reduce((sum, width) => sum + width, 0);
  const minGap = options.minGap ?? ROW_WRAP_RULES.minColumnGap;
  const maxGap = options.maxGap ?? ROW_WRAP_RULES.maxColumnGap;
  const availableGap = right - left - totalWidth;
  if (present.length > 1 && availableGap < minGap * (present.length - 1)) {
    throw new Error(`Program lane cannot fit without early wrapping: ${present.join(", ")}`);
  }
  const gap = present.length > 1
    ? clamp(availableGap / (present.length - 1), minGap, maxGap)
    : 0;
  let cursorX = left;
  for (const [index, nodeId] of present.entries()) {
    const box = layoutLike.positions.get(nodeId);
    const x = cursorX;
    moveNodeBox(layoutLike, nodeId, x + box.width / 2, centerY);
    cursorX = x + box.width + gap;
    if (index === present.length - 1 && options.alignLastToRight && present.length > 1 && gap < maxGap) {
      const last = layoutLike.positions.get(nodeId);
      moveNodeBox(layoutLike, nodeId, right - last.width / 2, centerY);
    }
  }
}

function spreadMainProgramRows(model, layoutLike) {
  const y = (row) => layoutLike.margin.top + layoutLike.rect.height / 2 + row * layoutLike.rowGap;
  const right = layoutLike.page.width - layoutLike.margin.right;
  spreadProgramLane(layoutLike, model, ["n01", "n02", "n03", "n04", "n05", "n06", "n07", "n08", "n78"], y(0), { right, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n09", "n10", "n11", "n12", "n13", "n99", "n14", "n18", "n19", "n20", "n81"], y(1), { left: 430, right, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n15", "n16", "n17", "n47", "n21", "n22", "n23", "n24", "n25", "n26", "n27", "n28"], y(2), { left: layoutLike.margin.left, right: right - 260, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n30", "n31", "n32", "n33", "n34", "n35", "n36", "n37", "n38", "n40", "n41", "n42"], y(3), { right, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n43", "n44", "n45", "n46", "n48", "n50", "n51", "n52", "n53"], y(4), { right: right - 360, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n54", "n55", "n56", "n57", "n58", "n59", "n60", "n61", "n62", "n63"], y(5), { right, alignLastToRight: true });
  spreadProgramLane(layoutLike, model, ["n64", "n65", "n66", "n67", "n68", "n69", "n70", "n71", "n80"], y(6), { left: 300, right: 2500, alignLastToRight: true });
  placeNodeRelative(layoutLike, "n69", "n65", "below", 0.72, { xU: 0.18 });
  placeNodeRelative(layoutLike, "n70", "n69", "right", 0.58);
  placeNodeRelative(layoutLike, "n71", "n70", "right", 0.58);
  placeNodeRelative(layoutLike, "n80", "n71", "right", 0.58);
  placeNodeRelative(layoutLike, "n99", "n13", "below", 0.44, { xU: -2.62 });
  placeNodeRelative(layoutLike, "n14", "n99", "right", 0.50);
  placeNodeRelative(layoutLike, "n18", "n14", "right", 0.78);
  placeNodeRelative(layoutLike, "n19", "n18", "right", 0.68);
  placeNodeRelative(layoutLike, "n20", "n19", "right", 0.68);
  placeNodeRelative(layoutLike, "n81", "n20", "right", 0.24);
  placeNodeRelative(layoutLike, "n15", "n14", "below", 0.58, { xU: 0.70 });
  placeNodeRelative(layoutLike, "n16", "n15", "right", 0.62);
  placeNodeRelative(layoutLike, "n17", "n16", "right", 0.62);
  placeNodeRelative(layoutLike, "n47", "n17", "right", 1.70);
  spreadProgramLane(
    layoutLike,
    model,
    ["n21", "n22", "n23", "n24", "n25", "n26", "n27", "n28"],
    layoutLike.positions.get("n15").centerY + layoutLike.U * 1.55,
    { left: layoutLike.margin.left, right: right - 360, alignLastToRight: true }
  );
  moveNodeBox(layoutLike, "n39", layoutLike.positions.get("n33").centerX, y(3) + layoutLike.rowGap * 0.55);
  moveNodeBox(layoutLike, "n49", layoutLike.positions.get("n51").centerX, layoutLike.positions.get("n51").centerY - layoutLike.U * 1.48);
}

function refreshLayoutRowsFromPositions(layoutLike, model) {
  const tolerance = layoutLike.U * ROW_WRAP_RULES.finalRowClusterToleranceU;
  const rows = [];
  for (const node of model.nodes) {
    const box = layoutLike.positions.get(node.id);
    if (!box) {
      continue;
    }
    let best = null;
    for (const row of rows) {
      const delta = Math.abs(row.centerY - box.centerY);
      if (delta <= tolerance && (!best || delta < best.delta)) {
        best = { row, delta };
      }
    }
    if (!best) {
      rows.push({ centerY: box.centerY, nodes: [node.id] });
    } else {
      best.row.nodes.push(node.id);
      best.row.centerY = best.row.nodes.reduce((sum, nodeId) => sum + layoutLike.positions.get(nodeId).centerY, 0) / best.row.nodes.length;
    }
  }
  rows.sort((a, b) => a.centerY - b.centerY);
  const rowIds = rows.map((row) => row.nodes.sort((a, b) => layoutLike.positions.get(a).centerX - layoutLike.positions.get(b).centerX));
  layoutLike.rows = rowIds;
  layoutLike.rowIndex = new Map();
  layoutLike.colIndex = new Map();
  rowIds.forEach((row, rowIndex) => {
    row.forEach((nodeId, colIndex) => {
      layoutLike.rowIndex.set(nodeId, rowIndex);
      layoutLike.colIndex.set(nodeId, colIndex);
    });
  });
  layoutLike.maxRow = Math.max(...rowIds.map((row) => row.length));
}

function anchorConnectorNearNode(layoutLike, connectorId, anchorId, side = "right", distance = null, offset = {}) {
  const connector = layoutLike.positions.get(connectorId);
  const anchor = layoutLike.positions.get(anchorId);
  if (!connector || !anchor) {
    throw new Error(`Cannot anchor ${connectorId} near ${anchorId}`);
  }
  const gap = distance ?? Math.round(layoutLike.U * 0.46);
  let centerX = anchor.centerX;
  let centerY = anchor.centerY;
  if (side === "right") {
    centerX = anchor.x + anchor.width + gap + connector.width / 2;
  } else if (side === "left") {
    centerX = anchor.x - gap - connector.width / 2;
  } else if (side === "below") {
    centerY = anchor.y + anchor.height + gap + connector.height / 2;
  } else if (side === "above") {
    centerY = anchor.y - gap - connector.height / 2;
  }
  centerX += (offset.xU || 0) * layoutLike.U;
  centerY += (offset.yU || 0) * layoutLike.U;
  moveNodeBox(layoutLike, connectorId, centerX, centerY);
}

function placeConnectorsBySemantics(model, layoutLike) {
  const nodesByText = new Map();
  const nodesByExactText = new Map();
  for (const node of model.nodes) {
    const key = normalizeText(node.text);
    const list = nodesByText.get(key) || [];
    list.push(node.id);
    nodesByText.set(key, list);
    const exactList = nodesByExactText.get(node.text) || [];
    exactList.push(node.id);
    nodesByExactText.set(node.text, exactList);
  }
  const connectorGroups = new Map();
  for (const node of model.nodes.filter((candidate) => candidate.type === "connector")) {
    const list = connectorGroups.get(node.text) || [];
    list.push(node.id);
    connectorGroups.set(node.text, list);
  }
  for (const [connectorLabel, anchors] of Object.entries(CONNECTOR_LOCALITY_RULES.semanticAnchors)) {
    const connectorIds = connectorGroups.get(connectorLabel) || [];
    if (connectorIds.length !== 2) {
      throw new Error(`Connector ${connectorLabel} must appear exactly twice for semantic placement.`);
    }
    const sourceAnchor = anchors.find((anchor) => anchor.role === "source");
    const targetAnchor = anchors.find((anchor) => anchor.role === "target");
    const sourceIds = nodesByExactText.get(sourceAnchor.near) || nodesByText.get(normalizeText(sourceAnchor.near)) || [];
    const targetIds = nodesByExactText.get(targetAnchor.near) || nodesByText.get(normalizeText(targetAnchor.near)) || [];
    if (!sourceIds.length || !targetIds.length) {
      throw new Error(`Cannot place connector ${connectorLabel}; anchor nodes are missing.`);
    }
    const sourceGap = sourceAnchor.gapPx == null
      ? edgeGapForSide(layoutLike, sourceAnchor.side || "right")
      : Math.round(sourceAnchor.gapPx);
    const targetGap = targetAnchor.gapPx == null
      ? edgeGapForSide(layoutLike, targetAnchor.side || "left")
      : Math.round(targetAnchor.gapPx);
    anchorConnectorNearNode(layoutLike, connectorIds[0], sourceIds[0], sourceAnchor.side || "right", sourceGap, {
      xU: sourceAnchor.offsetXU || 0,
      yU: sourceAnchor.offsetYU || 0
    });
    anchorConnectorNearNode(layoutLike, connectorIds[1], targetIds[0], targetAnchor.side || "left", targetGap, {
      xU: targetAnchor.offsetXU || 0,
      yU: targetAnchor.offsetYU || 0
    });
  }
  const layoutRows = layoutLike.rows || PROGRAM_SCHEME_LAYOUT_RULES.rows || [];
  layoutLike.rowIndex = new Map();
  layoutLike.colIndex = new Map();
  for (let row = 0; row < layoutRows.length; row += 1) {
    const nodes = Array.isArray(layoutRows[row]) ? layoutRows[row] : layoutRows[row].nodes || [];
    for (let col = 0; col < nodes.length; col += 1) {
      const nodeId = nodes[col];
      if (layoutLike.positions.has(nodeId)) {
        layoutLike.rowIndex.set(nodeId, row);
        layoutLike.colIndex.set(nodeId, col);
      }
    }
  }
}

function placeLocalBranchNodes(model, layoutLike) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  for (const branch of PROGRAM_SCHEME_LAYOUT_RULES.branches || []) {
    const anchor = layoutLike.positions.get(branch.anchor);
    if (!anchor) {
      throw new Error(`Cannot place branch; missing anchor ${branch.anchor}.`);
    }
    const present = (branch.nodes || []).filter((nodeId) => layoutLike.positions.has(nodeId) && nodeById.has(nodeId));
    if (!present.length) {
      continue;
    }
    const widths = present.map((nodeId) => layoutLike.positions.get(nodeId).width);
    const gap = layoutLike.U * (branch.gapU || 0.42);
    const totalWidth = widths.reduce((sum, width) => sum + width, 0) + gap * Math.max(0, present.length - 1);
    let left = branch.alignFirstUnderAnchor
      ? anchor.centerX - widths[0] / 2
      : anchor.centerX - totalWidth / 2;
    left += (branch.xOffsetU || 0) * layoutLike.U;
    left = clamp(left, layoutLike.margin.left, layoutLike.page.width - layoutLike.margin.right - totalWidth);
    const centerY = anchor.y + anchor.height + layoutLike.U * (branch.yOffsetU || 1.0);
    let cursor = left;
    for (const nodeId of present) {
      const box = layoutLike.positions.get(nodeId);
      moveNodeBox(layoutLike, nodeId, cursor + box.width / 2, centerY);
      cursor += box.width + gap;
    }
  }
}

function resetPlacedLabelState(layoutLike) {
  layoutLike.placedLabelBoxes = [];
}

function purgeExisting(root) {
  root.mxCell = asArray(root.mxCell).filter((cell) => {
    const id = String(cell["@_id"] || "");
    return !id.startsWith(ID_PREFIX) && !id.startsWith(FRAME_PREFIX);
  });
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
  if (!replaced) {
    updated.push(`${key}=${value}`);
  }
  return updated.join(";");
}

function normalizeTitleBlockStrokeWidths(root) {
  const thick = FRAME_RULES.titleBlock.thickStrokeWidth;
  const thin = FRAME_RULES.titleBlock.thinStrokeWidth;
  for (const cell of asArray(root.mxCell)) {
    const parent = String(cell["@_parent"] || "");
    const id = String(cell["@_id"] || "");
    if (parent !== FRAME_RULES.titleBlock.id && id !== FRAME_RULES.titleBlock.id) {
      continue;
    }
    const style = String(cell["@_style"] || "");
    if (!/strokeWidth=/.test(style)) {
      continue;
    }
    const current = Number((style.match(/strokeWidth=([0-9.]+)/) || [])[1]);
    if (!Number.isFinite(current)) {
      continue;
    }
    const normalized = current >= (thick + thin) / 2 ? thick : thin;
    cell["@_style"] = replaceStyleValue(style, "strokeWidth", normalized);
  }
}

function alignTitleBlockToFrame(root, page) {
  const frame = frameBoxForPage(page);
  const titleCell = asArray(root.mxCell).find((cell) => String(cell["@_id"] || "") === FRAME_RULES.titleBlock.id);
  if (!titleCell?.mxGeometry) {
    return;
  }
  const g = titleCell.mxGeometry;
  const width = attrNumber(g, "width");
  const height = attrNumber(g, "height");
  g["@_x"] = Number((frame.x + frame.width - width).toFixed(3));
  g["@_y"] = Number((frame.y + frame.height - height).toFixed(3));
}

function applyFrameRules(root, page) {
  alignTitleBlockToFrame(root, page);
  normalizeTitleBlockStrokeWidths(root);
  root.mxCell = asArray(root.mxCell).concat([createOuterFrameCell(page)]);
}

function validateModel(model) {
  if (model.nodes.length !== model.diagram.target_element_count) {
    throw new Error(`Model node count ${model.nodes.length} does not equal target ${model.diagram.target_element_count}`);
  }
  const ids = new Set();
  for (const node of model.nodes) {
    if (ids.has(node.id)) {
      throw new Error(`Duplicate node id ${node.id}`);
    }
    ids.add(node.id);
    if (containsChinese(node.text)) {
      throw new Error(`Non-English label detected in ${node.id}`);
    }
    fitLabelToShape(node.text, node.type, 170, 84);
  }
  for (const edge of model.edges) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) {
      throw new Error(`Edge ${edge.id} references a missing node`);
    }
    if (containsChinese(edge.label || "")) {
      throw new Error(`Non-English edge label detected in ${edge.id}`);
    }
  }
}

function portPoint(box, port) {
  if (port === "right") {
    return { x: box.x + box.width, y: box.centerY };
  }
  if (port === "left") {
    return { x: box.x, y: box.centerY };
  }
  if (port === "bottom") {
    return { x: box.centerX, y: box.y + box.height };
  }
  if (port === "top") {
    return { x: box.centerX, y: box.y };
  }
  throw new Error(`Unknown port: ${port}`);
}

function relativeXForAbsolute(box, x) {
  return clamp((x - box.x) / box.width, 0, 1);
}

function relativeYForAbsolute(box, y) {
  return clamp((y - box.y) / box.height, 0, 1);
}

function compactCollinear(points) {
  const cleaned = [];
  for (const point of points) {
    const last = cleaned[cleaned.length - 1];
    if (!last || Math.abs(last.x - point.x) > 0.1 || Math.abs(last.y - point.y) > 0.1) {
      cleaned.push(point);
    }
  }
  return cleaned.filter((point, index, list) => {
    if (index === 0 || index === list.length - 1) {
      return true;
    }
    const prev = list[index - 1];
    const next = list[index + 1];
    const sameVertical = Math.abs(prev.x - point.x) <= 0.1 && Math.abs(point.x - next.x) <= 0.1;
    const sameHorizontal = Math.abs(prev.y - point.y) <= 0.1 && Math.abs(point.y - next.y) <= 0.1;
    return !(sameVertical || sameHorizontal);
  });
}

function splitOrthogonalSegments(points, targetLength) {
  if (!points.length) {
    return points;
  }
  const result = [points[0]];
  for (let index = 1; index < points.length; index += 1) {
    const prev = result[result.length - 1];
    const next = points[index];
    const dx = next.x - prev.x;
    const dy = next.y - prev.y;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    const length = Math.max(absDx, absDy);
    if ((absDx > 0.1 && absDy > 0.1) || length <= targetLength * 1.45) {
      result.push(next);
      continue;
    }
    const segmentCount = Math.ceil(length / targetLength);
    for (let step = 1; step < segmentCount; step += 1) {
      result.push({
        x: prev.x + (dx * step) / segmentCount,
        y: prev.y + (dy * step) / segmentCount
      });
    }
    result.push(next);
  }
  return result;
}

function finalizeRoute(route, layout) {
  if (!route) {
    return null;
  }
  const points = route.preserveSegments
    ? compactCollinear(route.points || [])
    : splitOrthogonalSegments(route.points || [], layout.U);
  return {
    ...route,
    points,
    waypoints: points.slice(1, -1)
  };
}

function routeSummary(route, edgeId = "unknown") {
  const points = route?.points || [];
  const segments = [];
  let bends = 0;
  let previousDirection = null;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const dx = curr.x - prev.x;
    const dy = curr.y - prev.y;
    const absDx = Math.abs(dx);
    const absDy = Math.abs(dy);
    if (absDx > 0.1 && absDy > 0.1) {
      throw new Error(`Edge ${edgeId} has diagonal route segment between (${prev.x}, ${prev.y}) and (${curr.x}, ${curr.y}).`);
    }
    const direction = absDx > absDy ? "h" : "v";
    const length = Math.max(absDx, absDy);
    segments.push({ direction, length, dx: absDx, dy: absDy });
    if (previousDirection && direction !== previousDirection) {
      bends += 1;
    }
    previousDirection = direction;
  }
  return { points, segments, bends };
}

function mergedOrthogonalSegments(points) {
  const merged = [];
  let current = null;
  const flush = () => {
    if (current) {
      merged.push(current);
      current = null;
    }
  };
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const horizontal = Math.abs(a.y - b.y) <= 0.1;
    const vertical = Math.abs(a.x - b.x) <= 0.1;
    if (!horizontal && !vertical) {
      flush();
      continue;
    }
    const direction = horizontal ? "h" : "v";
    const axis = horizontal ? a.y : a.x;
    const min = horizontal ? Math.min(a.x, b.x) : Math.min(a.y, b.y);
    const max = horizontal ? Math.max(a.x, b.x) : Math.max(a.y, b.y);
    if (current && current.direction === direction && Math.abs(current.axis - axis) <= 0.1 && Math.abs(current.max - min) <= 0.1) {
      current.max = max;
      current.length = current.max - current.min;
    } else {
      flush();
      current = { direction, axis, min, max, length: max - min };
    }
  }
  flush();
  return merged;
}

function routeWithinEnvelope(route, source, target, layout) {
  const margin = layout.U * ROUTING_ENVELOPE_RULES.marginU;
  const minX = Math.min(source.x, target.x) - margin;
  const minY = Math.min(source.y, target.y) - margin;
  const maxX = Math.max(source.x + source.width, target.x + target.width) + margin;
  const maxY = Math.max(source.y + source.height, target.y + target.height) + margin;
  return route.points.every((point) => point.x >= minX - 0.01 && point.x <= maxX + 0.01 && point.y >= minY - 0.01 && point.y <= maxY + 0.01);
}

function validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout) {
  const summary = routeSummary(route, edge.id);
  const label = String(edge.label || "").trim();
  const isDecisionBranch = sourceNode.type === "decision" && Boolean(label);
  const isAbnormalDecisionBranch = isDecisionBranch && ABNORMAL_BRANCH_LABELS.has(label);
  const isReturnEdge = edge.channel === "return" || edge.channel === "feedback" || edge.channel === "loop";
  const isProgramContinuation = ["continuation", "row_continuation", "parameter", "downlink", "alarm", "telemetry"].includes(String(edge.channel || ""));
  const sourceRow = layout.rowIndex.get(edge.from);
  const targetRow = layout.rowIndex.get(edge.to);
  const sourceCol = layout.colIndex.get(edge.from);
  const targetCol = layout.colIndex.get(edge.to);
  const sameMainRowAdjacent = sourceRow === targetRow && targetCol === sourceCol + 1 && mainRuleNodeIds().has(edge.from) && mainRuleNodeIds().has(edge.to);
  const requiredStraight = (PROGRAM_SCHEME_LAYOUT_RULES.requiredStraightEdges || []).some(([from, to]) => {
    const sourceText = normalizeText(sourceNode.text);
    const targetText = normalizeText(targetNode.text);
    return normalizeText(from) === sourceText && normalizeText(to) === targetText;
  });
  const maxBends = isReturnEdge
    ? LONG_LINE_RULES.maxReturnBends
    : isAbnormalDecisionBranch
      ? LONG_LINE_RULES.maxDecisionAbnormalBends
      : LONG_LINE_RULES.maxBends;
  if (summary.bends > maxBends) {
    throw new Error(`Edge ${edge.id} has ${summary.bends} bend(s), exceeding the maximum of ${maxBends}.`);
  }
  if ((sameMainRowAdjacent || requiredStraight) && LONG_LINE_RULES.forbidSameRowDoglegs && summary.bends !== 0) {
    throw new Error(`Edge ${edge.id} must be a direct horizontal link with no bends.`);
  }
  if (sameMainRowAdjacent || requiredStraight) {
    const first = summary.points[0];
    const last = summary.points[summary.points.length - 1];
    if (summary.points.length !== 2 || Math.abs(first.y - last.y) > 0.1 || first.x >= last.x) {
      throw new Error(`Edge ${edge.id} must be a left-to-right straight horizontal connection.`);
    }
  }
  const maxSegmentLength = layout.U * (isReturnEdge
    ? LONG_LINE_RULES.maxReturnSegmentU
    : edge.id === "e14_merge_safety"
      ? LONG_LINE_RULES.maxControlMergeSegmentU
    : isDecisionBranch
      ? LONG_LINE_RULES.maxDecisionSegmentU
      : isProgramContinuation
        ? Math.max(LONG_LINE_RULES.maxStandardAdjacentSegmentU, LONG_LINE_RULES.maxSegmentLengthU)
      : LONG_LINE_RULES.maxSegmentLengthU);
  for (const segment of summary.segments) {
    if (segment.length > maxSegmentLength + 0.01) {
      throw new Error(`Edge ${edge.id} contains a segment of length ${segment.length.toFixed(3)}, exceeding ${maxSegmentLength.toFixed(3)}.`);
    }
  }
  for (const segment of mergedOrthogonalSegments(summary.points)) {
    if (segment.length > maxSegmentLength + 0.01) {
      throw new Error(`Edge ${edge.id} contains a merged straight segment of length ${segment.length.toFixed(3)}, exceeding ${maxSegmentLength.toFixed(3)}.`);
    }
  }
  const routeHasAnyBend = summary.bends > 0;
  const verticalStandard = standardVerticalLength();
  const verticalTolerance = layout.U * (LONG_LINE_RULES.verticalSegmentLengthToleranceU || LONG_LINE_RULES.standardSegmentLengthToleranceU || 0.08);
  const requiresFixedVerticalSegment = summary.segments.some((segment) => segment.direction === "v") && (
    sourceNode.type === "connector" ||
    targetNode.type === "connector" ||
    (isDecisionBranch && isAbnormalDecisionBranch && !routeHasAnyBend)
  );
  if (requiresFixedVerticalSegment) {
    for (const segment of summary.segments.filter((candidate) => candidate.direction === "v")) {
      if (Math.abs(segment.length - verticalStandard) > verticalTolerance + 0.01) {
        throw new Error(`Edge ${edge.id} vertical segment length ${segment.length.toFixed(1)} must match global vertical standard ${verticalStandard.toFixed(1)} +/- ${verticalTolerance.toFixed(1)}.`);
      }
    }
  }
  if (!route.relaxedEnvelope && !routeWithinEnvelope(route, source, target, layout)) {
    throw new Error(`Edge ${edge.id} escapes the local routing envelope.`);
  }
  if (sourceNode.type !== "connector" && targetNode.type !== "connector" && !isAbnormalDecisionBranch && !isReturnEdge) {
    const routeBox = {
      minY: Math.min(...summary.points.map((point) => point.y)),
      maxY: Math.max(...summary.points.map((point) => point.y))
    };
    if (routeBox.maxY - routeBox.minY > layout.rowGap * LONG_LINE_RULES.maxEdgeRowGapsSpanned + 0.01) {
      throw new Error(`Edge ${edge.id} crosses more than one row without a connector.`);
    }
  }
}

function orthogonalDogleg(source, target, sourcePort, targetPort, layout) {
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  const midY = (start.y + end.y) / 2;
  const dx = end.x - start.x;
  const absDx = Math.abs(dx);
  if (sourcePort === "bottom" && targetPort === "top" && absDx > 0.1 && absDx < layout.U * 0.40) {
    const dir = dx >= 0 ? 1 : -1;
    const bypassX = end.x + dir * layout.U * 0.85;
    const points = compactCollinear([
      start,
      { x: start.x, y: midY },
      { x: bypassX, y: midY },
      { x: bypassX, y: end.y },
      end
    ]);
    return {
      kind: "bottom-top-center-port-bypass",
      sourcePort,
      targetPort,
      waypoints: points.slice(1, -1),
      points
    };
  }
  const waypoints = [{ x: start.x, y: midY }];
  if (absDx > 0.1) {
    const segmentCount = Math.max(1, Math.ceil(absDx / (layout.U * 1.05)));
    for (let index = 1; index < segmentCount; index += 1) {
      waypoints.push({
        x: start.x + (dx * index) / segmentCount,
        y: midY
      });
    }
    waypoints.push({ x: end.x, y: midY });
  }
  return {
    kind: "dogleg",
    sourcePort,
    targetPort,
    waypoints,
    points: [start, ...waypoints, end]
  };
}

function routeRightToLeft(source, target) {
  const start = portPoint(source, "right");
  const end = portPoint(target, "left");
  if (Math.abs(start.y - end.y) <= 0.1 && start.x < end.x) {
    return {
      kind: "right-left-direct",
      sourcePort: "right",
      targetPort: "left",
      waypoints: [],
      points: [start, end]
    };
  }
  const midX = start.x < end.x ? (start.x + end.x) / 2 : Math.max(start.x + 26, target.x - 44);
  const points = compactCollinear([start, { x: midX, y: start.y }, { x: midX, y: end.y }, end]);
  return {
    kind: "right-left-dogleg",
    sourcePort: "right",
    targetPort: "left",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeBottomToTop(source, target, layout) {
  const start = portPoint(source, "bottom");
  const end = portPoint(target, "top");
  if (Math.abs(start.x - end.x) <= 0.1 && start.y < end.y) {
    return {
      kind: "bottom-top-direct",
      sourcePort: "bottom",
      targetPort: "top",
      waypoints: [],
      points: [start, end]
    };
  }
  const downward = target.y > source.y;
  const laneY = downward
    ? Math.max(start.y + layout.U * 0.45, Math.min(end.y - layout.U * 0.55, start.y + layout.U * 1.15))
    : Math.max(source.y + source.height + layout.U * 0.45, source.y + source.height + 42);
  const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "bottom-top-dogleg",
    sourcePort: "bottom",
    targetPort: "top",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeBottomToLeft(source, target, layout) {
  const start = portPoint(source, "bottom");
  const end = portPoint(target, "left");
  const laneY = Math.min(
    source.y + source.height + layout.U * 0.72,
    Math.max(source.y + source.height + 42, end.y)
  );
  const leftLaneX = Math.min(target.x - layout.U * 0.35, source.x + source.width + layout.U * 0.5);
  const points = compactCollinear([
    start,
    { x: start.x, y: laneY },
    { x: leftLaneX, y: laneY },
    { x: leftLaneX, y: end.y },
    end
  ]);
  return {
    kind: "bottom-left-dogleg",
    sourcePort: "bottom",
    targetPort: "left",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeTopToBottom(source, target, layout) {
  const start = portPoint(source, "top");
  const end = portPoint(target, "bottom");
  const laneY = Math.min(start.y - layout.U * 0.45, end.y + layout.U * 0.55);
  const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "top-bottom-dogleg",
    sourcePort: "top",
    targetPort: "bottom",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeTopToTop(source, target, layout) {
  const start = portPoint(source, "top");
  const end = portPoint(target, "top");
  const laneY = Math.min(source.y, target.y) - layout.U * 0.50;
  const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "top-top-overpass",
    sourcePort: "top",
    targetPort: "top",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeRightToBottom(source, target, layout) {
  const start = portPoint(source, "right");
  const end = portPoint(target, "bottom");
  const laneX = Math.min(start.x + layout.U * 0.70, Math.max(start.x + 34, end.x));
  const laneY = Math.max(end.y + layout.U * 0.55, target.y + target.height + 42);
  const points = compactCollinear([start, { x: laneX, y: start.y }, { x: laneX, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "right-bottom-local-return",
    sourcePort: "right",
    targetPort: "bottom",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeLeftToRight(source, target) {
  const start = portPoint(source, "left");
  const end = portPoint(target, "right");
  if (Math.abs(start.y - end.y) <= 0.1 && start.x > end.x) {
    return {
      kind: "left-right-direct",
      sourcePort: "left",
      targetPort: "right",
      waypoints: [],
      points: [start, end]
    };
  }
  const midX = start.x > end.x ? (start.x + end.x) / 2 : Math.min(start.x - 26, target.x + target.width + 44);
  const points = compactCollinear([start, { x: midX, y: start.y }, { x: midX, y: end.y }, end]);
  return {
    kind: "left-right-dogleg",
    sourcePort: "left",
    targetPort: "right",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeLeftToLeft(source, target, layout) {
  const start = portPoint(source, "left");
  const end = portPoint(target, "left");
  const laneX = Math.min(source.x, target.x) - layout.U * 0.42;
  const points = compactCollinear([start, { x: laneX, y: start.y }, { x: laneX, y: end.y }, end]);
  return {
    kind: "left-left-local-return",
    sourcePort: "left",
    targetPort: "left",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeBottomToBottom(source, target, layout) {
  const start = portPoint(source, "bottom");
  const end = portPoint(target, "bottom");
  const laneY = Math.max(source.y + source.height, target.y + target.height) + layout.U * 0.48;
  const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "bottom-bottom-clean-branch",
    sourcePort: "bottom",
    targetPort: "bottom",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeTopToLeft(source, target, layout) {
  const start = portPoint(source, "top");
  const end = portPoint(target, "left");
  const laneY = Math.min(source.y, target.y) - layout.U * 0.38;
  const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
  return {
    kind: "top-left-local-branch",
    sourcePort: "top",
    targetPort: "left",
    waypoints: points.slice(1, -1),
    points
  };
}

function routeLocalConnectorEdge(source, target, layout) {
  const dx = target.centerX - source.centerX;
  const dy = target.centerY - source.centerY;
  if (Math.abs(dx) > 0.1 && Math.abs(dy) > 0.1) {
    const startPort = dx >= 0 ? "right" : "left";
    const endPort = dy >= 0 ? "top" : "bottom";
    const start = portPoint(source, startPort);
    const end = portPoint(target, endPort);
    const points = compactCollinear([start, { x: end.x, y: start.y }, end]);
    return {
      kind: "connector-single-bend",
      sourcePort: startPort,
      targetPort: endPort,
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0 ? routeRightToLeft(source, target, layout) : routeLeftToRight(source, target, layout);
  }
  return dy >= 0 ? routeBottomToTop(source, target, layout) : routeTopToBottom(source, target, layout);
}

function boxForLabelCenter(center, value = "") {
  const size = labelBoxSize(value);
  return { x: center.x - size.width / 2, y: center.y - size.height / 2, width: size.width, height: size.height };
}

function segmentBox(a, b, pad = 3) {
  const vertical = Math.abs(a.x - b.x) <= 0.1;
  const horizontal = Math.abs(a.y - b.y) <= 0.1;
  return {
    x: Math.min(a.x, b.x) - (vertical ? pad : 0),
    y: Math.min(a.y, b.y) - (horizontal ? pad : 0),
    width: Math.max(1, Math.abs(a.x - b.x)) + (vertical ? pad * 2 : 0),
    height: Math.max(1, Math.abs(a.y - b.y)) + (horizontal ? pad * 2 : 0)
  };
}

function labelSafetyIssue(center, layout, value = "") {
  const labelBox = boxForLabelCenter(center, value);
  if (overlaps(labelBox, layout.forbiddenArea, 0)) {
    return "forbidden title-block area";
  }
  for (const [nodeId, box] of layout.positions.entries()) {
    if (overlaps(labelBox, box, 3)) {
      return `node ${nodeId}`;
    }
  }
  for (const [index, box] of (layout.placedLabelBoxes || []).entries()) {
    if (overlaps(labelBox, box, 4)) {
      return `branch label ${index + 1}`;
    }
  }
  for (const [routeIndex, route] of (layout.edgeRoutes || []).entries()) {
    const points = route.points || [];
    for (let index = 1; index < points.length; index += 1) {
      if (overlaps(labelBox, segmentBox(points[index - 1], points[index], 4), 0)) {
        return `edge route ${routeIndex + 1}`;
      }
    }
  }
  return "";
}

function labelIsSafe(center, layout, value = "") {
  return !labelSafetyIssue(center, layout, value);
}

function branchOrientationForLabel(label) {
  if (NORMAL_BRANCH_LABELS.has(label)) {
    return "horizontal";
  }
  if (ABNORMAL_BRANCH_LABELS.has(label)) {
    return "verticalDown";
  }
  return null;
}

function findBranchLabelSegment(edge, route, orientation, layout = null) {
  const points = route.points || [];
  const sourceBox = layout?.positions?.get(edge.from);
  const targetBox = layout?.positions?.get(edge.to);
  const outsideEndpointNodes = (a, b) => {
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const inSource = sourceBox && mid.x >= sourceBox.x - 2 && mid.x <= sourceBox.x + sourceBox.width + 2 && mid.y >= sourceBox.y - 2 && mid.y <= sourceBox.y + sourceBox.height + 2;
    const inTarget = targetBox && mid.x >= targetBox.x - 2 && mid.x <= targetBox.x + targetBox.width + 2 && mid.y >= targetBox.y - 2 && mid.y <= targetBox.y + targetBox.height + 2;
    return !inSource && !inTarget;
  };
  if (orientation === "horizontal" || orientation === "horizontalLeft") {
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      if (Math.abs(a.y - b.y) <= 0.1 && Math.abs(a.x - b.x) > 0.1) {
        if (orientation === "horizontal" && b.x >= a.x && outsideEndpointNodes(a, b)) {
          return { a, b, orientation };
        }
        if (orientation === "horizontalLeft" && b.x <= a.x && outsideEndpointNodes(a, b)) {
          return { a, b, orientation };
        }
      }
    }
  }
  if (orientation === "verticalDown" || orientation === "verticalUp") {
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      if (Math.abs(a.x - b.x) <= 0.1 && Math.abs(a.y - b.y) > 0.1) {
        if (orientation === "verticalDown" && b.y >= a.y && outsideEndpointNodes(a, b)) {
          return { a, b, orientation };
        }
        if (orientation === "verticalUp" && b.y <= a.y && outsideEndpointNodes(a, b)) {
          return { a, b, orientation };
        }
      }
    }
  }
  throw new Error(`No ${orientation} branch label segment found for edge ${edge.id} (${edge.label})`);
}

function labelGapForRule(rule, labelSize) {
  return clamp(Math.max(rule.minGap, 8), rule.minGap, rule.maxGap) + labelSize / 2;
}

function candidateForLabelSegment(segment, rule, value, delta = 0) {
  const { width: labelWidth, height: labelHeight } = labelBoxSize(value);
  const midX = (segment.a.x + segment.b.x) / 2;
  const midY = (segment.a.y + segment.b.y) / 2;
  if (rule.position === "above-center") {
    return {
      x: midX + delta,
      y: segment.a.y - labelGapForRule(rule, labelHeight)
    };
  }
  if (rule.position === "right-middle") {
    return {
      x: segment.a.x + labelGapForRule(rule, labelWidth),
      y: midY + delta
    };
  }
  throw new Error(`Unsupported label placement rule: ${rule.position}`);
}

function labelSatisfiesPlacement(center, segment, rule, value = "") {
  const labelBox = boxForLabelCenter(center, value);
  const midX = (segment.a.x + segment.b.x) / 2;
  const midY = (segment.a.y + segment.b.y) / 2;
  if (rule.position === "above-center") {
    const gap = segment.a.y - (labelBox.y + labelBox.height);
    return Math.abs(center.x - midX) <= 4 && gap >= rule.minGap && gap <= rule.maxGap;
  }
  if (rule.position === "right-middle") {
    const gap = labelBox.x - segment.a.x;
    return Math.abs(center.y - midY) <= 4 && gap >= rule.minGap && gap <= rule.maxGap;
  }
  return false;
}

function chooseSafeBranchLabelPosition(edge, route, layout) {
  const orientation = branchOrientationForLabel(String(edge.label || ""));
  if (!orientation) {
    return null;
  }
  const segment = findBranchLabelSegment(edge, route, orientation, layout);
  const rule = LABEL_RULES[orientation];
  const localDeltas = [0, -4, 4, -8, 8, -12, 12];
  const issues = [];
  for (const delta of localDeltas) {
    const candidate = candidateForLabelSegment(segment, rule, edge.label, delta);
    const placementOk = labelSatisfiesPlacement(candidate, segment, rule, edge.label);
    const safetyIssue = labelSafetyIssue(candidate, layout, edge.label);
    if (placementOk && !safetyIssue) {
      return candidate;
    }
    issues.push(`delta ${delta}: ${placementOk ? "placement ok" : "placement invalid"}, ${safetyIssue || "safe"}`);
  }
  throw new Error(`No standards-compliant branch label position found for edge ${edge.id} (${edge.label}); reroute the branch instead of moving the label away. Tried ${issues.join("; ")}.`);
}

function labelPositionForRoute(edge, route, layout) {
  if (!edge.label || !route?.points?.length) {
    return null;
  }
  const label = String(edge.label || "");
  if (NORMAL_BRANCH_LABELS.has(label) || ABNORMAL_BRANCH_LABELS.has(label)) {
    return chooseSafeBranchLabelPosition(edge, route, layout);
  }
  return null;
}

function decisionBranchRoute(edge, source, target, layout) {
  const label = String(edge.label || "");
  const sourceRow = layout.rowIndex.get(edge.from);
  const targetRow = layout.rowIndex.get(edge.to);
  if (NORMAL_BRANCH_LABELS.has(label)) {
    return routeRightToLeft(source, target, layout);
  }
  if (ABNORMAL_BRANCH_LABELS.has(label)) {
    return targetRow > sourceRow ? routeBottomToTop(source, target, layout) : routeBottomToLeft(source, target, layout);
  }
  return routeRightToLeft(source, target, layout);
}

function routeProgramSchemeOverride(edge, sourceNode, targetNode, source, target, layout) {
  const route = (base) => ({
    ...base,
    preserveSegments: true,
    relaxedEnvelope: true
  });
  if (edge.id === "e11_no") {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "top");
    const points = compactCollinear(Math.abs(start.x - end.x) <= 1
      ? [start, end]
      : [start, { x: end.x, y: start.y }, end]);
    return route({
      kind: "param-no-local-drop",
      sourcePort: "bottom",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    });
  }
  if (edge.id === "e14_ack_safety") {
    const start = portPoint(source, "right");
    const end = portPoint(target, "left");
    const points = compactCollinear([start, end]);
    return route({
      kind: "ack-to-safety-merge-direct",
      sourcePort: "right",
      targetPort: "left",
      waypoints: points.slice(1, -1),
      points
    });
  }
  if (edge.id === "e15_fault") {
    return route(routeBottomToTop(source, target, layout));
  }
  if (edge.id === "e35_invalid") {
    return route(routeBottomToTop(source, target, layout));
  }
  if (edge.id === "e34_from_r3") {
    const start = portPoint(source, "left");
    const end = portPoint(target, "top");
    const points = compactCollinear([
      start,
      { x: end.x, y: start.y },
      end
    ]);
    return route({
      kind: "r3-schema-top-entry",
      sourcePort: "left",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    });
  }
  if (edge.id === "e72") {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "top");
    const points = compactCollinear(Math.abs(start.x - end.x) <= 1
      ? [start, end]
      : [start, { x: end.x, y: start.y }, end]);
    return route({
      kind: "approved-rejected-local-drop",
      sourcePort: "bottom",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    });
  }
  if (edge.id === "e06_invalid") {
    return route(routeBottomToTop(source, target, layout));
  }
  if (edge.id === "e06_invalid_from_l1") {
    return route(routeRightToLeft(source, target, layout));
  }
  if (edge.id === "e27_feedback_return") {
    return route(routeTopToBottom(source, target, layout));
  }
  const sourceRow = layout.rowIndex.get(edge.from);
  const targetRow = layout.rowIndex.get(edge.to);
  const sourceCol = layout.colIndex.get(edge.from);
  const targetCol = layout.colIndex.get(edge.to);
  if (sourceNode.type === "connector" || targetNode.type === "connector") {
    if (sourceNode.type === "decision" && targetNode.type === "connector" && edge.label && ABNORMAL_BRANCH_LABELS.has(String(edge.label || ""))) {
      return route(routeBottomToTop(source, target, layout));
    }
    return route(routeLocalConnectorEdge(source, target, layout));
  }
  if (sourceRow === targetRow && targetCol === sourceCol + 1) {
    return route(routeRightToLeft(source, target, layout));
  }
  if (sourceRow === targetRow && targetCol > sourceCol) {
    return route(routeRightToLeft(source, target, layout));
  }
  if (targetRow === sourceRow + 1 && Math.abs(targetCol - sourceCol) <= 1) {
    return route(orthogonalDogleg(source, target, "bottom", "top", layout));
  }
  return null;
}

function routeByEdgeId(edge, source, target, layout) {
  if (edge.id === "e11_no") {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "left");
    const laneY = Math.max(source.y + source.height + layout.U * 0.48, Math.min(end.y, source.y + source.height + layout.U * 0.82));
    const points = compactCollinear([
      start,
      { x: start.x, y: laneY },
      { x: end.x, y: laneY },
      end
    ]);
    return {
      kind: "param-no-bypass",
      sourcePort: "bottom",
      targetPort: "left",
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (edge.id === "e14_merge_safety") {
    const start = portPoint(source, "right");
    const end = portPoint(target, "left");
    const points = compactCollinear([start, end]);
    return {
      kind: "safety-merge-to-check-direct",
      sourcePort: "right",
      targetPort: "left",
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (edge.id === "e15_fault") {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "top");
    const points = compactCollinear([start, end]);
    return {
      kind: "safety-fault-vertical",
      sourcePort: "bottom",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (edge.id === "e06_invalid_from_l1") {
    const start = portPoint(source, "left");
    const end = portPoint(target, "bottom");
    const laneY = Math.max(start.y - layout.U * 0.64, end.y + layout.U * 0.55);
    const points = compactCollinear([
      start,
      { x: start.x, y: laneY },
      { x: end.x, y: laneY },
      end
    ]);
    return {
      kind: "l1-fault-open-arrow-stem",
      sourcePort: "left",
      targetPort: "bottom",
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (edge.id === "e34_from_r3") {
    const start = portPoint(source, "left");
    const end = portPoint(target, "top");
    const points = compactCollinear([start, { x: end.x, y: start.y }, end]);
    return {
      kind: "r3-schema-top-entry",
      sourcePort: "left",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    };
  }
  if (edge.id === "e06_invalid" || edge.id === "e15_fault") {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "top");
    const laneY = target.y - layout.U * 0.42;
    const points = compactCollinear([start, { x: start.x, y: laneY }, { x: end.x, y: laneY }, end]);
    return {
      kind: `${edge.id}-fault-lane`,
      sourcePort: "bottom",
      targetPort: "top",
      waypoints: points.slice(1, -1),
      points
    };
  }
  return null;
}

function sameRowAdjacent(edge, layout) {
  const sourceRow = layout.rowIndex.get(edge.from);
  const targetRow = layout.rowIndex.get(edge.to);
  const sourceCol = layout.colIndex.get(edge.from);
  const targetCol = layout.colIndex.get(edge.to);
  return sourceRow === targetRow && targetCol === sourceCol + 1;
}

function chooseRoute(edge, sourceNode, targetNode, source, target, layout) {
  const sourceRow = layout.rowIndex.get(edge.from);
  const targetRow = layout.rowIndex.get(edge.to);
  const sourceCol = layout.colIndex.get(edge.from);
  const targetCol = layout.colIndex.get(edge.to);
  const isAdjacentRight = sourceRow === targetRow && targetCol === sourceCol + 1;
  const isAdjacentLeft = sourceRow === targetRow && targetCol === sourceCol - 1;
  const isAdjacentDown = targetRow === sourceRow + 1 && Math.abs(targetCol - sourceCol) <= 1;
  const isDecisionBranch = sourceNode.type === "decision" && edge.label;
  const isConnectorPair = sourceNode.type === "connector" && targetNode.type === "connector" && sourceNode.text === targetNode.text;

  if (isConnectorPair) {
    return null;
  }

  const programRoute = routeProgramSchemeOverride(edge, sourceNode, targetNode, source, target, layout);
  if (programRoute) {
    validateRouteAgainstRules(edge, programRoute, sourceNode, targetNode, source, target, layout);
    return programRoute;
  }

  const explicit = routeByEdgeId(edge, source, target, layout);
  if (explicit) {
    validateRouteAgainstRules(edge, explicit, sourceNode, targetNode, source, target, layout);
    return explicit;
  }

  const localConnectorEndpoint = sourceNode.type === "connector" || targetNode.type === "connector";
  const localDistance = Math.hypot(target.centerX - source.centerX, target.centerY - source.centerY);
  if (localConnectorEndpoint && localDistance <= layout.U * 1.8 + 32) {
    const route = routeLocalConnectorEdge(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }
  if (localDistance <= layout.U * 1.65 + Math.max(source.width, target.width)) {
    const route = routeLocalConnectorEdge(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (isDecisionBranch) {
    const route = decisionBranchRoute(edge, source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (isAdjacentRight || isConnectorPair) {
    const route = routeRightToLeft(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (isAdjacentLeft) {
    const route = routeLeftToRight(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (isAdjacentDown) {
    const start = portPoint(source, "bottom");
    const end = portPoint(target, "top");
    if (Math.abs(start.x - end.x) <= 1) {
      const route = {
        kind: "down",
        sourcePort: "bottom",
        targetPort: "top",
        waypoints: [],
        points: [start, end]
      };
      validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
      return route;
    }
    const route = orthogonalDogleg(source, target, "bottom", "top", layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (sourceRow === targetRow && targetCol > sourceCol && targetCol - sourceCol <= 5) {
    const route = targetCol === sourceCol + 1 ? routeRightToLeft(source, target, layout) : routeTopToTop(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (sourceRow === targetRow && targetCol < sourceCol && sourceCol - targetCol <= 5) {
    const route = routeTopToTop(source, target, layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  if (targetRow > sourceRow && targetRow <= sourceRow + 1) {
    const route = orthogonalDogleg(source, target, "bottom", "top", layout);
    validateRouteAgainstRules(edge, route, sourceNode, targetNode, source, target, layout);
    return route;
  }

  return null;
}

function canResolveRemoteEdge(edge, sourceNode, targetNode) {
  return sourceNode.type === "connector" && targetNode.type === "connector" && sourceNode.text === targetNode.text;
}

function addSyntheticContinuationEdges(model, layout) {
  const existing = new Set(model.edges.map((edge) => `${edge.from}->${edge.to}`));
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const isSameConnectorPair = (from, to) => {
    const a = nodeById.get(from);
    const b = nodeById.get(to);
    return a && b && a.type === "connector" && b.type === "connector" && a.text === b.text;
  };
  const isSemanticConnector = (id) => {
    const node = nodeById.get(id);
    return node && node.type === "connector";
  };
  const additions = [];
  for (let r = 0; r < layout.rows.length; r += 1) {
    const row = layout.rows[r].filter((id) => id !== null);
    for (let c = 0; c < row.length - 1; c += 1) {
      const from = row[c];
      const to = row[c + 1];
      const key = `${from}->${to}`;
      if (existing.has(key)) {
        continue;
      }
      if (isSameConnectorPair(from, to)) {
        continue;
      }
      if (isSemanticConnector(from) || isSemanticConnector(to)) {
        continue;
      }
      additions.push({
        id: `auto_grid_${r + 1}_${c + 1}`,
        from,
        to,
        label: "",
        channel: "grid_continuation",
        style: "orthogonal",
        must_be_local: true,
        uses_connector_if_far: false,
        segment_length_policy: "balanced-local"
      });
    }
  }
  for (let r = 0; r < layout.rows.length - 1; r += 1) {
    if (r === 4) {
      continue;
    }
    let best = null;
    for (const fromId of layout.rows[r].filter((id) => id !== null)) {
      const fromBox = layout.positions.get(fromId);
      for (const toId of layout.rows[r + 1].filter((id) => id !== null)) {
        const toBox = layout.positions.get(toId);
        if (isSameConnectorPair(fromId, toId)) {
          continue;
        }
        if (isSemanticConnector(fromId) || isSemanticConnector(toId)) {
          continue;
        }
        const dx = Math.abs(fromBox.centerX - toBox.centerX);
        const verticalGap = toBox.y - (fromBox.y + fromBox.height);
        if (verticalGap < layout.U * 0.95 || verticalGap > layout.U * 1.60) {
          continue;
        }
        const score = dx + Math.abs(verticalGap - layout.U) * 0.25;
        if (!best || score < best.score) {
          best = { from: fromId, to: toId, score };
        }
      }
    }
    if (!best) {
      continue;
    }
    additions.push({
      id: `auto_row_${r + 1}`,
      from: best.from,
      to: best.to,
      label: "",
      channel: "row_continuation",
      style: "orthogonal",
      must_be_local: true,
      uses_connector_if_far: false,
      segment_length_policy: "balanced-local"
    });
  }
  layout.syntheticConnections = additions;
  return additions;
}

function buildCells(model, layout) {
  const cells = [];
  for (const node of model.nodes) {
    const box = layout.positions.get(node.id);
    if (!box) {
      throw new Error(`No layout position for ${node.id}`);
    }
    cells.push(createVertexCell(`${ID_PREFIX}${node.id}`, box.label, styleFor(node.type), box.x, box.y, box.width, box.height));
    if (node.type === "predefined_process") {
      const inset = Math.max(10, Math.round(layout.rect.height * 0.16));
      cells.push(createDecorLine(`${DECOR_PREFIX}${node.id}_left`, box.x + inset, box.y, box.height));
      cells.push(createDecorLine(`${DECOR_PREFIX}${node.id}_right`, box.x + box.width - inset, box.y, box.height));
    }
  }

  const syntheticEdges = addSyntheticContinuationEdges(model, layout);
  const allEdges = [...model.edges];
  const renderedEdgeIds = [];
  const connectorResolvedEdges = [];
  const omittedSyntheticEdgeIds = syntheticEdges.map((edge) => edge.id);
  const edgeItems = [];
  for (const edge of allEdges) {
    const sourceNode = model.nodes.find((node) => node.id === edge.from);
    const physicalTargetId = edge.to;
    const targetNode = model.nodes.find((node) => node.id === physicalTargetId);
    const source = layout.positions.get(edge.from);
    const target = layout.positions.get(physicalTargetId);
    if (!sourceNode || !targetNode || !source || !target) {
      throw new Error(`Cannot render edge ${edge.id}`);
    }
    const route = finalizeRoute(chooseRoute({ ...edge, to: physicalTargetId }, sourceNode, targetNode, source, target, layout), layout);
    if (!route) {
      if (String(edge.id).startsWith("auto_")) {
        omittedSyntheticEdgeIds.push(edge.id);
        continue;
      }
      if (canResolveRemoteEdge(edge, sourceNode, targetNode)) {
        connectorResolvedEdges.push({
          id: edge.id,
          from: edge.from,
          to: edge.to,
          channel: edge.channel || "model",
          reason: "remote logical edge represented by connector or row-continuation semantics"
        });
        continue;
      }
      throw new Error(`Edge ${edge.id} cannot be rendered locally and has no valid connector resolution`);
    }
    edgeItems.push({ edge, sourceNode, targetNode, route });
    renderedEdgeIds.push(edge.id);
  }
  layout.edgeRoutes = edgeItems.map((item) => item.route);
  for (const item of edgeItems) {
    const { edge, sourceNode, targetNode, route } = item;
    cells.push(createEdgeCell(`${EDGE_PREFIX}${edge.id}`, edge, sourceNode, targetNode, route));
  }
  for (const item of edgeItems) {
    const { edge, route } = item;
    const labelPoint = labelPositionForRoute(edge, route, layout);
    if (labelPoint) {
      cells.push(createLabelCell(`${LABEL_PREFIX}${edge.id}`, fitEdgeLabel(edge.label || ""), labelPoint.x, labelPoint.y));
      layout.placedLabelBoxes = layout.placedLabelBoxes || [];
      layout.placedLabelBoxes.push(boxForLabelCenter(labelPoint, edge.label || ""));
    }
  }
  layout.renderedEdgeIds = renderedEdgeIds;
  layout.connectorResolvedEdges = connectorResolvedEdges;
  layout.connectorResolvedEdgeIds = connectorResolvedEdges.map((edge) => edge.id);
  layout.omittedSyntheticEdgeIds = omittedSyntheticEdgeIds;
  layout.skippedEdgeIds = [];
  return cells;
}

function writeLayoutPlan(model, layout) {
  const lines = [];
  lines.push("# A1 Engineering Flowchart Layout Plan");
  lines.push("");
  lines.push("## Page And Template");
  lines.push("- Template file: aa.drawio");
  lines.push(`- A1 page size read from template: ${layout.page.width} x ${layout.page.height}`);
  lines.push(`- Detected template title block: x=${layout.templateTitleBlock.x}, y=${layout.templateTitleBlock.y}, width=${layout.templateTitleBlock.width}, height=${layout.templateTitleBlock.height}`);
  lines.push(`- Forbidden title block area: x=${layout.forbiddenArea.x}, y=${layout.forbiddenArea.y}, width=${layout.forbiddenArea.width}, height=${layout.forbiddenArea.height}`);
  lines.push("");
  lines.push("## Symbol Ratio Rules");
  lines.push("- Terminator, process, predefined process, data, document, and manual input use L = 2W.");
  lines.push("- Stored data uses L = 1.5W, following the common horizontal 3:2 proportion used for database-style stored-data symbols.");
  lines.push("- Decision uses L = 1.5W.");
  lines.push("- Connector uses L = W.");
  lines.push("- Autosize is disabled on all repo_flow_ nodes.");
  lines.push("");
  lines.push("## Calculated Sizes");
  lines.push(`- Rect/parallelogram family: ${layout.rect.width} x ${layout.rect.height}`);
  lines.push(`- Stored data/database family: ${layout.stored.width} x ${layout.stored.height}`);
  lines.push(`- Decision: ${layout.decision.width} x ${layout.decision.height}`);
  lines.push(`- Connector: ${layout.connector.width} x ${layout.connector.height}`);
  lines.push(`- Uniform local segment length U: ${layout.U}`);
  lines.push(`- Row gap: ${layout.rowGap}`);
  lines.push("");
  lines.push("## Balanced 2D Grid Strategy");
  lines.push("- The renderer computes symbol sizes from the A1 free area, node count, and readability limits.");
  lines.push("- Nodes are placed in a program-scheme lane layout: multiple left-to-right horizontal flow lines with explicit row connector symbols.");
  lines.push("- Rows are not forced to connect with synthetic lines; cross-row relationships use R/F/T/P/A/L connector pairs or local decision branches.");
  lines.push("- Node labels are shortened, wrapped, and fitted before draw.io cells are generated.");
  lines.push("");
  lines.push("## Title Block Avoidance");
  lines.push("- The renderer rejects any node that intersects the forbidden area.");
  lines.push("- The validator checks nodes, lines, labels, and waypoints against the forbidden area.");
  lines.push("- The bottom-right page area is left clear around the original title block.");
  lines.push("");
  lines.push("## Connector Pairs");
  for (const pair of model.connectors) {
    lines.push(`- ${pair.label}: ${pair.meaning}; nodes ${pair.nodes.join(" and ")}`);
  }
  lines.push("");
  lines.push("## Long-Line Prevention");
  lines.push("- Direct visible edges are generated only for local rightward or adjacent downward relationships.");
  lines.push("- Remote logical transfers are recorded as connector-resolved logical edges, never as skipped edges.");
  lines.push("- Explicit mxPoint support is implemented in createEdgeCell for controlled Manhattan routing.");
  lines.push("- Decision branch labels are stored in separate repo_flow_label_ text cells so they can be offset from line segments.");
  lines.push("- No long cross-page polylines are generated.");
  lines.push("");
  lines.push("## No Visible Modules");
  lines.push("- Phase and group metadata are kept only in flow_model.json.");
  lines.push("- The draw.io page contains no module frames, module titles, legends, or top title.");
  lines.push("");
  lines.push("## English Labels");
  lines.push("- All generated node labels and edge labels are English.");
  lines.push("- Each node label is restricted to at most two lines.");
  lines.push("- Long labels are shortened before wrapping.");
  lines.push("- Decision labels are emitted once per rendered branch edge, without duplicate text cells.");
  lines.push("- Separate branch label cells use the repo_flow_label_ prefix and are excluded from the flowchart element count.");
  lines.push("");
  lines.push("## GOST / ISO 5807 Mapping Summary");
  lines.push("- Terminator: rounded start/end symbol.");
  lines.push("- Process: rectangle.");
  lines.push("- Predefined process: rectangle with two inner vertical lines.");
  lines.push("- Decision: diamond.");
  lines.push("- Data: parallelogram.");
  lines.push("- Stored data: cylinder-style stored data symbol.");
  lines.push("- Document: document symbol.");
  lines.push("- Manual input: manual input symbol.");
  lines.push("- Connector: circular connector.");
  lines.push("");
  lines.push(`## ${model.diagram.target_element_count} Elements`);
  for (const node of model.nodes) {
    const box = layout.positions.get(node.id);
    lines.push(`- ${node.preferred_order}. ${box.label.replace(/\n/g, " / ")} (${node.type})`);
  }
  fs.writeFileSync(path.join(WORK_DIR, "layout_plan_final.md"), `${lines.join("\n")}\n`);
}

async function main() {
  const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  validateModel(model);

  const xml = fs.readFileSync(TEMPLATE_PATH, "utf8");
  const doc = parser.parse(xml);
  const diagram = asArray(doc.mxfile.diagram)[0];
  const graph = diagram.mxGraphModel;
  const root = graph.root;
  purgeExisting(root);

  const templateInfo = computeTemplateInfo(graph, model);
  const elkResult = await runElk(model);
  const layout = computeLayout(model, templateInfo, elkResult);
  validateNodeNonOverlap(layout, model);
  const newCells = buildCells(model, layout);
  applyFrameRules(root, layout.page);
  root.mxCell = asArray(root.mxCell).concat(newCells);

  fs.writeFileSync(OUTPUT_PATH, builder.build(doc));
  const metrics = {
    page: layout.page,
    frame: frameBoxForPage(layout.page),
    frameRules: FRAME_RULES,
    templateTitleBlock: layout.templateTitleBlock,
    forbiddenArea: layout.forbiddenArea,
    U: layout.U,
    rect: layout.rect,
    decision: layout.decision,
    stored: layout.stored,
    connector: layout.connector,
    standardHorizontalSegmentLengthPx: standardHorizontalLength(),
    standardVerticalSegmentLengthPx: standardVerticalLength(),
    rowGap: layout.rowGap,
    rows: layout.rows,
    nodeCount: model.nodes.length,
    drawnEdgeCount: newCells.filter((cell) => String(cell["@_id"] || "").startsWith(EDGE_PREFIX)).length,
    renderedEdgeIds: layout.renderedEdgeIds,
    skippedEdgeIds: layout.skippedEdgeIds,
    connectorResolvedEdgeIds: layout.connectorResolvedEdgeIds,
    connectorResolvedEdges: layout.connectorResolvedEdges,
    omittedSyntheticEdgeIds: layout.omittedSyntheticEdgeIds,
    syntheticConnections: layout.syntheticConnections,
    elkUsed: Boolean(elkResult && elkResult.children),
    layoutMode: PROGRAM_SCHEME_LAYOUT_RULES.mode
  };
  fs.writeFileSync(METRICS_PATH, `${JSON.stringify(metrics, null, 2)}\n`);
  writeLayoutPlan(model, layout);
  console.log(`Rendered ${OUTPUT_PATH}`);
  console.log(`repo_flow_ elements: ${model.nodes.length}`);
  console.log(`Program scheme lanes: ${layout.rows.length} rows x ${layout.maxRow} max columns`);
  console.log(`Uniform local segment length U: ${layout.U}`);
  console.log(`Rendered local edges: ${layout.renderedEdgeIds.length}`);
  console.log(`Remote edges represented by connectors: ${layout.connectorResolvedEdgeIds.length}`);
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
