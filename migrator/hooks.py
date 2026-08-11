"""
Реєстр операцій пайплайна (хуків), які можна навісити на схему переносу за
іменем у field "hooks" (schema.py: HookSpec). Кожен хук - звичайна функція
(ctx, **args) -> None, ctx - engine.TransferContext поточного запуску.
Стадії: before_read, before_write, after_each_item, after_write
(engine.py викликає run() у кожній з цих точок).
"""

_REGISTRY: dict[str, callable] = {}


def register(name: str):
    def decorator(fn):
        _REGISTRY[name] = fn
        return fn
    return decorator


def get(name: str):
    if name not in _REGISTRY:
        raise KeyError(f"Хук '{name}' не зареєстровано (доступні: {', '.join(sorted(_REGISTRY)) or '(жодного)'})")
    return _REGISTRY[name]


def run(stage: str, ctx, hook_specs) -> None:
    for spec in hook_specs:
        if spec.stage != stage:
            continue
        get(spec.name)(ctx, **spec.args)


@register("require_fields")
def require_fields(ctx, fields: list[str]) -> None:
    """before_write: попереджає (не блокує запис) про рядки з порожнім
    обов'язковим полем - не блокуємо перенос, бо джерело може містити
    легітимно неповні старі записи, але оператору варто про це знати."""
    for row in ctx.rows:
        ref = row.get("Ссылка")
        row_id = ref.get("__ref_uuid__") if isinstance(ref, dict) else "?"
        for field_name in fields:
            value = row.get(field_name)
            if value in (None, ""):
                ctx.log(f"ПОПЕРЕДЖЕННЯ: {row_id} - порожнє обов'язкове поле '{field_name}'")


@register("log_progress")
def log_progress(ctx) -> None:
    """after_each_item: викликається ЛИШЕ якщо цей хук заявлено у схемі -
    інакше рушій пише всю пачку одним запитом до BridgeTool (швидше).
    Читає ctx.item/ctx.index/ctx.total, що engine.py виставляє ПЕРЕД
    кожним викликом (це рантайм-стан ітерації, не YAML-аргумент хука)."""
    ref = ctx.item.get("Ссылка")
    row_id = ref.get("__ref_uuid__") if isinstance(ref, dict) else "?"
    ctx.log(f"[{ctx.index}/{ctx.total}] {row_id}")


@register("print_summary")
def print_summary(ctx) -> None:
    """after_write: підсумок запису (перший рядок відповіді BridgeTool).
    Читає ctx.result, що engine.py виставляє перед викликом."""
    first_line = ctx.result.splitlines()[0] if ctx.result else "(порожня відповідь)"
    ctx.log(f"Підсумок {ctx.schema.kind}.{ctx.schema.name}: {first_line}")


@register("log_query")
def log_query(ctx) -> None:
    """before_read: логує СЕЛЕКТ-запит, яким буде прочитано джерело -
    корисно для діагностики select_mode=explicit (яка саме мапа полів
    реально пішла у запит)."""
    ctx.log(f"Запит: {ctx.query}")
