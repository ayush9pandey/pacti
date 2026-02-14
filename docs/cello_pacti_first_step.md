# First step to reproduce Cello behavior in Pacti

If your goal is to "do what Cello does, but with Pacti contracts," the **first practical step** is:

## Build a minimal, testable bridge from one Cello gate record to one Pacti contract

Do **not** start with full Verilog parsing or full search/assignment yet. Instead, create a tiny end-to-end slice that proves you can encode one characterized gate from Cello's library as a Pacti contract.

---

## Why this is the right first step

Cello's pipeline has many stages (Verilog parsing, logic synthesis, gate assignment, scoring, layout). The contract-centric part starts where Cello uses experimentally characterized gate response functions and signal compatibility.

A single-gate bridge lets you validate:

1. How Cello gate parameters map to Pacti input/output variables.
2. How to represent analog signal constraints (REU ranges) as assumptions/guarantees.
3. How to compose multiple contracts later for circuit-level checking.

---

## Concrete milestone (M0)

Implement a script/notebook that:

1. Loads one gate's response function parameters (e.g., `ymin`, `ymax`, `K`, `n`) from a Cello-style source.
2. Creates a **piecewise linear over/under approximation** of that response function over a chosen input domain.
3. Emits a `PolyhedralIoContract` with:
   - Input variable: upstream REU signal (e.g., `x_in`)
   - Output variable: gate output REU (e.g., `x_out`)
   - Assumptions: valid input range segment
   - Guarantees: linear bounds on output for that segment
4. Verifies numerically on sample points that true response stays inside contract bounds.

A successful M0 means you can mechanize contract extraction for a gate library.

---

## Immediate follow-up (M1)

After M0, do exactly one composition test:

- Build a toy 2-input AND implementation from NOT + NOR gates.
- Compose contracts for the assigned gates.
- Check that the composed contract preserves expected high/low output separation under assumed input ranges.

This mirrors the Cello "response function matching" step in contract form.

---

## Suggested repository contribution plan

1. Add a focused design note under `docs/` describing the contract model for Cello gates.
2. Add one executable example under `examples/` that converts one gate model to one contract.
3. Add a unit test under `tests/` for enclosure correctness of the linear approximation.

Keep this first PR small and scoped to M0.

---

## Questions to answer before implementation (interactive checklist)

To move fast without rework, decide these up front:

1. **Source format**: Which Cello data source do you want as initial truth (UCF JSON, exported table, or hand-curated CSV)?
2. **Signal domain**: Work in linear REU or log10(REU)?
3. **Error policy**: Do you need strict sound over-approximation guarantees, or is bounded empirical error acceptable initially?
4. **Granularity**: How many linear segments per gate for M0 (e.g., 4, 8, 16)?
5. **Goal metric**: What does success mean for first PR (e.g., max relative error < 10%, or binary high/low separability only)?

---

## One-sentence first step

**Import one characterized Cello gate into a normalized table and generate one validated Pacti `PolyhedralIoContract` from it.**
