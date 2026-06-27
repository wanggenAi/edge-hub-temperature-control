const page = {
  width: 3300,
  height: 2339,
  forbidden_area: { x: 2554.459, y: 2161.803, width: 725.922, height: 157.508 },
  title_block: {
    width_mm: 185,
    height_mm: 40,
    source_basis: "Thesis content-page lower table style: compact bottom table; fixed to 185 mm width and 40 mm height for the A1 flowchart title block."
  }
};

const subflowRefs = {};

const symbol_definitions = {
  terminator: {
    gost_section: "3.4.2",
    meaning: "External entry/exit of the scheme: start, end, external source or destination.",
    shape: "rounded capsule",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "0 for start, 1 for end/continuation",
    expected_outputs: "1 for start, 0 or 1 for end/continuation",
    constraints: { role_based: true, min_inputs: 0, max_inputs: 1, min_outputs: 0, max_outputs: 1 }
  },
  process: {
    gost_section: "3.2.1.1",
    meaning: "Processing function or operation.",
    shape: "rectangle",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "normally 1",
    expected_outputs: "normally 1",
    constraints: { min_inputs: 1, max_inputs: null, min_outputs: 0, max_outputs: null }
  },
  predefined_process: {
    gost_section: "3.2.2.1",
    meaning: "Process defined elsewhere as a subroutine/module/function block.",
    shape: "rectangle with two vertical side lines",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "normally 1",
    expected_outputs: "normally 1",
    requires_subflow_ref: true,
    constraints: { min_inputs: 1, max_inputs: null, min_outputs: 1, max_outputs: null, requires_subflow_ref: true }
  },
  decision: {
    gost_section: "3.2.2.4",
    meaning: "Switching/decision function with one input and alternative labeled outputs.",
    shape: "rhombus",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: 1,
    expected_outputs: "2 or more, all labeled",
    constraints: { min_inputs: 1, max_inputs: 1, min_outputs: 2, max_outputs: null, all_outputs_labeled: true }
  },
  data: {
    gost_section: "3.1.1.1",
    meaning: "Input/output data with unspecified carrier.",
    shape: "parallelogram",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "0 or more depending on data source",
    expected_outputs: "0 or more depending on data destination",
    constraints: { min_inputs: 0, max_inputs: null, min_outputs: 0, max_outputs: null }
  },
  stored_data: {
    gost_section: "3.1.1.2",
    meaning: "Stored data suitable for processing.",
    shape: "stored-data/database symbol",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "0 or more",
    expected_outputs: "0 or more",
    constraints: { min_inputs: 0, max_inputs: null, min_outputs: 0, max_outputs: null }
  },
  document: {
    gost_section: "3.1.2.4",
    meaning: "Human-readable document, log, report, request or approval artifact; in this drawing it is a terminal data output, not a processing step.",
    shape: "document with wavy bottom edge",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: [],
    expected_inputs: "0 or more",
    expected_outputs: "0; terminal human-readable artifact in this drawing",
    constraints: { min_inputs: 0, max_inputs: null, min_outputs: 0, max_outputs: 0 }
  },
  manual_input: {
    gost_section: "3.1.2.5",
    meaning: "Data entered manually during processing.",
    shape: "manual input",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "0; manual data source such as keyboard/switch/button",
    expected_outputs: "1 manual data output",
    constraints: { min_inputs: 0, max_inputs: 0, min_outputs: 1, max_outputs: 1 }
  },
  manual_operation: {
    gost_section: "3.2.2.2",
    meaning: "Operation performed by a human operator.",
    shape: "manual operation",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "normally 1",
    expected_outputs: "normally 1",
    constraints: { min_inputs: 0, max_inputs: null, min_outputs: 0, max_outputs: null }
  },
  display: {
    gost_section: "3.1.2.8",
    meaning: "Human-readable display output; in this drawing it is terminal visual output and does not drive a later process.",
    shape: "display",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: [],
    expected_inputs: "normally 1",
    expected_outputs: "0; terminal visual output in this drawing",
    constraints: { min_inputs: 1, max_inputs: null, min_outputs: 0, max_outputs: 0 }
  },
  connector: {
    gost_section: "3.4.1",
    meaning: "Line continuation marker. Same-letter C connectors are a traceable continuation group: branch-end C markers symbolically continue to the C marker before End without drawing long crossing lines.",
    shape: "circle with continuation label",
    default_allowed_input_sides: ["north", "south", "west", "east"],
    default_allowed_output_sides: ["north", "south", "west", "east"],
    expected_inputs: "branch-end C: one or more incoming lines; End-before C: continuation target",
    expected_outputs: "branch-end C: zero drawn outputs; End-before C: one drawn output to End",
    constraints: { min_inputs: 0, max_inputs: null, min_outputs: 0, max_outputs: null }
  }
};

const GLOBAL_LAYOUT_SHIFT_X = -30;
const shiftX = (value) => Number((value + GLOBAL_LAYOUT_SHIFT_X).toFixed(3));
const BRANCH_CENTER_X = shiftX(1650);
const BRANCH_COUNT = 8;
const BRANCH_X_STEP = 360;
const BRANCH_BUS_Y = 295;
const BRANCH_VERTICAL_GAP = 74;
const BRANCH_FIRST_TOP_Y = BRANCH_BUS_Y + BRANCH_VERTICAL_GAP;
const BRANCH_CONNECTOR_MIN_Y = 2050;
const BRANCH_CONNECTOR_MAX_Y = 2185;
const FINAL_EXIT_X = BRANCH_CENTER_X;
const RETURN_LANE_X = shiftX(3270);
const REJECTION_BRANCH_X = shiftX(3160);
const BRANCH_XS = Array.from(
  { length: BRANCH_COUNT },
  (_, index) => BRANCH_CENTER_X + (index - (BRANCH_COUNT - 1) / 2) * BRANCH_X_STEP
);
const SYMBOL_HEIGHTS = {
  terminator: 70,
  process: 85,
  predefined_process: 85,
  data: 70,
  document: 70,
  display: 70,
  manual_input: 70,
  manual_operation: 85,
  stored_data: 90,
  decision: 100,
  connector: 52
};
const FAULT_BRANCH_VERTICAL_GAP = 52;
const FAULT_BRANCH_FIRST_TOP_Y = BRANCH_BUS_Y + FAULT_BRANCH_VERTICAL_GAP;
const BOTTOM_RETURN_BUS_Y = 2066;
const BOTTOM_RETURN_BUS_LEFT_X = BRANCH_XS[3];
const FINAL_CONNECTOR_CENTER_Y = BOTTOM_RETURN_BUS_Y + SYMBOL_HEIGHTS.connector / 2 + 24;
const FINAL_END_CENTER_Y = FINAL_CONNECTOR_CENTER_Y + SYMBOL_HEIGHTS.connector / 2 + BRANCH_VERTICAL_GAP + SYMBOL_HEIGHTS.terminator / 2;
const BOTTOM_RETURN_ARROW_LENGTH = 44;
const BOTTOM_RETURN_ARROW_OFFSET = 12;

function symbolHeight(type) {
  return SYMBOL_HEIGHTS[type] || 85;
}

function branchCenterY(entries, targetIndex, firstTopY = BRANCH_FIRST_TOP_Y, lineGap = BRANCH_VERTICAL_GAP) {
  let y = firstTopY + symbolHeight(entries[0][2]) / 2;
  for (let index = 1; index <= targetIndex; index += 1) {
    const previousType = entries[index - 1][2];
    const currentType = entries[index][2];
    y += symbolHeight(previousType) / 2 + lineGap + symbolHeight(currentType) / 2;
  }
  return Number(y.toFixed(3));
}

function branchEntries(x, entries, connectorId, firstTopY = BRANCH_FIRST_TOP_Y, lineGap = BRANCH_VERTICAL_GAP) {
  const result = [];
  let y = firstTopY + symbolHeight(entries[0][2]) / 2;
  entries.forEach(([id, text, type], index) => {
    if (index > 0) {
      const previousType = entries[index - 1][2];
      y += symbolHeight(previousType) / 2 + lineGap + symbolHeight(type) / 2;
    }
    result.push([id, text, type, x, Number(y.toFixed(3))]);
  });
  const lastType = entries[entries.length - 1][2];
  y += symbolHeight(lastType) / 2 + lineGap + symbolHeight("connector") / 2;
  result.push([connectorId, "C", "connector", x, Number(y.toFixed(3))]);
  return result;
}

const branch_sequences = {
  backend: [
    ["n_status", "Status", "data"],
    ["n_telem_msg", "Telem Msg", "data"],
    ["n_mqtt", "MQTT Broker", "process"],
    ["n_telem_topic", "Telem Topic", "data"],
    ["n_parser", "Msg Parser", "process"],
    ["n_schema", "Schema Check?", "decision"],
    ["n_data_norm", "Data Norm", "process"],
    ["n_java_hub", "Java Hub", "process"],
    ["n_ts_store", "TS Store", "process"],
    ["n_backend_services", "Backend Services", "process"],
    ["n_hmi", "HMI", "process"]
  ],
  sample: [
    ["n_temp", "Temp Input", "data"],
    ["n_sensor", "Sensor Bus Read", "process"],
    ["n_raw", "Raw Sample", "data"],
    ["n_filter", "Sample Filter", "process"],
    ["n_range", "Range Check?", "decision"],
    ["n_norm", "Normalize", "process"],
    ["n_tick", "Edge Tick", "process"],
    ["n_sample_window", "Sample Window", "process"],
    ["n_cycle_state", "Cycle State", "data"],
    ["n_control_tick", "Control Tick", "process"],
    ["n_sample_complete", "Sample Complete", "process"]
  ],
  parameter: [
    ["n_param_wait", "Param Wait?", "decision"],
    ["n_param_candidate", "Param Candidate", "data"],
    ["n_param_validate", "Param Validate", "process"],
    ["n_param_apply", "Param Apply", "process"],
    ["n_param_ack", "Param ACK", "data"],
    ["n_param_store", "Param Store", "process"],
    ["n_param_audit", "Param Audit", "process"],
    ["n_param_sync", "Param Sync", "process"],
    ["n_param_ready", "Param Ready", "data"],
    ["n_param_commit", "Param Commit", "process"],
    ["n_param_branch_complete", "Param Complete", "process"]
  ],
  control: [
    ["n_safety_gate", "Safety Gate", "process"],
    ["n_safety_check", "Safety Check?", "decision"],
    ["n_pid", "PID Control", "process"],
    ["n_integral", "Integral Update", "process"],
    ["n_duty", "Duty Limit", "process"],
    ["n_pwm", "PWM Output", "process"],
    ["n_heater", "Heater Driver", "process"],
    ["n_actuator_ack", "Actuator ACK", "data"],
    ["n_heat_state", "Heat State", "data"],
    ["n_control_log", "Control Log", "process"],
    ["n_control_complete", "Control Complete", "process"]
  ],
  fault: [
    ["n_fault_handler", "Fault Handler", "process"],
    ["n_fault_latch", "Fault Latch", "process"],
    ["n_safety_cutoff", "Safety Cutoff", "process"],
    ["n_alarm_event", "Alarm Event", "data"],
    ["n_alarm_panel", "Alarm Panel", "process"],
    ["n_alarm_api", "Alarm API", "process"],
    ["n_device_api", "Device API", "process"],
    ["n_alarm_records", "Alarm Records", "process"],
    ["n_alarm_review", "Alarm Review", "process"],
    ["n_fault_reset", "Fault Reset", "process"],
    ["n_fault_report", "Fault Report", "process"],
    ["n_fault_archive", "Fault Archive", "process"],
    ["n_fault_complete", "Fault Complete", "process"]
  ],
  feedback: [
    ["n_run_config", "Run Config", "process"],
    ["n_chamber", "Chamber", "process"],
    ["n_temp_feed", "Temp Feed", "data"],
    ["n_control_status", "Control Status", "data"],
    ["n_feedback_filter", "Feedback Filter", "process"],
    ["n_status_window", "Status Window", "process"],
    ["n_history_api", "History API", "process"],
    ["n_history_cache", "History Cache", "process"],
    ["n_feedback_sync", "Feedback Sync", "process"],
    ["n_feedback_ready", "Feedback Ready", "data"],
    ["n_feedback_complete", "Feedback Complete", "process"]
  ],
  model: [
    ["n_window", "Window Build", "process"],
    ["n_feature_extract", "Feature Extract", "process"],
    ["n_feature_store", "Feature Store", "process"],
    ["n_dataset", "Dataset Builder", "process"],
    ["n_offline", "Offline Learn", "process"],
    ["n_model_eval", "Model Eval", "process"],
    ["n_policy", "Policy Rank", "process"],
    ["n_model_package", "Model Package", "process"],
    ["n_model_check", "Model Check", "process"],
    ["n_model_ready", "Model Ready", "data"],
    ["n_model_complete", "Model Complete", "process"]
  ],
  downlink: [
    ["n_candidate_set", "Candidate Set", "data"],
    ["n_safe_filter", "Safe Filter", "process"],
    ["n_preview", "Preview Sim", "process"],
    ["n_approve", "Approve Req", "process"],
    ["n_op_input", "Op Input", "manual_operation"],
    ["n_ok", "OK?", "decision"],
    ["n_publish", "Param Publish", "process"],
    ["n_topic", "Params Topic", "data"],
    ["n_down_ack", "Down ACK", "data"],
    ["n_model_files", "Model Files", "process"],
    ["n_publish_complete", "Publish Complete", "process"]
  ],
  rejection: [
    ["n_keep", "Keep Params", "process"],
    ["n_reject_log", "Reject Log", "process"]
  ]
};

const CONTROL_SAFETY_CHECK_Y = branchCenterY(branch_sequences.control, 1);
const DOWNLINK_OK_Y = branchCenterY(branch_sequences.downlink, 5);
const REJECTION_BRANCH_FIRST_TOP_Y = DOWNLINK_OK_Y - symbolHeight(branch_sequences.rejection[0][2]) / 2;

const branch_columns = [
  { id: "b_backend", side: "left", x: BRANCH_XS[0], first_node_id: "n_status", connector_id: "n_c_telemetry", bus_edge_id: "t01" },
  { id: "b_sample", side: "left", x: BRANCH_XS[1], first_node_id: "n_temp", connector_id: "n_c_sample", bus_edge_id: "s01" },
  { id: "b_param", side: "left", x: BRANCH_XS[2], first_node_id: "n_param_wait", connector_id: "n_c_param", bus_edge_id: "p01" },
  { id: "b_control", side: "left", x: BRANCH_XS[3], first_node_id: "n_safety_gate", connector_id: "n_c_control", bus_edge_id: "c01" },
  { id: "b_fault", side: "right", x: BRANCH_XS[4], first_node_id: "n_fault_handler", connector_id: "n_c_fault", bus_edge_id: "f00", connection_gap: FAULT_BRANCH_VERTICAL_GAP },
  { id: "b_feedback", side: "right", x: BRANCH_XS[5], first_node_id: "n_run_config", connector_id: "n_c_feedback", bus_edge_id: "g01" },
  { id: "b_model", side: "right", x: BRANCH_XS[6], first_node_id: "n_window", connector_id: "n_c_model", bus_edge_id: "r01" },
  { id: "b_downlink", side: "right", x: BRANCH_XS[7], first_node_id: "n_candidate_set", connector_id: "n_c_downlink", bus_edge_id: "d01" }
];

const nodes = [
  ["n_start", "Start", "terminator", BRANCH_CENTER_X, 70],
  ["n_item_menu", "Item Menu", "decision", BRANCH_CENTER_X, 230],
  ["n_cend", "C", "connector", FINAL_EXIT_X, FINAL_CONNECTOR_CENTER_Y],
  ["n_end", "End", "terminator", FINAL_EXIT_X, FINAL_END_CENTER_Y],

  ...branchEntries(BRANCH_XS[0], branch_sequences.backend, "n_c_telemetry"),
  ["n_c_schema_invalid", "C", "connector", shiftX(170), branchCenterY(branch_sequences.backend, 5)],

  ...branchEntries(BRANCH_XS[1], branch_sequences.sample, "n_c_sample"),
  ["n_c_range_invalid", "C", "connector", shiftX(970), branchCenterY(branch_sequences.sample, 4)],

  ...branchEntries(BRANCH_XS[2], branch_sequences.parameter, "n_c_param"),
  ["n_c_param_no", "C", "connector", shiftX(1325), branchCenterY(branch_sequences.parameter, 0)],

  ...branchEntries(BRANCH_XS[3], branch_sequences.control, "n_c_control"),

  ...branchEntries(BRANCH_XS[4], branch_sequences.fault, "n_c_fault", FAULT_BRANCH_FIRST_TOP_Y, FAULT_BRANCH_VERTICAL_GAP),

  ...branchEntries(BRANCH_XS[5], branch_sequences.feedback, "n_c_feedback"),

  ...branchEntries(BRANCH_XS[6], branch_sequences.model, "n_c_model"),

  ...branchEntries(BRANCH_XS[7], branch_sequences.downlink, "n_c_downlink"),

  ...branchEntries(REJECTION_BRANCH_X, branch_sequences.rejection, "n_c_reject", REJECTION_BRANCH_FIRST_TOP_Y)
].map(([id, text, type, x, y]) => ({
  id,
  label: text,
  text,
  gost_type: type,
  type,
  x,
  y,
  subflow_ref: subflowRefs[id] || null,
  text_fit_rule: "centered, max two lines, no overflow beyond symbol interior",
  notes: ""
}));

const dashedEdgeBasis = {};

const edges = [
  ["m00", "n_start", "n_item_menu", "", "control"],
  ["m01", "n_item_menu", "n_cend", "End", "control"],
  ["m02", "n_cend", "n_end", "", "control"],

  ["t01", "n_item_menu", "n_status", "Telemetry", "telemetry"],
  ["t02", "n_status", "n_telem_msg", "", "telemetry"],
  ["t03", "n_telem_msg", "n_mqtt", "", "telemetry"],
  ["t04", "n_mqtt", "n_telem_topic", "", "telemetry"],
  ["t05", "n_telem_topic", "n_parser", "", "telemetry"],
  ["t06", "n_parser", "n_schema", "", "telemetry"],
  ["t07", "n_schema", "n_data_norm", "Yes", "backend"],
  ["t08", "n_schema", "n_c_schema_invalid", "No", "backend"],
  ["t09", "n_data_norm", "n_java_hub", "", "backend"],
  ["t10", "n_java_hub", "n_ts_store", "", "backend"],
  ["t11", "n_ts_store", "n_backend_services", "", "backend"],
  ["t12", "n_backend_services", "n_hmi", "", "backend"],
  ["t13", "n_hmi", "n_c_telemetry", "", "control"],

  ["s01", "n_item_menu", "n_temp", "Sampling", "control"],
  ["s02", "n_temp", "n_sensor", "", "control"],
  ["s03", "n_sensor", "n_raw", "", "control"],
  ["s04", "n_raw", "n_filter", "", "control"],
  ["s05", "n_filter", "n_range", "", "control"],
  ["s06", "n_range", "n_norm", "Yes", "control"],
  ["s07", "n_norm", "n_tick", "", "control"],
  ["s08", "n_tick", "n_sample_window", "", "control"],
  ["s09", "n_sample_window", "n_cycle_state", "", "control"],
  ["s10", "n_cycle_state", "n_control_tick", "", "control"],
  ["s11", "n_control_tick", "n_sample_complete", "", "control"],
  ["s12", "n_sample_complete", "n_c_sample", "", "control"],
  ["s13", "n_range", "n_c_range_invalid", "No", "alarm"],

  ["p01", "n_item_menu", "n_param_wait", "Parameter", "control"],
  ["p02", "n_param_wait", "n_param_candidate", "Yes", "control"],
  ["p03", "n_param_candidate", "n_param_validate", "", "control"],
  ["p04", "n_param_validate", "n_param_apply", "", "control"],
  ["p05", "n_param_apply", "n_param_ack", "", "control"],
  ["p06", "n_param_ack", "n_param_store", "", "control"],
  ["p07", "n_param_wait", "n_c_param_no", "No", "control"],
  ["p08", "n_param_store", "n_param_audit", "", "control"],
  ["p09", "n_param_audit", "n_param_sync", "", "control"],
  ["p10", "n_param_sync", "n_param_ready", "", "control"],
  ["p11", "n_param_ready", "n_param_commit", "", "control"],
  ["p12", "n_param_commit", "n_param_branch_complete", "", "control"],
  ["p13", "n_param_branch_complete", "n_c_param", "", "control"],

  ["c01", "n_item_menu", "n_safety_gate", "Control", "control"],
  ["c02", "n_safety_gate", "n_safety_check", "", "control"],
  ["c03", "n_safety_check", "n_pid", "Yes", "control"],
  ["c04", "n_pid", "n_integral", "", "control"],
  ["c05", "n_integral", "n_duty", "", "control"],
  ["c06", "n_duty", "n_pwm", "", "control"],
  ["c07", "n_pwm", "n_heater", "", "control"],
  ["c08", "n_heater", "n_actuator_ack", "", "control"],
  ["c09", "n_actuator_ack", "n_heat_state", "", "control"],
  ["c10", "n_heat_state", "n_control_log", "", "control"],
  ["c11", "n_control_log", "n_control_complete", "", "control"],
  ["c12", "n_control_complete", "n_c_control", "", "control"],
  ["c13", "n_safety_check", "n_fault_handler", "No", "alarm"],

  ["f00", "n_item_menu", "n_fault_handler", "Fault", "alarm"],
  ["f01", "n_fault_handler", "n_fault_latch", "", "alarm"],
  ["f02", "n_fault_latch", "n_safety_cutoff", "", "alarm"],
  ["f03", "n_safety_cutoff", "n_alarm_event", "", "alarm"],
  ["f04", "n_alarm_event", "n_alarm_panel", "", "alarm"],
  ["f05", "n_alarm_panel", "n_alarm_api", "", "alarm"],
  ["f06", "n_alarm_api", "n_device_api", "", "alarm"],
  ["f07", "n_device_api", "n_alarm_records", "", "alarm"],
  ["f08", "n_alarm_records", "n_alarm_review", "", "alarm"],
  ["f09", "n_alarm_review", "n_fault_reset", "", "alarm"],
  ["f10", "n_fault_reset", "n_fault_report", "", "alarm"],
  ["f11", "n_fault_report", "n_fault_archive", "", "alarm"],
  ["f12", "n_fault_archive", "n_fault_complete", "", "alarm"],
  ["f13", "n_fault_complete", "n_c_fault", "", "alarm"],

  ["g01", "n_item_menu", "n_run_config", "Feedback", "feedback"],
  ["g02", "n_run_config", "n_chamber", "", "feedback"],
  ["g03", "n_chamber", "n_temp_feed", "", "feedback"],
  ["g04", "n_temp_feed", "n_control_status", "", "feedback"],
  ["g05", "n_control_status", "n_feedback_filter", "", "feedback"],
  ["g06", "n_feedback_filter", "n_status_window", "", "feedback"],
  ["g07", "n_status_window", "n_history_api", "", "feedback"],
  ["g08", "n_history_api", "n_history_cache", "", "feedback"],
  ["g09", "n_history_cache", "n_feedback_sync", "", "feedback"],
  ["g10", "n_feedback_sync", "n_feedback_ready", "", "feedback"],
  ["g11", "n_feedback_ready", "n_feedback_complete", "", "feedback"],
  ["g12", "n_feedback_complete", "n_c_feedback", "", "feedback"],

  ["r01", "n_item_menu", "n_window", "Model", "learning"],
  ["r02", "n_window", "n_feature_extract", "", "learning"],
  ["r03", "n_feature_extract", "n_feature_store", "", "learning"],
  ["r04", "n_feature_store", "n_dataset", "", "learning"],
  ["r05", "n_dataset", "n_offline", "", "learning"],
  ["r06", "n_offline", "n_model_eval", "", "learning"],
  ["r07", "n_model_eval", "n_policy", "", "learning"],
  ["r08", "n_policy", "n_model_package", "", "learning"],
  ["r09", "n_model_package", "n_model_check", "", "learning"],
  ["r10", "n_model_check", "n_model_ready", "", "learning"],
  ["r11", "n_model_ready", "n_model_complete", "", "learning"],
  ["r12", "n_model_complete", "n_c_model", "", "learning"],

  ["d01", "n_item_menu", "n_candidate_set", "Approval", "approval"],
  ["d02", "n_candidate_set", "n_safe_filter", "", "approval"],
  ["d03", "n_safe_filter", "n_preview", "", "approval"],
  ["d04", "n_preview", "n_approve", "", "approval"],
  ["d05", "n_approve", "n_op_input", "", "approval"],
  ["d06", "n_op_input", "n_ok", "", "approval"],
  ["d07", "n_ok", "n_publish", "Yes", "approval"],
  ["d08", "n_publish", "n_topic", "", "downlink"],
  ["d09", "n_topic", "n_down_ack", "", "downlink"],
  ["d10", "n_down_ack", "n_model_files", "", "downlink"],
  ["d11", "n_model_files", "n_publish_complete", "", "downlink"],
  ["d12", "n_publish_complete", "n_c_downlink", "", "control"],

  ["j01", "n_ok", "n_keep", "No", "rejection"],
  ["j02", "n_keep", "n_reject_log", "", "rejection"],
  ["j03", "n_reject_log", "n_c_reject", "", "rejection"]
].map(([id, from, to, label, channel]) => {
  const flow_kind = ["telemetry", "api", "downlink", "backend", "feedback"].includes(channel)
    ? "communication"
    : ["storage", "learning", "hmi", "rejection"].includes(channel)
      ? "data"
      : "control";
  const dashedBasis = dashedEdgeBasis[id] || null;
  return {
    id,
    from,
    to,
    label,
    channel,
    flow_kind,
    line_symbol: dashedBasis ? "dashed" : flow_kind === "communication" ? "communication_channel" : "line",
    line_style: dashedBasis ? "dashed" : "solid",
    line_style_basis: dashedBasis || (flow_kind === "communication"
      ? "GOST 19.701-90 3.3.2.2 communication channel; recorded semantically as a communication channel and drawn as a regular solid channel line unless it is an explicit asynchronous/topic auxiliary relation."
      : "GOST 19.701-90 3.3.1.1 line: flow of data or control."),
    orthogonal_only: true
  };
});

const subflows = {};
const merge_groups = [];
const branch_groups = [
  {
    id: "bg_start_distribution_bus",
    style: "stem_to_horizontal_bus",
    source_node: "n_item_menu",
    source_port: "south",
    trunk_edge_id: "m01",
    trunk_target_node: "n_cend",
    trunk_target_port: "north",
    bus_y: BRANCH_BUS_Y,
    bus_left_x: BRANCH_XS[0],
    bus_right_x: RETURN_LANE_X,
    bottom_return_bus_left_x: BOTTOM_RETURN_BUS_LEFT_X,
    bottom_return_bus_y: BOTTOM_RETURN_BUS_Y,
    return_lane_x: RETURN_LANE_X,
    min_branch_spacing: 220,
    branch_edge_ids: ["t01", "s01", "p01", "c01", "f00", "g01", "r01", "d01"],
    notes: "Start enters the Item Menu diamond. Item Menu drops to a horizontal distribution bus. Listed branch edges start on the bus and then run vertically downward into their top nodes. The final C is also a down-hanging connector reached from the bus by a vertical drop, not a circle placed on the bus endpoint."
  }
];

const layout_policy = {
  style: "center_start_distribution_bus_with_vertical_branches",
  main_axis_orientation: "stem_to_horizontal_bus",
  layout_horizontal_shift_x: GLOBAL_LAYOUT_SHIFT_X,
  start_center_x: BRANCH_CENTER_X,
  distribution_bus_y: BRANCH_BUS_Y,
  distribution_bus_left_x: BRANCH_XS[0],
  distribution_bus_right_x: RETURN_LANE_X,
  bottom_return_bus_left_x: BOTTOM_RETURN_BUS_LEFT_X,
  bottom_return_bus_y: BOTTOM_RETURN_BUS_Y,
  bottom_return_arrow_length: BOTTOM_RETURN_ARROW_LENGTH,
  bottom_return_arrow_offset: BOTTOM_RETURN_ARROW_OFFSET,
  bottom_return_arrow_node_ids: ["n_control_complete", "n_fault_complete", "n_feedback_complete", "n_model_complete", "n_publish_complete"],
  bottom_return_merge_edge_ids: ["c12", "f13", "g12", "r12", "d12"],
  return_lane_x: RETURN_LANE_X,
  start_node_id: "n_start",
  menu_node_id: "n_item_menu",
  end_node_id: "n_end",
  end_start_alignment_required: true,
  end_start_alignment_tolerance: 1,
  connector_group_label: "C",
  connector_exit_id: "n_cend",
  max_connectors: 14,
  reference_edge_id: "f00",
  arrowless_edge_ids: ["m01", "m02"],
  branch_count_min: 8,
  branch_count_exact: 8,
  branch_balance_required: true,
  branch_x_spacing: BRANCH_X_STEP,
  branch_x_spacing_tolerance: 1,
  branch_center_tolerance: 1,
  branch_connector_min_y: BRANCH_CONNECTOR_MIN_Y,
  branch_connector_max_y: BRANCH_CONNECTOR_MAX_Y,
  branch_global_connection_gap: BRANCH_VERTICAL_GAP,
  branch_connection_gap_tolerance: 0.75,
  main_axis_node_ids: [],
  main_axis_edge_ids: [],
  vertical_branch_edge_ids: [
    "m00",
    "t01", "t02", "t03", "t04", "t05", "t06", "t07", "t09", "t10", "t11", "t12", "t13",
    "s01", "s02", "s03", "s04", "s05", "s06", "s07", "s08", "s09", "s10", "s11", "s12",
    "p01", "p02", "p03", "p04", "p05", "p06", "p08", "p09", "p10", "p11", "p12", "p13",
    "c01", "c02", "c03", "c04", "c05", "c06", "c07", "c08", "c09", "c10", "c11", "c12",
    "f00", "f01", "f02", "f03", "f04", "f05", "f06", "f07", "f08", "f09", "f10", "f11", "f12", "f13",
    "g01", "g02", "g03", "g04", "g05", "g06", "g07", "g08", "g09", "g10", "g11", "g12",
    "r01", "r02", "r03", "r04", "r05", "r06", "r07", "r08", "r09", "r10", "r11", "r12",
    "d01", "d02", "d03", "d04", "d05", "d06", "d07", "d08", "d09", "d10", "d11", "d12",
    "j02", "j03"
  ],
  forbidden_labels: ["Live Chart", "Op View", "Operator View", "Audit Log"],
  forbidden_gost_types: ["stored_data"],
  notes: "Start is centered and leads to the Item Menu diamond. Item Menu feeds a horizontal distribution bus. Exactly eight visual columns are centered around the menu with equal x spacing. Every vertical branch input/output segment is generated with one fixed boundary-to-boundary line length, and all branch-end C markers must land in the safe band above the title block."
};

module.exports = {
  diagram: {
    title: "EdgeHub Temperature Control System Flowchart",
    standard: "GOST 19.701-90 / ISO 5807-85",
    language: "English",
    scheme: "system operation flowchart with program-flow fragments"
  },
  page,
  symbol_definitions,
  nodes,
  edges,
  subflows,
  merge_groups,
  branch_groups,
  branch_columns,
  layout_policy,
  brstu: {
    official_flowchart_rule_found: false,
    title_block_policy: "Use BrSTU/ESKD-style A1 frame and title block; apply GOST 19.701-90 as the binding flowchart-symbol standard.",
    drawing_code: "БрГТУ.241297 - 05 90 00"
  }
};
