"""Loaders turn a tool-specific export into the canonical ticket frame."""

from itsm_insights.loaders.generic import LoaderError, check_mapping, load_tickets

__all__ = ["LoaderError", "check_mapping", "load_tickets"]
