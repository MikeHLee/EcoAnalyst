"""Modules from EcoAnalyst 1.x, kept so that existing scripts keep working.

Submodules:

- ``network_model``: ``WasteNetwork``, a directed graph with a loss rate on
  each node and edge.
- ``advanced_network``: ``AdvancedWasteNetwork`` with typed node and edge
  classes and pluggable loss functions.
- ``causal_analysis``: ``WasteCausalNetwork``, Bayesian linear regression of
  loss against its drivers. Fitting needs the ``bayes`` extra.
- ``network_viz``: matplotlib drawing helpers for ``AdvancedWasteNetwork``.
  Needs the ``viz`` extra.

Importing this package does not import any submodule, and no submodule
imports pymc, pandas, scipy, or matplotlib at import time. New code should
use :class:`ecoanalyst.EcosystemNetwork`.
"""
