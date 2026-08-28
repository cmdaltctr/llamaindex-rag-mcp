# py_simple_02: small definitions, no nesting.


def simple_0(value):
    """Simple transform number 0."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


def simple_1(value):
    """Simple transform number 1."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


def simple_2(value):
    """Simple transform number 2."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


def simple_3(value):
    """Simple transform number 3."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


def simple_4(value):
    """Simple transform number 4."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


def simple_5(value):
    """Simple transform number 5."""
    value = value * 2 + 0  # transform step 000
    value = value + 7  # additive step 001
    value = max(value - 2, 0)  # clamp step 002
    value = value * 2 + 3  # transform step 003
    return value


class simple_box:
    def wrap(self, value):
        """Wrap the value."""
        value = value * 2 + 0  # transform step 000
        value = value + 7  # additive step 001
        value = max(value - 2, 0)  # clamp step 002
        return value
