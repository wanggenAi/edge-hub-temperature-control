#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const DRAWIO = path.join(__dirname, "esp32_temperature_node_gost.drawio");
const PNG = path.join(__dirname, "esp32_temperature_node_gost.png");
const SVG = path.join(__dirname, "esp32_temperature_node_gost.svg");
const PDF = path.join(__dirname, "esp32_temperature_node_gost.pdf");

const xml = fs.readFileSync(DRAWIO, "utf8");
const failures = [];
const warnings = [];

const page = { width: 3300, height: 2339 };
const frame = { x: 78.5, y: 19.7, width: 3201.9, height: 2299.6 };
const keepouts = [
  { name: "element-list", x: 2475, y: 30, width: 825, height: 1225 },
  { name: "title-block", x: 2546.6, y: 2098.3, width: 733.8, height: 221 }
];
const titleBlock = { x: 2546.6, y: 2098.3, width: 733.8, height: 221 };
const elementList = { x: 2475, y: 30, width: 825, height: 1225 };
const frameHeader = { x: frame.x, y: frame.y, width: frame.width, height: 50 };
const schematicArea = { x: 150, y: 130, width: 2250, height: 1760 };
const grid = 5;

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function nearGrid(value, step = grid, tolerance = 0.35) {
  return Math.abs(value / step - Math.round(value / step)) <= tolerance / step;
}

function overlap(a, b, margin = 0) {
  return a.x + a.width > b.x - margin &&
    b.x + b.width > a.x - margin &&
    a.y + a.height > b.y - margin &&
    b.y + b.height > a.y - margin;
}

function inside(box, outer) {
  return box.x >= outer.x &&
    box.y >= outer.y &&
    box.x + box.width <= outer.x + outer.width &&
    box.y + box.height <= outer.y + outer.height;
}

function edgeSegments() {
  const result = [];
  const cellRegex = /<mxCell\b([^>]*)>([\s\S]*?)<\/mxCell>/g;
  let match;
  while ((match = cellRegex.exec(xml))) {
    const attrs = match[1];
    const body = match[2];
    if (!/edge="1"/.test(attrs)) continue;
    const id = (attrs.match(/\bid="([^"]+)"/) || [])[1] || "(unknown)";
    const kind = (attrs.match(/\bdata-kind="([^"]+)"/) || [])[1] || "unknown";
    const s = body.match(/<mxPoint[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*as="sourcePoint"/);
    const t = body.match(/<mxPoint[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*as="targetPoint"/);
    if (!s || !t) continue;
    const x1 = num(s[1]);
    const y1 = num(s[2]);
    const x2 = num(t[1]);
    const y2 = num(t[2]);
    result.push({ id, kind, x1, y1, x2, y2, box: { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) } });
  }
  return result;
}

function vertices() {
  const result = [];
  const cellRegex = /<mxCell\b([^>]*)>([\s\S]*?)<\/mxCell>/g;
  let match;
  while ((match = cellRegex.exec(xml))) {
    const attrs = match[1];
    const body = match[2];
    if (!/vertex="1"/.test(attrs)) continue;
    const id = (attrs.match(/\bid="([^"]+)"/) || [])[1] || "(unknown)";
    const kind = (attrs.match(/\bdata-kind="([^"]+)"/) || [])[1] || "unknown";
    const value = (attrs.match(/\bvalue="([^"]*)"/) || [])[1] || "";
    const geom = body.match(/<mxGeometry[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*width="([^"]+)"[^>]*height="([^"]+)"/);
    if (!geom) continue;
    const x = num(geom[1]);
    const y = num(geom[2]);
    const width = num(geom[3]);
    const height = num(geom[4]);
    result.push({ id, kind, value, x, y, width, height });
  }
  return result;
}

const edges = edgeSegments();
const verts = vertices();
const wires = edges.filter((edge) => edge.kind === "wire");
const components = verts.filter((v) => v.kind === "component" && !/^repo_template_outer_border$|^title_group_border$/.test(v.id));
const textItems = verts.filter((v) => v.kind === "text");
const allText = verts.map((item) => item.value || "");
const semanticText = allText.map((value) => value
  .replace(/&lt;br&gt;|<br>/g, " ")
  .replace(/&amp;nbsp;/g, " ")
  .replace(/&quot;/g, "\"")
);
const semanticBlob = semanticText.join(" ");

for (const wire of wires) {
  if (wire.x1 !== wire.x2 && wire.y1 !== wire.y2) {
    failures.push(`Wire ${wire.id} is diagonal: (${wire.x1},${wire.y1}) -> (${wire.x2},${wire.y2})`);
  }
  for (const key of ["x1", "y1", "x2", "y2"]) {
    if (!nearGrid(wire[key])) failures.push(`Wire ${wire.id} endpoint ${key}=${wire[key]} is off ${grid}px grid`);
  }
  const length = Math.abs(wire.x2 - wire.x1) + Math.abs(wire.y2 - wire.y1);
  if (length < 25) warnings.push(`Wire ${wire.id} is very short (${length}px)`);
  const box = { x: Math.min(wire.x1, wire.x2), y: Math.min(wire.y1, wire.y2), width: Math.abs(wire.x2 - wire.x1) || 1, height: Math.abs(wire.y2 - wire.y1) || 1 };
  for (const keepout of keepouts) {
    if (overlap(box, keepout, 0)) failures.push(`Wire ${wire.id} enters reserved area ${keepout.name}`);
  }
}

for (const component of components) {
  if (!inside(component, frame)) failures.push(`Component ${component.id} is outside drawing frame`);
  if (!inside(component, schematicArea) && !component.id.startsWith("tbl")) {
    warnings.push(`Component ${component.id} sits outside preferred schematic area`);
  }
  for (const keepout of keepouts) {
    if (overlap(component, keepout, 0)) failures.push(`Component ${component.id} overlaps reserved area ${keepout.name}`);
  }
}

for (let i = 0; i < components.length; i += 1) {
  for (let j = i + 1; j < components.length; j += 1) {
    const a = components[i];
    const b = components[j];
    if (overlap(a, b, 12)) failures.push(`Components ${a.id} and ${b.id} overlap or are too close`);
  }
}

for (const item of textItems) {
  if (!inside(item, frame)) {
    const isFrameCoordinateText = inside(item, frameHeader);
    const isElementListTitle = item.x >= elementList.x - 5 &&
      item.x + item.width <= elementList.x + elementList.width + 15 &&
      item.y >= elementList.y &&
      item.y + item.height <= elementList.y + 40;
    if (!isFrameCoordinateText && !isElementListTitle) failures.push(`Text ${item.id} is outside drawing frame`);
  }
  for (const keepout of keepouts) {
    const isElementListHeaderText = keepout.name === "element-list" &&
      item.x >= elementList.x - 5 &&
      item.x + item.width <= elementList.x + elementList.width + 5 &&
      item.y >= elementList.y - 5 &&
      item.y + item.height <= elementList.y + elementList.height + 5;
    const isFrameCoordinateText = inside(item, frameHeader);
    const isTableOrTitleText = isFrameCoordinateText ||
      isElementListHeaderText ||
      (item.x >= keepout.x - 5 &&
        item.x + item.width <= keepout.x + keepout.width + 5 &&
        item.y >= keepout.y - 5 &&
        item.y + item.height <= keepout.y + keepout.height + 5);
    if (!isTableOrTitleText && overlap(item, keepout, 0)) failures.push(`Text ${item.id} overlaps reserved area ${keepout.name}`);
  }
}

const requiredLabels = ["DD1", "VT1", "HL1", "SB1", "SB2", "XS1", "XS2", "XS3", "XS4", "A1"];
for (const label of requiredLabels) {
  if (!semanticText.some((value) => value.includes(label)) && !components.some((component) => component.id === label)) {
    failures.push(`Missing required designation ${label}`);
  }
}

const forbiddenLegacyDesignations = [
  /\bQ1\b/,
  /\bD1\b/,
  /\bU1\b/,
  /\bU3_buck\b/,
  /\bU3_reset\b/,
  /\bU4_boot\b/,
  /\bJ2_heater\b/,
  /\bCN1\b/
];
for (const pattern of forbiddenLegacyDesignations) {
  if (pattern.test(semanticBlob)) failures.push(`Legacy JLCEDA-style designation remains: ${pattern}`);
}

const requiredNetLabels = ["GND", "+3V3", "+12V", "DQ", "GATE", "LED", "BOOT", "TXD0", "RXD0"];
for (const label of requiredNetLabels) {
  const netPattern = new RegExp(`(?:^|[^A-Za-z0-9+])${label.replace("+", "\\+")}(?:$|[^A-Za-z0-9])`);
  if (!netPattern.test(semanticBlob)) failures.push(`Missing normalized net label ${label}`);
}

const expectedBom = [
  { designator: "C1", name: "Конденсатор 10 мкФ, 0603", qty: "1" },
  { designator: "C2, C4", name: "Конденсатор 0,1 мкФ, 0603", qty: "2" },
  { designator: "C3", name: "Конденсатор 100 мкФ, 0603", qty: "1" },
  { designator: "R1, R5, R6", name: "Резистор 10 кОм, 0603", qty: "3" },
  { designator: "R2", name: "Резистор 4,7 кОм, 0603", qty: "1" },
  { designator: "R3", name: "Резистор 330 Ом, 0603", qty: "1" },
  { designator: "R4", name: "Резистор 100 Ом, 0603", qty: "1" },
  { designator: "DD1", name: "Модуль ESP32-WROOM-32", qty: "1" },
  { designator: "HL1", name: "Светодиод красный, 0603", qty: "1" },
  { designator: "VT1", name: "Транзистор NMOS 3400, SOT-23", qty: "1" },
  { designator: "SB1, SB2", name: "Кнопка тактовая 6x6x7,5", qty: "2" },
  { designator: "XS1", name: "Разъем XH-3PA, 3 контакта", qty: "1" },
  { designator: "XS2, XS3", name: "Клеммник KF2EDGV-3.81-2P", qty: "2" },
  { designator: "XS4", name: "Разъем 4 контакта, шаг 5,00", qty: "1" },
  { designator: "A1", name: "Модуль питания 12 В / 3,3 В", qty: "1" }
];
for (const row of expectedBom) {
  for (const value of [row.designator, row.name, row.qty]) {
    if (!semanticText.some((text) => text.includes(value))) {
      failures.push(`BOM table is missing value: ${value}`);
    }
  }
}

const titleTexts = textItems.filter((item) => inside(item, titleBlock));
for (let i = 0; i < titleTexts.length; i += 1) {
  for (let j = i + 1; j < titleTexts.length; j += 1) {
    if (overlap(titleTexts[i], titleTexts[j], 0)) failures.push(`Title-block text ${titleTexts[i].id} overlaps ${titleTexts[j].id}`);
  }
}

for (const file of [PNG, SVG, PDF]) {
  if (fs.existsSync(file)) {
    const size = fs.statSync(file).size;
    if (size < 10_000) failures.push(`Export file is too small or corrupt: ${path.basename(file)} (${size} bytes)`);
  } else {
    warnings.push(`Export not present yet: ${path.basename(file)}`);
  }
}

if (warnings.length) {
  console.log("Warnings:");
  warnings.forEach((warning) => console.log(`- ${warning}`));
}

if (failures.length) {
  console.error("Validation failed:");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log(`Validation passed: ${wires.length} wires, ${components.length} components, ${textItems.length} text objects checked.`);
