# 3 IMPLEMENTATION OF THE EDGE CONTROL LAYER

## 3.1 Control target and hardware design scope

The edge control layer is the local execution part of the developed temperature-control system. Its control target is to maintain the temperature of a small chamber near the specified setpoint by measuring chamber temperature, calculating a control action, and modulating heater power through a PWM-driven output stage. In the implemented configuration, the nominal setpoint is 35 °C, while the accepted operator-configurable setpoint range is 20–60 °C. The software safety limit is 65 °C. These values define the expected laboratory prototype operating range and prevent the operator from applying a target temperature outside the intended small-chamber control task [1].

The scope of this layer is intentionally limited to the local part of the control loop. It receives or stores the active setpoint, reads the temperature feedback, evaluates the controller output, and produces the actuator command that later becomes heater power. Higher-level storage, operator visualization, and recommendation logic are handled by the Data Hub and HMI layers, but they depend on the edge node to provide a stable and repeatable physical interface. For this reason, the hardware choices in this section are evaluated not only by component availability, but also by their influence on measurement reliability, actuator safety, and later experimental verification.

The main hardware choices connected with this control target are summarized in Table 3.1. The table is limited to the key design decisions that affect control execution, temperature feedback, power switching, supply stability, testing safety, debugging, and physical placement.

Table 3.1 – Main hardware choices for the edge control node

| Functional block | Selected hardware or solution | Purpose |
|---|---|---|
| Controller and communication | ESP32-WROOM-32 module | GPIO, PWM, Wi-Fi/MQTT, and serial debugging for local edge control |
| Temperature feedback | DS18B20 sensor with 4.7 kΩ OneWire pull-up | Digital chamber-temperature feedback without analog conditioning |
| Heater actuation | Low-side N-channel logic-level MOSFET switch | Separates heater current from ESP32 GPIO and supports PWM power control |
| Power supply path | 12 V input and 3.3 V buck-regulated logic rail | Supplies the load side and stable low-voltage electronics |
| Basic cutoff and testing | Series heater-supply cutoff in the 12 V path | Allows load-side interruption during setup and abnormal tests |
| Debugging and physical support | Status LED, serial interface, connectors, and separated enclosure layout | Supports assembly checks, diagnostics, and representative sensor placement |

For the simulation profile used during thesis development, the expected control performance is defined as a stable approach to the setpoint without sustained oscillation, with the temperature entering a ±0.5 °C band in approximately 20 s and a ±0.2 °C band in approximately 30 s for the default 35 °C case. The 90 % rise time for the same profile is expected to be about 11 s. These values are design targets for the simulated thermal model and firmware tuning, not final measured characteristics of the physical chamber. After real assembly, the same indicators must be measured again with an external thermometer and instrumented PWM/load-current checks.

This target determines the hardware structure: the system needs a microcontroller for control execution, a temperature sensor for feedback, a power driver for the heater, a stable low-voltage supply for logic, and a mechanical enclosure that separates the thermal chamber from the electronics area. The ESP32-WROOM-32 module is selected because it provides the embedded controller, GPIO, PWM-capable peripherals, and wireless communication resources required by the edge node [3]. The DS18B20 is selected because the control range is moderate and does not require a high-temperature thermocouple [4]. The MOSFET power stage is selected because the actuator is a heater and therefore requires switched load current rather than a direct microcontroller output. The enclosure geometry is selected to make the measured chamber temperature representative of the controlled object rather than the PCB, heater surface, or local hot spot.

The hardware part of the project is therefore not an isolated addition to the software system. It follows directly from the control objective. Since the controlled variable is chamber temperature, the sensor must be placed where it represents the chamber air rather than the PCB temperature or the heater surface. Since the manipulated variable is heater power, the actuator path must be designed as a power-switching path rather than as a direct microcontroller load. Since the Data Hub and HMI require traceability, the edge hardware must also support debugging, status indication, and a communication-capable controller.

The present project contains several hardware-design artifacts: the electrical schematic exported from the circuit-design environment, the component placement screenshot, the ESP32 pin map, the Wokwi simulation connection, PCB reference files, and a three-dimensional enclosure model. These artifacts are used to support the engineering design and to show how the simulated control node can be transferred toward a real device. At the same time, the current thesis does not claim that the final physical circuit has already been assembled and electrically tested. The real power stage and PCB must still be verified with hardware instruments after fabrication.

This boundary is important for correct engineering interpretation. The simulation verifies the logical connection between sensing, control, PWM output, telemetry, and parameter handling. The hardware design explains how this logic should be translated into an electrical and mechanical implementation. The remaining real-hardware stage must verify actual voltage levels, PWM waveform quality, MOSFET switching behavior, load current, heating response, grounding, and thermal safety under real operating conditions.

The electrical schematic of the edge temperature-control node is shown in Figure 3.1. It represents the main control, sensing, low-voltage supply, MOSFET switching, status indication, and connector paths prepared for the hardware stage.

## 3.2 Electrical schematic and pin assignment

Figure 3.1 shows the electrical schematic prepared for the edge node. The central component is the ESP32-WROOM-32 module. The DS18B20 temperature-sensor connector is connected to the ESP32 through the OneWire data line. The data line uses a 4.7 kΩ pull-up resistor to the 3.3 V rail, which is required because the OneWire bus needs a defined high level when no device is actively pulling the line low. The schematic also includes a status LED with a current-limiting resistor, reset and boot buttons, decoupling capacitors, a 12 V to 3.3 V supply path, a heater connector, and the MOSFET switching path used for the actuator.

The selected pin assignment is consistent with the firmware implementation. GPIO21 is used for the DS18B20 data line, GPIO18 is used as the PWM output, GPIO2 is used for the heartbeat LED, and the serial TX/RX pins are used for debugging. This assignment separates the sensing path from the actuation path and leaves the PWM output available for later connection to the MOSFET gate-drive circuit. The logic analyzer is connected to the PWM signal in the simulation so that the duty-cycle behavior can be observed during controller operation.

The pull-up resistor value is chosen as a typical value for DS18B20 OneWire communication. A very large pull-up resistance would make the signal rise more slowly and could reduce communication reliability, while a very small resistance would increase unnecessary current when the bus is pulled low. For the current design, the pull-up current can be estimated by formula (3.1).

{{FORMULA_3_1}}

where I_pullup – pull-up current, A;

U_DD – logic supply voltage, V;

R_pullup – pull-up resistance, Ω.

For U_DD = 3.3 V and R_pullup = 4.7 kΩ, the estimated pull-up current is approximately 0.7 mA when the line is low. This value is suitable for a low-power digital sensor interface and explains why the DS18B20 data line can be connected to the ESP32 logic domain without a high-current driver.

The Wokwi connection is still used as a simulation and firmware-verification aid [11]. It validates the logical pin mapping and the firmware interaction with the sensor, LED, PWM signal, logic analyzer, and serial monitor. However, the Wokwi model does not replace the electrical schematic, and the schematic itself does not replace physical measurement. Input protection, power regulation, grounding behavior, connector reliability, thermal protection, and load-side current must be checked during the later hardware stage.

## 3.3 Power path and MOSFET driver design

The actuation path is based on the idea that the ESP32 must not power the heater directly. A microcontroller pin can provide only a low-current logic signal, while a heater requires a separate power path. Therefore, the hardware design uses a low-side N-channel MOSFET switching concept. In this arrangement, the heater is connected to the positive load supply, the MOSFET is placed between the heater and ground, and the ESP32 PWM signal controls the MOSFET gate through a gate resistor.

The choice of a MOSFET low-side switch follows from the control target. The controller needs to vary the average heating power while keeping the local control loop simple and deterministic. PWM control provides this behavior by switching the load on and off with a controlled duty ratio. The average voltage applied to an ideal resistive load over one PWM period can be represented by formula (3.2).

{{FORMULA_3_2}}

where U_avg – average load voltage over one PWM period, V;

D – PWM duty ratio;

U_s – load supply voltage, V.

For a resistive heater, the load power depends on supply voltage and load resistance. The nominal heater power can be estimated by formula (3.3).

{{FORMULA_3_3}}

where P_load – heater load power, W;

U_s – load supply voltage, V;

R_load – heater resistance, Ω.

These formulas explain why the heater path must be designed as a power circuit. The ESP32 only determines the duty ratio, while the actual heater current depends on the external load supply and heater resistance. For this reason, the power path must be checked separately from the firmware logic during real-hardware testing.

The MOSFET must be selected according to several engineering criteria. First, the drain-source voltage rating must exceed the load supply voltage with margin. Second, the continuous drain-current rating must exceed the expected heater current. Third, the MOSFET should have low on-state resistance at the available gate-drive voltage. Since the ESP32 gate drive is 3.3 V, the MOSFET should be logic-level and suitable for low-voltage gate operation. The conduction loss of the MOSFET can be estimated by formula (3.4).

{{FORMULA_3_4}}

where P_Q – MOSFET conduction loss, W;

I_load – heater current, A;

R_DS(on) – MOSFET drain-source on-state resistance, Ω.

This loss estimate is needed because the MOSFET may heat during operation. If the calculated loss or measured temperature rise is too high, the design must be changed by selecting a lower-resistance MOSFET, improving thermal dissipation, reducing load current, or changing the switching arrangement. The gate resistor is included to limit fast switching edges and reduce stress or ringing on the gate path. The gate pull-down resistor is included so the MOSFET remains off during reset, startup, or a floating-control condition.

The driver concept also requires a common reference ground between the ESP32 logic and the MOSFET source. Without a common reference, the gate-source voltage would not be defined correctly. At the same time, the load-current return path must be designed carefully so that heater current does not disturb sensor measurement or controller operation. In later hardware testing, this point must be checked by measuring ground behavior and PWM switching under load.

## 3.4 PCB and enclosure design

The project also contains PCB reference files and a three-dimensional enclosure model. The PCB reference package includes a STEP model, a DXF board export, a BOM file, a netlist export, and the component placement screenshot shown in Figure 3.2. These files show that the board-level design has progressed beyond a simple simulation connection. They are used as mechanical and layout references for the enclosure and for future hardware integration. However, the current thesis must describe this stage accurately: the board is treated as a design reference and has not yet been verified as a fully tested physical power-control circuit.

The netlist export contains the main circuit elements expected for the edge control hardware, including the ESP32 module, the DS18B20 connector, the heater connector, a power connector, a buck-regulator-related connector block, decoupling capacitors, resistors, LED indication, reset and boot buttons, and a MOSFET device. This confirms the intended hardware direction: logic control, sensor input, low-voltage supply, heater output, and service/debug support are all represented in the design package.

The PCB design must be evaluated according to the same control objective as the firmware. The heater current path should be routed with sufficient width and clearance. The MOSFET and heater connector should be located so that load wiring remains short and separated from sensitive sensor wiring. The DS18B20 connector should avoid noisy high-current paths. The regulator and decoupling elements should provide stable power to the ESP32 and sensor. These requirements come from the need to maintain reliable feedback and safe power switching during closed-loop operation.

The mechanical enclosure is designed as a small temperature-control chamber rather than as a simple PCB box. The three-dimensional layout is shown in Figure 3.3. The model separates the thermal chamber from the electronics bay. This is important because the PCB should not be placed directly in the heated volume, and the DS18B20 should measure chamber temperature rather than the board temperature or heater surface temperature.

The enclosure design includes a chamber area, a separate electronics area, PCB support features, side guide rails, a sensor probe clip, heater wire pass-through support, heater strain relief, and a thermal safety barrier between sample and heater zones. These features reflect practical control-system requirements. The sensor needs repeatable placement, the heater wiring needs mechanical support, and the electronics need to be protected from direct chamber heating. The printable enclosure parts prepared for later fabrication are shown in Figure 3.4.

The enclosure is therefore part of the control design, not only a cosmetic shell. If the sensor is placed too close to the heater, the measured temperature may represent local heater temperature rather than chamber temperature. If the electronics are exposed to the heated volume, the ESP32, connectors, or power components may operate under unsuitable thermal conditions. If the heater wires are not constrained, mechanical movement may affect reliability. The enclosure geometry is designed to reduce these risks at the prototype stage.

The next hardware stage must include physical fabrication and measurement. After the PCB and enclosure are assembled, the circuit should be tested with a multimeter for supply rails and continuity, an oscilloscope or logic analyzer for PWM waveform quality, and a controlled load test for MOSFET switching and heater current. The DS18B20 reading should be compared with an external reference thermometer, and the chamber response should be recorded during heating and cooling. Only after these tests can the hardware be claimed as electrically and thermally validated.

## 3.5 Temperature measurement, feedback, and local control algorithm

The firmware implementation connects the hardware design to the closed-loop control behavior. At each control tick, the edge application reads the DS18B20 temperature value, checks sensor validity, selects the active feedback value, calculates the controller output, applies the PWM duty cycle, updates the simulation plant model when the simulator profile is active, and publishes telemetry. This sequence makes the ESP32 node the local execution core of the system.

The developed implementation distinguishes between physical sensor reading and simulated controlled temperature. In Wokwi, the DS18B20 value is available as a sensor reference, but the virtual heater output does not physically heat the DS18B20 model. Therefore, the simulator profile uses a virtual thermal model as the controlled process variable while still reporting the DS18B20 reading. This decision is important because it avoids claiming a physical heating effect that the simulator cannot provide.

The virtual thermal model represents heating as a function of normalized PWM duty and cooling as a function of the difference between simulated temperature and ambient temperature. It is intentionally simple, but it is sufficient for repeatable control experiments. The model lets the project demonstrate rise time, convergence, output saturation, parameter influence, and post-apply behavior without requiring a physical heater during early development.

The controller is PI-oriented with a PID-compatible runtime parameter structure. The runtime configuration contains proportional, integral, and derivative coefficients, but the default derivative coefficient is zero. This means the tuned default behavior is PI-like while the message contract remains compatible with PID-style parameter storage and future experiments. The control error is calculated by formula (3.5).

{{FORMULA_3_5}}

where e(t) – temperature-control error, °C;

T_set – target temperature, °C;

T(t) – measured or simulated controlled temperature, °C.

The general continuous PID control law used as the reference form is given by formula (3.6).

{{FORMULA_3_6}}

where u(t) – controller output before limiting;

K_p – proportional gain;

K_i – integral gain;

K_d – derivative gain.

The initial controller coefficients were not selected as arbitrary software constants. The engineering basis is the classical Ziegler-Nichols closed-loop method, also known as the ultimate-gain method, which is widely used as an initial PID tuning procedure [13]. In this procedure the integral and derivative actions are first disabled, the proportional gain is increased until the controlled process approaches sustained oscillation, and the observed ultimate gain and oscillation period are used to calculate the initial PID coefficients. For the parallel PID form in formula (3.6), the corresponding initial relations are given by formula (3.7).

{{FORMULA_3_7}}

where K_u – ultimate proportional gain obtained from the onset of sustained oscillation;

T_u – ultimate oscillation period, s.

In the present project this method was used as the engineering reference for the first tuning stage. Since the physical chamber and power stage had not yet been assembled and instrumented, the final ultimate gain and ultimate period must be confirmed later on the real device by a controlled closed-loop test. At the simulator stage, the Ziegler-Nichols-based estimate was intentionally converted into a conservative PI-oriented setting because the thermal object is slow, the actuator is PWM-limited, and the DS18B20 measurement is discrete.

In the implemented default configuration, K_p = 120, K_i = 12, and K_d = 0. This value set should therefore be interpreted as an initial engineering tuning refined by simulation rather than as a final industrial tuning of the physical object. The derivative part is available in the runtime structure but is not active in the tuned default behavior. The proportional term reacts to current error, while the integral term helps reduce steady-state error. The selected integral gain was reduced from the more aggressive initial PI test value after simulation showed that the lower value preserved final accuracy while avoiding unnecessary overshoot. The calculated output is limited to the PWM range from 0 to 255, and the normalized duty ratio sent to the actuator path is calculated by formula (3.8).

{{FORMULA_3_8}}

where D – normalized PWM duty ratio;

u – limited controller output.

Several implementation details improve embedded-control behavior. The controller uses the measured elapsed time between control ticks, clamps the output to the valid PWM range, limits the integral state, and avoids increasing the integral term when the output is already saturated in the same direction as the error. This is a practical anti-windup measure. The output saturation state is included in telemetry so that the Data Hub and HMI can explain slow response or limited control authority.

The key part of the implemented anti-windup logic is shown in Figure 3.5. The fragment demonstrates that the integral candidate is calculated first, but it is committed only when the controller output is not saturated in the same direction as the current error. The same fragment also shows how the raw controller output is limited to the PWM range and how the saturation state is made explicit for later telemetry analysis.

When a new runtime configuration is applied, the controller integral state can be reset. This prevents hidden accumulated error from continuing to influence the process after the operator changes the setpoint or gains. This behavior supports post-apply verification because the observed response after a parameter update is more directly connected to the new active configuration.

## 3.6 Runtime configuration, MQTT handling, and safety validation

The edge node maintains an active runtime configuration that includes the target temperature, controller gains, control period, and control mode. During operation, this configuration can be changed through the MQTT parameter command path. A parameter message is parsed, validated, applied immediately or staged, and followed by an acknowledgement. This behavior is essential because a command published by an upper layer is not the same as a command accepted by the device.

The parser supports partial parameter updates. For example, a message may update only the setpoint or only one controller coefficient while leaving the remaining parameters unchanged. The validator checks whether the target temperature, gains, control period, and control mode are within allowed ranges. If parsing or validation fails, the device does not apply the command and publishes a failure acknowledgement with a reason. If validation succeeds, the device either applies the update immediately or stores it as pending.

Telemetry is published after control ticks as structured JSON. It includes identity, uptime, setpoint, simulated and sensor temperature, control error, integral error, derivative information, PWM duty, normalized PWM output, saturation state, control period, timing error, controller parameters, Wi-Fi state, MQTT state, fault state, safety-output state, and pending-parameter state. These fields allow the Data Hub and HMI to reconstruct not only what temperature was measured, but also why the controller behaved in a particular way.

The acknowledgement payload contains the acknowledgement type, success flag, applied-immediately flag, pending-parameter state, active runtime parameters, reason, uptime, sensor validity, fault state, and software safety limit. This gives the HMI a reliable way to show whether a parameter command was processed by the edge node. It also gives the Data Hub a persistent record that can be compared with later telemetry during post-apply verification.

Safety behavior is implemented locally because the edge node is the final execution point for the actuator. If the sensor value is invalid, the firmware latches a fault. If the measured sensor temperature exceeds the configured software maximum safe temperature, the firmware also latches a fault. In a fault state, the controller integral is reset and the actuator output is forced to zero. The telemetry then reports the fault reason and the safety-output state.

The firmware fragment shown in Figure 3.6 connects measurement, safety checking, local control, actuator output, simulator update, telemetry construction, and MQTT publication. This fragment is important because it demonstrates that the edge layer is not only a mathematical controller, but a complete local execution loop with safety forcing and traceable output state.

The local safety behavior does not replace real electrical protection. It is a software safety layer that must be supported by proper hardware design and measurement. During later hardware testing, the PWM output should be checked with an oscilloscope, the MOSFET gate voltage should be measured under switching conditions, the heater current should be measured under load, the regulator output should be checked during switching, and the chamber temperature should be compared with an external thermometer. These tests are necessary before the PCB and enclosure can be considered validated as real hardware.

The planned hardware-verification sequence should therefore start from low-risk checks and move gradually toward closed-loop operation. First, the assembled PCB should be inspected visually to confirm component orientation, solder quality, connector placement, and absence of visible shorts. Second, continuity and resistance checks should be performed with the power disconnected, especially on the 12 V rail, the 3.3 V rail, the heater output path, and the ground network. Third, the low-voltage supply should be powered without the heater load, and the 3.3 V rail should be measured under static and switching conditions.

After the supply checks, the control-output path should be verified separately from the thermal chamber. The ESP32 PWM output should be observed with an oscilloscope or logic analyzer at the microcontroller pin and then at the MOSFET gate. The measured duty ratio should correspond to the controller command, and the waveform should not show unexpected pulses during reset or startup. A resistive test load can then be connected instead of the final heater so that MOSFET switching, load current, voltage drop, and component heating can be checked under controlled conditions.

The final hardware stage should connect the electrical behavior to the controlled object. The DS18B20 reading should be compared with an external thermometer at several chamber temperatures, and the sensor position should be adjusted if it measures local heater influence rather than representative chamber air. The heater should then be tested with conservative duty limits before the full controller is enabled. During this stage, recorded telemetry, acknowledgements, and HMI observations should be compared with instrument measurements. This comparison is necessary because a software log alone cannot prove that the physical circuit behaves safely.

These verification steps define the boundary between the completed design work and the remaining physical validation work. In the present thesis, the edge layer is implemented and prepared for hardware transfer, while the final claim of electrical and thermal validation is intentionally reserved for the later assembled prototype.

The implemented edge layer therefore connects the hardware design, control algorithm, runtime configuration, MQTT communication, and safety behavior into one local execution subsystem. It provides the foundation for the Data Hub and HMI implementation described in the following chapter.
