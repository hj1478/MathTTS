# Notation coverage fixture (issue #20)

One notation per line, written the way the OCR delivers it, so a run exercises
`normalize.py` and `sre-probe/speak.js` the same way a real page does. There
are deliberately no line labels: a label sitting next to a notation gets
pulled into the math span and corrupts the reading being measured (the label
itself is what ends up spoken). Results are keyed by the LaTeX in speak.js's
per-span table instead.

Trigonometry and the percent sign are written as LaTeX here. On a line of
their own the bare forms carry no math signal for `normalize.py`, so they stay
prose and never reach SRE at all — which is its own finding, but not the one
this fixture measures.

Regenerate with `python3 eval/notation_coverage.py`.

## 초등

12+7

45-8

6×7

12÷4

3×(4+2)

2/3

3/4+1/4

$25\%$

30°

5cm

3>2

5<9

12cm²

8cm³

3:4

## 중1–2

-3

-5+3

3x

2x+3y

2x+3=7

y=ax

x ≤ 3

∠BAC

l ∥ m

l ⊥ m

x²

2³

aⁿ

|-4|

(3,4)

p ≤ k < q

$0.1\dot{2}\dot{3}$

$\overline{AB}$

△ABC

## 중3

(x+1)(x-2)

(a+b)²

a²+b²=c²

x²-3x+2=0

√2

√16=4

$\sqrt{x+1}$

$\cos A$

$\sin A$

$\tan 30°$

πr²

2πr

y=ax²+bx+c

x² ≥ 0

△ABC≡△DEF

△ABC∽△DEF

$\triangle ABC \cong \triangle DEF$
