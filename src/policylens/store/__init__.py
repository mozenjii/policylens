"""The single SQLite file the service reads: built offline, opened read-only.

Deliberate boundary: nothing at request time writes to it. A new CMS snapshot means a new
file built by `build_database`, never an update in place, so every answer the service gives
traces to one snapshot and a bad build can be rolled back by keeping the old file.
"""
