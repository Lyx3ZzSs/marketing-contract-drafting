"""OA currency enum snapshot. Keys are exact string IDs, never floating point.

Source: 项目合同台账枚举映射表20261021.xlsx, 币种!A2:C4.
Workbook SHA-256: d2d8349a2366d8b4c1f52a6d0202db21d2ddaab73574dfde75ddfc1928e45c6a
Only currency entries are included; other enum groups are outside this feature.
"""

# OA enum ID -> (ISO currency code, source display name).
OA_CURRENCIES: dict[str, tuple[str, str]] = {
    "4747488595539675173": ("CNY", "人民币"),
    "-2224278840978685884": ("USD", "美元"),
    "3869348003057256238": ("EUR", "欧元"),
}
