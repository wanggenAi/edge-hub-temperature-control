# experiments

This directory stores experiment records, parameter settings, and result analysis materials.

Current experiment record structure:

- `stage_record_v1.md`: staged summary across the current control development path
- `p_control_v2.md`: detailed record for the V2 proportional-control experiment
- `pi_control_v3.md`: detailed record for the initial V3 PI-control experiment
- `pi_tuned_v3_1.md`: detailed record for the tuned V3.1 PI-control experiment
- `comparison_table.md`: cross-version comparison for quick review and later thesis reuse
- `control_validation_metrics.py`: reproducible offline calculation of staged controller metrics
- `control_validation_metrics.csv`: generated numeric comparison used for thesis validation
- `control_validation_metrics.md`: generated human-readable control validation table

For the graduation project, each experiment should record at least:

- experiment date
- simulation version
- target temperature
- control cycle
- control parameters
- initial temperature
- observed behavior
- steady-state error
- whether oscillation or overshoot occurred

Future additions may include:

- CSV data
- plotted curves
- screenshots
- experiment conclusions

Documentation sync date: 2026-05-09.
