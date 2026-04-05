import dataclasses as dtc


@dtc.dataclass
class Air:
    """Standard air properties at 25 degrees Celsius and 1 atm."""
    RHO: float = 1.1839  # density of air at 25 degrees Celsius
    P0: int = 101325  # atmospheric pressure
    GAMMA: float = 1.401  # adiabatic index of air
    Kair: float = P0 * GAMMA
    c_air: float = (Kair / RHO)**0.5
