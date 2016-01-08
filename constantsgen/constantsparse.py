import re
import os
from collections import namedtuple, OrderedDict

EnumImport = namedtuple("EnumImport",
                        "source_name destination_name name_overrides")

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


class ConstantsParser:
    def __init__(self, input_file):
        self.source_files = []
        self.imported_constants = {}
        self.imported_enums = {}
        self.constant_values = OrderedDict()
        self.enum_values = OrderedDict()

        section = None
        for line in input_file:
            # Skip blank lines and comments
            if line == "\n" or line.startswith("#"):
                continue

            # Set section based on header
            if line.endswith(":\n"):
                section = line[:-2]
                continue

            if section == "file":
                self.source_files.append(line[:-1])

            elif section == "constant":
                words = line.split()
                assert len(words) <= 2
                # Export as the source name if only one is provided; otherwise
                # use the override.
                self.imported_constants[words[0]] = words[-1]

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

                self.imported_enums[target.source_name] = target

            elif section == "manual":
                words = line.split()
                assert len(words) == 2
                self.constant_values[words[0]] = words[1]

        for filename in self.source_files:
            # Resolve paths in input file relative to its location.
            input_dir = os.path.dirname(input_file.name)
            file = open(os.path.join(input_dir, filename)).read()

            for constant in constants.findall(file):
                name, value = constant

                if name not in self.imported_constants:
                    continue

                name = self.imported_constants.pop(name)
                self.constant_values[name] = value

            for enum in enums.findall(file):
                # TODO: Could generate Enum classes only?
                # TODO: Option to consider an enum individual constants?
                name_search = enum_name.search(enum)
                if not name_search:
                    continue

                name = name_search.group(1)
                if not name in self.imported_enums:
                    continue

                enum_definition = self.imported_enums.pop(name)

                contents = enum_contents.search(enum).group(1)

                name = enum_definition.destination_name
                self.enum_values[name] = OrderedDict()
                enum_values = self.enum_values[name]

                explicit_values = enum_explicit_value.findall(contents)
                if explicit_values:
                    for name, value in explicit_values:
                        if name in enum_definition.name_overrides:
                            name = enum_definition.name_overrides[name]

                        enum_values[name] = value

                implicit_values = enum_implicit_value.findall(contents)
                # If there are any explicit values this assumes either all
                # values are explicit or only the first is explicit and the rest
                # are implicit.
                # TODO: Use C constants for extracted enums?
                if implicit_values:
                    assert len(explicit_values) <= 1
                    value = 0
                    if explicit_values:
                        name = explicit_values[0][0]
                        if name in enum_definition.name_overrides:
                            name = enum_definition.name_overrides[name]

                        value = int(enum_values[name], base=0) + 1

                    for name in implicit_values:
                        if name in enum_definition.name_overrides:
                            name = enum_definition.name_overrides[name]

                        enum_values[name] = value
                        value += 1

                assert enum_values

        if self.imported_constants:
            names = list(self.imported_constants)
            raise Exception("constants {} not found".format(names))

        if self.imported_enums:
            names = list(self.imported_enums)
            raise Exception("enums {} not found".format(names))
