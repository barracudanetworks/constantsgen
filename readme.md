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

Example usage:

    ./generate_constants constants.txt constants.py
    ./generate_constants -l php constants.txt constants.php
