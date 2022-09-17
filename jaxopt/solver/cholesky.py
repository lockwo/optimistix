class Cholesky(AbstractLinearSolver):
  def init(self, operator, options):
    del options
    if operator.in_size() != operator.out_size():
      raise ValueError("`Cholesky` may only be used for linear solves with square matrices")
    if not operator.symmetric:
      raise ValueError("`Cholesky` may only be used for symmetric linear operators")
    # Fix lower triangular, so that the boolean flag doesn't get needlessly promoted
    # to a tracer anywhere.
    factor, lower = jsp.linalg.cho_factor(operator.as_matrix())
    assert lower is False
    return factor

  def solve(self, state, vector, options):
    del options
    vector, unflatten = jfu.ravel_pytree(vector)
    return unflatten(jsp.linalg.cho_solve((state, False), vector))
