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
    writeOutput: false,
    ...DEFAULTS,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--dry-run") args.dryRun = true;
    else if (arg === "--no-circuit") args.noCircuit = true;
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

function main() {
  const args = parseArgs(process.argv);
  const { model, style, lock } = validateInputs(args);
  const summary = {
    mode: args.writeOutput ? "copy-template-no-circuit" : "dry-run-no-circuit",
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
    finalCircuitRendered: false,
  };
  if (args.writeOutput) {
    const sourceText = fs.readFileSync(args.sourceDrawio, "utf8");
    const generated = buildNoCircuitDrawio(sourceText, lock);
    fs.writeFileSync(args.outputDrawio, generated, "utf8");
    summary.generatedCellPolicy = {
      lockedRegionCellsPreservedUnchanged: true,
      lockedAncestorContainersTagged: RESERVED_CONTAINER_ROLE,
      middleCircuitRendered: false,
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
