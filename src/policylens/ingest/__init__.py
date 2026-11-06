"""Turn a CMS Medicare Coverage Database download into typed, checked records.

Deliberate boundary: ingest reads a package that is already on disk. Fetching it is a
separate script, because downloading means accepting CMS's licence terms, which is a
person's decision rather than something a build does on its own.
"""
