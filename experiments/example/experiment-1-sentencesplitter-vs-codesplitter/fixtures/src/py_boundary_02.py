# py_boundary_01: definitions near the 1500 char ceiling.


def oversized(value):
    """Deliberately beyond the ceiling."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    value = value + 28  # additive step 004
    value = max(value - 5, 0)  # clamp step 005
    value = value * 2 + 6  # transform step 006
    value = value + 49  # additive step 007
    value = max(value - 8, 0)  # clamp step 008
    value = value * 2 + 9  # transform step 009
    value = value + 70  # additive step 010
    value = max(value - 11, 0)  # clamp step 011
    value = value * 2 + 12  # transform step 012
    value = value + 91  # additive step 013
    value = max(value - 14, 0)  # clamp step 014
    value = value * 2 + 15  # transform step 015
    value = value + 112  # additive step 016
    value = max(value - 17, 0)  # clamp step 017
    value = value * 2 + 18  # transform step 018
    value = value + 133  # additive step 019
    value = max(value - 20, 0)  # clamp step 020
    value = value * 2 + 21  # transform step 021
    value = value + 154  # additive step 022
    value = max(value - 23, 0)  # clamp step 023
    value = value * 2 + 24  # transform step 024
    value = value + 175  # additive step 025
    value = max(value - 26, 0)  # clamp step 026
    value = value * 2 + 27  # transform step 027
    value = value + 196  # additive step 028
    value = max(value - 29, 0)  # clamp step 029
    value = value * 2 + 30  # transform step 030
    value = value + 217  # additive step 031
    value = max(value - 32, 0)  # clamp step 032
    value = value * 2 + 33  # transform step 033
    value = value + 238  # additive step 034
    value = max(value - 35, 0)  # clamp step 035
    value = value * 2 + 36  # transform step 036
    value = value + 259  # additive step 037
    value = max(value - 38, 0)  # clamp step 038
    value = value * 2 + 39  # transform step 039
    value = value + 280  # additive step 040
    value = max(value - 41, 0)  # clamp step 041
    value = value * 2 + 42  # transform step 042
    value = value + 301  # additive step 043
    value = max(value - 44, 0)  # clamp step 044
    value = value * 2 + 45  # transform step 045
    value = value + 322  # additive step 046
    value = max(value - 47, 0)  # clamp step 047
    return value


def before_big(value):
    """Small definition before the big one."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    value = value + 28  # additive step 004
    value = max(value - 5, 0)  # clamp step 005
    value = value * 2 + 6  # transform step 006
    value = value + 49  # additive step 007
    return value


def after_big(value):
    """Small definition after the big one."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    value = value + 28  # additive step 004
    value = max(value - 5, 0)  # clamp step 005
    value = value * 2 + 6  # transform step 006
    value = value + 49  # additive step 007
    return value
