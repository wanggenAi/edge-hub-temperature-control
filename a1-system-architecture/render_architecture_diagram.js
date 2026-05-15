#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { XMLParser, XMLBuilder } = require("fast-xml-parser");
const { FRAME_RULES, STYLE_RULES, TEXT_FIT_RULES } = require("./architecture_rules");

const WORK_DIR = __dirname;
const ROOT_DIR = path.resolve(WORK_DIR, "..");
const TEMPLATE_PATH = path.join(ROOT_DIR, "aa.drawio");
const OUT = path.join(WORK_DIR, "architecture_diagram.drawio");
const METRICS = path.join(WORK_DIR, "architecture_diagram_metrics.json");

const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: "@_", trimValues: false });
const builder = new XMLBuilder({ ignoreAttributes: false, attributeNamePrefix: "@_", format: true, suppressEmptyNode: true });

const PREFIX = "arch2_";
const FRAME_PREFIX = "repo_template_";
const forbiddenArea = { x: 2525, y: 2075, width: 775, height: 264 };

const layers = [
  {
    id: "hmi",
    title: "HMI & Decision Support Layer",
    y: 180,
    nodes: [
      ["react_hmi", "React HMI", "rect", 0, 0],
      ["live_chart", "Live Chart", "rect", 0, 0],
      ["alarm_panel", "Alarm Panel", "rect", 0, 0],
      ["offline_learning", "Offline Learning", "rect", 0, 1],
      ["policy_ranking", "Policy Ranking", "rect", 0, 1],
      ["approval_filter", "Approval & Safe Filter", "rect", 0, 1],
      ["param_publish", "Param Publish", "rect", 0, 1]
    ]
  },
  {
    id: "backend",
    title: "Backend & Data Hub Layer",
    y: 610,
    nodes: [
      ["fastapi", "FastAPI / History API", "rect", 0, 0],
      ["data_hub", "Java Data Hub", "rect", 0, 0],
      ["schema_validator", "Schema Validator", "rect", 0, 0],
      ["alarm_rules", "Alarm Rules", "rect", 0, 0],
      ["ts_writer", "TS Writer", "rect", 0, 0],
      ["tdengine_db", "TS DB / TDengine", "db", 0, 1],
      ["command_api", "Command API", "rect", 0, 1]
    ]
  },
  {
    id: "communication",
    title: "Communication Layer",
    y: 1040,
    nodes: [
      ["telemetry_topic", "Telemetry Topic", "topic", 0, 0],
      ["mqtt_broker", "MQTT Broker", "round", 0, 0],
      ["params_topic", "Param Topic", "topic", 0, 0]
    ]
  },
  {
    id: "edge",
    title: "Edge Control Layer",
    y: 1470,
    nodes: [
      ["temp_sensor", "Temperature Sensor", "rect", 0, 0],
      ["sample_filter", "Sample Filter", "rect", 0, 0],
      ["edge_control_unit", "Edge Controller", "rect", 0, 0],
      ["pid_controller", "PID Controller", "rect", 0, 0],
      ["pwm_output", "PWM Output", "rect", 0, 0],
      ["heater_driver", "Heater Driver", "rect", 0, 0],
      ["chamber", "Chamber", "rect", 0, 0]
    ]
  }
];

const edges = [
  ["temp_sensor", "sample_filter"],
  ["sample_filter", "edge_control_unit"],
  ["edge_control_unit", "pid_controller"],
  ["pid_controller", "pwm_output"],
  ["pwm_output", "heater_driver"],
  ["heater_driver", "chamber"],
  ["sample_filter", "telemetry_topic"],
  ["telemetry_topic", "mqtt_broker"],
  ["params_topic", "mqtt_broker"],
  ["mqtt_broker", "data_hub"],
  ["data_hub", "schema_validator"],
  ["schema_validator", "alarm_rules"],
  ["alarm_rules", "ts_writer"],
  ["ts_writer", "tdengine_db"],
  ["fastapi", "react_hmi"],
  ["react_hmi", "live_chart"],
  ["offline_learning", "policy_ranking"],
  ["policy_ranking", "approval_filter"],
  ["approval_filter", "param_publish"],
  ["param_publish", "command_api"],
  ["command_api", "params_topic"],
  ["mqtt_broker", "edge_control_unit"]
];

const nodePositions = {
  react_hmi: { x: 780, row: 0 },
  live_chart: { x: 1200, row: 0 },
  alarm_panel: { x: 1760, row: 0 },
  offline_learning: { x: 1200, row: 1 },
  policy_ranking: { x: 1480, row: 1 },
  approval_filter: { x: 1760, row: 1 },
  param_publish: { x: 2320, row: 1 },

  fastapi: { x: 780, row: 0 },
  data_hub: { x: 1200, row: 0 },
  schema_validator: { x: 1480, row: 0 },
  alarm_rules: { x: 1760, row: 0 },
  ts_writer: { x: 2040, row: 0 },
  tdengine_db: { x: 2040, row: 1 },
  command_api: { x: 2320, row: 1 },

  telemetry_topic: { x: 810, row: 0 },
  mqtt_broker: { x: 1200, row: 0 },
  params_topic: { x: 2320, row: 0 },

  temp_sensor: { x: 420, row: 0 },
  sample_filter: { x: 810, row: 0 },
  edge_control_unit: { x: 1200, row: 0 },
  pid_controller: { x: 1590, row: 0 },
  pwm_output: { x: 1980, row: 0 },
  heater_driver: { x: 2370, row: 0 },
  chamber: { x: 2760, row: 0 }
};

function asArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function attrNumber(obj, key, fallback = 0) {
  const value = Number(obj && obj[`@_${key}`]);
  return Number.isFinite(value) ? value : fallback;
}

function geom(x, y, width, height, extra = {}) {
  return { "@_x": +x.toFixed(3), "@_y": +y.toFixed(3), "@_width": +width.toFixed(3), "@_height": +height.toFixed(3), "@_as": "geometry", ...extra };
}

function cell(id, value, style, x, y, width, height, parent = "1") {
  return { "@_id": id, "@_value": String(value).replace(/\n/g, "<br>"), "@_style": style, "@_parent": parent, "@_vertex": "1", mxGeometry: geom(x, y, width, height) };
}

function wrapLabel(label, kind) {
  const maxChars = TEXT_FIT_RULES.maxLineChars[kind] || TEXT_FIT_RULES.maxLineChars.rect;
  const words = String(label).split(/\s+/).filter(Boolean);
  const lines = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length <= maxChars || !current) {
      current = candidate;
    } else {
      lines.push(current);
      current = word;
    }
  }
  if (current) lines.push(current);
  return lines.join("\n");
}

function visibleText(value) {
  return String(value || "").replace(/\n/g, " ");
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

function replaceStyleValue(style, key, value) {
  const parts = String(style || "").split(";").filter(Boolean);
  let found = false;
  const next = parts.map((part) => {
    if (part.startsWith(`${key}=`)) {
      found = true;
      return `${key}=${value}`;
    }
    return part;
  });
  if (!found) next.push(`${key}=${value}`);
  return next.join(";");
}

function applyFrame(root, page) {
  const frame = frameBox(page);
  const title = asArray(root.mxCell).find((item) => String(item["@_id"] || "") === FRAME_RULES.titleBlock.id);
  if (title?.mxGeometry) {
    const width = attrNumber(title.mxGeometry, "width");
    const height = attrNumber(title.mxGeometry, "height");
    title.mxGeometry["@_x"] = +(frame.x + frame.width - width).toFixed(3);
    title.mxGeometry["@_y"] = +(frame.y + frame.height - height).toFixed(3);
  }
  for (const item of asArray(root.mxCell)) {
    const id = String(item["@_id"] || "");
    const parent = String(item["@_parent"] || "");
    if (id !== FRAME_RULES.titleBlock.id && parent !== FRAME_RULES.titleBlock.id) continue;
    const style = String(item["@_style"] || "");
    const match = style.match(/strokeWidth=([0-9.]+)/);
    if (!match) continue;
    const current = Number(match[1]);
    const middle = (FRAME_RULES.titleBlock.thickStrokeWidth + FRAME_RULES.titleBlock.thinStrokeWidth) / 2;
    item["@_style"] = replaceStyleValue(style, "strokeWidth", current >= middle ? FRAME_RULES.titleBlock.thickStrokeWidth : FRAME_RULES.titleBlock.thinStrokeWidth);
  }
  root.mxCell = asArray(root.mxCell).concat([
    cell(FRAME_RULES.outerBorder.id, "", `rounded=0;whiteSpace=wrap;html=1;strokeWidth=${FRAME_RULES.outerBorder.strokeWidth};strokeColor=#000000;fillColor=none;pointerEvents=0;movable=0;resizable=0;rotatable=0;deletable=0;editable=0;connectable=0`, frame.x, frame.y, frame.width, frame.height)
  ]);
}

function nodeStyle(kind) {
  const fontSize = TEXT_FIT_RULES.nodeFontSize[kind] || TEXT_FIT_RULES.defaultFontSize;
  const pad = TEXT_FIT_RULES.defaultPaddingPx;
  const base = `html=1;whiteSpace=wrap;fontFamily=${STYLE_RULES.fontFamily};fontSize=${fontSize};fontColor=#000000;align=center;verticalAlign=middle;strokeColor=#000000;strokeWidth=2;fillColor=#ffffff;autosize=0;shadow=0;gradientColor=none;spacingLeft=${pad.left};spacingRight=${pad.right};spacingTop=${pad.top};spacingBottom=${pad.bottom};`;
  if (kind === "db") return `${base}shape=mxgraph.flowchart.database;rounded=0;spacingTop=18;spacingBottom=10`;
  if (kind === "topic") return `${base}shape=parallelogram;perimeter=parallelogramPerimeter;rounded=0;spacingLeft=28;spacingRight=28`;
  if (kind === "round") return `${base}rounded=1;arcSize=18`;
  return `${base}rounded=0`;
}

function edgeStyle(route) {
  const port = {
    left: [0, 0.5],
    right: [1, 0.5],
    top: [0.5, 0],
    bottom: [0.5, 1]
  };
  const [exitX, exitY] = port[route.sourcePort];
  const [entryX, entryY] = port[route.targetPort];
  return `html=1;edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;curved=0;endArrow=${STYLE_RULES.arrowStyle.endArrow};endFill=${STYLE_RULES.arrowStyle.endFill};endSize=${STYLE_RULES.arrowStyle.endSize};strokeColor=#000000;strokeWidth=2;exitX=${exitX};exitY=${exitY};entryX=${entryX};entryY=${entryY};exitDx=0;exitDy=0;entryDx=0;entryDy=0`;
}

function point(box, port) {
  if (port === "left") return { x: box.x, y: box.y + box.height / 2 };
  if (port === "right") return { x: box.x + box.width, y: box.y + box.height / 2 };
  if (port === "top") return { x: box.x + box.width / 2, y: box.y };
  if (port === "bottom") return { x: box.x + box.width / 2, y: box.y + box.height };
  throw new Error(`Bad port ${port}`);
}

function routeBetween(source, target) {
  const sc = { x: source.x + source.width / 2, y: source.y + source.height / 2 };
  const tc = { x: target.x + target.width / 2, y: target.y + target.height / 2 };
  let sourcePort = tc.x >= sc.x ? "right" : "left";
  let targetPort = sourcePort === "right" ? "left" : "right";
  if (Math.abs(tc.y - sc.y) > 180) {
    sourcePort = tc.y >= sc.y ? "bottom" : "top";
    targetPort = sourcePort === "bottom" ? "top" : "bottom";
  }
  const a = point(source, sourcePort);
  const b = point(target, targetPort);
  const waypoints = Math.abs(a.x - b.x) <= 0.1 || Math.abs(a.y - b.y) <= 0.1 ? [] : [{ x: b.x, y: a.y }];
  return { sourcePort, targetPort, points: [a, ...waypoints, b], waypoints };
}

function routeForEdge(from, to, source, target) {
  const verticalPairs = new Set([
    "sample_filter->telemetry_topic",
    "mqtt_broker->data_hub",
    "ts_writer->tdengine_db",
    "fastapi->react_hmi",
    "alarm_rules->alarm_panel",
    "param_publish->command_api",
    "command_api->params_topic",
    "mqtt_broker->edge_control_unit"
  ]);
  if (!verticalPairs.has(`${from}->${to}`)) return routeBetween(source, target);
  const sourcePort = target.y >= source.y ? "bottom" : "top";
  const targetPort = sourcePort === "bottom" ? "top" : "bottom";
  const a = point(source, sourcePort);
  const b = point(target, targetPort);
  const waypoints = Math.abs(a.x - b.x) <= 0.1 || Math.abs(a.y - b.y) <= 0.1 ? [] : [{ x: b.x, y: a.y }];
  return { sourcePort, targetPort, points: [a, ...waypoints, b], waypoints };
}

function assertTextFits(label, kind, width, height) {
  const styleKind = kind === "topic" ? "topic" : kind === "db" ? "db" : "rect";
  const fontSize = TEXT_FIT_RULES.nodeFontSize[styleKind] || TEXT_FIT_RULES.defaultFontSize;
  const pad = TEXT_FIT_RULES.defaultPaddingPx;
  const usableRatio = TEXT_FIT_RULES.nodeUsableWidthRatio[styleKind] || 1;
  const usableWidth = width * usableRatio - pad.left - pad.right;
  const usableHeight = height - pad.top - pad.bottom;
  const lines = String(label).split(/\n+/).filter(Boolean);
  const maxWidth = Math.max(0, ...lines.map((line) => line.length * fontSize * TEXT_FIT_RULES.averageCharWidthMultiplier));
  const textHeight = lines.length * fontSize * TEXT_FIT_RULES.lineHeightMultiplier;
  if (maxWidth > usableWidth || textHeight > usableHeight) {
    throw new Error(`Label does not fit ${kind} node: "${visibleText(label)}" (${maxWidth.toFixed(1)}/${usableWidth.toFixed(1)}, ${textHeight.toFixed(1)}/${usableHeight.toFixed(1)})`);
  }
}

function createEdge(id, from, to, route) {
  const mxGeometry = { "@_relative": "1", "@_as": "geometry" };
  if (route.waypoints.length) {
    mxGeometry.Array = { "@_as": "points", mxPoint: route.waypoints.map((p) => ({ "@_x": +p.x.toFixed(3), "@_y": +p.y.toFixed(3) })) };
  }
  return { "@_id": `${PREFIX}edge_${id}`, "@_value": "", "@_style": edgeStyle(route), "@_parent": "1", "@_edge": "1", "@_source": `${PREFIX}${from}`, "@_target": `${PREFIX}${to}`, mxGeometry };
}

function main() {
  const doc = parser.parse(fs.readFileSync(TEMPLATE_PATH, "utf8"));
  const diagram = asArray(doc.mxfile.diagram)[0];
  diagram["@_name"] = "Architecture Diagram";
  const graph = diagram.mxGraphModel;
  const page = { width: attrNumber(graph, "pageWidth", 3300), height: attrNumber(graph, "pageHeight", 2339) };
  const root = graph.root;
  root.mxCell = asArray(root.mxCell).filter((item) => {
    const id = String(item["@_id"] || "");
    return !id.startsWith(PREFIX) && !id.startsWith(FRAME_PREFIX);
  });

  const cells = [];
  const boxes = new Map();
  const layerX = 150;
  const layerW = 3030;
  const layerH = 395;
  const nodeW = 220;
  const nodeH = 110;
  for (const layer of layers) {
    cells.push(cell(`${PREFIX}layer_${layer.id}`, layer.title, "rounded=0;whiteSpace=wrap;html=1;fontFamily=Helvetica;fontSize=24;fontStyle=1;align=left;verticalAlign=top;spacingLeft=24;spacingTop=12;strokeColor=#000000;strokeWidth=2;fillColor=#ffffff;shadow=0", layerX, layer.y, layerW, layerH));
    for (const [id, label, kind, col, row = 0] of layer.nodes) {
      const position = nodePositions[id];
      if (!position) throw new Error(`Missing fixed architecture position for ${id}`);
      const x = position.x;
      const y = layer.y + 98 + (kind === "db" ? 0 : 0);
      const finalY = y + position.row * 150;
      const h = nodeH;
      const box = { x, y: finalY, width: nodeW, height: h };
      const renderedLabel = wrapLabel(label, kind);
      assertTextFits(renderedLabel, kind, box.width, box.height);
      boxes.set(id, box);
      cells.push(cell(`${PREFIX}${id}`, renderedLabel, nodeStyle(kind), box.x, box.y, box.width, box.height));
    }
  }

  edges.forEach(([from, to], index) => {
    const route = routeForEdge(from, to, boxes.get(from), boxes.get(to));
    cells.push(createEdge(String(index + 1).padStart(2, "0"), from, to, route));
  });

  applyFrame(root, page);
  root.mxCell = asArray(root.mxCell).concat(cells);
  fs.writeFileSync(OUT, builder.build(doc));
  const allBoxes = Array.from(boxes.values());
  const minX = Math.min(...allBoxes.map((b) => b.x));
  const maxX = Math.max(...allBoxes.map((b) => b.x + b.width));
  const minY = Math.min(...allBoxes.map((b) => b.y));
  const maxY = Math.max(...allBoxes.map((b) => b.y + b.height));
  fs.writeFileSync(METRICS, `${JSON.stringify({
    page,
    forbiddenArea,
    nodeCount: boxes.size,
    layerCount: layers.length,
    edgeCount: edges.length,
    coverageX: (maxX - minX) / page.width,
    coverageY: (maxY - minY) / (forbiddenArea.y - 40),
    boxes: Object.fromEntries(boxes)
  }, null, 2)}\n`);
  console.log(`Rendered ${OUT}`);
  console.log(`Architecture nodes: ${boxes.size}`);
  console.log(`Architecture edges: ${edges.length}`);
}

main();
