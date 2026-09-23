"""Live operations: scheduling, freshness provenance and health checks.

Atlas is a static site rebuilt from free sources. That makes it cheap to run
and easy to get subtly wrong: a build that succeeds against stale inputs looks
identical to one that succeeded against fresh ones. Everything in this package
exists so that the difference is visible - to the operator through
``python -m atlas.ops health``, and to a reader through a timestamp on every
surface and a public status page.

Three schedules, all Eastern, all defined in :mod:`atlas.ops.schedule`:

``heavy``   04:00 daily - warehouse, model, every page
``poll``    hourly - market only, no rebuild
``social``  05:00 daily - the featured card assets

Game days raise the poll to every fifteen minutes inside a window. Nothing
else changes, because a poll that does more than capture the market is a poll
that can fail in more ways.
"""
