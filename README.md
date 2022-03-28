# InkML for Python

## About

**pinkml** is a Python library for working with files in InkML format.
Ink Markup Language (InkML) is a W3C standard for complete and accurate representation of *digital ink*
(http://www.w3.org/tr/inkml).

## Installation

To install the latest stable version from the PyPI:

```shell script
$ pip install pinkml
```

## Reading InkML

```python
from inkml.reading import Reader

reader = Reader()

with open(input_path, 'r') as f:
    ink = reader.read(f.read())

for index, trace in enumerate(ink.traces):
    print(f'trace #{index}')
    for x, y, t in zip(trace.channels['X'], trace.channels['Y'], trace.channels['T']):
        print(f'{x:.3f}, {y:.3f}, {t:.3f}')
```

## TODO

* **Writing of InkML files** - currently only reading is implemented.

