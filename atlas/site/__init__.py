"""Atlas Sports Intelligence — the site build.

A static site generator. It reads the point-in-time warehouse and the live
tracking store and emits plain HTML: no server, no client framework, no
hydration. The card is a document, and a document loads instantly.

The design system, brand rules and card specification this implements are
approved and fixed:

* ``docs/UI_SYSTEM.md``       tokens, type, layout, chart rules
* ``docs/BRAND_GUIDE.md``     voice and the forbidden vocabulary
* ``docs/ATLAS_CARD_SPEC.md`` the eight sections and the grade rubric
* ``docs/PREMIUM_PLAN.md``    what is free and what is not

Nothing in this package decides what a reader should do. ``tests/test_site.py``
checks every emitted page for the vocabulary that would imply otherwise.
"""
