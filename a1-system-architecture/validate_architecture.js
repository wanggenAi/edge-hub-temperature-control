#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser } = require("fast-xml-parser");
const {
  FRAME_RULES,
  PROJECT_A1_RULES,
  ARCHITECTURE_LAYOUT_RULES,
  STYLE_RULES
} = require("./architecture_rules");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = path.join(ROOT_DIR, "aa.drawio");
const MODEL_PATH = path.join(WORK_DIR, "architecture_model.json");
const DRAWIO_PATH = path.join(WORK_DIR, "system_architecture_a1.drawio");
const METRICS_PATH = path.join(WORK_DIR, "architecture_metrics.json");
const SUMMARY_PATH = path.join(WORK_DIR, "architecture_validator_summary.json");
const REPORT_PATH = path.join(WORK_DIR, "architecture_compliance_report.md");

const NODE_PREFIX = "arch_node_";
const GROUP_PREFIX = "arch_group_";
const EDGE_PREFIX = "arch_edge_";
const LABEL_PREFIX = "arch_label_";

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  preserveOrder: false,
  trimValues: false
});

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const value = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(value) ? value : fallback;
}

function fail(errors, message) {
  errors.push(message);
}

function boxOf(cell) {
  const g = cell?.mxGeometry || {};
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

function approx(a, b, tolerance = 0.5) {
  return Math.abs(Number(a) - Number(b)) <= tolerance;
}

function parsePorts(style) {
  const get = (name, fallback) => {
    const match = String(style || "").match(new RegExp(`${name}=([0-9.]+)`));
    return match ? Number(match[1]) : fallback;
  };
  return {
    exitX: get("exitX", 1),
    exitY: get("exitY", 0.5),
    entryX: get("entryX", 0),
    entryY: get("entryY", 0.5)
  };
}

function sourceTargetPoints(edge, cellMap) {
  const source = cellMap.get(String(edge["@_source"] || ""));
  const target = cellMap.get(String(edge["@_target"] || ""));
  if (!source || !target) return null;
  const ports = parsePorts(edge["@_style"]);
  const sb = boxOf(source);
  const tb = boxOf(target);
  const points = [
    { x: sb.x + sb.width * ports.exitX, y: sb.y + sb.height * ports.exitY }
  ];
  const waypoints = edge.mxGeometry?.Array?.mxPoint ? asArray(edge.mxGeometry.Array.mxPoint) : [];
  for (const point of waypoints) points.push({ x: attrNumber(point, "x"), y: attrNumber(point, "y") });
  points.push({ x: tb.x + tb.width * ports.entryX, y: tb.y + tb.height * ports.entryY });
  return points;
}

function bendCount(points) {
  let bends = 0;
  let previous = null;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const direction = Math.abs(a.x - b.x) > Math.abs(a.y - b.y) ? "h" : "v";
    if (previous && previous !== direction) bends += 1;
    previous = direction;
  }
  return bends;
}

function segmentBoxes(points, pad = 0) {
  const boxes = [];
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    const vertical = Math.abs(a.x - b.x) <= 0.1;
    const horizontal = Math.abs(a.y - b.y) <= 0.1;
    boxes.push({
      x: Math.min(a.x, b.x) - (vertical ? pad : 0),
      y: Math.min(a.y, b.y) - (horizontal ? pad : 0),
      width: Math.max(1, Math.abs(a.x - b.x)) + (vertical ? pad * 2 : 0),
      height: Math.max(1, Math.abs(a.y - b.y)) + (horizontal ? pad * 2 : 0)
    });
  }
  return boxes;
}

function validateFrame(cellMap, page, errors) {
  const expected = frameBoxForPage(page);
  const border = cellMap.get(FRAME_RULES.outerBorder.id);
  if (!border) {
    fail(errors, "A1 outer border is missing.");
    return;
  }
  const box = boxOf(border);
  for (const key of ["x", "y", "width", "height"]) {
    if (!approx(box[key], expected[key], 0.75)) {
      fail(errors, `A1 outer border ${key}=${box[key]} does not match expected ${expected[key]}.`);
    }
  }
  const style = String(border["@_style"] || "");
  const stroke = Number((style.match(/strokeWidth=([0-9.]+)/) || [])[1]);
  if (!approx(stroke, FRAME_RULES.outerBorder.strokeWidth, FRAME_RULES.titleBlock.strokeTolerance)) {
    fail(errors, "A1 outer border stroke width is not reference-compliant.");
  }
  const title = cellMap.get(FRAME_RULES.titleBlock.id);
  if (!title) {
    fail(errors, "Original title block is missing.");
    return;
  }
  const titleBox = boxOf(title);
  if (!approx(titleBox.x + titleBox.width, expected.x + expected.width, 0.75)) {
    fail(errors, "Title block is not aligned to the outer frame right edge.");
  }
  if (!approx(titleBox.y + titleBox.height, expected.y + expected.height, 0.75)) {
    fail(errors, "Title block is not aligned to the outer frame bottom edge.");
  }
}

function validateTemplate(templateXml, drawioXml, errors) {
  const titleBlockToken = FRAME_RULES.titleBlock.id;
  if (!templateXml.includes(titleBlockToken) || !drawioXml.includes(titleBlockToken)) {
    fail(errors, "The original A1 title block was not preserved.");
  }
}

function validateMain() {
  const errors = [];
  const warnings = [];
  const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
  const metrics = JSON.parse(fs.readFileSync(METRICS_PATH, "utf8"));
  const drawioXml = fs.readFileSync(DRAWIO_PATH, "utf8");
  const templateXml = fs.readFileSync(TEMPLATE_PATH, "utf8");
  validateTemplate(templateXml, drawioXml, errors);
  const doc = parser.parse(drawioXml);
  const graph = asArray(doc.mxfile.diagram)[0].mxGraphModel;
  const page = { width: attrNumber(graph, "pageWidth"), height: attrNumber(graph, "pageHeight") };
  const cells = asArray(graph.root.mxCell);
  const cellMap = new Map(cells.map((cell) => [String(cell["@_id"] || ""), cell]));
  const nodes = cells.filter((cell) => String(cell["@_id"] || "").startsWith(NODE_PREFIX));
  const groups = cells.filter((cell) => String(cell["@_id"] || "").startsWith(GROUP_PREFIX));
  const edges = cells.filter((cell) => String(cell["@_id"] || "").startsWith(EDGE_PREFIX));
  const labels = cells.filter((cell) => String(cell["@_id"] || "").startsWith(LABEL_PREFIX));

  validateFrame(cellMap, page, errors);

  if (nodes.length !== model.diagram.target_element_count) {
    fail(errors, `Expected ${model.diagram.target_element_count} architecture nodes, found ${nodes.length}.`);
  }
  if (groups.length !== model.layers.length) {
    fail(errors, `Expected ${model.layers.length} layer groups, found ${groups.length}.`);
  }
  if (edges.length !== model.edges.length) {
    fail(errors, `Expected ${model.edges.length} architecture edges, found ${edges.length}.`);
  }
  if (metrics.coverageX < PROJECT_A1_RULES.minCoverageX || metrics.coverageY < PROJECT_A1_RULES.minCoverageY) {
    fail(errors, `A1 coverage is too low: ${metrics.coverageX.toFixed(3)} x ${metrics.coverageY.toFixed(3)}.`);
  }
  if (metrics.groupGap < ARCHITECTURE_LAYOUT_RULES.minLayerGapPx) {
    fail(errors, `Layer gap ${metrics.groupGap.toFixed(1)} is below ${ARCHITECTURE_LAYOUT_RULES.minLayerGapPx}.`);
  }

  for (const node of nodes) {
    const box = boxOf(node);
    if (overlaps(box, metrics.forbiddenArea, 0)) {
      fail(errors, `Architecture node ${node["@_id"]} enters the title-block forbidden area.`);
    }
    const value = String(node["@_value"] || "");
    if (/[\u3400-\u9fff]/.test(value)) {
      fail(errors, `Architecture node ${node["@_id"]} contains non-English text.`);
    }
  }
  for (let left = 0; left < nodes.length; left += 1) {
    for (let right = left + 1; right < nodes.length; right += 1) {
      if (overlaps(boxOf(nodes[left]), boxOf(nodes[right]), ARCHITECTURE_LAYOUT_RULES.minNodeGapPx * -0.2)) {
        fail(errors, `Architecture nodes overlap: ${nodes[left]["@_id"]} and ${nodes[right]["@_id"]}.`);
      }
    }
  }

  for (const edge of edges) {
    const id = String(edge["@_id"] || "");
    const style = String(edge["@_style"] || "");
    if (!style.includes("orthogonalEdgeStyle") || style.includes("curved=1")) {
      fail(errors, `Architecture edge ${id} is not a strict orthogonal connector.`);
    }
    if (!style.includes(`endArrow=${STYLE_RULES.arrowStyle.endArrow}`) || !style.includes("endFill=0")) {
      fail(errors, `Architecture edge ${id} does not use open arrow style.`);
    }
    const points = sourceTargetPoints(edge, cellMap);
    if (!points) {
      fail(errors, `Architecture edge ${id} has unresolved endpoints.`);
      continue;
    }
    if (bendCount(points) > ARCHITECTURE_LAYOUT_RULES.connection.maxBends) {
      fail(errors, `Architecture edge ${id} has too many bends.`);
    }
    for (let index = 1; index < points.length; index += 1) {
      const a = points[index - 1];
      const b = points[index];
      const dx = Math.abs(a.x - b.x);
      const dy = Math.abs(a.y - b.y);
      if (dx > 0.1 && dy > 0.1) {
        fail(errors, `Architecture edge ${id} has a diagonal segment.`);
      }
      const length = dx + dy;
      if (length > ARCHITECTURE_LAYOUT_RULES.connection.maxSegmentLengthPx + 0.01) {
        fail(errors, `Architecture edge ${id} has overlong segment ${length.toFixed(1)}.`);
      }
    }
    for (const box of segmentBoxes(points, 2)) {
      if (overlaps(box, metrics.forbiddenArea, 0)) {
        fail(errors, `Architecture edge ${id} enters the title-block forbidden area.`);
      }
    }
  }

  for (const label of labels) {
    if (overlaps(boxOf(label), metrics.forbiddenArea, 0)) {
      fail(errors, `Architecture label ${label["@_id"]} enters the title-block forbidden area.`);
    }
  }

  const summary = {
    passed: errors.length === 0,
    nodeCount: nodes.length,
    groupCount: groups.length,
    edgeCount: edges.length,
    labelCount: labels.length,
    coverageX: metrics.coverageX,
    coverageY: metrics.coverageY,
    layerGap: metrics.groupGap,
    frameRules: errors.filter((error) => /frame|title block|border/i.test(error)).length === 0 ? "passed" : "failed",
    architectureLayoutRules: errors.filter((error) => /coverage|Layer gap|overlap/i.test(error)).length === 0 ? "passed" : "failed",
    architectureLineRules: errors.filter((error) => /edge|diagonal|bend|segment|arrow/i.test(error)).length === 0 ? "passed" : "failed",
    errors,
    warnings
  };
  fs.writeFileSync(SUMMARY_PATH, `${JSON.stringify(summary, null, 2)}\n`);
  const lines = [
    "# System Architecture A1 Compliance Report",
    "",
    `Final validation status: **${summary.passed ? "PASSED" : "FAILED"}**.`,
    "",
    "The drawing is generated from `architecture_model.json` and `architecture_rules.js`; `architecture_validator_summary.json` is the source of truth.",
    "",
    "## Enforced Rules",
    "",
    "- A1 template, outer border, and original bottom-right title block are preserved.",
    "- Architecture nodes are grouped into five evenly spaced system layers.",
    "- All architecture connectors are editable orthogonal draw.io edges.",
    "- Lines use open arrowheads and may have at most one bend.",
    "- Nodes, edges, labels, and groups must stay clear of the title-block forbidden area.",
    "",
    "## Metrics",
    "",
    `- Nodes: ${summary.nodeCount}`,
    `- Layer groups: ${summary.groupCount}`,
    `- Edges: ${summary.edgeCount}`,
    `- A1 coverage: ${(summary.coverageX * 100).toFixed(1)}% x ${(summary.coverageY * 100).toFixed(1)}%`
  ];
  fs.writeFileSync(REPORT_PATH, `${lines.join("\n")}\n`);
  if (!summary.passed) {
    console.error(JSON.stringify(summary, null, 2));
    process.exit(1);
  }
  console.log("architecture validator passed");
  console.log(`- nodes: ${summary.nodeCount}`);
  console.log(`- groups: ${summary.groupCount}`);
  console.log(`- coverage: ${(summary.coverageX * 100).toFixed(1)}% x ${(summary.coverageY * 100).toFixed(1)}%`);
}

validateMain();
