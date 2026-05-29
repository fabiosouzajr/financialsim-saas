"""CPF and CNPJ validation (modulo-11 checks)."""

from __future__ import annotations


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def is_valid_cpf(cpf: str) -> bool:
    cpf = _only_digits(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    digits = [int(c) for c in cpf]
    for j in range(9, 11):
        s = sum(digits[i] * (j + 1 - i) for i in range(j))
        dv = (s * 10) % 11
        if dv == 10:
            dv = 0
        if dv != digits[j]:
            return False
    return True


def is_valid_cnpj(cnpj: str) -> bool:
    cnpj = _only_digits(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    digits = [int(c) for c in cnpj]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6] + weights1
    for j, weights in [(12, weights1), (13, weights2)]:
        s = sum(digits[i] * weights[i] for i in range(j))
        dv = s % 11
        dv = 0 if dv < 2 else 11 - dv
        if dv != digits[j]:
            return False
    return True
