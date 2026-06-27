# Full Semantic Audit

- Result: PASS
- Nodes: 108
- Edges: 108
- Standard: GOST 19.701-90 / ISO 5807-85

## Node Audit
| id | label | GOST type | section | inputs | outputs | text safe |
|---|---|---|---|---:|---:|---|
| n_start | Start | terminator | 3.4.2 | 0 | 1 | PASS |
| n_item_menu | Item / Menu | decision | 3.2.2.4 | 1 | 9 | PASS |
| n_cend | C | connector | 3.4.1 | 1 | 1 | PASS |
| n_end | End | terminator | 3.4.2 | 1 | 0 | PASS |
| n_status | Status | data | 3.1.1.1 | 1 | 1 | PASS |
| n_telem_msg | Telem / Msg | data | 3.1.1.1 | 1 | 1 | PASS |
| n_mqtt | MQTT / Broker | process | 3.2.1.1 | 1 | 1 | PASS |
| n_telem_topic | Telem / Topic | data | 3.1.1.1 | 1 | 1 | PASS |
| n_parser | Msg Parser | process | 3.2.1.1 | 1 | 1 | PASS |
| n_schema | Schema / Check? | decision | 3.2.2.4 | 1 | 2 | PASS |
| n_data_norm | Data / Norm | process | 3.2.1.1 | 1 | 1 | PASS |
| n_java_hub | Java / Hub | process | 3.2.1.1 | 1 | 1 | PASS |
| n_ts_store | TS Store | process | 3.2.1.1 | 1 | 1 | PASS |
| n_backend_services | Backend / Services | process | 3.2.1.1 | 1 | 1 | PASS |
| n_hmi | HMI | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_telemetry | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_c_schema_invalid | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_temp | Temp Input | data | 3.1.1.1 | 1 | 1 | PASS |
| n_sensor | Sensor / Bus Read | process | 3.2.1.1 | 1 | 1 | PASS |
| n_raw | Raw Sample | data | 3.1.1.1 | 1 | 1 | PASS |
| n_filter | Sample / Filter | process | 3.2.1.1 | 1 | 1 | PASS |
| n_range | Range / Check? | decision | 3.2.2.4 | 1 | 2 | PASS |
| n_norm | Normalize | process | 3.2.1.1 | 1 | 1 | PASS |
| n_tick | Edge Tick | process | 3.2.1.1 | 1 | 1 | PASS |
| n_sample_window | Sample / Window | process | 3.2.1.1 | 1 | 1 | PASS |
| n_cycle_state | Cycle / State | data | 3.1.1.1 | 1 | 1 | PASS |
| n_control_tick | Control / Tick | process | 3.2.1.1 | 1 | 1 | PASS |
| n_sample_complete | Sample / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_sample | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_c_range_invalid | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_param_wait | Param / Wait? | decision | 3.2.2.4 | 1 | 2 | PASS |
| n_param_candidate | Param / Candidate | data | 3.1.1.1 | 1 | 1 | PASS |
| n_param_validate | Param / Validate | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_apply | Param / Apply | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_ack | Param ACK | data | 3.1.1.1 | 1 | 1 | PASS |
| n_param_store | Param / Store | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_audit | Param / Audit | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_sync | Param / Sync | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_ready | Param / Ready | data | 3.1.1.1 | 1 | 1 | PASS |
| n_param_commit | Param / Commit | process | 3.2.1.1 | 1 | 1 | PASS |
| n_param_branch_complete | Param / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_param | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_c_param_no | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_safety_gate | Safety / Gate | process | 3.2.1.1 | 1 | 1 | PASS |
| n_safety_check | Safety / Check? | decision | 3.2.2.4 | 1 | 2 | PASS |
| n_pid | PID / Control | process | 3.2.1.1 | 1 | 1 | PASS |
| n_integral | Integral / Update | process | 3.2.1.1 | 1 | 1 | PASS |
| n_duty | Duty Limit | process | 3.2.1.1 | 1 | 1 | PASS |
| n_pwm | PWM Output | process | 3.2.1.1 | 1 | 1 | PASS |
| n_heater | Heater / Driver | process | 3.2.1.1 | 1 | 1 | PASS |
| n_actuator_ack | Actuator / ACK | data | 3.1.1.1 | 1 | 1 | PASS |
| n_heat_state | Heat / State | data | 3.1.1.1 | 1 | 1 | PASS |
| n_control_log | Control / Log | process | 3.2.1.1 | 1 | 1 | PASS |
| n_control_complete | Control / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_control | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_fault_handler | Fault / Handler | process | 3.2.1.1 | 2 | 1 | PASS |
| n_fault_latch | Fault / Latch | process | 3.2.1.1 | 1 | 1 | PASS |
| n_safety_cutoff | Safety / Cutoff | process | 3.2.1.1 | 1 | 1 | PASS |
| n_alarm_event | Alarm / Event | data | 3.1.1.1 | 1 | 1 | PASS |
| n_alarm_panel | Alarm / Panel | process | 3.2.1.1 | 1 | 1 | PASS |
| n_alarm_api | Alarm API | process | 3.2.1.1 | 1 | 1 | PASS |
| n_device_api | Device API | process | 3.2.1.1 | 1 | 1 | PASS |
| n_alarm_records | Alarm / Records | process | 3.2.1.1 | 1 | 1 | PASS |
| n_alarm_review | Alarm / Review | process | 3.2.1.1 | 1 | 1 | PASS |
| n_fault_reset | Fault / Reset | process | 3.2.1.1 | 1 | 1 | PASS |
| n_fault_report | Fault / Report | process | 3.2.1.1 | 1 | 1 | PASS |
| n_fault_archive | Fault / Archive | process | 3.2.1.1 | 1 | 1 | PASS |
| n_fault_complete | Fault Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_fault | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_run_config | Run / Config | process | 3.2.1.1 | 1 | 1 | PASS |
| n_chamber | Chamber | process | 3.2.1.1 | 1 | 1 | PASS |
| n_temp_feed | Temp Feed | data | 3.1.1.1 | 1 | 1 | PASS |
| n_control_status | Control / Status | data | 3.1.1.1 | 1 | 1 | PASS |
| n_feedback_filter | Feedback / Filter | process | 3.2.1.1 | 1 | 1 | PASS |
| n_status_window | Status / Window | process | 3.2.1.1 | 1 | 1 | PASS |
| n_history_api | History / API | process | 3.2.1.1 | 1 | 1 | PASS |
| n_history_cache | History / Cache | process | 3.2.1.1 | 1 | 1 | PASS |
| n_feedback_sync | Feedback / Sync | process | 3.2.1.1 | 1 | 1 | PASS |
| n_feedback_ready | Feedback / Ready | data | 3.1.1.1 | 1 | 1 | PASS |
| n_feedback_complete | Feedback / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_feedback | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_window | Window / Build | process | 3.2.1.1 | 1 | 1 | PASS |
| n_feature_extract | Feature / Extract | process | 3.2.1.1 | 1 | 1 | PASS |
| n_feature_store | Feature / Store | process | 3.2.1.1 | 1 | 1 | PASS |
| n_dataset | Dataset / Builder | process | 3.2.1.1 | 1 | 1 | PASS |
| n_offline | Offline / Learn | process | 3.2.1.1 | 1 | 1 | PASS |
| n_model_eval | Model / Eval | process | 3.2.1.1 | 1 | 1 | PASS |
| n_policy | Policy / Rank | process | 3.2.1.1 | 1 | 1 | PASS |
| n_model_package | Model / Package | process | 3.2.1.1 | 1 | 1 | PASS |
| n_model_check | Model / Check | process | 3.2.1.1 | 1 | 1 | PASS |
| n_model_ready | Model / Ready | data | 3.1.1.1 | 1 | 1 | PASS |
| n_model_complete | Model / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_model | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_candidate_set | Cand / Set | data | 3.1.1.1 | 1 | 1 | PASS |
| n_safe_filter | Safe / Filter | process | 3.2.1.1 | 1 | 1 | PASS |
| n_preview | Preview / Sim | process | 3.2.1.1 | 1 | 1 | PASS |
| n_approve | Approve / Req | process | 3.2.1.1 | 1 | 1 | PASS |
| n_op_input | Op Input | manual_operation | 3.2.2.2 | 1 | 1 | PASS |
| n_ok | OK? | decision | 3.2.2.4 | 1 | 2 | PASS |
| n_publish | Param / Publish | process | 3.2.1.1 | 1 | 1 | PASS |
| n_topic | Params / Topic | data | 3.1.1.1 | 1 | 1 | PASS |
| n_down_ack | Down / ACK | data | 3.1.1.1 | 1 | 1 | PASS |
| n_model_files | Model / Files | process | 3.2.1.1 | 1 | 1 | PASS |
| n_publish_complete | Publish / Complete | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_downlink | C | connector | 3.4.1 | 1 | 0 | PASS |
| n_keep | Keep / Params | process | 3.2.1.1 | 1 | 1 | PASS |
| n_reject_log | Reject / Log | process | 3.2.1.1 | 1 | 1 | PASS |
| n_c_reject | C | connector | 3.4.1 | 1 | 0 | PASS |

## Edge Audit
| id | from | port | to | port | len | orthogonal | source | target | arrow | label gap |
|---|---|---|---|---|---:|---|---|---|---|---|
| m00 | Start | south | Item Menu | north | 75 | PASS | PASS | PASS | none |  |
| m01 | Item Menu | south | C | north | 5050 | PASS | PASS | PASS | none | PASS 10 |
| m02 | C | south | End | north | 74 | PASS | PASS | PASS | none |  |
| t01 | Item Menu | south | Status | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| t02 | Status | south | Telem Msg | north | 74 | PASS | PASS | PASS | none |  |
| t03 | Telem Msg | south | MQTT Broker | north | 74 | PASS | PASS | PASS | none |  |
| t04 | MQTT Broker | south | Telem Topic | north | 74 | PASS | PASS | PASS | none |  |
| t05 | Telem Topic | south | Msg Parser | north | 74 | PASS | PASS | PASS | none |  |
| t06 | Msg Parser | south | Schema Check? | north | 74 | PASS | PASS | PASS | none |  |
| t07 | Schema Check? | south | Data Norm | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| t08 | Schema Check? | west | C | east | 119 | PASS | PASS | PASS | open | PASS 10 |
| t09 | Data Norm | south | Java Hub | north | 74 | PASS | PASS | PASS | none |  |
| t10 | Java Hub | south | TS Store | north | 74 | PASS | PASS | PASS | none |  |
| t11 | TS Store | south | Backend Services | north | 74 | PASS | PASS | PASS | none |  |
| t12 | Backend Services | south | HMI | north | 74 | PASS | PASS | PASS | none |  |
| t13 | HMI | south | C | north | 74 | PASS | PASS | PASS | none |  |
| s01 | Item Menu | south | Temp Input | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| s02 | Temp Input | south | Sensor Bus Read | north | 74 | PASS | PASS | PASS | none |  |
| s03 | Sensor Bus Read | south | Raw Sample | north | 74 | PASS | PASS | PASS | none |  |
| s04 | Raw Sample | south | Sample Filter | north | 74 | PASS | PASS | PASS | none |  |
| s05 | Sample Filter | south | Range Check? | north | 74 | PASS | PASS | PASS | none |  |
| s06 | Range Check? | south | Normalize | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| s07 | Normalize | south | Edge Tick | north | 74 | PASS | PASS | PASS | none |  |
| s08 | Edge Tick | south | Sample Window | north | 74 | PASS | PASS | PASS | none |  |
| s09 | Sample Window | south | Cycle State | north | 74 | PASS | PASS | PASS | none |  |
| s10 | Cycle State | south | Control Tick | north | 74 | PASS | PASS | PASS | none |  |
| s11 | Control Tick | south | Sample Complete | north | 74 | PASS | PASS | PASS | none |  |
| s12 | Sample Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| s13 | Range Check? | east | C | west | 119 | PASS | PASS | PASS | none | PASS 10 |
| p01 | Item Menu | south | Param Wait? | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| p02 | Param Wait? | south | Param Candidate | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| p03 | Param Candidate | south | Param Validate | north | 74 | PASS | PASS | PASS | none |  |
| p04 | Param Validate | south | Param Apply | north | 74 | PASS | PASS | PASS | none |  |
| p05 | Param Apply | south | Param ACK | north | 74 | PASS | PASS | PASS | none |  |
| p06 | Param ACK | south | Param Store | north | 74 | PASS | PASS | PASS | none |  |
| p07 | Param Wait? | east | C | west | 114 | PASS | PASS | PASS | none | PASS 10 |
| p08 | Param Store | south | Param Audit | north | 74 | PASS | PASS | PASS | none |  |
| p09 | Param Audit | south | Param Sync | north | 74 | PASS | PASS | PASS | none |  |
| p10 | Param Sync | south | Param Ready | north | 74 | PASS | PASS | PASS | none |  |
| p11 | Param Ready | south | Param Commit | north | 74 | PASS | PASS | PASS | none |  |
| p12 | Param Commit | south | Param Complete | north | 74 | PASS | PASS | PASS | none |  |
| p13 | Param Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| c01 | Item Menu | south | Safety Gate | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| c02 | Safety Gate | south | Safety Check? | north | 74 | PASS | PASS | PASS | none |  |
| c03 | Safety Check? | south | PID Control | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| c04 | PID Control | south | Integral Update | north | 74 | PASS | PASS | PASS | none |  |
| c05 | Integral Update | south | Duty Limit | north | 74 | PASS | PASS | PASS | none |  |
| c06 | Duty Limit | south | PWM Output | north | 74 | PASS | PASS | PASS | none |  |
| c07 | PWM Output | south | Heater Driver | north | 74 | PASS | PASS | PASS | none |  |
| c08 | Heater Driver | south | Actuator ACK | north | 74 | PASS | PASS | PASS | none |  |
| c09 | Actuator ACK | south | Heat State | north | 74 | PASS | PASS | PASS | none |  |
| c10 | Heat State | south | Control Log | north | 74 | PASS | PASS | PASS | none |  |
| c11 | Control Log | south | Control Complete | north | 74 | PASS | PASS | PASS | none |  |
| c12 | Control Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| c13 | Safety Check? | east | Fault Handler | west | 388.5 | PASS | PASS | PASS | open | PASS 10 |
| f00 | Item Menu | south | Fault Handler | north | 52 | PASS | PASS | PASS | none | PASS 10 |
| f01 | Fault Handler | south | Fault Latch | north | 52 | PASS | PASS | PASS | none |  |
| f02 | Fault Latch | south | Safety Cutoff | north | 52 | PASS | PASS | PASS | none |  |
| f03 | Safety Cutoff | south | Alarm Event | north | 52 | PASS | PASS | PASS | none |  |
| f04 | Alarm Event | south | Alarm Panel | north | 52 | PASS | PASS | PASS | none |  |
| f05 | Alarm Panel | south | Alarm API | north | 52 | PASS | PASS | PASS | none |  |
| f06 | Alarm API | south | Device API | north | 52 | PASS | PASS | PASS | none |  |
| f07 | Device API | south | Alarm Records | north | 52 | PASS | PASS | PASS | none |  |
| f08 | Alarm Records | south | Alarm Review | north | 52 | PASS | PASS | PASS | none |  |
| f09 | Alarm Review | south | Fault Reset | north | 52 | PASS | PASS | PASS | none |  |
| f10 | Fault Reset | south | Fault Report | north | 52 | PASS | PASS | PASS | none |  |
| f11 | Fault Report | south | Fault Archive | north | 52 | PASS | PASS | PASS | none |  |
| f12 | Fault Archive | south | Fault Complete | north | 52 | PASS | PASS | PASS | none |  |
| f13 | Fault Complete | south | C | north | 52 | PASS | PASS | PASS | none |  |
| g01 | Item Menu | south | Run Config | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| g02 | Run Config | south | Chamber | north | 74 | PASS | PASS | PASS | none |  |
| g03 | Chamber | south | Temp Feed | north | 74 | PASS | PASS | PASS | none |  |
| g04 | Temp Feed | south | Control Status | north | 74 | PASS | PASS | PASS | none |  |
| g05 | Control Status | south | Feedback Filter | north | 74 | PASS | PASS | PASS | none |  |
| g06 | Feedback Filter | south | Status Window | north | 74 | PASS | PASS | PASS | none |  |
| g07 | Status Window | south | History API | north | 74 | PASS | PASS | PASS | none |  |
| g08 | History API | south | History Cache | north | 74 | PASS | PASS | PASS | none |  |
| g09 | History Cache | south | Feedback Sync | north | 74 | PASS | PASS | PASS | none |  |
| g10 | Feedback Sync | south | Feedback Ready | north | 74 | PASS | PASS | PASS | none |  |
| g11 | Feedback Ready | south | Feedback Complete | north | 74 | PASS | PASS | PASS | none |  |
| g12 | Feedback Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| r01 | Item Menu | south | Window Build | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| r02 | Window Build | south | Feature Extract | north | 74 | PASS | PASS | PASS | none |  |
| r03 | Feature Extract | south | Feature Store | north | 74 | PASS | PASS | PASS | none |  |
| r04 | Feature Store | south | Dataset Builder | north | 74 | PASS | PASS | PASS | none |  |
| r05 | Dataset Builder | south | Offline Learn | north | 74 | PASS | PASS | PASS | none |  |
| r06 | Offline Learn | south | Model Eval | north | 74 | PASS | PASS | PASS | none |  |
| r07 | Model Eval | south | Policy Rank | north | 74 | PASS | PASS | PASS | none |  |
| r08 | Policy Rank | south | Model Package | north | 74 | PASS | PASS | PASS | none |  |
| r09 | Model Package | south | Model Check | north | 74 | PASS | PASS | PASS | none |  |
| r10 | Model Check | south | Model Ready | north | 74 | PASS | PASS | PASS | none |  |
| r11 | Model Ready | south | Model Complete | north | 74 | PASS | PASS | PASS | none |  |
| r12 | Model Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| d01 | Item Menu | south | Candidate Set | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| d02 | Candidate Set | south | Safe Filter | north | 74 | PASS | PASS | PASS | none |  |
| d03 | Safe Filter | south | Preview Sim | north | 74 | PASS | PASS | PASS | none |  |
| d04 | Preview Sim | south | Approve Req | north | 74 | PASS | PASS | PASS | none |  |
| d05 | Approve Req | south | Op Input | north | 74 | PASS | PASS | PASS | none |  |
| d06 | Op Input | south | OK? | north | 74 | PASS | PASS | PASS | none |  |
| d07 | OK? | south | Param Publish | north | 74 | PASS | PASS | PASS | none | PASS 10 |
| d08 | Param Publish | south | Params Topic | north | 74 | PASS | PASS | PASS | none |  |
| d09 | Params Topic | south | Down ACK | north | 74 | PASS | PASS | PASS | none |  |
| d10 | Down ACK | south | Model Files | north | 74 | PASS | PASS | PASS | none |  |
| d11 | Model Files | south | Publish Complete | north | 74 | PASS | PASS | PASS | none |  |
| d12 | Publish Complete | south | C | north | 74 | PASS | PASS | PASS | none |  |
| j01 | OK? | east | Keep Params | west | 90 | PASS | PASS | PASS | none | PASS 10 |
| j02 | Keep Params | south | Reject Log | north | 74 | PASS | PASS | PASS | none |  |
| j03 | Reject Log | south | C | north | 74 | PASS | PASS | PASS | none |  |

## Focus Checks
- All declared vertical branch edges: PASS (vertical, 101.0)
- bg_start_distribution_bus: PASS
- branch_column_layout: PASS

## Failures
- none

## Text-Safety Failures
- none

## Edge Geometry Failures
- none
