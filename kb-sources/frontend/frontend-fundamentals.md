## Frontend fundamentals
Component = props in, events out; state as low in the tree as possible, lifted only when shared.
Derived state is computed, never stored. Server state (data fetching) and UI state are different
concerns; do not hand-roll caching when a data-fetch layer exists. Every async flow has loading,
error, empty, and success states designed upfront.

## Performance and UX basics
Core Web Vitals mindset: smallest bundle that works, code-split by route, images sized/lazy, no
layout thrash. Perceived performance: optimistic UI for high-confidence actions, skeletons over
spinners. Accessibility is non-negotiable: semantic HTML first, keyboard operable, focus visible,
contrast >= 4.5:1, forms have labels and error text tied to fields.

## Forms and state
Client validation for UX, server validation for truth; show errors next to the field. Debounce
chatty inputs. Routing: one route = one screen state, deep-linkable. Never store secrets or tokens
in localStorage if httpOnly cookies are an option. Internationalize strings from day one if there
is any chance of more than one language.
