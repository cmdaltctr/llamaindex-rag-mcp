// js_nested_01.js: functions with inner functions.

function nestedStep0(input) {
    let value = input;
    function innerHelper(seed) {
        let seed = input;
        seed = seed * 2 + 0;  // transform 000
        seed = seed + 7;  // additive 001
        seed = Math.max(seed - 2, 0);  // clamp 002
        seed = seed * 2 + 3;  // transform 003
        return seed;
    }
    value = value * 2 + 0;  // transform 000
    value = value + 7;  // additive 001
    value = Math.max(value - 2, 0);  // clamp 002
    value = value * 2 + 3;  // transform 003
    value = value + 28;  // additive 004
    value = Math.max(value - 5, 0);  // clamp 005
    value = value * 2 + 6;  // transform 006
    value = value + 49;  // additive 007
    value = Math.max(value - 8, 0);  // clamp 008
    value = value * 2 + 9;  // transform 009
    value = value + innerHelper(value);
    return value;
}


function nestedStep1(input) {
    let value = input;
    function innerHelper(seed) {
        let seed = input;
        seed = seed * 2 + 0;  // transform 000
        seed = seed + 7;  // additive 001
        seed = Math.max(seed - 2, 0);  // clamp 002
        seed = seed * 2 + 3;  // transform 003
        return seed;
    }
    value = value * 2 + 0;  // transform 000
    value = value + 7;  // additive 001
    value = Math.max(value - 2, 0);  // clamp 002
    value = value * 2 + 3;  // transform 003
    value = value + 28;  // additive 004
    value = Math.max(value - 5, 0);  // clamp 005
    value = value * 2 + 6;  // transform 006
    value = value + 49;  // additive 007
    value = Math.max(value - 8, 0);  // clamp 008
    value = value * 2 + 9;  // transform 009
    value = value + innerHelper(value);
    return value;
}


function nestedStep2(input) {
    let value = input;
    function innerHelper(seed) {
        let seed = input;
        seed = seed * 2 + 0;  // transform 000
        seed = seed + 7;  // additive 001
        seed = Math.max(seed - 2, 0);  // clamp 002
        seed = seed * 2 + 3;  // transform 003
        return seed;
    }
    value = value * 2 + 0;  // transform 000
    value = value + 7;  // additive 001
    value = Math.max(value - 2, 0);  // clamp 002
    value = value * 2 + 3;  // transform 003
    value = value + 28;  // additive 004
    value = Math.max(value - 5, 0);  // clamp 005
    value = value * 2 + 6;  // transform 006
    value = value + 49;  // additive 007
    value = Math.max(value - 8, 0);  // clamp 008
    value = value * 2 + 9;  // transform 009
    value = value + innerHelper(value);
    return value;
}
