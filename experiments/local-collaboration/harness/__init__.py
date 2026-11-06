"""External harness adapters for the local-collaboration experiment.

Adapters bridge real OS processes to weave.local.v1 coordination and to a
stable, typed session record (see ``model``). They do not duplicate Exo swarm
plan validation or execution (PRs #1189–#1191); those remain contracts to wrap
once merged.
"""
