import pytest

from ecoanalyst import EcosystemNetwork
from helpers import REPO_ROOT, add, link


@pytest.fixture
def repo_root():
    return REPO_ROOT


@pytest.fixture
def chain():
    """farm -> store -> shop, a direct farm -> shop edge, and a payment edge back."""
    n = EcosystemNetwork(name="chain", network_type="supply_chain")
    add(n, "farm", "producer", rate=0.1, node_class="Farm")
    add(n, "store", "handler", rate=0.02, node_class="ColdStorage")
    add(n, "shop", "consumer", rate=0.2, node_class="Retailer")
    link(n, "farm", "store", 0.05)
    link(n, "store", "shop", 0.01)
    link(n, "farm", "shop", 0.3)
    link(n, "shop", "farm", None, kind="currency")
    return n
