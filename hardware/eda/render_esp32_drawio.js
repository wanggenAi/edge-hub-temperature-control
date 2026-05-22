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

function buildNoCircuitDrawio(sourceText, lock) {
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

  const beforeRoot = sourceText.slice(0, rootStart + "<root>".length);
  const afterRoot = sourceText.slice(rootEnd);
  return `${beforeRoot}\n${keptCells.map((cell) => `        ${cell}`).join("\n")}\n      ${afterRoot}`;
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
  const body = { x: 940, y: 640, width: 420, height: 760 };
  const pinLength = 60;
  const wireLength = 140;
  const textHeight = 24;
  const labelOffset = 2;
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
      attrs: generatedAttrs(component),
      style: `rounded=0;whiteSpace=wrap;html=1;strokeColor=#000000;fillColor=none;strokeWidth=${bodyStroke};`,
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
      x: body.x + 40,
      y: body.y + 24,
      width: body.width - 80,
      height: 44,
      role: "component_value",
      attrs: generatedAttrs(component),
      fontSizeValue: valueFont,
    }),
  ];

  for (const pin of pins) {
    const isLeft = pin.side === "left";
    const bodyX = isLeft ? body.x : body.x + body.width;
    const pinOuterX = isLeft ? body.x - pinLength : body.x + body.width + pinLength;
    const wireOuterX = isLeft ? pinOuterX - wireLength : pinOuterX + wireLength;
    const y = Number(pin.endpoint.y);
    const pinCenterX = (bodyX + pinOuterX) / 2;
    const labelWidth = Math.max(70, String(pin.name).length * 18);
    const netWidth = Math.max(72, String(pin.net).length * 18);
    const labelX = pinCenterX - labelWidth / 2;
    const netLabelX = isLeft ? wireOuterX - netWidth / 2 : wireOuterX - netWidth / 2;
    const lineStyle = `endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${wireStroke};`;
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
        x: labelX,
        y: y - textHeight - labelOffset,
        width: labelWidth,
        height: textHeight,
        role: "pin_label",
        attrs,
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
  const cells = [
    vertexCell({
      id: `component.${component.ref}.body`,
      parent,
      x: box.x,
      y: box.y,
      width: box.width,
      height: box.height,
      role: "component_body",
      attrs: generatedAttrs(component),
      style: `rounded=0;whiteSpace=wrap;html=1;strokeColor=#000000;fillColor=none;strokeWidth=${bodyStroke};`,
    }),
    textCell({
      id: `component.${component.ref}.ref`,
      parent,
      value: component.ref,
      x: box.x + box.width / 2 - 45,
      y: box.y - 46,
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
      x: box.x + 10,
      y: box.y + box.height + 14,
      width: box.width - 20,
      height: 30,
      role: "component_value",
      attrs: generatedAttrs(component),
      fontSizeValue: valueFont,
    }),
  ];

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
    const labelWidth = spec.labelWidth || Math.max(72, String(label).length * 18);
    const netWidth = Math.max(72, String(pin.net).length * 18);
    const labelX = pinCenterX - labelWidth / 2;
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
        y: y - textHeight - 2,
        width: labelWidth,
        height: textHeight,
        role: "pin_label",
        attrs,
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
    R1: "10 kOhm",
    R2: "4.7 kOhm",
    R3: "330 Ohm",
    SB1: "RESET button",
    HL1: "Red LED",
    XS1: "XH-3PA",
    XS4: "UART service",
  };
  return overrides[component.ref] || component.value || component.type || component.ref;
}

function buildUartBlockCells(model, style) {
  const xs4 = requireComponent(model, "XS4");
  const localStubOptions = { wireLength: 45, pinLength: 60 };
  return [
    ...buildComponentBoxCells(xs4, { x: 1640, y: 560, width: 210, height: 170 }, style, [
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
    ...buildComponentBoxCells(c1, { x: 300, y: 300, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 340, label: "+3V3" },
      { number: "2", side: "right", y: 340, label: "GND" },
    ], localStubOptions),
    ...buildComponentBoxCells(c2, { x: 300, y: 420, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 460, label: "+3V3" },
      { number: "2", side: "right", y: 460, label: "GND" },
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
    ...buildComponentBoxCells(r1, { x: 360, y: 720, width: 210, height: 90 }, style, [
      { number: "1", side: "left", y: 760, label: "+3V3" },
      { number: "2", side: "right", y: 760, label: "EN" },
    ], localStubOptions),
    ...buildComponentBoxCells(sb1, { x: 360, y: 835, width: 210, height: 90 }, style, [
      { number: "2", side: "right", y: 880, label: "EN" },
      { number: "4", side: "left", y: 880, label: "GND" },
    ], localStubOptions),
    ...buildComponentBoxCells(r3, { x: 250, y: 1330, width: 210, height: 90 }, style, [
      { number: "1", side: "right", y: 1370, label: "LED_A", labelWidth: 72, renderWire: false, renderNetLabel: false },
      { number: "2", side: "right", y: 1370, label: "+3V3" },
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
  const noCircuit = buildNoCircuitDrawio(sourceText, lock);
  const rootEnd = noCircuit.indexOf("</root>");
  if (rootEnd < 0) {
    throw new Error("Invalid generated draw.io XML: missing </root> element.");
  }
  const cells = buildDd1BlockCells(model, style).map((cell) => `        ${cell}`).join("\n");
  return `${noCircuit.slice(0, rootEnd)}${cells}\n      ${noCircuit.slice(rootEnd)}`;
}

function buildResetLedBlockDrawio(sourceText, lock, model, style) {
  const noCircuit = buildNoCircuitDrawio(sourceText, lock);
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
  const noCircuit = buildNoCircuitDrawio(sourceText, lock);
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
  const noCircuit = buildNoCircuitDrawio(sourceText, lock);
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
  const noCircuit = buildNoCircuitDrawio(sourceText, lock);
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

function main() {
  const args = parseArgs(process.argv);
  const { model, style, lock } = validateInputs(args);
  const summary = {
    mode: args.uartBlock ? "uart-block-checkpoint" : (args.sensorBlock ? "sensor-block-checkpoint" : (args.decouplingBlock ? "decoupling-block-checkpoint" : (args.resetLedBlock ? "reset-led-block-checkpoint" : (args.dd1Block ? "dd1-controller-block-checkpoint" : (args.writeOutput ? "copy-template-no-circuit" : "dry-run-no-circuit"))))),
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
    finalCircuitRendered: false,
  };
  if (args.writeOutput) {
    const sourceText = fs.readFileSync(args.sourceDrawio, "utf8");
    const generated = args.uartBlock
      ? buildUartBlockDrawio(sourceText, lock, model, style)
      : args.sensorBlock
      ? buildSensorBlockDrawio(sourceText, lock, model, style)
      : args.decouplingBlock
      ? buildDecouplingBlockDrawio(sourceText, lock, model, style)
      : args.resetLedBlock
      ? buildResetLedBlockDrawio(sourceText, lock, model, style)
      : args.dd1Block
      ? buildDd1BlockDrawio(sourceText, lock, model, style)
      : buildNoCircuitDrawio(sourceText, lock);
    fs.writeFileSync(args.outputDrawio, generated, "utf8");
    summary.generatedCellPolicy = {
      lockedRegionCellsPreservedUnchanged: true,
      lockedAncestorContainersTagged: RESERVED_CONTAINER_ROLE,
      middleCircuitRendered: args.uartBlock
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
