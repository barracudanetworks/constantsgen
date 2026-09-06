# constantsgen

Generate code in various languages containing constants defined in the
specified C-like files. It supports #define constants and named enums.

Requires Python 3.9 or later.

constants.txt contains a description and example of the input format.
It does not parse the files, so things that would contain syntax errors
in C, like XDR files, do not cause problems.

Supported output languages:

* Python
* PHP
* LaTeX

Installation:

    pip install .

This provides a `generate_constants` command. To run without installing,
use `python -m constantsgen` from this source tree.

Example usage:

    python -m constantsgen constants.txt constants.py
    python -m constantsgen -l php constants.txt constants.php
