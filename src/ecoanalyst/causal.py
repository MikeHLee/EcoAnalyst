"""
causal.py: a Bayesian causal graph that runs beside the flow network.

The flow network says what moves where and what each component loses. The
causal graph says why a loss rate, efficiency, or capacity takes the value it
does. Each causal variable has an equation in its parents, and a variable can
be bound to one parameter of the flow network, for example a cold store's
``waste_rate``.

Sampling the causal graph gives many sets of parameter values. Evaluating the
flow network once per set gives a distribution for any flow outcome: path
loss, delivered fraction, loss cost. An intervention ``do={"x": value}``
replaces the equation of ``x`` with that value, so its effect reaches the
flow outcomes through the graph. ``fit`` updates the equations from data with
conjugate Bayesian regression, so sampling also carries parameter
uncertainty.

Every variable has one of four kinds, each with a link function. The
equation is linear on the link scale:

=========== ========== ======================================================
kind        link       equation
=========== ========== ======================================================
continuous  identity   x = b0 + sum(b_p * parent_p) + e,        e ~ N(0, s^2)
rate        logit      x = sigmoid(b0 + sum(b_p * parent_p) + e)   (0 < x < 1)
positive    log        x = exp(b0 + sum(b_p * parent_p) + e)       (x > 0)
binary      logit      x ~ Bernoulli(sigmoid(b0 + sum(b_p * parent_p)))
=========== ========== ======================================================

Parents enter on their own scale. ``intercept``, ``coefficients``, and
``noise_sd`` are on the link scale; ``link()`` converts a value to it.

What the results mean depends on the graph being right. An effect computed
with ``do`` is a causal effect only if the graph includes every common cause
of the variables involved. ``adjustment_set`` and ``is_valid_adjustment``
check the back-door criterion for a graph with unobserved variables, and
``to_gml`` exports the graph for libraries such as DoWhy.
"""

from __future__ import annotations

import math
import re
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator, List, Literal, Mapping, Optional, Sequence, Set, Tuple, Union

import networkx as nx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

VARIABLE_KINDS = ("continuous", "rate", "positive", "binary")
VariableKind = Literal["continuous", "rate", "positive", "binary"]
NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EPS = 1e-9

# Flow-network parameters a causal variable can drive, and the kind it must have.
NODE_FIELDS = {"waste_rate": "rate", "efficiency": "rate", "degradation_rate": "rate", "capacity": "positive"}
EDGE_FIELDS = {"waste_rate": "rate", "efficiency": "rate", "max_rate": "positive"}


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.tanh(0.5 * z))


def link(kind: str, value: Any) -> Any:
    """Map a value to the link scale of ``kind`` (identity, logit, or log).

    Use it to state an intercept from a natural value, for example
    ``link("rate", 0.05)`` for a 5% loss rate.
    """
    x = np.asarray(value, dtype=float)
    if kind == "continuous":
        out = x
    elif kind in ("rate", "binary"):
        if np.any((x < 0) | (x > 1)):
            raise ValueError(f"{kind} values must be between 0 and 1")
        x = np.clip(x, _EPS, 1 - _EPS)
        out = np.log(x) - np.log1p(-x)
    elif kind == "positive":
        if np.any(x <= 0):
            raise ValueError("positive values must be greater than 0")
        out = np.log(x)
    else:
        raise ValueError(f"unknown variable kind {kind!r}; use one of {VARIABLE_KINDS}")
    return float(out) if np.ndim(out) == 0 else out


def inverse_link(kind: str, z: Any) -> Any:
    """Map from the link scale back to the natural scale (a probability for binary)."""
    z = np.asarray(z, dtype=float)
    if kind == "continuous":
        out = z
    elif kind in ("rate", "binary"):
        out = _sigmoid(z)
    elif kind == "positive":
        out = np.exp(z)
    else:
        raise ValueError(f"unknown variable kind {kind!r}; use one of {VARIABLE_KINDS}")
    return float(out) if np.ndim(out) == 0 else out


def _check_value(kind: str, value: Any, name: str, n: int) -> np.ndarray:
    """Validate an intervention value (a scalar or one value per sample) and broadcast it to n."""
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = np.full(n, float(arr))
    elif arr.shape != (n,):
        raise ValueError(f"do({name}): expected a scalar or {n} values, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"do({name}): values must be finite")
    if kind == "rate" and np.any((arr < 0.0) | (arr > 1.0)):
        raise ValueError(f"do({name}): a rate must be between 0 and 1")
    if kind == "positive" and np.any(arr <= 0.0):
        raise ValueError(f"do({name}): a positive variable must be > 0")
    if kind == "binary" and not np.all(np.isin(arr, (0.0, 1.0))):
        raise ValueError(f"do({name}): a binary variable must be 0 or 1")
    return arr


# ---------------------------------------------------------------------------
# Model objects
# ---------------------------------------------------------------------------


class Binding(BaseModel):
    """Attach a causal variable to one parameter of a node or an edge.

    ``field`` is one of ``waste_rate``, ``efficiency``, ``degradation_rate``,
    or ``capacity`` (the capacity value) for a node, and ``waste_rate``,
    ``efficiency``, or ``max_rate`` (the max-rate value) for an edge.
    """

    model_config = ConfigDict(frozen=True)

    target: Literal["node", "edge"]
    id: str
    field: str

    @classmethod
    def parse(cls, value: Union["Binding", Mapping[str, Any], str]) -> "Binding":
        """Accept a Binding, a dict, or a string ``"node:<id>:<field>"``."""
        if isinstance(value, Binding):
            return value
        if isinstance(value, str):
            parts = value.split(":", 2)
            if len(parts) != 3:
                raise ValueError(f'binding string must look like "node:<id>:<field>", got {value!r}')
            return cls(target=parts[0], id=parts[1], field=parts[2])
        return cls.model_validate(value)

    def required_kind(self) -> str:
        fields = NODE_FIELDS if self.target == "node" else EDGE_FIELDS
        if self.field not in fields:
            raise ValueError(f"{self.target} field must be one of {sorted(fields)}, got {self.field!r}")
        return fields[self.field]

    def __str__(self) -> str:
        return f"{self.target}:{self.id}:{self.field}"


class Posterior(BaseModel):
    """Fitted coefficients for one variable.

    ``normal_inverse_gamma``: coefficients | s^2 ~ N(mean, s^2 * scale),
    s^2 ~ InverseGamma(a, b). ``laplace``: coefficients ~ N(mean, scale)
    (binary variables). ``terms`` is ``["intercept", <parents>...]``.
    """

    family: Literal["normal_inverse_gamma", "laplace"]
    terms: List[str]
    mean: List[float]
    scale: List[List[float]]
    a: Optional[float] = None
    b: Optional[float] = None
    n_obs: int

    def noise_sd(self) -> Optional[float]:
        """Square root of the posterior mean of s^2 (None for binary variables)."""
        if self.family != "normal_inverse_gamma":
            return None
        return math.sqrt(self.b / (self.a - 1.0)) if self.a > 1.0 else math.sqrt(self.b / self.a)


class CausalVariable(BaseModel):
    """One node of the causal graph (see the module docstring for the equation)."""

    model_config = ConfigDict(validate_assignment=True)

    name: str
    kind: VariableKind = "continuous"
    parents: List[str] = Field(default_factory=list)
    intercept: float = 0.0
    coefficients: Dict[str, float] = Field(default_factory=dict)
    noise_sd: float = Field(1.0, ge=0.0)
    observed: bool = True
    unit: Optional[str] = None
    description: str = ""
    binds: Optional[Binding] = None
    posterior: Optional[Posterior] = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not NAME_PATTERN.match(value):
            raise ValueError(f"variable name {value!r} must be an identifier (letters, digits, _)")
        return value

    def terms(self) -> List[str]:
        return ["intercept", *self.parents]

    def point_estimate(self) -> Tuple[np.ndarray, float]:
        """(coefficients in ``terms()`` order, noise sd): posterior mean if fitted, else the stated values."""
        if self.posterior is not None:
            noise = self.posterior.noise_sd()
            return np.asarray(self.posterior.mean, dtype=float), (self.noise_sd if noise is None else noise)
        beta = [self.intercept] + [self.coefficients.get(p, 0.0) for p in self.parents]
        return np.asarray(beta, dtype=float), self.noise_sd


class ParameterDraw:
    """One set of equation coefficients per sample, drawn once and reused.

    Pass it to ``CausalModel.sample(parameters=...)`` to keep each sample's
    coefficients fixed across repeated calls, for example when a model is
    stepped through time one period per call.
    """

    def __init__(self, n: int, coefficients: Dict[str, np.ndarray], noise_sd: Dict[str, Any]):
        self.n = n
        self.coefficients = coefficients
        self.noise_sd = noise_sd


class CausalModel:
    """A directed acyclic graph of causal variables.

    Variables are added parents first, so the graph is acyclic by
    construction and the insertion order is a topological order.
    """

    def __init__(self) -> None:
        self.variables: Dict[str, CausalVariable] = {}

    # -- building ----------------------------------------------------------

    def add_variable(
        self,
        name: str,
        kind: str = "continuous",
        parents: Sequence[str] = (),
        intercept: float = 0.0,
        coefficients: Optional[Mapping[str, float]] = None,
        noise_sd: float = 1.0,
        binds: Union[Binding, Mapping[str, Any], str, None] = None,
        observed: bool = True,
        unit: Optional[str] = None,
        description: str = "",
    ) -> CausalVariable:
        """Add a variable. Its parents must already be in the model.

        Raises:
            ValueError: on a duplicate name, an unknown parent, a coefficient
                for a non-parent, or a binding whose field needs another kind
        """
        if name in self.variables:
            raise ValueError(f"duplicate causal variable {name!r}")
        parents = list(parents)
        for parent in parents:
            if parent not in self.variables:
                raise ValueError(f"{name}: parent {parent!r} must be added before its children")
        if len(set(parents)) != len(parents):
            raise ValueError(f"{name}: repeated parent")
        coefficients = dict(coefficients or {})
        extra = set(coefficients) - set(parents)
        if extra:
            raise ValueError(f"{name}: coefficients for non-parents {sorted(extra)}")
        binding = Binding.parse(binds) if binds is not None else None
        variable = CausalVariable(
            name=name, kind=kind, parents=parents, intercept=intercept,
            coefficients=coefficients, noise_sd=noise_sd, binds=binding,
            observed=observed, unit=unit, description=description,
        )
        if binding is not None and binding.required_kind() != variable.kind:
            raise ValueError(
                f"{name}: {binding.target} field {binding.field!r} needs a "
                f"{binding.required_kind()!r} variable, not {variable.kind!r}"
            )
        self.variables[name] = variable
        return variable

    def remove_variable(self, name: str) -> None:
        """Remove a variable that has no children."""
        self._require(name)
        children = self.children(name)
        if children:
            raise ValueError(f"{name} has children {children}; remove them first")
        del self.variables[name]

    def _require(self, name: str) -> CausalVariable:
        if name not in self.variables:
            raise ValueError(f"unknown causal variable {name!r}")
        return self.variables[name]

    # -- structure ---------------------------------------------------------

    def graph(self) -> nx.DiGraph:
        """The causal DAG as a networkx DiGraph (variable names as nodes)."""
        g = nx.DiGraph()
        for v in self.variables.values():
            g.add_node(v.name, kind=v.kind, observed=v.observed)
            for p in v.parents:
                g.add_edge(p, v.name)
        return g

    def children(self, name: str) -> List[str]:
        return [v.name for v in self.variables.values() if name in v.parents]

    def bindings(self) -> Dict[str, Binding]:
        """Variable name -> Binding for every bound variable."""
        return {v.name: v.binds for v in self.variables.values() if v.binds is not None}

    def check_bindings(self, network: Any) -> List[str]:
        """Problems with the bindings against ``network``: missing ids or duplicates."""
        problems = []
        seen: Dict[str, str] = {}
        for name, b in self.bindings().items():
            store = network.nodes if b.target == "node" else network.edges
            if b.id not in store:
                problems.append(f"{name}: {b.target} {b.id!r} is not in the network")
            key = str(b)
            if key in seen:
                problems.append(f"{name}: {key} is already driven by {seen[key]}")
            seen[key] = name
        return problems

    # -- identification ----------------------------------------------------

    def is_valid_adjustment(self, treatment: str, outcome: str, adjust: Iterable[str]) -> bool:
        """Back-door criterion: does ``adjust`` identify the effect of treatment on outcome?

        ``adjust`` must contain only observed variables, no descendant of the
        treatment, and must block every path from treatment to outcome that
        starts with an arrow into the treatment.
        """
        self._require(treatment)
        self._require(outcome)
        adjust = set(adjust)
        for name in adjust:
            if not self._require(name).observed:
                return False
        g = self.graph()
        if adjust & (nx.descendants(g, treatment) | {treatment, outcome}):
            return False
        g.remove_edges_from(list(g.out_edges(treatment)))
        return nx.is_d_separator(g, {treatment}, {outcome}, adjust)

    def adjustment_set(self, treatment: str, outcome: str) -> Optional[Set[str]]:
        """A minimal back-door adjustment set of observed variables, or None if none exists.

        An empty set means no adjustment is needed.
        """
        self._require(treatment)
        self._require(outcome)
        g = self.graph()
        excluded = nx.descendants(g, treatment) | {treatment, outcome}
        allowed = {v.name for v in self.variables.values() if v.observed and v.name not in excluded}
        g.remove_edges_from(list(g.out_edges(treatment)))
        found = nx.find_minimal_d_separator(g, {treatment}, {outcome}, restricted=allowed)
        return None if found is None else set(found)

    # -- sampling ----------------------------------------------------------

    def draw_parameters(
        self, n: int, seed: Optional[int] = None, parameter_uncertainty: bool = True,
    ) -> ParameterDraw:
        """Draw each sample's coefficients and noise sd once (see ``ParameterDraw``)."""
        rng = np.random.default_rng(seed)
        coefficients: Dict[str, np.ndarray] = {}
        noise: Dict[str, Any] = {}
        for v in self.variables.values():
            z_coef, u_scale = self._parameter_noise(rng, v, n)
            beta, sigma = _coefficients(v, n, z_coef, u_scale, parameter_uncertainty)
            coefficients[v.name] = np.array(beta)
            noise[v.name] = sigma
        return ParameterDraw(n, coefficients, noise)

    @staticmethod
    def _parameter_noise(rng, v: CausalVariable, n: int):
        z_coef = rng.standard_normal((n, len(v.parents) + 1))
        post = v.posterior
        u_scale = (
            rng.gamma(post.a, 1.0, size=n)
            if post is not None and post.family == "normal_inverse_gamma" else None
        )
        return z_coef, u_scale

    def sample(
        self,
        n: int = 1000,
        do: Optional[Mapping[str, Any]] = None,
        seed: Optional[int] = None,
        parameter_uncertainty: bool = True,
        parameters: Optional[ParameterDraw] = None,
    ) -> Dict[str, np.ndarray]:
        """Draw ``n`` joint samples, optionally under interventions.

        The random numbers are drawn in the same order whatever ``do`` holds,
        so two calls with the same seed and different interventions share
        their noise (common random numbers). The difference between them is
        then the effect of the intervention alone.

        Args:
            n: Number of samples
            do: Variable name -> fixed value, either one value for every
                sample or an array with one value per sample
            seed: Seed for numpy's default generator
            parameter_uncertainty: For fitted variables, draw coefficients
                from the posterior per sample (True) or use the posterior
                mean (False). Ignored when ``parameters`` is given.
            parameters: Coefficients from ``draw_parameters(n)`` to use
                instead of drawing new ones; only the noise is drawn

        Returns:
            Variable name -> array of ``n`` values
        """
        do = {
            name: _check_value(self._require(name).kind, value, name, n)
            for name, value in (do or {}).items()
        }
        if parameters is not None and parameters.n != n:
            raise ValueError(f"parameters were drawn for n={parameters.n}, not n={n}")
        rng = np.random.default_rng(seed)
        out: Dict[str, np.ndarray] = {}
        for v in self.variables.values():
            if parameters is None:
                z_coef, u_scale = self._parameter_noise(rng, v, n)
            u_noise = rng.standard_normal(n)
            u_bern = rng.random(n)
            if v.name in do:
                out[v.name] = do[v.name]
                continue
            design = np.column_stack([np.ones(n)] + [out[p] for p in v.parents])
            if parameters is None:
                beta, sigma = _coefficients(v, n, z_coef, u_scale, parameter_uncertainty)
            else:
                beta, sigma = parameters.coefficients[v.name], parameters.noise_sd[v.name]
            eta = np.einsum("ij,ij->i", design, beta)
            if v.kind == "binary":
                out[v.name] = (u_bern < _sigmoid(eta)).astype(float)
            else:
                out[v.name] = inverse_link(v.kind, eta + sigma * u_noise)
        return out

    def predict(self, data: Any, variables: Optional[Iterable[str]] = None) -> Dict[str, np.ndarray]:
        """Each variable's value implied by its equation and the parent values in ``data``.

        Uses the posterior mean when fitted, else the stated values, and no
        noise: the result is the inverse link of the linear predictor, which
        is the median for continuous, rate, and positive variables and the
        probability of 1 for binary ones. A variable is predicted when all
        its parents are columns; rows with a missing parent give NaN.
        ``variables`` limits the output to the named variables.

        Returns:
            Variable name -> array with one value per row
        """
        columns = {str(k): np.asarray(data[k], dtype=float) for k in _keys(data)}
        if not columns:
            raise ValueError("predict needs at least one column to know the number of rows")
        n_rows = len(next(iter(columns.values())))
        names = list(variables) if variables is not None else list(self.variables)
        out: Dict[str, np.ndarray] = {}
        for name in names:
            v = self._require(name)
            if not all(p in columns for p in v.parents):
                continue
            design = np.column_stack([np.ones(n_rows)] + [columns[p] for p in v.parents])
            beta, _ = v.point_estimate()
            out[name] = np.asarray(inverse_link(v.kind, design @ beta), dtype=float)
        return out

    # -- fitting -----------------------------------------------------------

    def fit(
        self, data: Any, prior_scale: float = 10.0, max_iter: int = 100, autoscale: bool = True,
    ) -> Dict[str, int]:
        """Update each variable's equation from data.

        ``data`` maps variable names to 1-D arrays of equal length (a dict or
        a pandas DataFrame). A variable is fitted when it and all its parents
        are columns; rows with a missing or non-finite value in any of them
        are skipped. Other variables keep their stated equation.

        The stated intercept and coefficients are the prior mean. For
        continuous, rate, and positive variables the prior is
        normal-inverse-gamma and the posterior is exact; for binary variables
        the posterior is a Laplace approximation on the logit scale.

        With ``autoscale`` (the default) the prior is measured in the data's
        own units, so the same data in other units gives the same fit in
        those units: a parent's coefficient has prior sd ``prior_scale`` x
        noise sd / sd(parent) (``prior_scale`` / sd(parent) for a binary
        variable), and the prior noise sd is the variable's sample sd on the
        link scale. With ``autoscale=False`` the prior noise sd is the
        stated ``noise_sd`` and every coefficient has prior sd
        ``prior_scale`` x noise sd (``prior_scale`` for binary), which is
        informative when a variable or a parent is far from unit scale.

        Returns:
            Variable name -> number of rows used, for each fitted variable
        """
        columns = {str(k): np.asarray(data[k], dtype=float) for k in _keys(data)}
        used: Dict[str, int] = {}
        for v in self.variables.values():
            needed = [v.name, *v.parents]
            if not all(c in columns for c in needed):
                continue
            stack = np.column_stack([columns[c] for c in needed])
            rows = np.all(np.isfinite(stack), axis=1)
            if rows.sum() == 0:
                continue
            y_raw, parents = stack[rows, 0], stack[rows, 1:]
            design = np.column_stack([np.ones(len(y_raw)), parents])
            prior_mean = np.array([v.intercept] + [v.coefficients.get(p, 0.0) for p in v.parents])
            # Prior sd of each term in units of (noise sd, or logit) per unit of the term.
            term_scale = np.full(design.shape[1], float(prior_scale))
            if autoscale:
                term_scale[1:] = prior_scale / _spread(parents)
            if v.kind == "binary":
                if not np.all(np.isin(y_raw, (0.0, 1.0))):
                    raise ValueError(f"{v.name}: binary data must be 0 or 1")
                v.posterior = _laplace_logistic(design, y_raw, prior_mean, term_scale, max_iter, v.terms())
            else:
                y = np.asarray(link(v.kind, y_raw), dtype=float)
                noise_prior = float(_spread(y[:, None])[0]) if autoscale and len(y) > 1 else v.noise_sd
                v.posterior = _normal_inverse_gamma(design, y, prior_mean, term_scale, noise_prior, v.terms())
            used[v.name] = int(rows.sum())
        return used

    # -- export ------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {"variables": [v.model_dump(mode="json", exclude_none=True) for v in self.variables.values()]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CausalModel":
        model = cls()
        for item in data.get("variables", []):
            item = dict(item)
            posterior = item.pop("posterior", None)
            model.add_variable(**{k: item[k] for k in item if k in _ADD_ARGS})
            if posterior is not None:
                model.variables[item["name"]].posterior = Posterior.model_validate(posterior)
        return model

    def to_networkx(self) -> nx.DiGraph:
        """The DAG with kind, observed, unit, and binding as node attributes."""
        g = self.graph()
        for v in self.variables.values():
            if v.unit:
                g.nodes[v.name]["unit"] = v.unit
            if v.binds is not None:
                g.nodes[v.name]["binds"] = str(v.binds)
        return g

    def to_gml(self) -> str:
        """The DAG as a GML string, the graph format DoWhy's CausalModel accepts."""
        g = nx.DiGraph()
        g.add_nodes_from(self.variables)
        for v in self.variables.values():
            g.add_edges_from((p, v.name) for p in v.parents)
        return "\n".join(nx.generate_gml(g))


_ADD_ARGS = {
    "name", "kind", "parents", "intercept", "coefficients", "noise_sd",
    "binds", "observed", "unit", "description",
}


def _keys(data: Any) -> List[Any]:
    return list(data.columns) if hasattr(data, "columns") else list(data.keys())


def _coefficients(v: CausalVariable, n: int, z_coef, u_scale, parameter_uncertainty: bool):
    """Per-sample coefficient rows (n x k) and noise sd (a scalar or an n-array)."""
    post = v.posterior
    if post is None or not parameter_uncertainty:
        beta, sigma = v.point_estimate()
        return np.broadcast_to(beta, (n, beta.size)), sigma
    mean = np.asarray(post.mean, dtype=float)
    chol = np.linalg.cholesky(np.asarray(post.scale, dtype=float))
    draws = z_coef @ chol.T
    if post.family == "laplace":
        return mean + draws, 0.0
    sigma = np.sqrt(post.b / u_scale)  # s^2 ~ InverseGamma(a, b) = b / Gamma(a, 1)
    return mean + sigma[:, None] * draws, sigma


def _spread(columns: np.ndarray) -> np.ndarray:
    """Sample sd of each column, with 1.0 for a constant column."""
    sd = np.std(np.atleast_2d(columns.T).T, axis=0)
    return np.where(sd > 0, sd, 1.0)


def _normal_inverse_gamma(X, y, m0, term_scale, noise_sd, terms) -> Posterior:
    """Conjugate update. Prior: beta | s2 ~ N(m0, s2 diag(term_scale^2)),
    s2 ~ InverseGamma(2, noise_sd^2), so the prior mean of s2 is noise_sd^2."""
    v0_inv = np.diag(1.0 / np.asarray(term_scale, dtype=float) ** 2)
    a0, b0 = 2.0, max(noise_sd, 1e-12) ** 2
    precision = v0_inv + X.T @ X
    scale = np.linalg.inv(precision)
    scale = 0.5 * (scale + scale.T)
    mean = scale @ (v0_inv @ m0 + X.T @ y)
    a = a0 + 0.5 * len(y)
    b = b0 + 0.5 * float(y @ y + m0 @ v0_inv @ m0 - mean @ precision @ mean)
    return Posterior(
        family="normal_inverse_gamma", terms=terms, mean=mean.tolist(),
        scale=scale.tolist(), a=a, b=max(b, 1e-12), n_obs=len(y),
    )


def _laplace_logistic(X, y, m0, term_scale, max_iter, terms) -> Posterior:
    beta = m0.astype(float).copy()
    prior_prec = np.diag(1.0 / np.asarray(term_scale, dtype=float) ** 2)
    for _ in range(max_iter):
        p = _sigmoid(X @ beta)
        grad = X.T @ (p - y) + prior_prec @ (beta - m0)
        hess = (X * (p * (1 - p))[:, None]).T @ X + prior_prec
        step = np.linalg.solve(hess, grad)
        beta -= step
        if np.max(np.abs(step)) < 1e-10:
            break
    p = _sigmoid(X @ beta)
    hess = (X * (p * (1 - p))[:, None]).T @ X + prior_prec
    scale = np.linalg.inv(hess)
    scale = 0.5 * (scale + scale.T)
    return Posterior(family="laplace", terms=terms, mean=beta.tolist(), scale=scale.tolist(), n_obs=len(y))


# ---------------------------------------------------------------------------
# Coupling to the flow network
# ---------------------------------------------------------------------------


def _field_owner(network: Any, binding: Binding) -> Tuple[Any, str]:
    """The pydantic object and attribute that a binding writes to."""
    binding.required_kind()
    if binding.target == "node":
        if binding.id not in network.nodes:
            raise ValueError(f"binding {binding}: node not in the network")
        props = network.nodes[binding.id].properties
        return (props.capacity, "value") if binding.field == "capacity" else (props, binding.field)
    if binding.id not in network.edges:
        raise ValueError(f"binding {binding}: edge not in the network")
    flow = network.edges[binding.id].flow
    return (flow.max_rate, "value") if binding.field == "max_rate" else (flow, binding.field)


@contextmanager
def bound_parameters(network: Any, values: Mapping[Binding, float]) -> Iterator[Any]:
    """Temporarily set bound flow parameters; restore them on exit.

    Not thread-safe: it writes to the network's objects in place.
    """
    saved = []
    try:
        for binding, value in values.items():
            owner, attr = _field_owner(network, binding)
            saved.append((owner, attr, getattr(owner, attr)))
            setattr(owner, attr, float(value))
        yield network
    finally:
        for owner, attr, old in reversed(saved):
            setattr(owner, attr, old)


Outcome = Callable[[Any], float]


def _named(fn: Outcome, name: str) -> Outcome:
    fn.__name__ = name
    return fn


def path_waste(path: Sequence[str], edge_kinds: Optional[Iterable[Any]] = None) -> Outcome:
    """Outcome: fraction of the input wasted along ``path``."""
    path, kinds = list(path), edge_kinds
    return _named(lambda net: net.calculate_path_waste(path, edge_kinds=kinds)[0], "path_waste")


def path_delivered(path: Sequence[str], edge_kinds: Optional[Iterable[Any]] = None) -> Outcome:
    """Outcome: fraction of the input delivered at the end of ``path``."""
    path, kinds = list(path), edge_kinds
    return _named(
        lambda net: net.calculate_path_transfer(path, edge_kinds=kinds)["delivered_fraction"],
        "path_delivered",
    )


def best_route_delivered(source: str, target: str, edge_kinds: Optional[Iterable[Any]] = None) -> Outcome:
    """Outcome: delivered fraction on the best route, re-routed for every sample."""

    def outcome(net: Any) -> float:
        path, _, _ = net.find_minimum_waste_path(source, target, edge_kinds=edge_kinds)
        if path is None:
            return 0.0
        return net.calculate_path_transfer(path, edge_kinds=edge_kinds)["delivered_fraction"]

    return _named(outcome, "best_route_delivered")


def waste_cost(pricing_data: Optional[Mapping[str, float]] = None, default_price: float = 1.0) -> Outcome:
    """Outcome: capacity-based loss cost of the whole network."""
    from .analysis import EconomicAnalysis

    pricing = dict(pricing_data or {})
    return _named(
        lambda net: EconomicAnalysis(net).calculate_waste_cost(pricing, default_price)["total_waste_cost"],
        "waste_cost",
    )


def path_cost(
    path: Sequence[str],
    pricing_data: Optional[Mapping[str, float]] = None,
    default_price: float = 1.0,
    input_quantity: Optional[float] = None,
    edge_kinds: Optional[Iterable[Any]] = None,
) -> Outcome:
    """Outcome: cost of the losses when a quantity follows ``path``."""
    from .analysis import EconomicAnalysis

    path, pricing = list(path), dict(pricing_data or {})
    return _named(
        lambda net: EconomicAnalysis(net).calculate_path_cost(
            path, pricing, default_price, input_quantity, edge_kinds)["total_cost"],
        "path_cost",
    )


class SimulationResult:
    """Samples of the causal variables and of the requested outcomes."""

    def __init__(self, variables: Dict[str, np.ndarray], outcomes: Dict[str, np.ndarray],
                 do: Dict[str, float], n: int, seed: Optional[int]):
        self.variables = variables
        self.outcomes = outcomes
        self.do = do
        self.n = n
        self.seed = seed

    def summary(self, quantiles: Sequence[float] = (0.05, 0.5, 0.95)) -> Dict[str, Dict[str, float]]:
        """Mean, sd, and quantiles for every outcome and variable."""
        out = {}
        for name, values in {**self.variables, **self.outcomes}.items():
            row = {"mean": float(np.mean(values)), "sd": float(np.std(values))}
            for q in quantiles:
                row[f"p{round(q * 100):02d}"] = float(np.quantile(values, q))
            out[name] = row
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"n": self.n, "seed": self.seed, "do": self.do, "summary": self.summary()}


def _resolve_model(network: Any, model: Optional[CausalModel]) -> CausalModel:
    model = model if model is not None else getattr(network, "causal", None)
    if model is None:
        raise ValueError("no causal model: pass model= or set network.causal")
    return model


def simulate(
    network: Any,
    outcomes: Optional[Mapping[str, Union[Outcome, str]]] = None,
    n: int = 1000,
    do: Optional[Mapping[str, float]] = None,
    seed: Optional[int] = None,
    model: Optional[CausalModel] = None,
    parameter_uncertainty: bool = True,
) -> SimulationResult:
    """Sample the causal graph and evaluate flow outcomes on each sample.

    Args:
        network: The EcosystemNetwork whose parameters the bindings drive
        outcomes: Name -> outcome function (see ``path_waste`` and the
            other outcome helpers) or the name of a causal variable
        n: Number of samples
        do: Interventions, variable name -> value
        seed: Random seed (use the same seed to compare interventions)
        model: Causal model; defaults to ``network.causal``
        parameter_uncertainty: See ``CausalModel.sample``

    Returns:
        SimulationResult
    """
    model = _resolve_model(network, model)
    problems = model.check_bindings(network)
    if problems:
        raise ValueError("; ".join(problems))
    outcomes = dict(outcomes or {})
    for value in outcomes.values():
        if not callable(value):
            model._require(value)
    draws = model.sample(n, do=do, seed=seed, parameter_uncertainty=parameter_uncertainty)
    functions = {k: f for k, f in outcomes.items() if callable(f)}
    results: Dict[str, np.ndarray] = {k: np.empty(n) for k in functions}
    bound = model.bindings()
    if functions:
        for i in range(n):
            values = {b: draws[name][i] for name, b in bound.items()}
            with bound_parameters(network, values):
                for key, fn in functions.items():
                    results[key][i] = fn(network)
    for key, value in outcomes.items():
        if not callable(value):
            results[key] = draws[value]
    return SimulationResult(draws, results, dict(do or {}), n, seed)


def compare(
    network: Any,
    outcome: Union[Outcome, str],
    do_a: Mapping[str, float],
    do_b: Mapping[str, float],
    n: int = 1000,
    seed: int = 0,
    model: Optional[CausalModel] = None,
    parameter_uncertainty: bool = True,
) -> Dict[str, Any]:
    """Average effect on ``outcome`` of intervention ``do_a`` versus ``do_b``.

    Both runs use the same seed, so they share their noise and the
    per-sample differences isolate the interventions.

    Returns:
        Dict with the mean outcome under each intervention, the mean
        difference (a - b), its 5th/50th/95th percentiles across samples,
        and the share of samples where a exceeds b
    """
    runs = [
        simulate(network, {"y": outcome}, n, do, seed, model, parameter_uncertainty).outcomes["y"]
        for do in (do_a, do_b)
    ]
    diff = runs[0] - runs[1]
    return {
        "do_a": dict(do_a),
        "do_b": dict(do_b),
        "mean_a": float(runs[0].mean()),
        "mean_b": float(runs[1].mean()),
        "effect": float(diff.mean()),
        "effect_p05": float(np.quantile(diff, 0.05)),
        "effect_p50": float(np.quantile(diff, 0.5)),
        "effect_p95": float(np.quantile(diff, 0.95)),
        "share_a_greater": float(np.mean(diff > 0)),
        "n": n,
        "seed": seed,
    }
