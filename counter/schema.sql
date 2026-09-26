-- The counter's one table: how many times each thing happened each day.
-- Nothing in it identifies a reader (counter/worker.js).
CREATE TABLE IF NOT EXISTS counts (
  day    TEXT NOT NULL,             -- YYYY-MM-DD, Eastern time
  event  TEXT NOT NULL,             -- view, visit or panel
  path   TEXT NOT NULL DEFAULT '',  -- the page, from the site root
  source TEXT NOT NULL DEFAULT '',  -- where a view came from: x, search, direct...
  detail TEXT NOT NULL DEFAULT '',  -- a visit's new or return; a panel's name
  n      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, event, path, source, detail)
);
