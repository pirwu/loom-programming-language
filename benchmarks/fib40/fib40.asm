format PE64 console
entry start

include 'win64a.inc'

section '.text' code readable executable

fib:
    ; rcx = n
    cmp rcx, 2
    jl .base
    push rbx
    push rcx
    dec rcx
    call fib
    mov rbx, rax
    pop rcx
    sub rcx, 2
    call fib
    add rax, rbx
    pop rbx
    ret
.base:
    mov rax, rcx
    ret

start:
    sub rsp, 40       ; shadow space + alignment
    mov rcx, 40
    call fib
    mov rdx, rax
    lea rcx, [fmt]
    call [printf]
    xor ecx, ecx
    call [ExitProcess]

section '.data' data readable writeable
    fmt db '%lld', 10, 0

section '.idata' import data readable writeable
    library kernel32, 'KERNEL32.DLL', msvcrt, 'MSVCRT.DLL'
    import kernel32, ExitProcess, 'ExitProcess'
    import msvcrt, printf, 'printf'