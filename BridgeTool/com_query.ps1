# Читає дані з ІНШОЇ бази 1С через COM (V83.COMConnector) - НЕ через BridgeTool.
# BridgeTool сам ніколи не встановлює зовнішніх з'єднань (працює лише зі
# своєю базою). COM-з'єднання до TEST_SKI_HIRE встановлює виключно ЦЕЙ
# скрипт, викликаний як окремий процес зі скрипта-оркестратора (Python).
#
# Властивості на COM-об'єктах пізнього зв'язування треба встановлювати/
# читати через явний Type.InvokeMember (BindingFlags) - звичайний
# dot-notation PowerShell ($obj.Прив = val) НЕ працює надійно для цих
# об'єктів (перевірено емпірично).
#
# Вивід: JSON-масив рядків у файл -OutFile (у форматі __ref_type__/__ref_uuid__/
# __enum_type__/__enum_value__, сумісному з ЗначениеЗJSON у BridgeTool).
#
# Табличні частини (-TabularParts): для кожної переданої назви ТЗ виконує
# ОКРЕМИЙ запит "ВЫБРАТЬ * ИЗ <ObjectRef>.<ІмяТЗ>" (Ссылка - лінк на
# власника), групує рядки за Ссылка і вкладає їх у відповідний рядок
# головної вибірки під ключем = імені ТЗ - готово для ЗаписатиЕлементи.

param(
    [Parameter(Mandatory)][string]$ConnectionString,
    [Parameter(Mandatory)][string]$QueryText,
    [Parameter(Mandatory)][string]$OutFile,
    [string]$TabularParts = "",   # напр. "КонтактнаяИнформация,ДоступныеУслуги"
    [string]$ObjectRef = ""       # напр. "Справочник.Склады" - обов'язково, якщо задано -TabularParts
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Reflection

$GetProp   = [System.Reflection.BindingFlags]::GetProperty
$SetProp   = [System.Reflection.BindingFlags]::SetProperty
$InvokeMet = [System.Reflection.BindingFlags]::InvokeMethod

function Get-Prop($obj, $name) {
    $obj.GetType().InvokeMember($name, $GetProp, $null, $obj, @())
}
function Set-Prop($obj, $name, $value) {
    $obj.GetType().InvokeMember($name, $SetProp, $null, $obj, @($value)) | Out-Null
}
function Invoke-Method($obj, $name, [object[]]$callArgs = @()) {
    $obj.GetType().InvokeMember($name, $InvokeMet, $null, $obj, $callArgs)
}

function Convert-ComValue($val, $connection) {
    if ($null -eq $val) { return $null }
    if ($val -is [DateTime]) {
        # 1С-дата маршалиться COM у нативний .NET DateTime - серіалізуємо
        # ЯВНО у формат "ГГГГММДДЧЧММСС" (14 цифр, без роздільників), який
        # BSL-функція Дата(<Строка>) приймає НАПРЯМУ - а не в дефолтний
        # формат ConvertTo-Json ("/Date(мс)/"), який BSL не розпізнає і
        # мовчки відкидає (поле лишається порожнім).
        return $val.ToString("yyyyMMddHHmmss")
    }
    if ($val -isnot [System.__ComObject]) {
        return $val
    }
    # Табличні частини як ЗНАЧЕННЯ окремого поля (не через -TabularParts)
    # не мають Метаданные() як прості значення - навмисно пропускаємо їх.
    try {
        $meta = Invoke-Method $val "Метаданные"
        $fullName = Invoke-Method $meta "ПолноеИмя"
    } catch {
        return $null
    }
    $parts = $fullName -split '\.'
    $kind = $parts[0]
    if ($kind -eq "Перечисление") {
        return Convert-EnumValue $val $meta $parts[1] $connection
    }
    try {
        $uuidObj = Invoke-Method $val "УникальныйИдентификатор"
        # String() - глобальна функція, викликається НА З'ЄДНАННІ, не на самому об'єкті.
        $uuidStr = Invoke-Method $connection "String" @($uuidObj)
    } catch {
        return $null
    }
    return [ordered]@{ "__ref_type__" = $fullName; "__ref_uuid__" = $uuidStr }
}

$script:EnumLookupCache = @{}  # ІмяТипуПереліку -> @{ ЗначениеВСтрокуВнутр-репр -> ІмяЗначення }

function Get-EnumLookupMap($connection, $enumTypeName, $valuesMeta) {
    if ($script:EnumLookupCache.ContainsKey($enumTypeName)) {
        return $script:EnumLookupCache[$enumTypeName]
    }
    # Довідково СПРОБУВАНО і ВІДКИНУТО: глобальний менеджер "Перечисления"
    # (Get-Prop $connection "Перечисления") через В83.COMConnector
    # маршалиться в ПЛОСКИЙ .NET-масив БЕЗ пойменованого доступу за назвою
    # типу (те саме - для "Справочники") - емпірично не працює для
    # зовнішнього COM-з'єднання, хоч і задокументовано як "працює" у BSL
    # (де Перечисления.Тип - синтаксис МОВИ, не COM-властивість).
    #
    # Натомість: будуємо LOOKUP-запит МОВОЮ ЗАПИТІВ - для кожної можливої
    # назви значення (з метаданих типу, ЗначенияПеречисления - це працює
    # надійно) через ЗНАЧЕНИЕ(Перечисление.Тип.Имя) отримуємо САМЕ значення,
    # а ЗначениеВСтрокуВнутр() - його канонічний, стабільний за значенням
    # (не за посиланням/RCW-обгорткою) рядок-репрезентацію. Раз побудована
    # мапа кешується на весь час роботи скрипта (по одному lookup-запиту на
    # ТИП переліку, не на кожне значення).
    $names = @()
    foreach ($valueMeta in $valuesMeta) { $names += (Get-Prop $valueMeta "Имя") }

    $selects = foreach ($name in $names) {
        # Рядкові літерали у МОВІ ЗАПИТІВ 1С - у ПОДВІЙНИХ лапках (не в
        # одинарних, як у BSL) - одинарні лапки в мові запитів позначають
        # ДАТУ, тому 'Ім'я' там - синтаксична помилка, а не рядок.
        "ВЫБРАТЬ ЗНАЧЕНИЕ(Перечисление.$enumTypeName.$name) КАК Знач, `"$name`" КАК Имя"
    }
    $lookupQuery = ($selects -join "`nОБЪЕДИНИТЬ ВСЕ`n")

    $query = Invoke-Method $connection "NewObject" @("Запрос")
    Set-Prop $query "Текст" $lookupQuery
    $result = Invoke-Method $query "Выполнить"
    $selection = Invoke-Method $result "Выбрать"

    $map = @{}
    while (Invoke-Method $selection "Следующий") {
        $rawValue = Get-Prop $selection "Знач"
        $name = Get-Prop $selection "Имя"
        $repr = Invoke-Method $connection "ЗначениеВСтрокуВнутр" @($rawValue)
        $map[$repr] = $name
    }
    $script:EnumLookupCache[$enumTypeName] = $map
    return $map
}

function Convert-EnumValue($val, $meta, $enumTypeName, $connection) {
    # БАГ, який тут виправляємо: $meta = Invoke-Method $val "Метаданные" на
    # ЗНАЧЕННІ переліку повертає метадані ТИПУ переліку (в переліків немає
    # per-значення метаданих, як у елементів довідника) - тому
    # "Get-Prop $meta Имя" завжди дає ІМ'Я ТИПУ (напр. "ТипыСкладов"), а НЕ
    # ім'я конкретного значення. Дивись Get-EnumLookupMap за фактичним
    # вирішенням - тут лише зіставляємо ПОТОЧНЕ значення з готовою мапою.
    $valuesMeta = Get-Prop $meta "ЗначенияПеречисления"
    $names = @()
    foreach ($valueMeta in $valuesMeta) { $names += (Get-Prop $valueMeta "Имя") }
    $fallback = [ordered]@{ "__enum_type__" = $enumTypeName; "__enum_value__" = $(if ($names.Count -gt 0) { $names[0] } else { $enumTypeName }) }
    try {
        $targetRepr = Invoke-Method $connection "ЗначениеВСтрокуВнутр" @($val)

        # Емпірично встановлено: поле, яке ДЖЕРЕЛО ніколи не встановлювало
        # явно (лишилось на типовому першому за метаданими значенні), у
        # внутрішньому представленні має ІДЕНТИФІКАТОР-ЗАГЛУШКУ з самих
        # нулів - на відміну від ЯВНО обраних значень (де ЗНАЧЕНИЕ(...)-
        # запит дає справжній хеш). Тому нульовий хвіст напряму мапимо на
        # ПЕРШЕ значення метаданих (ординал 0), без звернення до
        # lookup-запиту (там його все одно не буде - його репр інший).
        if ($targetRepr -match ':0+\}$') {
            return [ordered]@{ "__enum_type__" = $enumTypeName; "__enum_value__" = $names[0] }
        }

        $map = Get-EnumLookupMap $connection $enumTypeName $valuesMeta
        if ($map.ContainsKey($targetRepr)) {
            return [ordered]@{ "__enum_type__" = $enumTypeName; "__enum_value__" = $map[$targetRepr] }
        }
    } catch {
        return $fallback
    }
    return $fallback
}

function Read-QueryRows($connection, $queryText) {
    $query = Invoke-Method $connection "NewObject" @("Запрос")
    Set-Prop $query "Текст" $queryText

    $result = Invoke-Method $query "Выполнить"
    $columns = Get-Prop $result "Колонки"

    $colNames = @()
    if ($columns -is [System.Array]) {
        foreach ($col in $columns) {
            $colNames += (Get-Prop $col "Имя")
        }
    } else {
        try {
            $colCount = Invoke-Method $columns "Количество"
            for ($i = 0; $i -lt $colCount; $i++) {
                $col = Invoke-Method $columns "Получить" @($i)
                $colNames += (Get-Prop $col "Имя")
            }
        } catch {
            # Однокомпонентний SAFEARRAY (запит з РІВНО ОДНИМ полем у
            # SELECT) маршалиться як СКАЛЯР - сам об'єкт колонки, а не
            # колекція з "Количество"/"Получить" (перевірено емпірично:
            # "Unknown name" на .Количество() для такого випадку).
            $colNames += (Get-Prop $columns "Имя")
        }
    }

    $selection = Invoke-Method $result "Выбрать"
    $rows = New-Object System.Collections.ArrayList
    while (Invoke-Method $selection "Следующий") {
        $row = [ordered]@{}
        foreach ($name in $colNames) {
            try {
                $v = Get-Prop $selection $name
            } catch {
                # Складений тип колонки (напр. Владелец підпорядкованого
                # довідника - кілька можливих типів посилання) - COM
                # віддає значення ЛИШЕ через InvokeMethod; GetProperty дає
                # "Member not found" (DISP_E_MEMBERNOTFOUND), перевірено
                # емпірично на Справочник.КассыККМ.Владелец.
                $v = Invoke-Method $selection $name
            }
            $row[$name] = Convert-ComValue $v $connection
        }
        [void]$rows.Add($row)
    }
    return ,$rows
}

$connector = New-Object -ComObject V83.COMConnector
$src = $connector.Connect($ConnectionString)

$rows = Read-QueryRows $src $QueryText

if ($TabularParts) {
    if (-not $ObjectRef) {
        throw "-TabularParts вимагає -ObjectRef (напр. 'Справочник.Склады')."
    }
    # Індекс за UUID власника для O(1) прив'язки ТЗ-рядків до головного рядка.
    $rowsByOwner = @{}
    foreach ($row in $rows) {
        $ownerRef = $row["Ссылка"]
        if ($null -ne $ownerRef -and $ownerRef.Contains("__ref_uuid__")) {
            $rowsByOwner[$ownerRef["__ref_uuid__"]] = $row
        }
    }

    foreach ($tsName in ($TabularParts -split ',')) {
        $tsName = $tsName.Trim()
        if (-not $tsName) { continue }
        foreach ($row in $rows) { $row[$tsName] = New-Object System.Collections.ArrayList }

        $tsRows = Read-QueryRows $src "ВЫБРАТЬ * ИЗ $ObjectRef.$tsName"
        foreach ($tsRow in $tsRows) {
            $ownerRef = $tsRow["Ссылка"]
            if ($null -eq $ownerRef -or -not $ownerRef.Contains("__ref_uuid__")) { continue }
            $ownerUuid = $ownerRef["__ref_uuid__"]
            if (-not $rowsByOwner.ContainsKey($ownerUuid)) { continue }

            $tsRowCopy = [ordered]@{}
            foreach ($key in $tsRow.Keys) {
                if ($key -eq "Ссылка" -or $key -eq "НомерСтроки") { continue }
                $tsRowCopy[$key] = $tsRow[$key]
            }
            [void]$rowsByOwner[$ownerUuid][$tsName].Add($tsRowCopy)
        }
    }
}

# -InputObject, НЕ пайп ("$rows | ConvertTo-Json") - класична пастка
# PowerShell: пайп РОЗГОРТАЄ колекцію по одному елементу, і для РІВНО
# ОДНОГО елемента ConvertTo-Json бачить лише ЦЕЙ елемент (не "масив з 1"),
# серіалізуючи його як JSON-ОБ'ЄКТ {...} замість [{...}] - мовчки й без
# помилки. Перевірено емпірично на Справочник.Календари (1 запис) -
# приймач потім розбирав Структуру (поля рядка) як масив КлючЗначение
# пар, "Ссылка" не знаходилась, звідси Invalid parameter value на
# УникальныйИдентификатор("").
$json = ConvertTo-Json -InputObject $rows -Depth 20 -Compress
if ($rows.Count -eq 0) { $json = "[]" }
[System.IO.File]::WriteAllText($OutFile, $json, [System.Text.UTF8Encoding]::new($false))
Write-Output "OK: $($rows.Count) rows"
