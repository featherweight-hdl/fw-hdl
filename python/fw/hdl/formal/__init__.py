"""Formal SVUnit: prove an SVUnit test for every input (``formal-svunit.md``).

The same test file runs dynamically, at every level, and formally:

* :mod:`.lift` lifts an SVUnit test body to one static-subset IR function: the
  free inputs (``std::randomize``, class ``randomize()``) become its arguments,
  their constraints an *assume* bit, and each reached SVUnit ``fail()`` an
  obligation bit;
* :mod:`.smt` prints the lowered XLS IR as SMT-LIB2 QF_BV;
* :mod:`.prove` asks the solver (dv-solve) whether any input satisfying the
  assumptions reaches a failure.
"""
