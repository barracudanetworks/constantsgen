import re
from collections import namedtuple
from pathlib import Path

EnumImport = namedtuple("EnumImport",
                        "source_name destination_name name_overrides")


class ParseError(Exception):
    """Raised when the specification or a source file cannot be parsed."""

# #define constants. The separator must not cross a newline, or a #define
# with no value would take the following line as its value.
constants = re.compile(r"#define ([^\s]+)[^\S\n]+([^\s].*)")

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

# A whole line of an enum's contents holding one value, used to check that
# the patterns above can account for every line. They match a value anywhere
# in a line, so without this a line holding anything more -- a second value,
# or a value containing a space -- would be matched in part and the rest
# dropped from the output without an error.
enum_value_line = re.compile(r"[^\s,=]+(?:\s*=\s*[^\s,]+)?,?")

# Comments, removed from an enum's contents before its values are matched.
comments = re.compile(r"/\*.*?\*/|//[^\n]*", flags=re.DOTALL)


def clean_contents(contents):
    """Remove comments and trailing whitespace from an enum's contents.

    Both value patterns are anchored to the ends of lines, so anything left
    after a value -- a comment, or the whitespace where one was removed --
    makes that value match nothing and be dropped without an error.

    Newlines within a comment are kept, so that removing a comment spanning
    several lines cannot join two values onto one line, where neither would
    match.
    """
    def replacement(match):
        return "\n" * match.group().count("\n")

    contents = comments.sub(replacement, contents)

    return "\n".join(line.rstrip() for line in contents.split("\n"))


def override_name(name, enum_definition, overridden):
    """Apply a value name override from the specification, if there is one.

    Names that were overridden are added to overridden so that writers can
    tell them from names read from the source file.
    """
    if name in enum_definition.name_overrides:
        name = enum_definition.name_overrides[name]
        overridden.add(name)

    return name


class ConstantsParser:
    def __init__(self, input_file):
        self.source_files = []
        self.imported_constants = {}
        self.imported_enums = {}
        self.constant_values = {}
        self.enum_values = {}
        self.enum_overridden_names = {}

        manual_suffixes = {}

        section = None
        for line in input_file:
            # Skip blank lines and comments
            if line == "\n" or line.startswith("#"):
                continue

            # Set section based on header
            if line.endswith(":\n"):
                section = line[:-2]
                continue

            if section is None:
                raise ParseError(
                    f"data line before any section header: {line!r}")

            if section == "file":
                self.source_files.append(line[:-1])

            elif section == "constant":
                words = line.split()
                if not words or len(words) > 2:
                    raise ParseError(
                        f"constant line expects 'source_name [destination_name]': {line!r}")
                # Export as the source name if only one is provided; otherwise
                # use the override.
                self.imported_constants[words[0]] = words[-1]

            elif section == "enum":
                words = line.split()
                if len(words) < 2:
                    raise ParseError(
                        "enum line expects 'source_name destination_name "
                        f"[source_value destination_value]...': {line!r}")

                name_overrides = {}
                if len(words) > 2:
                    overrides = words[2:]
                    # Pairs: source_name dest_name
                    if len(overrides) % 2 != 0:
                        raise ParseError(
                            f"enum name overrides must come in pairs: {line!r}")
                    index = 0
                    while index + 1 < len(overrides):
                        name_overrides[overrides[index]] = overrides[index + 1]
                        index += 2

                target = EnumImport(words[0], words[1], name_overrides)

                self.imported_enums[target.source_name] = target

            elif section.startswith("manual"):
                target_container = None
                if section == "manual_prefix":
                    target_container = self.constant_values
                elif section == "manual" or section == "manual_suffix":
                    target_container = manual_suffixes

                if target_container is not None:
                    # Separate the key, and only the key, by whitespace.
                    # The remainder of the line is the value.
                    words = line.split(None, 1)
                    if len(words) < 2:
                        raise ParseError(
                            f"{section} line expects 'name value': {line!r}")
                    key, value = words
                    target_container[key] = value.rstrip()

        # Resolve paths in the input file relative to its location.
        input_dir = Path(input_file.name).parent
        for filename in self.source_files:
            file = (input_dir / filename).read_text(encoding="utf-8")

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

                contents = clean_contents(enum_contents.search(enum).group(1))

                name = enum_definition.destination_name
                self.enum_values[name] = {}
                enum_values = self.enum_values[name]
                self.enum_overridden_names[name] = set()
                overridden = self.enum_overridden_names[name]

                for value_line in contents.split("\n"):
                    value_line = value_line.strip()
                    if value_line and not enum_value_line.fullmatch(value_line):
                        raise ParseError(
                            f"enum {enum_definition.source_name} has a line "
                            "that is not a single value, which would be only "
                            f"partly read: {value_line!r}")

                explicit_values = enum_explicit_value.findall(contents)
                if explicit_values:
                    for name, value in explicit_values:
                        name = override_name(name, enum_definition, overridden)

                        enum_values[name] = value

                implicit_values = enum_implicit_value.findall(contents)
                # If there are any explicit values then either all values must
                # be explicit or only the first is explicit and the rest are
                # implicit; anything else is rejected below.
                # TODO: Use C constants for extracted enums?
                if implicit_values:
                    value = 0
                    if explicit_values:
                        # The continuation below counts up from the explicit
                        # value, so it is only correct if that value really is
                        # the first one declared. Compare where the two kinds
                        # of value first name something, so that comments and
                        # whitespace between values do not matter. The name
                        # group is what is compared because the explicit
                        # pattern's leading \s* reaches back over newlines.
                        first_explicit = enum_explicit_value.search(contents)
                        first_implicit = enum_implicit_value.search(contents)
                        if (len(explicit_values) > 1
                                or first_explicit.start(1)
                                > first_implicit.start(1)):
                            raise ParseError(
                                f"enum {enum_definition.source_name} mixes "
                                "explicit and implicit values in an unsupported "
                                "way; either all values or only the first must "
                                "be explicit")

                        name = override_name(explicit_values[0][0],
                                             enum_definition, overridden)

                        # The values are raw text and are never evaluated, so
                        # the one counted up from has to be a literal.
                        try:
                            value = int(enum_values[name], base=0) + 1
                        except ValueError:
                            raise ParseError(
                                f"enum {enum_definition.source_name} value "
                                f"{name} is {enum_values[name]!r}, which is "
                                "not an integer literal, so the implicit "
                                "values after it cannot be numbered") from None

                    for name in implicit_values:
                        name = override_name(name, enum_definition, overridden)

                        enum_values[name] = value
                        value += 1

                if not enum_values:
                    raise ParseError(
                        f"enum {enum_definition.source_name} has no values")

        if self.imported_constants:
            names = list(self.imported_constants)
            raise ParseError(f"constants {names} not found")

        if self.imported_enums:
            names = list(self.imported_enums)
            raise ParseError(f"enums {names} not found")

        # Add manual suffixes now that all values are loaded.
        for name, value in manual_suffixes.items():
            self.constant_values[name] = value
