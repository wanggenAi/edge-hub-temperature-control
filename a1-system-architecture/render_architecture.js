#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser, XMLBuilder } = require("fast-xml-parser");
const {
  FRAME_RULES,
  PROJECT_A1_RULES,
  ARCHITECTURE_LAYOUT_RULES,
  STYLE_RULES,
  ARCHITECTURE_RULES
} = require("./architecture_rules");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = path.join(ROOT_DIR, "aa.drawio");
const MODEL_PATH = path.join(WORK_DIR, "architecture_model.json");
const OUTPUT_PATH = path.join(WORK_DIR, "system_architecture_a1.drawio");
const METRICS_PATH = path.join(WORK_DIR, "architecture_metrics.json");

const NODE_PREFIX = "arch_node_";
const GROUP_PREFIX = "arch_group_";
const EDGE_PREFIX = "arch_edge_";
const LABEL_PREFIX = "arch_label_";
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

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const value = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(value) ? value : fallback;
}

function containsChinese(text) {
  return /[\u3400-\u9fff]/.test(String(text || ""));
}

function escapeText(value) {
  return String(value || "").replace(/\n/g, "<br>");
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
    const normalized = current >= (thick + thin) / 2 ? thick : thin;
    cell["@_style"] = replaceStyleValue(style, "strokeWidth", normalized);
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

function applyFrameRules(root, page) {
  alignTitleBlockToFrame(root, page);
  normalizeTitleBlockStrokeWidths(root);
  root.mxCell = asArray(root.mxCell).concat([createOuterFrameCell(page)]);
}

function computeTemplateInfo(graph) {
  const page = {
    width: attrNumber(graph, "pageWidth", 3300),
    height: attrNumber(graph, "pageHeight", 2339)
  };
  return {
    page,
    frame: frameBoxForPage(page),
    forbiddenArea: PROJECT_A1_RULES.forbiddenArea
  };
}

function baseNodeStyle(extra = "") {
  return [
    "html=1",
    "whiteSpace=wrap",
    "fontFamily=Helvetica",
    "fontSize=20",
    "fontColor=#000000",
    "align=center",
    "verticalAlign=middle",
    `strokeColor=${STYLE_RULES.strokeColor}`,
    `strokeWidth=${STYLE_RULES.strokeWidth}`,
    `fillColor=${STYLE_RULES.nodeFill}`,
    "autosize=0",
    "shadow=0",
    "gradientColor=none",
    extra
  ].filter(Boolean).join(";");
}

function nodeStyle(type) {
  switch (type) {
    case "database":
      return baseNodeStyle("shape=mxgraph.flowchart.database;rounded=0;fontSize=18;spacingTop=18");
    case "external":
      return baseNodeStyle("shape=actor;rounded=0");
    case "bus":
      return baseNodeStyle("shape=parallelogram;perimeter=parallelogramPerimeter;rounded=0");
    case "protocol":
      return baseNodeStyle("rounded=1;arcSize=18");
    case "ai":
      return baseNodeStyle("rounded=0;dashed=1");
    case "ui":
      return baseNodeStyle("shape=document;boundedLbl=1;rounded=0");
    case "device":
    case "edge":
    case "service":
    default:
      return baseNodeStyle("rounded=0");
  }
}

function groupStyle() {
  return [
    "rounded=0",
    "whiteSpace=wrap",
    "html=1",
    "fontFamily=Helvetica",
    "fontSize=22",
    "fontStyle=1",
    "align=center",
    "verticalAlign=top",
    "spacingTop=10",
    `strokeColor=${STYLE_RULES.strokeColor}`,
    `strokeWidth=${STYLE_RULES.groupStrokeWidth}`,
    `fillColor=${STYLE_RULES.groupFill}`,
    "shadow=0"
  ].join(";");
}

function edgeStyle(edge, route) {
  const portToPoint = (port) => {
    if (port === "right") return { x: 1, y: 0.5 };
    if (port === "left") return { x: 0, y: 0.5 };
    if (port === "top") return { x: 0.5, y: 0 };
    if (port === "bottom") return { x: 0.5, y: 1 };
    throw new Error(`Unsupported port: ${port}`);
  };
  const exit = portToPoint(route.sourcePort || "right");
  const entry = portToPoint(route.targetPort || "left");
  return [
    "html=1",
    "edgeStyle=orthogonalEdgeStyle",
    "rounded=0",
    "orthogonalLoop=1",
    "jettySize=auto",
    "curved=0",
    `endArrow=${STYLE_RULES.arrowStyle.endArrow}`,
    `endFill=${STYLE_RULES.arrowStyle.endFill}`,
    `endSize=${STYLE_RULES.arrowStyle.endSize}`,
    `strokeColor=${STYLE_RULES.strokeColor}`,
    `strokeWidth=${STYLE_RULES.connectorStrokeWidth}`,
    "fontFamily=Helvetica",
    "fontSize=17",
    "fontColor=#000000",
    `exitX=${exit.x}`,
    `exitY=${exit.y}`,
    `entryX=${entry.x}`,
    `entryY=${entry.y}`,
    "exitDx=0",
    "exitDy=0",
    "entryDx=0",
    "entryDy=0"
  ].join(";");
}

function labelBoxSize(text) {
  return {
    width: Math.max(70, String(text || "").length * 8 + 20),
    height: 26
  };
}

function boxCenter(box) {
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

function overlaps(a, b, pad = 0) {
  return !(
    a.x + a.width <= b.x - pad ||
    a.x >= b.x + b.width + pad ||
    a.y + a.height <= b.y - pad ||
    a.y >= b.y + b.height + pad
  );
}

function computeLayout(model, templateInfo) {
  const { page, forbiddenArea } = templateInfo;
  const frame = frameBoxForPage(page);
  const rules = ARCHITECTURE_LAYOUT_RULES;
  const groupWidth = rules.groupSize.width;
  const groupHeight = rules.groupSize.height;
  const groupCount = model.layers.length;
  const drawingLeft = frame.x + rules.pagePaddingPx.left;
  const drawingRight = frame.x + frame.width - rules.pagePaddingPx.right;
  const drawingTop = frame.y + rules.pagePaddingPx.top;
  const usableWidth = drawingRight - drawingLeft;
  const groupGap = (usableWidth - groupWidth * groupCount) / Math.max(1, groupCount - 1);
  if (groupGap < rules.minLayerGapPx) {
    throw new Error(`Layer gap ${groupGap.toFixed(1)} is too small for an A1 architecture drawing.`);
  }
  const groupY = drawingTop;
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const globalMaxRow = Math.max(...model.nodes.map((node) => node.row));
  const globalRowStep = (groupHeight - rules.groupHeaderHeightPx - rules.groupPaddingPx * 2) / Math.max(1, globalMaxRow);
  const groups = new Map();
  const nodes = new Map();
  for (let index = 0; index < model.layers.length; index += 1) {
    const layer = model.layers[index];
    const groupX = drawingLeft + index * (groupWidth + groupGap);
    const groupBox = { x: groupX, y: groupY, width: groupWidth, height: groupHeight };
    groups.set(layer.id, groupBox);
    const layerNodes = layer.nodes.map((nodeId) => nodeById.get(nodeId)).filter(Boolean);
    const rowCounts = new Map();
    for (const node of layerNodes) {
      rowCounts.set(node.row, (rowCounts.get(node.row) || 0) + 1);
    }
    const rowSeen = new Map();
    for (const node of layerNodes) {
      const size = node.type === "bus" ? rules.busSize : node.type === "external" ? rules.smallComponentSize : rules.componentSize;
      const countInRow = rowCounts.get(node.row) || 1;
      const seenInRow = rowSeen.get(node.row) || 0;
      rowSeen.set(node.row, seenInRow + 1);
      const slotGap = 16;
      const totalSlotWidth = countInRow * size.width + Math.max(0, countInRow - 1) * slotGap;
      const rowLeft = groupX + (groupWidth - totalSlotWidth) / 2;
      const x = countInRow === 1
        ? groupX + (groupWidth - size.width) / 2
        : rowLeft + seenInRow * (size.width + slotGap);
      const y = groupY + rules.groupHeaderHeightPx + rules.groupPaddingPx + node.row * globalRowStep;
      const box = { x, y, width: size.width, height: size.height };
      if (overlaps(box, forbiddenArea, 8)) {
        throw new Error(`Node ${node.id} intersects title-block forbidden area.`);
      }
      nodes.set(node.id, box);
    }
  }
  return { page, frame, forbiddenArea, groups, nodes, groupGap };
}

function purgeExisting(root) {
  root.mxCell = asArray(root.mxCell).filter((cell) => {
    const id = String(cell["@_id"] || "");
    return !id.startsWith(NODE_PREFIX) &&
      !id.startsWith(GROUP_PREFIX) &&
      !id.startsWith(EDGE_PREFIX) &&
      !id.startsWith(LABEL_PREFIX) &&
      !id.startsWith(FRAME_PREFIX);
  });
}

function portPoint(box, port) {
  if (port === "right") return { x: box.x + box.width, y: box.y + box.height / 2 };
  if (port === "left") return { x: box.x, y: box.y + box.height / 2 };
  if (port === "top") return { x: box.x + box.width / 2, y: box.y };
  if (port === "bottom") return { x: box.x + box.width / 2, y: box.y + box.height };
  throw new Error(`Unsupported port: ${port}`);
}

function compactCollinear(points) {
  const result = [];
  for (const point of points) {
    const prev = result[result.length - 1];
    if (prev && Math.abs(prev.x - point.x) <= 0.1 && Math.abs(prev.y - point.y) <= 0.1) continue;
    result.push(point);
  }
  let changed = true;
  while (changed) {
    changed = false;
    for (let index = 1; index < result.length - 1; index += 1) {
      const a = result[index - 1];
      const b = result[index];
      const c = result[index + 1];
      if ((Math.abs(a.x - b.x) <= 0.1 && Math.abs(b.x - c.x) <= 0.1) ||
        (Math.abs(a.y - b.y) <= 0.1 && Math.abs(b.y - c.y) <= 0.1)) {
        result.splice(index, 1);
        changed = true;
        break;
      }
    }
  }
  return result;
}

function routeEdge(edge, layout) {
  const source = layout.nodes.get(edge.from);
  const target = layout.nodes.get(edge.to);
  if (!source || !target) throw new Error(`Cannot route ${edge.id}`);
  const sourceCenter = boxCenter(source);
  const targetCenter = boxCenter(target);
  let sourcePort = targetCenter.x >= sourceCenter.x ? "right" : "left";
  let targetPort = sourcePort === "right" ? "left" : "right";
  if (Math.abs(targetCenter.x - sourceCenter.x) <= 1) {
    sourcePort = targetCenter.y >= sourceCenter.y ? "bottom" : "top";
    targetPort = sourcePort === "bottom" ? "top" : "bottom";
  }
  const start = portPoint(source, sourcePort);
  const end = portPoint(target, targetPort);
  const points = Math.abs(start.y - end.y) <= 0.1
    ? [start, end]
    : Math.abs(start.x - end.x) <= 0.1
      ? [start, end]
      : compactCollinear([start, { x: end.x, y: start.y }, end]);
  const bends = Math.max(0, points.length - 2);
  if (bends > ARCHITECTURE_LAYOUT_RULES.connection.maxBends) {
    throw new Error(`Edge ${edge.id} has ${bends} bends; architecture rule allows ${ARCHITECTURE_LAYOUT_RULES.connection.maxBends}.`);
  }
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    if (Math.abs(a.x - b.x) > 0.1 && Math.abs(a.y - b.y) > 0.1) {
      throw new Error(`Edge ${edge.id} contains a diagonal segment.`);
    }
    const length = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    if (length > ARCHITECTURE_LAYOUT_RULES.connection.maxSegmentLengthPx) {
      throw new Error(`Edge ${edge.id} segment ${length.toFixed(1)} exceeds max ${ARCHITECTURE_LAYOUT_RULES.connection.maxSegmentLengthPx}.`);
    }
  }
  return { sourcePort, targetPort, points, waypoints: points.slice(1, -1) };
}

function createEdgeCell(id, edge, route) {
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
  return {
    "@_id": id,
    "@_value": "",
    "@_style": edgeStyle(edge, route),
    "@_parent": "1",
    "@_edge": "1",
    "@_source": `${NODE_PREFIX}${edge.from}`,
    "@_target": `${NODE_PREFIX}${edge.to}`,
    mxGeometry
  };
}

function createLabelCell(id, value, x, y) {
  const size = labelBoxSize(value);
  return createVertexCell(
    id,
    value,
    [
      "text",
      "html=1",
      "strokeColor=none",
      "fillColor=none",
      "fontFamily=Helvetica",
      "fontSize=15",
      "fontColor=#000000",
      "align=center",
      "verticalAlign=middle",
      "resizable=0",
      "autosize=0"
    ].join(";"),
    x - size.width / 2,
    y - size.height / 2,
    size.width,
    size.height
  );
}

function buildCells(model, layout) {
  const cells = [];
  for (const layer of model.layers) {
    const box = layout.groups.get(layer.id);
    cells.push(createVertexCell(`${GROUP_PREFIX}${layer.id}`, layer.title, groupStyle(), box.x, box.y, box.width, box.height));
  }
  for (const node of model.nodes) {
    const box = layout.nodes.get(node.id);
    cells.push(createVertexCell(`${NODE_PREFIX}${node.id}`, node.label, nodeStyle(node.type), box.x, box.y, box.width, box.height));
  }
  const routes = [];
  for (const edge of model.edges) {
    const route = routeEdge(edge, layout);
    routes.push({ edge, route });
    cells.push(createEdgeCell(`${EDGE_PREFIX}${edge.id}`, edge, route));
  }
  for (const { edge, route } of routes) {
    if (!edge.label) continue;
    const middleSegmentIndex = Math.max(1, Math.floor(route.points.length / 2));
    const a = route.points[middleSegmentIndex - 1];
    const b = route.points[middleSegmentIndex];
    const center = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 20 };
    cells.push(createLabelCell(`${LABEL_PREFIX}${edge.id}`, edge.label, center.x, center.y));
  }
  return { cells, routes };
}

function validateModel(model) {
  if (model.nodes.length !== model.diagram.target_element_count) {
    throw new Error(`Model node count ${model.nodes.length} does not equal target ${model.diagram.target_element_count}.`);
  }
  if (model.nodes.length < ARCHITECTURE_RULES.minElements || model.nodes.length > ARCHITECTURE_RULES.maxElements) {
    throw new Error(`Architecture element count ${model.nodes.length} is outside ${ARCHITECTURE_RULES.minElements}-${ARCHITECTURE_RULES.maxElements}.`);
  }
  const ids = new Set();
  for (const node of model.nodes) {
    if (ids.has(node.id)) throw new Error(`Duplicate node id ${node.id}.`);
    ids.add(node.id);
    if (!ARCHITECTURE_RULES.allowedNodeTypes.includes(node.type)) throw new Error(`Unsupported node type ${node.type}.`);
    if (containsChinese(node.label)) throw new Error(`Chinese label is not allowed: ${node.label}`);
  }
  for (const edge of model.edges) {
    if (!ids.has(edge.from) || !ids.has(edge.to)) throw new Error(`Edge ${edge.id} references missing node.`);
  }
}

function main() {
  const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  validateModel(model);
  const xml = fs.readFileSync(TEMPLATE_PATH, "utf8");
  const doc = parser.parse(xml);
  const diagram = asArray(doc.mxfile.diagram)[0];
  diagram["@_name"] = "System Architecture A1";
  const graph = diagram.mxGraphModel;
  const root = graph.root;
  purgeExisting(root);
  const templateInfo = computeTemplateInfo(graph);
  const layout = computeLayout(model, templateInfo);
  const { cells, routes } = buildCells(model, layout);
  applyFrameRules(root, layout.page);
  root.mxCell = asArray(root.mxCell).concat(cells);
  fs.writeFileSync(OUTPUT_PATH, builder.build(doc));
  const nodeBoxes = Array.from(layout.nodes.values());
  const minX = Math.min(...nodeBoxes.map((box) => box.x));
  const maxX = Math.max(...nodeBoxes.map((box) => box.x + box.width));
  const minY = Math.min(...nodeBoxes.map((box) => box.y));
  const maxY = Math.max(...nodeBoxes.map((box) => box.y + box.height));
  const metrics = {
    page: layout.page,
    frame: layout.frame,
    frameRules: FRAME_RULES,
    forbiddenArea: layout.forbiddenArea,
    nodeCount: model.nodes.length,
    edgeCount: model.edges.length,
    groupCount: model.layers.length,
    coverageX: (maxX - minX) / layout.page.width,
    coverageY: (maxY - minY) / (layout.forbiddenArea.y - 40),
    groupGap: layout.groupGap,
    layoutMode: ARCHITECTURE_LAYOUT_RULES.mode,
    nodes: Object.fromEntries(Array.from(layout.nodes.entries())),
    groups: Object.fromEntries(Array.from(layout.groups.entries())),
    routes: routes.map(({ edge, route }) => ({ id: edge.id, points: route.points }))
  };
  fs.writeFileSync(METRICS_PATH, `${JSON.stringify(metrics, null, 2)}\n`);
  console.log(`Rendered ${OUTPUT_PATH}`);
  console.log(`Architecture elements: ${model.nodes.length}`);
  console.log(`Layer groups: ${model.layers.length}`);
  console.log(`Coverage: ${(metrics.coverageX * 100).toFixed(1)}% x ${(metrics.coverageY * 100).toFixed(1)}%`);
}

main();
