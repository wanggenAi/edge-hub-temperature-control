#!/usr/bin/env python3
"""Generate clean vector poster-support SVG assets.

The assets are deliberately composed as readable poster panels, not flowcharts:
large hierarchy, few connectors, and stable grids that remain legible when
placed on an A1 layout.
"""

from __future__ import annotations

from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
FONT = "Inter, Arial, sans-serif"


def svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        "<defs>",
        '<linearGradient id="panelBg" x1="0" y1="0" x2="1" y2="1">',
        '<stop offset="0%" stop-color="#0b2032"/>',
        '<stop offset="100%" stop-color="#102b3f"/>',
        "</linearGradient>",
        '<linearGradient id="softBlue" x1="0" y1="0" x2="1" y2="0">',
        '<stop offset="0%" stop-color="#5ef2ff"/>',
        '<stop offset="100%" stop-color="#7da7ff"/>',
        "</linearGradient>",
        '<linearGradient id="softGreen" x1="0" y1="0" x2="1" y2="0">',
        '<stop offset="0%" stop-color="#6df0c2"/>',
        '<stop offset="100%" stop-color="#c6f36b"/>',
        "</linearGradient>",
        '<linearGradient id="softWarm" x1="0" y1="0" x2="1" y2="0">',
        '<stop offset="0%" stop-color="#ffd166"/>',
        '<stop offset="100%" stop-color="#ff8f70"/>',
        "</linearGradient>",
        '<filter id="panelShadow" x="-10%" y="-10%" width="120%" height="120%">',
        '<feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#03101a" flood-opacity="0.32"/>',
        "</filter>",
        "</defs>",
    ]


def text(x: int | float, y: int | float, value: str, *, size: int = 18, color: str = "#d8e8f2", weight: int = 400, anchor: str = "start") -> str:
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{FONT}" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}">{escape(value)}</text>'
    )


def multi_text(
    x: int | float,
    y: int | float,
    rows: list[str],
    *,
    size: int = 18,
    color: str = "#d8e8f2",
    weight: int = 400,
    anchor: str = "start",
    line_gap: int = 25,
) -> list[str]:
    return [
        text(x, y + idx * line_gap, row, size=size, color=color, weight=weight, anchor=anchor)
        for idx, row in enumerate(rows)
    ]


def pill(x: int, y: int, w: int, label: str, color: str) -> list[str]:
    return [
        f'<rect x="{x}" y="{y}" width="{w}" height="44" rx="22" fill="{color}" fill-opacity="0.13" stroke="{color}" stroke-width="2"/>',
        text(x + w / 2, y + 29, label, size=17, color="#f5fbff", weight=700, anchor="middle"),
    ]


def status_tile(x: int, y: int, w: int, title: str, value: str, color: str) -> list[str]:
    return [
        f'<rect x="{x}" y="{y}" width="{w}" height="70" rx="18" fill="#071723" stroke="{color}" stroke-width="2"/>',
        f'<circle cx="{x + 34}" cy="{y + 35}" r="11" fill="{color}" fill-opacity="0.2" stroke="{color}" stroke-width="2"/>',
        f'<circle cx="{x + 34}" cy="{y + 35}" r="5" fill="{color}"/>',
        text(x + 58, y + 30, title, size=16, color="#bdd2df", weight=700),
        text(x + 58, y + 54, value, size=19, color="#f6fbff", weight=800),
    ]


def module_card(x: int, y: int, w: int, h: int, title: str, lines: list[str], color: str) -> list[str]:
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#0e2638" stroke="{color}" stroke-width="2"/>',
        f'<rect x="{x + 18}" y="{y + 18}" width="42" height="42" rx="12" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="2"/>',
        f'<circle cx="{x + 39}" cy="{y + 39}" r="8" fill="{color}"/>',
        text(x + 74, y + 45, title, size=22, color="#f6fbff", weight=700),
    ]
    out += multi_text(x + 24, y + 88, lines, size=16, color="#bdd2df", line_gap=24)
    return out


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_data_hub() -> str:
    w, h = 1600, 920
    lines = svg_header(w, h, "Data-Hub vector cluster")
    lines += [
        '<rect width="1600" height="920" fill="none"/>',
        '<g filter="url(#panelShadow)">',
        '<rect x="58" y="56" width="1484" height="808" rx="30" fill="url(#panelBg)" stroke="#2b526d" stroke-width="2"/>',
        text(118, 126, "Data-Hub Runtime Cluster", size=38, color="#f6fbff", weight=800),
        text(118, 166, "MQTT ingress, Java Reactor pipelines,", size=21, color="#bdd2df"),
        text(118, 196, "backpressure, persistence, and visibility.", size=21, color="#bdd2df"),
        '<rect x="118" y="226" width="1364" height="92" rx="24" fill="#071723" stroke="#2b526d" stroke-width="2"/>',
        '<path d="M800 318 V354" stroke="#4d7188" stroke-width="3" stroke-linecap="round" opacity="0.62"/>',
        '<rect x="570" y="354" width="460" height="278" rx="34" fill="#071723" stroke="#5ef2ff" stroke-width="3"/>',
        '<path d="M670 446 h260 a76 76 0 0 1 0 152 H668 a82 82 0 0 1-12-162 a96 96 0 0 1 14 10Z" fill="#102b3d" stroke="url(#softBlue)" stroke-width="4"/>',
        text(800, 503, "DATA-HUB", size=38, color="#ffffff", weight=800, anchor="middle"),
        text(800, 544, "runtime coordination center", size=21, color="#bfe8f5", weight=700, anchor="middle"),
        text(800, 576, "fan-in, buffering, persistence", size=18, color="#bdd2df", anchor="middle"),
        '<path d="M518 403 C542 420, 554 444, 570 482" stroke="#5ef2ff" stroke-width="3" fill="none" opacity="0.62"/>',
        '<path d="M1082 403 C1058 420, 1046 444, 1030 482" stroke="#6df0c2" stroke-width="3" fill="none" opacity="0.62"/>',
        '<path d="M518 620 C548 600, 558 578, 570 536" stroke="#7da7ff" stroke-width="3" fill="none" opacity="0.62"/>',
        '<path d="M1082 620 C1052 600, 1042 578, 1030 536" stroke="#ffd166" stroke-width="3" fill="none" opacity="0.62"/>',
    ]
    lines += status_tile(150, 237, 392, "Device Status", "online state + heartbeat", "#ff9c7a")
    lines += status_tile(604, 237, 392, "Runtime Metrics", "TPS, queue depth, drops", "#c8a4ff")
    lines += status_tile(1058, 237, 392, "Contract Health", "schema checks + ACK trace", "#6df0c2")
    cards = [
        (126, 350, "MQTT Broker", ["telemetry topics", "params/set + params/ack"], "#5ef2ff"),
        (1084, 350, "Java Reactor Ingestion", ["reactive streams", "backpressure-aware"], "#6df0c2"),
        (126, 580, "Backpressure Buffer", ["bounded queues", "drop reason counters"], "#7da7ff"),
        (1084, 580, "TDengine Storage", ["time-series history", "validation windows"], "#ffd166"),
    ]
    for x, y, title, rows, color in cards:
        lines += module_card(x, y, 392, 160, title, rows, color)
    lines += [
        '<rect x="120" y="786" width="1360" height="36" rx="18" fill="#071723" stroke="#2b526d" stroke-width="1"/>',
        text(800, 810, "Telemetry in | command acknowledgements out | status and metrics stay observable", size=18, color="#d8e8f2", weight=700, anchor="middle"),
        "</g>",
        "</svg>",
    ]
    return "\n".join(lines)


def build_hmi_layer() -> str:
    w, h = 1600, 920
    lines = svg_header(w, h, "HMI layer frame")
    lines += [
        '<rect width="1600" height="920" fill="none"/>',
        '<g filter="url(#panelShadow)">',
        '<rect x="58" y="56" width="1484" height="808" rx="30" fill="url(#panelBg)" stroke="#2b526d" stroke-width="2"/>',
        text(118, 126, "HMI Operation Layer", size=38, color="#f6fbff", weight=800),
        text(118, 166, "FastAPI backend, React dashboard,", size=21, color="#bdd2df"),
        text(118, 196, "PostgreSQL control plane, MQTT publish.", size=21, color="#bdd2df"),
        '<rect x="128" y="234" width="872" height="500" rx="26" fill="#050d15" stroke="#5ef2ff" stroke-width="4"/>',
        '<rect x="164" y="280" width="800" height="394" rx="12" fill="#0b1c2c" stroke="#223f56" stroke-width="2"/>',
        '<rect x="164" y="280" width="800" height="52" rx="12" fill="#102f43"/>',
        text(196, 314, "Device Detail / AI Recommendation / Ops Console", size=20, color="#effcff", weight=700),
        '<rect x="198" y="372" width="360" height="210" rx="14" fill="#112c40" stroke="#5ef2ff" stroke-width="2"/>',
        '<path d="M226 532 C270 472, 318 456, 368 492 S464 548, 526 420" stroke="#5ef2ff" stroke-width="5" fill="none"/>',
        '<path d="M226 542 C284 520, 338 516, 394 526 S474 548, 526 502" stroke="#6df0c2" stroke-width="4" fill="none"/>',
        text(234, 406, "Temperature Trend", size=18, color="#effcff", weight=700),
        '<rect x="600" y="372" width="330" height="92" rx="14" fill="#112c40" stroke="#6df0c2" stroke-width="2"/>',
        text(626, 410, "Parameter Apply", size=18, color="#effcff", weight=700),
        text(626, 438, "review -> confirm -> ACK", size=16, color="#bcd2df"),
        '<rect x="600" y="490" width="330" height="92" rx="14" fill="#112c40" stroke="#ffd166" stroke-width="2"/>',
        text(626, 528, "AI Validation", size=18, color="#effcff", weight=700),
        text(626, 556, "preview vs actual effect", size=16, color="#bcd2df"),
        '<rect x="470" y="734" width="190" height="32" rx="16" fill="#132e43" stroke="#2b526d"/>',
        '<rect x="524" y="766" width="82" height="18" rx="9" fill="#132e43" stroke="#2b526d"/>',
    ]
    right_cards = [
        (1060, 246, "FastAPI Backend", ["Auth, devices, params", "AI validation APIs"], "#5ef2ff"),
        (1060, 416, "React Frontend", ["Operator dashboard", "Real screenshots fit here"], "#6df0c2"),
        (1060, 586, "Control Plane", ["PostgreSQL records", "MQTT publish path"], "#ffd166"),
    ]
    for card in right_cards:
        lines += module_card(*card[:2], 390, 132, card[2], card[3], card[4])
    lines += [
        '<rect x="118" y="792" width="1364" height="34" rx="17" fill="#071723" stroke="#2b526d" stroke-width="1"/>',
        text(800, 816, "The final poster places real HMI PNG screenshots inside this monitor/tablet visual language.", size=18, color="#d8e8f2", weight=700, anchor="middle"),
        "</g>",
        "</svg>",
    ]
    return "\n".join(lines)


def build_ai_decision() -> str:
    w, h = 1600, 920
    lines = svg_header(w, h, "AI-assisted decision panel")
    lines += [
        '<rect width="1600" height="920" fill="none"/>',
        '<g filter="url(#panelShadow)">',
        '<rect x="58" y="56" width="1484" height="808" rx="30" fill="url(#panelBg)" stroke="#2b526d" stroke-width="2"/>',
        text(118, 126, "AI-Assisted PID Decision", size=38, color="#f6fbff", weight=800),
        text(118, 166, "Classify behavior, recommend PID changes,", size=21, color="#bdd2df"),
        text(118, 196, "preview impact, then validate ACK.", size=21, color="#bdd2df"),
        '<rect x="118" y="230" width="440" height="500" rx="26" fill="#071723" stroke="#5ef2ff" stroke-width="3"/>',
        '<rect x="236" y="302" width="204" height="176" rx="28" fill="#102b3d" stroke="#5ef2ff" stroke-width="3"/>',
        '<rect x="282" y="346" width="112" height="88" rx="18" fill="#071723" stroke="#6df0c2" stroke-width="3"/>',
        '<path d="M236 348 H190 M236 390 H190 M236 432 H190 M440 348 H486 M440 390 H486 M440 432 H486" stroke="#5ef2ff" stroke-width="3"/>',
        '<path d="M292 390 h92 M338 356 v68" stroke="#6df0c2" stroke-width="5" stroke-linecap="round"/>',
        text(338, 540, "Decision Assistant", size=28, color="#f6fbff", weight=800, anchor="middle"),
        text(338, 578, "human-confirmed PID optimization", size=18, color="#bdd2df", weight=600, anchor="middle"),
    ]
    lines += pill(174, 630, 142, "Telemetry", "#5ef2ff")
    lines += pill(336, 630, 132, "History", "#6df0c2")
    lines += [
        '<rect x="606" y="230" width="876" height="262" rx="26" fill="#071723" stroke="#2b526d" stroke-width="2"/>',
        text(650, 282, "Before / After Temperature Response", size=25, color="#f6fbff", weight=800),
        '<line x1="662" y1="426" x2="1414" y2="426" stroke="#4b6578" stroke-width="2" stroke-dasharray="9 9"/>',
        '<path d="M662 422 C720 318, 786 304, 850 376 S964 470, 1048 340 S1214 306, 1414 364" stroke="#ff9c7a" stroke-width="6" fill="none"/>',
        '<path d="M662 422 C730 392, 798 384, 870 404 S1010 438, 1110 412 S1286 392, 1414 406" stroke="#6df0c2" stroke-width="6" fill="none"/>',
        text(1348, 354, "before", size=17, color="#ffb29c", weight=700),
        text(1348, 404, "after", size=17, color="#9ef4cf", weight=700),
        '<rect x="606" y="530" width="876" height="220" rx="26" fill="#071723" stroke="#2b526d" stroke-width="2"/>',
        text(650, 568, "Decision Capabilities", size=22, color="#f6fbff", weight=800),
    ]
    capability_cards = [
        (640, 592, "Feature Extraction", "windowed stats", "#5ef2ff"),
        (850, 592, "Problem Class", "oscillation / error", "#c8a4ff"),
        (1060, 592, "PID Recommendation", "Kp Ki Kd delta", "#ffd166"),
        (1270, 592, "Preview Simulation", "expected effect", "#ff9c7a"),
        (850, 678, "Operator Apply", "human confirmation", "#7da7ff"),
        (1060, 678, "ACK Validation", "post-apply check", "#6df0c2"),
    ]
    for x, y, title, subtitle, color in capability_cards:
        lines += [
            f'<rect x="{x}" y="{y}" width="168" height="62" rx="16" fill="#102b3d" stroke="{color}" stroke-width="2"/>',
            text(x + 84, y + 26, title, size=14, color="#f6fbff", weight=800, anchor="middle"),
            text(x + 84, y + 48, subtitle, size=12, color="#bdd2df", anchor="middle"),
        ]
    lines += [
        '<rect x="118" y="772" width="1364" height="36" rx="18" fill="#071723" stroke="#2b526d" stroke-width="1"/>',
        text(800, 797, "Telemetry History | Features | Recommendation | Preview | Operator Apply | ACK Validation", size=18, color="#d8e8f2", weight=700, anchor="middle"),
        "</g>",
        "</svg>",
    ]
    return "\n".join(lines)


def build_key_contributions() -> str:
    w, h = 1600, 320
    lines = svg_header(w, h, "Key contributions")
    lines += [
        '<rect width="1600" height="320" fill="none"/>',
        '<g filter="url(#panelShadow)">',
        '<rect x="34" y="36" width="1532" height="248" rx="28" fill="url(#panelBg)" stroke="#2b526d" stroke-width="2"/>',
        text(80, 94, "Key Contributions", size=30, color="#f6fbff", weight=800),
    ]
    items = [
        ("01", "Edge closed-loop", "temperature control", "#5ef2ff"),
        ("02", "MQTT runtime", "telemetry + commands", "#6df0c2"),
        ("03", "Data-Hub", "time-series persistence", "#7da7ff"),
        ("04", "HMI workflow", "operate + apply params", "#ffd166"),
        ("05", "AI PID assist", "recommend + validate", "#c8a4ff"),
    ]
    x = 80
    for number, title, subtitle, color in items:
        lines += [
            f'<rect x="{x}" y="124" width="276" height="112" rx="18" fill="#071723" stroke="{color}" stroke-width="2"/>',
            f'<circle cx="{x + 42}" cy="180" r="24" fill="{color}" fill-opacity="0.16" stroke="{color}" stroke-width="2"/>',
            text(x + 42, 188, number, size=18, color="#ffffff", weight=800, anchor="middle"),
            text(x + 82, 168, title, size=20, color="#f6fbff", weight=800),
            text(x + 82, 202, subtitle, size=16, color="#bdd2df", weight=600),
        ]
        x += 292
    lines += ["</g>", "</svg>"]
    return "\n".join(lines)


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    write(ASSET_DIR / "data-hub.svg", build_data_hub())
    write(ASSET_DIR / "hmi-layer.svg", build_hmi_layer())
    write(ASSET_DIR / "ai-decision.svg", build_ai_decision())
    write(ASSET_DIR / "key-contributions.svg", build_key_contributions())
    print("Vector assets written to", ASSET_DIR)


if __name__ == "__main__":
    main()
