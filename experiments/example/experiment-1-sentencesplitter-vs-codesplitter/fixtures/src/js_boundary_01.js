// js_boundary_01.js: definitions near the 1500 char ceiling.

function fitsBelow(input) {
    let value = input;
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
    value = value + 70;  // additive 010
    value = Math.max(value - 11, 0);  // clamp 011
    value = value * 2 + 12;  // transform 012
    value = value + 91;  // additive 013
    value = Math.max(value - 14, 0);  // clamp 014
    value = value * 2 + 15;  // transform 015
    value = value + 112;  // additive 016
    value = Math.max(value - 17, 0);  // clamp 017
    value = value * 2 + 18;  // transform 018
    value = value + 133;  // additive 019
    value = Math.max(value - 20, 0);  // clamp 020
    value = value * 2 + 21;  // transform 021
    value = value + 154;  // additive 022
    value = Math.max(value - 23, 0);  // clamp 023
    value = value * 2 + 24;  // transform 024
    value = value + 175;  // additive 025
    value = Math.max(value - 26, 0);  // clamp 026
    value = value * 2 + 27;  // transform 027
    return value;
}


function oversizedJs(input) {
    let value = input;
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
    value = value + 70;  // additive 010
    value = Math.max(value - 11, 0);  // clamp 011
    value = value * 2 + 12;  // transform 012
    value = value + 91;  // additive 013
    value = Math.max(value - 14, 0);  // clamp 014
    value = value * 2 + 15;  // transform 015
    value = value + 112;  // additive 016
    value = Math.max(value - 17, 0);  // clamp 017
    value = value * 2 + 18;  // transform 018
    value = value + 133;  // additive 019
    value = Math.max(value - 20, 0);  // clamp 020
    value = value * 2 + 21;  // transform 021
    value = value + 154;  // additive 022
    value = Math.max(value - 23, 0);  // clamp 023
    value = value * 2 + 24;  // transform 024
    value = value + 175;  // additive 025
    value = Math.max(value - 26, 0);  // clamp 026
    value = value * 2 + 27;  // transform 027
    value = value + 196;  // additive 028
    value = Math.max(value - 29, 0);  // clamp 029
    value = value * 2 + 30;  // transform 030
    value = value + 217;  // additive 031
    value = Math.max(value - 32, 0);  // clamp 032
    value = value * 2 + 33;  // transform 033
    value = value + 238;  // additive 034
    value = Math.max(value - 35, 0);  // clamp 035
    value = value * 2 + 36;  // transform 036
    value = value + 259;  // additive 037
    value = Math.max(value - 38, 0);  // clamp 038
    value = value * 2 + 39;  // transform 039
    value = value + 280;  // additive 040
    value = Math.max(value - 41, 0);  // clamp 041
    value = value * 2 + 42;  // transform 042
    value = value + 301;  // additive 043
    value = Math.max(value - 44, 0);  // clamp 044
    value = value * 2 + 45;  // transform 045
    return value;
}


function tailSmall(input) {
    let value = input;
    value = value * 2 + 0;  // transform 000
    value = value + 7;  // additive 001
    value = Math.max(value - 2, 0);  // clamp 002
    value = value * 2 + 3;  // transform 003
    value = value + 28;  // additive 004
    return value;
}
