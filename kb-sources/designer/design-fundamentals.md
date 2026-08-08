## Design process
Start from user tasks, not aesthetics: list the top 3 jobs the user does, design those flows first.
Deliver: information architecture, wireframes of key flows, then a token-based visual spec. Every
screen spec includes all states (empty/loading/error/full) and mobile behavior.

## Visual system
Design tokens: color (semantic names: bg, surface, text-primary, accent, danger), type scale
(4-6 sizes), spacing scale (4/8px base), radii, shadows, motion durations. Component inventory with
variants before building screens. Contrast: WCAG AA minimum (4.5:1 text, 3:1 large text/UI).
Typography: one display + one body family max unless brand demands more. Limit the palette:
1 primary, 1 accent, neutrals, plus semantic colors.

## Handoff
A spec a developer cannot misread: token values explicit, spacing by the scale, interaction notes
(hover/focus/disabled/loading), asset formats and sizes. Flag anything novel that needs a custom
component. Review implemented UI against spec and report deltas.
