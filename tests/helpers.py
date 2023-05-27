import functools as ft
import operator
import random

import jax
import jax.numpy as jnp
import jax.random as jr
import jax.tree_util as jtu
import lineax as lx
import numpy as np
from equinox.internal import ω


def getkey():
    return jr.PRNGKey(random.randint(0, 2**31 - 1))


def _shaped_allclose(x, y, **kwargs):
    if type(x) is not type(y):
        return False
    if isinstance(x, jnp.ndarray):
        if jnp.issubdtype(x.dtype, jnp.inexact):
            return (
                x.shape == y.shape
                and x.dtype == y.dtype
                and jnp.allclose(x, y, **kwargs)
            )
        else:
            return x.shape == y.shape and x.dtype == y.dtype and jnp.all(x == y)
    elif isinstance(x, np.ndarray):
        if np.issubdtype(x.dtype, np.inexact):
            return (
                x.shape == y.shape
                and x.dtype == y.dtype
                and np.allclose(x, y, **kwargs)
            )
        else:
            return x.shape == y.shape and x.dtype == y.dtype and np.all(x == y)
    elif isinstance(x, jax.ShapeDtypeStruct):
        assert x.shape == y.shape and x.dtype == y.dtype
    else:
        return x == y


def shaped_allclose(x, y, **kwargs):
    """As `jnp.allclose`, except:
    - It also supports PyTree arguments.
    - It mandates that shapes match as well (no broadcasting)
    """
    same_structure = jtu.tree_structure(x) == jtu.tree_structure(y)
    allclose = ft.partial(_shaped_allclose, **kwargs)
    return same_structure and jtu.tree_reduce(
        operator.and_, jtu.tree_map(allclose, x, y), True
    )


def finite_difference_jvp(fn, primals, tangents):
    out = fn(*primals)
    # Choose ε to trade-off truncation error and floating-point rounding error.
    max_leaves = [jnp.max(jnp.abs(p)) for p in jtu.tree_leaves(primals)] + [1]
    scale = jnp.max(jnp.stack(max_leaves))
    ε = np.sqrt(np.finfo(np.float64).eps) * scale
    primals_ε = (ω(primals) + ε * ω(tangents)).ω
    out_ε = fn(*primals_ε)
    tangents_out = jtu.tree_map(lambda x, y: (x - y) / ε, out_ε, out)
    return out, tangents_out


def has_tag(tags, tag):
    return tag is tags or (isinstance(tags, tuple) and tag in tags)


make_operators = []


def _operators_append(x):
    make_operators.append(x)
    return x


@_operators_append
def make_matrix_operator(matrix, tags):
    return lx.MatrixLinearOperator(matrix, tags)


@_operators_append
def make_trivial_pytree_operator(matrix, tags):
    out_size, _ = matrix.shape
    struct = jax.ShapeDtypeStruct((out_size,), matrix.dtype)
    return lx.PyTreeLinearOperator(matrix, struct, tags)


@_operators_append
def make_function_operator(matrix, tags):
    fn = lambda x: matrix @ x
    _, in_size = matrix.shape
    in_struct = jax.ShapeDtypeStruct((in_size,), matrix.dtype)
    return lx.FunctionLinearOperator(fn, in_struct, tags)


@_operators_append
def make_jac_operator(matrix, tags):
    out_size, in_size = matrix.shape
    x = jr.normal(getkey(), (in_size,))
    a = jr.normal(getkey(), (out_size,))
    b = jr.normal(getkey(), (out_size, in_size))
    c = jr.normal(getkey(), (out_size, in_size))
    fn_tmp = lambda x, _: a + b @ x + c @ x**2
    jac = jax.jacfwd(fn_tmp)(x, None)
    diff = matrix - jac
    fn = lambda x, _: a + (b + diff) @ x + c @ x**2
    return lx.JacobianLinearOperator(fn, x, None, tags)


@_operators_append
def make_diagonal_operator(matrix, tags):
    assert has_tag(tags, lx.diagonal_tag)
    diag = jnp.diag(matrix)
    return lx.DiagonalLinearOperator(diag)


@_operators_append
def make_add_operator(matrix, tags):
    matrix1 = 0.7 * matrix
    matrix2 = 0.3 * matrix
    operator = make_matrix_operator(matrix1, ()) + make_function_operator(matrix2, ())
    return lx.TaggedLinearOperator(operator, tags)


@_operators_append
def make_mul_operator(matrix, tags):
    operator = make_jac_operator(0.7 * matrix, ()) / 0.7
    return lx.TaggedLinearOperator(operator, tags)


@_operators_append
def make_composed_operator(matrix, tags):
    _, size = matrix.shape
    diag = jr.normal(getkey(), (size,))
    diag = jnp.where(jnp.abs(diag) < 0.05, 0.8, diag)
    operator1 = make_trivial_pytree_operator(matrix / diag, ())
    operator2 = lx.DiagonalLinearOperator(diag)
    return lx.TaggedLinearOperator(operator1 @ operator2, tags)
