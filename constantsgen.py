import re
import sys
from collections import namedtuple, OrderedDict
import argparse

# #define constants.
constants = re.compile(r"#define ([^\s]+)\s+(.+)")

# Enums.
enums = re.compile(r"enum[^{]+\{[^}]+\};")

# Name of an enum.
enum_name = re.compile(r"enum\s+([^\s{]+)")

# Enum contents between the braces.
enum_contents = re.compile(r"{([^}]+)};")

# Enum value with an explicit value.
enum_explicit_value = re.compile(r"(?:\s*([^\s]+)\s*=\s*([^\s,]+),?)$",
                                 flags=re.MULTILINE)

# Enum value with an implicit value.
enum_implicit_value = re.compile(r"(?:^\s*([^\s,]+),?$)", flags=re.MULTILINE)

EnumImport = namedtuple("EnumImport",
                        "source_name destination_name name_overrides")
imported_constants = {}
imported_enums = {}

parser = argparse.ArgumentParser(description="""Generate Python containing
constants in the specified C-like files.

It supports #define constants and named enums. It takes a specification of which
constants to export on standard input and outputs to standard output.
""")
parser.add_argument("file", nargs='+')
args = parser.parse_args()

print("from enum import Enum, unique\n")

section = None
for line in sys.stdin:
    # Skip blank lines and comments
    if line == "\n" or line.startswith("#"):
        continue

    # Set section based on header
    if line.endswith(":\n"):
        section = line[:-2]
        continue

    if section == "constant":
        words = line.split()
        assert len(words) <= 2
        # Export as the source name if only one is provided; otherwise use the
        # override.
        imported_constants[words[0]] = words[-1]

    elif section == "enum":
        words = line.split()
        assert len(words) >= 2

        name_overrides = {}
        if len(words) > 2:
            overrides = words[2:]
            # Pairs: source_name dest_name
            assert len(overrides) % 2 == 0
            index = 0
            while index + 1 < len(overrides):
                name_overrides[overrides[index]] = overrides[index + 1]
                index += 2

        target = EnumImport(words[0], words[1], name_overrides)

        imported_enums[target.source_name] = target

    elif section == "verbatim":
        print(line)

for filename in args.file:
    file = open(filename).read()

    print()

    for constant in constants.findall(file):
        name, value = constant

        if name not in imported_constants:
            continue

        print("{} = {}".format(imported_constants[name], value))

    for enum in enums.findall(file):
        # TODO: Could generate Enum classes only?
        # TODO: Option to consider an enum individual constants?
        name_search = enum_name.search(enum)
        if not name_search:
            continue

        name = name_search.group(1)
        if not name in imported_enums:
            continue

        enum_definition = imported_enums[name]
        contents = enum_contents.search(enum).group(1)

        enum_defines = OrderedDict()

        explicit_values = enum_explicit_value.findall(contents)
        if explicit_values:
            for name, value in explicit_values:
                enum_defines[name] = value

        implicit_values = enum_implicit_value.findall(contents)
        # If there are any explicit values this assumes either all values are
        # explicit or only the first is explicit and the rest are implicit.
        # TODO: Use C parser for extracted enums?
        if implicit_values:
            assert len(explicit_values) <= 1
            value = 0
            if explicit_values:
                name = explicit_values[0][0]
                value = int(enum_defines[name], base=0) + 1

            for name in implicit_values:
                enum_defines[name] = value
                value += 1

        assert enum_defines

        print("""

@unique
class {}(Enum):""".format(enum_definition.destination_name))
        for base_name, value in enum_defines.items():
            # For the enum value names remove everything up through the first
            # underscore and convert the remainder to lowercase. For example the
            # value NV_BOOL is assigned to bool. If there is no underscore,
            # find() returns -1 and the entire string is used.
            first_underscore = base_name.find("_")
            name = base_name[first_underscore + 1:].lower()

            if base_name in enum_definition.name_overrides:
                name = enum_definition.name_overrides[base_name]

            print("    {} = {}".format(name, value))
