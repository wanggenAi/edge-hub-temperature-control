#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const MODEL_PATH = path.join(__dirname, "schematic_model.yaml");
const TITLE_TEMPLATE_PATH = path.join(ROOT, "templates", "gost_2_104_form1_title_block.yaml");
const LIST_TEMPLATE_PATH = path.join(ROOT, "templates", "gost_2_701_element_list.yaml");
const OUT = path.join(__dirname, "esp32_temperature_node_gost.drawio");

const model = JSON.parse(fs.readFileSync(MODEL_PATH, "utf8"));
const titleTemplate = JSON.parse(fs.readFileSync(TITLE_TEMPLATE_PATH, "utf8"));
const listTemplate = JSON.parse(fs.readFileSync(LIST_TEMPLATE_PATH, "utf8"));

const cells = [];

function safeId(value) {
  return String(value)
    .replace(/^\+/, "P")
    .replace(/[^A-Za-z0-9_.:-]+/g, "_")
    .replace(/\+/g, "P")
    .replace(/-$/g, "_N")
    .replace(/--+/g, "_");
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "&lt;br&gt;");
}

function metaAttrs(meta = {}) {
  return Object.entries(meta)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => ` data-${key}="${esc(value)}"`)
    .join("");
}

function shape(id, value, style, x, y, width, height, kind, meta = {}) {
  id = safeId(id);
  cells.push(
    `<mxCell id="${esc(id)}" value="${esc(value)}" style="${style}" parent="1" vertex="1" data-kind="${esc(kind)}"${metaAttrs(meta)}><mxGeometry x="${x}" y="${y}" width="${width}" height="${height}" as="geometry"/></mxCell>`
  );
}

function edge(id, x1, y1, x2, y2, strokeWidth, kind, meta = {}) {
  id = safeId(id);
  cells.push(
    `<mxCell id="${esc(id)}" value="" style="endArrow=none;html=1;rounded=0;strokeColor=#000000;strokeWidth=${strokeWidth};" parent="1" edge="1" data-kind="${esc(kind)}"${metaAttrs(meta)}><mxGeometry width="50" height="50" relative="1" as="geometry"><mxPoint x="${x1}" y="${y1}" as="sourcePoint"/><mxPoint x="${x2}" y="${y2}" as="targetPoint"/></mxGeometry></mxCell>`
  );
}

function rect(id, x, y, width, height, strokeWidth, kind, meta = {}, value = "") {
  shape(
    id,
    value,
    `rounded=0;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#000000;strokeWidth=${strokeWidth};fontFamily=Arial;fontSize=2.5;align=center;verticalAlign=middle;spacing=0;`,
    x,
    y,
    width,
    height,
    kind,
    meta
  );
}

function cellBox(id, x, y, width, height, kind, meta = {}) {
  shape(
    id,
    "",
    "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;strokeWidth=0;spacing=0;",
    x,
    y,
    width,
    height,
    kind,
    meta
  );
}

function text(id, value, x, y, width, height, fontHeight, align, kind, meta = {}) {
  shape(
    id,
    value,
    `text;html=1;strokeColor=none;fillColor=none;align=${align};verticalAlign=middle;whiteSpace=wrap;rounded=0;fontFamily=Arial;fontSize=${fontHeight};rotation=0;spacing=0;`,
    x,
    y,
    width,
    height,
    kind,
    { role: meta.role || kind, font_height_mm: fontHeight, ...meta }
  );
}

function line(id, x1, y1, x2, y2, strokeWidth, kind, meta = {}) {
  edge(id, x1, y1, x2, y2, strokeWidth, kind, { role: meta.role || kind, ...meta });
}

function dot(id, x, y, net) {
  shape(
    id,
    "",
    "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=#000000;strokeColor=#000000;strokeWidth=0.25;",
    x - 1,
    y - 1,
    2,
    2,
    "junction",
    { role: "junction", net, anchor_x: x, anchor_y: y, unit: "mm" }
  );
}

function pinId(ref, number) {
  return `${safeId(ref)}_${safeId(number)}`;
}

const PIN_TABLE_WIDTH_MM = 56;
const PIN_TABLE_LEAD_MM = 4;
const PIN_TABLE_NUMBER_COL_MM = 8;
const PIN_TABLE_FONT_MM = 2.2;

function isPinTableComponent(component) {
  return ["mcu", "module", "connector_left", "connector_right"].includes(component.symbol);
}

function pinTableBox(component) {
  const box = component.bbox_mm;
  const leftPins = component.pins.filter((pin) => pin.side === "left");
  const rightPins = component.pins.filter((pin) => pin.side === "right");
  if (leftPins.length && rightPins.length) {
    const leftX = Math.min(...leftPins.map((pin) => pin.x));
    const rightX = Math.max(...rightPins.map((pin) => pin.x));
    return { x: (leftX + rightX - PIN_TABLE_WIDTH_MM) / 2, y: box.y, width: PIN_TABLE_WIDTH_MM, height: box.height };
  }
  if (leftPins.length) {
    const leftX = Math.min(...leftPins.map((pin) => pin.x));
    return { x: leftX + PIN_TABLE_LEAD_MM, y: box.y, width: PIN_TABLE_WIDTH_MM, height: box.height };
  }
  if (rightPins.length) {
    const rightX = Math.max(...rightPins.map((pin) => pin.x));
    return { x: rightX - PIN_TABLE_LEAD_MM - PIN_TABLE_WIDTH_MM, y: box.y, width: PIN_TABLE_WIDTH_MM, height: box.height };
  }
  return { x: box.x, y: box.y, width: PIN_TABLE_WIDTH_MM, height: box.height };
}

function pinRowBounds(component, tableBox, pin) {
  const rows = Array.from(new Set(component.pins.map((candidate) => candidate.y))).sort((a, b) => a - b);
  const index = rows.indexOf(pin.y);
  const top = index === 0 ? tableBox.y : (rows[index - 1] + pin.y) / 2;
  const bottom = index === rows.length - 1 ? tableBox.y + tableBox.height : (pin.y + rows[index + 1]) / 2;
  return { top, bottom, height: bottom - top };
}

function drawFrame() {
  const frame = model.drawing_frame;
  rect("frame.outer", frame.x, frame.y, frame.width, frame.height, frame.line_width_mm, "frame", {
    role: "drawing_frame",
    id: "frame.outer",
    unit: "mm"
  });
}

function drawTitleBlock() {
  const tb = titleTemplate.title_block;
  const lw = titleTemplate.line_widths;
  const major = lw.major_line_mm || lw.major_mm || lw.outer_border_mm;
  const minor = lw.minor_line_mm || lw.minor_mm;
  rect("title_block.outer", tb.x, tb.y, tb.width, tb.height, major, "title_block", {
    role: "title_block.outer_border",
    template_id: "gost_2_104_form1",
    unit: "mm"
  });

  (titleTemplate.lines || []).forEach((gridLine, index) => {
    const stroke = gridLine.line_type === "minor" ? minor : major;
    line(
      `title_block.line.${gridLine.id || String(index).padStart(3, "0")}`,
      tb.x + gridLine.x1,
      tb.y + gridLine.y1,
      tb.x + gridLine.x2,
      tb.y + gridLine.y2,
      stroke,
      "title_block_line",
      {
        role: gridLine.line_type === "minor" ? "title_block.minor_line" : "title_block.major_line",
        template_id: gridLine.id,
        line_type: gridLine.line_type,
        unit: "mm"
      }
    );
  });

  titleTemplate.cells.forEach((cell) => {
    cellBox(
      `title_block.cell.${cell.id}`,
      tb.x + cell.x,
      tb.y + cell.y,
      cell.width,
      cell.height,
      "title_block_cell",
      {
        role: "title_block_cell",
        template_id: cell.id,
        field_name: cell.field_name,
        line_type: cell.line_type,
        unit: "mm"
      }
    );
    if (cell.expected_text) {
      const pad = 0.5;
      text(
        `title_block.text.${cell.id}`,
        cell.expected_text,
        tb.x + cell.x + pad,
        tb.y + cell.y + pad,
        cell.width - pad * 2,
        cell.height - pad * 2,
        cell.font_height_mm,
        cell.horizontal_align || "center",
        "title_block",
        {
          role: "title_block_text",
          template_id: cell.id,
          field_name: cell.field_name,
          unit: "mm"
        }
      );
    }
  });
}

function drawListOfElements() {
  const table = listTemplate.overall || listTemplate.list_of_elements;
  const tableRules = listTemplate.element_list || listTemplate.list_of_elements;
  const columns = listTemplate.columns;
  const major = tableRules.line_width_major_mm;
  const minor = tableRules.line_width_minor_mm;
  const titleH = listTemplate.title?.height || 0;
  const headerH = listTemplate.header.height;
  const groupRowH = listTemplate.rows?.group_row_height_mm || listTemplate.row_height_mm;
  const itemRowH = listTemplate.rows?.item_row_height_mm || listTemplate.row_height_mm;
  const blankRowH = listTemplate.rows?.blank_row_height_mm || itemRowH;
  const separatorCount = Math.max(0, listTemplate.groups.length - 1);
  const totalHeight =
    titleH +
    headerH +
    listTemplate.groups.reduce((sum, group) => sum + groupRowH + itemRowH * group.items.length, 0) +
    separatorCount * blankRowH;
  let y = table.y;

  cellBox("element_list.outer", table.x, table.y, table.width, totalHeight, "element_list", {
    role: "element_list.outer_border",
    template_id: "gost_2_701_element_list",
    unit: "mm"
  });

  const verticals = [0, ...columns.slice(1).map((column) => column.x)];
  verticals.forEach((x, index) => {
    const role = index === 0 ? "element_list.outer_border" : "element_list.major_line";
    line(
      `element_list.line.v.${String(index).padStart(3, "0")}`,
      table.x + x,
      table.y,
      table.x + x,
      table.y + totalHeight,
      major,
      "element_list_line",
      {
        role,
        line_type: index === 0 ? "outer" : "major",
        unit: "mm"
      }
    );
  });
  const horizontalLines = [{ y: headerH, major: true }];

  columns.forEach((column) => {
    cellBox(`element_list.cell.header.${column.id}`, table.x + column.x, y, column.width, headerH, "element_list_cell", {
      role: "element_list_cell",
      column_id: column.id,
      unit: "mm"
    });
    text(`element_list.text.header.${column.id}`, column.title, table.x + column.x + 0.6, y + 0.4, column.width - 1.2, headerH - 0.8, listTemplate.header.font_height_mm, "center", "element_list_text", {
      role: "element_list_text",
      column_id: column.id
    });
  });
  y += headerH;

  listTemplate.groups.forEach((group, groupIndex) => {
    const groupKey = group.name.replace(/[^A-Za-z0-9]+/g, "_");
    columns.forEach((column) => {
      cellBox(`element_list.cell.group.${groupKey}.${column.id}`, table.x + column.x, y, column.width, groupRowH, "element_list_cell", {
        role: "element_list_cell",
        group: group.name,
        column_id: column.id,
        unit: "mm"
      });
    });
    const nameColumn = columns.find((column) => column.id === "description") || columns[1];
    const groupPad = 0.8;
    text(`element_list.text.group.${groupKey}`, group.name, table.x + nameColumn.x + groupPad, y + 1.0, nameColumn.width - groupPad * 2, groupRowH - 2.0, tableRules.min_font_height_mm, "center", "element_list_text", {
      role: "element_list_text",
      group: group.name,
      column_id: nameColumn.id
    });
    y += groupRowH;
    horizontalLines.push({ y: y - table.y, major: false });

    group.items.forEach((item) => {
      const values = {
        ref_designator: item.refs,
        description: item.description,
        qty: String(item.qty),
        note: item.note
      };
      columns.forEach((column) => {
        cellBox(`element_list.cell.${item.refs.replace(/[^A-Za-z0-9]+/g, "_")}.${column.id}`, table.x + column.x, y, column.width, itemRowH, "element_list_cell", {
          role: "element_list_cell",
          refs: item.refs,
          column_id: column.id,
          unit: "mm"
        });
        const align = "center";
        const pad = 0.8;
        text(`element_list.text.${item.refs.replace(/[^A-Za-z0-9]+/g, "_")}.${column.id}`, values[column.id], table.x + column.x + pad, y + 1.0, column.width - pad * 2, itemRowH - 2.0, tableRules.min_font_height_mm, align, "element_list_text", {
          role: "element_list_text",
          refs: item.refs,
          column_id: column.id
        });
      });
      y += itemRowH;
      horizontalLines.push({ y: y - table.y, major: false });
    });
    if (groupIndex < listTemplate.groups.length - 1) {
      columns.forEach((column) => {
        cellBox(`element_list.cell.blank.${groupKey}.${column.id}`, table.x + column.x, y, column.width, blankRowH, "element_list_cell", {
          role: "element_list_cell",
          group_after: group.name,
          column_id: column.id,
          blank_row: "true",
          unit: "mm"
        });
      });
      y += blankRowH;
      horizontalLines.push({ y: y - table.y, major: false });
    }
  });

  horizontalLines.forEach((gridLine, index) => {
    if (gridLine.y <= 0 || gridLine.y >= totalHeight) return;
    const isMajor = gridLine.major;
    line(
      `element_list.line.h.${String(index).padStart(3, "0")}`,
      table.x,
      table.y + gridLine.y,
      table.x + table.width,
      table.y + gridLine.y,
      isMajor ? major : minor,
      "element_list_line",
      {
        role: isMajor ? "element_list.major_line" : "element_list.minor_line",
        line_type: isMajor ? "major" : "minor",
        unit: "mm"
      }
    );
  });
  line(
    "element_list.line.h.bottom",
    table.x,
    table.y + totalHeight,
    table.x + table.width,
    table.y + totalHeight,
    major,
    "element_list_line",
    {
      role: "element_list.outer_border",
      line_type: "outer",
      unit: "mm"
    }
  );
}

function drawPin(component, pin, bodyOverride = component.bbox_mm, drawLabel = true) {
  const body = bodyOverride;
  let bodyX = pin.x;
  let bodyY = pin.y;
  if (pin.side === "left") bodyX = body.x;
  if (pin.side === "right") bodyX = body.x + body.width;
  if (pin.side === "top") bodyY = body.y;
  if (pin.side === "bottom") bodyY = body.y + body.height;
  line(
    `component.${component.ref}.pin.${pinId(component.ref, pin.number)}`,
    pin.x,
    pin.y,
    bodyX,
    bodyY,
    0.25,
    "pin",
    {
      role: "component_pin",
      ref: component.ref,
      pin_number: pin.number,
      pin_name: pin.name,
      net: pin.net,
      endpoint_x: pin.x,
      endpoint_y: pin.y,
      line_center_x: (pin.x + bodyX) / 2,
      line_center_y: (pin.y + bodyY) / 2,
      unit: "mm"
    }
  );
  if (drawLabel) {
    let box = pin.label_bbox_mm;
    let font = 2.5;
    let align = pin.side === "left" ? "left" : pin.side === "right" ? "right" : "center";
    if (pin.side === "left" || pin.side === "right") {
      const width = Math.max(12, Math.min(24, String(pin.name).length * 3.0 + 4));
      const centerX = (pin.x + bodyX) / 2;
      box = { x: centerX - width / 2, y: pin.y - 4.0, width, height: 3.0 };
      font = 2.0;
      align = "center";
    }
    text(
      `component.${component.ref}.pinlabel.${pinId(component.ref, pin.number)}`,
      pin.name,
      box.x,
      box.y,
      box.width,
      box.height,
      font,
      align,
      "pin-label",
      {
        role: "pin_label",
        ref: component.ref,
        pin_number: pin.number,
        pin_name: pin.name,
        net: pin.net,
        pin_x: pin.x,
        pin_y: pin.y,
        pin_side: pin.side,
        pin_line_center_x: (pin.x + bodyX) / 2,
        pin_line_center_y: (pin.y + bodyY) / 2,
        pin_line_y: pin.y,
        label_policy: pin.side === "left" || pin.side === "right" ? "above_pin_line" : "side_or_above",
        unit: "mm"
      }
    );
  }
}

function drawPinTable(component, tableBox) {
  rect(`component.${component.ref}.body`, tableBox.x, tableBox.y, tableBox.width, tableBox.height, 0.25, "component", {
    role: "component_body",
    ref: component.ref,
    component_type: component.type,
    zone: component.zone,
    pin_table: "true",
    pin_table_width_mm: PIN_TABLE_WIDTH_MM,
    unit: "mm"
  });

  const leftPins = component.pins.filter((pin) => pin.side === "left");
  const rightPins = component.pins.filter((pin) => pin.side === "right");
  const hasBothSides = leftPins.length > 0 && rightPins.length > 0;
  const midX = tableBox.x + tableBox.width / 2;
  const verticals = [];
  if (leftPins.length) verticals.push(tableBox.x + PIN_TABLE_NUMBER_COL_MM);
  if (hasBothSides) {
    verticals.push(midX, tableBox.x + tableBox.width - PIN_TABLE_NUMBER_COL_MM);
  } else if (rightPins.length) {
    verticals.push(tableBox.x + tableBox.width - PIN_TABLE_NUMBER_COL_MM);
  }
  Array.from(new Set(verticals.map((value) => Number(value.toFixed(3))))).forEach((x, index) => {
    line(`component.${component.ref}.pintable.v.${String(index).padStart(2, "0")}`, x, tableBox.y, x, tableBox.y + tableBox.height, 0.25, "symbol", {
      role: "component_symbol",
      ref: component.ref,
      pin_table_line: "vertical",
      unit: "mm"
    });
  });

  const rowYs = Array.from(new Set(component.pins.map((pin) => pin.y))).sort((a, b) => a - b);
  for (let i = 0; i < rowYs.length - 1; i += 1) {
    const y = (rowYs[i] + rowYs[i + 1]) / 2;
    line(`component.${component.ref}.pintable.h.${String(i).padStart(2, "0")}`, tableBox.x, y, tableBox.x + tableBox.width, y, 0.25, "symbol", {
      role: "component_symbol",
      ref: component.ref,
      pin_table_line: "horizontal",
      unit: "mm"
    });
  }

  component.pins.forEach((pin) => {
    const row = pinRowBounds(component, tableBox, pin);
    const padY = Math.min(1, Math.max(0.4, row.height * 0.16));
    const textY = row.top + padY;
    const textH = row.height - padY * 2;
    let numberBox;
    let nameBox;
    if (pin.side === "right") {
      const nameLeft = hasBothSides ? midX : tableBox.x;
      numberBox = { x: tableBox.x + tableBox.width - PIN_TABLE_NUMBER_COL_MM, y: textY, width: PIN_TABLE_NUMBER_COL_MM, height: textH };
      nameBox = { x: nameLeft + 0.4, y: textY, width: tableBox.x + tableBox.width - PIN_TABLE_NUMBER_COL_MM - nameLeft - 0.8, height: textH };
    } else {
      const nameRight = hasBothSides ? midX : tableBox.x + tableBox.width;
      numberBox = { x: tableBox.x, y: textY, width: PIN_TABLE_NUMBER_COL_MM, height: textH };
      nameBox = { x: tableBox.x + PIN_TABLE_NUMBER_COL_MM + 0.4, y: textY, width: nameRight - tableBox.x - PIN_TABLE_NUMBER_COL_MM - 0.8, height: textH };
    }
    text(`component.${component.ref}.pinnumber.${pinId(component.ref, pin.number)}`, pin.number, numberBox.x, numberBox.y, numberBox.width, numberBox.height, PIN_TABLE_FONT_MM, "center", "component-text", {
      role: "component_text",
      ref: component.ref,
      pin_number: pin.number,
      pin_name: pin.name,
      unit: "mm"
    });
    text(`component.${component.ref}.pinlabel.${pinId(component.ref, pin.number)}`, pin.name, nameBox.x, nameBox.y, nameBox.width, nameBox.height, PIN_TABLE_FONT_MM, "center", "pin-label", {
      role: "pin_label",
      ref: component.ref,
      pin_number: pin.number,
      pin_name: pin.name,
      net: pin.net,
      pin_x: pin.x,
      pin_y: pin.y,
      pin_side: pin.side,
      pin_line_center_x: (pin.x + (pin.side === "right" ? tableBox.x + tableBox.width : tableBox.x)) / 2,
      pin_line_center_y: pin.y,
      pin_line_y: pin.y,
      label_policy: "pin_table_cell",
      expected_center_x: nameBox.x + nameBox.width / 2,
      expected_center_y: nameBox.y + nameBox.height / 2,
      unit: "mm"
    });
  });
}

function drawComponent(component) {
  const box = component.bbox_mm;
  const isModule = isPinTableComponent(component);
  const tableBox = isModule ? pinTableBox(component) : null;
  if (isModule) {
    drawPinTable(component, tableBox);
  } else {
    shape(
      `component.${component.ref}.bbox`,
      "",
      "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=none;strokeWidth=0;",
      box.x,
      box.y,
      box.width,
      box.height,
      "component",
      {
        role: "component_body",
        ref: component.ref,
        component_type: component.type,
        zone: component.zone,
        unit: "mm"
      }
    );
  }

  if (component.symbol === "resistor_horizontal") {
    const cy = component.pins[0].y;
    const x1 = component.pins[0].x;
    const x2 = component.pins[1].x;
    rect(`component.${component.ref}.symbol.resistor`, x1 + 8, cy - 3, x2 - x1 - 16, 6, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.left`, x1, cy, x1 + 8, cy, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.right`, x2 - 8, cy, x2, cy, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "resistor_vertical") {
    const cx = component.pins[0].x;
    const y1 = component.pins[0].y;
    const y2 = component.pins[1].y;
    rect(`component.${component.ref}.symbol.resistor`, cx - 3, y1 + 8, 6, y2 - y1 - 16, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.top`, cx, y1, cx, y1 + 8, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.bottom`, cx, y2 - 8, cx, y2, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "capacitor_vertical") {
    const cx = component.pins[0].x;
    const y1 = component.pins[0].y;
    const y2 = component.pins[1].y;
    line(`component.${component.ref}.symbol.top`, cx, y1, cx, y1 + 14, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.plate1`, cx - 5, y1 + 14, cx + 5, y1 + 14, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.plate2`, cx - 5, y1 + 18, cx + 5, y1 + 18, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.bottom`, cx, y1 + 18, cx, y2, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "capacitor_horizontal") {
    const y = component.pins[0].y;
    const x1 = component.pins[0].x;
    const x2 = component.pins[1].x;
    line(`component.${component.ref}.symbol.left`, x1, y, x1 + 20, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.plate1`, x1 + 20, y - 5, x1 + 20, y + 5, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.plate2`, x1 + 25, y - 5, x1 + 25, y + 5, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.right`, x1 + 25, y, x2, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "button_vertical") {
    const cx = component.pins[0].x;
    const y1 = component.pins[0].y;
    const y2 = component.pins[1].y;
    line(`component.${component.ref}.symbol.top`, cx, y1, cx, y1 + 12, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.bottom`, cx, y2 - 12, cx, y2, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.contact`, cx - 8, y1 + 29, cx + 8, y1 + 19, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "led_horizontal") {
    const y = component.pins[0].y;
    const x1 = component.pins[0].x;
    const x2 = component.pins[1].x;
    line(`component.${component.ref}.symbol.left`, x1, y, x1 + 10, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.tri1`, x1 + 10, y - 7, x1 + 10, y + 7, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.tri2`, x1 + 10, y - 7, x1 + 22, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.tri3`, x1 + 10, y + 7, x1 + 22, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.cathode`, x1 + 24, y - 7, x1 + 24, y + 7, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.right`, x1 + 24, y, x2, y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  } else if (component.symbol === "mosfet") {
    const g = component.pins.find((p) => p.number === "G");
    const d = component.pins.find((p) => p.number === "D");
    const s = component.pins.find((p) => p.number === "S");
    rect(`component.${component.ref}.symbol.channel`, box.x + 14, box.y + 12, 8, 30, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.gate`, g.x, g.y, box.x + 14, g.y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.drain`, d.x, d.y, d.x, box.y + 12, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
    line(`component.${component.ref}.symbol.source`, s.x, box.y + 42, s.x, s.y, 0.25, "symbol", { role: "component_symbol", ref: component.ref });
  }

  component.pins.forEach((pin) => drawPin(component, pin, tableBox || component.bbox_mm, !isModule));

  if (component.ref_text_bbox_mm) {
    const refBox = component.ref_text_bbox_mm;
    text(`component.${component.ref}.ref`, component.ref, refBox.x, refBox.y, refBox.width, refBox.height, 3.0, "center", "component-ref", {
      role: "component_ref",
      ref: component.ref,
      unit: "mm"
    });
  }
  if (component.value_text_bbox_mm) {
    const valueBox = component.value_text_bbox_mm;
    const value = component.ref === "DD1" ? "ESP32-WROOM-32" : component.ref === "A1" ? "DC/DC 12 V / 3.3 V" : component.type.split(",")[0].replace("Resistor ", "").replace("Capacitor ", "");
    text(`component.${component.ref}.value`, value, valueBox.x, valueBox.y, valueBox.width, valueBox.height, 2.5, "center", "component-value", {
      role: "component_value",
      ref: component.ref,
      unit: "mm"
    });
  }
}

function drawJunctions() {
  model.junctions.forEach((junction) => dot(`junction.${junction.id}`, junction.x, junction.y, junction.net));
}

function drawNetLabels() {
  model.net_labels.forEach((label) => {
    const b = label.bbox_mm;
    text(`netlabel.${label.id}`, label.text, b.x, b.y, b.width, b.height, 2.5, "center", "net-label", {
      role: "net_label",
      net: label.net,
      anchor_x: label.anchor.x,
      anchor_y: label.anchor.y,
      unit: "mm"
    });
  });
}

function drawWires() {
  model.wires.forEach((wire) => {
    for (let i = 0; i < wire.points.length - 1; i += 1) {
      const [x1, y1] = wire.points[i];
      const [x2, y2] = wire.points[i + 1];
      line(`wire.${wire.net}.${wire.id}.${String(i + 1).padStart(3, "0")}`, x1, y1, x2, y2, 0.25, "wire", {
        role: "wire",
        wire_id: wire.id,
        net: wire.net,
        unit: "mm"
      });
    }
  });
}

function drawSchematic() {
  model.components.forEach(drawComponent);
  drawWires();
  drawJunctions();
  drawNetLabels();
}

function build() {
  drawFrame();
  drawTitleBlock();
  drawListOfElements();
  drawSchematic();
  return `<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" modified="2026-05-20T00:00:00.000Z" agent="Codex" version="24.7.17" type="device">
  <diagram id="esp32-temperature-node" name="A1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="1" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="${model.page.width_mm}" pageHeight="${model.page.height_mm}" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        ${cells.join("\n        ")}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
`;
}

fs.writeFileSync(OUT, build(), "utf8");
console.log(`Wrote ${OUT}`);
