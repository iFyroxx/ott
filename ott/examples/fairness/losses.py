# coding=utf-8
"""Losses for the fairness example."""

import functools

import jax
import jax.numpy as jnp
import ott


def binary_cross_entropy(logits, labels):
  return jnp.sum(
      -labels * jnp.log(logits) - (1 - labels) * jnp.log(1 - logits))


def compute_metrics(logits, labels):
  loss = binary_cross_entropy(logits, labels)
  accuracy = jnp.mean((logits > 0.5) == labels)
  metrics = {
      'loss': loss,
      'accuracy': accuracy,
  }
  metrics = jax.lax.pmean(metrics, axis_name='batch')
  return metrics


@functools.partial(jax.jit, static_argnums=(2, 3))
def sort_group(inputs: jnp.ndarray,
               in_group: jnp.ndarray,
               quantization: int,
               epsilon: float):
  """Sorts and quantizes only the member of the given group.

  Args:
    inputs: 1D array to be sorted.
    in_group: a 1D array of 0s and 1s indicating if the element is part of the
      group or not.
    quantization: the number of values the sorted values output should be mapped
      onto.
    epsilon: sinkhorn entropic regularization.

  Returns:
    A sorted array of size `quantization`.
  """
  a = in_group / jnp.sum(in_group)
  b = jnp.ones(quantization) / quantization
  ot = ott.tools.soft_sort.transport_for_sort(
      inputs, a, b, dict(epsilon=epsilon))
  return 1.0 / b * ot.apply(inputs, axis=0)


def fairness_regularizer(inputs: jnp.ndarray,
                         groups: jnp.ndarray,
                         quantization: int = 16,
                         epsilon: float = 1e-2,
                         num_groups: int = 2):
  """Approximation of the wasserstein between the per-group distributions."""
  quantiles = jnp.stack([sort_group(inputs, groups == g, quantization, epsilon)
                         for g in range(num_groups)])
  weights = jnp.stack(
      [jnp.sum(groups == g) for g in range(num_groups)]) / groups.shape[0]
  mean_quantile = jnp.sum(weights[:, None] * quantiles, axis=0)
  delta = jnp.where(quantiles,
                    quantiles - mean_quantile,
                    jnp.zeros_like(mean_quantile))
  return jnp.mean(delta ** 2)

