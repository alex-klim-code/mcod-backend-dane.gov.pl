"""Export the existing Pipenv lock without changing its versions."""

import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[2]
    packages = json.loads((root / "Pipfile.lock").read_text())["default"]
    for name, package in sorted(packages.items()):
        requirement = package.get("path", name + package.get("version", ""))
        if package.get("extras") and "path" not in package:
            requirement = "{}[{}]{}".format(
                name, ",".join(package["extras"]), package.get("version", "")
            )
        if package.get("markers"):
            requirement += "; " + package["markers"]
        print(requirement)


if __name__ == "__main__":
    main()
