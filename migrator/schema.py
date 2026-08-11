"""
Формат "Транспортної схеми" (Transfer Schema) - YAML-файл на кожне завдання
переносу (Справочник/Документ), що описує:

  - джерело (SourceSpec) і приймач (DestinationSpec) - ЯК підключатись;
  - select_mode - чи брати ВСІ поля джерела ("all", безпечний дефолт) чи
    ЛИШЕ перелічені у field_mappings ("explicit");
  - field_mappings - "Схема 1 <-> Схема 2" за СТАБІЛЬНИМ внутрішнім id:
    для кожного цікавого поля - його ім'я у джерелі, ім'я у приймачі (може
    відрізнятись) і людський опис. Не обов'язково перелічувати ВСІ поля
    довідника/документа - лише ті, що варто задокументувати, перейменувати
    чи на які згодом навішується хук; решта завжди переноситься 1:1, поки
    select_mode="all". (Свідоме спрощення просимо в юзера моделі "Схема 1 /
    Схема 2 / Схема переносу" як трьох окремих паралельних списків - для
    even case, коли обидві бази - той самий BAF-конфіг, тримати три списки
    синхронними за id було б чистим накладним обов'язком без користі.)
  - related_catalogs - каскадні правила для пов'язаних довідників
    (за типом посилання __ref_type__, що трапляється у вибраних рядках);
  - hooks - точки розширення пайплайна (before_read/before_write/
    after_each_item/after_write), кожна - зареєстроване ім'я з migrator.hooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceSpec:
    connection: str  # "com" - джерело читається лише через COM (com_query.ps1)
    connection_string: str | None = None


@dataclass
class DestinationSpec:
    connection: str  # "bridge" - приймач пишеться лише через BridgeTool
    platform_exe: str | None = None
    connect_args: list[str] = field(default_factory=list)


@dataclass
class FieldMapping:
    id: str
    source_field: str
    destination_field: str
    description: str = ""


@dataclass
class RelatedCatalogRule:
    ref_type: str  # напр. "Справочник.ВидыЦен"
    detail: str = "reference_only"  # "reference_only" | "full"
    depth: int = 1
    description: str = ""

    def __post_init__(self):
        if self.detail not in ("reference_only", "full"):
            raise ValueError(f"related_catalogs[{self.ref_type}]: invalid detail={self.detail!r}")


@dataclass
class TabularPartSpec:
    name: str
    description: str = ""


@dataclass
class HookSpec:
    stage: str  # "before_read" | "before_write" | "after_each_item" | "after_write"
    name: str
    args: dict = field(default_factory=dict)

    VALID_STAGES = ("before_read", "before_write", "after_each_item", "after_write")

    def __post_init__(self):
        if self.stage not in self.VALID_STAGES:
            raise ValueError(f"hooks: invalid stage={self.stage!r} (must be one of {self.VALID_STAGES})")


@dataclass
class TransferSchema:
    task: str
    kind: str  # "Справочник" | "Документ"
    name: str
    source: SourceSpec
    destination: DestinationSpec
    schema_version: int = 1
    description: str = ""
    select_mode: str = "all"  # "all" -> SELECT *; "explicit" -> лише field_mappings
    field_mappings: list[FieldMapping] = field(default_factory=list)
    related_catalogs: list[RelatedCatalogRule] = field(default_factory=list)
    tabular_parts: list[TabularPartSpec] = field(default_factory=list)
    hooks: list[HookSpec] = field(default_factory=list)
    path: Path | None = None

    # Атрибути, без яких ЗаписатиЕлементи не може коректно розібрати
    # ієрархію/предопределені елементи - завжди додаються до explicit-
    # переліку колонок, навіть якщо їх не було у field_mappings.
    _REQUIRED_FIELDS = {
        "Справочник": ["Ссылка", "ЭтоГруппа", "Родитель", "Предопределенный", "ИмяПредопределенныхДанных"],
        "Документ": ["Ссылка", "Дата", "Номер"],
    }

    def hooks_for(self, stage: str) -> list[HookSpec]:
        return [h for h in self.hooks if h.stage == stage]

    def select_query(self, limit: int | None = None) -> str:
        top = f"ПЕРВЫЕ {limit} " if limit else ""
        object_ref = f"{self.kind}.{self.name}"

        if self.select_mode == "all" or not self.field_mappings:
            return f"ВЫБРАТЬ {top}* ИЗ {object_ref}"

        if self.select_mode != "explicit":
            raise ValueError(f"{self.task}: invalid select_mode={self.select_mode!r}")

        columns = list(self._REQUIRED_FIELDS.get(self.kind, ["Ссылка"]))
        for mapping in self.field_mappings:
            if mapping.source_field in columns:
                continue
            if mapping.source_field == mapping.destination_field:
                columns.append(mapping.source_field)
            else:
                columns.append(f"{mapping.source_field} КАК {mapping.destination_field}")
        return f"ВЫБРАТЬ {top}{', '.join(columns)} ИЗ {object_ref}"


def load_schema(path: str | Path) -> TransferSchema:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    source = SourceSpec(**raw["source"])
    destination = DestinationSpec(**raw["destination"])
    field_mappings = [FieldMapping(**m) for m in raw.get("field_mappings", [])]
    related_catalogs = [RelatedCatalogRule(**r) for r in raw.get("related_catalogs", [])]
    tabular_parts = [TabularPartSpec(**t) for t in raw.get("tabular_parts", [])]
    hooks = [HookSpec(**h) for h in raw.get("hooks", [])]

    return TransferSchema(
        task=raw["task"],
        kind=raw["kind"],
        name=raw["name"],
        source=source,
        destination=destination,
        schema_version=raw.get("schema_version", 1),
        description=raw.get("description", ""),
        select_mode=raw.get("select_mode", "all"),
        field_mappings=field_mappings,
        related_catalogs=related_catalogs,
        tabular_parts=tabular_parts,
        hooks=hooks,
        path=path,
    )
