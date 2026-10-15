# run_all.ps1

$pass = 0
$fail = 0

function Run-Test {
    param(
        [string]$Name,
        [string[]]$Sources,
        [string[]]$Expected
    )
    Write-Host "=== $Name ===" -ForegroundColor Cyan

    # Уникальное имя для каждого теста
    $out = "test_$Name"
    $argsList = @("-m", "loomc") + $Sources + @("-o", $out)

    # На всякий случай убьём остатки
    Remove-Item "$out.exe" -ErrorAction SilentlyContinue
    Remove-Item "$out.obj" -ErrorAction SilentlyContinue

    $compile = & python $argsList 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "COMPILE FAIL:" -ForegroundColor Red
        Write-Host $compile
        $script:fail++
        Remove-Item "$out.exe" -ErrorAction SilentlyContinue
        Remove-Item "$out.obj" -ErrorAction SilentlyContinue
        return
    }

    $actual = & ".\$out.exe" 2>&1 | Out-String

    $actualLines = $actual -split "`r?`n" | Where-Object { $_ -ne "" } | ForEach-Object { $_.Trim() }
    $expectedLines = $Expected | ForEach-Object { $_.Trim() }

    $actualJoined = ($actualLines -join "`n")
    $expectedJoined = ($expectedLines -join "`n")

    if ($actualJoined -eq $expectedJoined) {
        Write-Host "PASS" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "FAIL" -ForegroundColor Red
        Write-Host "  expected: [$expectedJoined]"
        Write-Host "  actual:   [$actualJoined]"
        $script:fail++
    }
    Remove-Item "$out.exe" -ErrorAction SilentlyContinue
    Remove-Item "$out.obj" -ErrorAction SilentlyContinue
}

Run-Test "arith"        @("tests/arith.loom")        @("14")
Run-Test "loop"         @("tests/loop.loom")         @("45")
Run-Test "ifelse"       @("tests/ifelse.loom")       @("-1","0","1")
Run-Test "ptr"          @("tests/ptr.loom")          @("42")
Run-Test "extern"       @("tests/extern.loom")       @("hello from extern","8")
Run-Test "alloc"        @("tests/alloc.loom")        @("42")
Run-Test "struct_field" @("tests/struct_field.loom") @("30")
Run-Test "struct_ptr"   @("tests/struct_ptr.loom")   @("3","4","100")
Run-Test "const_basic"  @("tests/const_basic.loom")  @("100","0","10","2","-42","15")
Run-Test "enum_basic"   @("tests/enum_basic.loom")   @("0","1","2","10","11","12","100","101","102")
Run-Test "const_sizeof" @("tests/const_sizeof.loom") @("16")
Run-Test "enum_loop"    @("tests/enum_loop.loom")    @("7","7","42")
Run-Test "array_stack"  @("tests/array_stack.loom")  @("130")
Run-Test "array_heap"   @("tests/array_heap.loom")   @("285")
Run-Test "array_sizeof" @("tests/array_sizeof.loom") @("64","100","16")
Run-Test "array_u8"     @("tests/array_u8.loom")     @("ABC")
Run-Test "dbg_print"    @("tests/dbg_print.loom")    @("hello from print")
Run-Test "dbg_write"    @("tests/dbg_write.loom")    @("hello")
Run-Test "global_basic" @("tests/global_basic.loom") @("3")
Run-Test "logic"        @("tests/logic.loom")        @("0","1","0","1","0","1")

Run-Test "multi"        @("tests/multi/lexer.loom","tests/multi/main.loom") @("5")

Write-Host ""
Write-Host "Passed: $pass" -ForegroundColor Green
Write-Host "Failed: $fail" -ForegroundColor $(if ($fail -eq 0) {"Green"} else {"Red"})

if ($fail -gt 0) { exit 1 }