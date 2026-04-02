# Small Incubator Layout Strategy

This note defines the enclosure as a small temperature-control chamber rather than a simple PCB box.

The enclosure must support:

- a usable heated cavity for test items
- a control PCB that stays outside the direct heated volume
- an external or embedded heater load connection
- accessible TX / RX debugging access
- a DS18B20 sensing position that represents chamber temperature rather than board temperature

## 1. Product-Level Layout Direction

The enclosure should be treated as two functional zones:

- thermal chamber zone
- electronics service zone

The thermal chamber zone is where the heated air and test items live.

The electronics service zone is where the PCB, power wiring, heater wiring, and debug access live.

These two zones should not be merged into one cavity.

For a V1 3D-printed design, the recommended arrangement is:

- upper volume: insulated or semi-enclosed test chamber
- lower or side volume: electronics bay

This is the most practical way to avoid:

- heating the PCB directly
- corrupting temperature measurement with PCB self-heating
- exposing the ESP32 and connectors to unnecessary thermal stress
- making debug and wiring access difficult

## 2. PCB Placement Strategy

The PCB should be mounted in the electronics bay, not on the chamber floor.

Recommended placement:

- mount the PCB vertically against a side wall, or
- mount the PCB horizontally in a separate lower compartment

For the current board state, a separate electronics bay is preferred over placing the board under the usable chamber floor without separation.

Reason:

- the chamber must remain available for placing small samples
- the heater wiring and power switching path need room
- the PCB does not currently expose clearly confirmed enclosure mounting holes
- a side-bay or lower-bay architecture makes non-hole-based retention easier

## 3. PCB Retention Strategy

Because dedicated mounting holes have not yet been confirmed from the PCB reference files, V1 fixation should not depend on screw standoffs.

Recommended V1 retention:

- PCB support ledge under the board edge
- two side guide rails to constrain lateral movement
- one top clip or screw-down pressure bar to stop lift-out

This gives a practical retention scheme with low risk:

- the board can be inserted and removed
- no drilling assumptions are required
- minor PCB export inaccuracies do not break the enclosure

Avoid for V1:

- relying on guessed mounting-hole positions
- tightly clamping tall components
- placing a retention feature over the ESP32 antenna area

## 4. Chamber Layout Strategy

The heated chamber should be the primary volume of the product.

Recommended V1 chamber arrangement:

- chamber located above the electronics bay
- removable top lid for access
- internal flat platform or basket area for small items
- heater mounted near chamber perimeter or below an internal divider
- DS18B20 probe placed in the chamber air region, not touching the heater

The chamber floor should ideally be a divider plate above the PCB zone.

That divider does two jobs:

- physically separates objects in the chamber from the electronics
- slows direct radiant heating from biasing the PCB temperature

## 5. Heater Integration Strategy

Your heater must be treated as a real load interface, not as a PCB detail.

That means the enclosure needs:

- a dedicated heater cable exit or terminal access area
- strain relief for heater wiring
- separation between heater wiring and signal wiring
- local space near the power-driver side of the PCB

Recommended physical arrangement:

- heater attached to chamber wall, chamber base plate, or air path region
- heater wires routed directly to the electronics bay through a dedicated pass-through
- MOSFET / load-side wiring kept short and routed away from the TX/RX and DS18B20 signal path

For V1, do not route heater wires loosely through the same free space used by the debug wires.

## 6. DS18B20 Placement Strategy

The DS18B20 should measure chamber temperature, not PCB temperature and not heater surface temperature.

Recommended placement:

- suspend or mount the DS18B20 tip inside the chamber air volume
- keep it offset from the heater
- keep it away from direct wall contact if wall temperature is not the target variable

Good V1 rule:

- place the probe around the middle height of the chamber
- place it near where the sample sits
- do not let it touch the heater, MOSFET area, or PCB

The enclosure should therefore include:

- a sensor wire pass-through
- a clip, slot, or probe seat for the DS18B20 cable or head

## 7. TX / RX Debug Access Strategy

TX / RX access is a product-level service feature and should stay reachable without opening the thermal chamber.

Recommended V1 approach:

- expose a small service opening in the electronics bay wall
- optionally use a recessed connector window or header access slot
- keep this interface separate from heater wiring exits

This lets you:

- connect to the upper computer during tuning
- inspect logs without disturbing the chamber setup
- avoid opening the heated chamber every time you debug

## 8. Suggested Whole-Box Arrangement

The most practical V1 arrangement is:

- top: chamber lid
- center: usable heated chamber
- middle divider: chamber floor / electronics roof
- bottom or side bay: PCB and wiring
- side wall opening: TX / RX access
- separate cable exit: heater load wiring
- separate small pass-through: DS18B20 cable

In words, this is a chamber-first enclosure with a service compartment attached to it.

It is not a PCB enclosure with some empty room left over.

## 9. What This Means For Future CadQuery Modeling

The modeling order should follow product intent:

1. define the chamber volume first
2. define the divider and electronics bay second
3. place the PCB in the service bay
4. add PCB retention features
5. add heater cable routing and load-side access
6. add DS18B20 routing and probe position
7. add TX / RX service opening

This order is important because the PCB should adapt to the product layout, not the other way around.
