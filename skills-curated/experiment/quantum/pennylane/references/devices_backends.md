# Devices and Backends in PennyLane

## Table of Contents
1. [Built-in Simulators](#built-in-simulators)
2. [Simulator Plugins](#simulator-plugins)
3. [Device Selection](#device-selection)
4. [Device Configuration](#device-configuration)
5. [Custom Devices](#custom-devices)
6. [Performance Optimization](#performance-optimization)

## Built-in Simulators

### default.qubit

General-purpose state vector simulator:

```python
import pennylane as qml

# Basic initialization
dev = qml.device('default.qubit', wires=4)

# For sampling mode, set shots on the QNode with qml.set_shots
dev = qml.device('default.qubit', wires=4)

# Specify wire labels
dev = qml.device('default.qubit', wires=['a', 'b', 'c', 'd'])
```

### default.mixed

Mixed-state simulator for noisy quantum systems:

```python
# Supports density matrix simulation
dev = qml.device('default.mixed', wires=2)

@qml.qnode(dev)
def noisy_circuit():
    qml.Hadamard(wires=0)

    # Apply noise
    qml.DepolarizingChannel(0.1, wires=0)

    qml.CNOT(wires=[0, 1])

    # Amplitude damping
    qml.AmplitudeDamping(0.05, wires=1)

    return qml.expval(qml.PauliZ(0))
```

### Machine Learning Interfaces

Use `default.qubit` with the QNode interface for PyTorch or JAX. The old interface-specific device names are not needed in current PennyLane examples, and TensorFlow support is no longer maintained as of PennyLane v0.44.

```python
# PyTorch
dev = qml.device('default.qubit', wires=4)

@qml.qnode(dev, interface="torch")
def torch_circuit(weights):
    qml.RX(weights[0], wires=0)
    return qml.expval(qml.Z(0))
```

### lightning.qubit

High-performance C++ simulator:

```python
# Faster than default.qubit
dev = qml.device('lightning.qubit', wires=20)

# Supports larger systems efficiently
@qml.qnode(dev)
def large_circuit():
    for i in range(20):
        qml.Hadamard(wires=i)

    for i in range(19):
        qml.CNOT(wires=[i, i+1])

    return qml.expval(qml.PauliZ(0))
```

### default.clifford

Efficient simulator for Clifford circuits:

```python
# Only supports Clifford gates (H, S, CNOT, etc.)
dev = qml.device('default.clifford', wires=100)

@qml.qnode(dev)
def clifford_circuit():
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    qml.S(wires=1)
    # Cannot use RX, RY, RZ, etc.

    return qml.expval(qml.PauliZ(0))
```

## Simulator Plugins

Cloud QPU and managed-simulator access (IBM Quantum, Amazon Braket managed devices, IonQ, Rigetti QPU, Xanadu) needs a provider account and is not covered by this skill; everything here runs on local simulators.

### Qiskit Aer

```bash
# Install plugin
uv pip install "pennylane-qiskit==0.45.0"
```

```python
import pennylane as qml

# Use the Qiskit Aer simulator
dev = qml.device('qiskit.aer', wires=2)

@qml.qnode(dev)
def circuit():
    qml.Hadamard(wires=0)
    qml.CNOT(wires=[0, 1])
    return qml.expval(qml.PauliZ(0))

sampled_circuit = qml.set_shots(circuit, shots=1024)
```

### Amazon Braket (local simulator)

```bash
# Install plugin
uv pip install "amazon-braket-pennylane-plugin==1.34.1"
```

```python
# Use the Braket local simulator
dev = qml.device(
    'braket.local.qubit',
    wires=2
)
```

### Google Cirq

```bash
# Install plugin
uv pip install "pennylane-cirq==0.44.0"
```

```python
# Use Cirq simulator
dev = qml.device('cirq.simulator', wires=2)

# Use Cirq with qsim (faster)
dev = qml.device('cirq.qsim', wires=20)
```

## Device Selection

### Choosing the Right Device

```python
def select_device(n_qubits, noise_model=None):
    """Select appropriate device based on requirements."""

    if noise_model:
        # Use noisy simulator
        return qml.device('default.mixed', wires=n_qubits)

    else:
        # Use ideal simulator
        if n_qubits <= 20:
            return qml.device('lightning.qubit', wires=n_qubits)
        else:
            return qml.device('default.qubit', wires=n_qubits)

# Usage
dev = select_device(n_qubits=10)
```

### Device Capabilities

```python
# Check device capabilities
dev = qml.device('default.qubit', wires=4)

print("Device name:", dev.name)
print("Number of wires:", dev.num_wires)
print("Supports shots:", dev.shots is not None)

# Check supported operations
print("Supported gates:", dev.operations)

# Check supported observables
print("Supported observables:", dev.observables)
```

## Device Configuration

### Setting Shots

```python
# Exact simulation (no shots)
dev = qml.device('default.qubit', wires=2)

@qml.qnode(dev)
def exact_circuit():
    qml.Hadamard(wires=0)
    return qml.expval(qml.PauliZ(0))

result = exact_circuit()  # Returns exact expectation

# Sampling mode (with shots)
dev_sampled = qml.device('default.qubit', wires=2)

@qml.set_shots(1000)
@qml.qnode(dev_sampled)
def sampled_circuit():
    qml.Hadamard(wires=0)
    return qml.expval(qml.PauliZ(0))

result = sampled_circuit()  # Estimated from samples
```

### Dynamic Shots

```python
# Change shots per execution
dev = qml.device('default.qubit', wires=2)

@qml.qnode(dev)
def circuit():
    qml.Hadamard(wires=0)
    return qml.expval(qml.PauliZ(0))

# Different shot numbers
result_100 = qml.set_shots(circuit, shots=100)()
result_1000 = qml.set_shots(circuit, shots=1000)()
result_exact = qml.set_shots(circuit, shots=None)()  # Exact
```

### Analytic Mode vs Finite Shots

```python
# Compare analytic vs sampled
dev_analytic = qml.device('default.qubit', wires=2)
dev_sampled = qml.device('default.qubit', wires=2)

@qml.qnode(dev_analytic)
def circuit_analytic(x):
    qml.RX(x, wires=0)
    return qml.expval(qml.PauliZ(0))

@qml.qnode(dev_sampled)
def circuit_sampled(x):
    qml.RX(x, wires=0)
    return qml.expval(qml.PauliZ(0))

import numpy as np
x = np.pi / 4

print(f"Analytic: {circuit_analytic(x)}")
print(f"Sampled: {qml.set_shots(circuit_sampled, shots=1000)(x)}")
print(f"Exact value: {np.cos(x)}")
```

### Seed for Reproducibility

```python
# Set random seed
dev = qml.device('default.qubit', wires=2, seed=42)

@qml.set_shots(1000)
@qml.qnode(dev)
def circuit():
    qml.Hadamard(wires=0)
    return qml.sample(qml.PauliZ(0))

# Reproducible results
samples1 = circuit()
samples2 = circuit()  # Same as samples1 if seed is set
```

## Custom Devices

### Creating a Custom Device

```python
from pennylane.devices import DefaultQubit

class CustomDevice(DefaultQubit):
    """Custom quantum device with additional features."""

    name = 'Custom device'
    short_name = 'custom'
    pennylane_requires = '>=0.30.0'
    version = '0.1.0'
    author = 'Your Name'

    def __init__(self, wires, shots=None, **kwargs):
        super().__init__(wires=wires, shots=shots)
        # Custom initialization

    def apply(self, operations, **kwargs):
        """Apply operations with custom logic."""
        # Custom operation handling
        for op in operations:
            # Log or modify operations
            print(f"Applying: {op.name}")

        # Call parent implementation
        super().apply(operations, **kwargs)

# Use custom device
dev = CustomDevice(wires=4)
```

### Plugin Development

```python
# Define custom plugin operations
class CustomGate(qml.operation.Operation):
    """Custom quantum gate."""

    num_wires = 1
    num_params = 1
    par_domain = 'R'

    def decomposition(self):
        """Decompose into standard gates."""
        theta = self.parameters[0]
        wires = self.wires

        return [
            qml.RY(theta / 2, wires=wires),
            qml.RZ(theta, wires=wires),
            qml.RY(-theta / 2, wires=wires)
        ]

# Register with device
qml.ops.CustomGate = CustomGate
```

## Performance Optimization

### Batch Execution

```python
# Execute multiple parameter sets efficiently
dev = qml.device('default.qubit', wires=2)

@qml.qnode(dev)
def circuit(params):
    qml.RX(params[0], wires=0)
    qml.RY(params[1], wires=1)
    qml.CNOT(wires=[0, 1])
    return qml.expval(qml.PauliZ(0))

# Batch parameters
params_batch = np.random.random((100, 2))

# Vectorized execution (faster)
results = [circuit(p) for p in params_batch]
```

### Device Caching

```python
# Cache device for reuse
_device_cache = {}

def get_device(n_qubits, device_type='default.qubit'):
    """Get or create cached device."""
    key = (device_type, n_qubits)

    if key not in _device_cache:
        _device_cache[key] = qml.device(device_type, wires=n_qubits)

    return _device_cache[key]

# Reuse devices
dev1 = get_device(4)
dev2 = get_device(4)  # Returns same device
```

### JIT Compilation with Catalyst

```python
# Install Catalyst
# uv pip install "pennylane-catalyst==0.15.0"

import pennylane as qml
from catalyst import qjit

dev = qml.device('lightning.qubit', wires=4)

@qjit  # Just-in-time compilation
@qml.qnode(dev)
def compiled_circuit(x):
    qml.RX(x, wires=0)
    qml.Hadamard(wires=1)
    qml.CNOT(wires=[0, 1])
    return qml.expval(qml.PauliZ(0))

# First call compiles, subsequent calls are fast
result = compiled_circuit(0.5)
```

### Parallel Execution

```python
from multiprocessing import Pool

def run_circuit(params):
    """Run circuit with given parameters."""
    dev = qml.device('default.qubit', wires=4)

    @qml.qnode(dev)
    def circuit(p):
        # Circuit definition
        return qml.expval(qml.PauliZ(0))

    return circuit(params)

# Parallel execution
param_list = [np.random.random(10) for _ in range(100)]

with Pool(processes=4) as pool:
    results = pool.map(run_circuit, param_list)
```

### GPU Acceleration

```python
# Use GPU-accelerated devices if available
try:
    dev = qml.device('lightning.gpu', wires=20)
except Exception:
    dev = qml.device('lightning.qubit', wires=20)

@qml.qnode(dev)
def gpu_circuit():
    # Large circuit benefits from GPU
    for i in range(20):
        qml.Hadamard(wires=i)

    for i in range(19):
        qml.CNOT(wires=[i, i+1])

    return [qml.expval(qml.PauliZ(i)) for i in range(20)]
```

## Best Practices

1. **Start with simulators** - Test on `default.qubit` before hardware
2. **Use lightning for speed** - Switch to `lightning.qubit` for larger circuits
3. **Match device to task** - Use `default.mixed` for noise studies
4. **Cache devices** - Reuse device objects to avoid initialization overhead
5. **Set appropriate shots** - Balance accuracy vs speed
6. **Check capabilities** - Verify device supports required operations
7. **Use JIT when possible** - Compile circuits with Catalyst for speedup

## Device Comparison

| Device | Type | Max Qubits | Speed | Noise | Use Case |
|--------|------|-----------|-------|-------|----------|
| default.qubit | Simulator | ~25 | Medium | No | General purpose |
| lightning.qubit | Simulator | ~30 | Fast | No | Large circuits |
| default.mixed | Simulator | ~15 | Slow | Yes | Noise studies |
| default.clifford | Simulator | 100+ | Very fast | No | Clifford circuits |
