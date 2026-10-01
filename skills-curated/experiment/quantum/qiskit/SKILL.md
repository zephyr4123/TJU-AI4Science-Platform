---
name: qiskit
description: Build, simulate, and transpile quantum circuits with Qiskit. Use for Qiskit 2.x circuits and operators, V2 Sampler or Estimator primitives, target-aware transpilation against fake backends, local or noisy simulation with Aer, and Qiskit ecosystem packages.
license: Apache-2.0
compatibility: Python 3.10+ on a supported 64-bit platform. Local SDK workflows need qiskit; noisy simulation needs qiskit-aer; fake backends need qiskit-ibm-runtime.
metadata:
  version: "2.1"
  skill-author: K-Dense Inc.
---

# Qiskit

本 skill 目录里的其它文件用 `ai4sci skill show qiskit <相对路径>` 读。

Use current Qiskit 2.x APIs to build circuits, prepare hardware-compatible instruction set architecture (ISA) circuits, and execute them through V2 primitives.

This skill was verified on **2026-07-23** against the PyPI releases `qiskit==2.5.0`, `qiskit-ibm-runtime==0.48.0`, and `qiskit-aer==0.17.2`. Check [references/sources.md](references/sources.md) before changing pins or documenting newly released behavior.

## Choose the Right Path

| Goal | Recommended interface |
|---|---|
| Exact local sampling | `qiskit.primitives.StatevectorSampler` |
| Exact local expectation values | `qiskit.primitives.StatevectorEstimator` |
| High-performance or noisy simulation | Qiskit Aer |
| Backend without native primitives | `BackendSamplerV2` or `BackendEstimatorV2` |
| Open-system or master-equation dynamics | Prefer QuTiP |
| Differentiable quantum machine learning | Prefer PennyLane unless Qiskit integration is required |

## Installation

Create an isolated environment and install only the components needed:

```bash
uv venv --python 3.13
source .venv/bin/activate

# Core SDK plus plotting support
uv pip install "qiskit[visualization]==2.5.0"

# Add only when needed
uv pip install "qiskit-ibm-runtime==0.48.0"
uv pip install "qiskit-aer==0.17.2"
```

Do not install `qiskit-terra`; it was superseded by the `qiskit` distribution. Qiskit Runtime, Aer, Nature, Machine Learning, Optimization, and Algorithms are separate distributions.

For optional packages and environment repair, read [references/setup.md](references/setup.md).

## Core Workflow

Follow this sequence for every hardware-oriented workload:

1. **Map** the problem to a circuit and, for Estimator, one or more observables.
2. **Optimize** the parameterized circuit once for the selected backend.
3. **Apply the layout** to every observable.
4. **Execute** ISA circuits through a V2 primitive using Primitive Unified Blocs (PUBs).
5. **Analyze** register-aware results, metadata, uncertainty, and resource usage.

Do not bind and retranspile a parameterized circuit inside every optimizer iteration. Transpile the parameterized circuit once, then pass parameter arrays in PUBs.

## Quick Local Sampling

```python
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)
circuit.measure_all()  # creates the classical register named "meas"

sampler = StatevectorSampler(seed=7)
pub_result = sampler.run([circuit], shots=1024).result()[0]
counts = pub_result.data.meas.get_counts()
print(counts)
```

Sampler V2 preserves shots and classical-register structure. Access the register by its actual name; `measure_all()` uses `meas`.

## Quick Local Estimation

```python
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.primitives import StatevectorEstimator
from qiskit.quantum_info import SparsePauliOp

theta = Parameter("theta")
circuit = QuantumCircuit(2)
circuit.ry(theta, 0)
circuit.cx(0, 1)

observable = SparsePauliOp.from_list([("ZZ", 1.0), ("XX", 0.5)])
parameter_values = [[0.0], [np.pi / 4], [np.pi / 2]]

estimator = StatevectorEstimator(seed=7)
pub = (circuit, observable, parameter_values)
pub_result = estimator.run([pub]).result()[0]
print(pub_result.data.evs)
```

Estimator circuits should not contain final measurements. PUB arrays broadcast; verify circuit parameter order before constructing large sweeps.

## Non-Negotiable Qiskit 2.x Rules

- Use V2 primitive interfaces and PUB inputs. Do not write new V1 `Sampler`, `Estimator`, or `QuantumInstance` code.
- Runtime primitives accept ISA circuits; they do not perform layout, routing, and basis translation for you.
- Apply the transpiler layout to Estimator observables with `observable.apply_layout(isa_circuit.layout)`.
- Use `mode=backend`, `mode=session`, or `mode=batch` for Runtime primitives.
- Use `EstimatorV2` for resilience levels and expectation-value mitigation. Sampler has different noise-management options and no Estimator-style resilience levels.
- Treat `BackendV2.target`, `backend.operation_names`, `backend.coupling_map`, and direct backend attributes as the source of hardware constraints. Do not use `backend.configuration()` or `BackendProperties`.
- Read Sampler output by classical register name. Bitstrings are displayed most-significant bit first; Qiskit qubit 0 is conventionally the least-significant bit.
- Use a fixed `seed_transpiler` when comparing compilation settings. A simulator seed does not make QPU results deterministic.
- `qiskit.pulse` was removed in Qiskit 2.0. Use supported fractional gates for IBM hardware or Qiskit Dynamics for pulse-model research.
- QPY is the Qiskit-native circuit serialization format. Do not use Python pickle for untrusted circuit artifacts.

See [references/migration.md](references/migration.md) for a detailed old-to-current API map.

## Reference Map

Read only the files needed for the current task:

| Topic | Reference |
|---|---|
| Versions, installation, environment repair | [references/setup.md](references/setup.md) |
| Circuits, parameters, control flow, QPY | [references/circuits.md](references/circuits.md) |
| V2 PUBs, broadcasting, local and Runtime results | [references/primitives.md](references/primitives.md) |
| Targets, ISA circuits, layouts, pass managers | [references/transpilation.md](references/transpilation.md) |
| Backends, Runtime local-testing modes, Aer, fake backends, mitigation | [references/backends.md](references/backends.md) |
| End-to-end map/optimize/execute/analyze patterns | [references/patterns.md](references/patterns.md) |
| Algorithms, addons, Nature, ML, Optimization | [references/algorithms.md](references/algorithms.md) |
| Circuit, result, state, and backend plots | [references/visualization.md](references/visualization.md) |
| Qiskit 0.x/1.x and Runtime migration | [references/migration.md](references/migration.md) |
| Testing, reproducibility, and troubleshooting | [references/testing.md](references/testing.md) |
| Upstream docs, release notes, and version baseline | [references/sources.md](references/sources.md) |

## Bundled Scripts

```bash
# Runnable V2 local Sampler and Estimator example
ai4sci skill run qiskit --script run_local_primitives.py --shots 1024 --seed 7
```

Installed-package and legacy-environment checks: `references/check_environment.py` checks the interpreter that runs it, so copy it into the experiment code and run it with the experiment's own Python; it makes no network calls and reads no credentials.

## Final Checklist

Before returning Qiskit code:

1. Confirm package versions and Python compatibility.
2. Run locally with statevector primitives or Aer.
3. Verify parameter order, observable qubit count, and classical-register names.
4. Transpile against the exact `BackendV2` target and inspect depth and two-qubit operations.
5. Apply the final layout to every observable.
6. Save job IDs, package versions, seeds, backend name, primitive options, and result metadata.
