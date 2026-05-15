#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser } = require("fast-xml-parser");
const {
  SHAPE_RULES,
  CONNECTOR_RULES,
  DECISION_RULES,
  REQUIRED_LOGIC_EDGES,
  LABEL_PLACEMENT_RULES,
  ARROW_RULES,
  CONNECTOR_LOCALITY_RULES,
  CONTROL_BLOCK_RULES,
  PRIMARY_FLOW_DIRECTION_RULES,
  LONG_LINE_RULES,
  VISUAL_DENSITY_RULES,
  VISUAL_BALANCE_RULES,
  SYNTHETIC_EDGE_RULES,
  ROUTING_ENVELOPE_RULES,
  FRAME_RULES,
  ROW_WRAP_RULES,
  PROGRAM_SCHEME_LAYOUT_RULES,
  DISPLAY_LABEL_OVERRIDES,
  NORMAL_BRANCH_LABELS,
  ABNORMAL_BRANCH_LABELS,
  normalizeText,
  findEdges
} = require("./flow_rules");

const LABEL_RULES = LABEL_PLACEMENT_RULES;

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = path.join(ROOT_DIR, "aa.drawio");
const MODEL_PATH = path.join(WORK_DIR, "flow_model.json");
const DRAWIO_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");
const METRICS_PATH = path.join(WORK_DIR, "layout_metrics.json");
const SUMMARY_PATH = path.join(WORK_DIR, "validator_summary.json");
const REPORT_PATH = path.join(WORK_DIR, "compliance_report.md");

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

function asArray(value) {
  if (value == null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const raw = obj && obj[`@_${key}`];
  const value = Number(raw);
  return Number.isFinite(value) ? value : fallback;
}

function fail(errors, message) {
  errors.push(message);
}

function approx(actual, expected, tolerance = 0.01) {
  return Math.abs(actual - expected) <= tolerance;
}

function approxRatio(width, height, expected) {
  return Math.abs(width / height - expected) <= 0.01;
}

function nodeText(model, id) {
  return model.nodes.find((node) => node.id === id)?.text || id;
}

function boxOf(cell) {
  const g = cell.mxGeometry || {};
  return {
    x: attrNumber(g, "x"),
    y: attrNumber(g, "y"),
    width: attrNumber(g, "width"),
    height: attrNumber(g, "height")
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

function expandedBox(box, pad) {
  return {
    x: box.x - pad,
    y: box.y - pad,
    width: box.width + pad * 2,
    height: box.height + pad * 2
  };
}

function segmentToBoxClearance(a, b, box) {
  if (Math.abs(a.y - b.y) <= 0.1) {
    const y = a.y;
    const minX = Math.min(a.x, b.x);
    const maxX = Math.max(a.x, b.x);
    const overlapX = maxX >= box.x && minX <= box.x + box.width;
    if (!overlapX) {
      return Infinity;
    }
    if (y < box.y) {
      return box.y - y;
    }
    if (y > box.y + box.height) {
      return y - (box.y + box.height);
    }
    return 0;
  }
  if (Math.abs(a.x - b.x) <= 0.1) {
    const x = a.x;
    const minY = Math.min(a.y, b.y);
    const maxY = Math.max(a.y, b.y);
    const overlapY = maxY >= box.y && minY <= box.y + box.height;
    if (!overlapY) {
      return Infinity;
    }
    if (x < box.x) {
      return box.x - x;
    }
    if (x > box.x + box.width) {
      return x - (box.x + box.width);
    }
    return 0;
  }
  return Infinity;
}

function orthogonalSegmentDescriptors(edge, points) {
  const id = String(edge["@_id"] || "");
  const segments = [];
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    if (Math.abs(a.y - b.y) <= 0.1 && Math.abs(a.x - b.x) > 0.1) {
      segments.push({ edgeId: id, orientation: "h", axis: a.y, min: Math.min(a.x, b.x), max: Math.max(a.x, b.x), a, b });
    } else if (Math.abs(a.x - b.x) <= 0.1 && Math.abs(a.y - b.y) > 0.1) {
      segments.push({ edgeId: id, orientation: "v", axis: a.x, min: Math.min(a.y, b.y), max: Math.max(a.y, b.y), a, b });
    }
  }
  return segments;
}

function decodeText(text) {
  return String(text || "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function containsChinese(text) {
  return /[\u3400-\u9fff]/.test(text);
}

function hasTruncatedWord(text) {
  const normalized = decodeText(text).replace(/\r/g, "").trim();
  const allowed = new Set(Object.values(DISPLAY_LABEL_OVERRIDES || {}).map((value) => String(value).replace(/\r/g, "").trim()));
  if (allowed.has(normalized)) {
    return false;
  }
  return /\b(Pendin|Teleme|Approv|Operat|Artifa|Candid|Paramet)\b/i.test(normalized.replace(/\n/g, " "));
}

function textOverflowRisk(text, modelType, box) {
  const lines = decodeText(text).split(/\n/);
  if (lines.length > 2) {
    return true;
  }
  const innerWidth = modelType === "decision"
    ? box.width * 0.46
    : modelType === "connector"
      ? box.width * 0.60
      : modelType === "stored_data"
        ? box.width * 0.56
      : modelType === "manual_input"
        ? box.width * 0.34
      : ["data", "document"].includes(modelType)
        ? box.width * 0.48
        : box.width * 0.56;
  const innerHeight = modelType === "decision"
    ? box.height - 28
    : modelType === "stored_data"
      ? box.height - 32
      : modelType === "manual_input"
        ? box.height - 26
        : box.height - 22;
  const charWidth = modelType === "connector"
    ? 10
    : modelType === "decision"
      ? 9.8
      : modelType === "stored_data"
        ? 9.0
        : modelType === "manual_input"
          ? 10.2
          : 10.7;
  const lineHeight = modelType === "stored_data" ? 23 : 25;
  if (lines.length * lineHeight > innerHeight) {
    return true;
  }
  return lines.some((line) => line.length * charWidth > innerWidth);
}

function isFlowNode(cell) {
  const id = String(cell["@_id"] || "");
  return id.startsWith(ID_PREFIX) &&
    !id.startsWith(EDGE_PREFIX) &&
    !id.startsWith(LABEL_PREFIX) &&
    !id.startsWith(DECOR_PREFIX) &&
    cell["@_vertex"] === "1";
}

function isRepoEdge(cell) {
  const id = String(cell["@_id"] || "");
  return id.startsWith(EDGE_PREFIX) && cell["@_edge"] === "1";
}

function isLabel(cell) {
  return String(cell["@_id"] || "").startsWith(LABEL_PREFIX);
}

function isDecor(cell) {
  return String(cell["@_id"] || "").startsWith(DECOR_PREFIX);
}

function nodeTypeByStyle(style) {
  const value = String(style || "");
  if (value.includes("ellipse")) return "connector";
  if (value.includes("rhombus")) return "decision";
  if (value.includes("shape=parallelogram")) return "data";
  if (value.includes("shape=mxgraph.flowchart.database")) return "stored_data";
  if (value.includes("shape=document")) return "document";
  if (value.includes("shape=manualInput")) return "manual_input";
  if (value.includes("rounded=1")) return "terminator";
  return "rect_family";
}

function sourceTargetPoints(edge, cellMap) {
  const source = cellMap.get(String(edge["@_source"] || ""));
  const target = cellMap.get(String(edge["@_target"] || ""));
  if (!source || !target) {
    return null;
  }
  const sb = boxOf(source);
  const tb = boxOf(target);
  const start = { x: sb.x + sb.width, y: sb.y + sb.height / 2 };
  const end = { x: tb.x, y: tb.y + tb.height / 2 };
  const points = [start];
  const geo = edge.mxGeometry || {};
  const array = geo.Array && geo.Array.mxPoint ? asArray(geo.Array.mxPoint) : [];
  for (const p of array) {
    points.push({ x: attrNumber(p, "x"), y: attrNumber(p, "y") });
  }
  points.push(end);
  return points;
}

function sourceTargetPointsWithPorts(edge, cellMap) {
  const source = cellMap.get(String(edge["@_source"] || ""));
  const target = cellMap.get(String(edge["@_target"] || ""));
  const geo = edge.mxGeometry || {};
  const directPoints = asArray(geo.mxPoint || []);
  const sourcePoint = directPoints.find((point) => point["@_as"] === "sourcePoint");
  const targetPoint = directPoints.find((point) => point["@_as"] === "targetPoint");
  if (!source && !target && sourcePoint && targetPoint) {
    const points = [{ x: attrNumber(sourcePoint, "x"), y: attrNumber(sourcePoint, "y") }];
    const array = geo.Array && geo.Array.mxPoint ? asArray(geo.Array.mxPoint) : [];
    for (const p of array) {
      points.push({ x: attrNumber(p, "x"), y: attrNumber(p, "y") });
    }
    points.push({ x: attrNumber(targetPoint, "x"), y: attrNumber(targetPoint, "y") });
    return points;
  }
  if (!source || !target) {
    return null;
  }
  const style = String(edge["@_style"] || "");
  const exitX = Number((style.match(/exitX=([0-9.]+)/) || [])[1] || 1);
  const exitY = Number((style.match(/exitY=([0-9.]+)/) || [])[1] || 0.5);
  const entryX = Number((style.match(/entryX=([0-9.]+)/) || [])[1] || 0);
  const entryY = Number((style.match(/entryY=([0-9.]+)/) || [])[1] || 0.5);
  const sb = boxOf(source);
  const tb = boxOf(target);
  const start = { x: sb.x + sb.width * exitX, y: sb.y + sb.height * exitY };
  const end = { x: tb.x + tb.width * entryX, y: tb.y + tb.height * entryY };
  const points = [start];
  const array = geo.Array && geo.Array.mxPoint ? asArray(geo.Array.mxPoint) : [];
  for (const p of array) {
    points.push({ x: attrNumber(p, "x"), y: attrNumber(p, "y") });
  }
  points.push(end);
  return points;
}

function centerOf(cell) {
  const box = boxOf(cell);
  return {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2
  };
}

function distanceBetweenCells(a, b) {
  const ca = centerOf(a);
  const cb = centerOf(b);
  return Math.hypot(ca.x - cb.x, ca.y - cb.y);
}

function routeTotalLength(points) {
  return segmentLengths(points).reduce((sum, segment) => sum + segment.length, 0);
}

function routeSpan(points) {
  return {
    width: Math.max(...points.map((point) => point.x)) - Math.min(...points.map((point) => point.x)),
    height: Math.max(...points.map((point) => point.y)) - Math.min(...points.map((point) => point.y))
  };
}

function parsePorts(style) {
  const value = String(style || "");
  const get = (name, fallback = null) => {
    const match = value.match(new RegExp(`${name}=([0-9.]+)`));
    return match ? Number(match[1]) : fallback;
  };
  return {
    exitX: get("exitX"),
    exitY: get("exitY"),
    entryX: get("entryX"),
    entryY: get("entryY")
  };
}

function styleValue(style, key) {
  const match = String(style || "").match(new RegExp(`(?:^|;)${key}=([^;]*)`));
  return match ? match[1] : null;
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
  if (ports.entryX === 0 && ports.entryY === 0.5) return "left-to-right";
  if (ports.entryX === 1 && ports.entryY === 0.5) return "right-to-left";
  if (ports.entryX === 0.5 && ports.entryY === 0) return "top-to-bottom";
  if (ports.entryX === 0.5 && ports.entryY === 1) return "bottom-to-top";
  return null;
}

function validateOpenArrowStyle(repoEdges, cellMap, metrics, errors) {
  const invalidArrowEdges = [];
  const requiredOpenArrowEdges = [];
  const forbiddenArrowEdges = [];
  let arrowsRequired = 0;
  let arrowsForbidden = 0;
  for (const edge of repoEdges) {
    const id = String(edge["@_id"] || "");
    const points = sourceTargetPointsWithPorts(edge, cellMap);
    const style = String(edge["@_style"] || "");
    const ports = parsePorts(style);
    const direction = getFinalSegmentDirection({ points, ports });
    if (!direction) {
      const message = `Edge ${id} final segment direction cannot be determined for arrow validation.`;
      invalidArrowEdges.push({ id, direction: null, reason: message });
      fail(errors, message);
      continue;
    }
    const endArrow = String(styleValue(style, "endArrow") || "").trim();
    const endFill = String(styleValue(style, "endFill") || "").trim();
    if (ARROW_RULES.noArrowDirections.includes(direction)) {
      arrowsForbidden += 1;
      forbiddenArrowEdges.push(id);
      if (endArrow && endArrow !== "none") {
        const message = `Edge ${id} is ${direction} but incorrectly has endArrow=${endArrow}; no arrow is allowed.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      }
      if (endFill === "1") {
        const message = `Edge ${id} is ${direction} but has endFill=1; forward-direction edges must not use a filled arrow.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      }
      continue;
    }
    if (ARROW_RULES.arrowDirections.includes(direction)) {
      arrowsRequired += 1;
      requiredOpenArrowEdges.push(id);
      if (ARROW_RULES.forbiddenArrowStyles.includes(endArrow)) {
        const message = `Edge ${id} uses forbidden arrow style ${endArrow || "(missing)"}; open arrow is required.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      } else if (endArrow !== ARROW_RULES.arrowStyle.endArrow) {
        const message = `Edge ${id} is ${direction} but has endArrow=${endArrow || "(missing)"}; open arrow required.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      } else if (endFill !== String(ARROW_RULES.arrowStyle.endFill)) {
        const message = `Edge ${id} is ${direction} but endFill=${endFill || "(missing)"}; open arrow must be hollow.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      }
      const finalStem = lastVisibleSegmentLength(points);
      const modelEdgeId = id.replace(EDGE_PREFIX, "");
      const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
      const edgeModel = model.edges.find((candidate) => candidate.id === modelEdgeId);
      const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
      const isConnectorLocalArrow = nodeById.get(edgeModel?.from)?.type === "connector" || nodeById.get(edgeModel?.to)?.type === "connector";
      void isConnectorLocalArrow;
      const minStem = (metrics.U || 1) * VISUAL_DENSITY_RULES.minArrowStemU;
      if (finalStem < minStem - 0.01) {
        const message = `Edge ${id} arrow stem is too short: ${finalStem.toFixed(1)} < ${minStem.toFixed(1)}.`;
        invalidArrowEdges.push({ id, direction, reason: message });
        fail(errors, message);
      }
      continue;
    }
    const message = `Edge ${id} has unsupported final segment direction ${direction}.`;
    invalidArrowEdges.push({ id, direction, reason: message });
    fail(errors, message);
  }
  return {
    passed: invalidArrowEdges.length === 0,
    checkedEdges: repoEdges.length,
    arrowsRequired,
    arrowsForbidden,
    invalidArrowEdges,
    requiredOpenArrowEdges,
    forbiddenArrowEdges
  };
}

const validateArrowRules = validateOpenArrowStyle;

function lastVisibleSegmentLength(points) {
  for (let index = points.length - 1; index >= 1; index -= 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const length = Math.abs(curr.x - prev.x) + Math.abs(curr.y - prev.y);
    if (length > 0.1) {
      return length;
    }
  }
  return 0;
}

function approxPort(actual, expected) {
  return actual !== null && Math.abs(actual - expected) <= 0.0005;
}

function isCenterPort(x, y) {
  return [
    [0, 0.5],
    [1, 0.5],
    [0.5, 0],
    [0.5, 1]
  ].some(([expectedX, expectedY]) => approxPort(x, expectedX) && approxPort(y, expectedY));
}

function segmentLengths(points) {
  const lengths = [];
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const dx = Math.abs(curr.x - prev.x);
    const dy = Math.abs(curr.y - prev.y);
    if (dx > 0.1 && dy > 0.1) {
      lengths.push({ length: Math.sqrt(dx * dx + dy * dy), orthogonal: false, dx, dy });
    } else if (dx > 0.1 || dy > 0.1) {
      lengths.push({ length: Math.max(dx, dy), orthogonal: true, dx, dy });
    }
  }
  return lengths;
}

function mergedOrthogonalSegments(points) {
  const merged = [];
  if (!points || points.length < 2) {
    return merged;
  }
  let start = points[0];
  let previous = points[0];
  let currentDirection = null;
  for (let index = 1; index < points.length; index += 1) {
    const point = points[index];
    const dx = point.x - previous.x;
    const dy = point.y - previous.y;
    let direction = null;
    if (Math.abs(dx) > 0.1 && Math.abs(dy) <= 0.1) {
      direction = "h";
    } else if (Math.abs(dy) > 0.1 && Math.abs(dx) <= 0.1) {
      direction = "v";
    } else if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) {
      direction = "diagonal";
    }
    if (!direction) {
      continue;
    }
    if (currentDirection && direction !== currentDirection) {
      merged.push({
        a: start,
        b: previous,
        direction: currentDirection,
        length: Math.abs(previous.x - start.x) + Math.abs(previous.y - start.y)
      });
      start = previous;
    }
    currentDirection = direction;
    previous = point;
  }
  if (currentDirection) {
    merged.push({
      a: start,
      b: previous,
      direction: currentDirection,
      length: Math.abs(previous.x - start.x) + Math.abs(previous.y - start.y)
    });
  }
  return merged;
}

function routeEnvelopeForEdge(points, sourceBox, targetBox, margin) {
  return {
    minX: Math.min(sourceBox.x, targetBox.x) - margin,
    minY: Math.min(sourceBox.y, targetBox.y) - margin,
    maxX: Math.max(sourceBox.x + sourceBox.width, targetBox.x + targetBox.width) + margin,
    maxY: Math.max(sourceBox.y + sourceBox.height, targetBox.y + targetBox.height) + margin,
    points
  };
}

function bendCountOf(points) {
  let bends = 0;
  let previousDirection = null;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    const dx = curr.x - prev.x;
    const dy = curr.y - prev.y;
    let direction = null;
    if (Math.abs(dx) > 0.1 && Math.abs(dy) <= 0.1) {
      direction = "h";
    } else if (Math.abs(dy) > 0.1 && Math.abs(dx) <= 0.1) {
      direction = "v";
    } else if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) {
      direction = "diagonal";
    }
    if (!direction) {
      continue;
    }
    if (previousDirection && direction !== previousDirection) {
      bends += 1;
    }
    previousDirection = direction;
  }
  return bends;
}

function segmentBoxes(points, pad = 0) {
  const boxes = [];
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const x = Math.min(a.x, b.x);
    const y = Math.min(a.y, b.y);
    boxes.push({
      x: Math.abs(a.x - b.x) <= 0.1 ? x - pad : x,
      y: Math.abs(a.y - b.y) <= 0.1 ? y - pad : y,
      width: Math.max(1, Math.abs(a.x - b.x)) + (Math.abs(a.x - b.x) <= 0.1 ? pad * 2 : 0),
      height: Math.max(1, Math.abs(a.y - b.y)) + (Math.abs(a.y - b.y) <= 0.1 ? pad * 2 : 0)
    });
  }
  return boxes;
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

function findBranchPlacementSegment(points, orientation) {
  if (!points || points.length < 2) {
    return null;
  }
  if (orientation === "horizontal" || orientation === "horizontalLeft") {
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      const isHorizontal = Math.abs(a.y - b.y) <= 0.1 && Math.abs(a.x - b.x) > 0.1;
      if (!isHorizontal) {
        continue;
      }
      if (orientation === "horizontal" && b.x >= a.x) {
        return { a, b };
      }
      if (orientation === "horizontalLeft" && b.x <= a.x) {
        return { a, b };
      }
    }
  }
  if (orientation === "verticalDown" || orientation === "verticalUp") {
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      const isVertical = Math.abs(a.x - b.x) <= 0.1 && Math.abs(a.y - b.y) > 0.1;
      if (!isVertical) {
        continue;
      }
      if (orientation === "verticalDown" && b.y >= a.y) {
        return { a, b };
      }
      if (orientation === "verticalUp" && b.y <= a.y) {
        return { a, b };
      }
    }
  }
  return null;
}

function validateBranchLabelPlacement(model, repoEdges, labelByEdgeId, labelCells, flowNodes, cellMap, forbiddenArea, errors) {
  const repoEdgeByModelId = new Map(repoEdges.map((edge) => [String(edge["@_id"] || "").replace(EDGE_PREFIX, ""), edge]));
  const labelCellById = new Map(labelCells.map((cell) => [String(cell["@_id"] || ""), cell]));
  const violations = [];
  const pushViolation = (message) => {
    violations.push(message);
    fail(errors, message);
  };
  for (const edge of model.edges) {
    const sourceNode = model.nodes.find((node) => node.id === edge.from);
    if (sourceNode?.type !== "decision" || !edge.label) {
      continue;
    }
    const orientation = branchOrientationForLabel(String(edge.label || "").trim());
    if (!orientation) {
      fail(errors, `Decision branch ${edge.id} has unsupported branch label ${edge.label}.`);
      continue;
    }
    const rule = LABEL_RULES[orientation];
    const rendered = repoEdgeByModelId.get(edge.id);
    const labelCell = labelByEdgeId.get(edge.id);
    if (!rendered || !labelCell) {
      continue;
    }
    const points = sourceTargetPointsWithPorts(rendered, cellMap);
    const segment = findBranchPlacementSegment(points, orientation);
    if (!segment) {
      pushViolation(`Decision branch ${edge.id} (${edge.label}) has no ${orientation} segment for label placement.`);
      continue;
    }
    const labelBox = boxOf(labelCell);
    const labelCenter = {
      x: labelBox.x + labelBox.width / 2,
      y: labelBox.y + labelBox.height / 2
    };
    const midX = (segment.a.x + segment.b.x) / 2;
    const midY = (segment.a.y + segment.b.y) / 2;
    if (rule.position === "above-center") {
      const segmentY = segment.a.y;
      const gap = segmentY - (labelBox.y + labelBox.height);
      const centerTolerance = Math.max(4, Math.min(8, Math.abs(segment.a.x - segment.b.x) * 0.04));
      if (Math.abs(labelCenter.x - midX) > centerTolerance) {
        pushViolation(`Branch label ${labelCell["@_id"]} must be horizontally centered above ${edge.id}; center delta ${Math.abs(labelCenter.x - midX).toFixed(1)} > ${centerTolerance.toFixed(1)}.`);
      }
      if (labelBox.y + labelBox.height > segmentY - rule.minGap || gap < rule.minGap || gap > rule.maxGap) {
        pushViolation(`Branch label ${labelCell["@_id"]} gap above ${edge.id} is ${gap.toFixed(1)}, expected ${rule.minGap}-${rule.maxGap}.`);
      }
    } else if (rule.position === "right-middle") {
      const segmentX = segment.a.x;
      const gap = labelBox.x - segmentX;
      const centerTolerance = Math.max(4, Math.min(8, Math.abs(segment.a.y - segment.b.y) * 0.04));
      if (Math.abs(labelCenter.y - midY) > centerTolerance) {
        pushViolation(`Branch label ${labelCell["@_id"]} must be vertically centered beside ${edge.id}; center delta ${Math.abs(labelCenter.y - midY).toFixed(1)} > ${centerTolerance.toFixed(1)}.`);
      }
      if (labelBox.x < segmentX + rule.minGap || gap < rule.minGap || gap > rule.maxGap) {
        pushViolation(`Branch label ${labelCell["@_id"]} gap beside ${edge.id} is ${gap.toFixed(1)}, expected ${rule.minGap}-${rule.maxGap}.`);
      }
    }
    for (const edgeBox of segmentBoxes(points, 3)) {
      if (overlaps(labelBox, edgeBox, 0)) {
        pushViolation(`Branch label ${labelCell["@_id"]} intersects its branch line ${edge.id}.`);
      }
    }
    for (const node of flowNodes) {
      if (overlaps(labelBox, boxOf(node), 2)) {
        pushViolation(`Branch label ${labelCell["@_id"]} overlaps node ${node["@_id"]}.`);
      }
    }
    if (overlaps(labelBox, forbiddenArea, 0)) {
      pushViolation(`Branch label ${labelCell["@_id"]} enters the forbidden title-block area.`);
    }
  }
  for (let left = 0; left < labelCells.length; left += 1) {
    for (let right = left + 1; right < labelCells.length; right += 1) {
      const a = labelCells[left];
      const b = labelCells[right];
      if (a === b || !labelCellById.has(String(a["@_id"] || "")) || !labelCellById.has(String(b["@_id"] || ""))) {
        continue;
      }
      if (overlaps(boxOf(a), boxOf(b), 2)) {
        pushViolation(`Branch label ${a["@_id"]} overlaps branch label ${b["@_id"]}.`);
      }
    }
  }
  return violations;
}

function validateNoLongBusLines(repoEdges, cellMap, model, metrics, rowMembership, colMembership, errors) {
  const longBusLines = [];
  const edgesTooManyBends = [];
  const routingEnvelopeViolations = [];
  const connectionLengthViolations = [];
  const verticalConnectionLengthViolations = [];
  const modelByEdgeId = new Map(model.edges.map((edge) => [edge.id, edge]));
  const modelById = new Map(model.nodes.map((node) => [node.id, node]));
  const mainRuleNodeIds = new Set((PROGRAM_SCHEME_LAYOUT_RULES.rows || []).flatMap((row) => row.nodes || []));
  const standardSameRowLengths = [];
  const requiredStraightPairs = new Set((PROGRAM_SCHEME_LAYOUT_RULES.requiredStraightEdges || []).map(([from, to]) => `${normalizeText(from)}->${normalizeText(to)}`));
  for (const edge of repoEdges) {
    const id = String(edge["@_id"] || "");
    const points = sourceTargetPointsWithPorts(edge, cellMap);
    if (!points) {
      continue;
    }
    const modelEdge = modelByEdgeId.get(id.replace(EDGE_PREFIX, ""));
    const sourceNode = modelById.get(modelEdge?.from);
    const targetNode = modelById.get(modelEdge?.to);
    const sourceText = normalizeText(sourceNode?.text || "");
    const targetText = normalizeText(targetNode?.text || "");
    const isDecisionBranch = sourceNode?.type === "decision" && Boolean(modelEdge?.label);
    const isAbnormalDecisionBranch = isDecisionBranch && ABNORMAL_BRANCH_LABELS.has(String(modelEdge?.label || "").trim());
    const isReturnEdge = modelEdge && ["return", "feedback", "loop"].includes(String(modelEdge.channel || ""));
    const sourceRow = rowMembership.get(modelEdge?.from);
    const targetRow = rowMembership.get(modelEdge?.to);
    const sourceCol = colMembership.get(modelEdge?.from);
    const targetCol = colMembership.get(modelEdge?.to);
    const sameMainRowAdjacent = sourceRow === targetRow && targetCol === sourceCol + 1 && mainRuleNodeIds.has(modelEdge?.from) && mainRuleNodeIds.has(modelEdge?.to);
    const requiredStraight = requiredStraightPairs.has(`${sourceText}->${targetText}`);
    const maxBends = isReturnEdge
      ? LONG_LINE_RULES.maxReturnBends
      : isDecisionBranch && ABNORMAL_BRANCH_LABELS.has(String(modelEdge?.label || "").trim())
        ? LONG_LINE_RULES.maxDecisionAbnormalBends
        : LONG_LINE_RULES.maxBends;
    const bends = bendCountOf(points);
    if (bends > maxBends) {
      const message = `Edge ${id} has ${bends} bend(s), exceeding the maximum of ${maxBends}.`;
      edgesTooManyBends.push(message);
      fail(errors, message);
    }
    if ((sameMainRowAdjacent || requiredStraight) && LONG_LINE_RULES.forbidSameRowDoglegs) {
      const direct = points.length === 2 && Math.abs(points[0].y - points[1].y) <= 0.1 && points[0].x < points[1].x;
      if (!direct) {
        const message = `Edge ${id} must be a same-row straight horizontal connection; doglegs or reverse segments are forbidden.`;
        longBusLines.push(message);
        fail(errors, message);
      }
    }
    const segmentLimit = metrics.U * (isReturnEdge
      ? LONG_LINE_RULES.maxReturnSegmentU
      : isDecisionBranch
        ? LONG_LINE_RULES.maxDecisionSegmentU
        : LONG_LINE_RULES.maxSegmentLengthU);
    for (const segment of segmentLengths(points)) {
      if (segment.length > segmentLimit + 0.01) {
        const message = `Edge ${id} contains a segment of length ${segment.length.toFixed(3)}, exceeding ${segmentLimit.toFixed(3)}.`;
        longBusLines.push(message);
        fail(errors, message);
      }
    }
    const hasBend = bends > 0;
    const requiresFixedVerticalSegment = segmentLengths(points).some((segment) => segment.orthogonal && segment.dy > 0.1 && segment.dx <= 0.1) && (
      sourceNode?.type === "connector" ||
      targetNode?.type === "connector" ||
      (isAbnormalDecisionBranch && !hasBend)
    );
    if (requiresFixedVerticalSegment) {
      const verticalStandard = LONG_LINE_RULES.globalStandardVerticalSegmentLengthPx || CONNECTOR_LOCALITY_RULES.localEdgeClarity?.verticalTargetLengthPx || metrics.U;
      const verticalTolerance = metrics.U * (LONG_LINE_RULES.verticalSegmentLengthToleranceU || LONG_LINE_RULES.standardSegmentLengthToleranceU || 0.08);
      for (const segment of segmentLengths(points).filter((candidate) => candidate.orthogonal && candidate.dy > 0.1 && candidate.dx <= 0.1)) {
        if (Math.abs(segment.length - verticalStandard) > verticalTolerance + 0.01) {
          const message = `Vertical connection length uniformity violation: ${id} vertical segment ${segment.length.toFixed(1)} differs from global vertical standard ${verticalStandard.toFixed(1)} by more than ${verticalTolerance.toFixed(1)}.`;
          verticalConnectionLengthViolations.push(message);
          fail(errors, message);
        }
      }
    }
    if (sameMainRowAdjacent && !isDecisionBranch && sourceNode?.type !== "connector" && targetNode?.type !== "connector") {
      const totalLength = routeTotalLength(points);
      standardSameRowLengths.push({ id, totalLength });
    }
    const merged = mergedOrthogonalSegments(points);
    for (const segment of merged) {
      if (segment.length > segmentLimit + 0.01) {
        const message = `Edge ${id} has a merged orthogonal segment of length ${segment.length.toFixed(3)}, exceeding ${segmentLimit.toFixed(3)}.`;
        longBusLines.push(message);
        fail(errors, message);
      }
    }
    const sourceBox = boxOf(cellMap.get(String(edge["@_source"] || "")));
    const targetBox = boxOf(cellMap.get(String(edge["@_target"] || "")));
    const bbox = {
      x: Math.min(...points.map((point) => point.x)),
      y: Math.min(...points.map((point) => point.y)),
      width: Math.max(...points.map((point) => point.x)) - Math.min(...points.map((point) => point.x)),
      height: Math.max(...points.map((point) => point.y)) - Math.min(...points.map((point) => point.y))
    };
    const maxWidth = (sourceBox.width + targetBox.width) + metrics.U * (isReturnEdge ? LONG_LINE_RULES.maxReturnColumnsSpanned : LONG_LINE_RULES.maxEdgeColumnsSpanned);
    if (bbox.width > maxWidth + 0.01) {
      const message = `Edge ${id} spans too many columns horizontally: ${bbox.width.toFixed(3)} > ${maxWidth.toFixed(3)}.`;
      longBusLines.push(message);
      fail(errors, message);
    }
    const rowGapLimitMultiplier = isReturnEdge
      ? LONG_LINE_RULES.maxDecisionAbnormalRowGapsSpanned
      : isDecisionBranch && ABNORMAL_BRANCH_LABELS.has(String(modelEdge?.label || "").trim())
      ? LONG_LINE_RULES.maxDecisionAbnormalRowGapsSpanned
      : LONG_LINE_RULES.maxEdgeRowGapsSpanned;
    if (bbox.height > metrics.rowGap * rowGapLimitMultiplier + 0.01) {
      const message = `Edge ${id} spans too many row gaps vertically: ${bbox.height.toFixed(3)} > ${(metrics.rowGap * rowGapLimitMultiplier).toFixed(3)}.`;
      longBusLines.push(message);
      fail(errors, message);
    }
    const envelope = routeEnvelopeForEdge(points, sourceBox, targetBox, metrics.U * ROUTING_ENVELOPE_RULES.marginU);
    for (const point of points) {
      if (point.x < envelope.minX - 0.01 || point.x > envelope.maxX + 0.01 || point.y < envelope.minY - 0.01 || point.y > envelope.maxY + 0.01) {
        const message = `Edge ${id} has waypoint outside local routing envelope.`;
        routingEnvelopeViolations.push(message);
        fail(errors, message);
        break;
      }
    }
  }
  if (standardSameRowLengths.length >= 3) {
    const standard = LONG_LINE_RULES.globalStandardSegmentLengthPx || metrics.U;
    const tolerance = metrics.U * LONG_LINE_RULES.standardSegmentLengthToleranceU;
    for (const item of standardSameRowLengths) {
      if (Math.abs(item.totalLength - standard) > tolerance + 0.01) {
        const message = `Connection length uniformity violation: ${item.id} length ${item.totalLength.toFixed(1)} differs from global standard ${standard.toFixed(1)} by more than ${tolerance.toFixed(1)}.`;
        connectionLengthViolations.push(message);
        fail(errors, message);
      }
    }
  }
  return { longBusLines, edgesTooManyBends, routingEnvelopeViolations, connectionLengthViolations, verticalConnectionLengthViolations };
}

function validateVisualBalance(flowNodes, metrics, model, errors) {
  const violations = [];
  const area = VISUAL_BALANCE_RULES.upperRightFocusArea;
  const nodesInArea = [];
  const rowBands = new Set();
  const colBands = new Set();
  const rowGap = Number(metrics.rowGap || 1);
  const unit = Number(metrics.U || 1);
  const modelNodeByRepoId = new Map(model.nodes.map((node) => [`${ID_PREFIX}${node.id}`, node]));
  for (const node of flowNodes) {
    const box = boxOf(node);
    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;
    if (centerX >= area.x && centerX <= area.x + area.width && centerY >= area.y && centerY <= area.y + area.height) {
      nodesInArea.push(node);
      rowBands.add(Math.floor((centerY - area.y) / Math.max(1, rowGap)));
      colBands.add(Math.floor((centerX - area.x) / Math.max(1, unit)));
    }
  }
  if (nodesInArea.length < VISUAL_BALANCE_RULES.minNodeCount) {
    const message = `Visual balance: upper-right focus area has only ${nodesInArea.length} nodes; expected at least ${VISUAL_BALANCE_RULES.minNodeCount}.`;
    violations.push(message);
    fail(errors, message);
  }
  if (rowBands.size < VISUAL_BALANCE_RULES.minDistinctRowBands) {
    const message = `Visual balance: upper-right focus area uses only ${rowBands.size} distinct row bands; expected at least ${VISUAL_BALANCE_RULES.minDistinctRowBands}.`;
    violations.push(message);
    fail(errors, message);
  }
  if (colBands.size < VISUAL_BALANCE_RULES.minDistinctColumnBands) {
    const message = `Visual balance: upper-right focus area uses only ${colBands.size} distinct column bands; expected at least ${VISUAL_BALANCE_RULES.minDistinctColumnBands}.`;
    violations.push(message);
    fail(errors, message);
  }
  const bandCenters = [];
  for (const node of nodesInArea) {
    const box = boxOf(node);
    const id = String(node["@_id"] || "").replace(ID_PREFIX, "");
    const modelNode = modelNodeByRepoId.get(String(node["@_id"] || ""));
    const localBranchIds = new Set(ROW_WRAP_RULES.localBranchNodeIds || []);
    if (modelNode?.type === "connector" || localBranchIds.has(id)) {
      continue;
    }
    const centerY = box.y + box.height / 2;
    const existing = bandCenters.find((band) => Math.abs(band.center - centerY) <= PROGRAM_SCHEME_LAYOUT_RULES.laneCenterTolerance);
    if (existing) {
      existing.values.push(centerY);
      existing.center = existing.values.reduce((sum, value) => sum + value, 0) / existing.values.length;
    } else {
      bandCenters.push({ center: centerY, values: [centerY] });
    }
  }
  bandCenters.sort((a, b) => a.center - b.center);
  if (bandCenters.length >= 3) {
    const gaps = [];
    for (let index = 1; index < bandCenters.length; index += 1) {
      gaps.push(bandCenters[index].center - bandCenters[index - 1].center);
    }
    for (const [index, gap] of gaps.entries()) {
      if (gap < VISUAL_BALANCE_RULES.upperRightMinLaneGap || gap > VISUAL_BALANCE_RULES.upperRightMaxLaneGap) {
        const message = `Visual balance: upper-right lane gap ${index + 1} is ${gap.toFixed(1)}, expected ${VISUAL_BALANCE_RULES.upperRightMinLaneGap}-${VISUAL_BALANCE_RULES.upperRightMaxLaneGap}.`;
        violations.push(message);
        fail(errors, message);
      }
    }
    const avgGap = gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length;
    for (const [index, gap] of gaps.entries()) {
      if (Math.abs(gap - avgGap) > VISUAL_BALANCE_RULES.upperRightLaneGapTolerance) {
        const message = `Visual balance: upper-right lane gap ${index + 1} is uneven (${gap.toFixed(1)} vs average ${avgGap.toFixed(1)}).`;
        violations.push(message);
        fail(errors, message);
      }
    }
  }
  return violations;
}

function validateProgramSchemeLayout(model, metrics, flowNodes, repoEdges, cellMap, rowMembership, colMembership, errors) {
  const violations = [];
  const push = (message) => {
    violations.push(message);
    fail(errors, message);
  };
  const flowCellByModelId = new Map();
  for (const node of flowNodes) {
    flowCellByModelId.set(String(node["@_id"] || "").replace(ID_PREFIX, ""), node);
  }
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const localBranchIds = new Set(ROW_WRAP_RULES.localBranchNodeIds || []);
  const ruleMainRows = PROGRAM_SCHEME_LAYOUT_RULES.rows || [];
  const ruleMainNodeIds = new Set(ruleMainRows.flatMap((row) => row.nodes || []));
  const rows = metrics.rows || [];
  if (rows.length > ROW_WRAP_RULES.maxPhysicalRows) {
    push(`Program scheme layout uses ${rows.length} rows; maximum is ${ROW_WRAP_RULES.maxPhysicalRows}.`);
  }
  const allLaneNodes = new Set(rows.flat().filter(Boolean));
  for (const node of model.nodes) {
    if (!allLaneNodes.has(node.id)) {
      push(`Program scheme layout rule does not place node ${node.id}:${node.text}.`);
    }
  }
  for (let laneIndex = 0; laneIndex < rows.length; laneIndex += 1) {
    const ids = rows[laneIndex] || [];
    const ruleMainIds = new Set((ruleMainRows[laneIndex]?.nodes || []).filter(Boolean));
    const laneCenterCells = ids
      .filter((id) => ruleMainIds.has(id) && nodeById.get(id)?.type !== "connector" && !localBranchIds.has(id))
      .map((id) => flowCellByModelId.get(id))
      .filter(Boolean);
    const boxes = (laneCenterCells.length ? laneCenterCells : ids.map((id) => flowCellByModelId.get(id)).filter(Boolean)).map(boxOf);
    if (!boxes.length) {
      push(`Program scheme lane ${laneIndex + 1} has no visible nodes.`);
      continue;
    }
    const centers = boxes.map((box) => box.y + box.height / 2);
    const averageCenter = centers.reduce((sum, value) => sum + value, 0) / centers.length;
    for (const [index, id] of ids.entries()) {
      const cell = flowCellByModelId.get(id);
      if (!cell) {
        push(`Program scheme lane ${laneIndex + 1} is missing node ${id}.`);
        continue;
      }
      const box = boxOf(cell);
      const centerY = box.y + box.height / 2;
      const node = nodeById.get(id);
      const isLocalConnector = node?.type === "connector";
      const isLocalBranch = localBranchIds.has(id) || !ruleMainIds.has(id);
      const tolerance = node?.type === "connector"
        ? PROGRAM_SCHEME_LAYOUT_RULES.connectorLaneTolerance
        : PROGRAM_SCHEME_LAYOUT_RULES.laneCenterTolerance;
      if (!isLocalConnector && !isLocalBranch && Math.abs(centerY - averageCenter) > tolerance) {
        push(`Program scheme node ${id} is not aligned with lane ${laneIndex + 1}; delta ${Math.abs(centerY - averageCenter).toFixed(1)} > ${tolerance}.`);
      }
      if (index > 0 && node?.type !== "connector" && !isLocalBranch) {
        const previousMainId = ids.slice(0, index).reverse().find((candidateId) => {
          const candidate = nodeById.get(candidateId);
          return ruleMainIds.has(candidateId) && candidate?.type !== "connector" && !localBranchIds.has(candidateId);
        });
        const prevCell = previousMainId ? flowCellByModelId.get(previousMainId) : null;
        const prevNode = previousMainId ? nodeById.get(previousMainId) : null;
        if (prevCell && prevNode?.type !== "connector") {
          const prevBox = boxOf(prevCell);
          const gap = box.x - (prevBox.x + prevBox.width);
          if (gap < PROGRAM_SCHEME_LAYOUT_RULES.minColumnGap) {
            push(`Program scheme nodes ${previousMainId} and ${id} are too close in lane ${laneIndex + 1}: ${gap.toFixed(1)} < ${PROGRAM_SCHEME_LAYOUT_RULES.minColumnGap}.`);
          }
          const maxGap = PROGRAM_SCHEME_LAYOUT_RULES.maxColumnGap + metrics.U * 0.05;
          if (gap > maxGap) {
            push(`Program scheme nodes ${previousMainId} and ${id} are too far apart in lane ${laneIndex + 1}: ${gap.toFixed(1)} > ${maxGap.toFixed(1)}.`);
          }
        }
      }
    }
    const nonConnectorBoxes = ids
      .map((id) => ({ id, cell: flowCellByModelId.get(id), node: nodeById.get(id) }))
      .filter((item) => item.cell && ruleMainIds.has(item.id) && item.node?.type !== "connector" && !localBranchIds.has(item.id))
      .map((item) => boxOf(item.cell));
    const mainLaneNodeCount = nonConnectorBoxes.length;
    if (laneIndex < rows.length - 1 && mainLaneNodeCount >= ROW_WRAP_RULES.minNodesForRightSlackCheck) {
      const rightmost = Math.max(...nonConnectorBoxes.map((box) => box.x + box.width));
      const rightBoundary = metrics.page.width - Math.round(metrics.page.width * 0.030);
      const slack = rightBoundary - rightmost;
      const maxSlack = ROW_WRAP_RULES.maxMainRowRightSlackPx ?? ROW_WRAP_RULES.wrapTriggerSlackPx;
      if (slack > maxSlack) {
        push(`Program scheme lane ${laneIndex + 1} wraps too early with ${slack.toFixed(1)} px still available; wrap only when slack <= ${maxSlack}.`);
      }
    }
  }
  for (let index = 1; index < rows.length; index += 1) {
    const previousRuleIds = new Set((ruleMainRows[index - 1]?.nodes || []).filter(Boolean));
    const currentRuleIds = new Set((ruleMainRows[index]?.nodes || []).filter(Boolean));
    const previousBoxes = (rows[index - 1] || [])
      .filter((id) => previousRuleIds.has(id) && !localBranchIds.has(id))
      .map((id) => flowCellByModelId.get(id))
      .filter(Boolean)
      .map(boxOf);
    const currentBoxes = (rows[index] || [])
      .filter((id) => currentRuleIds.has(id) && !localBranchIds.has(id))
      .map((id) => flowCellByModelId.get(id))
      .filter(Boolean)
      .map(boxOf);
    if (!previousBoxes.length || !currentBoxes.length) {
      continue;
    }
    const previousCenter = previousBoxes.reduce((sum, box) => sum + box.y + box.height / 2, 0) / previousBoxes.length;
    const currentCenter = currentBoxes.reduce((sum, box) => sum + box.y + box.height / 2, 0) / currentBoxes.length;
    const gap = currentCenter - previousCenter;
    if (gap < PROGRAM_SCHEME_LAYOUT_RULES.minLaneGap || gap > PROGRAM_SCHEME_LAYOUT_RULES.maxLaneGap + 32) {
      push(`Program scheme lane gap ${index}->${index + 1} is ${gap.toFixed(1)}, expected ${PROGRAM_SCHEME_LAYOUT_RULES.minLaneGap}-${PROGRAM_SCHEME_LAYOUT_RULES.maxLaneGap + 32}.`);
    }
  }
  for (const chain of PROGRAM_SCHEME_LAYOUT_RULES.requiredCleanHorizontalChains || []) {
    for (let index = 1; index < chain.length; index += 1) {
      const from = chain[index - 1];
      const to = chain[index];
      const fromCell = flowCellByModelId.get(from);
      const toCell = flowCellByModelId.get(to);
      if (!fromCell || !toCell) {
        continue;
      }
      const fromNode = nodeById.get(from);
      const toNode = nodeById.get(to);
      if (fromNode?.type === "connector" || toNode?.type === "connector") {
        continue;
      }
      const fromBox = boxOf(fromCell);
      const toBox = boxOf(toCell);
      if (toBox.x <= fromBox.x) {
        push(`Program scheme chain must read left-to-right: ${from} -> ${to}.`);
      }
    }
  }
  const edgeById = new Map(model.edges.map((edge) => [edge.id, edge]));
  const allowedReverseChannels = new Set(PROGRAM_SCHEME_LAYOUT_RULES.allowedReverseEdgeChannels || []);
  for (const edge of repoEdges) {
    const modelEdge = edgeById.get(String(edge["@_id"] || "").replace(EDGE_PREFIX, ""));
    if (!modelEdge) {
      continue;
    }
    const sourceNode = nodeById.get(modelEdge.from);
    const targetNode = nodeById.get(modelEdge.to);
    const sourceRow = rowMembership.get(modelEdge.from);
    const targetRow = rowMembership.get(modelEdge.to);
    const sourceCol = colMembership.get(modelEdge.from);
    const targetCol = colMembership.get(modelEdge.to);
    const channel = String(modelEdge.channel || "");
    const connectorLocal = sourceNode?.type === "connector" || targetNode?.type === "connector";
    const rowSpan = Math.abs((targetRow ?? sourceRow) - (sourceRow ?? targetRow));
    if (!connectorLocal && !allowedReverseChannels.has(channel) && Number.isInteger(sourceCol) && Number.isInteger(targetCol) && sourceRow === targetRow && targetCol < sourceCol) {
      push(`Program scheme ordinary edge ${modelEdge.id} runs right-to-left inside a lane.`);
    }
    if (!connectorLocal && rowSpan > PROGRAM_SCHEME_LAYOUT_RULES.maxNonConnectorLaneSpan) {
      push(`Program scheme ordinary edge ${modelEdge.id} spans ${rowSpan} lanes without a connector.`);
    }
    if (connectorLocal && rowSpan > PROGRAM_SCHEME_LAYOUT_RULES.maxConnectorLaneSpan) {
      push(`Program scheme connector edge ${modelEdge.id} spans ${rowSpan} lanes, too far for a local connector edge.`);
    }
  }
  for (const node of flowNodes) {
    const center = centerOf(node);
    let neighbors = 0;
    for (const other of flowNodes) {
      if (other === node) continue;
      if (Math.hypot(center.x - centerOf(other).x, center.y - centerOf(other).y) <= metrics.U * PROGRAM_SCHEME_LAYOUT_RULES.tightAreaRadiusU) {
        neighbors += 1;
      }
    }
    if (neighbors > PROGRAM_SCHEME_LAYOUT_RULES.maxNodesPerTightArea) {
      push(`Program scheme local area around ${node["@_id"]} is crowded with ${neighbors + 1} nodes.`);
    }
  }
  return violations;
}

function validateVisualCrowding(repoEdges, flowNodes, cellMap, metrics, errors) {
  const visualCrowdingViolations = [];
  const clearance = metrics.U * VISUAL_DENSITY_RULES.minNodeClearanceU;
  const parallelGap = metrics.U * VISUAL_DENSITY_RULES.minParallelSegmentGapU;
  const edgeSegments = [];

  for (const edge of repoEdges) {
    const sourceId = String(edge["@_source"] || "");
    const targetId = String(edge["@_target"] || "");
    const points = sourceTargetPointsWithPorts(edge, cellMap);
    if (!points) {
      continue;
    }
    edgeSegments.push(...orthogonalSegmentDescriptors(edge, points));
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      for (const node of flowNodes) {
        const nodeId = String(node["@_id"] || "");
        if (nodeId === sourceId || nodeId === targetId) {
          continue;
        }
        const gap = segmentToBoxClearance(a, b, boxOf(node));
        if (gap < clearance - 0.01) {
          const message = `Visual crowding: edge ${edge["@_id"]} is too close to ${nodeId}: ${gap.toFixed(1)} < ${clearance.toFixed(1)}.`;
          visualCrowdingViolations.push(message);
          fail(errors, message);
          break;
        }
      }
    }
  }

  for (let left = 0; left < edgeSegments.length; left += 1) {
    for (let right = left + 1; right < edgeSegments.length; right += 1) {
      const a = edgeSegments[left];
      const b = edgeSegments[right];
      if (a.edgeId === b.edgeId || a.orientation !== b.orientation) {
        continue;
      }
      const overlap = Math.min(a.max, b.max) - Math.max(a.min, b.min);
      if (overlap <= Math.min(metrics.U * 0.18, 24)) {
        continue;
      }
      const aEdge = cellMap.get(a.edgeId);
      const bEdge = cellMap.get(b.edgeId);
      if (aEdge && bEdge && aEdge["@_source"] && aEdge["@_source"] === bEdge["@_source"] && overlap <= metrics.U * 1.20) {
        continue;
      }
      const gap = Math.abs(a.axis - b.axis);
      if (gap < parallelGap - 0.01) {
        const message = `Visual crowding: parallel segments ${a.edgeId} and ${b.edgeId} are too close: ${gap.toFixed(1)} < ${parallelGap.toFixed(1)}.`;
        visualCrowdingViolations.push(message);
        fail(errors, message);
      }
    }
  }

  for (let left = 0; left < flowNodes.length; left += 1) {
    for (let right = left + 1; right < flowNodes.length; right += 1) {
      const a = flowNodes[left];
      const b = flowNodes[right];
      if (overlaps(expandedBox(boxOf(a), clearance), boxOf(b), 0)) {
        const message = `Visual crowding: nodes ${a["@_id"]} and ${b["@_id"]} are closer than ${clearance.toFixed(1)}.`;
        visualCrowdingViolations.push(message);
        fail(errors, message);
      }
    }
  }

  return visualCrowdingViolations;
}

function segmentIntersection(a, b) {
  if (a.orientation === b.orientation) {
    return null;
  }
  const horizontal = a.orientation === "h" ? a : b;
  const vertical = a.orientation === "v" ? a : b;
  const x = vertical.axis;
  const y = horizontal.axis;
  if (x <= horizontal.min + 1 || x >= horizontal.max - 1) {
    return null;
  }
  if (y <= vertical.min + 1 || y >= vertical.max - 1) {
    return null;
  }
  return { x, y };
}

function validateNoEdgeCrossings(repoEdges, cellMap, errors) {
  const edgeCrossingViolations = [];
  const segments = [];
  for (const edge of repoEdges) {
    const points = sourceTargetPointsWithPorts(edge, cellMap);
    if (!points) {
      continue;
    }
    segments.push(...orthogonalSegmentDescriptors(edge, points));
  }
  for (let left = 0; left < segments.length; left += 1) {
    for (let right = left + 1; right < segments.length; right += 1) {
      const a = segments[left];
      const b = segments[right];
      if (a.edgeId === b.edgeId) {
        continue;
      }
      const crossing = segmentIntersection(a, b);
      if (!crossing) {
        continue;
      }
      const message = `Edge crossing: ${a.edgeId} crosses ${b.edgeId} at (${crossing.x.toFixed(1)}, ${crossing.y.toFixed(1)}).`;
      edgeCrossingViolations.push(message);
      fail(errors, message);
    }
  }
  return edgeCrossingViolations;
}

function segmentIntersectsNode(points, sourceId, targetId, flowNodes, cellMap) {
  const blocked = flowNodes.filter((cell) => {
    const id = String(cell["@_id"] || "");
    return id !== sourceId && id !== targetId;
  });
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    if (Math.abs(a.y - b.y) <= 0.1) {
      const x1 = Math.min(a.x, b.x);
      const x2 = Math.max(a.x, b.x);
      const y = a.y;
      for (const node of blocked) {
        const box = boxOf(node);
        if (y > box.y + 2 && y < box.y + box.height - 2 && x2 > box.x + 2 && x1 < box.x + box.width - 2) {
          return true;
        }
      }
    }
    if (Math.abs(a.x - b.x) <= 0.1) {
      const y1 = Math.min(a.y, b.y);
      const y2 = Math.max(a.y, b.y);
      const x = a.x;
      for (const node of blocked) {
        const box = boxOf(node);
        if (x > box.x + 2 && x < box.x + box.width - 2 && y2 > box.y + 2 && y1 < box.y + box.height - 2) {
          return true;
        }
      }
    }
  }
  return false;
}

function isSameRowAdjacent(edge, rowMembership, colMembership) {
  const sourceRow = rowMembership.get(edge.from);
  const targetRow = rowMembership.get(edge.to);
  const sourceCol = colMembership.get(edge.from);
  const targetCol = colMembership.get(edge.to);
  return sourceRow === targetRow && targetCol === sourceCol + 1;
}

function buildLogicalGraph(model) {
  const adjacency = new Map();
  const reverse = new Map();
  const logicalEdges = [];
  for (const node of model.nodes) {
    adjacency.set(node.id, []);
    reverse.set(node.id, []);
  }
  const addEdge = (from, to, id, channel = "model") => {
    if (!adjacency.has(from) || !reverse.has(to)) {
      return;
    }
    adjacency.get(from).push(to);
    reverse.get(to).push(from);
    logicalEdges.push({ id, from, to, channel });
  };
  for (const edge of model.edges) {
    addEdge(edge.from, edge.to, edge.id, edge.channel || "model");
  }
  for (const pair of model.connectors || []) {
    const nodes = pair.nodes || [];
    if (nodes.length === 2) {
      addEdge(nodes[0], nodes[1], `connector_${pair.label}_forward`, "connector_pair");
      addEdge(nodes[1], nodes[0], `connector_${pair.label}_reverse`, "connector_pair");
    }
  }
  return { adjacency, reverse, logicalEdges };
}

function reachableFrom(start, adjacency) {
  const seen = new Set([start]);
  const queue = [start];
  while (queue.length) {
    const current = queue.shift();
    for (const next of adjacency.get(current) || []) {
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }
  return seen;
}

function validateConnectorSemantics(model, errors) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const edges = model.edges;
  const hasEdgeByText = (from, to, label = "") => findEdges(model, from, to, label).length > 0;
  const connectors = new Map();
  for (const node of model.nodes.filter((candidate) => candidate.type === "connector")) {
    const list = connectors.get(node.text) || [];
    list.push(node.id);
    connectors.set(node.text, list);
  }

  for (const [label, rule] of Object.entries(CONNECTOR_RULES)) {
    const actual = connectors.get(label) || [];
    if (actual.length !== 2) {
      fail(errors, `Connector ${label} must appear exactly twice for ${rule.meaning}.`);
    }
    for (const [from, to] of rule.requiredEdges || []) {
      if (!hasEdgeByText(from, to)) {
        fail(errors, `Connector ${label} semantic edge is missing: ${from} -> ${to}.`);
      }
    }
    for (const [from, to] of rule.forbidden || []) {
      if (hasEdgeByText(from, to)) {
        fail(errors, `Connector ${label} uses forbidden semantic edge: ${from} -> ${to}.`);
      }
    }
  }

  for (const edge of edges) {
    const fromNode = nodeById.get(edge.from);
    const toNode = nodeById.get(edge.to);
    if (fromNode?.type === "connector" && !/^R[0-9]+$/.test(fromNode.text) && edge.channel === "grid_continuation") {
      fail(errors, `Semantic connector ${fromNode.text} is used as row continuation by ${edge.id}.`);
    }
    if (toNode?.type === "connector" && !/^R[0-9]+$/.test(toNode.text) && edge.channel === "grid_continuation") {
      fail(errors, `Semantic connector ${toNode.text} is used as row continuation by ${edge.id}.`);
    }
  }
}

function validateRequiredLogic(model, errors) {
  for (const [from, to, label = ""] of REQUIRED_LOGIC_EDGES) {
    if (!findEdges(model, from, to, label).length) {
      fail(errors, `Required logic edge is missing: ${from} -> ${to}${label ? ` [${label}]` : ""}.`);
    }
  }
}

function validateControlBlockRules(model, errors) {
  const violations = [];
  const push = (message) => {
    violations.push(message);
    fail(errors, message);
  };
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  const nodeIdsByText = new Map();
  for (const node of model.nodes) {
    const key = normalizeText(node.text);
    const ids = nodeIdsByText.get(key) || [];
    ids.push(node.id);
    nodeIdsByText.set(key, ids);
  }
  const hasEdgeByText = (from, to, label = "") => findEdges(model, from, to, label).length > 0;
  const rule = CONTROL_BLOCK_RULES.safetyMerge;
  if (!rule) {
    return violations;
  }
  if ((nodeIdsByText.get(normalizeText(rule.node)) || []).length !== 1) {
    push(`Control block must contain exactly one ${rule.node} node.`);
  }
  for (const [from, to, label = ""] of rule.requiredIncoming || []) {
    if (!hasEdgeByText(from, to, label)) {
      push(`Control block merge edge is missing: ${from} -> ${to}${label ? ` [${label}]` : ""}.`);
    }
  }
  for (const [from, to, label = ""] of rule.requiredOutgoing || []) {
    if (!hasEdgeByText(from, to, label)) {
      push(`Control block merge output is missing: ${from} -> ${to}${label ? ` [${label}]` : ""}.`);
    }
  }
  for (const [from, to, label = ""] of rule.forbiddenDirectEdges || []) {
    if (hasEdgeByText(from, to, label)) {
      push(`Control block forbids crowded direct edge: ${from} -> ${to}${label ? ` [${label}]` : ""}; route through ${rule.node}.`);
    }
  }
  const safetyIds = nodeIdsByText.get(normalizeText("Safety Check?")) || [];
  if (safetyIds.length === 1) {
    const incoming = model.edges.filter((edge) => edge.to === safetyIds[0]);
    const incomingTexts = incoming.map((edge) => normalizeText(nodeById.get(edge.from)?.text));
    const expected = normalizeText(rule.safetyCheckPrimaryIncoming?.[0] || "");
    if (incoming.length !== 1 || incomingTexts[0] !== expected) {
      push(`Safety Check? must have exactly one primary incoming edge from ${rule.safetyCheckPrimaryIncoming?.[0]}; found ${incomingTexts.join(", ") || "none"}.`);
    }
  }
  return violations;
}

function validateConnectorVisualLocality(model, metrics, flowNodes, repoEdges, cellMap, errors) {
  const repoIdByText = new Map();
  const repoIdByExactText = new Map();
  for (const node of model.nodes) {
    const key = normalizeText(node.text);
    const ids = repoIdByText.get(key) || [];
    ids.push(`${ID_PREFIX}${node.id}`);
    repoIdByText.set(key, ids);
    const exactIds = repoIdByExactText.get(node.text) || [];
    exactIds.push(`${ID_PREFIX}${node.id}`);
    repoIdByExactText.set(node.text, exactIds);
  }
  const connectorCellsByText = new Map();
  for (const node of model.nodes.filter((candidate) => candidate.type === "connector")) {
    const ids = connectorCellsByText.get(node.text) || [];
    ids.push(`${ID_PREFIX}${node.id}`);
    connectorCellsByText.set(node.text, ids);
  }
  const hasVisibleEdge = (fromText, toText) => {
    const fromIds = new Set(repoIdByText.get(normalizeText(fromText)) || []);
    const toIds = new Set(repoIdByText.get(normalizeText(toText)) || []);
    return repoEdges.some((edge) => fromIds.has(String(edge["@_source"] || "")) && toIds.has(String(edge["@_target"] || "")));
  };
  const invalidLocality = [];
  const isolatedConnectors = [];
  const connectorLocalEdgeClarityViolations = [];
  const requireNear = (connectorLabel, connectorIndex, targetText, limitMultiplier) => {
    const connectorIds = connectorCellsByText.get(connectorLabel) || [];
    const connector = cellMap.get(connectorIds[connectorIndex]);
    const targets = repoIdByExactText.get(targetText) || repoIdByText.get(normalizeText(targetText)) || [];
    if (!connector || !targets.length) {
      fail(errors, `Connector ${connectorLabel} locality check cannot find ${targetText}.`);
      return;
    }
    const nearest = Math.min(...targets.map((id) => distanceBetweenCells(connector, cellMap.get(id))));
    const limit = metrics.U * limitMultiplier;
    if (nearest > limit) {
      const message = `Connector ${connectorLabel} endpoint ${connectorIndex + 1} is too far from ${targetText}: ${nearest.toFixed(1)} > ${limit.toFixed(1)}.`;
      invalidLocality.push(message);
      fail(errors, message);
    }
  };

  for (const [connectorLabel, anchors] of Object.entries(CONNECTOR_LOCALITY_RULES.semanticAnchors || {})) {
    anchors.forEach((anchor, index) => {
      requireNear(connectorLabel, index, anchor.near, CONNECTOR_LOCALITY_RULES.maxBusinessNodeDistanceU);
    });
  }

  for (const [label, ids] of connectorCellsByText.entries()) {
    if (ids.length === 2) {
      const first = cellMap.get(ids[0]);
      const second = cellMap.get(ids[1]);
      if (first && second) {
        const gap = distanceBetweenCells(first, second);
        const minGap = metrics.U * CONNECTOR_LOCALITY_RULES.minConnectorCenterDistanceU;
        if (gap < minGap) {
          const message = `Connector pair ${label} is too close: ${gap.toFixed(1)} < ${minGap.toFixed(1)}.`;
          invalidLocality.push(message);
          fail(errors, message);
        }
      }
    }
  }

  if (CONNECTOR_LOCALITY_RULES.forbidConnectorCrowding) {
    const allConnectorIds = Array.from(connectorCellsByText.values()).flat();
    const minGap = metrics.U * (CONNECTOR_LOCALITY_RULES.minDifferentConnectorCenterDistanceU || CONNECTOR_LOCALITY_RULES.minConnectorCenterDistanceU);
    for (let left = 0; left < allConnectorIds.length; left += 1) {
      for (let right = left + 1; right < allConnectorIds.length; right += 1) {
        const leftId = allConnectorIds[left];
        const rightId = allConnectorIds[right];
        const leftCell = cellMap.get(leftId);
        const rightCell = cellMap.get(rightId);
        if (!leftCell || !rightCell) {
          continue;
        }
        const leftLabel = decodeText(leftCell["@_value"]).trim();
        const rightLabel = decodeText(rightCell["@_value"]).trim();
        if (leftLabel === rightLabel) {
          continue;
        }
        const gap = distanceBetweenCells(leftCell, rightCell);
        if (gap < minGap) {
          const message = `Connector crowding: ${leftId}:${leftLabel} and ${rightId}:${rightLabel} are too close: ${gap.toFixed(1)} < ${minGap.toFixed(1)}.`;
          invalidLocality.push(message);
          fail(errors, message);
        }
      }
    }
  }

  const requiredVisibleConnectorEdges = CONNECTOR_LOCALITY_RULES.requiredVisibleLocalEdges;
  const clarity = CONNECTOR_LOCALITY_RULES.localEdgeClarity || {};
  for (const [from, to] of requiredVisibleConnectorEdges) {
    if (!hasVisibleEdge(from, to)) {
      fail(errors, `Connector local edge must be visibly rendered: ${from} -> ${to}.`);
      continue;
    }
    const fromIds = new Set(repoIdByText.get(normalizeText(from)) || []);
    const toIds = new Set(repoIdByText.get(normalizeText(to)) || []);
    const rendered = repoEdges.find((edge) => fromIds.has(String(edge["@_source"] || "")) && toIds.has(String(edge["@_target"] || "")));
    if (!rendered) {
      continue;
    }
    const points = sourceTargetPointsWithPorts(rendered, cellMap);
    if (!points) {
      const message = `Connector local edge ${from} -> ${to} has no resolvable geometry.`;
      connectorLocalEdgeClarityViolations.push(message);
      fail(errors, message);
      continue;
    }
    const sourceModelId = String(rendered["@_source"] || "").replace(ID_PREFIX, "");
    const targetModelId = String(rendered["@_target"] || "").replace(ID_PREFIX, "");
    const sourceIsConnector = model.nodes.find((node) => node.id === sourceModelId)?.type === "connector";
    const targetIsConnector = model.nodes.find((node) => node.id === targetModelId)?.type === "connector";
    if (!sourceIsConnector && !targetIsConnector) {
      const message = `Connector local edge ${from} -> ${to} does not touch a connector node.`;
      connectorLocalEdgeClarityViolations.push(message);
      fail(errors, message);
    }
    const totalLength = routeTotalLength(points);
    const span = routeSpan(points);
    const bends = bendCountOf(points);
    const verticalOnly = span.height > 0.1 && span.width <= 0.1;
    const horizontalOnly = span.width > 0.1 && span.height <= 0.1;
    const targetTotal = verticalOnly
      ? (clarity.verticalTargetLengthPx || clarity.targetLengthPx)
      : horizontalOnly
        ? (clarity.horizontalTargetLengthPx || clarity.targetLengthPx)
        : null;
    const targetTolerance = metrics.U * (verticalOnly
      ? (clarity.verticalLengthToleranceU ?? clarity.lengthToleranceU ?? 0.10)
      : (clarity.lengthToleranceU ?? 0.10));
    const minTotal = targetTotal == null ? metrics.U * (clarity.minTotalLengthU ?? 0) : targetTotal - targetTolerance;
    const maxTotal = targetTotal == null ? metrics.U * (clarity.maxTotalLengthU ?? Infinity) : targetTotal + targetTolerance;
    const maxSpan = metrics.U * (clarity.maxSpanU ?? Infinity);
    const maxBends = clarity.maxBends ?? Infinity;
    if (totalLength < minTotal - 0.01 || totalLength > maxTotal + 0.01) {
      const message = `Connector local edge ${from} -> ${to} length ${totalLength.toFixed(1)} is outside ${minTotal.toFixed(1)}-${maxTotal.toFixed(1)}.`;
      connectorLocalEdgeClarityViolations.push(message);
      fail(errors, message);
    }
    if (span.width > maxSpan + 0.01 || span.height > maxSpan + 0.01) {
      const message = `Connector local edge ${from} -> ${to} span ${span.width.toFixed(1)}x${span.height.toFixed(1)} exceeds ${maxSpan.toFixed(1)}.`;
      connectorLocalEdgeClarityViolations.push(message);
      fail(errors, message);
    }
    if (bends > maxBends) {
      const message = `Connector local edge ${from} -> ${to} has ${bends} bends; maximum is ${maxBends}.`;
      connectorLocalEdgeClarityViolations.push(message);
      fail(errors, message);
    }
  }

  for (const node of model.nodes.filter((candidate) => candidate.type === "connector")) {
    const repoId = `${ID_PREFIX}${node.id}`;
    const incident = repoEdges.filter((edge) => edge["@_source"] === repoId || edge["@_target"] === repoId);
    if (!incident.length) {
      const message = `Connector ${node.id}:${node.text} is visually isolated; it has no visible local edge.`;
      isolatedConnectors.push(message);
      fail(errors, message);
    }
  }

  return { invalidLocality, isolatedConnectors, connectorLocalEdgeClarityViolations };
}

function validateNoVisibleSyntheticEdges(repoEdges, errors) {
  const visibleSyntheticEdges = repoEdges
    .map((edge) => String(edge["@_id"] || ""))
    .filter((id) => SYNTHETIC_EDGE_RULES.forbiddenVisiblePrefixes.some((prefix) => id.startsWith(`${EDGE_PREFIX}${prefix}`)));
  if (visibleSyntheticEdges.length) {
    fail(errors, `Visible synthetic edges are forbidden: ${visibleSyntheticEdges.join(", ")}.`);
  }
  return visibleSyntheticEdges;
}

function validatePrimaryFlowDirection(model, rowMembership, colMembership, errors) {
  const violations = [];
  const allowedReverseChannels = new Set(PRIMARY_FLOW_DIRECTION_RULES.allowedReverseChannels || []);
  const chainViolations = [];
  for (const chain of PRIMARY_FLOW_DIRECTION_RULES.enforcedLeftToRightChains || []) {
    for (let index = 1; index < chain.length; index += 1) {
      const from = chain[index - 1];
      const to = chain[index];
      const edge = findEdges(model, from, to)[0];
      if (!edge) {
        continue;
      }
      const sourceIndex = chain.indexOf(from);
      const targetIndex = chain.indexOf(to);
      if (sourceIndex >= 0 && targetIndex >= 0 && targetIndex !== sourceIndex + 1) {
        continue;
      }
      const reverse = findEdges(model, to, from)[0];
      if (reverse) {
        const message = `Primary flow chain must run left-to-right: ${from} -> ${to}.`;
        chainViolations.push(message);
        fail(errors, message);
      }
    }
  }
  for (const edge of model.edges) {
    const sourceRow = rowMembership.get(edge.from);
    const targetRow = rowMembership.get(edge.to);
    if (!Number.isInteger(sourceRow) || !Number.isInteger(targetRow)) {
      continue;
    }
    const sourceCol = colMembership.get(edge.from);
    const targetCol = colMembership.get(edge.to);
    const channel = String(edge.channel || "model");
    if (sourceRow === targetRow && targetCol < sourceCol && !allowedReverseChannels.has(channel)) {
      const message = `Primary flow direction violation: ${edge.from} -> ${edge.to} runs right-to-left on row ${sourceRow + 1}.`;
      violations.push(message);
      fail(errors, message);
    }
    if (targetRow < sourceRow && !allowedReverseChannels.has(channel)) {
      const message = `Primary flow direction violation: ${edge.from} -> ${edge.to} runs bottom-to-top across rows ${sourceRow + 1} -> ${targetRow + 1}.`;
      violations.push(message);
      fail(errors, message);
    }
  }
  return { violations, chainViolations };
}

function validateTemplate(templateXml, drawioXml, errors) {
  if (!drawioXml.includes("<mxfile") || !drawioXml.includes("<mxGraphModel")) {
    fail(errors, "Output is not a draw.io mxfile.");
  }
  if (!drawioXml.includes('pageWidth="3300"') || !drawioXml.includes('pageHeight="2339"')) {
    fail(errors, "Template page dimensions are not preserved.");
  }
  const titleBlockToken = 'pFFQBGnBG81xobuCz_b_-1';
  if (!templateXml.includes(titleBlockToken) || !drawioXml.includes(titleBlockToken)) {
    fail(errors, "Original bottom-right title block group is not preserved.");
  }
}

function mmToPageX(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.width) * page.width;
}

function mmToPageY(mm, page) {
  return (mm / FRAME_RULES.physicalPageMm.height) * page.height;
}

function expectedFrameBox(page) {
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

function validateFrameRules(cellMap, page, errors) {
  const tolerance = 0.75;
  const expected = expectedFrameBox(page);
  const border = cellMap.get(FRAME_RULES.outerBorder.id);
  if (!border) {
    fail(errors, `A1 outer border ${FRAME_RULES.outerBorder.id} is missing.`);
    return;
  }
  const borderBox = boxOf(border);
  for (const key of ["x", "y", "width", "height"]) {
    if (Math.abs(borderBox[key] - expected[key]) > tolerance) {
      fail(errors, `A1 outer border ${key}=${borderBox[key].toFixed(2)} does not match expected ${expected[key].toFixed(2)}.`);
    }
  }
  const borderStyle = String(border["@_style"] || "");
  const borderStroke = Number((borderStyle.match(/strokeWidth=([0-9.]+)/) || [])[1]);
  if (Math.abs(borderStroke - FRAME_RULES.outerBorder.strokeWidth) > FRAME_RULES.titleBlock.strokeTolerance) {
    fail(errors, `A1 outer border strokeWidth=${borderStroke} does not match ${FRAME_RULES.outerBorder.strokeWidth}.`);
  }

  const title = cellMap.get(FRAME_RULES.titleBlock.id);
  if (!title) {
    fail(errors, `Title block ${FRAME_RULES.titleBlock.id} is missing.`);
    return;
  }
  const titleBox = boxOf(title);
  if (Math.abs((titleBox.x + titleBox.width) - (expected.x + expected.width)) > tolerance) {
    fail(errors, "Title block right edge is not aligned to the A1 outer frame.");
  }
  if (Math.abs((titleBox.y + titleBox.height) - (expected.y + expected.height)) > tolerance) {
    fail(errors, "Title block bottom edge is not aligned to the A1 outer frame.");
  }

  const allowed = [FRAME_RULES.titleBlock.thickStrokeWidth, FRAME_RULES.titleBlock.thinStrokeWidth];
  for (const cell of Array.from(cellMap.values())) {
    const id = String(cell["@_id"] || "");
    const parent = String(cell["@_parent"] || "");
    if (id !== FRAME_RULES.titleBlock.id && parent !== FRAME_RULES.titleBlock.id) {
      continue;
    }
    const style = String(cell["@_style"] || "");
    const match = style.match(/strokeWidth=([0-9.]+)/);
    if (!match) {
      continue;
    }
    const value = Number(match[1]);
    if (!allowed.some((item) => Math.abs(item - value) <= FRAME_RULES.titleBlock.strokeTolerance)) {
      fail(errors, `Title block cell ${id} uses non-reference strokeWidth=${value}; expected ${allowed.join(" or ")}.`);
    }
  }
}

function countValidationCategories(errors, baseCounters = {}) {
  const count = (pattern) => errors.filter((error) => pattern.test(error)).length;
  return {
    visibleSyntheticEdges: baseCounters.visibleSyntheticEdges || 0,
    isolatedConnectors: count(/visually isolated/i),
    diagonalEdges: count(/Diagonal segment/i),
    curveEdges: count(/Curved edge style/i),
    labelOverlaps: count(/label .*overlaps|label .*intersects|overlaps line segment/i),
    branchLabelPlacementErrors: count(/Branch label .*must|Branch label .*gap|Branch label .*intersects|Branch label .*enters|Decision branch .*label placement/i),
    shortArrowStemEdges: errors.filter((error) => /arrow stem is too short/i.test(error)),
    visualCrowdingViolations: errors.filter((error) => /Visual crowding/i.test(error)),
    invalidConnectorLocality: errors.filter((error) => /Connector .*too far|Connector local edge|visually isolated/i.test(error)),
    overusedConnectorResolvedEdges: errors.filter((error) => /connector-resolved|connectorResolvedEdgeIds/i.test(error)),
    longBusLines: errors.filter((error) => /segment of length|spans too many columns|spans too many row gaps|merged orthogonal segment|same-row straight|Connection length uniformity|Vertical connection length uniformity/i.test(error)),
    edgesTooManyBends: errors.filter((error) => /bend\(s\)/i.test(error)),
    routingEnvelopeViolations: errors.filter((error) => /routing envelope/i.test(error)),
    invalidArrowEdges: errors.filter((error) => /arrow/i.test(error))
  };
}

function writeComplianceReport(summary) {
  const statusText = summary.passed ? "PASSED" : "FAILED";
  const lines = [];
  lines.push("# Compliance Report");
  lines.push("");
  lines.push("## Validation Status");
  lines.push("");
  lines.push(`Final validation status: **${statusText}**.`);
  lines.push("");
  lines.push("This report is generated by `validate_drawio.js` from `validator_summary.json`. The validator summary is the source of truth; this file must not claim compliance when `validator_summary.json` has `passed=false`.");
  lines.push("");
  lines.push("## Template And Drawing Area");
  lines.push("");
  lines.push("- The final draw.io file is generated from `aa.drawio`.");
  lines.push("- The original A1 border and bottom-right title block are preserved.");
  lines.push(`- Page size: \`${summary.page.width} x ${summary.page.height}\`.`);
  lines.push(`- Forbidden title-block area: ` +
    `x=${summary.forbiddenArea.x}, y=${summary.forbiddenArea.y}, width=${summary.forbiddenArea.width}, height=${summary.forbiddenArea.height}.`);
  lines.push("- No generated flowchart node, branch label, or visible edge may enter the forbidden area.");
  lines.push("");
  lines.push("## Enforced Rule Set");
  lines.push("");
  lines.push("- `flow_rules.js` defines the shape ratios, connector semantics, decision branches, label aliases, and required closed-loop logic edges.");
  lines.push("- `render_drawio.js` uses those rules to generate editable draw.io `mxCell` nodes, explicit center-port orthogonal edges, and separate branch label cells.");
  lines.push("- `validate_drawio.js` checks the generated draw.io file, model logic, connector semantics, decision ports, label placement, reachability, and forbidden-area clearance.");
  lines.push("- The upper control block must route the `No` bypass and `Param ACK` return through `Safety Merge` before entering `Safety Check?`, preventing crowded multi-edge decision inputs.");
  lines.push("- Same-name connector pairs must be visually separated and locally connected; crowded duplicate-looking connector circles fail validation.");
  lines.push("- Connector local edges must be clear short visible links: they must touch a connector, stay within configured length/span limits, and avoid excessive bends.");
  lines.push("");
  lines.push("## Directional Arrow Rule");
  lines.push("");
  lines.push("- Top-to-bottom and left-to-right flow lines are drawn without arrowheads.");
  lines.push("- Bottom-to-top and right-to-left flow lines are drawn with open arrowheads.");
  lines.push("- Feedback and return paths follow the same direction-based rule.");
  lines.push("- The renderer uses the editable draw.io open arrow style: `endArrow=open;endFill=0;endSize=12`.");
  lines.push("- The validator rejects `endArrow=block`, filled arrows, classic arrows, diamond, oval, and circle arrowheads.");
  lines.push(`- Arrow validation: \`${summary.arrowRules?.checkedEdges || 0}\` visible edges checked, ` +
    `\`${summary.arrowRules?.arrowsRequired || 0}\` requiring open arrows, ` +
    `\`${summary.arrowRules?.arrowsForbidden || 0}\` requiring no arrows.`);
  lines.push("");
  lines.push("## Current Metrics");
  lines.push("");
  lines.push(`- Flowchart elements: \`${summary.nodeCount}\`.`);
  lines.push(`- Visible generated edges: \`${summary.repoEdgeCount}\`.`);
  lines.push(`- Separate branch labels: \`${summary.labelCount}\`.`);
  lines.push(`- Decor cells for predefined-process symbols: \`${summary.decorCount}\`.`);
  lines.push(`- Uniform local segment length: ` + "`U = " + summary.U + "`.");
  lines.push(`- Reachable nodes from Cycle Start: \`${summary.reachableFromStart} / ${summary.nodeCount}\`.`);
  lines.push(`- Page usage coverage: \`${(summary.coverageX * 100).toFixed(1)}% x ${(summary.coverageY * 100).toFixed(1)}%\`.`);
  lines.push(`- Skipped edge ids: \`${summary.skippedEdgeIds.length}\`.`);
  lines.push(`- Connector-resolved edge ids: \`${summary.connectorResolvedEdgeIds.length}\`.`);
  lines.push(`- Connector local edge clarity violations: \`${(summary.connectorLocalEdgeClarityViolations || []).length}\`.`);
  lines.push("");
  lines.push("## Connector Pairs");
  lines.push("");
  for (const [label, ids] of Object.entries(summary.connectorPairs || {})) {
    lines.push(`- ${label}: ${ids.join(" and ")}`);
  }
  lines.push("");
  lines.push("## Result Details");
  lines.push("");
  if (summary.passed) {
    lines.push(`- Exactly ${summary.nodeCount} flowchart elements were validated.`);
    lines.push("- All required decision branches are present and labeled once.");
    lines.push("- All required closed-loop logic edges exist in `flow_model.json`.");
  lines.push("- `skippedEdgeIds` is empty; remote semantic relationships are expressed by visible local connector edges, and connector-resolved edges are limited to same-name connector-pair logic.");
    lines.push("- All visible edges are orthogonal and use explicit center-port exit and entry styles.");
    lines.push("- All connector local edges pass the short-link clarity rule for length, span, and bend count.");
    lines.push("- Branch labels do not overlap nodes, line segments, or the forbidden title-block area.");
    lines.push("- The feedback loop and parameter downlink loop are reachable from `Cycle Start`.");
  } else {
    lines.push("Validation failed. The diagram is not compliant until these errors are fixed:");
    for (const error of summary.errors) {
      lines.push(`- ${error}`);
    }
  }
  if ((summary.warnings || []).length) {
    lines.push("");
    lines.push("## Warnings");
    lines.push("");
    for (const warning of summary.warnings || []) {
      lines.push(`- ${warning}`);
    }
  }
  fs.writeFileSync(REPORT_PATH, `${lines.join("\n")}\n`);
}

function main() {
  const errors = [];
  const warnings = [];
  const counters = {
    visibleSyntheticEdges: 0,
    isolatedConnectors: 0,
    diagonalEdges: 0,
    curveEdges: 0,
    labelOverlaps: 0,
    branchLabelPlacementErrors: 0
  };
  const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  const metrics = JSON.parse(fs.readFileSync(METRICS_PATH, "utf8"));
  const drawioXml = fs.readFileSync(DRAWIO_PATH, "utf8");
  const templateXml = fs.readFileSync(TEMPLATE_PATH, "utf8");
  validateTemplate(templateXml, drawioXml, errors);

  const doc = parser.parse(drawioXml);
  const diagram = asArray(doc.mxfile.diagram)[0];
  const graph = diagram.mxGraphModel;
  const root = graph.root;
  const cells = asArray(root.mxCell);
  const cellMap = new Map(cells.map((cell) => [String(cell["@_id"] || ""), cell]));

  const flowNodes = cells.filter(isFlowNode);
  const repoEdges = cells.filter(isRepoEdge);
  const labelCells = cells.filter(isLabel);
  const decorCells = cells.filter(isDecor);
  const allRepoCells = cells.filter((cell) => String(cell["@_id"] || "").startsWith(ID_PREFIX));
  const forbiddenArea = metrics.forbiddenArea;
  const page = metrics.page;
  validateFrameRules(cellMap, page, errors);
  const renderedEdgeIds = new Set(metrics.renderedEdgeIds || repoEdges.map((edge) => String(edge["@_id"] || "").replace(EDGE_PREFIX, "")));
  const skippedEdgeIds = new Set(metrics.skippedEdgeIds || []);
  const connectorResolvedEdgeIds = new Set(metrics.connectorResolvedEdgeIds || []);
  const rowMembership = new Map();
  const colMembership = new Map();
  (metrics.rows || []).forEach((row, rowIndex) => {
    for (let col = 0; col < row.length; col += 1) {
      rowMembership.set(row[col], rowIndex);
      colMembership.set(row[col], col);
    }
  });

  if (skippedEdgeIds.size > 0) {
    fail(errors, `No edge may be silently skipped; skippedEdgeIds must be empty, found: ${Array.from(skippedEdgeIds).join(", ")}.`);
  }
  const visibleSyntheticEdges = validateNoVisibleSyntheticEdges(repoEdges, errors);
  counters.visibleSyntheticEdges = visibleSyntheticEdges.length;

  if (flowNodes.length !== model.diagram.target_element_count) {
    fail(errors, `Expected exactly ${model.diagram.target_element_count} flowchart elements, found ${flowNodes.length}.`);
  }

  validateConnectorSemantics(model, errors);
  validateRequiredLogic(model, errors);
  const controlBlockViolations = validateControlBlockRules(model, errors);
  const connectorLocality = validateConnectorVisualLocality(model, metrics, flowNodes, repoEdges, cellMap, errors);
  const primaryFlowDirection = validatePrimaryFlowDirection(model, rowMembership, colMembership, errors);
  const arrowRules = validateArrowRules(repoEdges, cellMap, metrics, errors);

  const modelByRepoId = new Map(model.nodes.map((node) => [`${ID_PREFIX}${node.id}`, node]));
  const typeSizes = new Map();
  const connectorLabels = new Map();

  for (const node of flowNodes) {
    const id = String(node["@_id"] || "");
    const text = decodeText(node["@_value"]);
    const box = boxOf(node);
    const style = String(node["@_style"] || "");
    const modelNode = modelByRepoId.get(id);
    if (!modelNode) {
      fail(errors, `Unexpected repo_flow_ node ${id}.`);
      continue;
    }

    if (containsChinese(text)) {
      fail(errors, `Chinese text found in ${id}.`);
    }
    if (hasTruncatedWord(text)) {
      fail(errors, `Node ${id} has a truncated unreadable label: ${JSON.stringify(text)}.`);
    }
    if (!text.trim()) {
      fail(errors, `Node ${id} has an empty label.`);
    }
    const lines = text.split(/\n/);
    if (lines.length > 2) {
      fail(errors, `Node ${id} has more than two label lines.`);
    }
    if (textOverflowRisk(text, modelNode.type, box)) {
      fail(errors, `Node ${id} has text overflow risk.`);
    }
    if (style.includes("autosize=1")) {
      fail(errors, `Autosize is enabled on ${id}.`);
    }
    if (!style.includes("autosize=0")) {
      fail(errors, `Autosize is not explicitly disabled on ${id}.`);
    }
    if (box.x < 0 || box.y < 0 || box.x + box.width > page.width || box.y + box.height > page.height) {
      fail(errors, `Node ${id} is outside the page.`);
    }
    if (overlaps(box, forbiddenArea, 0)) {
      fail(errors, `Node ${id} overlaps the forbidden title block area.`);
    }

    const expectedRatio = SHAPE_RULES[modelNode.type]?.ratio || SHAPE_RULES.process.ratio;
    if (modelNode.type === "decision" && !approxRatio(box.width, box.height, expectedRatio)) {
      fail(errors, `Decision ${id} ratio is ${box.width / box.height}, expected ${expectedRatio}.`);
    } else if (modelNode.type === "connector" && !approx(box.width, box.height, 0.01)) {
      fail(errors, `Connector ${id} is not circular.`);
    } else if (modelNode.type === "stored_data" && !approxRatio(box.width, box.height, expectedRatio)) {
      fail(errors, `Stored data ${id} ratio is ${box.width / box.height}, expected ${expectedRatio}.`);
    } else if (modelNode.type !== "decision" && modelNode.type !== "connector" && modelNode.type !== "stored_data" && !approxRatio(box.width, box.height, expectedRatio)) {
      fail(errors, `Rect/parallelogram-family ${id} ratio is ${box.width / box.height}, expected ${expectedRatio}.`);
    }

    const sizeKey = modelNode.type === "decision" ? "decision" : modelNode.type === "connector" ? "connector" : modelNode.type === "stored_data" ? "stored_data" : "rect_family";
    const actualSize = `${box.width.toFixed(3)}x${box.height.toFixed(3)}`;
    if (!typeSizes.has(sizeKey)) {
      typeSizes.set(sizeKey, actualSize);
    } else if (typeSizes.get(sizeKey) !== actualSize) {
      fail(errors, `Inconsistent size for ${sizeKey}: ${actualSize} differs from ${typeSizes.get(sizeKey)}.`);
    }

    if (modelNode.type === "connector") {
      const list = connectorLabels.get(text) || [];
      list.push(id);
      connectorLabels.set(text, list);
    }
  }

  for (const [label, ids] of connectorLabels.entries()) {
    if (ids.length !== 2) {
      fail(errors, `Connector label ${label} appears ${ids.length} times instead of a pair.`);
    }
    if (!/^[FTPARL][0-9]+$/.test(label)) {
      fail(errors, `Connector label ${label} is not meaningful.`);
    }
    if (ids.length === 2) {
      const a = boxOf(cellMap.get(ids[0]));
      const b = boxOf(cellMap.get(ids[1]));
      const centerDistance = Math.hypot((a.x + a.width / 2) - (b.x + b.width / 2), (a.y + a.height / 2) - (b.y + b.height / 2));
      const minVisualSeparation = metrics.U * CONNECTOR_LOCALITY_RULES.minConnectorPairVisualSeparationU;
      if (centerDistance < minVisualSeparation) {
        fail(errors, `Connector pair ${label} is too close and looks duplicated.`);
      }
    }
  }

  for (let left = 0; left < flowNodes.length; left += 1) {
    for (let right = left + 1; right < flowNodes.length; right += 1) {
      const a = flowNodes[left];
      const b = flowNodes[right];
      if (overlaps(boxOf(a), boxOf(b), 0)) {
        fail(errors, `Flowchart node ${a["@_id"]} overlaps flowchart node ${b["@_id"]}.`);
      }
    }
  }

  const decisionEdgeIds = new Set(model.edges
    .filter((edge) => model.nodes.some((node) => node.id === edge.from && node.type === "decision") && edge.label)
    .map((edge) => edge.id));
  const labelByEdgeId = new Map();
  for (const labelCell of labelCells) {
    const id = String(labelCell["@_id"] || "");
    const edgeId = id.replace(LABEL_PREFIX, "");
    const text = decodeText(labelCell["@_value"]).trim();
    const box = boxOf(labelCell);
    if (!decisionEdgeIds.has(edgeId)) {
      fail(errors, `Standalone label ${id} does not belong to a decision branch edge.`);
    }
    if (containsChinese(text)) {
      fail(errors, `Chinese text found in edge label ${id}.`);
    }
    if (!text) {
      fail(errors, `Edge label ${id} is empty.`);
    }
    if (labelByEdgeId.has(edgeId)) {
      fail(errors, `Duplicate label cells for edge ${edgeId}.`);
    }
    labelByEdgeId.set(edgeId, labelCell);
    if (overlaps(box, forbiddenArea, 0)) {
      fail(errors, `Edge label ${id} overlaps the forbidden area.`);
    }
    for (const node of flowNodes) {
      if (overlaps(box, boxOf(node), 2)) {
        fail(errors, `Edge label ${id} overlaps flowchart node ${node["@_id"]}.`);
      }
    }
  }
  for (const edgeId of decisionEdgeIds) {
    if (!labelByEdgeId.has(edgeId)) {
      fail(errors, `Decision branch edge ${edgeId} is missing its separate label cell.`);
    }
  }
  for (let left = 0; left < labelCells.length; left += 1) {
    for (let right = left + 1; right < labelCells.length; right += 1) {
      const a = labelCells[left];
      const b = labelCells[right];
      if (overlaps(boxOf(a), boxOf(b), 2)) {
        fail(errors, `Edge label ${a["@_id"]} overlaps edge label ${b["@_id"]}.`);
      }
    }
  }

  const labelPlacementViolations = validateBranchLabelPlacement(model, repoEdges, labelByEdgeId, labelCells, flowNodes, cellMap, forbiddenArea, errors);

  for (const cell of decorCells) {
    const box = boxOf(cell);
    if (box.width && overlaps(box, forbiddenArea, 0)) {
      fail(errors, `Repo label/decor ${cell["@_id"]} overlaps the forbidden area.`);
    }
  }

  const longLineValidation = validateNoLongBusLines(repoEdges, cellMap, model, metrics, rowMembership, colMembership, errors);
  const visualCrowdingViolations = validateVisualCrowding(repoEdges, flowNodes, cellMap, metrics, errors);
  const programSchemeLayoutViolations = validateProgramSchemeLayout(model, metrics, flowNodes, repoEdges, cellMap, rowMembership, colMembership, errors);
  const visualBalanceViolations = validateVisualBalance(flowNodes, metrics, model, errors);
  const edgeCrossingViolations = validateNoEdgeCrossings(repoEdges, cellMap, errors);

  for (const edge of repoEdges) {
    const id = String(edge["@_id"] || "");
    const style = String(edge["@_style"] || "");
    if (style.includes("curved=1")) {
      fail(errors, `Curved edge style found on ${id}.`);
    }
    if (!style.includes("orthogonalEdgeStyle")) {
      fail(errors, `Non-orthogonal edge style found on ${id}.`);
    }
    if (containsChinese(edge["@_value"])) {
      fail(errors, `Chinese edge label found on ${id}.`);
    }
    if (String(edge["@_value"] || "").trim()) {
      fail(errors, `Edge ${id} must not store a label value; labels must use separate repo_flow_label_ cells.`);
    }

    const points = sourceTargetPointsWithPorts(edge, cellMap);
    if (!points) {
      fail(errors, `Edge ${id} is missing source or target.`);
      continue;
    }
    const segments = segmentLengths(points);
    const bendCount = bendCountOf(points);
    const edgeBoxes = segmentBoxes(points, 3);
    for (const labelCell of labelCells) {
      const labelBox = boxOf(labelCell);
      for (const edgeBox of edgeBoxes) {
        if (overlaps(labelBox, edgeBox, 0)) {
          fail(errors, `Edge label ${labelCell["@_id"]} overlaps line segment on ${id}.`);
          break;
        }
      }
    }
    const edgeModelId = id.replace(EDGE_PREFIX, "");
    const modelEdge = model.edges.find((candidate) => candidate.id === edgeModelId);
    const modelSourceNode = model.nodes.find((node) => node.id === modelEdge?.from);
    const sourceModelForEdge = modelByRepoId.get(String(edge["@_source"] || "")) || modelSourceNode;
    const isDecisionBranchEdge = sourceModelForEdge?.type === "decision" && Boolean(modelEdge?.label);
    if (!edge["@_source"] || !edge["@_target"]) {
      fail(errors, `Edge ${id} must connect real source and target cells; detached sourcePoint/targetPoint edges are not allowed.`);
    }
    const ports = parsePorts(style);
    if ([ports.exitX, ports.exitY, ports.entryX, ports.entryY].some((value) => value === null || !Number.isFinite(value))) {
      fail(errors, `Edge ${id} is missing explicit center-port exit/entry style.`);
    }
    if (!isCenterPort(ports.exitX, ports.exitY)) {
      fail(errors, `Edge ${id} source port is not a center-side port.`);
    }
    if (!isCenterPort(ports.entryX, ports.entryY)) {
      fail(errors, `Edge ${id} target port is not a center-side port.`);
    }
    if (modelEdge) {
      const renderedSource = String(edge["@_source"] || "").replace(ID_PREFIX, "");
      const renderedTarget = String(edge["@_target"] || "").replace(ID_PREFIX, "");
      if (renderedSource && renderedSource !== modelEdge.from) {
        fail(errors, `Edge ${id} source ${renderedSource} does not match flow_model source ${modelEdge.from}.`);
      }
      if (renderedTarget && renderedTarget !== modelEdge.to) {
        fail(errors, `Edge ${id} target ${renderedTarget} does not match flow_model target ${modelEdge.to}.`);
      }
    }
    if (isDecisionBranchEdge) {
      const label = String(modelEdge.label || "").trim();
      if (NORMAL_BRANCH_LABELS.has(label)) {
        if (!approxPort(ports.exitX, 1) || !approxPort(ports.exitY, 0.5)) {
          fail(errors, `Decision branch ${id} (${label}) must exit from right center.`);
        }
        if (!approxPort(ports.entryX, 0) || !approxPort(ports.entryY, 0.5)) {
          fail(errors, `Decision branch ${id} (${label}) must enter target left center.`);
        }
      } else if (ABNORMAL_BRANCH_LABELS.has(label)) {
        if (!approxPort(ports.exitX, 0.5) || !approxPort(ports.exitY, 1)) {
          fail(errors, `Decision branch ${id} (${label}) must exit from bottom center.`);
        }
        const entersTop = approxPort(ports.entryX, 0.5) && approxPort(ports.entryY, 0);
        const entersLeft = approxPort(ports.entryX, 0) && approxPort(ports.entryY, 0.5);
        if (!entersTop && !entersLeft) {
          fail(errors, `Decision branch ${id} (${label}) must enter target top center or left center.`);
        }
      }
    }
    const modelLabel = String(modelEdge?.label || "").trim();
    const isAbnormalDecisionBranch = isDecisionBranchEdge && ABNORMAL_BRANCH_LABELS.has(modelLabel);
    const isReturnEdge = ["return", "feedback", "loop"].includes(String(modelEdge?.channel || ""));
    const maxBends = isReturnEdge
      ? LONG_LINE_RULES.maxReturnBends
      : isAbnormalDecisionBranch
        ? LONG_LINE_RULES.maxDecisionAbnormalBends
        : LONG_LINE_RULES.maxBends;
    if (bendCount > maxBends) {
      fail(errors, `Edge ${id} has ${bendCount} bend point(s), maximum allowed is ${maxBends}.`);
    }
    const isConnectorLocalEdge = sourceModelForEdge?.type === "connector" || model.nodes.find((node) => node.id === modelEdge?.to)?.type === "connector";
    for (const [segmentIndex, segment] of segments.entries()) {
      if (!segment.orthogonal) {
        fail(errors, `Diagonal segment found on ${id}.`);
      }
      const maxAllowed = metrics.U * (isReturnEdge
        ? LONG_LINE_RULES.maxReturnSegmentU
        : isDecisionBranchEdge
          ? LONG_LINE_RULES.maxDecisionSegmentU
          : LONG_LINE_RULES.maxSegmentLengthU);
      const minAllowed = isConnectorLocalEdge
        ? 0
        : isDecisionBranchEdge && (segmentIndex === 0 || segmentIndex === segments.length - 1)
        ? metrics.U * 0.08
        : metrics.U * 0.40;
      if (segment.length > maxAllowed) {
        fail(errors, `Visible segment on ${id} is too long: ${segment.length.toFixed(3)}, expected local U near ${metrics.U}.`);
      }
    }
    const sourceId = String(edge["@_source"] || "");
    const targetId = String(edge["@_target"] || "");
    const sourceCell = cellMap.get(sourceId);
    const targetCell = cellMap.get(targetId);
    if (sourceCell && targetCell) {
      const sourceText = decodeText(sourceCell["@_value"]);
      const targetText = decodeText(targetCell["@_value"]);
      const sourceModel = modelByRepoId.get(sourceId);
      const targetModel = modelByRepoId.get(targetId);
      if (sourceModel?.type === "connector" && targetModel?.type === "connector" && sourceText === targetText) {
        fail(errors, `Connector pair ${sourceText} is connected by visible edge ${id}.`);
      }
    }
    const ignoredSourceId = sourceId || `${ID_PREFIX}${modelEdge?.from || ""}`;
    const ignoredTargetId = targetId || "";
    if (segmentIntersectsNode(points, ignoredSourceId, ignoredTargetId, flowNodes, cellMap)) {
      fail(errors, `Edge ${id} crosses another flowchart node.`);
    }
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      const segmentBox = {
        x: Math.min(a.x, b.x),
        y: Math.min(a.y, b.y),
        width: Math.max(1, Math.abs(a.x - b.x)),
        height: Math.max(1, Math.abs(a.y - b.y))
      };
      if (overlaps(segmentBox, forbiddenArea, 0)) {
        fail(errors, `Edge ${id} enters the forbidden title block area.`);
      }
    }
  }

  const modelDecisionNodes = model.nodes.filter((node) => node.type === "decision");
  const modelDecisionIds = new Set(modelDecisionNodes.map((node) => node.id));
  const outgoingByDecision = new Map(modelDecisionNodes.map((node) => [node.id, []]));
  for (const edge of model.edges) {
    if (modelDecisionIds.has(edge.from)) {
      outgoingByDecision.get(edge.from).push(edge);
    }
  }
  const repoEdgeByModelId = new Map(repoEdges.map((edge) => [String(edge["@_id"] || "").replace(EDGE_PREFIX, ""), edge]));
  const decisionRulesByText = new Map(Object.entries(DECISION_RULES).map(([key, value]) => [normalizeText(key), value]));
  for (const decision of modelDecisionNodes) {
    const edges = outgoingByDecision.get(decision.id) || [];
    if (edges.length < 2) {
      fail(errors, `Decision ${decision.id} has only ${edges.length} outgoing branch(es).`);
    }
    const labels = edges.map((edge) => String(edge.label || "").trim());
    if (labels.some((label) => !label || containsChinese(label))) {
      fail(errors, `Decision ${decision.id} has an unlabeled or non-English branch in flow_model.json.`);
    }
    if (new Set(labels).size !== labels.length) {
      fail(errors, `Decision ${decision.id} has duplicate branch labels: ${labels.join(", ")}.`);
    }
    const requiredRule = decisionRulesByText.get(normalizeText(decision.text));
    if (!requiredRule) {
      fail(errors, `Decision ${decision.id}:${decision.text} is not defined in flow_rules.js.`);
    }
    for (const [requiredLabel, requiredTarget] of Object.entries(requiredRule?.branches || {})) {
      const matchingEdge = edges.find((edge) => {
        const target = model.nodes.find((node) => node.id === edge.to);
        return String(edge.label || "").trim() === requiredLabel && normalizeText(target?.text) === normalizeText(requiredTarget);
      });
      if (!matchingEdge) {
        fail(errors, `Decision ${decision.id}:${decision.text} is missing required branch ${requiredLabel} -> ${requiredTarget}.`);
      }
    }
    for (const edge of edges) {
      if (!renderedEdgeIds.has(edge.id)) {
        fail(errors, `Decision branch ${edge.id} (${decision.text} / ${edge.label}) is not visibly rendered.`);
        continue;
      }
      const rendered = repoEdgeByModelId.get(edge.id);
      const value = decodeText(rendered?.["@_value"] || "").trim();
      if (value) {
        fail(errors, `Rendered decision edge ${edge.id} must keep edge value empty because labels use separate cells.`);
      }
      const labelCell = labelByEdgeId.get(edge.id);
      const labelValue = decodeText(labelCell?.["@_value"] || "").trim();
      if (labelValue !== String(edge.label || "").trim()) {
        fail(errors, `Rendered decision label ${edge.id} is ${JSON.stringify(labelValue)}, expected ${JSON.stringify(edge.label)}.`);
      }
    }
  }

  const missingRenderedOrResolved = [];
  for (const edge of model.edges) {
    if (!renderedEdgeIds.has(edge.id) && !connectorResolvedEdgeIds.has(edge.id)) {
      missingRenderedOrResolved.push(edge.id);
    }
  }
  if (missingRenderedOrResolved.length) {
    fail(errors, `Edges neither visibly rendered nor connector-resolved: ${missingRenderedOrResolved.join(", ")}.`);
  }

  for (const edgeId of connectorResolvedEdgeIds) {
    const edge = model.edges.find((candidate) => candidate.id === edgeId);
    if (!edge) {
      fail(errors, `connectorResolvedEdgeIds contains unknown edge ${edgeId}.`);
      continue;
    }
    const sourceNode = model.nodes.find((node) => node.id === edge.from);
    const targetNode = model.nodes.find((node) => node.id === edge.to);
    const isSameConnectorPair = sourceNode?.type === "connector" && targetNode?.type === "connector" && sourceNode.text === targetNode.text;
    if (!isSameConnectorPair) {
      fail(errors, `Overused connectorResolved edge ${edgeId}: only same-name connector pairs may be invisible connector-resolved links.`);
    }
    if (edge.label) {
      fail(errors, `Labeled edge ${edgeId} must be visibly rendered, not connector-resolved.`);
    }
  }
  const requiredVisibleFlowEdges = [
    ["Integral Update", "Duty Limit"],
    ["Telemetry Topic", "Msg Parser"],
    ["Java Data Hub", "Alarm Rules"],
    ["TS DB", "Backend DB"],
    ["Model Evaluation", "Policy Ranking"]
  ];
  for (const [from, to] of requiredVisibleFlowEdges) {
    for (const edge of findEdges(model, from, to)) {
      if (connectorResolvedEdgeIds.has(edge.id)) {
        fail(errors, `Ordinary flow edge ${from} -> ${to} must be visible or use an explicit R connector, not connector-resolved (${edge.id}).`);
      }
    }
  }
  const { adjacency: logicalAdjacency, reverse: logicalReverse, logicalEdges } = buildLogicalGraph(model);
  const start = "n01";
  const seen = reachableFrom(start, logicalAdjacency);
  if (seen.size !== model.nodes.length) {
    const missing = model.nodes
      .filter((node) => !seen.has(node.id))
      .map((node) => `${node.id}:${node.text}`)
      .join(", ");
    fail(errors, `Logical flow is disconnected from Cycle Start: ${seen.size} of ${model.nodes.length} nodes reachable; missing ${missing}.`);
  }

  for (const node of model.nodes) {
    const outgoing = logicalAdjacency.get(node.id) || [];
    const incoming = logicalReverse.get(node.id) || [];
    if (node.id === start && outgoing.length === 0) {
      fail(errors, "Cycle Start has no outgoing logical flow.");
    } else if (node.id !== start && incoming.length + outgoing.length === 0) {
      fail(errors, `Node ${node.id}:${node.text} is logically isolated.`);
    }
  }

  const undirectedSeen = new Set([start]);
  const undirectedQueue = [start];
  const undirected = new Map(model.nodes.map((node) => [node.id, []]));
  for (const edge of logicalEdges) {
    if (!undirected.has(edge.from) || !undirected.has(edge.to)) {
      continue;
    }
    undirected.get(edge.from).push(edge.to);
    undirected.get(edge.to).push(edge.from);
  }
  while (undirectedQueue.length) {
    const current = undirectedQueue.shift();
    for (const next of undirected.get(current) || []) {
      if (!undirectedSeen.has(next)) {
        undirectedSeen.add(next);
        undirectedQueue.push(next);
      }
    }
  }
  if (undirectedSeen.size !== model.nodes.length) {
    fail(errors, `Flow network is visually disconnected: ${undirectedSeen.size} of ${model.nodes.length} nodes are in the main component.`);
  }

  const connectedRows = new Set();
  for (const edge of logicalEdges) {
    const a = rowMembership.get(edge.from);
    const b = rowMembership.get(edge.to);
    if (Number.isInteger(a) && Number.isInteger(b) && a !== b) {
      connectedRows.add(`${Math.min(a, b)}-${Math.max(a, b)}`);
    }
  }
  const rowCount = (metrics.rows || []).length;

  const forbiddenRepo = allRepoCells.filter((cell) => {
    const g = cell.mxGeometry || {};
    const box = {
      x: attrNumber(g, "x"),
      y: attrNumber(g, "y"),
      width: attrNumber(g, "width"),
      height: attrNumber(g, "height")
    };
    return box.width > 0 && box.height > 0 && overlaps(box, forbiddenArea, 0);
  });
  if (forbiddenRepo.length) {
    fail(errors, `Repo cells overlap forbidden area: ${forbiddenRepo.map((cell) => cell["@_id"]).join(", ")}.`);
  }

  if (/Legend|Module|Phase|Architecture Flowchart|Top Title/i.test(drawioXml.replace(/EdgeHub Temperature Control Architecture and Control Flow/g, ""))) {
    warnings.push("Text scan found words that may look like titles; no repo_flow_ module/title cells were generated.");
  }

  const xs = flowNodes.map((cell) => boxOf(cell).x);
  const ys = flowNodes.map((cell) => boxOf(cell).y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...flowNodes.map((cell) => boxOf(cell).x + boxOf(cell).width));
  const minY = Math.min(...ys);
  const maxY = Math.max(...flowNodes.map((cell) => boxOf(cell).y + boxOf(cell).height));
  const coverageX = (maxX - minX) / page.width;
  const coverageY = (maxY - minY) / (metrics.forbiddenArea.y - 40);
  if (coverageX < 0.78 || coverageY < 0.60) {
    fail(errors, `Visual density is too low: coverageX=${coverageX.toFixed(3)}, coverageY=${coverageY.toFixed(3)}.`);
  }

  const validationCounts = countValidationCategories(errors, counters);
  const invalidConnectorLocality = [
    ...connectorLocality.invalidLocality,
    ...validationCounts.invalidConnectorLocality.filter((item) => !connectorLocality.invalidLocality.includes(item))
  ];
  const connectorLocalEdgeClarityViolations = connectorLocality.connectorLocalEdgeClarityViolations || [];
  const isolatedConnectors = connectorLocality.isolatedConnectors.length || validationCounts.isolatedConnectors;
  const overusedConnectorResolvedEdges = validationCounts.overusedConnectorResolvedEdges;
  const primaryFlowDirectionViolations = primaryFlowDirection.violations;
  const longBusLines = [
    ...longLineValidation.longBusLines,
    ...(longLineValidation.connectionLengthViolations || []),
    ...(longLineValidation.verticalConnectionLengthViolations || []),
    ...validationCounts.longBusLines.filter((item) => !longLineValidation.longBusLines.includes(item))
  ];
  const edgesTooManyBends = [
    ...longLineValidation.edgesTooManyBends,
    ...validationCounts.edgesTooManyBends.filter((item) => !longLineValidation.edgesTooManyBends.includes(item))
  ];
  const routingEnvelopeViolations = [
    ...longLineValidation.routingEnvelopeViolations,
    ...validationCounts.routingEnvelopeViolations.filter((item) => !longLineValidation.routingEnvelopeViolations.includes(item))
  ];
  const invalidArrowEdges = arrowRules.invalidArrowEdges.map((item) => item.reason || item.id || String(item));
  const shortArrowStemEdges = [
    ...validationCounts.shortArrowStemEdges
  ];
  const isoGostSymbolErrors = errors.filter((error) => /ratio|symbol|Autosize|text overflow|Chinese text|empty label|more than two label lines|shape/i.test(error));
  const isoGostDecisionErrors = errors.filter((error) => /Decision|decision branch/i.test(error));
  const isoGostConnectorErrors = errors.filter((error) => /Connector|connector/i.test(error));
  const isoGostLineErrors = errors.filter((error) => /Diagonal|Curved|orthogonal|segment|bend|port|crosses another flowchart node|forbidden title block area|routing envelope|arrow/i.test(error));
  const isoGostLabelErrors = errors.filter((error) => /label/i.test(error));
  const projectA1Errors = errors.filter((error) => /Template|title block|forbidden|page|module|Legend|Visual density|Program scheme/i.test(error));
  const requiredClosedLoopErrors = errors.filter((error) => /Required logic|Cycle Start|feedback loop|parameter loop|reachable|disconnected/i.test(error));
  const summary = {
    passed: errors.length === 0,
    isoGostSymbolRules: isoGostSymbolErrors.length === 0 ? "passed" : "failed",
    isoGostDecisionRules: isoGostDecisionErrors.length === 0 ? "passed" : "failed",
    isoGostConnectorRules: isoGostConnectorErrors.length === 0 ? "passed" : "failed",
    isoGostLineRules: isoGostLineErrors.length === 0 ? "passed" : "failed",
    isoGostLabelRules: isoGostLabelErrors.length === 0 ? "passed" : "failed",
    projectA1Rules: projectA1Errors.length === 0 ? "passed" : "failed",
    requiredClosedLoop: requiredClosedLoopErrors.length === 0 ? "passed" : "failed",
    arrowRules: {
      ...arrowRules,
      passed: arrowRules.invalidArrowEdges.length === 0
    },
    openArrowRules: {
      passed: arrowRules.invalidArrowEdges.length === 0,
      requiredOpenArrowEdges: arrowRules.requiredOpenArrowEdges,
      forbiddenArrowEdges: arrowRules.forbiddenArrowEdges
    },
    branchLabelPlacement: validationCounts.branchLabelPlacementErrors === 0 ? "passed" : "failed",
    ...validationCounts,
    visibleSyntheticEdges: visibleSyntheticEdges.length,
    isolatedConnectors,
    invalidConnectorLocality,
    connectorLocalEdgeClarityViolations,
    overusedConnectorResolvedEdges,
    primaryFlowDirectionViolations,
    longBusLines,
    edgesTooManyBends,
    routingEnvelopeViolations,
    controlBlockViolations,
    visualBalanceViolations,
    programSchemeLayoutViolations,
    edgeCrossingViolations,
    invalidArrowEdges,
    shortArrowStemEdges,
    visualCrowdingViolations,
    labelPlacementViolations,
    errors,
    warnings,
    nodeCount: flowNodes.length,
    repoEdgeCount: repoEdges.length,
    labelCount: labelCells.length,
    decorCount: decorCells.length,
    connectorPairs: Object.fromEntries(connectorLabels.entries()),
    U: metrics.U,
    renderedEdgeIds: Array.from(renderedEdgeIds),
    skippedEdgeIds: Array.from(skippedEdgeIds),
    connectorResolvedEdgeIds: Array.from(connectorResolvedEdgeIds),
    connectedRows: Array.from(connectedRows),
    reachableFromStart: seen.size,
    coverageX,
    coverageY,
    forbiddenArea,
    page
  };
  fs.writeFileSync(SUMMARY_PATH, `${JSON.stringify(summary, null, 2)}\n`);
  writeComplianceReport(summary);

  if (errors.length) {
    console.error("validator failed");
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  console.log("validator passed summary");
  console.log(`- flowchart elements: ${flowNodes.length}`);
  console.log(`- visible repo edges: ${repoEdges.length}`);
  console.log(`- uniform segment length U: ${metrics.U}`);
  console.log(`- page coverage: ${(coverageX * 100).toFixed(1)}% x ${(coverageY * 100).toFixed(1)}%`);
  if (warnings.length) {
    console.log(`- warnings: ${warnings.length}`);
  }
}

main();
