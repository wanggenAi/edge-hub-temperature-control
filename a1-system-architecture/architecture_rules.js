const FRAME_RULES = {
  physicalPageMm: { width: 841, height: 594 },
  marginsMm: { left: 20, top: 5, right: 5, bottom: 5 },
  outerBorder: {
    id: "repo_template_outer_border",
    strokeWidth: 3.937,
    strokeColor: "#000000"
  },
  titleBlock: {
    id: "pFFQBGnBG81xobuCz_b_-1",
    alignToFrameRight: true,
    alignToFrameBottom: true,
    thickStrokeWidth: 3.937,
    thinStrokeWidth: 1.9685,
    strokeTolerance: 0.03
  }
};

const PROJECT_A1_RULES = {
  templateFile: "../aa.drawio",
  forbiddenArea: { x: 2525, y: 2075, width: 775, height: 264 },
  noTopTitle: true,
  preserveTitleBlock: true,
  preserveOuterBorder: true,
  minCoverageX: 0.72,
  minCoverageY: 0.58
};

const ARCHITECTURE_LAYOUT_RULES = {
  mode: "layered-a1-system-architecture",
  layerCount: 4,
  minLayerGapPx: 78,
  minNodeGapPx: 46,
  groupHeaderHeightPx: 42,
  groupPaddingPx: 28,
  groupStrokeWidth: 2,
  pagePaddingPx: { left: 150, top: 110, right: 170, bottom: 330 },
  componentSize: { width: 220, height: 110 },
  smallComponentSize: { width: 218, height: 72 },
  busSize: { width: 260, height: 66 },
  groupSize: { width: 475, height: 1540 },
  rowCount: 6,
  rowGapPx: 210,
  connection: {
    minLengthPx: 72,
    maxSegmentLengthPx: 620,
    maxCommunicationSpineLengthPx: 900,
    maxVerticalSegmentLengthPx: 335,
    maxBends: 1,
    avoidCrossings: true,
    orthogonalOnly: true
  },
  maxEdges: 28,
  shapeRatios: {
    rect: 2,
    round: 2,
    topic: 2,
    db: 2,
    decision: 1.5
  },
  ratioTolerance: 0.08,
  titleZone: { xOffset: 24, yOffset: 12, width: 620, height: 46 },
  requiredLayerOrder: ["hmi", "backend", "communication", "edge"],
  mqttCenterRules: {
    brokerId: "mqtt_broker",
    requiredAdjacentEdges: [
      ["telemetry_topic", "mqtt_broker"],
      ["params_topic", "mqtt_broker"]
    ]
  },
  edgeControllerRules: {
    controllerId: "edge_control_unit",
    requiredAdjacentEdges: [
      ["sample_filter", "edge_control_unit"],
      ["edge_control_unit", "pid_controller"],
      ["mqtt_broker", "edge_control_unit"]
    ]
  },
  exactLayers: [
    "HMI & Decision Support Layer",
    "Backend & Data Hub Layer",
    "Communication Layer",
    "Edge Control Layer"
  ],
  exactComponents: [
    "React HMI",
    "Live Chart",
    "Alarm Panel",
    "Offline Learning",
    "Policy Ranking",
    "Approval & Safe Filter",
    "Param Publish",
    "FastAPI / History API",
    "Java Data Hub",
    "Schema Validator",
    "Alarm Rules",
    "TS Writer",
    "TS DB / TDengine",
    "Command API",
    "Telemetry Topic",
    "MQTT Broker",
    "Param Topic",
    "Temperature Sensor",
    "Sample Filter",
    "Edge Controller",
    "PID Controller",
    "PWM Output",
    "Heater Driver",
    "Chamber"
  ],
  alignment: {
    tolerancePx: 4,
    rowTolerancePx: 4,
    spacingTolerancePx: 8,
    centralAxis: ["data_hub", "mqtt_broker", "edge_control_unit"],
    commandAxis: ["param_publish", "command_api", "params_topic"],
    bottomControlChain: [
      "temp_sensor",
      "sample_filter",
      "edge_control_unit",
      "pid_controller",
      "pwm_output",
      "heater_driver",
      "chamber"
    ],
    communicationRow: ["telemetry_topic", "mqtt_broker", "params_topic"],
    topUpperRow: ["react_hmi", "live_chart", "alarm_panel"],
    topLowerRow: ["offline_learning", "policy_ranking", "approval_filter", "param_publish"]
  }
};

const STYLE_RULES = {
  blackAndWhite: true,
  fontFamily: "Helvetica",
  groupFill: "#ffffff",
  nodeFill: "#ffffff",
  strokeColor: "#000000",
  strokeWidth: 2,
  groupStrokeWidth: 2,
  connectorStrokeWidth: 2,
  arrowStyle: {
    endArrow: "open",
    endFill: 0,
    endSize: 12
  }
};

const TEXT_FIT_RULES = {
  defaultFontSize: 20,
  defaultPaddingPx: { left: 18, right: 18, top: 12, bottom: 12 },
  lineHeightMultiplier: 1.25,
  averageCharWidthMultiplier: 0.58,
  nodeUsableWidthRatio: {
    rect: 1,
    round: 0.96,
    dash: 1,
    topic: 0.72,
    db: 0.88
  },
  nodeFontSize: {
    rect: 20,
    round: 20,
    dash: 20,
    topic: 16,
    db: 18
  },
  maxLineChars: {
    rect: 14,
    round: 18,
    dash: 18,
    topic: 12,
    db: 15
  },
  minBorderClearancePx: 10,
  failOnEstimatedOverflow: true
};

const ARCHITECTURE_RULES = {
  allowedNodeTypes: ["device", "edge", "protocol", "service", "database", "ui", "ai", "external", "bus"],
  maxElements: 36,
  minElements: 22,
  requireEnglishLabels: true,
  requireLayerGroups: true,
  forbidFloatingNodes: true,
  forbidOverlaps: true,
  forbidNodeInTitleBlock: true,
  requireEditableDrawio: true
};

function normalizeText(text) {
  return String(text || "").replace(/\s+/g, " ").trim().toLowerCase();
}

module.exports = {
  FRAME_RULES,
  PROJECT_A1_RULES,
  ARCHITECTURE_LAYOUT_RULES,
  STYLE_RULES,
  TEXT_FIT_RULES,
  ARCHITECTURE_RULES,
  normalizeText
};
