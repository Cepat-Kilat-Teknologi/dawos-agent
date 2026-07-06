"""Pydantic models for the dawos-agent REST API.

This sub-package houses all request/response schemas used across the API
routers.  Centralizing models here avoids circular imports and makes the
data contracts easy to discover and reference.

Sub-modules
-----------
schemas
    All Pydantic ``BaseModel`` and ``Enum`` definitions grouped by
    feature domain (health, system, sessions, config, network, firewall,
    routing, etc.).
"""
