# py_nested_02: nested functions and classes.


def nested_function_0(value):
    """Nested function number 0."""

    def inner_helper(seed):
        """Inner helper number 0."""
        seed = seed * 2 + 0  # transform step 000
        seed = seed + 7  # additive step 001
        seed = max(seed - 2, 0)  # clamp step 002
        seed = seed * 2 + 3  # transform step 003
        seed = seed + 28  # additive step 004
        seed = max(seed - 5, 0)  # clamp step 005
        return seed

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
    return value


def nested_function_1(value):
    """Nested function number 1."""

    def inner_helper(seed):
        """Inner helper number 1."""
        seed = seed * 2 + 0  # transform step 000
        seed = seed + 7  # additive step 001
        seed = max(seed - 2, 0)  # clamp step 002
        seed = seed * 2 + 3  # transform step 003
        seed = seed + 28  # additive step 004
        seed = max(seed - 5, 0)  # clamp step 005
        seed = seed * 2 + 6  # transform step 006
        return seed

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
    return value


def nested_function_2(value):
    """Nested function number 2."""

    def inner_helper(seed):
        """Inner helper number 2."""
        seed = seed * 2 + 0  # transform step 000
        seed = seed + 7  # additive step 001
        seed = max(seed - 2, 0)  # clamp step 002
        seed = seed * 2 + 3  # transform step 003
        seed = seed + 28  # additive step 004
        seed = max(seed - 5, 0)  # clamp step 005
        seed = seed * 2 + 6  # transform step 006
        seed = seed + 49  # additive step 007
        return seed

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
    return value


class nested_engine:
    def method_0(self, value):
        """Class method number 0."""
        value = value * 2 + 0  # transform step 000
        value = value + 7  # additive step 001
        value = max(value - 2, 0)  # clamp step 002
        value = value * 2 + 3  # transform step 003
        value = value + 28  # additive step 004
        value = max(value - 5, 0)  # clamp step 005
        value = value * 2 + 6  # transform step 006
        value = value + 49  # additive step 007
        return value

    def method_1(self, value):
        """Class method number 1."""
        value = value * 2 + 0  # transform step 000
        value = value + 7  # additive step 001
        value = max(value - 2, 0)  # clamp step 002
        value = value * 2 + 3  # transform step 003
        value = value + 28  # additive step 004
        value = max(value - 5, 0)  # clamp step 005
        value = value * 2 + 6  # transform step 006
        value = value + 49  # additive step 007
        return value

    def method_2(self, value):
        """Class method number 2."""
        value = value * 2 + 0  # transform step 000
        value = value + 7  # additive step 001
        value = max(value - 2, 0)  # clamp step 002
        value = value * 2 + 3  # transform step 003
        value = value + 28  # additive step 004
        value = max(value - 5, 0)  # clamp step 005
        value = value * 2 + 6  # transform step 006
        value = value + 49  # additive step 007
        return value
