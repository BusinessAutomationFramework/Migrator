"""
Пише поточну версію Migrator (VERSION у корені репозиторію) у всі місця,
де вона задубльована як текст, щоб їх не редагувати вручну і не пропустити
жодне при черговому бампі версії:

  - BridgeTool.xml       <Comment>Migrator BridgeTool build X</Comment>
  - ObjectModule.bsl     Функция ВерсіяBridgeTool() Экспорт ... Возврат "X";

Запускати ПІСЛЯ зміни VERSION і ПЕРЕД перезбіркою BridgeTool.epf:

    python BridgeTool/scripts/stamp_version.py
"""

import re
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = TOOL_DIR.parent

BRIDGETOOL_XML = TOOL_DIR / "BridgeTool.xml"
OBJECT_MODULE_BSL = TOOL_DIR / "BridgeTool" / "Ext" / "ObjectModule.bsl"


def stamp(version: str) -> None:
    xml_text = BRIDGETOOL_XML.read_text(encoding="utf-8")
    xml_text, n = re.subn(
        r"<Comment>Migrator BridgeTool build [^<]*</Comment>",
        f"<Comment>Migrator BridgeTool build {version}</Comment>",
        xml_text,
    )
    if n != 1:
        raise RuntimeError(f"Очікував рівно 1 заміну <Comment> у {BRIDGETOOL_XML}, знайдено {n}")
    BRIDGETOOL_XML.write_text(xml_text, encoding="utf-8")

    bsl_text = OBJECT_MODULE_BSL.read_text(encoding="utf-8-sig")
    bsl_text, n = re.subn(
        r'(Функция ВерсіяBridgeTool\(\) Экспорт\s*\n\s*Возврат ")[^"]*(";)',
        rf"\g<1>{version}\g<2>",
        bsl_text,
    )
    if n != 1:
        raise RuntimeError(f"Очікував рівно 1 заміну ВерсіяBridgeTool() у {OBJECT_MODULE_BSL}, знайдено {n}")
    OBJECT_MODULE_BSL.write_text(bsl_text, encoding="utf-8-sig")

    print(f"Stamped version {version} into {BRIDGETOOL_XML.name} and {OBJECT_MODULE_BSL.name}.")


if __name__ == "__main__":
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    stamp(version)
