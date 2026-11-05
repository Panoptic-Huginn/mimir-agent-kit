# SPARK Ada 2022 Toolchain Switches & Workflow Commands

Reference compiler switches (`package Compiler` in `.gpr`), `gnatprove` switches (`package Prove` in `.gpr`), and standard `alr` CLI commands for GNAT FSF 16.1+ and GNATprove 16.1+.

---

## Required GNAT Compiler & Proof Switches

In addition to Alire's default switches, safety-critical SPARK projects must enable:

```text
-- Compiler switches (package Compiler in .gpr):
-gnat2022                 -- Enforce ISO Ada 2022 standard
-gnatW8                   -- UTF-8 source encoding
-gnatwa -gnatwe           -- Enable all standard warnings and treat warnings as errors
-gnatw.X                  -- Suppress warnings when No_Exception_Propagation is active
-gnatVa                   -- Enable all validity checks (essential at C/DMA boundaries)
-gnato13                  -- Strict overflow checking (or proven away via gnatprove)
-gnata                    -- Enable runtime assertions/contracts in development & validation profiles
-gnaty3aAbBcefhiIklnOprStux -gnaty-d -gnatyM100 -- Strict GNAT style checks (100-col max)
-ffunction-sections -fdata-sections -fcallgraph-info=su,da

-- GNATprove switches (package Prove in .gpr):
--mode=all                -- Run Stone + Bronze (flow) + Silver (AoRTE) + Gold (contracts)
--level=2                 -- Level 2 for fast dev iteration (--level=4 for CI/Safety gates)
--prover=cvc5,z3,altergo  -- Portfolio SMT solvers
--warnings=error          -- Fail verification on any flow/proof warning
--report=all              -- Emit full assurance report in obj/gnatprove/gnatprove.out
-j0                       -- Use all available CPU cores
```

---

## Standard Workflow Commands

Always execute build, proof, and formatting commands via `alr`:

```bash
# 1. Select / verify toolchain (first-time setup on macOS or Ubuntu)
alr toolchain --select gnat_native gprbuild

# 2. Add formal verification & companion libraries to a project
alr with gnatprove
alr with sparklib

# 3. Compile with full assertions & runtime validity checks
alr build --validation

# 4. Run formal deductive verification (Silver + Gold proofs)
alr gnatprove --level=2 -j0
# For exhaustive CI / safety sign-off:
alr gnatprove --level=4 --prover=cvc5,z3,altergo --warnings=error --report=all -j0

# 5. Format Ada/SPARK sources
alr exec -- gnatformat -P <project_name>.gpr
```
