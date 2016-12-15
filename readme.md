# constantsgen

Generate code in various languages containing constants defined in the
specified C-like files.

It supports #define constants and named enums. It takes a specification
of which constants to export on standard input and outputs to standard
output.

It uses Python 3.4 enums, so it works with Python 3.4 or higher and
earlier versions with the enum34 package.

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
