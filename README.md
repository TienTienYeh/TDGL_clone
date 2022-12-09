# pyTDGL

![pyTDGL Logo](docs/images/logo-transparent-small.png)

Time-dependent Ginzburg-Landau in Python

![GitHub Workflow Status (branch)](https://img.shields.io/github/workflow/status/loganbvh/py-tdgl/lint-and-test/main)
[![Documentation Status](https://readthedocs.org/projects/py-tdgl/badge/?version=latest)](https://py-tdgl.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/loganbvh/py-tdgl/branch/main/graph/badge.svg?token=VXdxJKP6Ag)](https://codecov.io/gh/loganbvh/py-tdgl)
![GitHub](https://img.shields.io/github/license/loganbvh/py-tdgl)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## Motivation
`pyTDGL` solves a 2D generalized time-dependent Ginzburg-Landau (TDGL) equation, enabling simulations of vortex and phase dynamics in thin film superconducting devices.

## Installation

`pyTDGL` requires `python` `3.8`, `3.9`, or `3.10`. We recommend installing `pyTDGL` in a [`conda` environment](https://conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html), e.g.

```bash
conda create --name tdgl python=3.9
conda activate tdgl
```

### Install via `pip`

- From this [GitHub repository](https://github.com/loganbvh/py-tdgl/):

    ```bash
    pip install git+https://github.com/loganbvh/py-tdgl.git
    ```

- From  PyPI, the Python Package index:
    
    Coming soon...

### Editable installation

```bash
git clone https://github.com/loganbvh/py-tdgl.git
cd py-tdgl
pip install -e .[dev,docs]
```

## Acknowledgments

Parts of this package have been adapted from [`SuperDetectorPy`](https://github.com/afsa/super-detector-py), a GitHub repo authored by [Mattias Jönsson](https://github.com/afsa). Both `SuperDetectorPy` and `py-tdgl` are released under the open-source MIT License. If you use either package in an academic publication or similar, please consider citing the following:

- Mattias Jönsson, Theory for superconducting few-photon detectors (Doctoral dissertation), KTH Royal Institute of Technology (2022) ([Link](http://urn.kb.se/resolve?urn=urn:nbn:se:kth:diva-312132))
- Mattias Jönsson, Robert Vedin, Samuel Gyger, James A. Sutton, Stephan Steinhauer, Val Zwiller, Mats Wallin, Jack Lidmar, Current crowding in nanoscale superconductors within the Ginzburg-Landau model, Phys. Rev. Applied 17, 064046 (2022) ([Link](https://journals.aps.org/prapplied/abstract/10.1103/PhysRevApplied.17.064046))

The user interface is adaptive from [`SuperScreen`](https://github.com/loganbvh/superscreen).

