# Vendored dependencies

The scripts need a YAML parser. They use the PyYAML installed on the machine when there is one
(with its C loader, faster), and fall back to this copy otherwise, so the plugin runs anywhere
`python3` does — no `pip install`.

| package | version | files | source | sha256 of the sdist |
|---|---|---|---|---|
| PyYAML (pure Python) | 6.0.3 | `yaml/*.py`, `yaml/LICENSE` (MIT) | https://files.pythonhosted.org/packages/05/8e/961c0007c59b8dd7729d542c61a4d537767a59645b82a0b521206e1e25c2/pyyaml-6.0.3.tar.gz | `d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f` |

Copied unmodified from `lib/yaml/` of that sdist; the C extension (`_yaml`) is not included, so
`yaml.CSafeLoader` is absent and the scripts use the pure loader. To update: download the sdist
from PyPI, check its sha256 against PyPI's JSON API, replace `yaml/` and this table.
