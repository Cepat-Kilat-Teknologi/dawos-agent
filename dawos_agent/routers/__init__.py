"""Router package for the dawos-agent REST API.

Each sub-module registers a FastAPI ``APIRouter`` that is mounted by the
application factory.  Routers are organised by functional domain (sessions,
firewall, network, etc.) and collectively expose the full BNG management
surface over HTTP.
"""
