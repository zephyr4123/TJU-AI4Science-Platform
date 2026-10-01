# Hardware Integration

This guide covers designing circuits for real quantum hardware through Cirq's device interfaces: device models, qubit topology, and hardware-aware compilation.

## Device Representation

### Device Classes

```python
import cirq

# Define device with connectivity
class MyDevice(cirq.Device):
    def __init__(self, qubits, connectivity):
        self.qubits = qubits
        self.connectivity = connectivity

    @property
    def metadata(self):
        return cirq.DeviceMetadata(
            self.qubits,
            self.connectivity
        )

    def validate_operation(self, operation):
        # Check if operation is valid on this device
        if len(operation.qubits) == 2:
            q0, q1 = operation.qubits
            if (q0, q1) not in self.connectivity:
                raise ValueError(f"Qubits {q0} and {q1} not connected")
```

### Device Constraints

```python
# Check device metadata
device = cirq_google.Sycamore

# Get qubit topology
qubits = device.metadata.qubit_set
print(f"Available qubits: {len(qubits)}")

# Check connectivity
for q0 in qubits:
    neighbors = device.metadata.nx_graph.neighbors(q0)
    print(f"{q0} connected to: {list(neighbors)}")

# Validate circuit against device
try:
    device.validate_circuit(circuit)
    print("Circuit is valid for device")
except ValueError as e:
    print(f"Invalid circuit: {e}")
```

## Qubit Selection

### Topology-Aware Selection

```python
def select_connected_qubits(device, n_qubits):
    """Select connected qubits forming a path or grid."""
    graph = device.metadata.nx_graph

    # Find connected subgraph
    import networkx as nx
    for node in graph.nodes():
        subgraph = nx.ego_graph(graph, node, radius=n_qubits)
        if len(subgraph) >= n_qubits:
            return list(subgraph.nodes())[:n_qubits]

    raise ValueError(f"Could not find {n_qubits} connected qubits")
```

## Hardware Best Practices

### Circuit Optimization for Hardware

```python
def optimize_for_hardware(circuit, device):
    """Optimize circuit for specific hardware."""
    from cirq.transformers import (
        optimize_for_target_gateset,
        merge_single_qubit_gates_to_phxz,
        drop_negligible_operations
    )

    # Get device gateset
    if hasattr(device, 'gateset'):
        gateset = device.gateset
    else:
        gateset = cirq.CZTargetGateset()  # Default

    # Optimize
    circuit = merge_single_qubit_gates_to_phxz(circuit)
    circuit = drop_negligible_operations(circuit)
    circuit = optimize_for_target_gateset(circuit, gateset=gateset)

    return circuit
```

### Error Mitigation

```python
def run_with_readout_error_mitigation(circuit, sampler, repetitions):
    """Mitigate readout errors using calibration."""

    # Measure readout error
    cal_circuits = []
    for state in range(2**len(circuit.qubits)):
        cal_circuit = cirq.Circuit()
        for i, q in enumerate(circuit.qubits):
            if state & (1 << i):
                cal_circuit.append(cirq.X(q))
        cal_circuit.append(cirq.measure(*circuit.qubits, key='m'))
        cal_circuits.append(cal_circuit)

    # Run calibration
    cal_results = [sampler.run(c, repetitions=1000) for c in cal_circuits]

    # Build confusion matrix
    # ... (implementation details)

    # Run actual circuit
    result = sampler.run(circuit, repetitions=repetitions)

    # Apply correction
    # ... (apply inverse of confusion matrix)

    return result
```

### Job Management

```python
def submit_jobs_in_batches(circuits, sampler, batch_size=10):
    """Submit multiple circuits in batches."""
    jobs = []

    for i in range(0, len(circuits), batch_size):
        batch = circuits[i:i+batch_size]
        job_ids = []

        for circuit in batch:
            job = sampler.run_async(circuit, repetitions=1000)
            job_ids.append(job)

        jobs.extend(job_ids)

    # Wait for all jobs
    results = [job.result() for job in jobs]
    return results
```

## Device Specifications

### Checking Device Capabilities

```python
def print_device_info(device):
    """Print device capabilities and constraints."""

    print(f"Device: {device}")
    print(f"Number of qubits: {len(device.metadata.qubit_set)}")

    # Gate support
    print("\nSupported gates:")
    if hasattr(device, 'gateset'):
        for gate in device.gateset.gates:
            print(f"  - {gate}")

    # Connectivity
    print("\nConnectivity:")
    graph = device.metadata.nx_graph
    print(f"  Edges: {graph.number_of_edges()}")
    print(f"  Average degree: {sum(dict(graph.degree()).values()) / graph.number_of_nodes():.2f}")

    # Duration constraints
    if hasattr(device, 'gate_durations'):
        print("\nGate durations:")
        for gate, duration in device.gate_durations.items():
            print(f"  {gate}: {duration}")
```

## Best Practices

1. **Validate circuits before submission**: Use device.validate_circuit()
2. **Optimize for target hardware**: Decompose to native gates
3. **Select best qubits**: Use calibration data for qubit selection
4. **Monitor job status**: Check job completion before retrieving results
5. **Implement error mitigation**: Use readout error correction
6. **Batch jobs efficiently**: Submit multiple circuits together
7. **Respect rate limits**: Follow provider-specific API limits
8. **Store results**: Save expensive hardware results immediately
9. **Test on simulators first**: Validate on simulators before hardware
10. **Keep circuits shallow**: Hardware has limited coherence times
