"""
Планувальник каскадного переносу пов'язаних довідників (related_catalogs).

Спрощення, свідомо прийняте для першої версії: "reference_only" переносить
ВЕСЬ пов'язаний довідник (SELECT *), а не лише ті UUID, що реально
трапились у вибірці. Ці довідники (Види цін, Структура підприємства,
Календарі, БізнесРегіони тощо) - як правило, невеликі довідники-переліки;
параметризований запит "Ссылка В (&Список)" через com_query.ps1 додав би
реальну складність (передача масиву параметрів через COM) заради економії,
яка на такому масштабі не виправдана - і "зайві" елементи цього ж
довідника-приймача однаково потрібні для повноти даних.
"""

from __future__ import annotations

from migrator.schema import RelatedCatalogRule


def find_related_ref_types(rows: list[dict]) -> set[str]:
    """Усі __ref_type__, що реально трапляються у вибраних рядках (включно
    з табличними частинами, коли вони зʼявляться) - для /suggest."""
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            ref_type = value.get("__ref_type__")
            if ref_type:
                found.add(ref_type)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for row in rows:
        walk(row)
    return found


def plan_cascade(rows: list[dict], rules: list[RelatedCatalogRule]) -> list[RelatedCatalogRule]:
    """Які з налаштованих правил каскадування реально спрацьовують для цієї
    вибірки (їх __ref_type__ дійсно трапився хоча б раз)."""
    present = find_related_ref_types(rows)
    return [rule for rule in rules if rule.ref_type in present]
