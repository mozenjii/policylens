"""The HTTP surface: JSON API and, later, the server-rendered pages.

Deliberate boundary: this package validates requests and shapes responses. Coverage logic,
retrieval and answering live in their own packages and never import from here.
"""
