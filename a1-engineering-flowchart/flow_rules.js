const SHAPE_RULES = {
  terminator: { ratio: 2, family: "rect_family" },
  process: { ratio: 2, family: "rect_family" },
  predefined_process: { ratio: 2, family: "rect_family" },
  data: { ratio: 2, family: "rect_family" },
  document: { ratio: 2, family: "rect_family" },
  manual_input: { ratio: 2, family: "rect_family" },
  stored_data: { ratio: 1.5, family: "stored_data" },
  decision: { ratio: 1.5, family: "decision" },
  connector: { ratio: 1, family: "connector" }
};

const LABEL_ALIASES = {
  "Sensor Read": ["Sensor Bus Read"],
  "Normalize": ["Signal Normalize", "Data Normalize"],
  "Run Config": ["Runtime Config"],
  "Telemetry Msg": ["Telemetry Packet"],
  "Msg Parser": ["Message Parser"],
  "TS Writer": ["Time-Series Writer"],
  "TS DB": ["Time-Series DB"],
  "FastAPI": ["FastAPI Service"],
  "HMI": ["React HMI"],
  "Operator Act": ["Operator Action"],
  "History Win": ["History Window"],
  "Window Build": ["Window Builder"],
  "Feature Extract": ["Feature Extraction"],
  "Offline Learn": ["Offline Learning"],
  "Model Eval": ["Model Evaluation"],
  "Candidate Set": ["Candidate Params"],
  "Safe Filter": ["Safety Filter"],
  "Preview Sim": ["Preview Simulation"],
  "Approve Req": ["Approval Request"],
  "Operator In": ["Operator Input"],
  "Params Topic": ["MQTT Params Topic"],
  "ACK": ["Downlink ACK"],
  "Keep Params": ["Keep Current Params"],
  "Artifacts": ["Model Artifacts"],
  "Chamber": ["Thermal Chamber"],
  "Status": ["Control Status"]
};

const DISPLAY_LABEL_OVERRIDES = {
  "Runtime Config": "Run\nConfig",
  "Signal Normalize": "Norm",
  "Normalize": "Norm",
  "Edge Tick": "Edge\nTick",
  "Param Pending?": "Param\nWait?",
  "Param Validate": "Param\nValid",
  "Param Apply": "Param\nApply",
  "Param ACK": "Param\nACK",
  "Safety Check?": "Safety\nCheck?",
  "Integral Update": "Int\nUpd",
  "Fault Latch": "Fault\nLatch",
  "Safety Cutoff": "Safety\nCutoff",
  "Alarm Event": "Alarm\nEvent",
  "Alarm Panel": "Alarm\nPanel",
  "Thermal Chamber": "Chamber",
  "Temp Feedback": "Temp\nFeed",
  "Telemetry Msg": "Telem\nMsg",
  "Telemetry Topic": "Telem\nTopic",
  "Message Parser": "Msg\nParser",
  "Data Normalize": "Data\nNorm",
  "Java Data Hub": "Java\nHub",
  "TS Writer": "TS\nWriter",
  "Time-Series Writer": "TS\nWriter",
  "Alarm API": "Alarm\nAPI",
  "Backend DB": "Backend\nDB",
  "Window Builder": "Window\nBuild",
  "Feature Extraction": "Feature\nExtract",
  "Policy Ranking": "Policy\nRank",
  "Approval Request": "Appr\nReq",
  "Approve Req": "Appr\nReq",
  "Approval Request": "Approve\nReq",
  "Operator Input": "OpIn",
  "Operator In": "OpIn",
  "Operator View": "OpVw",
  "Operator Action": "Act",
  "Operator Act": "Act",
  "Approved?": "OK?",
  "Artifacts": "Model\nFiles",
  "Candidate Params": "Cand\nSet",
  "Candidate Set": "Cand\nSet",
  "End / Continue": "End /\nCont"
};

const DISPLAY_ALIASES = Object.entries(LABEL_ALIASES).reduce((acc, [canonical, aliases]) => {
  acc[canonical] = canonical;
  for (const alias of aliases) acc[alias] = canonical;
  return acc;
}, {});

function normalizeText(text) {
  const value = String(text || "").replace(/<br\s*\/?>/gi, " ").replace(/\s+/g, " ").trim();
  return DISPLAY_ALIASES[value] || value;
}

const NORMAL_BRANCH_LABELS = new Set(["Valid", "Yes", "Safe", "Approved"]);
const ABNORMAL_BRANCH_LABELS = new Set(["Invalid", "No", "Fault", "Rejected"]);

const DECISION_RULES = {
  "Range Check?": { branches: { Valid: "Normalize", Invalid: "Fault Merge" } },
  "Param Pending?": { branches: { Yes: "Param Validate", No: "R7" } },
  "Safety Check?": { branches: { Safe: "PID Control", Fault: "R8" } },
  "Schema Check?": { branches: { Valid: "R3", Invalid: "Alarm Store" } },
  "Approved?": { branches: { Approved: "Param Publish", Rejected: "Keep Params" } }
};

const CONNECTOR_RULES = {
  F1: {
    meaning: "temperature feedback return",
    nodes: ["F1", "F1"],
    requiredEdges: [["Temp Feedback", "F1"], ["F1", "Input Merge"]],
    forbidden: [["F1", "Status"]]
  },
  P1: {
    meaning: "parameter downlink",
    nodes: ["P1", "P1"],
    requiredEdges: [["ACK", "P1"], ["P1", "Config Merge"]],
    forbidden: [["P1", "Keep Params"], ["Edge Tick", "P1"]]
  },
  R1: { meaning: "row continuation", nodes: ["R1", "R1"], requiredEdges: [["Edge Tick", "R1"], ["R1", "Config Merge"]] },
  R2: { meaning: "row continuation", nodes: ["R2", "R2"], requiredEdges: [["Duty Limit", "R2"], ["R2", "PWM Output"]] },
  R3: { meaning: "row continuation", nodes: ["R3", "R3"], requiredEdges: [["Schema Check?", "R3"], ["R3", "Normalize"]] },
  R4: { meaning: "row continuation", nodes: ["R4", "R4"], requiredEdges: [["History API", "R4"], ["R4", "Alarm API"]] },
  R5: { meaning: "row continuation", nodes: ["R5", "R5"], requiredEdges: [["Window Builder", "R5"], ["R5", "Feature Extraction"]] },
  R6: { meaning: "row continuation", nodes: ["R6", "R6"], requiredEdges: [["Approval Request", "R6"], ["R6", "Operator Input"]] },
  R7: { meaning: "short parameter bypass row continuation", nodes: ["R7", "R7"], requiredEdges: [["Param Pending?", "R7"], ["R7", "Safety Merge"]] },
  R8: { meaning: "short safety fault row continuation", nodes: ["R8", "R8"], requiredEdges: [["Safety Check?", "R8"], ["R8", "Fault Merge"]] }
};

const REQUIRED_LOGIC_EDGES = [
  ["Cycle Start", "Input Merge"],
  ["Input Merge", "Temp Input"],
  ["Temp Input", "Sensor Read"],
  ["Sensor Read", "Raw Sample"],
  ["Raw Sample", "Sample Filter"],
  ["Sample Filter", "Range Check?"],
  ["Range Check?", "Normalize", "Valid"],
  ["Range Check?", "Fault Merge", "Invalid"],
  ["Fault Merge", "Fault Latch"],
  ["Normalize", "Edge Tick"],
  ["Edge Tick", "R1"],
  ["R1", "Config Merge"],
  ["Config Merge", "Run Config"],
  ["Run Config", "Param Pending?"],
  ["Param Pending?", "Param Validate", "Yes"],
  ["Param Pending?", "R7", "No"],
  ["R7", "Safety Merge"],
  ["Param Validate", "Param Apply"],
  ["Param Apply", "Param ACK"],
  ["Param ACK", "Safety Merge"],
  ["Safety Merge", "Safety Check?"],
  ["Safety Check?", "PID Control", "Safe"],
  ["Safety Check?", "R8", "Fault"],
  ["R8", "Fault Merge"],
  ["PID Control", "Integral Update"],
  ["Integral Update", "Duty Limit"],
  ["Duty Limit", "R2"],
  ["R2", "PWM Output"],
  ["PWM Output", "Heater Driver"],
  ["Heater Driver", "Chamber"],
  ["Chamber", "Temp Feedback"],
  ["Temp Feedback", "F1"],
  ["F1", "Input Merge"],
  ["Temp Feedback", "Status"],
  ["Status", "Telemetry Msg"],
  ["Telemetry Msg", "Edge Log"],
  ["Edge Log", "MQTT Broker"],
  ["MQTT Broker", "Telemetry Topic"],
  ["Telemetry Topic", "Msg Parser"],
  ["Msg Parser", "Schema Check?"],
  ["Schema Check?", "R3", "Valid"],
  ["R3", "Normalize"],
  ["Schema Check?", "Alarm Store", "Invalid"],
  ["Java Data Hub", "Alarm Rules"],
  ["Alarm Rules", "TS Writer"],
  ["TS Writer", "TS DB"],
  ["TS DB", "Backend DB"],
  ["Backend DB", "FastAPI"],
  ["FastAPI", "History API"],
  ["History API", "R4"],
  ["R4", "Alarm API"],
  ["Alarm API", "Device API"],
  ["Device API", "HMI"],
  ["HMI", "Live Chart"],
  ["Live Chart", "Operator View"],
  ["Operator View", "Operator Act"],
  ["Operator Act", "Audit Log"],
  ["Audit Log", "History Win"],
  ["History Win", "Window Builder"],
  ["Window Builder", "R5"],
  ["R5", "Feature Extraction"],
  ["Feature Extraction", "Feature Store"],
  ["Feature Store", "Dataset Builder"],
  ["Dataset Builder", "Offline Learning"],
  ["Offline Learning", "Model Evaluation"],
  ["Model Evaluation", "Policy Ranking"],
  ["Policy Ranking", "Candidate Params"],
  ["Candidate Params", "Safety Filter"],
  ["Safety Filter", "Preview Simulation"],
  ["Preview Simulation", "Approval Request"],
  ["Approval Request", "R6"],
  ["R6", "Operator Input"],
  ["Operator Input", "Approved?"],
  ["Approved?", "Param Publish", "Approved"],
  ["Param Publish", "Params Topic"],
  ["Params Topic", "ACK"],
  ["ACK", "P1"],
  ["P1", "Config Merge"],
  ["Approved?", "Keep Params", "Rejected"],
  ["Keep Params", "Rejected Log"],
  ["Rejected Log", "Artifacts"],
  ["Artifacts", "End / Continue"]
];

const LABEL_RULES = {
  horizontal: { position: "above-center", minGap: 6, maxGap: 14 },
  verticalDown: { position: "right-middle", minGap: 6, maxGap: 14 },
  verticalUp: { position: "right-middle", minGap: 6, maxGap: 14 },
  horizontalLeft: { position: "above-center", minGap: 6, maxGap: 14 }
};

const LABEL_PLACEMENT_RULES = LABEL_RULES;

const ARROW_RULES = {
  noArrowDirections: ["left-to-right", "top-to-bottom"],
  arrowDirections: ["right-to-left", "bottom-to-top"],
  arrowStyle: { endArrow: "open", endFill: 0, endSize: 12 },
  forbiddenArrowStyles: ["block", "classic", "blockThin", "filled", "diamond", "oval", "circle"]
};

const CONNECTOR_LOCALITY_RULES = {
  maxConnectorPairs: 10,
  maxConnectorNodes: 20,
  maxBusinessNodeDistanceU: 1.70,
  minConnectorCenterDistanceU: 1.0,
  minDifferentConnectorCenterDistanceU: 0.75,
  minConnectorPairVisualSeparationU: 1.35,
  forbidConnectorCrowding: true,
  localEdgeClarity: {
    minTotalLengthU: 0.58,
    maxTotalLengthU: 0.96,
    maxSpanU: 0.96,
    horizontalTargetLengthPx: 112,
    verticalTargetLengthPx: 88,
    targetLengthPx: 112,
    lengthToleranceU: 0.10,
    verticalLengthToleranceU: 0.08,
    maxBends: 1
  },
  requiredVisibleLocalEdges: [
    ["Temp Feedback", "F1"],
    ["F1", "Input Merge"],
    ["ACK", "P1"],
    ["P1", "Config Merge"],
    ["Edge Tick", "R1"],
    ["R1", "Config Merge"],
    ["Duty Limit", "R2"],
    ["R2", "PWM Output"],
    ["Schema Check?", "R3"],
    ["R3", "Normalize"],
    ["History API", "R4"],
    ["R4", "Alarm API"],
    ["Window Builder", "R5"],
    ["R5", "Feature Extraction"],
    ["Approval Request", "R6"],
    ["R6", "Operator Input"],
    ["Param Pending?", "R7"],
    ["R7", "Safety Merge"],
    ["Safety Check?", "R8"],
    ["R8", "Fault Merge"]
  ],
  semanticAnchors: {
    F1: [
      { role: "source", near: "Temp Feedback", side: "below", gapU: 0.86, visibleEdge: ["Temp Feedback", "F1"] },
      { role: "target", near: "Input Merge", side: "below", gapU: 0.86, visibleEdge: ["F1", "Input Merge"] }
    ],
    P1: [
      { role: "source", near: "ACK", side: "right", gapU: 0.86, visibleEdge: ["ACK", "P1"] },
      { role: "target", near: "Config Merge", side: "below", gapU: 0.86, visibleEdge: ["P1", "Config Merge"] }
    ],
    R1: [
      { role: "source", near: "Edge Tick", side: "right", gapU: 0.86, visibleEdge: ["Edge Tick", "R1"] },
      { role: "target", near: "Config Merge", side: "left", gapU: 0.86, visibleEdge: ["R1", "Config Merge"] }
    ],
    R2: [
      { role: "source", near: "Duty Limit", side: "right", gapU: 0.86, visibleEdge: ["Duty Limit", "R2"] },
      { role: "target", near: "PWM Output", side: "left", gapU: 0.86, visibleEdge: ["R2", "PWM Output"] }
    ],
    R3: [
      { role: "source", near: "Schema Check?", side: "right", gapU: 0.86, visibleEdge: ["Schema Check?", "R3"] },
      { role: "target", near: "Data Normalize", side: "left", gapU: 0.86, visibleEdge: ["R3", "Data Normalize"] }
    ],
    R4: [
      { role: "source", near: "History API", side: "right", gapU: 0.86, visibleEdge: ["History API", "R4"] },
      { role: "target", near: "Alarm API", side: "left", gapU: 0.86, visibleEdge: ["R4", "Alarm API"] }
    ],
    R5: [
      { role: "source", near: "Window Builder", side: "right", gapU: 0.86, visibleEdge: ["Window Builder", "R5"] },
      { role: "target", near: "Feature Extraction", side: "left", gapU: 0.86, visibleEdge: ["R5", "Feature Extraction"] }
    ],
    R6: [
      { role: "source", near: "Approval Request", side: "right", gapU: 0.86, visibleEdge: ["Approval Request", "R6"] },
      { role: "target", near: "Operator Input", side: "left", gapU: 0.86, visibleEdge: ["R6", "Operator Input"] }
    ],
    R7: [
      { role: "source", near: "Param Pending?", side: "below", gapU: 0.86, visibleEdge: ["Param Pending?", "R7"] },
      { role: "target", near: "Safety Merge", side: "below", gapU: 0.86, visibleEdge: ["R7", "Safety Merge"] }
    ],
    R8: [
      { role: "source", near: "Safety Check?", side: "below", gapU: 0.86, visibleEdge: ["Safety Check?", "R8"] },
      { role: "target", near: "Fault Merge", side: "left", gapU: 0.86, visibleEdge: ["R8", "Fault Merge"] }
    ]
  }
};

const CONTROL_BLOCK_RULES = {
  allowedMultiInputNodes: ["Input Merge", "Config Merge", "Safety Merge", "Fault Merge"],
  oneInputPerBusinessNode: true,
  safetyMerge: {
    node: "Safety Merge",
    requiredIncoming: [["R7", "Safety Merge"], ["Param ACK", "Safety Merge"]],
    requiredOutgoing: [["Safety Merge", "Safety Check?"]],
    forbiddenDirectEdges: [["Param Pending?", "Safety Check?", "No"], ["Param ACK", "Safety Check?"]],
    safetyCheckPrimaryIncoming: ["Safety Merge"]
  }
};

const PRIMARY_FLOW_DIRECTION_RULES = {
  avoidSerpentineMainFlow: true,
  rowsMustReadLeftToRight: true,
  allowedShortReverseChannels: ["feedback", "return", "loop", "parameter", "downlink", "row_continuation"],
  allowedReverseChannels: ["feedback", "return", "loop", "parameter", "downlink", "row_continuation"],
  maxReverseDistanceU: 1.8,
  enforcedLeftToRightChains: [
    ["PID Control", "Integral Update", "Duty Limit", "PWM Output", "Heater Driver", "Chamber", "Temp Feedback"],
    ["Java Data Hub", "Alarm Rules", "TS Writer", "TS DB", "Backend DB", "FastAPI"],
    ["FastAPI", "History API", "Alarm API", "Device API", "HMI", "Live Chart", "Operator View"],
    ["History Win", "Window Builder", "Feature Extraction", "Feature Store", "Dataset Builder", "Offline Learning", "Model Evaluation", "Policy Ranking", "Candidate Params"],
    ["Candidate Params", "Safety Filter", "Preview Simulation", "Approval Request", "Operator Input", "Approved?", "Param Publish", "Params Topic", "ACK", "P1"]
  ]
};

const LONG_LINE_RULES = {
  maxSegmentLengthU: 2.95,
  maxBranchSegmentLengthU: 3.1,
  maxReturnSegmentLengthU: 1.8,
  maxBends: 1,
  maxDecisionBends: 1,
  maxConnectorBends: 1,
  maxReturnBends: 1,
  maxDecisionAbnormalBends: 1,
  maxDecisionSegmentU: 2.2,
  maxReturnSegmentU: 1.8,
  maxControlMergeSegmentU: 4.8,
  maxStandardAdjacentSegmentU: 2.95,
  maxEdgeColumnsSpanned: 2.2,
  maxReturnColumnsSpanned: 1.4,
  maxEdgeRowGapsSpanned: 1.05,
  maxDecisionAbnormalRowGapsSpanned: 1.05,
  minArrowStemU: 0.5,
  minNodeClearanceU: 0.12,
  minParallelSegmentGapU: 0.18,
  globalStandardSegmentLengthPx: 112,
  globalStandardVerticalSegmentLengthPx: 88,
  sameRowDirectLengthToleranceU: 0.08,
  verticalSegmentLengthToleranceU: 0.08,
  standardSegmentLengthToleranceU: 0.10,
  forbidSameRowDoglegs: true
};

const VISUAL_DENSITY_RULES = {
  minNodeClearanceU: LONG_LINE_RULES.minNodeClearanceU,
  minParallelSegmentGapU: LONG_LINE_RULES.minParallelSegmentGapU,
  minArrowStemU: LONG_LINE_RULES.minArrowStemU
};

const SYNTHETIC_EDGE_RULES = {
  forbiddenVisiblePrefixes: ["auto_row_", "auto_grid_"],
  metricsBucket: "omittedSyntheticEdges"
};

const ROUTING_ENVELOPE_RULES = { marginU: 0.9 };

const ROW_WRAP_RULES = {
  mode: "fixed-gap-centered",
  minColumnGap: 112,
  maxColumnGap: 112,
  targetColumnGap: 112,
  wrapTriggerSlackPx: 170,
  maxMainRowRightSlackPx: 1400,
  minNodesForRightSlackCheck: 7,
  finalRowClusterToleranceU: 0.28,
  maxPhysicalRows: 9,
  localBranchNodeIds: ["n93", "n15", "n16", "n17", "n39", "n47", "n69", "n70", "n71", "n80"]
};

const PROGRAM_SCHEME_LAYOUT_RULES = {
  mode: "program-scheme-left-to-right-lanes",
  nodeHeight: 72,
  unit: 130,
  minColumnGap: 112,
  maxColumnGap: 112,
  targetColumnGap: 112,
  minLaneGap: 285,
  maxLaneGap: 305,
  laneGapTolerance: 12,
  laneCenterTolerance: 16,
  upperRightLaneGapTolerance: 16,
  connectorLaneTolerance: 86,
  maxNonConnectorLaneSpan: 1,
  maxConnectorLaneSpan: 1,
  maxNodesPerTightArea: 4,
  tightAreaRadiusU: 1.0,
  minPageCoverageX: 0.76,
  minPageCoverageY: 0.68,
  requiredStraightEdges: [
    ["Param ACK", "Safety Merge"],
    ["Safety Merge", "Safety Check?"]
  ],
  rows: [
    { name: "sampling", nodes: ["n01", "n91", "n02", "n03", "n04", "n05", "n06", "n07", "n08", "n81"] },
    { name: "configuration and control", nodes: ["n82", "n92", "n09", "n10", "n11", "n12", "n13", "n99", "n14", "n18", "n19", "n20", "n83"] },
    { name: "actuator and telemetry", nodes: ["n84", "n21", "n22", "n23", "n24", "n25", "n26", "n27", "n30", "n31", "n32", "n33", "n85"] },
    { name: "backend", nodes: ["n86", "n34", "n35", "n36", "n37", "n38", "n40", "n41", "n42", "n87"] },
    { name: "hmi history", nodes: ["n88", "n43", "n44", "n45", "n46", "n48", "n50", "n51", "n52", "n53", "n89"] },
    { name: "learning approval", nodes: ["n90", "n54", "n55", "n56", "n57", "n58", "n59", "n60", "n61", "n62", "n63", "n94"] },
    { name: "downlink and rejection", nodes: ["n95", "n64", "n65", "n66", "n67", "n68", "n74"] }
  ],
  branches: [
    { anchor: "n06", nodes: ["n93", "n15", "n16", "n17", "n47"], yOffsetU: 0.75, gapU: 0.38, alignFirstUnderAnchor: true },
    { anchor: "n33", nodes: ["n39"], yOffsetU: 0.75 },
    { anchor: "n65", nodes: ["n69", "n70", "n71", "n80"], yOffsetU: 1.04, gapU: 0.38, alignFirstUnderAnchor: true }
  ],
  floating: ["n72", "n73", "n75", "n96", "n97", "n98", "n100"]
};

const VISUAL_BALANCE_RULES = {
  minPageCoverageX: PROGRAM_SCHEME_LAYOUT_RULES.minPageCoverageX,
  minPageCoverageY: PROGRAM_SCHEME_LAYOUT_RULES.minPageCoverageY,
  maxConnectorNodes: CONNECTOR_LOCALITY_RULES.maxConnectorNodes,
  upperRightFocusArea: { x: 2050, y: 70, width: 1050, height: 740 },
  minNodeCount: 6,
  minDistinctRowBands: 2,
  minDistinctColumnBands: 3,
  upperRightMinLaneGap: 250,
  upperRightMaxLaneGap: 350,
  upperRightLaneGapTolerance: 42
};

const ISO_GOST_SYMBOL_RULES = {};
const ISO_GOST_DECISION_RULES = { projectBranches: DECISION_RULES };
const ISO_GOST_CONNECTOR_RULES = {};
const ISO_GOST_LINE_RULES = {};
const ISO_GOST_LABEL_RULES = {};
const PROJECT_A1_RULES = { forbiddenArea: { x: 2525, y: 2075, width: 775, height: 264 } };

const FRAME_RULES = {
  sourceReference: "Poyasnitelnaya_zapiska Томашов (1).pdf / GOST-style drawing frame",
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

function canonicalEdgeKey(from, to, label = "") {
  return `${normalizeText(from)}->${normalizeText(to)}::${String(label || "").trim()}`;
}

function buildNodeLookup(model) {
  const byId = new Map();
  const byText = new Map();
  for (const node of model.nodes || []) {
    byId.set(node.id, node);
    const key = normalizeText(node.text);
    const list = byText.get(key) || [];
    list.push(node);
    byText.set(key, list);
  }
  return { byId, byText };
}

function edgeMatches(edge, fromText, toText, label, nodeById) {
  const from = nodeById.get(edge.from);
  const to = nodeById.get(edge.to);
  if (!from || !to) return false;
  if (normalizeText(from.text) !== normalizeText(fromText)) return false;
  if (normalizeText(to.text) !== normalizeText(toText)) return false;
  if (label && String(edge.label || "").trim() !== label) return false;
  return true;
}

function findEdges(model, fromText, toText, label = "") {
  const nodeById = new Map((model.nodes || []).map((node) => [node.id, node]));
  return (model.edges || []).filter((edge) => edgeMatches(edge, fromText, toText, label, nodeById));
}

module.exports = {
  SHAPE_RULES,
  LABEL_ALIASES,
  DISPLAY_LABEL_OVERRIDES,
  DISPLAY_ALIASES,
  ISO_GOST_SYMBOL_RULES,
  ISO_GOST_DECISION_RULES,
  ISO_GOST_CONNECTOR_RULES,
  ISO_GOST_LINE_RULES,
  ISO_GOST_LABEL_RULES,
  CONNECTOR_RULES,
  DECISION_RULES,
  REQUIRED_LOGIC_EDGES,
  NORMAL_BRANCH_LABELS,
  ABNORMAL_BRANCH_LABELS,
  LABEL_RULES,
  LABEL_PLACEMENT_RULES,
  PROJECT_A1_RULES,
  FRAME_RULES,
  ARROW_RULES,
  CONNECTOR_LOCALITY_RULES,
  CONTROL_BLOCK_RULES,
  PRIMARY_FLOW_DIRECTION_RULES,
  LONG_LINE_RULES,
  VISUAL_DENSITY_RULES,
  VISUAL_BALANCE_RULES,
  SYNTHETIC_EDGE_RULES,
  ROUTING_ENVELOPE_RULES,
  ROW_WRAP_RULES,
  PROGRAM_SCHEME_LAYOUT_RULES,
  normalizeText,
  canonicalEdgeKey,
  buildNodeLookup,
  findEdges
};
