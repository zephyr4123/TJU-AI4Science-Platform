# Setup and Versions

## Verified Version Baseline

Checked against PyPI and official release notes on **2026-07-23**:

| Distribution | Verified version | Purpose | Python requirement |
|---|---:|---|---|
| `qiskit` | 2.5.0 | Core circuits, operators, transpiler, local statevector primitives | Python 3.10+ |
| `qiskit-ibm-runtime` | 0.48.0 | IBM Quantum Platform service and Runtime primitives | Python 3.10+ |
| `qiskit-aer` | 0.17.2 | High-performance and noisy simulation | See its PyPI metadata |
| `qiskit-algorithms` | 0.4.0 | VQE, QAOA, Grover, phase estimation, optimizers | Python 3.9+ |
| `qiskit-nature` | 0.8.0 | Quantum chemistry and second-quantized problems | Python 3.10+ |
| `qiskit-nature-pyscf` | 0.4.0 | PySCF integration for Qiskit Nature | Python 3.8+ |
| `qiskit-machine-learning` | 0.9.0 | Quantum kernels, QNNs, Torch integration | Python 3.10+ |
| `qiskit-optimization` | 0.7.0 | Quadratic programs and quantum optimizers | Python 3.9+ |

The Qiskit GitHub repository published a `2.5.1` patch release on 2026-07-23, but PyPI still served `2.5.0` when this skill was verified. Use the PyPI-available pin for reproducibility and check [sources.md](sources.md) before updating it.

## Create an Environment

The repository recommends Python 3.13. Qiskit 2.5 supports CPython 3.10 and newer on supported 64-bit platforms.

```bash
uv venv --python 3.13
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
uv venv --python 3.13
.venv\Scripts\Activate.ps1
```

Install the smallest useful set:

```bash
# Core SDK
uv pip install "qiskit==2.5.0"

# Core plus Matplotlib/LaTeX visualization dependencies
uv pip install "qiskit[visualization]==2.5.0"

# IBM QPUs and Runtime primitives
uv pip install "qiskit-ibm-runtime==0.48.0"

# High-performance and noisy simulation
uv pip install "qiskit-aer==0.17.2"
```

For a project, declare the same exact pins with `uv add`:

```bash
uv add "qiskit[visualization]==2.5.0"
uv add "qiskit-ibm-runtime==0.48.0"
uv add "qiskit-aer==0.17.2"
```

Do not install `qiskit-terra`. Since Qiskit 1.0, the `qiskit` distribution owns the complete `qiskit` package namespace. Aer and application packages remain separate distributions.

## Optional Application Packages

Install these only for the corresponding workflow:

```bash
uv pip install "qiskit-algorithms==0.4.0"
uv pip install "qiskit-nature==0.8.0" "qiskit-nature-pyscf==0.4.0"
uv pip install "qiskit-machine-learning==0.9.0"
uv pip install "qiskit-optimization==0.7.0"
```

Resolve all selected packages together in a fresh environment. Do not force-install incompatible distributions with dependency checks disabled.

## Verify the Environment

Use the bundled checker (flags: `--require-runtime --require-aer`, `--json`). `references/check_environment.py` checks the interpreter that runs it, so copy it into the experiment code and run it with the experiment's own Python; it makes no network calls and reads no credentials.

Or inspect versions directly:

```python
from importlib.metadata import version

for distribution in ("qiskit", "qiskit-ibm-runtime", "qiskit-aer"):
    try:
        print(distribution, version(distribution))
    except Exception:
        print(distribution, "not installed")
```

Run the local smoke test:

```bash
ai4sci skill run qiskit --script run_local_primitives.py --shots 256 --seed 7
```

## Local-Only Development

No account or network access is needed for:

- `StatevectorSampler`
- `StatevectorEstimator`
- `Statevector`, `DensityMatrix`, and other `qiskit.quantum_info` tools
- Qiskit Aer simulators
- fake backends bundled with `qiskit-ibm-runtime`

Use local primitives for algorithm logic, Aer for larger/noisy simulations, and fake backends for target-aware compilation tests.

## Repair a Broken Pre-1.0 Environment

Typical symptoms include:

- An error saying Qiskit is installed in an invalid environment.
- Both `qiskit-terra` and modern `qiskit` distributions are present.
- Imports resolve to files left behind by an old namespace-package installation.
- A notebook kernel uses a different Python interpreter from the activated environment.

The reliable repair is a new environment:

```bash
deactivate 2>/dev/null || true
uv venv --python 3.13 .venv-qiskit
source .venv-qiskit/bin/activate
uv pip install "qiskit[visualization]==2.5.0"
```

Avoid trying to repair a mixed pre-1.0 environment by repeatedly uninstalling individual packages; stale namespace files can remain.

Confirm the active interpreter:

```python
import sys
import qiskit

print(sys.executable)
print(qiskit.__version__)
print(qiskit.__file__)
```

## Upgrade Policy

For reproducible work:

1. Pin all Qiskit distributions.
2. Record Python, Qiskit, Runtime, Aer, and application-package versions with results.
3. Read the SDK and Runtime release notes before updating.
4. Re-run local primitive tests and transpilation snapshots.
5. Revalidate Runtime option names and execution-mode restrictions.
6. Upgrade in a new lockfile branch or environment, not in the middle of a paid QPU experiment.
