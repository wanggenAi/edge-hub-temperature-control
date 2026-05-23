#!/usr/bin/env node
/*
 * Dry-run renderer skeleton for the ESP32 draw.io schematic workflow.
 *
 * This phase deliberately does not draw the final middle circuit. In write
 * mode it creates a no-circuit generated draw.io file that preserves only the
 * locked template regions plus their parent containers.
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const DEFAULTS = {
  sourceDrawio: path.join(ROOT, "hardware/eda/functiondiagramYUANLITU.drawio"),
  outputDrawio: path.join(ROOT, "hardware/eda/functiondiagramYUANLITU.generated.drawio"),
  schematicModel: path.join(ROOT, "hardware/eda/schematic_model.yaml"),
  styleRules: path.join(ROOT, "hardware/eda/style_rules_from_drawio.yaml"),
  reservedLock: path.join(ROOT, "hardware/eda/reserved_regions.lock.json"),
};

function parseArgs(argv) {
  const args = {
    dryRun: true,
    noCircuit: true,
    dd1Block: false,
    resetLedBlock: false,
    decouplingBlock: false,
    sensorBlock: false,
    uartBlock: false,
    bootBlock: false,
    heaterBlock: false,
    powerBlock: false,
    layoutRefinement: false,
    writeOutput: false,
    ...DEFAULTS,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--dry-run") args.dryRun = true;
    else if (arg === "--no-circuit") args.noCircuit = true;
    else if (arg === "--dd1-block") {
      args.dd1Block = true;
      args.noCircuit = false;
    }
    else if (arg === "--reset-led-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--decoupling-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--sensor-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--uart-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.uartBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--boot-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.uartBlock = true;
      args.bootBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--heater-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.uartBlock = true;
      args.bootBlock = true;
      args.heaterBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--power-block") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.uartBlock = true;
      args.bootBlock = true;
      args.heaterBlock = true;
      args.powerBlock = true;
      args.noCircuit = false;
    }
    else if (arg === "--layout-refinement") {
      args.dd1Block = true;
      args.resetLedBlock = true;
      args.decouplingBlock = true;
      args.sensorBlock = true;
      args.uartBlock = true;
      args.bootBlock = true;
      args.heaterBlock = true;
      args.powerBlock = true;
      args.layoutRefinement = true;
      args.noCircuit = false;
    }
    else if (arg === "--write-output") args.writeOutput = true;
    else if (arg === "--source") args.sourceDrawio = path.resolve(argv[++i]);
    else if (arg === "--output") args.outputDrawio = path.resolve(argv[++i]);
    else if (arg === "--model") args.schematicModel = path.resolve(argv[++i]);
    else if (arg === "--style") args.styleRules = path.resolve(argv[++i]);
    else if (arg === "--lock") args.reservedLock = path.resolve(argv[++i]);
    else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function readJsonish(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function assertExists(filePath, label) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`${label} missing: ${filePath}`);
  }
}

function validateInputs(args) {
  assertExists(args.sourceDrawio, "source draw.io");
  assertExists(args.schematicModel, "schematic model");
  assertExists(args.styleRules, "style rules");
  assertExists(args.reservedLock, "reserved region lock");
  if (path.resolve(args.sourceDrawio) === path.resolve(args.outputDrawio)) {
    throw new Error("Refusing to overwrite source draw.io; output must be functiondiagramYUANLITU.generated.drawio or another distinct path.");
  }
  const model = readJsonish(args.schematicModel);
  const style = readJsonish(args.styleRules);
  const lock = readJsonish(args.reservedLock);
  if (model.status !== "phase2_model_ref_mapping_confirmed") {
    throw new Error(`schematic_model.yaml is not confirmed; status=${model.status}`);
  }
  if (!model.connector_numbering_policy || model.connector_numbering_policy.confirmed !== true) {
    throw new Error("connector_numbering_policy must be confirmed before rendering.");
  }
  for (const region of ["outer_frame", "element_list", "title_block"]) {
    if (!lock.regions || !lock.regions[region]) {
      throw new Error(`reserved region missing from lock: ${region}`);
    }
  }
  if (!style.extracted || !style.quantified_visual_rules) {
    throw new Error("style_rules_from_drawio.yaml must contain extracted styles and quantified visual rules.");
  }
  return { model, style, lock };
}

function collectLockedIds(lock) {
  const ids = new Set(["0", "1"]);
  for (const region of Object.values(lock.regions || {})) {
    for (const cellId of region.cell_ids || []) {
      ids.add(cellId);
    }
  }
  return ids;
}

function parseCells(sourceText) {
  const cellRe = /<mxCell\b[^>]*\/>|<mxCell\b[\s\S]*?<\/mxCell>/g;
  const cells = new Map();
  let match;
  while ((match = cellRe.exec(sourceText)) !== null) {
    const xml = match[0];
    const idMatch = xml.match(/\bid="([^"]+)"/);
    if (!idMatch) continue;
    const parentMatch = xml.match(/\bparent="([^"]+)"/);
    cells.set(idMatch[1], {
      id: idMatch[1],
      parent: parentMatch ? parentMatch[1] : "",
      xml,
      index: match.index,
    });
  }
  return cells;
}

function collectKeepIds(cells, lock) {
  const keep = collectLockedIds(lock);
  for (const cellId of Array.from(keep)) {
    let cell = cells.get(cellId);
    while (cell && cell.parent && !keep.has(cell.parent)) {
      keep.add(cell.parent);
      cell = cells.get(cell.parent);
    }
  }
  return keep;
}

function addReservedContainerRole(xml, cellId) {
  if (/\bdata-role="/.test(xml) || /\brole="/.test(xml)) {
    return xml;
  }
  return xml.replace(
    "<mxCell ",
    `<mxCell data-role="${RESERVED_CONTAINER_ROLE}" data-generated="true" data-owner="renderer.no_circuit" `
  );
}

const RESERVED_CONTAINER_ROLE = "reserved_container";

function buildNoCircuitDrawio(sourceText, lock, model, style) {
  const rootStart = sourceText.indexOf("<root>");
  const rootEnd = sourceText.indexOf("</root>");
  if (rootStart < 0 || rootEnd < 0) {
    throw new Error("Invalid draw.io XML: missing <root> element.");
  }
  const cells = parseCells(sourceText);
  const keepIds = collectKeepIds(cells, lock);
  const lockedIds = collectLockedIds(lock);
  const keptCells = Array.from(cells.values())
    .filter((cell) => keepIds.has(cell.id))
    .sort((a, b) => a.index - b.index)
    .map((cell) => (cell.id === "0" || cell.id === "1" || lockedIds.has(cell.id) ? cell.xml : addReservedContainerRole(cell.xml, cell.id)));
  const elementListCells = buildElementListCells(model, style, lock).map((cell) => `        ${cell}`);

  const beforeRoot = sourceText.slice(0, rootStart + "<root>".length);
  const afterRoot = sourceText.slice(rootEnd);
  return `${beforeRoot}\n${keptCells.map((cell) => `        ${cell}`).join("\n")}\n${elementListCells.join("\n")}\n      ${afterRoot}`;
}

function xmlAttr(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function strokeWidth(style, key, fallback) {
  return style.extracted?.[key]?.value || fallback;
}

function fontSize(style, key, fallback) {
  return style.extracted?.[key]?.value || fallback;
}

function findComponent(model, ref) {
  return (model.components || []).find((component) => component.ref === ref || component.source_ref === ref);
}

function requireComponent(model, ref) {
  const component = findComponent(model, ref);
  if (!component) {
    throw new Error(`${ref} component missing from schematic_model.yaml`);
  }
  return component;
}

function selectedDd1Pins(component) {
  const selectedNumbers = new Set(["1", "2", "3", "24", "25", "30", "33", "34", "35", "38"]);
  return (component.pins || []).filter((pin) => selectedNumbers.has(String(pin.number)));
}

function dd1ReadablePinY(pin) {
  const readableRows = {
    "24": 730,
    "25": 820,
    "30": 910,
    "33": 1000,
    "34": 1090,
    "2": 1150,
    "35": 1180,
    "1": 1210,
    "38": 1300,
    "3": 1330,
  };
  return readableRows[String(pin.number)] || Number(pin.endpoint.y);
}

function textCell({ id, parent, value, x, y, width, height, role, attrs = {}, fontSizeValue = 30, align = "center" }) {
  const extra = Object.entries(attrs)
    .map(([key, val]) => ` ${key}="${xmlAttr(val)}"`)
    .join("");
  return `<mxCell id="${xmlAttr(id)}" value="${xmlAttr(value)}" style="text;html=1;strokeColor=none;fillColor=none;align=${align};verticalAlign=middle;whiteSpace=wrap;fontSize=${fontSizeValue};" parent="${xmlAttr(parent)}" vertex="1" data-role="${xmlAttr(role)}"${extra}><mxGeometry x="${x}" y="${y}" width="${width}" height="${height}" as="geometry"/></mxCell>`;
}

function vertexCell({ id, parent, value = "", x, y, width, height, role, attrs = {}, style }) {
  const extra = Object.entries(attrs)
    .map(([key, val]) => ` ${key}="${xmlAttr(val)}"`)
    .join("");
  return `<mxCell id="${xmlAttr(id)}" value="${xmlAttr(value)}" style="${xmlAttr(style)}" parent="${xmlAttr(parent)}" vertex="1" data-role="${xmlAttr(role)}"${extra}><mxGeometry x="${x}" y="${y}" width="${width}" height="${height}" as="geometry"/></mxCell>`;
}

function edgeCell({ id, parent, x1, y1, x2, y2, role, attrs = {}, style }) {
  const extra = Object.entries(attrs)
    .map(([key, val]) => ` ${key}="${xmlAttr(val)}"`)
    .join("");
  return `<mxCell id="${xmlAttr(id)}" value="" style="${xmlAttr(style)}" parent="${xmlAttr(parent)}" edge="1" data-role="${xmlAttr(role)}"${extra}><mxGeometry relative="1" as="geometry"><mxPoint x="${x1}" y="${y1}" as="sourcePoint"/><mxPoint x="${x2}" y="${y2}" as="targetPoint"/></mxGeometry></mxCell>`;
}

function wireAttrs(component, pin, label = pin.name) {
  return {
    "data-generated": "true",
    "data-owner": "render_esp32_drawio.js",
    "data-net": pin.net,
    "data-source-net": pin.source_net || pin.net,
    "data-zone": component.zone,
    "data-ref": component.ref,
    "data-source-ref": component.source_ref,
    "data-pin": label,
    "data-pin-number": pin.number,
  };
}

function generatedAttrs(component, pin = null) {
  const attrs = {
    "data-generated": "true",
    "data-owner": "render_esp32_drawio.js",
    "data-ref": component.ref,
    "data-source-ref": component.source_ref,
    "data-zone": component.zone,
  };
  if (pin) {
    attrs["data-pin"] = pin.name;
    attrs["data-pin-number"] = pin.number;
    attrs["data-net"] = pin.net;
    attrs["data-source-net"] = pin.source_net || pin.net;
  }
  return attrs;
}

function elementListRows(model) {
  const existingRefs = new Set((model.components || []).map((component) => component.ref));
  const groups = [
    {
      name: "Capacitors",
      items: [
        { refs: ["C1", "C4"], name: "Capacitor 0.1 uF 0603", qty: "2", note: "LCSC" },
        { refs: ["C2"], name: "Capacitor 10 uF 0603", qty: "1", note: "LCSC" },
        { refs: ["C3"], name: "Capacitor 100 uF 0603", qty: "1", note: "LCSC" },
      ],
    },
    {
      name: "Resistors",
      items: [
        { refs: ["R1", "R5", "R6"], name: "Resistor 10 kOhm 0603", qty: "3", note: "LCSC" },
        { refs: ["R2"], name: "Resistor 4.7 kOhm 0603", qty: "1", note: "Sensor pull-up" },
        { refs: ["R3"], name: "Resistor 330 Ohm 0603", qty: "1", note: "LED series" },
        { refs: ["R4"], name: "Resistor 100 Ohm 0603", qty: "1", note: "Gate resistor" },
      ],
    },
    {
      name: "Semiconductor Devices",
      items: [
        { refs: ["DD1"], name: "ESP32-WROOM-32 module", qty: "1", note: "Espressif" },
        { refs: ["HL1"], name: "Red LED 0603", qty: "1", note: "LCSC" },
        { refs: ["VT1"], name: "NMOS3400 N-channel MOSFET", qty: "1", note: "SOT-23" },
      ],
    },
    {
      name: "Switching Components",
      items: [
        { refs: ["SB1", "SB2"], name: "Tact switch SMT 6x6x7.5", qty: "2", note: "RESET, BOOT" },
      ],
    },
    {
      name: "Connectors",
      items: [
        { refs: ["XS1"], name: "XH-3PA 3-pin sensor connector", qty: "1", note: "ZHOURI" },
        { refs: ["XS2", "XS3"], name: "KF2EDGV-3.81-2P terminal", qty: "2", note: "Heater, power" },
        { refs: ["XS4"], name: "Header45.08-4P connector", qty: "1", note: "UART" },
        { refs: ["XS5"], name: "KF301-2P thermal switch terminal", qty: "1", note: "Safety" },
      ],
    },
    {
      name: "Power Modules",
      items: [
        { refs: ["A1"], name: "DC/DC converter 12 V to 3.3 V", qty: "1", note: "Buck module" },
      ],
    },
  ];
  const coveredRefs = new Set();
  const rows = [];
  groups.forEach((group, groupIndex) => {
    rows.push({ type: "group", name: group.name });
    for (const item of group.items) {
      for (const ref of item.refs) {
        if (!existingRefs.has(ref)) {
          throw new Error(`Element list references missing component ${ref}`);
        }
        coveredRefs.add(ref);
      }
      rows.push({ type: "item", ...item });
    }
    if (groupIndex !== groups.length - 1) {
      rows.push({ type: "blank" });
    }
  });
  const uncovered = [...existingRefs].filter((ref) => !coveredRefs.has(ref)).sort();
  if (uncovered.length) {
    throw new Error(`Element list does not cover component refs: ${uncovered.join(", ")}`);
  }
  return rows;
}

function elementListAttrs(extra = {}) {
  return {
    "data-generated": "true",
    "data-owner": "render_esp32_drawio.js",
    "data-region": "element_list",
    ...extra,
  };
}

function buildElementListCells(model, style, lock) {
  const region = lock.regions?.element_list?.bbox;
  if (!region) {
    throw new Error("element_list reserved region missing bbox");
  }
  const x = Number(region.x);
  const y = Number(region.y);
  const width = Number(region.width);
  const height = Number(region.height);
  const right = x + width;
  const bottom = y + height;
  const strokeMajor = 3.937;
  const strokeMinor = 1.9685;
  const headerFont = 24;
  const bodyFont = 22;
  const headerHeight = 64;
  const rows = elementListRows(model);
  const rowHeight = (height - headerHeight) / rows.length;
  const columns = [
    { id: "ref", title: "Position number", x: x, width: 149 },
    { id: "name", title: "Name", x: x + 149, width: 340 },
    { id: "qty", title: "Qty.", x: x + 489, width: 68 },
    { id: "note", title: "Note", x: x + 557, width: right - (x + 557) },
  ];
  const lineStyleMajor = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${strokeMajor};`;
  const lineStyleMinor = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${strokeMinor};`;
  const cells = [];
  for (const xLine of [x + 149, x + 489, x + 557]) {
    cells.push(edgeCell({
      id: `element_list.line.v.${Math.round(xLine)}`,
      parent: "1",
      x1: roundCoord(xLine),
      y1: roundCoord(y),
      x2: roundCoord(xLine),
      y2: roundCoord(bottom),
      role: "element_list_line",
      attrs: elementListAttrs({ "data-line-type": "vertical-major" }),
      style: lineStyleMajor,
    }));
  }
  columns.forEach((column) => {
    cells.push(textCell({
      id: `element_list.text.header.${column.id}`,
      parent: "1",
      value: column.title,
      x: roundCoord(column.x + 2),
      y: roundCoord(y + 2),
      width: roundCoord(column.width - 4),
      height: roundCoord(headerHeight - 4),
      role: "element_list_text",
      fontSizeValue: headerFont,
      attrs: elementListAttrs({ "data-row-type": "header", "data-column": column.id }),
    }));
  });
  cells.push(edgeCell({
    id: "element_list.line.h.header",
    parent: "1",
    x1: roundCoord(x),
    y1: roundCoord(y + headerHeight),
    x2: roundCoord(right),
    y2: roundCoord(y + headerHeight),
    role: "element_list_line",
    attrs: elementListAttrs({ "data-line-type": "header-major" }),
    style: lineStyleMajor,
  }));

  let rowY = y + headerHeight;
  rows.forEach((row, rowIndex) => {
    const rowId = String(rowIndex).padStart(2, "0");
    if (row.type === "group") {
      cells.push(textCell({
        id: `element_list.text.group.${xmlSafeId(row.name)}`,
        parent: "1",
        value: row.name,
        x: roundCoord(columns[1].x + 2),
        y: roundCoord(rowY + 2),
        width: roundCoord(columns[1].width - 4),
        height: roundCoord(rowHeight - 4),
        role: "element_list_text",
        fontSizeValue: bodyFont,
        attrs: elementListAttrs({ "data-row-type": "group", "data-group": row.name, "data-row-index": rowId, "data-column": "name" }),
      }));
    } else if (row.type === "item") {
      const values = {
        ref: row.refs.join(", "),
        name: row.name,
        qty: row.qty,
        note: row.note,
      };
      columns.forEach((column) => {
        cells.push(textCell({
          id: `element_list.text.${xmlSafeId(values.ref)}.${column.id}`,
          parent: "1",
          value: values[column.id],
          x: roundCoord(column.x + 2),
          y: roundCoord(rowY + 2),
          width: roundCoord(column.width - 4),
          height: roundCoord(rowHeight - 4),
          role: "element_list_text",
          fontSizeValue: bodyFont,
          attrs: elementListAttrs({ "data-row-type": "item", "data-refs": values.ref, "data-row-index": rowId, "data-column": column.id }),
        }));
      });
    }
    const lineY = rowY + rowHeight;
    if (rowIndex !== rows.length - 1) {
      cells.push(edgeCell({
        id: `element_list.line.h.${rowId}`,
        parent: "1",
        x1: roundCoord(x),
        y1: roundCoord(lineY),
        x2: roundCoord(right),
        y2: roundCoord(lineY),
        role: "element_list_line",
        attrs: elementListAttrs({ "data-line-type": "row-minor", "data-row-index": rowId }),
        style: lineStyleMinor,
      }));
    }
    rowY = lineY;
  });
  return cells;
}

function roundCoord(value) {
  return Number(value).toFixed(3).replace(/\.?0+$/, "");
}

function referenceComponentStyle(style) {
  const reference = style.reference_component_table || {};
  const lock = style.renderer_component_style_lock || {};
  return {
    commonWidth: Number(lock.common_body_width?.value || 210),
    minRowHeight: Number(reference.row_height_median?.value || 61),
    splitColumnRatio: Number(lock.split_column_ratio?.value || 0.5),
  };
}

function lockedBodyBox(box, style, options = {}) {
  const reference = referenceComponentStyle(style);
  const width = options.preserveWidth ? box.width : reference.commonWidth;
  const x = options.centerLockedWidth ? box.x + (box.width - width) / 2 : box.x;
  return { ...box, x, width };
}

function rowsByY(pinSpecs) {
  const rows = [];
  for (const spec of pinSpecs) {
    let row = rows.find((candidate) => Math.abs(candidate.y - spec.y) < 0.001);
    if (!row) {
      row = { y: spec.y, specs: [] };
      rows.push(row);
    }
    row.specs.push(spec);
  }
  return rows.sort((a, b) => a.y - b.y);
}

function tableLineStyle(strokeWidthValue) {
  return `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${strokeWidthValue};`;
}

function componentTableLine({ id, parent, ref, x1, y1, x2, y2, style, lineType }) {
  return edgeCell({
    id,
    parent,
    x1,
    y1,
    x2,
    y2,
    role: "component_table_line",
    attrs: {
      "data-generated": "true",
      "data-owner": "render_esp32_drawio.js",
      "data-ref": ref,
      "data-line-type": lineType,
      "data-style-source": "functiondiagramYUANLITU.drawio",
    },
    style,
  });
}

function componentPinLabelBox(body, rowSpecs, side, label) {
  const hasBothSides = rowSpecs.some((spec) => (spec.side || "left") === "left")
    && rowSpecs.some((spec) => (spec.side || "left") === "right");
  const padding = 8;
  if (hasBothSides) {
    const half = body.width / 2;
    if (side === "right") {
      return { x: body.x + half + padding, width: half - padding * 2 };
    }
    return { x: body.x + padding, width: half - padding * 2 };
  }
  return {
    x: body.x + padding,
    width: Math.max(40, body.width - padding * 2, String(label).length * 12),
  };
}

function buildDd1BlockCells(model, style) {
  const component = requireComponent(model, "DD1");
  const pins = selectedDd1Pins(component);
  if (pins.length !== 10) {
    throw new Error(`DD1 checkpoint requires 10 selected pins, found ${pins.length}`);
  }

  const rootId = "generated.schematic.root";
  const wireStroke = strokeWidth(style, "wire_stroke_width", 1.9685);
  const bodyStroke = strokeWidth(style, "component_body_stroke_width", 1.9685);
  const refFont = fontSize(style, "component_ref_font_size", 30);
  const valueFont = fontSize(style, "component_value_font_size", 30);
  const pinFont = fontSize(style, "pin_label_font_size", 30);
  const netFont = fontSize(style, "net_label_font_size", 15);
  const body = lockedBodyBox({ x: 940, y: 640, width: 420, height: 760 }, style);
  const pinLength = 60;
  const wireLength = 140;
  const textHeight = 24;
  const reference = referenceComponentStyle(style);
  const rowGroups = rowsByY(pins.map((pin) => ({ ...pin, side: pin.side || "left", y: dd1ReadablePinY(pin), label: pin.name })));
  const lineStyle = tableLineStyle(wireStroke);
  const cells = [
    vertexCell({
      id: rootId,
      parent: "1",
      x: 0,
      y: 0,
      width: 2550,
      height: 2100,
      role: "schematic_root",
      attrs: {
        "data-generated": "true",
        "data-owner": "render_esp32_drawio.js",
        "data-zone": "main_schematic_area",
      },
      style: "group;strokeWidth=1.9685;",
    }),
    vertexCell({
      id: "component.DD1.body",
      parent: rootId,
      x: body.x,
      y: body.y,
      width: body.width,
      height: body.height,
      role: "component_body",
      attrs: {
        ...generatedAttrs(component),
        "data-style-lock": "reference_table_component",
        "data-style-source": "functiondiagramYUANLITU.drawio",
        "data-common-width": String(reference.commonWidth),
      },
      style: `shape=table;startSize=0;container=1;collapsible=0;childLayout=tableLayout;fillColor=none;strokeColor=#000000;strokeWidth=${bodyStroke};`,
    }),
    textCell({
      id: "component.DD1.ref",
      parent: rootId,
      value: "DD1",
      x: body.x + body.width / 2 - 45,
      y: body.y - 52,
      width: 90,
      height: 36,
      role: "component_ref",
      attrs: generatedAttrs(component),
      fontSizeValue: refFont,
    }),
    textCell({
      id: "component.DD1.value",
      parent: rootId,
      value: component.value,
      x: body.x - 70,
      y: body.y + body.height + 14,
      width: body.width + 140,
      height: 44,
      role: "component_value",
      attrs: generatedAttrs(component),
      fontSizeValue: valueFont,
    }),
  ];

  const boundaryYs = [body.y, ...rowGroups.slice(1).map((row, index) => (row.y + rowGroups[index].y) / 2), body.y + body.height];
  for (let index = 1; index < boundaryYs.length - 1; index += 1) {
    cells.push(componentTableLine({
      id: `component.DD1.table.h.${index}`,
      parent: rootId,
      ref: "DD1",
      x1: body.x,
      y1: boundaryYs[index],
      x2: body.x + body.width,
      y2: boundaryYs[index],
      style: tableLineStyle(bodyStroke),
      lineType: "row",
    }));
  }
  if (rowGroups.some((row) => row.specs.some((spec) => spec.side === "left") && row.specs.some((spec) => spec.side === "right"))) {
    cells.push(componentTableLine({
      id: "component.DD1.table.v.split",
      parent: rootId,
      ref: "DD1",
      x1: body.x + body.width * reference.splitColumnRatio,
      y1: body.y,
      x2: body.x + body.width * reference.splitColumnRatio,
      y2: body.y + body.height,
      style: tableLineStyle(bodyStroke),
      lineType: "column",
    }));
  }

  for (const pin of pins) {
    const isLeft = pin.side === "left";
    const bodyX = isLeft ? body.x : body.x + body.width;
    const pinOuterX = isLeft ? body.x - pinLength : body.x + body.width + pinLength;
    const wireOuterX = isLeft ? pinOuterX - wireLength : pinOuterX + wireLength;
    const y = dd1ReadablePinY(pin);
    const pinCenterX = (bodyX + pinOuterX) / 2;
    const netWidth = Math.max(72, String(pin.net).length * 18);
    const row = rowGroups.find((candidate) => Math.abs(candidate.y - y) < 0.001);
    const labelBox = componentPinLabelBox(body, row ? row.specs : [{ side: pin.side }], pin.side, pin.name);
    const netLabelX = isLeft ? wireOuterX - netWidth / 2 : wireOuterX - netWidth / 2;
    const attrs = generatedAttrs(component, pin);
    cells.push(
      edgeCell({
        id: `pin.DD1.${xmlSafeId(pin.name)}.${pin.number}`,
        parent: rootId,
        x1: isLeft ? pinOuterX : bodyX,
        y1: y,
        x2: isLeft ? bodyX : pinOuterX,
        y2: y,
        role: "pin",
        attrs,
        style: lineStyle,
      }),
      textCell({
        id: `label.pin.DD1.${xmlSafeId(pin.name)}.${pin.number}`,
        parent: rootId,
        value: pin.name,
        x: labelBox.x,
        y: y - textHeight / 2,
        width: labelBox.width,
        height: textHeight,
        role: "pin_label",
        attrs: {
          ...attrs,
          "data-label-policy": "inside_table_row",
          "data-style-source": "functiondiagramYUANLITU.drawio",
        },
        fontSizeValue: pinFont,
      }),
      edgeCell({
        id: `wire.${xmlSafeId(pin.net)}.${pin.number}`,
        parent: rootId,
        x1: isLeft ? wireOuterX : pinOuterX,
        y1: y,
        x2: isLeft ? pinOuterX : wireOuterX,
        y2: y,
        role: "wire",
        attrs: {
          "data-generated": "true",
          "data-owner": "render_esp32_drawio.js",
          "data-net": pin.net,
          "data-source-net": pin.source_net || pin.net,
          "data-zone": component.zone,
          "data-ref": component.ref,
          "data-source-ref": component.source_ref,
          "data-pin": pin.name,
          "data-pin-number": pin.number,
        },
        style: lineStyle,
      }),
      textCell({
        id: `netlabel.${xmlSafeId(pin.net)}.${pin.number}`,
        parent: rootId,
        value: pin.net,
        x: netLabelX,
        y: y - textHeight - 6,
        width: netWidth,
        height: textHeight,
        role: "net_label",
        attrs: {
          "data-generated": "true",
          "data-owner": "render_esp32_drawio.js",
          "data-net": pin.net,
          "data-source-net": pin.source_net || pin.net,
          "data-zone": component.zone,
          "data-anchor-x": wireOuterX,
          "data-anchor-y": y,
        },
        fontSizeValue: netFont,
      })
    );
  }
  return cells;
}

function findPin(component, number) {
  const pin = (component.pins || []).find((candidate) => String(candidate.number) === String(number));
  if (!pin) {
    throw new Error(`${component.ref} pin ${number} missing from schematic_model.yaml`);
  }
  return pin;
}

function buildComponentBoxCells(component, box, style, pinSpecs, options = {}) {
  const wireStroke = strokeWidth(style, "wire_stroke_width", 1.9685);
  const bodyStroke = strokeWidth(style, "component_body_stroke_width", 1.9685);
  const refFont = fontSize(style, "component_ref_font_size", 30);
  const valueFont = fontSize(style, "component_value_font_size", 30);
  const pinFont = fontSize(style, "pin_label_font_size", 30);
  const netFont = fontSize(style, "net_label_font_size", 15);
  const parent = options.parent || "generated.schematic.root";
  const textHeight = options.textHeight || 24;
  const pinLength = options.pinLength || 60;
  const wireLength = options.wireLength || 90;
  const body = lockedBodyBox(box, style, { preserveWidth: options.preserveWidth, centerLockedWidth: options.centerLockedWidth === true });
  const reference = referenceComponentStyle(style);
  const rowGroups = rowsByY(pinSpecs);
  const cells = [
    vertexCell({
      id: `component.${component.ref}.body`,
      parent,
      x: body.x,
      y: body.y,
      width: body.width,
      height: body.height,
      role: "component_body",
      attrs: {
        ...generatedAttrs(component),
        "data-style-lock": "reference_table_component",
        "data-style-source": "functiondiagramYUANLITU.drawio",
        "data-common-width": String(reference.commonWidth),
      },
      style: `shape=table;startSize=0;container=1;collapsible=0;childLayout=tableLayout;fillColor=none;strokeColor=#000000;strokeWidth=${bodyStroke};`,
    }),
    textCell({
      id: `component.${component.ref}.ref`,
      parent,
      value: component.ref,
      x: body.x + body.width / 2 - 45,
      y: body.y - 46,
      width: 90,
      height: 30,
      role: "component_ref",
      attrs: generatedAttrs(component),
      fontSizeValue: refFont,
    }),
    textCell({
      id: `component.${component.ref}.value`,
      parent,
      value: englishValue(component),
      x: body.x + 10,
      y: body.y + body.height + 14,
      width: body.width - 20,
      height: 30,
      role: "component_value",
      attrs: generatedAttrs(component),
      fontSizeValue: valueFont,
    }),
  ];

  const boundaryYs = [body.y, ...rowGroups.slice(1).map((row, index) => (row.y + rowGroups[index].y) / 2), body.y + body.height];
  for (let index = 1; index < boundaryYs.length - 1; index += 1) {
    cells.push(componentTableLine({
      id: `component.${component.ref}.table.h.${index}`,
      parent,
      ref: component.ref,
      x1: body.x,
      y1: boundaryYs[index],
      x2: body.x + body.width,
      y2: boundaryYs[index],
      style: tableLineStyle(bodyStroke),
      lineType: "row",
    }));
  }
  if (rowGroups.some((row) => row.specs.some((spec) => (spec.side || "left") === "left") && row.specs.some((spec) => (spec.side || "left") === "right"))) {
    cells.push(componentTableLine({
      id: `component.${component.ref}.table.v.split`,
      parent,
      ref: component.ref,
      x1: body.x + body.width * reference.splitColumnRatio,
      y1: body.y,
      x2: body.x + body.width * reference.splitColumnRatio,
      y2: body.y + body.height,
      style: tableLineStyle(bodyStroke),
      lineType: "column",
    }));
  }

  for (const spec of pinSpecs) {
    const pin = findPin(component, spec.number);
    const side = spec.side || pin.side || "left";
    const y = spec.y;
    const isLeft = side === "left";
    const bodyX = isLeft ? box.x : box.x + box.width;
    const pinOuterX = isLeft ? bodyX - pinLength : bodyX + pinLength;
    const wireOuterX = isLeft ? pinOuterX - wireLength : pinOuterX + wireLength;
    const pinCenterX = (bodyX + pinOuterX) / 2;
    const label = spec.label || pin.name;
    const row = rowGroups.find((candidate) => Math.abs(candidate.y - y) < 0.001);
    const labelBox = componentPinLabelBox(body, row ? row.specs : [spec], side, label);
    const labelWidth = labelBox.width;
    const netWidth = Math.max(72, String(pin.net).length * 18);
    const labelX = labelBox.x;
    const netLabelX = wireOuterX - netWidth / 2;
    const lineStyle = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${wireStroke};`;
    const attrs = generatedAttrs(component, { ...pin, name: label });
    const pinAndLabelCells = [
      edgeCell({
        id: `pin.${component.ref}.${xmlSafeId(label)}.${pin.number}`,
        parent,
        x1: isLeft ? pinOuterX : bodyX,
        y1: y,
        x2: isLeft ? bodyX : pinOuterX,
        y2: y,
        role: "pin",
        attrs,
        style: lineStyle,
      }),
      textCell({
        id: `label.pin.${component.ref}.${xmlSafeId(label)}.${pin.number}`,
        parent,
        value: label,
        x: labelX,
        y: y - textHeight / 2,
        width: labelWidth,
        height: textHeight,
        role: "pin_label",
        attrs: {
          ...attrs,
          "data-label-policy": "inside_table_row",
          "data-style-source": "functiondiagramYUANLITU.drawio",
        },
        fontSizeValue: pinFont,
      }),
    ];
    const wireAndLabelCells = [];
    if (spec.renderWire !== false) {
      wireAndLabelCells.push(
      edgeCell({
        id: `wire.${component.ref}.${xmlSafeId(pin.net)}.${pin.number}`,
        parent,
        x1: isLeft ? wireOuterX : pinOuterX,
        y1: y,
        x2: isLeft ? pinOuterX : wireOuterX,
        y2: y,
        role: "wire",
        attrs: wireAttrs(component, pin, label),
        style: lineStyle,
      })
      );
    }
    if (spec.renderNetLabel !== false) {
      wireAndLabelCells.push(
      textCell({
        id: `netlabel.${component.ref}.${xmlSafeId(pin.net)}.${pin.number}`,
        parent,
        value: pin.net,
        x: netLabelX,
        y: y - textHeight - 6,
        width: netWidth,
        height: textHeight,
        role: "net_label",
        attrs: {
          "data-generated": "true",
          "data-owner": "render_esp32_drawio.js",
          "data-net": pin.net,
          "data-source-net": pin.source_net || pin.net,
          "data-zone": component.zone,
          "data-anchor-x": wireOuterX,
          "data-anchor-y": y,
        },
        fontSizeValue: netFont,
      })
      );
    }
    cells.push(...pinAndLabelCells, ...wireAndLabelCells);
  }
  return cells;
}

function buildLocalWire({ id, parent = "generated.schematic.root", net, sourceNet, zone, x1, y1, x2, y2, style, ref = "LOCAL", sourceRef = "LOCAL", pin = "LOCAL", pinNumber = "0" }) {
  return edgeCell({
    id,
    parent,
    x1,
    y1,
    x2,
    y2,
    role: "wire",
    attrs: {
      "data-generated": "true",
      "data-owner": "render_esp32_drawio.js",
      "data-net": net,
      "data-source-net": sourceNet || net,
      "data-zone": zone,
      "data-ref": ref,
      "data-source-ref": sourceRef,
      "data-pin": pin,
      "data-pin-number": pinNumber,
    },
    style,
  });
}

function englishValue(component) {
  const overrides = {
    C1: "0.1 uF",
    C2: "10 uF",
    C3: "100 uF",
    C4: "0.1 uF",
    A1: "DC/DC 12V to 3.3V",
    R1: "10 kOhm",
    R2: "4.7 kOhm",
    R3: "330 Ohm",
    R4: "100 Ohm",
    R5: "10 kOhm",
    R6: "10 kOhm",
    SB1: "RESET button",
    SB2: "BOOT button",
    HL1: "Red LED",
    VT1: "NMOS3400",
    XS2: "Heater",
    XS1: "XH-3PA",
    XS3: "Power input",
    XS4: "UART service",
    XS5: "Thermal switch",
  };
  return overrides[component.ref] || component.value || component.type || component.ref;
}

function buildPowerBlockCells(model, style) {
  const a1 = requireComponent(model, "A1");
  const xs3 = requireComponent(model, "XS3");
  const c3 = requireComponent(model, "C3");
  const c4 = requireComponent(model, "C4");
  return [
    ...buildComponentBoxCells(xs3, { x: 1600, y: 1595, width: 210, height: 110 }, style, [
      { number: "1", side: "left", y: 1630, label: "+12V" },
      { number: "2", side: "left", y: 1685, label: "GND" },
    ], { pinLength: 50, wireLength: 45 }),
    ...buildComponentBoxCells(a1, { x: 1980, y: 1530, width: 210, height: 205 }, style, [
      { number: "1", side: "left", y: 1575, label: "+12V IN" },
      { number: "2", side: "left", y: 1620, label: "GND" },
      { number: "3", side: "left", y: 1665, label: "GND" },
      { number: "4", side: "right", y: 1710, label: "+3V3 OUT" },
    ], { pinLength: 50, wireLength: 45 }),
    ...buildComponentBoxCells(c3, { x: 1600, y: 1815, width: 210, height: 80 }, style, [
      { number: "1", side: "left", y: 1855, label: "GND" },
      { number: "2", side: "right", y: 1855, label: "+12V" },
    ], { pinLength: 50, wireLength: 45 }),
    ...buildComponentBoxCells(c4, { x: 2220, y: 1840, width: 210, height: 80 }, style, [
      { number: "1", side: "left", y: 1880, label: "GND" },
      { number: "2", side: "right", y: 1880, label: "+12V" },
    ], { pinLength: 50, wireLength: 45 }),
  ];
}

function buildHeaterBlockCells(model, style) {
  const r4 = requireComponent(model, "R4");
  const r5 = requireComponent(model, "R5");
  const vt1 = requireComponent(model, "VT1");
  const xs2 = requireComponent(model, "XS2");
  const xs5 = requireComponent(model, "XS5");
  const wireStroke = strokeWidth(style, "wire_stroke_width", 1.9685);
  const lineStyle = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${wireStroke};`;
  return [
    ...buildComponentBoxCells(r4, { x: 1660, y: 910, width: 210, height: 70 }, style, [
      { number: "1", side: "left", y: 940, label: "GATE" },
      { number: "2", side: "right", y: 940, label: "GATE_R", renderWire: false, renderNetLabel: false },
    ], { pinLength: 50, wireLength: 45 }),
    ...buildComponentBoxCells(r5, { x: 1660, y: 1145, width: 210, height: 70 }, style, [
      { number: "1", side: "right", y: 1185, label: "GATE_R", renderWire: false, renderNetLabel: false },
      { number: "2", side: "left", y: 1185, label: "GND" },
    ], { pinLength: 50, wireLength: 45 }),
    ...buildComponentBoxCells(vt1, { x: 1940, y: 890, width: 210, height: 160 }, style, [
      { number: "1", side: "left", y: 940, label: "GATE_R", renderWire: false, renderNetLabel: false },
      { number: "2", side: "right", y: 1025, label: "GND", renderWire: false, renderNetLabel: false },
      { number: "3", side: "right", y: 985, label: "HEAT-", renderWire: false, renderNetLabel: false },
    ], { pinLength: 40, wireLength: 45 }),
    ...buildComponentBoxCells(xs2, { x: 2240, y: 895, width: 210, height: 105 }, style, [
      { number: "1", side: "left", y: 930, label: "HEAT+", renderWire: false, renderNetLabel: false },
      { number: "2", side: "left", y: 985, label: "HEAT-", renderWire: false, renderNetLabel: false },
    ], { pinLength: 40, wireLength: 45 }),
    ...buildComponentBoxCells(xs5, { x: 2240, y: 1165, width: 210, height: 100 }, style, [
      { number: "1", side: "left", y: 1205, label: "+12V" },
      { number: "2", side: "left", y: 1250, label: "HEAT+" },
    ], { pinLength: 40, wireLength: 45 }),
    buildLocalWire({
      id: "wire.local.GATE_R.R4_VT1_R5",
      net: "GATE_R",
      sourceNet: "$1N24",
      zone: "mosfet_heater_driver",
      ref: "R4_VT1_R5",
      sourceRef: "R4_Q1_R5",
      pin: "GATE_R",
      pinNumber: "2_1_1",
      x1: 1920,
      y1: 940,
      x2: 1920,
      y2: 1185,
      style: lineStyle,
    }),
    buildLocalWire({
      id: "wire.local.GATE_R.R4_bus",
      net: "GATE_R",
      sourceNet: "$1N24",
      zone: "mosfet_heater_driver",
      ref: "R4_VT1_R5",
      sourceRef: "R4_Q1_R5",
      pin: "GATE_R",
      pinNumber: "2_1_1",
      x1: 1920,
      y1: 940,
      x2: 1920,
      y2: 940,
      style: lineStyle,
    }),
    buildLocalWire({
      id: "wire.local.GATE_R.R5_bus",
      net: "GATE_R",
      sourceNet: "$1N24",
      zone: "mosfet_heater_driver",
      ref: "R4_VT1_R5",
      sourceRef: "R4_Q1_R5",
      pin: "GATE_R",
      pinNumber: "2_1_1",
      x1: 1920,
      y1: 1185,
      x2: 1920,
      y2: 1185,
      style: lineStyle,
    }),
    buildLocalWire({
      id: "wire.local.HEAT-.VT1_XS2",
      net: "HEAT-",
      sourceNet: "$1N29",
      zone: "mosfet_heater_driver",
      ref: "VT1_XS2",
      sourceRef: "Q1_J2_heater",
      pin: "HEAT-",
      pinNumber: "3_2",
      x1: 2190,
      y1: 985,
      x2: 2200,
      y2: 985,
      style: lineStyle,
    }),
  ];
}

function buildBootBlockCells(model, style) {
  const r6 = requireComponent(model, "R6");
  const sb2 = requireComponent(model, "SB2");
  const localStubOptions = { wireLength: 45 };
  return [
    ...buildComponentBoxCells(r6, { x: 1090, y: 1670, width: 210, height: 90 }, style, [
      { number: "1", side: "right", y: 1710, label: "BOOT" },
      { number: "2", side: "left", y: 1710, label: "+3V3" },
    ], localStubOptions),
    ...buildComponentBoxCells(sb2, { x: 1090, y: 1885, width: 210, height: 90 }, style, [
      { number: "1", side: "right", y: 1930, label: "BOOT" },
      { number: "3", side: "left", y: 1930, label: "GND" },
    ], localStubOptions),
  ];
}

function buildUartBlockCells(model, style) {
  const xs4 = requireComponent(model, "XS4");
  const localStubOptions = { wireLength: 45, pinLength: 60 };
  return [
    ...buildComponentBoxCells(xs4, { x: 1640, y: 560, width: 210, height: 185 }, style, [
      { number: "1", side: "right", y: 600, label: "+3V3" },
      { number: "2", side: "right", y: 640, label: "GND" },
      { number: "3", side: "right", y: 680, label: "RXD0" },
      { number: "4", side: "right", y: 720, label: "TXD0" },
    ], localStubOptions),
  ];
}

function buildSensorBlockCells(model, style) {
  const r2 = requireComponent(model, "R2");
  const xs1 = requireComponent(model, "XS1");
  const localStubOptions = { wireLength: 45 };
  const localDqOptions = { wireLength: 45, pinLength: 60 };
  const wireStroke = strokeWidth(style, "wire_stroke_width", 1.9685);
  const lineStyle = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${wireStroke};`;
  return [
    ...buildComponentBoxCells(r2, { x: 1640, y: 305, width: 210, height: 90 }, style, [
      { number: "1", side: "right", y: 350, label: "DQ", renderWire: false, renderNetLabel: false },
      { number: "2", side: "left", y: 350, label: "+3V3" },
    ], localDqOptions),
    ...buildComponentBoxCells(xs1, { x: 1990, y: 270, width: 210, height: 170 }, style, [
      { number: "1", side: "right", y: 310, label: "GND" },
      { number: "2", side: "left", y: 350, label: "DQ", renderWire: false, renderNetLabel: false },
      { number: "3", side: "right", y: 390, label: "+3V3" },
    ], localStubOptions),
    buildLocalWire({
      id: "wire.local.DQ.R2_XS1",
      net: "DQ",
      sourceNet: "$1N14",
      zone: "ds18b20_sensor_connector",
      ref: "R2_XS1",
      sourceRef: "R2_CN1",
      pin: "DQ",
      pinNumber: "1_2",
      x1: 1910,
      y1: 350,
      x2: 1930,
      y2: 350,
      style: lineStyle,
    }),
  ];
}

function buildDecouplingBlockCells(model, style) {
  const c1 = requireComponent(model, "C1");
  const c2 = requireComponent(model, "C2");
  const localStubOptions = { wireLength: 45 };
  return [
    ...buildComponentBoxCells(c1, { x: 300, y: 270, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 310, label: "+3V3" },
      { number: "2", side: "right", y: 310, label: "GND" },
    ], localStubOptions),
    ...buildComponentBoxCells(c2, { x: 300, y: 470, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 510, label: "+3V3" },
      { number: "2", side: "right", y: 510, label: "GND" },
    ], localStubOptions),
  ];
}

function buildResetLedBlockCells(model, style) {
  const r1 = requireComponent(model, "R1");
  const sb1 = requireComponent(model, "SB1");
  const r3 = requireComponent(model, "R3");
  const hl1 = requireComponent(model, "HL1");
  const localStubOptions = { wireLength: 45 };
  const ledLocalOptions = { wireLength: 45, pinLength: 10 };
  const wireStroke = strokeWidth(style, "wire_stroke_width", 1.9685);
  const lineStyle = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${wireStroke};`;
  return [
    ...buildComponentBoxCells(r1, { x: 360, y: 690, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 730, label: "+3V3" },
      { number: "2", side: "right", y: 730, label: "EN" },
    ], localStubOptions),
    ...buildComponentBoxCells(sb1, { x: 360, y: 875, width: 210, height: 90 }, style, [
      { number: "2", side: "right", y: 920, label: "EN" },
      { number: "4", side: "left", y: 920, label: "GND" },
    ], localStubOptions),
    ...buildComponentBoxCells(r3, { x: 250, y: 1330, width: 210, height: 90 }, style, [
      { number: "1", side: "right", y: 1370, label: "LED_A", labelWidth: 72, renderWire: false, renderNetLabel: false },
      { number: "2", side: "left", y: 1370, label: "+3V3" },
    ], ledLocalOptions),
    ...buildComponentBoxCells(hl1, { x: 550, y: 1330, width: 210, height: 190 }, style, [
      { number: "1", side: "left", y: 1500, label: "LED" },
      { number: "2", side: "left", y: 1370, label: "LED_A", labelWidth: 72, renderWire: false, renderNetLabel: false },
    ], ledLocalOptions),
    buildLocalWire({
      id: "wire.local.LED_A.R3_HL1",
      net: "LED_A",
      sourceNet: "$1N18",
      zone: "led_status",
      ref: "R3_HL1",
      sourceRef: "R3_D1",
      pin: "LED_A",
      pinNumber: "1_2",
      x1: 470,
      y1: 1370,
      x2: 540,
      y2: 1370,
      style: lineStyle,
    }),
  ];
}

function xmlSafeId(value) {
  return String(value).replace(/[^A-Za-z0-9_.+-]+/g, "_");
}

function buildDd1BlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = buildDd1BlockCells(model, style).map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildResetLedBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildDecouplingBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildSensorBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
    ...buildSensorBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildUartBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
    ...buildSensorBlockCells(model, style),
    ...buildUartBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildBootBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
    ...buildSensorBlockCells(model, style),
    ...buildUartBlockCells(model, style),
    ...buildBootBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildHeaterBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
    ...buildSensorBlockCells(model, style),
    ...buildUartBlockCells(model, style),
    ...buildBootBlockCells(model, style),
    ...buildHeaterBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildPowerBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock, model, style);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = [
    ...buildDd1BlockCells(model, style),
    ...buildResetLedBlockCells(model, style),
    ...buildDecouplingBlockCells(model, style),
    ...buildSensorBlockCells(model, style),
    ...buildUartBlockCells(model, style),
    ...buildBootBlockCells(model, style),
    ...buildHeaterBlockCells(model, style),
    ...buildPowerBlockCells(model, style),
  ].map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildLayoutRefinementDrawio(sourceText, lock, model, style) {
  return buildPowerBlockDrawio(sourceText, lock, model, style);
}

function main() {
  const args = parseArgs(process.argv);
  const { model, style, lock } = validateInputs(args);
  const renderedStage = args.layoutRefinement
    ? "middle_schematic_layout_refinement"
    : (args.powerBlock ? "power-block-checkpoint" : (args.heaterBlock ? "heater-block-checkpoint" : (args.bootBlock ? "boot-block-checkpoint" : (args.uartBlock ? "uart-block-checkpoint" : (args.sensorBlock ? "sensor-block-checkpoint" : (args.decouplingBlock ? "decoupling-block-checkpoint" : (args.resetLedBlock ? "reset-led-block-checkpoint" : (args.dd1Block ? "dd1-controller-block-checkpoint" : (args.writeOutput ? "copy-template-no-circuit" : "dry-run-no-circuit")))))))));
  const summary = {
    mode: renderedStage,
    renderedStage,
    sourceDrawio: args.sourceDrawio,
    outputDrawio: args.outputDrawio,
    componentCount: Array.isArray(model.components) ? model.components.length : 0,
    netCount: Array.isArray(model.nets) ? model.nets.length : 0,
    reservedRegions: Object.fromEntries(
      Object.entries(lock.regions).map(([name, region]) => [name, {
        cellCount: region.cell_count,
        bbox: region.bbox,
      }])
    ),
    styleDefaults: {
      wireStrokeWidth: style.extracted?.wire_stroke_width?.value,
      componentBodyStrokeWidth: style.extracted?.component_body_stroke_width?.value,
      pinLabelFontSize: style.extracted?.pin_label_font_size?.value,
      netLabelFontSize: style.extracted?.net_label_font_size?.value,
    },
    dd1BlockRendered: args.dd1Block,
    resetLedBlockRendered: args.resetLedBlock,
    decouplingBlockRendered: args.decouplingBlock,
    sensorBlockRendered: args.sensorBlock,
    uartBlockRendered: args.uartBlock,
    bootBlockRendered: args.bootBlock,
    heaterBlockRendered: args.heaterBlock,
    powerBlockRendered: args.powerBlock,
    layoutRefinementRendered: args.layoutRefinement,
    changedLayoutOnly: args.layoutRefinement,
    generatedComponentsCount: args.layoutRefinement ? 21 : undefined,
    finalCircuitRendered: false,
    exportedArtifacts: false,
  };
  if (args.writeOutput) {
    const sourceText = fs.readFileSync(args.sourceDrawio, "utf8");
    const generated = args.layoutRefinement
      ? buildLayoutRefinementDrawio(sourceText, lock, model, style)
      : args.powerBlock
      ? buildPowerBlockDrawio(sourceText, lock, model, style)
      : args.heaterBlock
      ? buildHeaterBlockDrawio(sourceText, lock, model, style)
      : args.bootBlock
      ? buildBootBlockDrawio(sourceText, lock, model, style)
      : args.uartBlock
      ? buildUartBlockDrawio(sourceText, lock, model, style)
      : args.sensorBlock
      ? buildSensorBlockDrawio(sourceText, lock, model, style)
      : args.decouplingBlock
      ? buildDecouplingBlockDrawio(sourceText, lock, model, style)
      : args.resetLedBlock
      ? buildResetLedBlockDrawio(sourceText, lock, model, style)
      : args.dd1Block
      ? buildDd1BlockDrawio(sourceText, lock, model, style)
      : buildNoCircuitDrawio(sourceText, lock, model, style);
    fs.writeFileSync(args.outputDrawio, generated, "utf8");
    summary.generatedCellPolicy = {
      lockedRegionCellsPreservedUnchanged: true,
      lockedAncestorContainersTagged: RESERVED_CONTAINER_ROLE,
      middleCircuitRendered: args.layoutRefinement
        ? "middle schematic layout refinement with all 21 confirmed components; no export artifacts"
        : args.powerBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor + XS4 UART/service + R6/SB2 BOOT + R4/R5/VT1/XS2/XS5 heater + A1/XS3/C3/C4 power checkpoint only"
        : args.heaterBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor + XS4 UART/service + R6/SB2 BOOT + R4/R5/VT1/XS2/XS5 heater checkpoint only"
        : args.bootBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor + XS4 UART/service + R6/SB2 BOOT checkpoint only"
        : args.uartBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor + XS4 UART/service checkpoint only"
        : args.sensorBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling + XS1/R2 sensor checkpoint only"
        : args.decouplingBlock
        ? "DD1 + RESET/EN + LED status + C1/C2 decoupling checkpoint only"
        : (args.resetLedBlock ? "DD1 + RESET/EN + LED status checkpoint only" : (args.dd1Block ? "DD1 checkpoint only" : false)),
    };
  }
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

try {
  main();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
