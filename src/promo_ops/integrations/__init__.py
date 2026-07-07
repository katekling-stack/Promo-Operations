"""Integration clients for the external systems.

Each client reads its credentials from the environment (see .env.example) and is
gated: constructing it without credentials raises a clear error, so nothing tries
to talk to a live system by accident. The push flows are scaffolded against each
system's documented API; where the exact request schema needs confirmation against
a live tenant, it is marked with `# CONFIRM:`.
"""
