# Symbol Definition Table

| gost_type | GOST section | Meaning | Shape | Input sides | Output sides |
| --- | --- | --- | --- | --- | --- |
| terminator | 3.4.2 | External entry/exit of the scheme: start, end, external source or destination. | rounded capsule | north, south, west, east | north, south, west, east |
| process | 3.2.1.1 | Processing function or operation. | rectangle | north, south, west, east | north, south, west, east |
| predefined_process | 3.2.2.1 | Process defined elsewhere as a subroutine/module/function block. | rectangle with two vertical side lines | north, south, west, east | north, south, west, east |
| decision | 3.2.2.4 | Switching/decision function with one input and alternative labeled outputs. | rhombus | north, south, west, east | north, south, west, east |
| data | 3.1.1.1 | Input/output data with unspecified carrier. | parallelogram | north, south, west, east | north, south, west, east |
| stored_data | 3.1.1.2 | Stored data suitable for processing. | stored-data/database symbol | north, south, west, east | north, south, west, east |
| document | 3.1.2.4 | Human-readable document, log, report, request or approval artifact; in this drawing it is a terminal data output, not a processing step. | document with wavy bottom edge | north, south, west, east |  |
| manual_input | 3.1.2.5 | Data entered manually during processing. | manual input | north, south, west, east | north, south, west, east |
| manual_operation | 3.2.2.2 | Operation performed by a human operator. | manual operation | north, south, west, east | north, south, west, east |
| display | 3.1.2.8 | Human-readable display output; in this drawing it is terminal visual output and does not drive a later process. | display | north, south, west, east |  |
| connector | 3.4.1 | Line continuation marker. Same-letter C connectors are a traceable continuation group: branch-end C markers symbolically continue to the C marker before End without drawing long crossing lines. | circle with continuation label | north, south, west, east | north, south, west, east |
