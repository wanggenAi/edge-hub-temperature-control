#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser } = require("fast-xml-parser");

const WORK_DIR = __dirname;
const DRAWIO_PATH = path.join(WORK_DIR, "optimized_architecture_flowchart.drawio");
const TOL = 1;
const RETURN_Y = 2120;
const LEFT_RETURN_Y = 2088;
const START_END_X = 1620;
const FLOW_EDGE_STROKE_WIDTH = "1.9685";

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: "@_",
  trimValues: false
});

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key) {
  const value = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(value) ? value : NaN;
}

function plainLabel(cell) {
  return String(cell["@_value"] || "")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function close(a, b, tol = TOL) {
  return Math.abs(Number(a) - Number(b)) <= tol;
}

function pointOf(edge, pointAs) {
  const points = asArray(edge.mxGeometry && edge.mxGeometry.mxPoint);
  return points.find((point) => point["@_as"] === pointAs);
}

function center(cell) {
  const g = cell.mxGeometry || {};
  const x = attrNumber(g, "x");
  const y = attrNumber(g, "y");
  const width = attrNumber(g, "width");
  const height = attrNumber(g, "height");
  return { x: x + width / 2, y: y + height / 2, width, height };
}

function fail(errors, code, detail) {
  errors.push({ code, detail });
}

const xml = fs.readFileSync(DRAWIO_PATH, "utf8");
const doc = parser.parse(xml);
const diagram = asArray(doc.mxfile.diagram)[0];
const cells = asArray(diagram.mxGraphModel.root.mxCell);
const byId = new Map(cells.map((cell) => [cell["@_id"], cell]));
const errors = [];

function oneLabel(label) {
  const matches = cells.filter((cell) => plainLabel(cell) === label);
  if (matches.length !== 1) {
    fail(errors, "LABEL_COUNT_MISMATCH", `${label}: expected 1, found ${matches.length}`);
    return null;
  }
  return matches[0];
}

const start = oneLabel("Start");
const end = oneLabel("End");
if (start && end) {
  const sc = center(start);
  const ec = center(end);
  if (!close(sc.x, ec.x)) {
    fail(errors, "END_NOT_ALIGNED_WITH_START", `Start center x=${sc.x}, End center x=${ec.x}`);
  }
  if (!close(ec.x, START_END_X)) {
    fail(errors, "END_NOT_ON_EXPECTED_CENTERLINE", `End center x=${ec.x}, expected ${START_END_X}`);
  }
}

for (const label of ["Fault Report", "Fault Archive"]) {
  const node = oneLabel(label);
  if (!node) continue;
  const c = center(node);
  if (!close(c.x, 1800)) {
    fail(errors, "FAULT_BRANCH_NODE_NOT_CENTERED", `${label}: center x=${c.x}, expected 1800`);
  }
}

const expectedArrows = {
  manual_fix_return_arrow_spine: 1620,
  manual_fix_return_arrow_fault_complete: 1800,
  manual_fix_return_arrow_feedback_complete: 2160,
  manual_fix_return_arrow_model_complete: 2520,
  manual_fix_return_arrow_publish_complete: 2880,
  manual_fix_return_arrow_reject_log: 3143
};

for (const [id, x] of Object.entries(expectedArrows)) {
  const edge = byId.get(id);
  if (!edge) {
    fail(errors, "RETURN_ARROW_MISSING", id);
    continue;
  }
  const style = String(edge["@_style"] || "");
  if (!style.includes("endArrow=open") || !style.includes("endFill=0")) {
    fail(errors, "RETURN_ARROW_STYLE_INVALID", `${id}: ${style}`);
  }
  const source = pointOf(edge, "sourcePoint");
  const target = pointOf(edge, "targetPoint");
  if (!source || !target) {
    fail(errors, "RETURN_ARROW_ENDPOINT_MISSING", id);
    continue;
  }
  const sx = attrNumber(source, "x");
  const sy = attrNumber(source, "y");
  const tx = attrNumber(target, "x");
  const ty = attrNumber(target, "y");
  if (!close(tx, x) || !close(ty, RETURN_Y)) {
    fail(errors, "RETURN_ARROW_HEAD_NOT_ON_MERGE", `${id}: target=(${tx}, ${ty}), expected=(${x}, ${RETURN_Y})`);
  }
  if (!close(sy, ty) || sx <= tx) {
    fail(errors, "RETURN_ARROW_NOT_RIGHT_TO_LEFT", `${id}: source=(${sx}, ${sy}), target=(${tx}, ${ty})`);
  }
}

for (const [id, y] of Object.entries({
  repo_flow_edge_g12: RETURN_Y,
  repo_flow_edge_r12: RETURN_Y,
  repo_flow_edge_d12: RETURN_Y,
  repo_flow_edge_j03: RETURN_Y,
  "XPCkQVmFVOrDNIZzhBCc-3": LEFT_RETURN_Y
})) {
  const edge = byId.get(id);
  if (!edge) {
    fail(errors, "EDGE_MISSING", id);
    continue;
  }
  const target = pointOf(edge, "targetPoint");
  if (!target) {
    fail(errors, "EDGE_TARGET_POINT_MISSING", id);
    continue;
  }
  const ty = attrNumber(target, "y");
  if (!close(ty, y)) {
    fail(errors, "EDGE_NOT_SNAPPED_TO_RETURN_LINE", `${id}: target y=${ty}, expected ${y}`);
  }
}

for (const cell of cells) {
  if (cell["@_edge"] !== "1") continue;
  const id = String(cell["@_id"] || "");
  if (id.startsWith("content_page_titleblock_")) continue;
  const style = String(cell["@_style"] || "");
  const match = style.match(/(?:^|;)strokeWidth=([^;]+)/);
  if (!match || match[1] !== FLOW_EDGE_STROKE_WIDTH) {
    fail(errors, "FLOW_EDGE_STROKE_WIDTH_INVALID", `${id}: expected strokeWidth=${FLOW_EDGE_STROKE_WIDTH}, style=${style}`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  checks: [
    "Start and End center x aligned",
    "Fault branch has two added process nodes on the same centerline",
    "Right-to-left return arrows terminate exactly at merge intersections",
    "Bottom return lines are snapped to the expected y-levels",
    "All non-title-block connection lines use 0.5 mm stroke width"
  ]
}, null, 2));
