
import math

import numpy as np
import matplotlib.pyplot as plt

from qiskit import QuantumCircuit, transpile, qpy
from qiskit.quantum_info import random_unitary, Statevector, Operator
from qiskit.visualization import plot_histogram

from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2 as Sampler
from qiskit_aer.noise import NoiseModel, depolarizing_error

from circuit_utils import random_circuit, create_noise_model, generate_emp_distribution


def calculate_true_distribution(qc: QuantumCircuit):
    """
    Calculates the true output distribution of a quantum circuit.

    Note:
        Any measurements must be applied before calling this function, as
        they will be removed internally to extract the pure statevector.

    Args:
        qc (QuantumCircuit): A quantum circuit (with or without measurements).

    Returns:
        dict: A full probability distribution over basis states (including zero-probability outcomes).
    """

    # Remove final measurements to extract the pure statevector
    qc.remove_final_measurements()
    
    # Simulate the quantum circuit to get the statevector
    statevector = Statevector(qc)
    probabilities = statevector.probabilities()

    # Generate all basis states in lexicographic order (e.g., '000', '001', ...)
    num_qubits = qc.num_qubits
    basis_states = []
    for i in range(2 ** num_qubits):
        bitstring = format(i, f'0{num_qubits}b')
        basis_states.append(bitstring)

    # Map each basis state to its corresponding probability
    true_distribution = {
        basis_states[i]: probabilities[i] for i in range(len(probabilities))
    }

    return true_distribution

# Debugging function to make sure prob distributions sum up to around 1.
# should be called with probability distributions.
def check_distribution_normalization(distribution):
    """
    Checks if the given probability distribution sums to 1 (within a tolerance).
    
    Args:
        distribution (dict): Dictionary of state probabilities.
    
    Returns:
        bool: True if the distribution sums to 1, False otherwise.
    """
    total_probability = sum(distribution.values())
    
    # Check if the total probability is close to 1
    if np.isclose(total_probability, 1.0):
        return True
    else:
        print(f"Warning: Total probability is {total_probability}, not 1.0")
        return False


# visualize output probability distribution given a distribution
def plot_distribution(distribution, title="Distribution Over Many Random Circuits"):
    """
    Plots the probability distribution of basis states without labeling the x-axis.
    
    Args:
        distribution (dict): A dictionary with the basis states as keys and their probabilities as values.
        title (str): The title of the plot (default: "Distribution Over Many Random Circuits").
    """
    # Sort the distribution by basis state (keys)
    states = list(distribution.keys())
    probabilities = list(distribution.values())

    # Create the plot
    plt.figure(figsize=(10, 6))
    plt.bar(range(len(states)), probabilities, color='b', width=0.5)

    # Remove the x-axis label and ticks
    plt.xticks([])  # Remove x-axis ticks (basis states)
    
    # Label the y-axis as Probability
    plt.ylabel('Probability')

    # Set the plot title
    plt.title(title)

    # Display the plot
    plt.show()


def total_variation_distance(distribution1: dict[str, float], distribution2: dict[str, float]):
    """
    Computes the total variation distance (TVD) between two probability distributions.

    Args:
        distribution1 (dict): First probability distribution (must include all basis states).
        distribution2 (dict): Second probability distribution (must include all basis states).

    Returns:
        float: The total variation distance between the two distributions.

    Raises:
        ValueError: If the distributions do not share the same basis states.
    """
    # Ensure the two distributions have the same basis states
    keys1 = set(distribution1.keys())
    keys2 = set(distribution2.keys())
    if keys1 != keys2:
        raise ValueError("Distributions must have the same basis states.")

    # Calculate TVD
    tvd = 0.5 * sum(np.abs(distribution1[key] - distribution2[key]) for key in keys1)
    return tvd


def tvd_truedist_empdist(num_qubits: int, noise_rate: float, shots: int, depth=None):
    """
    Calculates the total variation distance between a circuit's true output distribution
    and its empirical distribution under noise.

    Args:
        num_qubits (int): Number of qubits in the circuit.
        noise_rate (float): Depolarizing noise rate to simulate.
        shots (int): Number of times to sample the circuit.
        depth (int, optional): Depth of the random circuit. Defaults to log2(num_qubits).

    Returns:
        float: The total variation distance between the true and empirical distributions.
    """
    # Generate a random brickwork circuit
    qc = random_circuit(num_qubits, depth)

    # Compute the true noiseless distribution
    true_dist = calculate_true_distribution(qc)

    # Apply measurement to the circuit (must be done after computing true distribution)
    qc.measure_all()

    # Generate empirical distribution using noisy simulation
    noise = create_noise_model(noise_rate)
    noisy_dist = generate_emp_distribution(qc, shots, noise, depth)

    # Compute and return the TVD
    TVD = total_variation_distance(noisy_dist, true_dist)
    return TVD



def compute_xeb(empirical_distribution: dict[str, float], true_distribution: dict[str, float], num_qubits: int):
    """
    Computes the Cross-Entropy Benchmarking (XEB) score.

    The XEB score is given by:
        XEB = 2^n * SUM p(C, x) * q(C, x) - 1
    where:
        - n is the number of qubits
        - p(C, x) is the true ideal distribution (from the statevector)
        - q(C, x) is the noisy empirical distribution (from the simulation)

    Args:
        empirical_distribution (dict): Empirical probabilities from the noisy simulation.
        true_distribution (dict): True probabilities from the ideal simulation.
        num_qubits (int): Number of qubits in the circuit.

    Returns:
        float: The XEB score between the two distributions.
    """

    # Ensure both distributions have the same basis states
    if set(empirical_distribution.keys()) != set(true_distribution.keys()):
        raise ValueError("Distributions must have the same basis states.")

    # Calculate the XEB sum: sum(p(C, x) * q(C, x)) over all basis states
    xeb_sum = sum(true_distribution[state] * empirical_distribution.get(state, 0)
                  for state in true_distribution.keys())

    # Scale by 2^num_qubits and subtract 1 to get the final XEB score
    xeb_score = (2 ** num_qubits) * xeb_sum - 1

    return xeb_score


def xeb_truedist_empdist_noisy(num_qubits: int, noise_rate: float, shots: int, depth: int = None):
    """
    Generates a random quantum circuit, simulates it with noise, and computes the XEB score
    between the true distribution and the empirical noisy distribution.

    Args:
        num_qubits (int): Number of qubits in the circuit.
        noise_rate (float): The depolarizing noise rate for the simulation.
        shots (int): Number of shots for the noisy simulation.
        depth (int, optional): Depth of the circuit. Defaults to log2(num_qubits).

    Returns:
        float: The XEB score between the true and noisy empirical distributions.
    """
    # Generate random circuit with the specified number of qubits and depth
    qc = random_circuit(num_qubits, depth)

    # Calculate the true distribution (ideal statevector-based probabilities)
    true_dist = calculate_true_distribution(qc)
    qc.measure_all()

    # Apply noise and simulate the noisy empirical distribution
    noise = create_noise_model(noise_rate)
    noisy_dist = generate_emp_distribution(qc, shots, noise, depth)

    # Compute the XEB score between the true and noisy distributions
    XEB = compute_xeb(noisy_dist, true_dist, num_qubits)
    return XEB


def xeb_truedist_empdist_ideal(num_qubits: int, noise_rate: float, shots: int, depth: int = None):
    """
    Generates a random quantum circuit, simulates it without noise, and computes the XEB score
    between the true distribution and the empirical distribution under ideal conditions.

    Args:
        num_qubits (int): Number of qubits in the circuit.
        noise_rate (float): The depolarizing noise rate for the simulation (ignored here).
        shots (int): Number of shots for the simulation.
        depth (int, optional): Depth of the circuit. Defaults to log2(num_qubits).

    Returns:
        float: The XEB score between the true and empirical distributions under ideal conditions.
    """
    # Generate random circuit with the specified number of qubits and depth
    qc = random_circuit(num_qubits, depth)

    # Calculate the true distribution (ideal statevector-based probabilities)
    true_dist = calculate_true_distribution(qc)
    qc.measure_all()

    # No noise applied, generate ideal empirical distribution
    noise = create_noise_model(0.0)  # Ideal case (no noise)
    noisy_dist = generate_emp_distribution(qc, shots, noise, depth)

    # Compute the XEB score between the true and empirical distributions
    XEB = compute_xeb(noisy_dist, true_dist, num_qubits)
    return XEB
