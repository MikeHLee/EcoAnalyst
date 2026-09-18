"""
causal_analysis.py: Bayesian linear regression of loss against its drivers.

The module fits linear models such as ``waste ~ storage_time + temperature``
with PyMC and reports posterior means and standard deviations of the
coefficients. The results describe association in the data you supply.
Nothing here identifies cause and effect: the class name
``WasteCausalNetwork`` and the method names ``get_causal_effect`` and
``discover_causal_structure`` are kept only so that 1.x scripts keep working.

PyMC, pandas, SciPy, and matplotlib are imported inside the methods that
need them, so importing this module only needs numpy and networkx. Install
the ``bayes`` extra to fit models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import networkx as nx
import numpy as np


@dataclass
class RegressionResult:
    """Coefficients and fit statistics from a regression.

    ``coefficients`` maps each term (including ``"intercept"``) to a
    ``(posterior_mean, posterior_std)`` pair.
    """

    coefficients: Dict[str, Tuple[float, float]]
    predictions: np.ndarray
    prediction_intervals: np.ndarray  # shape (n_samples, 2): lower and upper bounds
    r2_score: float
    model_summary: str


class WasteCausalNetwork:
    """Container for loss data, a variable graph, and Bayesian regressions.

    The graph (``add_node`` / ``add_edge``) is a drawing and bookkeeping aid:
    the ``effect_size`` you attach to an edge is stored as given and is not
    estimated. The regressions (``fit`` and ``fit_regression``) are ordinary
    Bayesian linear or logistic models of one column on the others.
    """

    def __init__(self):
        import pandas as pd

        self.graph = nx.DiGraph()
        self.data = pd.DataFrame()
        self.model = None
        self.trace = None
        self.variables = {}
        self.regression_results = {}

    def add_node(self, node_id: str, node_type: str,
                 distribution: str = 'normal',
                 params: Dict = None):
        """
        Add a variable to the graph.

        Args:
            node_id: Variable name (normally a column in the data)
            node_type: Free-form label used for colouring plots, for example
                "cause", "effect", or "confounder"
            distribution: Stored for reference; not used by the fitting code
            params: Stored for reference; not used by the fitting code
        """
        self.graph.add_node(node_id,
                            node_type=node_type,
                            distribution=distribution,
                            params=params or {})

    def add_edge(self, source: str, target: str, effect_size: float = None):
        """Add a directed edge between two variables with an optional user-supplied weight."""
        self.graph.add_edge(source, target, effect_size=effect_size)

    def add_data(self, data):
        """Attach observations as a pandas DataFrame (one column per variable)."""
        self.data = data

    def build_model(self):
        """Build a PyMC linear model of the ``waste`` column on every other column."""
        import pymc as pm

        with pm.Model() as self.model:
            feature_vars = {}
            for col in self.data.columns:
                if col != 'waste':
                    feature_vars[col] = pm.Normal(
                        col,
                        mu=self.data[col].mean(),
                        sigma=self.data[col].std(),
                        observed=self.data[col].values
                    )

            intercept = pm.Normal('intercept', mu=0, sigma=10)
            coeffs = {
                col: pm.Normal(f'beta_{col}', mu=0, sigma=2)
                for col in feature_vars.keys()
            }

            mu = intercept
            for col, coeff in coeffs.items():
                mu = mu + coeff * feature_vars[col]

            sigma = pm.HalfNormal('sigma', sigma=1)
            pm.Normal('waste', mu=mu, sigma=sigma, observed=self.data['waste'])

    def fit(self, samples=2000):
        """Fit the ``waste`` regression by MCMC and store it under ``regression_results['waste']``.

        Features are used on their original scale, so the coefficients can be
        applied directly to raw feature values (see
        ``advanced_network.CausalWasteFunction``).
        """
        import pymc as pm

        if self.model is None:
            self.build_model()

        with self.model:
            self.trace = pm.sample(samples, tune=1000)

            coefficients = {}
            for var in self.model.named_vars:
                if var.startswith('beta_') or var == 'intercept':
                    trace_vals = self.trace.posterior[var].values.flatten()
                    coefficients[var.replace('beta_', '')] = (float(trace_vals.mean()), float(trace_vals.std()))

            X = self.data.drop('waste', axis=1)
            predictions = (
                coefficients['intercept'][0] +
                sum(coefficients[col][0] * X[col] for col in X.columns)
            )

            residuals = self.data['waste'] - predictions
            std_residuals = residuals.std()
            prediction_intervals = np.column_stack([
                predictions - 1.96 * std_residuals,
                predictions + 1.96 * std_residuals
            ])

            r2 = 1 - (residuals ** 2).sum() / ((self.data['waste'] - self.data['waste'].mean()) ** 2).sum()

            summary = (
                f"Model Summary:\n"
                f"Number of observations: {len(self.data)}\n"
                f"R² score: {r2:.3f}\n"
                f"Residual std: {std_residuals:.3f}"
            )

            self.regression_results = {
                'waste': RegressionResult(
                    coefficients=coefficients,
                    predictions=predictions,
                    prediction_intervals=prediction_intervals,
                    r2_score=r2,
                    model_summary=summary
                )
            }

    def get_causal_effect(self, cause: str, effect: str) -> Tuple[float, float]:
        """
        Multiply the stored edge weights along the path from ``cause`` to ``effect``.

        The first value is the product of the ``effect_size`` numbers passed to
        ``add_edge`` along the shortest path between the two variables. It is
        not estimated from data. The second value is the bootstrap standard
        deviation of the Pearson correlation between the two variables. The
        method name is kept for compatibility; the result is not a causal
        effect estimate.

        Returns:
            Tuple of (product of edge weights, bootstrap std of the correlation)
        """
        if self.trace is None:
            raise ValueError("Model must be fit before calling get_causal_effect")

        effect_path = nx.shortest_path(self.graph, cause, effect)
        total_effect = 1.0
        for i in range(len(effect_path) - 1):
            source, target = effect_path[i], effect_path[i + 1]
            total_effect *= self.graph[source][target]['effect_size']

        n_bootstrap = 1000
        bootstrap_effects = []

        effect_samples = self.trace.posterior[effect].values.mean(axis=0).flatten()

        if cause in self.data.columns:
            cause_data = self.data[cause].values
        else:
            cause_data = self.trace.posterior[cause].values.mean(axis=0).flatten()

        n_samples = len(cause_data)

        for _ in range(n_bootstrap):
            indices = np.random.choice(n_samples, size=n_samples, replace=True)
            cause_bootstrap = cause_data[indices]
            effect_bootstrap = effect_samples[indices]
            bootstrap_effect = np.corrcoef(cause_bootstrap, effect_bootstrap)[0, 1]
            bootstrap_effects.append(bootstrap_effect)

        return total_effect, np.std(bootstrap_effects)

    def discover_causal_structure(self, significance_threshold: float = 0.05):
        """
        Build a graph of pairwise correlations between the data columns.

        This is a correlation-threshold heuristic, not a causal discovery
        algorithm. Two columns are joined when the p-value of their Pearson
        correlation is at or below ``significance_threshold``. No conditional
        independence tests are run. Edge direction carries no information:
        Pearson correlation is symmetric, so every edge points from the
        column whose name sorts later to the one whose name sorts earlier.
        The method name is kept for compatibility.

        Returns:
            networkx.DiGraph over the data columns
        """
        from scipy import stats

        discovered_graph = nx.Graph()
        discovered_graph.add_nodes_from(self.data.columns)
        discovered_graph.add_edges_from([(i, j)
                                         for i in self.data.columns
                                         for j in self.data.columns if i < j])

        # Drop pairs whose marginal correlation is not significant.
        for i in self.data.columns:
            for j in self.data.columns:
                if i < j:
                    p_value = stats.pearsonr(self.data[i], self.data[j])[1]
                    if p_value > significance_threshold:
                        discovered_graph.remove_edge(i, j)

        directed_graph = nx.DiGraph()
        directed_graph.add_nodes_from(discovered_graph.nodes())

        for i, j in discovered_graph.edges():
            corr_i_j = abs(stats.pearsonr(self.data[i], self.data[j])[0])
            corr_j_i = abs(stats.pearsonr(self.data[j], self.data[i])[0])
            # The two values are equal (correlation is symmetric), so this
            # always takes the else branch.
            if corr_i_j > corr_j_i:
                directed_graph.add_edge(i, j)
            else:
                directed_graph.add_edge(j, i)

        return directed_graph

    def plot_causal_graph(self, highlight_path: List[str] = None):
        """Draw the variable graph with optional path highlighting. Returns ``matplotlib.pyplot``."""
        import matplotlib.pyplot as plt

        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(self.graph)

        node_colors = ['lightblue' if self.graph.nodes[node]['node_type'] == 'cause'
                       else 'lightgreen' if self.graph.nodes[node]['node_type'] == 'effect'
                       else 'lightgray' for node in self.graph.nodes()]

        nx.draw_networkx_nodes(self.graph, pos, node_color=node_colors,
                               node_size=2000)
        nx.draw_networkx_labels(self.graph, pos)

        edge_labels = {(u, v): f"{d['effect_size']:.2f}"
                       for u, v, d in self.graph.edges(data=True)
                       if d.get('effect_size') is not None}

        if highlight_path:
            path_edges = list(zip(highlight_path[:-1], highlight_path[1:]))
            nx.draw_networkx_edges(self.graph, pos,
                                   edgelist=path_edges,
                                   edge_color='r',
                                   width=2)

            other_edges = [(u, v) for u, v in self.graph.edges()
                           if (u, v) not in path_edges]
            nx.draw_networkx_edges(self.graph, pos,
                                   edgelist=other_edges,
                                   edge_color='gray')
        else:
            nx.draw_networkx_edges(self.graph, pos, edge_color='gray')

        nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=edge_labels)

        plt.title("Loss driver graph")
        plt.axis('off')
        return plt

    def fit_regression(
        self,
        target: str,
        features: List[str],
        model_type: str = 'linear',
        link_function: Optional[Callable] = None,
        samples: int = 2000
    ) -> RegressionResult:
        """
        Fit a Bayesian linear or logistic regression of ``target`` on ``features``.

        Features are standardized (zero mean, unit variance) before fitting,
        so the coefficients are per standard deviation of each feature.

        Args:
            target: Target column name
            features: Feature column names
            model_type: 'linear' or 'logistic'
            link_function: Optional link function for the logistic model
            samples: Number of MCMC draws

        Returns:
            RegressionResult with coefficients, predictions, and intervals
        """
        import pymc as pm

        X = self.data[features].values
        y = self.data[target].values

        with pm.Model():
            X_standardized = (X - np.mean(X, axis=0)) / np.std(X, axis=0)

            alpha = pm.Normal('alpha', mu=0, sigma=10)
            betas = pm.Normal('betas', mu=0, sigma=2, shape=len(features))
            sigma = pm.HalfNormal('sigma', sigma=1)

            mu = alpha + pm.math.dot(X_standardized, betas)

            if model_type == 'linear':
                pm.Normal('y_obs', mu=mu, sigma=sigma, observed=y)
            elif model_type == 'logistic':
                p = pm.math.sigmoid(mu) if link_function is None else link_function(mu)
                pm.Bernoulli('y_obs', p=p, observed=y)
            else:
                raise ValueError(f"Unknown model type: {model_type}")

            trace = pm.sample(samples, tune=1000)

            coef_means = {}
            coef_stds = {}

            alpha_samples = trace.posterior['alpha'].values.flatten()
            coef_means['intercept'] = np.mean(alpha_samples)
            coef_stds['intercept'] = np.std(alpha_samples)

            beta_samples = trace.posterior['betas'].values.reshape(-1, len(features))
            for i, feature in enumerate(features):
                coef_means[feature] = np.mean(beta_samples[:, i])
                coef_stds[feature] = np.std(beta_samples[:, i])

            if model_type == 'linear':
                y_pred = coef_means['intercept'] + np.dot(X_standardized,
                                                          [coef_means[f] for f in features])
            else:
                linear_pred = coef_means['intercept'] + np.dot(X_standardized,
                                                               [coef_means[f] for f in features])
                y_pred = 1 / (1 + np.exp(-linear_pred))

            pred_samples = np.zeros((len(y), samples))
            for i in range(samples):
                alpha_i = alpha_samples[i]
                beta_i = beta_samples[i]
                pred_i = alpha_i + np.dot(X_standardized, beta_i)
                if model_type == 'logistic':
                    pred_i = 1 / (1 + np.exp(-pred_i))
                pred_samples[:, i] = pred_i

            pred_intervals = np.percentile(pred_samples, [2.5, 97.5], axis=1).T

            if model_type == 'linear':
                r2 = 1 - np.sum((y - y_pred) ** 2) / np.sum((y - np.mean(y)) ** 2)
            else:
                r2 = None

            r2_str = f"{r2:.3f}" if r2 is not None else "N/A"
            summary = (
                f"Bayesian {model_type.capitalize()} Regression Results\n"
                f"Number of observations: {len(y)}\n"
                f"Number of features: {len(features)}\n"
                f"R² Score: {r2_str}\n\n"
                "Coefficients:\n"
            )

            summary += f"{'Parameter':<20} {'Mean':>10} {'Std':>10}\n"
            summary += "-" * 40 + "\n"
            summary += f"{'Intercept':<20} {coef_means['intercept']:>10.3f} {coef_stds['intercept']:>10.3f}\n"
            for feature in features:
                summary += f"{feature:<20} {coef_means[feature]:>10.3f} {coef_stds[feature]:>10.3f}\n"

            coefficients = {
                name: (coef_means[name], coef_stds[name])
                for name in ['intercept'] + features
            }

            result = RegressionResult(
                coefficients=coefficients,
                predictions=y_pred,
                prediction_intervals=pred_intervals,
                r2_score=r2,
                model_summary=summary
            )

            self.regression_results[target] = result
            return result

    def plot_regression_results(
        self,
        target: str,
        feature: Optional[str] = None,
        show_intervals: bool = True
    ):
        """
        Plot regression results and return the matplotlib Figure.

        Args:
            target: Target variable name
            feature: Optional feature for a 2D plot against the target
            show_intervals: Whether to shade the prediction intervals
        """
        import matplotlib.pyplot as plt

        if target not in self.regression_results:
            raise ValueError(f"No regression results found for {target}")

        result = self.regression_results[target]
        fig, ax = plt.subplots(figsize=(10, 6))

        if feature is not None:
            x = self.data[feature].values
            y = self.data[target].values
            y_pred = np.asarray(result.predictions)

            sort_idx = np.argsort(x)
            x = x[sort_idx]
            y = y[sort_idx]
            y_pred = y_pred[sort_idx]

            ax.scatter(x, y, alpha=0.5, label='Actual')
            ax.plot(x, y_pred, 'r-', label='Predicted')

            if show_intervals and result.prediction_intervals is not None:
                intervals = result.prediction_intervals[sort_idx]
                ax.fill_between(x, intervals[:, 0], intervals[:, 1],
                                alpha=0.2, color='r', label='95% PI')

            ax.set_xlabel(feature)
            ax.set_ylabel(target)

        else:
            y = self.data[target].values
            y_pred = result.predictions

            ax.scatter(y, y_pred, alpha=0.5)

            min_val = min(min(y), min(y_pred))
            max_val = max(max(y), max(y_pred))
            ax.plot([min_val, max_val], [min_val, max_val], 'r--',
                    label='Perfect Prediction')

            ax.set_xlabel('Actual')
            ax.set_ylabel('Predicted')

        ax.set_title(f'Regression Results for {target}')
        ax.legend()
        ax.grid(True, alpha=0.3)

        return fig

    def visualize_causal_graph(self, show_effects: bool = True):
        """Draw the variable graph with the stored edge weights. Returns the matplotlib Figure."""
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(12, 8))
        pos = nx.spring_layout(self.graph)

        nx.draw_networkx_nodes(self.graph, pos, ax=ax, node_color='lightblue',
                               node_size=2000, alpha=0.7)
        nx.draw_networkx_labels(self.graph, pos)

        if show_effects:
            edge_labels = {}
            for u, v, data in self.graph.edges(data=True):
                if data.get('effect_size') is not None:
                    edge_labels[(u, v)] = f"{data['effect_size']:.2f}"

            nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=edge_labels)

        nx.draw_networkx_edges(self.graph, pos, ax=ax, edge_color='gray',
                               arrowsize=20)

        for target, result in self.regression_results.items():
            if target in pos:
                x, y = pos[target]
                text = f"\nR² = {result.r2_score:.2f}" if result.r2_score else ""
                ax.annotate(text, (x, y), xytext=(0, -20),
                            textcoords="offset points", ha='center')

        ax.set_title("Loss driver graph")
        ax.axis('off')

        return fig
