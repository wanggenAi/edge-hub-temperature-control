#!/usr/bin/env python3
"""Convert thesis references to a BrSTU/GOST-like bibliography style.

The script edits only the REFERENCES paragraphs in the DOCX package. It keeps
the existing numbering and citation order unchanged.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


REFERENCES = [
    "[1] Astrom K. J. Feedback Systems: An Introduction for Scientists and Engineers / K. J. Astrom, R. M. Murray. – Princeton: Princeton University Press, 2008. – 408 p.",
    "[2] MQTT Version 5.0 [Electronic resource] / OASIS. – OASIS Standard, 07 March 2019. – Mode of access: https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html. – Date of access: 15.05.2026.",
    "[3] ESP32-WROOM-32 Datasheet [Electronic resource] / Espressif Systems. – Version 3.6. – Mode of access: https://documentation.espressif.com/esp32-wroom-32_datasheet_en.pdf. – Date of access: 15.05.2026.",
    "[4] DS18B20 Programmable Resolution 1-Wire Digital Thermometer Data Sheet [Electronic resource] / Analog Devices. – Rev. 6. – Mode of access: https://www.analog.com/en/products/DS18B20.html. – Date of access: 15.05.2026.",
    "[5] Spring Boot Reference Documentation [Electronic resource] / Spring. – Mode of access: https://docs.spring.io/spring-boot/reference/index.html. – Date of access: 15.05.2026.",
    "[6] Reactor Reference Guide [Electronic resource] / Project Reactor. – Mode of access: https://projectreactor.io/docs/core/release/reference/. – Date of access: 15.05.2026.",
    "[7] TDengine Documentation [Electronic resource] / TDengine. – Mode of access: https://docs.tdengine.com/. – Date of access: 15.05.2026.",
    "[8] FastAPI Documentation [Electronic resource] / FastAPI. – Mode of access: https://fastapi.tiangolo.com/. – Date of access: 15.05.2026.",
    "[9] React Reference Overview [Electronic resource] / React. – Mode of access: https://react.dev/reference/react. – Date of access: 15.05.2026.",
    "[10] Docker Compose Documentation [Electronic resource] / Docker. – Mode of access: https://docs.docker.com/compose/. – Date of access: 15.05.2026.",
    "[11] Wokwi Documentation [Electronic resource] / Wokwi. – Mode of access: https://docs.wokwi.com/. – Date of access: 15.05.2026.",
    "[12] PostgreSQL Documentation [Electronic resource] / PostgreSQL Global Development Group. – Mode of access: https://www.postgresql.org/docs/. – Date of access: 15.05.2026.",
    "[13] ISO/IEC/IEEE 29148:2018. Systems and software engineering. Life cycle processes. Requirements engineering. – Geneva: ISO, 2018.",
    "[14] Astrom K. J. PID Controllers: Theory, Design, and Tuning / K. J. Astrom, T. Hagglund. – 2nd ed. – Research Triangle Park: Instrument Society of America, 1995. – 343 p.",
    "[15] ESP-IDF Programming Guide for ESP32 [Electronic resource] / Espressif Systems. – Mode of access: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/. – Date of access: 15.05.2026.",
    "[16] PlatformIO Documentation [Electronic resource] / PlatformIO. – Mode of access: https://docs.platformio.org/. – Date of access: 15.05.2026.",
    "[17] Eclipse Mosquitto Documentation [Electronic resource] / Eclipse Foundation. – Mode of access: https://mosquitto.org/documentation/. – Date of access: 15.05.2026.",
    "[18] HiveMQ MQTT Client Documentation [Electronic resource] / HiveMQ. – Mode of access: https://hivemq.github.io/hivemq-mqtt-client/. – Date of access: 15.05.2026.",
    "[19] Redis Documentation [Electronic resource] / Redis. – Mode of access: https://redis.io/docs/latest/. – Date of access: 15.05.2026.",
    "[20] SQLAlchemy 2.0 Documentation [Electronic resource] / SQLAlchemy. – Mode of access: https://docs.sqlalchemy.org/en/20/. – Date of access: 15.05.2026.",
    "[21] Alembic Documentation [Electronic resource] / Alembic. – Mode of access: https://alembic.sqlalchemy.org/. – Date of access: 15.05.2026.",
    "[22] Pydantic Documentation [Electronic resource] / Pydantic. – Mode of access: https://docs.pydantic.dev/. – Date of access: 15.05.2026.",
    "[23] Vite Guide [Electronic resource] / Vite. – Mode of access: https://vite.dev/guide/. – Date of access: 15.05.2026.",
    "[24] Tailwind CSS Documentation [Electronic resource] / Tailwind Labs. – Mode of access: https://tailwindcss.com/docs. – Date of access: 15.05.2026.",
    "[25] Arduino Documentation [Electronic resource] / Arduino. – Mode of access: https://docs.arduino.cc/. – Date of access: 15.05.2026.",
    "[26] OneWire Library [Electronic resource] / P. Stoffregen. – Mode of access: https://www.pjrc.com/teensy/td_libs_OneWire.html. – Date of access: 15.05.2026.",
    "[27] DallasTemperature Library Documentation [Electronic resource] / M. Burton. – Mode of access: https://github.com/milesburton/Arduino-Temperature-Control-Library. – Date of access: 15.05.2026.",
    "[28] Paho MQTT Python Client Documentation [Electronic resource] / Eclipse Foundation. – Mode of access: https://eclipse.dev/paho/files/paho.mqtt.python/html/. – Date of access: 15.05.2026.",
    "[29] Micrometer Documentation [Electronic resource] / Micrometer. – Mode of access: https://docs.micrometer.io/micrometer/reference/. – Date of access: 15.05.2026.",
    "[30] scikit-learn User Guide [Electronic resource] / scikit-learn. – Mode of access: https://scikit-learn.org/stable/user_guide.html. – Date of access: 15.05.2026.",
]


def paragraph_text(paragraph: etree._Element) -> str:
    return "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))


def replace_paragraph_text(paragraph: etree._Element, text: str) -> None:
    runs = paragraph.xpath("./w:r", namespaces=NS)
    if not runs:
        raise RuntimeError("Cannot replace paragraph without runs")

    first_text = runs[0].find(".//w:t", namespaces=NS)
    if first_text is None:
        first_text = etree.SubElement(runs[0], f"{{{NS['w']}}}t")
    first_text.text = text

    for run in runs[1:]:
        paragraph.remove(run)


def apply_references(src: Path, dst: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        with zipfile.ZipFile(src) as zin:
            zin.extractall(tmpdir)

        doc_path = tmpdir / "word" / "document.xml"
        root = etree.fromstring(doc_path.read_bytes())
        paragraphs = root.xpath("//w:body/w:p", namespaces=NS)

        ref_heading_idx = None
        for index, paragraph in enumerate(paragraphs):
            if paragraph_text(paragraph).strip() == "REFERENCES":
                ref_heading_idx = index
                break
        if ref_heading_idx is None:
            raise RuntimeError("REFERENCES heading not found")

        replaced = 0
        for paragraph in paragraphs[ref_heading_idx + 1 :]:
            text = paragraph_text(paragraph).strip()
            if not text:
                continue
            if text.startswith("[") and "]" in text:
                if replaced >= len(REFERENCES):
                    raise RuntimeError("More reference paragraphs found than expected")
                replace_paragraph_text(paragraph, REFERENCES[replaced])
                replaced += 1
                continue
            if replaced:
                break

        if replaced != len(REFERENCES):
            raise RuntimeError(f"Expected {len(REFERENCES)} references, replaced {replaced}")

        doc_path.write_bytes(
            etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone="yes")
        )

        if dst.exists():
            dst.unlink()
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for path in tmpdir.rglob("*"):
                if path.is_file():
                    zout.write(path, path.relative_to(tmpdir).as_posix())


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: apply_gost_references.py INPUT.docx OUTPUT.docx", file=sys.stderr)
        return 2

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if not src.exists():
        print(f"Input file does not exist: {src}", file=sys.stderr)
        return 2

    if src.resolve() == dst.resolve():
        backup = src.with_suffix(".before_gost_references.docx")
        shutil.copy2(src, backup)

    apply_references(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
