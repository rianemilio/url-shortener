from prometheus_client import REGISTRY


def sample(name: str, **labels: str) -> float:
    """Valor atual de uma métrica no registry global (0 se a série ainda não existe).

    Os testes comparam antes/depois: o registry é do processo e acumula entre testes.
    """
    return REGISTRY.get_sample_value(name, labels) or 0.0
