from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "KIM-meso_v1.0" / "Registry" / "Registry.EM_COMMON"
SCALAR_INDICES = ROOT / "KIM-meso_v1.0" / "inc" / "scalar_indices.inc"


def _package_fields(registry: str, package_name: str) -> dict[str, tuple[str, ...]]:
    line = next(line for line in registry.splitlines() if line.startswith(f"package   {package_name}"))
    fields = {}
    for key, value in re.findall(r"(moist|scalar|state):([^;\s]+)", line):
        fields[key] = tuple(value.split(","))
    return fields


def test_kdm6ad_registry_package_matches_kdm6_tracers():
    registry = REGISTRY.read_text()

    assert _package_fields(registry, "kdm6adscheme") == _package_fields(registry, "kdm6scheme")


def test_kdm6ad_registry_package_is_reflected_in_scalar_indices():
    registry = REGISTRY.read_text()
    scalar_indices = SCALAR_INDICES.read_text()

    assert "package   kdm6adscheme    mp_physics==137" in registry
    assert "model_config_rec%mp_physics(idomain)==37 .OR. model_config_rec%mp_physics(idomain)==137" in scalar_indices
