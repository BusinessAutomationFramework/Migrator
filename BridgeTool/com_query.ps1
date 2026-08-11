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

param(
    [Parameter(Mandatory)][string]$ConnectionString,
    [Parameter(Mandatory)][string]$QueryText,
    [Parameter(Mandatory)][string]$OutFile
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
    # Табличні частини (КонтактнаяИнформация тощо) і подібні складні колекції
    # не мають Метаданные() як прості значення - навмисно пропускаємо їх
    # (як і в BSL-версії, табличні частини поза межами цього інструменту).
    try {
        $meta = Invoke-Method $val "Метаданные"
        $fullName = Invoke-Method $meta "ПолноеИмя"
    } catch {
        return $null
    }
    $parts = $fullName -split '\.'
    $kind = $parts[0]
    if ($kind -eq "Перечисление") {
        $valueName = Get-Prop $meta "Имя"
        return [ordered]@{ "__enum_type__" = $parts[1]; "__enum_value__" = $valueName }
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

$connector = New-Object -ComObject V83.COMConnector
$src = $connector.Connect($ConnectionString)

$query = Invoke-Method $src "NewObject" @("Запрос")
Set-Prop $query "Текст" $QueryText

$result = Invoke-Method $query "Выполнить"
$columns = Get-Prop $result "Колонки"

$colNames = @()
if ($columns -is [System.Array]) {
    foreach ($col in $columns) {
        $colNames += (Get-Prop $col "Имя")
    }
} else {
    $colCount = Invoke-Method $columns "Количество"
    for ($i = 0; $i -lt $colCount; $i++) {
        $col = Invoke-Method $columns "Получить" @($i)
        $colNames += (Get-Prop $col "Имя")
    }
}

$selection = Invoke-Method $result "Выбрать"

$rows = New-Object System.Collections.ArrayList
while (Invoke-Method $selection "Следующий") {
    $row = [ordered]@{}
    foreach ($name in $colNames) {
        $v = Get-Prop $selection $name
        $row[$name] = Convert-ComValue $v $src
    }
    [void]$rows.Add($row)
}

$json = $rows | ConvertTo-Json -Depth 20 -Compress
if ($rows.Count -eq 0) { $json = "[]" }
[System.IO.File]::WriteAllText($OutFile, $json, [System.Text.UTF8Encoding]::new($false))
Write-Output "OK: $($rows.Count) rows"
