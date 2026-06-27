#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser } = require("fast-xml-parser");

const WORK_DIR = __dirname;
const MODEL_PATH = path.join(WORK_DIR, "gost_flow_model.json");
const DRAWIO_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");
const SUBFLOW_DIR = path.join(WORK_DIR, "subflows");
const SUMMARY_PATH = path.join(WORK_DIR, "validator_summary.json");
const REPORT_PATH = path.join(WORK_DIR, "compliance_report.md");
const AUDIT_JSON_PATH = path.join(WORK_DIR, "full_semantic_audit.json");
const AUDIT_MD_PATH = path.join(WORK_DIR, "full_semantic_audit.md");

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  preserveOrder: false,
  trimValues: false
});

const CONTENT_TITLE_PREFIX = "content_page_titleblock_";
const LEGACY_TITLE_PREFIX = "pFFQBGnBG81xobuCz_b_";
const DECOR_PREFIX = "repo_flow_decor_";
const TITLE_BLOCK_DRAWING_CODE = "БрГТУ.241297 - 05 90 00";
const TITLE_BLOCK_DRAWING_TITLE = "EdgeHub-Based Closed-Loop Temperature Control System Program diagram";
const TITLE_THICK_STROKE = 3.937;
const TITLE_THIN_STROKE = 1.9685;
const CONTENT_TITLE_BLOCK_GRID = {
  // Ratios measured from the thesis content-page lower table rendered from DOCX.
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

function boxOf(cell) {
  const g = cell.mxGeometry || {};
  return { x: attrNumber(g, "x"), y: attrNumber(g, "y"), width: attrNumber(g, "width"), height: attrNumber(g, "height") };
}

const symbolGeometry = {
  data: { skew: 34 }
};

const aspectRatioRules = {
  terminator: 170 / 70,
  process: 2,
  predefined_process: 2,
  data: 170 / 70,
  document: 170 / 70,
  display: 170 / 70,
  manual_input: 170 / 70,
  manual_operation: 2,
  stored_data: 1.5,
  decision: 1.5,
  connector: 1
};

const LABEL_OFFSET = 10;
const LABEL_OFFSET_TOLERANCE = 1.5;
const LABEL_BOX_GAP = 10;
const LABEL_BOX_GAP_TOLERANCE = 1.5;
const LABEL_HEIGHT = 26;
const NODE_TEXT_MARGIN = 10;
const SYMBOL_TEXT_SAFE_WIDTH = {
  decision: 0.78,
  manual_input: 0.86,
  data: 0.86,
  display: 0.86,
  document: 0.86,
  terminator: 0.86,
  stored_data: 0.86
};
const SYMBOL_TEXT_SAFE_HEIGHT = {
  decision: 0.84,
  manual_input: 0.92,
  data: 0.92,
  display: 0.92,
  document: 0.92,
  stored_data: 0.90,
  terminator: 0.92
};
const CONNECTION_LENGTH_TOLERANCE = 0.5;
const MIN_CONNECTION_TOTAL_FACTOR = 1;

function overlaps(a, b, pad = 0) {
  return !(
    a.x + a.width <= b.x - pad ||
    a.x >= b.x + b.width + pad ||
    a.y + a.height <= b.y - pad ||
    a.y >= b.y + b.height + pad
  );
}

function decodeText(text) {
  return String(text || "").replace(/<br\s*\/?>/gi, "\n").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&");
}

function addError(errors, code, detail) {
  errors.push({ code, detail });
}

function styleHas(cell, fragment) {
  return String(cell["@_style"] || "").includes(fragment);
}

function frameBox(page) {
  return {
    x: (20 / 841) * page.width,
    y: (5 / 594) * page.height,
    width: page.width - ((20 + 5) / 841) * page.width,
    height: page.height - ((5 + 5) / 594) * page.height
  };
}

function mmToPageX(mm, page) {
  return (mm / 841) * page.width;
}

function mmToPageY(mm, page) {
  return (mm / 594) * page.height;
}

function titleBlockBox(page) {
  const frame = frameBox(page);
  const width = mmToPageX(page.title_block?.width_mm || 185, page);
  const height = mmToPageY(page.title_block?.height_mm || 40, page);
  return {
    x: frame.x + frame.width - width,
    y: frame.y + frame.height - height,
    width,
    height
  };
}

function contentTitleLineDefinitions(page) {
  const box = titleBlockBox(page);
  const xs = CONTENT_TITLE_BLOCK_GRID.x.map((ratio) => box.x + box.width * ratio);
  const ys = CONTENT_TITLE_BLOCK_GRID.y.map((ratio) => box.y + box.height * ratio);
  const rs = CONTENT_TITLE_BLOCK_GRID.rightSubX.map((ratio) => box.x + box.width * ratio);
  const defs = [];
  const add = (id, x1, y1, x2, y2, strokeWidth) => defs.push({ id: `${CONTENT_TITLE_PREFIX}${id}`, x1, y1, x2, y2, strokeWidth });

  add("v0_outer_left", xs[0], ys[0], xs[0], ys[8], TITLE_THICK_STROKE);
  add("v1_left_grid", xs[1], ys[0], xs[1], ys[8], TITLE_THICK_STROKE);
  add("v2_left_grid", xs[2], ys[0], xs[2], ys[8], TITLE_THICK_STROKE);
  add("v3_left_grid", xs[3], ys[0], xs[3], ys[8], TITLE_THICK_STROKE);
  add("v4_left_grid", xs[4], ys[0], xs[4], ys[8], TITLE_THICK_STROKE);
  add("v5_left_mid_divider", xs[5], ys[0], xs[5], ys[8], TITLE_THICK_STROKE);
  add("v6_mid_right_divider", xs[6], ys[3], xs[6], ys[8], TITLE_THICK_STROKE);
  add("v7_right_page_divider", xs[7], ys[3], xs[7], ys[5], TITLE_THICK_STROKE);
  add("v8_right_pages_divider", xs[8], ys[3], xs[8], ys[5], TITLE_THICK_STROKE);
  add("v9_outer_right", xs[9], ys[0], xs[9], ys[8], TITLE_THICK_STROKE);
  add("rv1_right_small", rs[1], ys[4], rs[1], ys[5], TITLE_THIN_STROKE);
  add("rv2_right_small", rs[2], ys[4], rs[2], ys[5], TITLE_THIN_STROKE);
  add("h0_outer_top", xs[0], ys[0], xs[9], ys[0], TITLE_THICK_STROKE);
  add("h1_left_revision", xs[0], ys[1], xs[5], ys[1], TITLE_THIN_STROKE);
  add("h2_left_revision", xs[0], ys[2], xs[5], ys[2], TITLE_THICK_STROKE);
  add("h3_code_bottom", xs[0], ys[3], xs[9], ys[3], TITLE_THICK_STROKE);
  add("h4_left_signature", xs[0], ys[4], xs[5], ys[4], TITLE_THIN_STROKE);
  add("h4_right_page", xs[6], ys[4], xs[9], ys[4], TITLE_THICK_STROKE);
  add("h5_left_signature", xs[0], ys[5], xs[5], ys[5], TITLE_THICK_STROKE);
  add("h5_right_department", xs[6], ys[5], xs[9], ys[5], TITLE_THICK_STROKE);
  add("h6_left_blank", xs[0], ys[6], xs[5], ys[6], TITLE_THIN_STROKE);
  add("h7_left_blank", xs[0], ys[7], xs[5], ys[7], TITLE_THIN_STROKE);
  add("h8_outer_bottom", xs[0], ys[8], xs[9], ys[8], TITLE_THICK_STROKE);
  return defs;
}

function lineEndpoints(cell) {
  const points = asArray(cell.mxGeometry?.mxPoint);
  const source = points.find((point) => point["@_as"] === "sourcePoint") || points[0];
  const target = points.find((point) => point["@_as"] === "targetPoint") || points[points.length - 1];
  return {
    source: { x: attrNumber(source, "x"), y: attrNumber(source, "y") },
    target: { x: attrNumber(target, "x"), y: attrNumber(target, "y") }
  };
}

function strokeWidth(cell) {
  const match = String(cell["@_style"] || "").match(/(?:^|;)strokeWidth=([0-9.]+)/);
  return match ? Number(match[1]) : NaN;
}

function validateContentTitleBlock(cells, page, allText, errors) {
  const titleCells = cells.filter((cell) => String(cell["@_id"] || "").startsWith(CONTENT_TITLE_PREFIX));
  if (!titleCells.length) {
    addError(errors, "EDGE_FLOATING", "title block: missing content-page table cells");
    return;
  }

  const expectedBox = titleBlockBox(page);
  const background = cells.find((cell) => String(cell["@_id"] || "") === `${CONTENT_TITLE_PREFIX}background`);
  if (!background?.mxGeometry) {
    addError(errors, "EDGE_FLOATING", "title block: missing white background");
  } else {
    const box = boxOf(background);
    if (Math.abs(box.x - expectedBox.x) > 0.75 || Math.abs(box.y - expectedBox.y) > 0.75 ||
        Math.abs(box.width - expectedBox.width) > 0.75 || Math.abs(box.height - expectedBox.height) > 0.75) {
      addError(errors, "EDGE_FLOATING", "title block: background must stay 185mm x 40mm and aligned to the lower-right inner frame");
    }
  }

  for (const requiredText of [TITLE_BLOCK_DRAWING_CODE, TITLE_BLOCK_DRAWING_TITLE, "Author", "Supervisor", "Sign", "Date", "Page", "Pages", "Computer&Systems"]) {
    if (!allText.includes(requiredText)) addError(errors, "EDGE_FLOATING", `title block: missing ${requiredText}`);
  }
}

function fontSizeForNode(node) {
  if (node.gost_type === "decision" || node.gost_type === "stored_data") return 18;
  return 20;
}

function normalizedTextLines(node) {
  const explicit = String(node.rendered_label || "").split(/\n|<br\s*\/?>/).filter(Boolean);
  return explicit.length ? explicit : String(node.label || "").split(/\s+|\/+/).reduce((acc, token) => {
    if (!token) return acc;
    const last = acc[acc.length - 1] || "";
    if (!last || `${last} ${token}`.length > 14) acc.push(token);
    else acc[acc.length - 1] = `${last} ${token}`;
    return acc;
  }, []);
}

function textLineWidth(line, fontSize) {
  return [...String(line)].reduce((sum, ch) => {
    if (ch === " ") return sum + fontSize * 0.25;
    if (/[ijlI1|]/.test(ch)) return sum + fontSize * 0.26;
    if (/[mwMW]/.test(ch)) return sum + fontSize * 0.70;
    if (/[A-Z]/.test(ch)) return sum + fontSize * 0.54;
    if (/[a-z]/.test(ch)) return sum + fontSize * 0.46;
    if (/[0-9]/.test(ch)) return sum + fontSize * 0.48;
    if (/[-/?.,:;]/.test(ch)) return sum + fontSize * 0.30;
    return sum + fontSize * 0.50;
  }, 0);
}

function textSafetyForNode(node) {
  const lines = normalizedTextLines(node);
  const widthMargin = node.gost_type === "process" || node.gost_type === "manual_operation" ? 10 : NODE_TEXT_MARGIN;
  const heightMargin = node.gost_type === "process" || node.gost_type === "manual_operation" ? 8 : NODE_TEXT_MARGIN;
  const safeWidth = node.bbox.width * (SYMBOL_TEXT_SAFE_WIDTH[node.gost_type] || 1) - widthMargin * 2;
  const safeHeight = node.bbox.height * (SYMBOL_TEXT_SAFE_HEIGHT[node.gost_type] || 1) - heightMargin * 2;
  const fontSize = fontSizeForNode(node);
  const lineWidths = lines.map((line) => textLineWidth(line, fontSize));
  const approxWidth = Math.max(0, ...lineWidths);
  const approxHeight = Math.max(1, lines.length) * fontSize * 1.02;
  return {
    ok: approxWidth <= safeWidth && approxHeight <= safeHeight,
    lines,
    font_size: fontSize,
    estimated_width: Number(approxWidth.toFixed(2)),
    estimated_height: Number(approxHeight.toFixed(2)),
    safe_width: Number(safeWidth.toFixed(2)),
    safe_height: Number(safeHeight.toFixed(2)),
    width_margin: widthMargin,
    height_margin: heightMargin
  };
}

function textLikelyFits(node) {
  return textSafetyForNode(node).ok;
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

function expectedPortPoint(node, side) {
  const box = node.bbox;
  if (node.gost_type === "data" && (side === "west" || side === "east")) {
    const skewHalf = symbolGeometry.data.skew / 2;
    if (side === "west") return { x: box.x + skewHalf, y: box.y + box.height / 2 };
    if (side === "east") return { x: box.x + box.width - skewHalf, y: box.y + box.height / 2 };
  }
  if (side === "west") return { x: box.x, y: box.y + box.height / 2 };
  if (side === "east") return { x: box.x + box.width, y: box.y + box.height / 2 };
  if (side === "north") return { x: box.x + box.width / 2, y: box.y };
  if (side === "south") return { x: box.x + box.width / 2, y: box.y + box.height };
  return null;
}

function pointOnNodePort(point, node, side, tolerance = 1) {
  const expected = expectedPortPoint(node, side);
  if (!expected) return false;
  return Math.abs(point.x - expected.x) <= tolerance && Math.abs(point.y - expected.y) <= tolerance;
}

function segmentsIntersect(a, b, c, d) {
  const h1 = Math.abs(a.y - b.y) <= 0.1;
  const v1 = Math.abs(a.x - b.x) <= 0.1;
  const h2 = Math.abs(c.y - d.y) <= 0.1;
  const v2 = Math.abs(c.x - d.x) <= 0.1;
  if (h1 && v2) {
    return c.x > Math.min(a.x, b.x) && c.x < Math.max(a.x, b.x) && a.y > Math.min(c.y, d.y) && a.y < Math.max(c.y, d.y);
  }
  if (v1 && h2) {
    return a.x > Math.min(c.x, d.x) && a.x < Math.max(c.x, d.x) && c.y > Math.min(a.y, b.y) && c.y < Math.max(a.y, b.y);
  }
  return false;
}

function isAllowedBottomReturnMerge(aEdgeId, bEdgeId, model) {
  const mergeEdgeIds = new Set(model.layout_policy?.bottom_return_merge_edge_ids || []);
  return (aEdgeId === "m01" && mergeEdgeIds.has(bEdgeId)) ||
    (bEdgeId === "m01" && mergeEdgeIds.has(aEdgeId));
}

function collinearOverlapLength(a, b, c, d) {
  const h1 = Math.abs(a.y - b.y) <= 0.1;
  const v1 = Math.abs(a.x - b.x) <= 0.1;
  const h2 = Math.abs(c.y - d.y) <= 0.1;
  const v2 = Math.abs(c.x - d.x) <= 0.1;
  if (h1 && h2 && Math.abs(a.y - c.y) <= 0.1) {
    const start = Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x));
    const end = Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x));
    return Math.max(0, end - start);
  }
  if (v1 && v2 && Math.abs(a.x - c.x) <= 0.1) {
    const start = Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y));
    const end = Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y));
    return Math.max(0, end - start);
  }
  return 0;
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function segmentLength(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

function distancePointToSegment(point, a, b) {
  const horizontal = Math.abs(a.y - b.y) <= 0.1;
  const vertical = Math.abs(a.x - b.x) <= 0.1;
  if (horizontal && point.x >= Math.min(a.x, b.x) - 0.1 && point.x <= Math.max(a.x, b.x) + 0.1) {
    return Math.abs(point.y - a.y);
  }
  if (vertical && point.y >= Math.min(a.y, b.y) - 0.1 && point.y <= Math.max(a.y, b.y) + 0.1) {
    return Math.abs(point.x - a.x);
  }
  return Infinity;
}

function labelWidthFor(label) {
  return Math.max(52, String(label).length * 9 + 14);
}

function labelBoxFor(edge) {
  const width = labelWidthFor(edge.label);
  return {
    x: edge.label_position.x - width / 2,
    y: edge.label_position.y - LABEL_HEIGHT / 2,
    width,
    height: LABEL_HEIGHT
  };
}

function labelBoxGapToSegment(box, a, b) {
  const horizontal = Math.abs(a.y - b.y) <= 0.1;
  const vertical = Math.abs(a.x - b.x) <= 0.1;
  if (horizontal && box.x + box.width >= Math.min(a.x, b.x) - 0.1 && box.x <= Math.max(a.x, b.x) + 0.1) {
    if (box.y >= a.y) return box.y - a.y;
    if (box.y + box.height <= a.y) return a.y - (box.y + box.height);
    return 0;
  }
  if (vertical && box.y + box.height >= Math.min(a.y, b.y) - 0.1 && box.y <= Math.max(a.y, b.y) + 0.1) {
    if (box.x >= a.x) return box.x - a.x;
    if (box.x + box.width <= a.x) return a.x - (box.x + box.width);
    return 0;
  }
  return Infinity;
}

function pointInBox(point, box, pad = 0) {
  return point.x >= box.x - pad && point.x <= box.x + box.width + pad && point.y >= box.y - pad && point.y <= box.y + box.height + pad;
}

function routeHasNonStandardDirection(points) {
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1];
    const b = points[i];
    if (Math.abs(a.x - b.x) > 0.1 && b.x < a.x) return true;
    if (Math.abs(a.y - b.y) > 0.1 && b.y < a.y) return true;
  }
  return false;
}

function routeHasReverseSegment(points) {
  return points.slice(1).some((point, index) => {
    const previous = points[index];
    return (
      (Math.abs(previous.x - point.x) > 0.1 && point.x < previous.x) ||
      (Math.abs(previous.y - point.y) > 0.1 && point.y < previous.y)
    );
  });
}

function finalDirection(points) {
  const a = points[points.length - 2];
  const b = points[points.length - 1];
  if (Math.abs(a.x - b.x) > Math.abs(a.y - b.y)) return b.x > a.x ? "right" : "left";
  return b.y > a.y ? "down" : "up";
}

function routeTouchesDataSymbolEdge(edge, node, endpoint, port) {
  if (node.gost_type !== "data") return true;
  return pointOnNodePort(endpoint, node, port, 1);
}

function routeLength(points) {
  return points.slice(1).reduce((sum, point, index) => sum + segmentLength(points[index], point), 0);
}

function routeIsOrthogonal(points) {
  return points.slice(1).every((point, index) => {
    const previous = points[index];
    return Math.abs(previous.x - point.x) <= 0.1 || Math.abs(previous.y - point.y) <= 0.1;
  });
}

function reachableFrom(startId, edges) {
  return reachableFromWithContinuation(startId, edges, new Map());
}

function reachableFromWithContinuation(startId, edges, continuationGroups) {
  const outgoing = new Map();
  for (const edge of edges) {
    if (!outgoing.has(edge.from_node)) outgoing.set(edge.from_node, []);
    outgoing.get(edge.from_node).push(edge.to_node);
  }
  const seen = new Set();
  const queue = [startId];
  while (queue.length) {
    const id = queue.shift();
    if (seen.has(id)) continue;
    seen.add(id);
    for (const next of outgoing.get(id) || []) {
      if (!seen.has(next)) queue.push(next);
    }
    for (const next of continuationGroups.get(id) || []) {
      if (!seen.has(next)) queue.push(next);
    }
  }
  return seen;
}

function canReachEnd(endId, edges) {
  return canReachAny([endId], edges);
}

function canReachAny(targetIds, edges) {
  return canReachAnyWithContinuation(targetIds, edges, new Map());
}

function canReachAnyWithContinuation(targetIds, edges, continuationGroups) {
  const incoming = new Map();
  for (const edge of edges) {
    if (!incoming.has(edge.to_node)) incoming.set(edge.to_node, []);
    incoming.get(edge.to_node).push(edge.from_node);
  }
  const reverseContinuation = new Map();
  for (const [from, tos] of continuationGroups.entries()) {
    for (const to of tos) {
      if (!reverseContinuation.has(to)) reverseContinuation.set(to, []);
      reverseContinuation.get(to).push(from);
    }
  }
  const seen = new Set();
  const queue = [...targetIds];
  while (queue.length) {
    const id = queue.shift();
    if (seen.has(id)) continue;
    seen.add(id);
    for (const previous of incoming.get(id) || []) {
      if (!seen.has(previous)) queue.push(previous);
    }
    for (const previous of reverseContinuation.get(id) || []) {
      if (!seen.has(previous)) queue.push(previous);
    }
  }
  return seen;
}

function nearestLabelMetrics(edge) {
  if (!edge.label_position) return null;
  const labelBox = labelBoxFor(edge);
  const labelPoint = { x: edge.label_position.x, y: edge.label_position.y };
  const distanceToLine = edge.route_points.slice(1).reduce((best, point, index) => {
    return Math.min(best, distancePointToSegment(labelPoint, edge.route_points[index], point));
  }, Infinity);
  const boxGapToLine = edge.route_points.slice(1).reduce((best, point, index) => {
    return Math.min(best, labelBoxGapToSegment(labelBox, edge.route_points[index], point));
  }, Infinity);
  return {
    label_box: labelBox,
    center_distance_to_line: Number(distanceToLine.toFixed(2)),
    box_gap_to_line: Number(boxGapToLine.toFixed(2)),
    target_box_gap_px: LABEL_BOX_GAP,
    ok: Math.abs(boxGapToLine - LABEL_BOX_GAP) <= LABEL_BOX_GAP_TOLERANCE && distanceToLine >= LABEL_OFFSET - LABEL_OFFSET_TOLERANCE
  };
}

function buildSemanticAudit(model, errors, passes, alignmentChecks, mergeChecks, branchChecks, semanticChecks, cellsByNodeId = new Map()) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const nodes = model.nodes.map((node) => {
    const definition = model.symbol_definitions[node.gost_type] || {};
    return {
      id: node.id,
      label: node.label,
      rendered_label: node.rendered_label,
      gost_type: node.gost_type,
      gost_section: definition.gost_section,
      meaning: definition.meaning,
      bbox: node.bbox,
      ports: node.ports,
      allowed_input_sides: node.allowed_input_sides,
      allowed_output_sides: node.allowed_output_sides,
      expected_inputs: node.expected_inputs,
      expected_outputs: node.expected_outputs,
      actual_inputs: node.actual_inputs,
      actual_outputs: node.actual_outputs,
      text_safety: textSafetyForNode(node),
      subflow_ref: node.subflow_ref || null,
      notes: node.notes || ""
    };
  });
  const edges = model.edges.map((edge) => {
    const source = nodeById.get(edge.from_node);
    const target = nodeById.get(edge.to_node);
    const start = edge.route_points[0];
    const end = edge.route_points.at(-1);
    const sourceOnPort = source ? pointOnNodePort(start, source, edge.from_port) : false;
    const controlledBranch = (model.branch_groups || []).some((group) => (
      group.branch_edge_ids.includes(edge.id) &&
      group.source_node === edge.from_node &&
      edge.from_port === group.source_port
    ));
    const targetOnPort = target ? pointOnNodePort(end, target, edge.to_port) : false;
    return {
      id: edge.id,
      from_node: edge.from_node,
      from_label: source?.label,
      from_port: edge.from_port,
      to_node: edge.to_node,
      to_label: target?.label,
      to_port: edge.to_port,
      route_points: edge.route_points,
      length_px: Number(routeLength(edge.route_points).toFixed(2)),
      orthogonal: routeIsOrthogonal(edge.route_points),
      source_on_port: sourceOnPort,
      source_on_controlled_branch: controlledBranch,
      source_connection_ok: sourceOnPort || controlledBranch,
      target_on_port: targetOnPort,
      arrow_required: edge.arrow_required,
      final_direction: finalDirection(edge.route_points),
      label: edge.label,
      label_position: edge.label_position || null,
      label_metrics: nearestLabelMetrics(edge),
      flow_kind: edge.flow_kind,
      line_symbol: edge.line_symbol,
      line_style: edge.line_style,
      dashed: edge.line_style === "dashed",
      semantic_basis: edge.line_style_basis
    };
  });
  return {
    ok: errors.length === 0,
    generated_at: new Date().toISOString(),
    standard_basis: model.standard_basis,
    brstu: model.brstu,
    node_count: model.nodes.length,
    edge_count: model.edges.length,
    error_count: errors.length,
    errors,
    passes,
    nodes,
    edges,
    alignmentChecks,
    mergeChecks,
    branchChecks,
    semanticChecks
  };
}

function auditMarkdown(audit) {
  const failedNodes = audit.nodes.filter((node) => !node.text_safety.ok);
  const failedEdges = audit.edges.filter((edge) => !edge.orthogonal || !edge.source_connection_ok || !edge.target_on_port || edge.label_metrics?.ok === false);
  const lines = [
    "# Full Semantic Audit",
    "",
    `- Result: ${audit.ok ? "PASS" : "FAIL"}`,
    `- Nodes: ${audit.node_count}`,
    `- Edges: ${audit.edge_count}`,
    `- Standard: ${audit.standard_basis.gost}`,
    "",
    "## Node Audit",
    "| id | label | GOST type | section | inputs | outputs | text safe |",
    "|---|---|---|---|---:|---:|---|",
    ...audit.nodes.map((node) => `| ${node.id} | ${String(node.rendered_label || node.label).replace(/\n/g, " / ")} | ${node.gost_type} | ${node.gost_section || ""} | ${node.actual_inputs.length} | ${node.actual_outputs.length} | ${node.text_safety.ok ? "PASS" : `FAIL ${node.text_safety.estimated_width}x${node.text_safety.estimated_height}/${node.text_safety.safe_width}x${node.text_safety.safe_height}`} |`),
    "",
    "## Edge Audit",
    "| id | from | port | to | port | len | orthogonal | source | target | arrow | label gap |",
    "|---|---|---|---|---|---:|---|---|---|---|---|",
    ...audit.edges.map((edge) => `| ${edge.id} | ${edge.from_label || edge.from_node} | ${edge.from_port} | ${edge.to_label || edge.to_node} | ${edge.to_port} | ${edge.length_px} | ${edge.orthogonal ? "PASS" : "FAIL"} | ${edge.source_connection_ok ? "PASS" : "FAIL"} | ${edge.target_on_port ? "PASS" : "FAIL"} | ${edge.arrow_required ? "open" : "none"} | ${edge.label_metrics ? `${edge.label_metrics.ok ? "PASS" : "FAIL"} ${edge.label_metrics.box_gap_to_line}` : ""} |`),
    "",
    "## Focus Checks",
    ...audit.alignmentChecks.map((check) => `- ${check.label}: ${check.ok ? "PASS" : "FAIL"} (${check.orientation}, ${check.values.map((value) => Number(value).toFixed(1)).join(", ")})`),
    ...audit.mergeChecks.map((check) => `- ${check.id}: ${check.ok ? "PASS" : "FAIL"}`),
    ...audit.branchChecks.map((check) => `- ${check.id}: ${check.ok ? "PASS" : "FAIL"}`),
    "",
    "## Failures",
    ...(audit.errors.length ? audit.errors.map((error) => `- ${error.code}: ${error.detail}`) : ["- none"]),
    "",
    "## Text-Safety Failures",
    ...(failedNodes.length ? failedNodes.map((node) => `- ${node.id} ${node.label}: estimated ${node.text_safety.estimated_width}x${node.text_safety.estimated_height}, safe ${node.text_safety.safe_width}x${node.text_safety.safe_height}`) : ["- none"]),
    "",
    "## Edge Geometry Failures",
    ...(failedEdges.length ? failedEdges.map((edge) => `- ${edge.id}: orthogonal=${edge.orthogonal}, source=${edge.source_connection_ok}, target=${edge.target_on_port}, label=${edge.label_metrics?.ok ?? "n/a"}`) : ["- none"])
  ];
  return `${lines.join("\n")}\n`;
}

function addAlignmentCheck(errors, model, edgeIds, orientation, label) {
  const values = [];
  for (const edgeId of edgeIds) {
    const edge = model.edges.find((item) => item.id === edgeId);
    if (!edge) {
      addError(errors, "EDGE_FLOATING", `${label}: missing edge ${edgeId}`);
      continue;
    }
    const points = edge.route_points;
    if (orientation === "horizontal") {
      if (!points.every((point) => Math.abs(point.y - points[0].y) <= 1)) addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${edgeId}: horizontal chain has non-uniform y`);
      values.push(points[0].y);
    } else {
      if (!points.every((point) => Math.abs(point.x - points[0].x) <= 1)) addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${edgeId}: vertical chain has non-uniform x`);
      values.push(points[0].x);
    }
  }
  const reference = values[0];
  const ok = values.every((value) => Math.abs(value - reference) <= 1);
  if (!ok) {
    addError(
      errors,
      orientation === "horizontal" ? "HORIZONTAL_EDGE_Y_MISALIGNED" : "VERTICAL_EDGE_X_MISALIGNED",
      `${label}: alignment values ${values.map((value) => value.toFixed(3)).join(", ")}`
    );
  }
  return { label, orientation, values, ok };
}

function addMergeGroupCheck(errors, model, group) {
  const target = model.nodes.find((node) => node.id === group.target_node);
  if (!target) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing target node ${group.target_node}`);
    return { id: group.id, ok: false, detail: "missing target" };
  }
  const targetPort = target.ports?.[group.target_port];
  const merge = group.merge_point;
  const incoming = group.edge_ids.map((edgeId) => model.edges.find((edge) => edge.id === edgeId));
  let ok = true;
  if (incoming.some((edge) => !edge)) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing merge edge`);
    ok = false;
  }
  const validEdges = incoming.filter(Boolean);
  const sourceXs = [];
  const mainEdge = validEdges.find((edge) => edge.id === group.main_edge_id);
  if (group.style === "offset_side_merge" && !mainEdge) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing declared main edge ${group.main_edge_id}`);
    ok = false;
  }
  for (const edge of validEdges) {
    const points = edge.route_points;
    const source = model.nodes.find((node) => node.id === edge.from_node);
    const sourcePort = source?.ports?.[edge.from_port];
    if (!sourcePort || !targetPort) {
      addError(errors, "EDGE_FLOATING", `${group.id}/${edge.id}: missing source or target port`);
      ok = false;
      continue;
    }
    sourceXs.push(sourcePort.x);
    const isMain = edge.id === group.main_edge_id;
    if (!isMain && points.length !== 4) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edge.id}: merge route must have 4 points`);
      ok = false;
    }
    if (isMain && points.length < 2) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edge.id}: main merge route must have a vertical stem`);
      ok = false;
    }
    if (Math.abs(points[1]?.x - sourcePort.x) > 1 || Math.abs(points[1]?.y - merge.y) > 1) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edge.id}: first stem must drop vertically to merge lane`);
      ok = false;
    }
    if (!isMain && (Math.abs(points[2]?.y - merge.y) > 1 || Math.abs(points[2]?.x - merge.x) > 1)) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edge.id}: horizontal branch must end at merge point`);
      ok = false;
    }
    const last = points[points.length - 1];
    if (Math.abs(last?.x - targetPort.x) > 1 || Math.abs(last?.y - targetPort.y) > 1) {
      addError(errors, "EDGE_TARGET_NOT_ON_PORT", `${group.id}/${edge.id}: final stem must enter target port`);
      ok = false;
    }
    if (Math.abs(sourcePort.y - merge.y) < group.min_source_stem) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}/${edge.id}: connector stem is too short to show the center line`);
      ok = false;
    }
    if (Math.abs(targetPort.y - merge.y) < group.min_target_stem) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}/${edge.id}: merge lane is too close to target symbol`);
      ok = false;
    }
    if (group.style === "offset_side_merge") {
      if (isMain && Math.abs(sourcePort.x - merge.x) > 1) {
        addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}/${edge.id}: main merge line must share target center x`);
        ok = false;
      }
      if (!isMain && Math.abs(sourcePort.x - merge.x) < group.min_branch_offset) {
        addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}/${edge.id}: side branch must be offset from main vertical line`);
        ok = false;
      }
    }
  }
  const uniqueXs = [...new Set(sourceXs.map((value) => Math.round(value)))];
  if (uniqueXs.length < 2) {
    addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: merge branches must be visibly offset`);
    ok = false;
  }
  return { id: group.id, ok, merge_point: merge, edge_ids: group.edge_ids };
}

function addBranchGroupCheck(errors, model, group) {
  if (group.style === "stem_to_horizontal_bus") return addStemBusBranchGroupCheck(errors, model, group);
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const trunk = edgeById.get(group.trunk_edge_id);
  const source = nodeById.get(group.source_node);
  const target = nodeById.get(group.trunk_target_node);
  let ok = true;
  if (!trunk || !source || !target) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing trunk/source/target`);
    return { id: group.id, ok: false, detail: "missing trunk/source/target" };
  }
  const sourcePortPoint = source.ports[group.source_port];
  const targetPortPoint = target.ports?.[group.trunk_target_port || "north"];
  const trunkIsHorizontal = sourcePortPoint && targetPortPoint && Math.abs(sourcePortPoint.y - targetPortPoint.y) <= 1;
  if (trunkIsHorizontal) return addHorizontalBranchGroupCheck(errors, model, group);
  const trunkX = source.ports[group.source_port]?.x;
  const trunkStart = source.ports[group.source_port];
  const trunkEnd = target.ports?.[group.trunk_target_port || "north"];
  if (!trunkStart || !trunkEnd || Math.abs(trunk.route_points[0].x - trunkX) > 1 || Math.abs(trunk.route_points.at(-1).x - trunkX) > 1) {
    addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: trunk is not on source centerline`);
    ok = false;
  }
  for (let i = 1; i < trunk.route_points.length; i += 1) {
    if (Math.abs(trunk.route_points[i].x - trunkX) > 1) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: trunk route is not a straight centerline`);
      ok = false;
    }
  }
  const branchPoints = [];
  for (const edgeId of group.branch_edge_ids) {
    const edge = edgeById.get(edgeId);
    if (!edge || ![2, 3].includes(edge.route_points.length)) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: branch must be a straight or one-bend segment from trunk to target`);
      ok = false;
      continue;
    }
    const start = edge.route_points[0];
    const end = edge.route_points[1];
    if (Math.abs(start.x - trunkX) > 1) {
      addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${group.id}/${edgeId}: branch start is not on trunk centerline`);
      ok = false;
    }
    if (start.y <= Math.min(trunkStart.y, trunkEnd.y) + 1 || start.y >= Math.max(trunkStart.y, trunkEnd.y) - 1) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}/${edgeId}: branch point must be inside the trunk span`);
      ok = false;
    }
    if (!["north", "west"].includes(edge.to_port)) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${group.id}/${edgeId}: branch target must enter from north or west per GOST 4.2.4`);
      ok = false;
    }
    if (edge.route_points.length === 2) {
      if (Math.abs(start.y - edge.route_points[1].y) > 1) {
        addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}/${edgeId}: straight branch must be horizontal`);
        ok = false;
      }
    } else {
      const bend = edge.route_points[1];
      const final = edge.route_points[2];
      if (Math.abs(start.y - bend.y) > 1 || Math.abs(bend.x - final.x) > 1) {
        addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: one-bend branch must run horizontal then vertical into the target`);
        ok = false;
      }
    }
    branchPoints.push(start);
  }
  for (let i = 1; i < branchPoints.length; i += 1) {
    if (Math.abs(branchPoints[i].y - branchPoints[i - 1].y) < group.min_branch_spacing) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}: branch points must be separated by at least ${group.min_branch_spacing}px`);
      ok = false;
    }
  }
  return { id: group.id, ok, trunk_edge_id: group.trunk_edge_id, branch_edge_ids: group.branch_edge_ids };
}

function addStemBusBranchGroupCheck(errors, model, group) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const trunk = edgeById.get(group.trunk_edge_id);
  const source = nodeById.get(group.source_node);
  const target = nodeById.get(group.trunk_target_node);
  let ok = true;
  if (!trunk || !source || !target) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing stem bus trunk/source/target`);
    return { id: group.id, ok: false, detail: "missing trunk/source/target" };
  }
  const sourcePort = source.ports[group.source_port];
  const targetPortName = group.trunk_target_port || "west";
  const targetPort = target.ports[targetPortName];
  const points = trunk.route_points;
  const busY = group.bus_y;
  if (!sourcePort || !targetPort || points.length < 3) {
    addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}: trunk must be Start stem and final C point on the distribution bus`);
    ok = false;
  } else {
    if (Math.abs(points[0].x - sourcePort.x) > 1 || Math.abs(points[0].y - sourcePort.y) > 1) {
      addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${group.id}: trunk must begin at Start south port`);
      ok = false;
    }
    if (Math.abs(points[1].x - sourcePort.x) > 1 || Math.abs(points[1].y - busY) > 1) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: Start stem must drop vertically to distribution bus y=${busY}`);
      ok = false;
    }
    if (targetPortName === "north") {
      if (group.bus_left_x >= sourcePort.x - 1) {
        addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: controlled left bus segment must extend to the left of Start`);
        ok = false;
      }
    } else if (points.length > 3) {
      if (Math.abs(points[2].y - busY) > 1 || Math.abs(points[2].x - group.bus_left_x) > 1) {
        addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: trunk must include the left end of the distribution bus when drawn as a single polyline`);
        ok = false;
      }
    } else if (group.bus_left_x >= sourcePort.x - 1) {
      addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: controlled left bus segment must extend to the left of Start`);
      ok = false;
    }
    const last = points.at(-1);
    if (Math.abs(last.x - targetPort.x) > 1 || Math.abs(last.y - targetPort.y) > 1) {
      addError(errors, "EDGE_TARGET_NOT_ON_PORT", `${group.id}: distribution bus must end at the declared End-before C port`);
      ok = false;
    }
	    if (targetPortName === "north") {
	      const bottomY = group.bottom_return_bus_y;
	      const returnLaneX = group.return_lane_x ?? group.bus_right_x;
	      if (Number.isFinite(bottomY)) {
	        if (points.length !== 6) {
	          addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}: trunk must be Start stem, top distribution bus, right return lane, bottom return bus, and final C drop`);
	          ok = false;
	        }
	        const topBusRight = points[2];
	        const returnDrop = points[3];
	        const bottomReturnEnd = points[4];
	        if (Math.abs(topBusRight.x - returnLaneX) > 1 || Math.abs(topBusRight.y - busY) > 1) {
	          addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: top bus must reach the declared right return lane x=${returnLaneX}`);
	          ok = false;
	        }
	        if (Math.abs(returnDrop.x - returnLaneX) > 1 || Math.abs(returnDrop.y - bottomY) > 1) {
	          addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: right return lane must drop vertically to bottom return y=${bottomY}`);
	          ok = false;
	        }
	        if (Math.abs(bottomReturnEnd.x - targetPort.x) > 1 || Math.abs(bottomReturnEnd.y - bottomY) > 1) {
	          addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: bottom return bus must arrive directly above final C.north`);
	          ok = false;
	        }
	        if (targetPort.y <= bottomY + 1) {
	          addError(errors, "EDGE_WRONG_DIRECTION", `${group.id}: final C must hang below the bottom return bus`);
	          ok = false;
	        }
	      } else {
	        if (points.length !== 4) {
	          addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}: final connector must hang below the distribution bus using one vertical drop`);
	          ok = false;
	        }
	        const busEnd = points[points.length - 2];
	        if (Math.abs(busEnd.y - busY) > 1 || Math.abs(busEnd.x - targetPort.x) > 1) {
	          addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}: final C drop must start on the bus directly above C.north`);
	          ok = false;
	        }
	        if (targetPort.y <= busY + 1) {
	          addError(errors, "EDGE_WRONG_DIRECTION", `${group.id}: final C must be below the bus, not on the bus endpoint`);
	          ok = false;
	        }
	        for (let i = 1; i < points.length - 1; i += 1) {
	          if (Math.abs(points[i].y - busY) > 1) {
	            addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: distribution bus segment after the Start stem must stay horizontal before the final C drop`);
	            ok = false;
	          }
	        }
	      }
    } else {
      for (let i = 1; i < points.length; i += 1) {
        if (Math.abs(points[i].y - busY) > 1) {
          addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: distribution bus segment after the Start stem must stay horizontal`);
          ok = false;
        }
      }
    }
  }
	  const minX = group.bus_left_x;
	  const maxX = group.bus_right_x ?? targetPort?.x;
  const branchXs = [];
  for (const edgeId of group.branch_edge_ids) {
    const edge = edgeById.get(edgeId);
    if (!edge) {
      addError(errors, "EDGE_FLOATING", `${group.id}/${edgeId}: missing branch edge`);
      ok = false;
      continue;
    }
    const branchTarget = nodeById.get(edge.to_node);
    const targetNorth = branchTarget?.ports?.north;
    const start = edge.route_points[0];
    const end = edge.route_points.at(-1);
    if (!targetNorth || edge.route_points.length !== 2) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: bus branch must be a single vertical line into target north port`);
      ok = false;
      continue;
    }
    if (Math.abs(start.y - busY) > 1) {
      addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${group.id}/${edgeId}: branch must start on horizontal distribution bus`);
      ok = false;
    }
    if (start.x < minX - 1 || start.x > maxX + 1) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}/${edgeId}: branch x=${start.x.toFixed(1)} is outside bus span`);
      ok = false;
    }
    if (Math.abs(start.x - targetNorth.x) > 1 || Math.abs(end.x - targetNorth.x) > 1 || Math.abs(end.y - targetNorth.y) > 1) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${group.id}/${edgeId}: branch must descend vertically into target north port`);
      ok = false;
    }
    if (start.y >= end.y - 1) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${group.id}/${edgeId}: branch must run downward from bus to target`);
      ok = false;
    }
    branchXs.push(start.x);
  }
  branchXs.sort((a, b) => a - b);
  for (let i = 1; i < branchXs.length; i += 1) {
    if (branchXs[i] - branchXs[i - 1] < group.min_branch_spacing) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}: branch x points must be separated by at least ${group.min_branch_spacing}px`);
      ok = false;
    }
  }
  return { id: group.id, ok, style: group.style, trunk_edge_id: group.trunk_edge_id, branch_edge_ids: group.branch_edge_ids };
}

function addBranchColumnLayoutCheck(errors, model) {
  const policy = model.layout_policy || {};
  const columns = model.branch_columns || [];
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const checks = [];
  let ok = true;

  const minCount = policy.branch_count_min ?? 0;
  if (columns.length < minCount) {
    addError(errors, "EDGE_FLOATING", `layout: visual branch count ${columns.length} is below required ${minCount}`);
    ok = false;
  }
  if (Number.isFinite(policy.branch_count_exact) && columns.length !== policy.branch_count_exact) {
    addError(errors, "EDGE_FLOATING", `layout: visual branch count must be exactly ${policy.branch_count_exact}, got ${columns.length}`);
    ok = false;
  }

  const sortedColumns = [...columns].sort((a, b) => a.x - b.x);
  if (sortedColumns.length > 1) {
    const expectedSpacing = policy.branch_x_spacing;
    const spacingTolerance = policy.branch_x_spacing_tolerance ?? 1;
    const spacings = sortedColumns.slice(1).map((column, index) => column.x - sortedColumns[index].x);
    const referenceSpacing = Number.isFinite(expectedSpacing) ? expectedSpacing : spacings[0];
    const spacingOk = spacings.every((spacing) => Math.abs(spacing - referenceSpacing) <= spacingTolerance);
    if (!spacingOk) {
      addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `layout: branch x spacing must be uniform ${referenceSpacing}px, got ${spacings.map((value) => value.toFixed(1)).join(", ")}`);
      ok = false;
    }
    const center = (sortedColumns[0].x + sortedColumns.at(-1).x) / 2;
    const centerTolerance = policy.branch_center_tolerance ?? 1;
    if (Number.isFinite(policy.start_center_x) && Math.abs(center - policy.start_center_x) > centerTolerance) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `layout: branch group center ${center.toFixed(1)} must align with Start center ${policy.start_center_x}`);
      ok = false;
    }
    checks.push({
      id: "branch_equal_spacing",
      ok: spacingOk,
      x_values: sortedColumns.map((column) => column.x),
      spacings: spacings.map((value) => Number(value.toFixed(3))),
      target_spacing: referenceSpacing,
      center: Number(center.toFixed(3))
    });
  }

  if (policy.branch_balance_required) {
    const left = columns.filter((column) => column.side === "left").length;
    const right = columns.filter((column) => column.side === "right").length;
    if (left !== right) {
      addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `layout: left/right branch count must match, got ${left}/${right}`);
      ok = false;
    }
    checks.push({ id: "branch_balance", ok: left === right, left, right });
  }

  const targetBottomY = policy.branch_bottom_y;
  const bottomTolerance = policy.branch_bottom_tolerance ?? 1;
  const minBottomY = policy.branch_connector_min_y;
  const maxBottomY = policy.branch_connector_max_y;
  const globalConnectionGap = policy.branch_global_connection_gap;
  const gapTolerance = policy.branch_connection_gap_tolerance ?? policy.branch_internal_gap_tolerance ?? 1;
  const branchEdges = new Set((model.layout_policy?.vertical_branch_edge_ids || []));

  for (const column of columns) {
    const connector = nodeById.get(column.connector_id);
    const firstNode = nodeById.get(column.first_node_id);
    if (!connector || !firstNode) {
      addError(errors, "EDGE_FLOATING", `${column.id}: missing first node or connector`);
      ok = false;
      checks.push({ id: column.id, ok: false, detail: "missing node" });
      continue;
    }
    const connectorCenterY = connector.bbox.y + connector.bbox.height / 2;
    const connectorCenterX = connector.bbox.x + connector.bbox.width / 2;
    let columnOk = true;
    if (Math.abs(connectorCenterX - column.x) > 1) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${column.id}: connector C center x must equal declared branch x`);
      ok = false;
      columnOk = false;
    }
    if (Number.isFinite(targetBottomY) && Math.abs(connectorCenterY - targetBottomY) > bottomTolerance) {
      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${column.id}: bottom C must align at y=${targetBottomY}`);
      ok = false;
      columnOk = false;
    }
    if (Number.isFinite(minBottomY) && connectorCenterY < minBottomY) {
      addError(errors, "EDGE_GAP_TO_NODE", `${column.id}: bottom C y=${connectorCenterY.toFixed(1)} is too high; must be >= ${minBottomY}`);
      ok = false;
      columnOk = false;
    }
    if (Number.isFinite(maxBottomY) && connectorCenterY > maxBottomY) {
      addError(errors, "EDGE_GAP_TO_NODE", `${column.id}: bottom C y=${connectorCenterY.toFixed(1)} is too low; must be <= ${maxBottomY}`);
      ok = false;
      columnOk = false;
    }

    const chainEdges = [];
    if (column.bus_edge_id) {
      const busEdge = edgeById.get(column.bus_edge_id);
      if (busEdge) chainEdges.push(busEdge);
      else {
        addError(errors, "EDGE_FLOATING", `${column.id}: missing bus edge ${column.bus_edge_id}`);
        ok = false;
        columnOk = false;
      }
    }
    let currentId = column.first_node_id;
    const visited = new Set();
    while (!visited.has(currentId) && currentId !== column.connector_id) {
      visited.add(currentId);
      const outgoing = model.edges.filter((edge) => (
        edge.from_node === currentId &&
        edge.to_node !== currentId &&
        branchEdges.has(edge.id) &&
        Math.abs((nodeById.get(edge.from_node)?.ports?.south?.x ?? NaN) - column.x) <= 1
      ));
      if (outgoing.length !== 1) break;
      chainEdges.push(outgoing[0]);
      currentId = outgoing[0].to_node;
    }

    const lengths = chainEdges.map((edge) => {
      const route = edgeById.get(edge.id)?.route_points || edge.route_points || [];
      return route.slice(1).reduce((sum, point, index) => sum + segmentLength(route[index], point), 0);
    });
	    const requiredConnectionGap = Number.isFinite(column.connection_gap) ? column.connection_gap : globalConnectionGap;
	    if (Number.isFinite(requiredConnectionGap)) {
	      lengths.forEach((length, index) => {
	        if (Math.abs(length - requiredConnectionGap) > gapTolerance) {
	          addError(errors, "EDGE_GAP_TO_NODE", `${column.id}/${chainEdges[index]?.id}: vertical input/output segment length must be ${requiredConnectionGap}px, got ${length.toFixed(1)}px`);
	          ok = false;
	          columnOk = false;
	        }
      });
    }
    if (lengths.length > 1) {
      const min = Math.min(...lengths);
      const max = Math.max(...lengths);
      if (max - min > gapTolerance) {
        addError(errors, "EDGE_GAP_TO_NODE", `${column.id}: internal vertical connection lengths must be uniform, got ${lengths.map((value) => value.toFixed(1)).join(", ")}`);
        ok = false;
        columnOk = false;
      }
    }
    checks.push({
      id: column.id,
      side: column.side,
      x: column.x,
      ok: columnOk,
      connector_y: Number(connectorCenterY.toFixed(3)),
      chain_edge_count: chainEdges.length,
      internal_lengths: lengths.map((value) => Number(value.toFixed(2)))
    });
  }

  return { id: "branch_column_layout", ok, checks };
}

function addHorizontalBranchGroupCheck(errors, model, group) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const trunk = edgeById.get(group.trunk_edge_id);
  const source = nodeById.get(group.source_node);
  const target = nodeById.get(group.trunk_target_node);
  let ok = true;
  const trunkY = source.ports[group.source_port]?.y;
  const trunkStart = source.ports[group.source_port];
  const trunkEnd = target.ports?.[group.trunk_target_port || "west"];
  if (!trunk || !source || !target || !trunkStart || !trunkEnd) {
    addError(errors, "EDGE_FLOATING", `${group.id}: missing horizontal trunk/source/target`);
    return { id: group.id, ok: false, detail: "missing horizontal trunk/source/target" };
  }
  if (Math.abs(trunk.route_points[0].y - trunkY) > 1 || Math.abs(trunk.route_points.at(-1).y - trunkY) > 1) {
    addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: trunk is not on source centerline`);
    ok = false;
  }
  for (let i = 1; i < trunk.route_points.length; i += 1) {
    if (Math.abs(trunk.route_points[i].y - trunkY) > 1) {
      addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${group.id}: trunk route is not a straight centerline`);
      ok = false;
    }
  }
  const minX = Math.min(trunkStart.x, trunkEnd.x);
  const maxX = Math.max(trunkStart.x, trunkEnd.x);
  const branchPoints = [];
  for (const edgeId of group.branch_edge_ids) {
    const edge = edgeById.get(edgeId);
    if (!edge || ![2, 3].includes(edge.route_points.length)) {
      addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: branch must be a straight or one-bend segment from horizontal trunk to target`);
      ok = false;
      continue;
    }
    const start = edge.route_points[0];
    if (Math.abs(start.y - trunkY) > 1) {
      addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${group.id}/${edgeId}: branch start is not on horizontal trunk centerline`);
      ok = false;
    }
    if (start.x <= minX + 1 || start.x >= maxX - 1) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}/${edgeId}: branch point must be inside the horizontal trunk span`);
      ok = false;
    }
    if (!["north", "west"].includes(edge.to_port)) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${group.id}/${edgeId}: branch target must enter from north or west per GOST 4.2.4`);
      ok = false;
    }
    if (edge.route_points.length === 2) {
      if (Math.abs(start.x - edge.route_points[1].x) > 1 && Math.abs(start.y - edge.route_points[1].y) > 1) {
        addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: straight branch must be horizontal or vertical`);
        ok = false;
      }
    } else {
      const bend = edge.route_points[1];
      const final = edge.route_points[2];
      if (Math.abs(start.x - bend.x) > 1 || Math.abs(bend.y - final.y) > 1) {
        addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${group.id}/${edgeId}: one-bend branch must run vertical then horizontal into the target`);
        ok = false;
      }
    }
    branchPoints.push(start);
  }
  for (let i = 1; i < branchPoints.length; i += 1) {
    if (Math.abs(branchPoints[i].x - branchPoints[i - 1].x) < group.min_branch_spacing) {
      addError(errors, "EDGE_GAP_TO_NODE", `${group.id}: branch points must be separated by at least ${group.min_branch_spacing}px`);
      ok = false;
    }
  }
  return { id: group.id, ok, trunk_edge_id: group.trunk_edge_id, branch_edge_ids: group.branch_edge_ids };
}

function loadDrawio(file) {
  const xml = fs.readFileSync(file, "utf8");
  const doc = parser.parse(xml);
  const diagram = asArray(doc.mxfile.diagram)[0];
  return asArray(diagram.mxGraphModel.root.mxCell);
}

function loadDrawioDiagrams(file) {
  const xml = fs.readFileSync(file, "utf8");
  const doc = parser.parse(xml);
  return asArray(doc.mxfile.diagram);
}

function validate() {
  const errors = [];
  const passes = [];
  const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  const allowedTypes = new Set(Object.keys(model.symbol_definitions));
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));

  for (const node of model.nodes) {
    if (!allowedTypes.has(node.gost_type)) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `${node.id}: unknown gost_type ${node.gost_type}`);
    if (!node.bbox || !Number.isFinite(node.bbox.x)) addError(errors, "EDGE_FLOATING", `${node.id}: missing bbox`);
    if (!Array.isArray(node.allowed_input_sides) || !Array.isArray(node.allowed_output_sides)) addError(errors, "EDGE_FLOATING", `${node.id}: missing allowed sides`);
    if (!Array.isArray(node.actual_inputs) || !Array.isArray(node.actual_outputs)) addError(errors, "EDGE_FLOATING", `${node.id}: missing actual input/output edge lists`);
    const constraints = model.symbol_definitions[node.gost_type]?.constraints || {};
    if (constraints.min_inputs != null && node.actual_inputs.length < constraints.min_inputs) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: has too few inputs for ${node.gost_type}`);
    if (constraints.max_inputs != null && node.actual_inputs.length > constraints.max_inputs) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: has too many inputs for ${node.gost_type}`);
    if (constraints.min_outputs != null && node.actual_outputs.length < constraints.min_outputs) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: has too few outputs for ${node.gost_type}`);
    if (constraints.max_outputs != null && node.actual_outputs.length > constraints.max_outputs) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: has too many outputs for ${node.gost_type}`);
    if (node.gost_type === "predefined_process") addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: predefined_process/function-block shape is disabled for this simplified drawing`);
  }
  for (const node of model.nodes.filter((item) => item.gost_type === "decision" && String(item.label).includes("?"))) {
    const outgoingLabels = node.actual_outputs.map((edgeId) => String(edgeById.get(edgeId)?.label || "").trim());
    for (const label of outgoingLabels) {
      if (!["Yes", "No"].includes(label)) {
        addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: question decision output labels must be Yes/No only, got "${label || "(empty)"}"`);
      }
    }
    if (!outgoingLabels.includes("Yes") || !outgoingLabels.includes("No")) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: question decision must include both Yes and No output labels`);
    }
  }
  passes.push("All nodes declare legal GOST types, bbox, side rules and machine I/O constraints.");

  const layoutPolicy = model.layout_policy || {};
  const startNodes = model.nodes.filter((node) => node.gost_type === "terminator" && node.label === "Start");
  const endNodes = model.nodes.filter((node) => node.gost_type === "terminator" && node.label === "End");
  const connectorNodes = model.nodes.filter((item) => item.gost_type === "connector");
  const connectorGroupLabel = layoutPolicy.connector_group_label || layoutPolicy.final_connector_label;
  const connectorExitId = layoutPolicy.connector_exit_id || layoutPolicy.final_connector_id;
  const continuationTargets = connectorNodes
    .filter((node) => node.label === connectorGroupLabel)
    .map((node) => node.id);
  const continuationGroups = new Map();
  if (connectorGroupLabel && connectorExitId) {
    for (const connector of connectorNodes.filter((node) => node.label === connectorGroupLabel && node.id !== connectorExitId)) {
      continuationGroups.set(connector.id, [connectorExitId]);
    }
  }
  if (startNodes.length !== 1) addError(errors, "EDGE_WRONG_DIRECTION", `layout: expected exactly one Start terminator, found ${startNodes.length}`);
  if (endNodes.length !== 1) addError(errors, "EDGE_WRONG_DIRECTION", `layout: expected exactly one End terminator, found ${endNodes.length}`);
  if (startNodes[0] && (startNodes[0].actual_inputs.length !== 0 || startNodes[0].actual_outputs.length !== 1)) {
    addError(errors, "EDGE_WRONG_DIRECTION", "Start must have 0 inputs and 1 output");
  }
	  if (endNodes[0] && (endNodes[0].actual_inputs.length !== 1 || endNodes[0].actual_outputs.length !== 0)) {
	    addError(errors, "EDGE_WRONG_DIRECTION", "End must have 1 input and 0 outputs");
	  }
	  if (layoutPolicy.end_start_alignment_required && startNodes[0] && endNodes[0]) {
	    const startCenterX = startNodes[0].bbox.x + startNodes[0].bbox.width / 2;
	    const endCenterX = endNodes[0].bbox.x + endNodes[0].bbox.width / 2;
	    const tolerance = layoutPolicy.end_start_alignment_tolerance ?? 1;
	    if (Math.abs(startCenterX - endCenterX) > tolerance) {
	      addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `layout: End center x=${endCenterX.toFixed(1)} must align with Start center x=${startCenterX.toFixed(1)}`);
	    }
	  }
	  for (const forbidden of layoutPolicy.forbidden_labels || []) {
    if (model.nodes.some((node) => node.label === forbidden || node.rendered_label === forbidden)) {
      addError(errors, "EDGE_WRONG_DIRECTION", `layout: forbidden deleted element remains: ${forbidden}`);
    }
  }
  for (const forbiddenType of layoutPolicy.forbidden_gost_types || []) {
    const offenders = model.nodes.filter((node) => node.gost_type === forbiddenType).map((node) => node.id);
    if (offenders.length) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `layout: forbidden gost_type ${forbiddenType} remains on ${offenders.join(", ")}`);
  }
  const reachable = startNodes[0] ? reachableFromWithContinuation(startNodes[0].id, model.edges, continuationGroups) : new Set();
  const reachesEnd = endNodes[0] ? canReachAnyWithContinuation([endNodes[0].id], model.edges, continuationGroups) : new Set();
  for (const node of model.nodes) {
    if (startNodes[0] && !reachable.has(node.id)) addError(errors, "EDGE_FLOATING", `${node.id}: not reachable from Start`);
    if (endNodes[0] && !reachesEnd.has(node.id)) addError(errors, "EDGE_FLOATING", `${node.id}: does not reach End or a declared continuation connector`);
    const isContinuationTerminal = node.gost_type === "connector" && node.label === connectorGroupLabel && node.id !== connectorExitId;
    if (node.id !== layoutPolicy.end_node_id && !isContinuationTerminal && node.actual_outputs.length === 0) addError(errors, "EDGE_FLOATING", `${node.id}: non-End node has no exit toward final merge or continuation connector`);
  }
  if (layoutPolicy.main_axis_node_ids?.length) {
    for (const id of layoutPolicy.main_axis_node_ids) {
      const node = nodeById.get(id);
      if (!node) {
        addError(errors, "EDGE_FLOATING", `layout: missing main-axis node ${id}`);
        continue;
      }
      const centerX = node.bbox.x + node.bbox.width / 2;
      const centerY = node.bbox.y + node.bbox.height / 2;
      if (layoutPolicy.main_axis_orientation === "horizontal") {
        if (Math.abs(centerY - layoutPolicy.main_axis_y) > 1) {
          addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `${id}: center is not on the required horizontal main trunk`);
        }
      } else if (Math.abs(centerX - layoutPolicy.main_axis_x) > 1) {
        addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `${id}: center is not on the required vertical main axis`);
      }
    }
  }
  passes.push("Single Start/End, deleted elements, no database-symbol nodes, graph connectivity and trunk-axis policy checked.");

  for (const node of model.nodes.filter((item) => item.gost_type === "decision")) {
    if (node.actual_inputs.length !== 1) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: decision must have exactly one input`);
    if (node.actual_outputs.length < 2) addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: decision must have at least two outputs`);
    for (const edgeId of node.actual_outputs) {
      const edge = edgeById.get(edgeId);
      if (!edge?.label) addError(errors, "EDGE_OVERLAPS_TEXT", `${node.id}: decision output ${edgeId} has no condition label`);
    }
  }
  const processBoxes = model.nodes.filter((node) => node.gost_type === "process").map((node) => node.bbox);
  const processRef = processBoxes[0];
  for (const node of model.nodes.filter((item) => item.gost_type === "process")) {
    if (Math.abs(node.bbox.width - processRef.width) > 0.01 || Math.abs(node.bbox.height - processRef.height) > 0.01) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: process rectangles must share identical width and height`);
    }
  }
  passes.push("Decision blocks have one input and labeled alternative outputs.");

  for (const edge of model.edges) {
    if (!nodeById.has(edge.from_node) || !nodeById.has(edge.to_node)) addError(errors, "EDGE_FLOATING", `${edge.id}: bad node reference`);
    if (!edge.orthogonal_only) addError(errors, "EDGE_ROUTE_NOT_ORTHOGONAL", `${edge.id}: orthogonal_only is not true`);
    if (!["control", "data", "communication"].includes(edge.flow_kind)) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: invalid flow_kind ${edge.flow_kind}`);
    if (!["line", "communication_channel", "control_transfer", "dashed"].includes(edge.line_symbol)) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: invalid line_symbol ${edge.line_symbol}`);
    if (!["solid", "dashed"].includes(edge.line_style)) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: invalid line_style ${edge.line_style}`);
    if (edge.line_symbol === "dashed" && edge.line_style !== "dashed") addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: dashed line symbol must use dashed style`);
    if (edge.line_symbol !== "dashed" && edge.line_style === "dashed") addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: dashed style is only allowed for dashed line symbol`);
    const from = nodeById.get(edge.from_node);
    const to = nodeById.get(edge.to_node);
    if (from && !from.allowed_output_sides.includes(edge.from_port)) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: ${edge.from_node}.${edge.from_port} is not an allowed output side`);
    if (to && !to.allowed_input_sides.includes(edge.to_port)) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: ${edge.to_node}.${edge.to_port} is not an allowed input side`);
    const nonStandard = routeHasReverseSegment(edge.route_points);
    const forcedArrowless = new Set(model.layout_policy?.arrowless_edge_ids || []).has(edge.id);
    if (forcedArrowless) {
      if (edge.arrow_required) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: forced arrowless edge must not require an arrow`);
    } else if (edge.arrow_required !== nonStandard) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: arrow_required must match non-standard route direction`);
    }
    for (let i = 1; i < edge.route_points.length; i += 1) {
      const a = edge.route_points[i - 1];
      const b = edge.route_points[i];
      if (Math.abs(a.x - b.x) > 0.1 && Math.abs(a.y - b.y) > 0.1) addError(errors, "EDGE_HAS_DIAGONAL_SEGMENT", `${edge.id}: diagonal segment`);
    }
  }
  passes.push("Edges declare ports, flow kind and orthogonal route points.");

  const maxConnectors = model.layout_policy?.max_connectors ?? 5;
  if (connectorNodes.length > maxConnectors) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `connector count ${connectorNodes.length} exceeds ${maxConnectors}`);
  const connectorGroups = new Map();
  for (const connector of connectorNodes) {
    if (!connectorGroups.has(connector.label)) connectorGroups.set(connector.label, []);
    connectorGroups.get(connector.label).push(connector);
  }
  const cGroup = connectorGroups.get(connectorGroupLabel) || [];
  const exitConnector = nodeById.get(connectorExitId);
  if (!connectorGroupLabel || cGroup.length < 2) {
    addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `layout: continuation connector group ${connectorGroupLabel || "(unset)"} must contain at least two circles`);
  }
  if (!exitConnector || exitConnector.gost_type !== "connector" || exitConnector.label !== connectorGroupLabel) {
    addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", "layout: missing declared End-before continuation connector");
  } else {
    if (exitConnector.actual_outputs.length !== 1) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", "End-before continuation connector must have exactly one outgoing line to End");
    const finalOutput = edgeById.get(exitConnector.actual_outputs[0]);
    if (!finalOutput || finalOutput.to_node !== model.layout_policy?.end_node_id) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", "End-before continuation connector output must be the only line entering End");
    const endInputs = (nodeById.get(model.layout_policy?.end_node_id)?.actual_inputs || []);
    if (endInputs.length !== 1 || endInputs[0] !== exitConnector.actual_outputs[0]) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", "End must receive only the End-before continuation connector line");
  }
  for (const edge of model.edges) {
    if (edge.to_node === model.layout_policy?.end_node_id && edge.from_node !== connectorExitId) {
      addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: no branch may point directly to End`);
    }
  }
  for (const connector of connectorNodes) {
    if (connector.label !== connectorGroupLabel) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `${connector.id}: connector label must be ${connectorGroupLabel}`);
    if (connector.id === connectorExitId) continue;
    if (connector.actual_inputs.length < 1) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `${connector.id}: branch continuation connector must have an incoming line`);
    if (connector.actual_outputs.length !== 0) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `${connector.id}: branch continuation connector must not directly point to a flow element`);
  }
  passes.push("Connector count and grouped same-letter C continuation policy checked.");

  if (Object.keys(model.subflows || {}).length) addError(errors, "EDGE_WRONG_DIRECTION", "subflows: simplified drawing must not define separate subflows");
  if (fs.existsSync(SUBFLOW_DIR) && fs.readdirSync(SUBFLOW_DIR).some((name) => name.endsWith(".drawio"))) addError(errors, "EDGE_WRONG_DIRECTION", "subflows: simplified drawing must not leave generated subflow drawio files");
  passes.push("No predefined-process/function-block shapes or separate subflow drawings remain.");

  const diagrams = loadDrawioDiagrams(DRAWIO_PATH);
  const diagramByName = new Map(diagrams.map((diagram) => [String(diagram["@_name"] || ""), diagram]));
  if (!diagramByName.has("Main A1 Flowchart")) addError(errors, "EDGE_FLOATING", "combined drawio: missing Main A1 Flowchart page");
  if (diagrams.length !== 1) addError(errors, "EDGE_FLOATING", `drawio: simplified drawing must be one page, found ${diagrams.length}`);
  passes.push("Drawio file is a single-page main drawing.");

  const mainDiagram = diagramByName.get("Main A1 Flowchart") || diagrams[0];
  const cells = asArray(mainDiagram.mxGraphModel.root.mxCell);
  const nodeCells = cells.filter((cell) => String(cell["@_id"] || "").startsWith("repo_flow_") && cell["@_vertex"] === "1" && !String(cell["@_id"]).startsWith("repo_flow_label_"));
  const edgeCells = cells.filter((cell) => String(cell["@_id"] || "").startsWith("repo_flow_edge_"));
  const labelCells = cells.filter((cell) => String(cell["@_id"] || "").startsWith("repo_flow_label_"));
  const strayGeneratedEndpointEdges = cells.filter((cell) => {
    const id = String(cell["@_id"] || "");
    const source = String(cell["@_source"] || "");
    const target = String(cell["@_target"] || "");
    return cell["@_edge"] === "1" &&
      !id.startsWith("repo_flow_edge_") &&
      (source.startsWith("repo_flow_") || target.startsWith("repo_flow_"));
  });
  if (strayGeneratedEndpointEdges.length) {
    addError(
      errors,
      "EDGE_FLOATING",
      `drawio: ${strayGeneratedEndpointEdges.length} stray non-generated edge(s) remain attached to generated flow nodes: ${strayGeneratedEndpointEdges.map((cell) => cell["@_id"]).join(", ")}`
    );
  }
  const allText = cells.map((cell) => decodeText(cell["@_value"])).join("\n");
  if (nodeCells.length !== model.nodes.length) addError(errors, "EDGE_FLOATING", `drawio: expected ${model.nodes.length} nodes, found ${nodeCells.length}`);
  if (edgeCells.length !== model.edges.length) addError(errors, "EDGE_FLOATING", `drawio: expected ${model.edges.length} edges, found ${edgeCells.length}`);
  if (!allText.includes(TITLE_BLOCK_DRAWING_CODE)) addError(errors, `EDGE_FLOATING`, `title block: missing ${TITLE_BLOCK_DRAWING_CODE} drawing code`);
  if (/BSTU\.241297\.005/.test(allText)) addError(errors, "EDGE_FLOATING", "title block: legacy BSTU code remains");
	  validateContentTitleBlock(cells, model.page, allText, errors);
	  passes.push("Title block uses the thesis content-page lower-table proportions, 185mm x 40mm size, lower-right frame alignment, and checked thick/thin grid strokes.");

	  const bottomReturnArrowNodeIds = model.layout_policy?.bottom_return_arrow_node_ids || [];
	  if (bottomReturnArrowNodeIds.length) {
	    const bottomY = model.layout_policy?.bottom_return_bus_y;
	    const arrowLength = model.layout_policy?.bottom_return_arrow_length ?? 44;
	    const arrowOffset = model.layout_policy?.bottom_return_arrow_offset ?? 12;
	    const bottomLeftX = model.layout_policy?.bottom_return_bus_left_x;
	    const finalConnectorId = model.layout_policy?.connector_exit_id;
	    const finalConnector = finalConnectorId ? nodeById.get(finalConnectorId) : null;
	    const leftBusCell = cells.find((item) => String(item["@_id"] || "") === `${DECOR_PREFIX}bottom_return_bus_left`);
	    if (Number.isFinite(bottomLeftX) && finalConnector) {
	      if (!leftBusCell) {
	        addError(errors, "EDGE_FLOATING", "bottom return: missing generated left bus segment under the first merge arrow");
	      } else {
	        const style = String(leftBusCell["@_style"] || "");
	        const endpoints = lineEndpoints(leftBusCell);
	        const finalCenterX = finalConnector.bbox.x + finalConnector.bbox.width / 2;
	        if (style.includes("endArrow=open")) addError(errors, "EDGE_TARGET_MISSING_ARROWHEAD", "bottom return: left bus segment must not have an arrow");
	        if (Math.abs(endpoints.source.x - bottomLeftX) > 1 || Math.abs(endpoints.target.x - finalCenterX) > 1 ||
	            Math.abs(endpoints.source.y - bottomY) > 1 || Math.abs(endpoints.target.y - bottomY) > 1) {
	          addError(errors, "EDGE_GAP_TO_NODE", "bottom return: left bus segment must exactly span from declared left x to the final C vertical drop");
	        }
	      }
	    }
	    for (const nodeId of bottomReturnArrowNodeIds) {
	      const node = nodeById.get(nodeId);
	      const cell = cells.find((item) => String(item["@_id"] || "") === `${DECOR_PREFIX}bottom_return_arrow_${nodeId}`);
	      if (!node || !cell) {
	        addError(errors, "EDGE_TARGET_MISSING_ARROWHEAD", `bottom return: missing required left-pointing arrow at ${nodeId}`);
	        continue;
	      }
	      const style = String(cell["@_style"] || "");
	      const endpoints = lineEndpoints(cell);
	      const centerX = node.bbox.x + node.bbox.width / 2;
	      const expectedTargetX = centerX + arrowOffset;
	      const expectedSourceX = expectedTargetX + arrowLength;
	      if (!style.includes("endArrow=open") || !style.includes("endFill=0")) {
	        addError(errors, "EDGE_TARGET_MISSING_ARROWHEAD", `bottom return: ${nodeId} arrow must use open, unfilled target arrow`);
	      }
	      if (Math.abs(endpoints.source.y - bottomY) > 1 || Math.abs(endpoints.target.y - bottomY) > 1 || Math.abs(endpoints.source.y - endpoints.target.y) > 1) {
	        addError(errors, "HORIZONTAL_EDGE_Y_MISALIGNED", `bottom return: ${nodeId} arrow must lie on y=${bottomY}`);
	      }
	      if (endpoints.source.x <= endpoints.target.x) {
	        addError(errors, "EDGE_WRONG_DIRECTION", `bottom return: ${nodeId} arrow must point right-to-left toward the branch merge`);
	      }
	      if (Math.abs(endpoints.target.x - expectedTargetX) > 1 || Math.abs(endpoints.source.x - expectedSourceX) > 1) {
	        addError(errors, "EDGE_GAP_TO_NODE", `bottom return: ${nodeId} arrow must start ${arrowLength}px to the right and end ${arrowOffset}px right of the branch centerline`);
	      }
	    }
	  }
	  passes.push("Bottom return-lane arrows are generated, open, horizontal, and positioned just right of their branch merge points.");

  const shapeChecks = {
    terminator: (cell) => styleHas(cell, "rounded=1"),
    process: (cell) => !styleHas(cell, "shape=") && !styleHas(cell, "rhombus"),
    predefined_process: (cell) => !styleHas(cell, "shape=") && !styleHas(cell, "rhombus"),
    decision: (cell) => styleHas(cell, "rhombus"),
    data: (cell) => styleHas(cell, "shape=parallelogram"),
    stored_data: (cell) => styleHas(cell, "database"),
    document: (cell) => styleHas(cell, "shape=document"),
    display: (cell) => styleHas(cell, "shape=display"),
    manual_input: (cell) => styleHas(cell, "shape=manualInput"),
    manual_operation: (cell) => styleHas(cell, "shape=manualOperation"),
    connector: (cell) => styleHas(cell, "ellipse")
  };
  const cellsByNodeId = new Map(nodeCells.map((cell) => [String(cell["@_id"]).replace("repo_flow_", ""), cell]));
  const databaseCells = nodeCells.filter((cell) => styleHas(cell, "database"));
  if (databaseCells.length) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `layout: database/cylinder shapes are forbidden (${databaseCells.map((cell) => cell["@_id"]).join(", ")})`);
  const frame = frameBox(model.page);
  for (const node of model.nodes) {
    const cell = cellsByNodeId.get(node.id);
    if (!cell) continue;
    const box = boxOf(cell);
    if (!shapeChecks[node.gost_type]?.(cell)) addError(errors, "CONNECTOR_CIRCLE_NOT_MODELED_AS_NODE", `${node.id}: drawio shape does not match ${node.gost_type}`);
    if (Math.abs(box.x - node.bbox.x) > 0.01 || Math.abs(box.y - node.bbox.y) > 0.01 || Math.abs(box.width - node.bbox.width) > 0.01 || Math.abs(box.height - node.bbox.height) > 0.01) {
      addError(errors, "EDGE_FLOATING", `${node.id}: drawio bbox differs from model`);
    }
    if (/[\u3400-\u9fff]/.test(decodeText(cell["@_value"]))) addError(errors, "EDGE_OVERLAPS_TEXT", `${node.id}: contains Chinese text`);
    if (box.x < frame.x + 8 || box.y < frame.y + 8 || box.x + box.width > frame.x + frame.width - 8 || box.y + box.height > frame.y + frame.height - 8) addError(errors, "EDGE_FLOATING", `${node.id}: outside usable A1 drawing field`);
    if (overlaps(box, model.page.forbidden_area, 0)) addError(errors, "EDGE_CROSSES_NODE", `${node.id}: overlaps title block forbidden area`);
    if (!textLikelyFits(node)) addError(errors, "EDGE_OVERLAPS_TEXT", `${node.id}: text likely overflows symbol interior`);
    const expectedRatio = aspectRatioRules[node.gost_type];
    if (expectedRatio) {
      const ratio = box.width / box.height;
      if (Math.abs(ratio - expectedRatio) > 0.035) {
        addError(errors, "EDGE_WRONG_DIRECTION", `${node.id}: ${node.gost_type} aspect ratio ${ratio.toFixed(3)} must be ${expectedRatio.toFixed(3)}`);
      }
    }
  }
  passes.push("Drawio nodes and title block match model bboxes, GOST shape styles, frame margins, aspect ratios and text-fit estimates.");

  for (let i = 0; i < nodeCells.length; i += 1) {
    for (let j = i + 1; j < nodeCells.length; j += 1) {
      const a = boxOf(nodeCells[i]);
      const b = boxOf(nodeCells[j]);
      const nodeA = String(nodeCells[i]["@_id"]).replace("repo_flow_", "");
      const nodeB = String(nodeCells[j]["@_id"]).replace("repo_flow_", "");
      if (overlaps(a, b, 0)) addError(errors, "EDGE_CROSSES_NODE", `${nodeCells[i]["@_id"]} overlaps ${nodeCells[j]["@_id"]}`);
      const horizontalOverlap = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
      const verticalOverlap = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
      const verticalGap = Math.max(a.y, b.y) - Math.min(a.y + a.height, b.y + b.height);
      const horizontalGap = Math.max(a.x, b.x) - Math.min(a.x + a.width, b.x + b.width);
      const isConnectorPair = nodeById.get(nodeA)?.gost_type === "connector" || nodeById.get(nodeB)?.gost_type === "connector";
      const hasDirectEdge = model.edges.some((edge) => (
        (edge.from_node === nodeA && edge.to_node === nodeB) ||
        (edge.from_node === nodeB && edge.to_node === nodeA)
      ));
      if (!isConnectorPair && !hasDirectEdge && horizontalOverlap > 8 && verticalGap >= 0 && verticalGap < 12) {
        addError(errors, "EDGE_GAP_TO_NODE", `${nodeA}/${nodeB}: vertical symbol gap ${verticalGap.toFixed(1)} is too small`);
      }
      if (!isConnectorPair && !hasDirectEdge && verticalOverlap > 8 && horizontalGap >= 0 && horizontalGap < 12) {
        addError(errors, "EDGE_GAP_TO_NODE", `${nodeA}/${nodeB}: horizontal symbol gap ${horizontalGap.toFixed(1)} is too small`);
      }
    }
  }

  const segments = [];
  const referenceEdge = edgeById.get(model.layout_policy?.reference_edge_id || "e01");
  const referenceLength = referenceEdge
    ? referenceEdge.route_points.slice(1).reduce((sum, point, index) => sum + segmentLength(referenceEdge.route_points[index], point), 0)
    : 45;
  for (const edge of model.edges) {
    const sourceCell = cellsByNodeId.get(edge.from_node);
    const targetCell = cellsByNodeId.get(edge.to_node);
    if (!sourceCell || !targetCell) continue;
    const sourceBox = boxOf(sourceCell);
    const targetBox = boxOf(targetCell);
    const start = edge.route_points[0];
    const end = edge.route_points[edge.route_points.length - 1];
    const sourceNode = nodeById.get(edge.from_node);
    const targetNode = nodeById.get(edge.to_node);
    const sourceOnPort = sourceNode && pointOnNodePort(start, sourceNode, edge.from_port);
    const sourceOnControlledBranch = (model.branch_groups || []).some((group) => (
      group.branch_edge_ids.includes(edge.id) &&
      group.source_node === edge.from_node &&
      edge.from_port === group.source_port
    ));
    if (sourceNode && !sourceOnPort && !sourceOnControlledBranch) addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${edge.id}: start point not centered on ${edge.from_node}.${edge.from_port}`);
    if (targetNode && !pointOnNodePort(end, targetNode, edge.to_port)) addError(errors, "EDGE_TARGET_NOT_ON_PORT", `${edge.id}: end point not centered on ${edge.to_node}.${edge.to_port}`);
    if (sourceNode && !sourceOnControlledBranch && !routeTouchesDataSymbolEdge(edge, sourceNode, start, edge.from_port)) addError(errors, "EDGE_SOURCE_NOT_ON_PORT", `${edge.id}: data-symbol output must terminate on the declared edge port`);
    if (targetNode && !routeTouchesDataSymbolEdge(edge, targetNode, end, edge.to_port)) addError(errors, "EDGE_TARGET_NOT_ON_PORT", `${edge.id}: data-symbol input must terminate on the declared edge port`);
    if (edge.arrow_required) {
      const edgeCell = cells.find((cell) => String(cell["@_id"] || "") === `repo_flow_edge_${edge.id}`);
      const style = String(edgeCell?.["@_style"] || "");
      if (!edgeCell || !style.includes("endArrow=open") || !style.includes("endFill=0")) addError(errors, "EDGE_TARGET_MISSING_ARROWHEAD", `${edge.id}: required open target arrow missing`);
      if (edge.route_points.length > 2 && distance(edge.route_points[edge.route_points.length - 2], end) < 24) addError(errors, "EDGE_GAP_TO_NODE", `${edge.id}: final arrow segment too short to read`);
    } else {
      const edgeCell = cells.find((cell) => String(cell["@_id"] || "") === `repo_flow_edge_${edge.id}`);
      const style = String(edgeCell?.["@_style"] || "");
      if (style.includes("endArrow=open")) addError(errors, "EDGE_TARGET_MISSING_ARROWHEAD", `${edge.id}: standard direction must not draw an arrowhead`);
    }
    const edgeCell = cells.find((cell) => String(cell["@_id"] || "") === `repo_flow_edge_${edge.id}`);
    const style = String(edgeCell?.["@_style"] || "");
    const isDashedInDrawio = style.includes("dashed=1");
    if (edge.line_style === "dashed" && !isDashedInDrawio) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: model says dashed but drawio style is solid`);
    if (edge.line_style === "solid" && isDashedInDrawio) addError(errors, "EDGE_WRONG_DIRECTION", `${edge.id}: model says solid but drawio style is dashed`);
    if (edge.label && !labelCells.some((cell) => String(cell["@_id"] || "") === `repo_flow_label_${edge.id}`)) addError(errors, "EDGE_OVERLAPS_TEXT", `${edge.id}: missing label cell`);
    if (edge.label_position) {
      const labelBox = labelBoxFor(edge);
      const labelPoint = { x: edge.label_position.x, y: edge.label_position.y };
      const nearestLabelDistance = edge.route_points.slice(1).reduce((best, point, index) => {
        return Math.min(best, distancePointToSegment(labelPoint, edge.route_points[index], point));
      }, Infinity);
      const nearestLabelBoxGap = edge.route_points.slice(1).reduce((best, point, index) => {
        return Math.min(best, labelBoxGapToSegment(labelBox, edge.route_points[index], point));
      }, Infinity);
      if (nearestLabelDistance < LABEL_OFFSET - LABEL_OFFSET_TOLERANCE) {
        addError(errors, "EDGE_OVERLAPS_TEXT", `${edge.id}: label offset ${nearestLabelDistance.toFixed(1)} must be ${LABEL_OFFSET}px`);
      }
      if (Math.abs(nearestLabelBoxGap - LABEL_BOX_GAP) > LABEL_BOX_GAP_TOLERANCE) {
        addError(errors, "EDGE_OVERLAPS_TEXT", `${edge.id}: label box gap ${nearestLabelBoxGap.toFixed(1)} must be ${LABEL_BOX_GAP}px`);
      }
      for (const nodeCell of nodeCells) {
        const nodeId = String(nodeCell["@_id"]).replace("repo_flow_", "");
        if (overlaps(labelBox, boxOf(nodeCell), 2)) addError(errors, "EDGE_OVERLAPS_TEXT", `${edge.id}: label overlaps or crowds node ${nodeId}`);
      }
    }
    const totalLength = edge.route_points.slice(1).reduce((sum, point, index) => sum + segmentLength(edge.route_points[index], point), 0);
    if (totalLength + CONNECTION_LENGTH_TOLERANCE < referenceLength * MIN_CONNECTION_TOTAL_FACTOR) {
      addError(errors, "EDGE_GAP_TO_NODE", `${edge.id}: total route length ${totalLength.toFixed(1)} is shorter than reference ${referenceLength.toFixed(1)}`);
    }
    for (let i = 1; i < edge.route_points.length; i += 1) {
      const a = edge.route_points[i - 1];
      const b = edge.route_points[i];
      const segBox = segmentBox(a, b, 3);
      for (const nodeCell of nodeCells) {
        const nodeId = String(nodeCell["@_id"]).replace("repo_flow_", "");
        if (nodeId === edge.from_node || nodeId === edge.to_node) continue;
        const nodeBox = boxOf(nodeCell);
        if (overlaps(segBox, nodeBox, 2)) addError(errors, "EDGE_CROSSES_NODE", `${edge.id}: line crosses node ${nodeId}`);
        if (nodeId !== edge.from_node && nodeId !== edge.to_node && (pointInBox(a, nodeBox, 1) || pointInBox(b, nodeBox, 1))) addError(errors, "EDGE_CROSSES_NODE", `${edge.id}: waypoint touches non-target node ${nodeId}`);
      }
      segments.push({ edgeId: edge.id, a, b });
    }
  }
  passes.push("Edges connect to declared centered ports, labels exist and line segments avoid symbols.");

  for (let i = 0; i < segments.length; i += 1) {
    for (let j = i + 1; j < segments.length; j += 1) {
      if (segments[i].edgeId === segments[j].edgeId) continue;
      if (segmentsIntersect(segments[i].a, segments[i].b, segments[j].a, segments[j].b)) {
        if (!isAllowedBottomReturnMerge(segments[i].edgeId, segments[j].edgeId, model)) {
          addError(errors, "EDGE_CROSSES_NODE", `line crossing: ${segments[i].edgeId} intersects ${segments[j].edgeId}`);
        }
      }
      const overlapLength = collinearOverlapLength(segments[i].a, segments[i].b, segments[j].a, segments[j].b);
      if (overlapLength > 4) {
        addError(errors, "EDGE_CROSSES_NODE", `line overlap: ${segments[i].edgeId} overlaps ${segments[j].edgeId} by ${overlapLength.toFixed(1)}px`);
      }
    }
  }
  passes.push("Line crossing and same-lane overlap checks executed; any crossing or hidden overlap is reported.");

  const alignmentChecks = [];
  if (model.layout_policy?.main_axis_edge_ids?.length) {
    alignmentChecks.push(addAlignmentCheck(
      errors,
      model,
      model.layout_policy.main_axis_edge_ids,
      model.layout_policy.main_axis_orientation === "horizontal" ? "horizontal" : "vertical",
      model.layout_policy.main_axis_orientation === "horizontal" ? "Start -> End horizontal trunk" : "Start -> C -> End center axis"
    ));
  }
  const verticalBranchIds = model.layout_policy?.vertical_branch_edge_ids || [];
  if (verticalBranchIds.length) {
    const nonVertical = verticalBranchIds.filter((edgeId) => {
      const edge = model.edges.find((item) => item.id === edgeId);
      return !edge || !edge.route_points.every((point) => Math.abs(point.x - edge.route_points[0].x) <= 1);
    });
    if (nonVertical.length) addError(errors, "VERTICAL_EDGE_X_MISALIGNED", `vertical branch edges must stay in one x lane: ${nonVertical.join(", ")}`);
    alignmentChecks.push({ label: "All declared vertical branch edges", orientation: "vertical", values: [verticalBranchIds.length], ok: nonVertical.length === 0 });
  }
  passes.push("Required horizontal and vertical chain alignment checks executed.");

  const mergeChecks = (model.merge_groups || []).map((group) => addMergeGroupCheck(errors, model, group));
  passes.push("Merge groups use visible connector stems, horizontal merge lane and one centered incoming line.");

  const branchChecks = [
    ...(model.branch_groups || []).map((group) => addBranchGroupCheck(errors, model, group)),
    addBranchColumnLayoutCheck(errors, model)
  ];
  passes.push("Branch groups are controlled GOST 4.3.1 tee branches from a centerline; visual columns are balanced left/right, bottom-aligned and internally uniform.");

  const semanticChecks = {
    display_outputs: model.nodes.filter((node) => node.gost_type === "display").map((node) => ({ id: node.id, label: node.label, outputs: node.actual_outputs.length })),
    document_outputs: model.nodes.filter((node) => node.gost_type === "document").map((node) => ({ id: node.id, label: node.label, outputs: node.actual_outputs.length })),
    arrow_required_edges: model.edges.filter((edge) => edge.arrow_required).length,
    arrowless_standard_edges: model.edges.filter((edge) => !edge.arrow_required).length,
    dashed_edges: model.edges.filter((edge) => edge.line_style === "dashed").map((edge) => edge.id),
    communication_channel_edges: model.edges.filter((edge) => edge.line_symbol === "communication_channel").map((edge) => ({ id: edge.id, line_style: edge.line_style }))
  };
  if (semanticChecks.display_outputs.some((item) => item.outputs !== 0)) addError(errors, "EDGE_WRONG_DIRECTION", "display nodes must be terminal outputs in this drawing");
  if (semanticChecks.document_outputs.some((item) => item.outputs !== 0)) addError(errors, "EDGE_WRONG_DIRECTION", "document nodes must be terminal artifacts in this drawing");
  if (semanticChecks.dashed_edges.length) addError(errors, "EDGE_WRONG_DIRECTION", `dashed lines are disabled for this scheme unless a specific GOST 19.701-90 3.3.2.3 alternative-link justification is added: ${semanticChecks.dashed_edges.join(", ")}`);
  if (semanticChecks.communication_channel_edges.some((edge) => edge.line_style !== "solid")) addError(errors, "EDGE_WRONG_DIRECTION", "communication-channel edges must remain solid in this drawing; GOST 19.701-90 3.3.2.2 does not require dashed style");
  passes.push("Display and document symbols are terminal outputs; arrows and dashed lines follow explicit line-style rules.");

  const report = [
    "# Flowchart Compliance Report",
    "",
    "## Normative Basis",
    `- GOST/ISO: ${model.standard_basis.gost}`,
    "- BrSTU official public flowchart-specific rule found: no. BrSTU/ESKD A1 frame/title-block style retained; GOST 19.701-90 is the hard flowchart standard.",
    "- Line policy: communication channels are semantically marked as GOST 19.701-90 3.3.2.2 and drawn solid; dashed lines are not used because 3.3.2.3 is reserved for alternative/auxiliary links or annotated areas.",
    "",
    "## Pass Checks",
    ...passes.map((item) => `- ${item}`),
    "",
    errors.length ? "## Errors" : "## Result",
    ...(errors.length ? errors.map((error) => `- ${error.code}: ${error.detail}`) : ["- PASS"])
  ];
  const audit = buildSemanticAudit(model, errors, passes, alignmentChecks, mergeChecks, branchChecks, semanticChecks, cellsByNodeId);
  fs.writeFileSync(SUMMARY_PATH, JSON.stringify({ ok: errors.length === 0, errors, passes, alignmentChecks, mergeChecks, branchChecks, semanticChecks }, null, 2));
  fs.writeFileSync(REPORT_PATH, `${report.join("\n")}\n`);
  fs.writeFileSync(AUDIT_JSON_PATH, JSON.stringify(audit, null, 2));
  fs.writeFileSync(AUDIT_MD_PATH, auditMarkdown(audit));
  if (errors.length) {
    console.error(errors.map((error) => `${error.code}: ${error.detail}`).join("\n"));
    process.exit(1);
  }
  console.log("Flowchart validation passed");
}

validate();
