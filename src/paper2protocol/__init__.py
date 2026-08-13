"""Paper2Protocol — paper -> validated Opentrons protocol via an agent-in-the-loop.

The acceptance authority is the real ``opentrons analyze`` engine, driven by a
deterministic loop (``loop.py``). No LLM — and not the orchestrating agent — may
declare a protocol converged.
"""

__version__ = "0.1.0"
