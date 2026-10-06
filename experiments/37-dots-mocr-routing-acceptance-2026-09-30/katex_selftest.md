Self-test for check_katex.mjs: 6 formulas, 3 of them broken on purpose.

Good inline: $x^2 + y^2 = z^2$ and display:

$$\int_0^1 f(x)\,dx = \frac{1}{2}$$

Broken inline (undefined command): $\notacommand{x}$

Broken display (unbalanced brace):

$$\frac{1}{2$$

Good inline: $\alpha + \beta$

Broken inline (double superscript): $x^2^3$
