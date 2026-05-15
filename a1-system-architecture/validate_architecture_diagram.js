#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser } = require("fast-xml-parser");
const { FRAME_RULES, ARCHITECTURE_LAYOUT_RULES, TEXT_FIT_RULES } = require("./architecture_rules");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const DRAWIO = path.join(WORK_DIR, "architecture_diagram.drawio");
const TEMPLATE = path.join(ROOT_DIR, "aa.drawio");
const METRICS = path.join(WORK_DIR, "architecture_diagram_metrics.json");
const SUMMARY = path.join(WORK_DIR, "architecture_diagram_validator_summary.json");
const REPORT = path.join(WORK_DIR, "architecture_diagram_check_report.md");
const PREFIX = "arch2_";

const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: "@_", trimValues: false });

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const n = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(n) ? n : fallback;
}

function boxOf(cell) {
  const g = cell?.mxGeometry || {};
  return { x: attrNumber(g, "x"), y: attrNumber(g, "y"), width: attrNumber(g, "width"), height: attrNumber(g, "height") };
}

function overlaps(a, b, pad = 0) {
  return !(a.x + a.width <= b.x - pad || a.x >= b.x + b.width + pad || a.y + a.height <= b.y - pad || a.y >= b.y + b.height + pad);
}

function mmToPageX(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.width) * page.width;
}

function mmToPageY(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.height) * page.height;
}

function frameBox(page) {
  const left = mmToPageX(FRAME_RULES.marginsMm.left, page);
  const top = mmToPageY(FRAME_RULES.marginsMm.top, page);
  const right = mmToPageX(FRAME_RULES.marginsMm.right, page);
  const bottom = mmToPageY(FRAME_RULES.marginsMm.bottom, page);
  return { x: left, y: top, width: page.width - left - right, height: page.height - top - bottom };
}

function parsePorts(style) {
  const get = (name, fallback) => {
    const m = String(style || "").match(new RegExp(`${name}=([0-9.]+)`));
    return m ? Number(m[1]) : fallback;
  };
  return { exitX: get("exitX", 1), exitY: get("exitY", 0.5), entryX: get("entryX", 0), entryY: get("entryY", 0.5) };
}

function portNameFromPair(x, y) {
  const close = (a, b) => Math.abs(a - b) <= 0.01;
  if (close(x, 0) && close(y, 0.5)) return "left";
  if (close(x, 1) && close(y, 0.5)) return "right";
  if (close(x, 0.5) && close(y, 0)) return "top";
  if (close(x, 0.5) && close(y, 1)) return "bottom";
  return null;
}

function parseStyle(style) {
  const out = {};
  for (const part of String(style || "").split(";")) {
    if (!part || !part.includes("=")) continue;
    const [key, ...rest] = part.split("=");
    out[key] = rest.join("=");
  }
  return out;
}

function decodeLabel(value) {
  return String(value || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .trim();
}

function nodeKind(cell) {
  const style = String(cell["@_style"] || "");
  if (style.includes("shape=parallelogram")) return "topic";
  if (style.includes("database")) return "db";
  if (style.includes("rounded=1")) return "round";
  return "rect";
}

function estimateTextBox(cell) {
  const box = boxOf(cell);
  const style = parseStyle(cell["@_style"]);
  const kind = nodeKind(cell);
  const fontSize = Number(style.fontSize) || TEXT_FIT_RULES.nodeFontSize[kind] || TEXT_FIT_RULES.defaultFontSize;
  const pad = {
    left: Number(style.spacingLeft) || TEXT_FIT_RULES.defaultPaddingPx.left,
    right: Number(style.spacingRight) || TEXT_FIT_RULES.defaultPaddingPx.right,
    top: Number(style.spacingTop) || TEXT_FIT_RULES.defaultPaddingPx.top,
    bottom: Number(style.spacingBottom) || TEXT_FIT_RULES.defaultPaddingPx.bottom
  };
  const usableRatio = TEXT_FIT_RULES.nodeUsableWidthRatio[kind] || 1;
  const usableWidth = Math.max(0, box.width * usableRatio - pad.left - pad.right);
  const usableHeight = Math.max(0, box.height - pad.top - pad.bottom);
  const lines = decodeLabel(cell["@_value"]).split(/\n+/).filter(Boolean);
  const estimatedLineWidths = lines.map((line) => line.length * fontSize * TEXT_FIT_RULES.averageCharWidthMultiplier);
  const estimatedWidth = Math.max(0, ...estimatedLineWidths);
  const estimatedHeight = lines.length * fontSize * TEXT_FIT_RULES.lineHeightMultiplier;
  return { kind, fontSize, lines, usableWidth, usableHeight, estimatedWidth, estimatedHeight };
}

function edgePoints(edge, map) {
  const source = map.get(String(edge["@_source"] || ""));
  const target = map.get(String(edge["@_target"] || ""));
  if (!source || !target) return null;
  const ports = parsePorts(edge["@_style"]);
  const sb = boxOf(source);
  const tb = boxOf(target);
  const points = [{ x: sb.x + sb.width * ports.exitX, y: sb.y + sb.height * ports.exitY }];
  const waypoints = edge.mxGeometry?.Array?.mxPoint ? asArray(edge.mxGeometry.Array.mxPoint) : [];
  for (const p of waypoints) points.push({ x: attrNumber(p, "x"), y: attrNumber(p, "y") });
  points.push({ x: tb.x + tb.width * ports.entryX, y: tb.y + tb.height * ports.entryY });
  return points;
}

function pointAlmostEqual(a, b, tolerance = 0.2) {
  return Math.abs(a.x - b.x) <= tolerance && Math.abs(a.y - b.y) <= tolerance;
}

function centerPointForPort(box, port) {
  if (port === "left") return { x: box.x, y: box.y + box.height / 2 };
  if (port === "right") return { x: box.x + box.width, y: box.y + box.height / 2 };
  if (port === "top") return { x: box.x + box.width / 2, y: box.y };
  if (port === "bottom") return { x: box.x + box.width / 2, y: box.y + box.height };
  return null;
}

function segmentApproachesPort(previous, endpoint, port) {
  const tol = 0.2;
  if (pointAlmostEqual(previous, endpoint, tol)) return true;
  if (port === "left") return Math.abs(previous.y - endpoint.y) <= tol && previous.x < endpoint.x - tol;
  if (port === "right") return Math.abs(previous.y - endpoint.y) <= tol && previous.x > endpoint.x + tol;
  if (port === "top") return Math.abs(previous.x - endpoint.x) <= tol && previous.y < endpoint.y - tol;
  if (port === "bottom") return Math.abs(previous.x - endpoint.x) <= tol && previous.y > endpoint.y + tol;
  return false;
}

function segmentLeavesPort(start, next, port) {
  const tol = 0.2;
  if (pointAlmostEqual(start, next, tol)) return true;
  if (port === "left") return Math.abs(next.y - start.y) <= tol && next.x < start.x - tol;
  if (port === "right") return Math.abs(next.y - start.y) <= tol && next.x > start.x + tol;
  if (port === "top") return Math.abs(next.x - start.x) <= tol && next.y < start.y - tol;
  if (port === "bottom") return Math.abs(next.x - start.x) <= tol && next.y > start.y + tol;
  return false;
}

function bendCount(points) {
  let bends = 0;
  let prev = null;
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1];
    const b = points[i];
    const dir = Math.abs(a.x - b.x) > Math.abs(a.y - b.y) ? "h" : "v";
    if (prev && prev !== dir) bends += 1;
    prev = dir;
  }
  return bends;
}

function edgeKey(edge) {
  return [String(edge["@_source"] || "").replace(PREFIX, ""), String(edge["@_target"] || "").replace(PREFIX, "")];
}

function edgeKeyString(edge) {
  return edgeKey(edge).join("->");
}

function centerX(cell) {
  const b = boxOf(cell);
  return b.x + b.width / 2;
}

function centerY(cell) {
  const b = boxOf(cell);
  return b.y + b.height / 2;
}

function allowedHorizontalSegmentLength(edge) {
  const key = edgeKeyString(edge);
  if (key === "params_topic->mqtt_broker" || key === "telemetry_topic->mqtt_broker") {
    return ARCHITECTURE_LAYOUT_RULES.connection.maxCommunicationSpineLengthPx;
  }
  return ARCHITECTURE_LAYOUT_RULES.connection.maxSegmentLengthPx;
}

function segmentBox(a, b, pad = 2) {
  const vertical = Math.abs(a.x - b.x) <= 0.1;
  const horizontal = Math.abs(a.y - b.y) <= 0.1;
  return {
    x: Math.min(a.x, b.x) - (vertical ? pad : 0),
    y: Math.min(a.y, b.y) - (horizontal ? pad : 0),
    width: Math.max(1, Math.abs(a.x - b.x)) + (vertical ? pad * 2 : 0),
    height: Math.max(1, Math.abs(a.y - b.y)) + (horizontal ? pad * 2 : 0)
  };
}

function orientation(a, b, c) {
  const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
  if (Math.abs(value) < 0.01) return 0;
  return value > 0 ? 1 : 2;
}

function segmentsIntersect(a, b, c, d) {
  const o1 = orientation(a, b, c);
  const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a);
  const o4 = orientation(c, d, b);
  return o1 !== o2 && o3 !== o4;
}

function main() {
  const errors = [];
  const warnings = [];
  const xml = fs.readFileSync(DRAWIO, "utf8");
  const templateXml = fs.readFileSync(TEMPLATE, "utf8");
  const metrics = JSON.parse(fs.readFileSync(METRICS, "utf8"));
  if (!templateXml.includes(FRAME_RULES.titleBlock.id) || !xml.includes(FRAME_RULES.titleBlock.id)) errors.push("Original title block is not preserved.");
  const doc = parser.parse(xml);
  const graph = asArray(doc.mxfile.diagram)[0].mxGraphModel;
  const page = { width: attrNumber(graph, "pageWidth"), height: attrNumber(graph, "pageHeight") };
  const cells = asArray(graph.root.mxCell);
  const map = new Map(cells.map((cell) => [String(cell["@_id"] || ""), cell]));
  const nodes = cells.filter((cell) => String(cell["@_id"] || "").startsWith(PREFIX) && String(cell["@_vertex"] || "") === "1" && !String(cell["@_id"] || "").startsWith(`${PREFIX}layer_`));
  const layers = cells.filter((cell) => String(cell["@_id"] || "").startsWith(`${PREFIX}layer_`));
  const edges = cells.filter((cell) => String(cell["@_id"] || "").startsWith(`${PREFIX}edge_`) && String(cell["@_edge"] || "") === "1");
  const edgeKeySet = new Set(edges.map(edgeKeyString));
  const border = map.get(FRAME_RULES.outerBorder.id);
  if (!border) errors.push("Outer A1 border is missing.");
  else {
    const expected = frameBox(page);
    const actual = boxOf(border);
    for (const key of ["x", "y", "width", "height"]) {
      if (Math.abs(actual[key] - expected[key]) > 0.8) errors.push(`Outer border ${key} mismatch.`);
    }
  }
  const title = map.get(FRAME_RULES.titleBlock.id);
  if (!title) errors.push("Bottom-right title block is missing.");
  if (nodes.length < 20 || nodes.length > 25) errors.push(`Expected 20-25 architecture nodes, found ${nodes.length}.`);
  if (layers.length !== 4) errors.push(`Expected 4 horizontal layers, found ${layers.length}.`);
  if (edges.length > ARCHITECTURE_LAYOUT_RULES.maxEdges) errors.push(`Too many architecture edges: ${edges.length}.`);
  const actualLayerLabels = layers.map((layer) => decodeLabel(layer["@_value"]).replace(/\n/g, " ")).sort();
  const expectedLayerLabels = [...ARCHITECTURE_LAYOUT_RULES.exactLayers].sort();
  if (JSON.stringify(actualLayerLabels) !== JSON.stringify(expectedLayerLabels)) {
    errors.push(`Layer labels changed. Expected exactly ${expectedLayerLabels.join(", ")}.`);
  }
  const actualNodeLabels = nodes.map((node) => decodeLabel(node["@_value"]).replace(/\n/g, " ")).sort();
  const expectedNodeLabels = [...ARCHITECTURE_LAYOUT_RULES.exactComponents].sort();
  if (JSON.stringify(actualNodeLabels) !== JSON.stringify(expectedNodeLabels)) {
    errors.push(`Component labels changed. Expected exactly the approved 24 architecture components.`);
  }
  for (const item of [...nodes, ...layers]) {
    if (overlaps(boxOf(item), metrics.forbiddenArea, 0)) errors.push(`${item["@_id"]} overlaps title block forbidden area.`);
  }
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      if (overlaps(boxOf(nodes[i]), boxOf(nodes[j]), 0)) errors.push(`Node overlap: ${nodes[i]["@_id"]} and ${nodes[j]["@_id"]}.`);
    }
  }
  const textOverflowErrors = [];
  for (const node of nodes) {
    const fit = estimateTextBox(node);
    if (fit.estimatedWidth > fit.usableWidth || fit.estimatedHeight > fit.usableHeight) {
      textOverflowErrors.push(`${node["@_id"]} text does not fit safely: width ${fit.estimatedWidth.toFixed(1)}/${fit.usableWidth.toFixed(1)}, height ${fit.estimatedHeight.toFixed(1)}/${fit.usableHeight.toFixed(1)}.`);
    }
  }
  errors.push(...textOverflowErrors);

  const labelSpellingErrors = [];
  const knownMisspellings = [
    [/\bDecsion\b/, "Decision"],
    [/\bBackend & Data Hu Layer\b/, "Backend & Data Hub Layer"],
    [/\bTemprature\b/, "Temperature"],
    [/\bControler\b/, "Controller"]
  ];
  for (const item of [...nodes, ...layers]) {
    const label = decodeLabel(item["@_value"]).replace(/\n/g, " ");
    for (const [pattern, good] of knownMisspellings) {
      if (pattern.test(label)) labelSpellingErrors.push(`${item["@_id"]} contains spelling error matching ${pattern}, expected "${good}".`);
    }
  }
  errors.push(...labelSpellingErrors);

  const shapeRatioErrors = [];
  for (const node of nodes) {
    const kind = nodeKind(node);
    const expectedRatio = ARCHITECTURE_LAYOUT_RULES.shapeRatios[kind];
    if (!expectedRatio) continue;
    const box = boxOf(node);
    const actualRatio = box.width / box.height;
    if (Math.abs(actualRatio - expectedRatio) > ARCHITECTURE_LAYOUT_RULES.ratioTolerance) {
      shapeRatioErrors.push(`${node["@_id"]} ratio ${actualRatio.toFixed(2)} differs from required ${expectedRatio.toFixed(2)}.`);
    }
  }
  errors.push(...shapeRatioErrors);

  const missingArchitectureEdges = [];
  for (const [from, to] of ARCHITECTURE_LAYOUT_RULES.mqttCenterRules.requiredAdjacentEdges) {
    if (!edgeKeySet.has(`${from}->${to}`)) missingArchitectureEdges.push(`Missing MQTT-centered edge ${from}->${to}.`);
  }
  for (const [from, to] of ARCHITECTURE_LAYOUT_RULES.edgeControllerRules.requiredAdjacentEdges) {
    if (!edgeKeySet.has(`${from}->${to}`)) missingArchitectureEdges.push(`Missing Edge Controller adjacency edge ${from}->${to}.`);
  }
  errors.push(...missingArchitectureEdges);

  const broker = map.get(`${PREFIX}${ARCHITECTURE_LAYOUT_RULES.mqttCenterRules.brokerId}`);
  const telemetry = map.get(`${PREFIX}telemetry_topic`);
  const params = map.get(`${PREFIX}params_topic`);
  const dataHub = map.get(`${PREFIX}data_hub`);
  const edgeController = map.get(`${PREFIX}${ARCHITECTURE_LAYOUT_RULES.edgeControllerRules.controllerId}`);
  if (broker && telemetry && params) {
    const bb = boxOf(broker);
    const tb = boxOf(telemetry);
    const pb = boxOf(params);
    if (!(tb.x < bb.x && bb.x < pb.x)) errors.push("MQTT Broker must be visually centered between Telemetry Topic and Params Topic.");
  }
  if (edgeController && dataHub) {
    const ec = boxOf(edgeController);
    const dh = boxOf(dataHub);
    if (Math.abs((ec.x + ec.width / 2) - (dh.x + dh.width / 2)) > 420) errors.push("Edge Controller and Java Data Hub should stay roughly vertically aligned to avoid long cross-layer routing.");
  }

  const allSegments = [];
  const longLineErrors = [];
  const titleCrossingErrors = [];
  const portCenterErrors = [];
  const alignmentErrors = [];
  const layerTitleZones = layers.map((layer) => {
    const box = boxOf(layer);
    const zone = ARCHITECTURE_LAYOUT_RULES.titleZone;
    return {
      id: String(layer["@_id"]),
      x: box.x + zone.xOffset,
      y: box.y + zone.yOffset,
      width: zone.width,
      height: zone.height
    };
  });
  for (const edge of edges) {
    const style = String(edge["@_style"] || "");
    if (!style.includes("orthogonalEdgeStyle") || style.includes("curved=1")) errors.push(`${edge["@_id"]} is not orthogonal.`);
    const stylePorts = parsePorts(style);
    const sourcePort = portNameFromPair(stylePorts.exitX, stylePorts.exitY);
    const targetPort = portNameFromPair(stylePorts.entryX, stylePorts.entryY);
    if (!sourcePort || !targetPort) {
      portCenterErrors.push(`${edge["@_id"]} does not use a side-center source/target port.`);
    }
    const points = edgePoints(edge, map);
    if (!points) {
      errors.push(`${edge["@_id"]} has unresolved endpoints.`);
      continue;
    }
    const source = map.get(String(edge["@_source"] || ""));
    const target = map.get(String(edge["@_target"] || ""));
    if (source && target && sourcePort && targetPort) {
      const expectedStart = centerPointForPort(boxOf(source), sourcePort);
      const expectedEnd = centerPointForPort(boxOf(target), targetPort);
      if (!pointAlmostEqual(points[0], expectedStart)) {
        portCenterErrors.push(`${edge["@_id"]} does not start at the exact ${sourcePort} center port.`);
      }
      if (!pointAlmostEqual(points[points.length - 1], expectedEnd)) {
        portCenterErrors.push(`${edge["@_id"]} does not end at the exact ${targetPort} center port.`);
      }
      if (points.length >= 2 && !segmentLeavesPort(points[0], points[1], sourcePort)) {
        portCenterErrors.push(`${edge["@_id"]} leaves ${sourcePort} port in the wrong direction.`);
      }
      if (points.length >= 2 && !segmentApproachesPort(points[points.length - 2], points[points.length - 1], targetPort)) {
        portCenterErrors.push(`${edge["@_id"]} approaches ${targetPort} port from the wrong direction.`);
      }
    }
    if (bendCount(points) > 1) errors.push(`${edge["@_id"]} has more than one bend.`);
    for (let i = 1; i < points.length; i += 1) {
      const a = points[i - 1];
      const b = points[i];
      const horizontalLength = Math.abs(a.x - b.x);
      const verticalLength = Math.abs(a.y - b.y);
      if (horizontalLength > allowedHorizontalSegmentLength(edge)) {
        longLineErrors.push(`${edge["@_id"]} horizontal segment is too long: ${horizontalLength.toFixed(1)} px.`);
      }
      if (verticalLength > ARCHITECTURE_LAYOUT_RULES.connection.maxVerticalSegmentLengthPx) {
        longLineErrors.push(`${edge["@_id"]} vertical segment is too long: ${verticalLength.toFixed(1)} px.`);
      }
      if (Math.abs(a.x - b.x) > 0.1 && Math.abs(a.y - b.y) > 0.1) errors.push(`${edge["@_id"]} has a diagonal segment.`);
      const box = segmentBox(a, b, 2);
      if (overlaps(box, metrics.forbiddenArea, 0)) errors.push(`${edge["@_id"]} enters title block forbidden area.`);
      for (const titleZone of layerTitleZones) {
        if (overlaps(box, titleZone, 0)) titleCrossingErrors.push(`${edge["@_id"]} crosses layer title zone ${titleZone.id}.`);
      }
      for (const node of nodes) {
        if (String(node["@_id"]) === String(edge["@_source"]) || String(node["@_id"]) === String(edge["@_target"])) continue;
        if (overlaps(box, boxOf(node), 0)) errors.push(`${edge["@_id"]} crosses node ${node["@_id"]}.`);
      }
      allSegments.push({ edge: String(edge["@_id"]), a, b });
    }
  }
  errors.push(...longLineErrors);
  errors.push(...titleCrossingErrors);
  errors.push(...portCenterErrors);

  const byId = (id) => map.get(`${PREFIX}${id}`);
  const checkVerticalAxis = (ids, name) => {
    const cellsForAxis = ids.map(byId).filter(Boolean);
    if (cellsForAxis.length !== ids.length) {
      alignmentErrors.push(`${name} cannot be validated because an axis component is missing.`);
      return;
    }
    const baseline = centerX(cellsForAxis[0]);
    for (const cell of cellsForAxis.slice(1)) {
      if (Math.abs(centerX(cell) - baseline) > ARCHITECTURE_LAYOUT_RULES.alignment.tolerancePx) {
        alignmentErrors.push(`${name} is not vertically aligned at ${cell["@_id"]}.`);
      }
    }
  };
  const checkRow = (ids, name) => {
    const rowCells = ids.map(byId).filter(Boolean);
    if (rowCells.length !== ids.length) {
      alignmentErrors.push(`${name} cannot be validated because a row component is missing.`);
      return;
    }
    const baseline = centerY(rowCells[0]);
    for (const cell of rowCells.slice(1)) {
      if (Math.abs(centerY(cell) - baseline) > ARCHITECTURE_LAYOUT_RULES.alignment.rowTolerancePx) {
        alignmentErrors.push(`${name} is not on one horizontal centerline at ${cell["@_id"]}.`);
      }
    }
  };
  const checkUniformSpacing = (ids, name) => {
    const rowCells = ids.map(byId).filter(Boolean);
    if (rowCells.length !== ids.length || rowCells.length < 3) return;
    const gaps = [];
    for (let i = 1; i < rowCells.length; i += 1) {
      gaps.push(boxOf(rowCells[i]).x - (boxOf(rowCells[i - 1]).x + boxOf(rowCells[i - 1]).width));
    }
    const average = gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length;
    for (const gap of gaps) {
      if (Math.abs(gap - average) > ARCHITECTURE_LAYOUT_RULES.alignment.spacingTolerancePx) {
        alignmentErrors.push(`${name} has non-uniform spacing: ${gaps.map((v) => v.toFixed(1)).join(", ")}.`);
        break;
      }
    }
  };
  checkVerticalAxis(ARCHITECTURE_LAYOUT_RULES.alignment.centralAxis, "Central Java Data Hub / MQTT Broker / Edge Controller axis");
  checkVerticalAxis(ARCHITECTURE_LAYOUT_RULES.alignment.commandAxis, "Right-side Param Publish / Command API / Param Topic axis");
  checkRow(ARCHITECTURE_LAYOUT_RULES.alignment.bottomControlChain, "Bottom control chain");
  checkUniformSpacing(ARCHITECTURE_LAYOUT_RULES.alignment.bottomControlChain, "Bottom control chain");
  checkRow(ARCHITECTURE_LAYOUT_RULES.alignment.communicationRow, "Communication layer row");
  checkRow(ARCHITECTURE_LAYOUT_RULES.alignment.topUpperRow, "Top HMI row");
  checkRow(ARCHITECTURE_LAYOUT_RULES.alignment.topLowerRow, "Top decision-support row");
  errors.push(...alignmentErrors);
  const crossings = [];
  for (let i = 0; i < allSegments.length; i += 1) {
    for (let j = i + 1; j < allSegments.length; j += 1) {
      const s1 = allSegments[i];
      const s2 = allSegments[j];
      if (s1.edge === s2.edge) continue;
      if (segmentsIntersect(s1.a, s1.b, s2.a, s2.b)) crossings.push(`${s1.edge} intersects ${s2.edge}`);
    }
  }
  if (crossings.length) errors.push(...crossings);
  if (metrics.coverageX < 0.70 || metrics.coverageY < 0.60) errors.push(`A1 coverage too low: ${metrics.coverageX.toFixed(3)} x ${metrics.coverageY.toFixed(3)}.`);
  const summary = {
    passed: errors.length === 0,
    nodeCount: nodes.length,
    layerCount: layers.length,
    edgeCount: edges.length,
    coverageX: metrics.coverageX,
    coverageY: metrics.coverageY,
    crossingLines: crossings,
    nodeCrossingErrors: errors.filter((e) => /crosses node/.test(e)),
    complexPolylineErrors: errors.filter((e) => /more than one bend|diagonal/.test(e)),
    titleBlockErrors: errors.filter((e) => /title block|forbidden/.test(e)),
    textOverflowErrors,
    labelSpellingErrors,
    shapeRatioErrors,
    missingArchitectureEdges,
    longLineErrors,
    titleCrossingErrors,
    portCenterErrors,
    alignmentErrors,
    mqttCentered: !errors.some((e) => /MQTT Broker/.test(e)),
    errors,
    warnings
  };
  fs.writeFileSync(SUMMARY, `${JSON.stringify(summary, null, 2)}\n`);
  fs.writeFileSync(REPORT, [
    "# Architecture Diagram Check Report",
    "",
    `Validation status: **${summary.passed ? "PASSED" : "FAILED"}**.`,
    "",
    "## Layer Meaning",
    "",
    "- HMI & Decision Support Layer: operator UI, live monitoring, alarms, learning, ranking, approval, and parameter publishing.",
    "- Backend & Data Hub Layer: API services, Java ingestion, validation, alarm rules, time-series writing, and storage.",
    "- Communication Layer: MQTT broker and project topics/channels for telemetry, alarms, and parameters.",
    "- Edge Control Layer: controller, sensing, filtering, PID control, PWM output, heater driver, chamber, and feedback.",
    "",
    "## Checks",
    "",
    `- Crossing lines: ${summary.crossingLines.length}`,
    `- Lines crossing nodes: ${summary.nodeCrossingErrors.length}`,
    `- Complex polylines or diagonal lines: ${summary.complexPolylineErrors.length}`,
    `- Title block / forbidden area errors: ${summary.titleBlockErrors.length}`,
    `- Text overflow / border overlap errors: ${summary.textOverflowErrors.length}`,
    `- Label spelling errors: ${summary.labelSpellingErrors.length}`,
    `- Shape ratio errors: ${summary.shapeRatioErrors.length}`,
    `- Missing architecture relationship edges: ${summary.missingArchitectureEdges.length}`,
    `- Overlong line segments: ${summary.longLineErrors.length}`,
    `- Layer title crossing errors: ${summary.titleCrossingErrors.length}`,
    `- Port center / approach-direction errors: ${summary.portCenterErrors.length}`,
    `- Required axis / row alignment errors: ${summary.alignmentErrors.length}`,
    `- MQTT centered in communication layer: ${summary.mqttCentered ? "yes" : "no"}`,
    `- A1 coverage: ${(summary.coverageX * 100).toFixed(1)}% x ${(summary.coverageY * 100).toFixed(1)}%`
  ].join("\n") + "\n");
  if (!summary.passed) {
    console.error(JSON.stringify(summary, null, 2));
    process.exit(1);
  }
  console.log("architecture diagram validator passed");
  console.log(`- nodes: ${summary.nodeCount}`);
  console.log(`- layers: ${summary.layerCount}`);
  console.log(`- edges: ${summary.edgeCount}`);
}

main();
