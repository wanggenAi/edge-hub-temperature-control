# A1 Engineering Flowchart Layout Plan

## Page And Template
- Template file: aa.drawio
- A1 page size read from template: 3300 x 2339
- Detected template title block: x=2555.18, y=2107.42, width=733.7860000000003, height=221
- Forbidden title block area: x=2525, y=2075, width=775, height=264

## Symbol Ratio Rules
- Terminator, process, predefined process, data, document, and manual input use L = 2W.
- Stored data uses L = 1.5W, following the common horizontal 3:2 proportion used for database-style stored-data symbols.
- Decision uses L = 1.5W.
- Connector uses L = W.
- Autosize is disabled on all repo_flow_ nodes.

## Calculated Sizes
- Rect/parallelogram family: 144 x 72
- Stored data/database family: 119 x 79
- Decision: 132 x 88
- Connector: 52 x 52
- Uniform local segment length U: 130
- Row gap: 285

## Balanced 2D Grid Strategy
- The renderer computes symbol sizes from the A1 free area, node count, and readability limits.
- Nodes are placed in a program-scheme lane layout: multiple left-to-right horizontal flow lines with explicit row connector symbols.
- Rows are not forced to connect with synthetic lines; cross-row relationships use R/F/T/P/A/L connector pairs or local decision branches.
- Node labels are shortened, wrapped, and fitted before draw.io cells are generated.

## Title Block Avoidance
- The renderer rejects any node that intersects the forbidden area.
- The validator checks nodes, lines, labels, and waypoints against the forbidden area.
- The bottom-right page area is left clear around the original title block.

## Connector Pairs
- F1: temperature feedback return; nodes n72 and n73
- P1: parameter downlink; nodes n74 and n75
- R1: row continuation; nodes n81 and n82
- R2: row continuation; nodes n83 and n84
- R3: row continuation; nodes n85 and n86
- R4: row continuation; nodes n87 and n88
- R5: row continuation; nodes n89 and n90
- R6: row continuation; nodes n94 and n95
- R7: short parameter bypass row continuation; nodes n96 and n97
- R8: short safety fault row continuation; nodes n98 and n100

## Long-Line Prevention
- Direct visible edges are generated only for local rightward or adjacent downward relationships.
- Remote logical transfers are recorded as connector-resolved logical edges, never as skipped edges.
- Explicit mxPoint support is implemented in createEdgeCell for controlled Manhattan routing.
- Decision branch labels are stored in separate repo_flow_label_ text cells so they can be offset from line segments.
- No long cross-page polylines are generated.

## No Visible Modules
- Phase and group metadata are kept only in flow_model.json.
- The draw.io page contains no module frames, module titles, legends, or top title.

## English Labels
- All generated node labels and edge labels are English.
- Each node label is restricted to at most two lines.
- Long labels are shortened before wrapping.
- Decision labels are emitted once per rendered branch edge, without duplicate text cells.
- Separate branch label cells use the repo_flow_label_ prefix and are excluded from the flowchart element count.

## GOST / ISO 5807 Mapping Summary
- Terminator: rounded start/end symbol.
- Process: rectangle.
- Predefined process: rectangle with two inner vertical lines.
- Decision: diamond.
- Data: parallelogram.
- Stored data: cylinder-style stored data symbol.
- Document: document symbol.
- Manual input: manual input symbol.
- Connector: circular connector.

## 93 Elements
- 1. Cycle / Start (terminator)
- 2. Temp / Input (data)
- 3. Sensor / Read (process)
- 4. Raw / Sample (data)
- 5. Sample / Filter (process)
- 6. Range / Check? (decision)
- 7. Norm (process)
- 8. Edge / Tick (predefined_process)
- 9. Run / Config (stored_data)
- 10. Param / Wait? (decision)
- 11. Param / Valid (process)
- 12. Param / Apply (process)
- 13. Param / ACK (document)
- 14. Safety / Merge (process)
- 15. Safety / Check? (decision)
- 16. Fault / Latch (process)
- 17. Safety / Cutoff (process)
- 17. Alarm / Event (data)
- 18. PID / Control (predefined_process)
- 19. Int / Upd (process)
- 20. Duty / Limit (process)
- 21. PWM / Output (process)
- 22. Heater / Driver (process)
- 23. Chamber (process)
- 24. Temp / Feed (data)
- 25. Status (data)
- 26. Telem / Msg (data)
- 27. Edge / Log (document)
- 30. MQTT / Broker (predefined_process)
- 31. Telem / Topic (data)
- 32. Msg / Parser (process)
- 33. Schema / Check? (decision)
- 34. Norm (process)
- 35. Java / Hub (predefined_process)
- 36. Alarm / Rules (predefined_process)
- 37. TS / Writer (process)
- 38. TS DB (stored_data)
- 39. Alarm / Store (stored_data)
- 40. Backend / DB (stored_data)
- 41. FastAPI (predefined_process)
- 42. History / API (process)
- 43. Alarm / API (process)
- 44. Device / API (process)
- 45. HMI (predefined_process)
- 46. Live / Chart (document)
- 47. Alarm / Panel (document)
- 48. OpVw (manual_input)
- 50. Act (manual_input)
- 51. Audit / Log (document)
- 52. History / Win (stored_data)
- 53. Window / Build (process)
- 54. Feature / Extract (predefined_process)
- 55. Feature / Store (stored_data)
- 56. Dataset / Builder (process)
- 57. Offline / Learn (predefined_process)
- 58. Model / Eval (process)
- 59. Policy / Rank (predefined_process)
- 60. Cand / Set (data)
- 61. Safe / Filter (process)
- 62. Preview / Sim (predefined_process)
- 63. Appr / Req (document)
- 64. OpIn (manual_input)
- 65. OK? (decision)
- 66. Param / Publish (process)
- 67. Params / Topic (data)
- 68. ACK (document)
- 69. Keep / Params (document)
- 70. Reject / Log (document)
- 71. Model / Files (document)
- 72. F1 (connector)
- 73. F1 (connector)
- 74. P1 (connector)
- 75. P1 (connector)
- 80. End / / Cont (terminator)
- 81. R1 (connector)
- 82. R1 (connector)
- 83. R2 (connector)
- 84. R2 (connector)
- 85. R3 (connector)
- 86. R3 (connector)
- 87. R4 (connector)
- 88. R4 (connector)
- 89. R5 (connector)
- 90. R5 (connector)
- 91. Input / Merge (process)
- 92. Config / Merge (process)
- 93. Fault / Merge (process)
- 94. R6 (connector)
- 95. R6 (connector)
- 96. R7 (connector)
- 97. R7 (connector)
- 98. R8 (connector)
- 100. R8 (connector)
