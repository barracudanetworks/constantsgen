"""Tests for the parser and the writers.

Each test writes a specification, and the sources it names, to a temporary
directory, because ConstantsParser resolves source paths relative to the
specification and so needs a real file rather than a string.
"""

import io
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from constantsgen.constantsparse import ConstantsParser, ParseError
from constantsgen.latexwriter import LatexWriter
from constantsgen.phpwriter import PHPWriter
from constantsgen.pythonwriter import PythonWriter


class GeneratorTestCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def parse(self, specification, sources=None):
        """Parse a specification, having written out the sources it names."""
        for name, contents in (sources or {}).items():
            path = self.directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(contents))

        specification_path = self.directory / "specification.txt"
        specification_path.write_text(textwrap.dedent(specification))

        with specification_path.open() as specification_file:
            return ConstantsParser(specification_file)

    def generate(self, writer, specification, sources=None):
        """Return what a writer generates for a specification."""
        out = io.StringIO()
        writer(self.parse(specification, sources)).write(out)

        return out.getvalue()


class ConstantTest(GeneratorTestCase):
    def test_exported_under_its_own_name(self):
        constants = self.parse("""\
            file:
            file.h
            constant:
            A_CONSTANT
            """, {"file.h": "#define A_CONSTANT 1\n"})

        self.assertEqual(constants.constant_values, {"A_CONSTANT": "1"})

    def test_exported_under_a_destination_name(self):
        constants = self.parse("""\
            file:
            file.h
            constant:
            A_CONSTANT RENAMED
            """, {"file.h": "#define A_CONSTANT 1\n"})

        self.assertEqual(constants.constant_values, {"RENAMED": "1"})

    def test_separated_by_a_tab(self):
        constants = self.parse("""\
            file:
            file.h
            constant:
            A_CONSTANT
            """, {"file.h": "#define A_CONSTANT\t1\n"})

        self.assertEqual(constants.constant_values, {"A_CONSTANT": "1"})

    def test_without_a_value_is_not_found(self):
        with self.assertRaises(ParseError):
            self.parse("""\
                file:
                file.h
                constant:
                NO_VALUE
                """, {"file.h": "#define NO_VALUE\n#define AFTER 2\n"})

    def test_without_a_value_does_not_consume_the_next_line(self):
        constants = self.parse("""\
            file:
            file.h
            constant:
            AFTER
            """, {"file.h": "#define NO_VALUE\n#define AFTER 2\n"})

        self.assertEqual(constants.constant_values, {"AFTER": "2"})

    def test_not_found_raises(self):
        with self.assertRaises(ParseError):
            self.parse("""\
                file:
                file.h
                constant:
                MISSING
                """, {"file.h": "#define SOMETHING_ELSE 1\n"})

    def test_source_paths_are_relative_to_the_specification(self):
        constants = self.parse("""\
            file:
            headers/file.h
            constant:
            A_CONSTANT
            """, {"headers/file.h": "#define A_CONSTANT 1\n"})

        self.assertEqual(constants.constant_values, {"A_CONSTANT": "1"})


class EnumTest(GeneratorTestCase):
    def enum(self, body, specification_line="an_enum_e AnEnum"):
        constants = self.parse(f"""\
            file:
            file.h
            enum:
            {specification_line}
            """, {"file.h": f"enum an_enum_e {{\n{body}}};\n"})

        return constants.enum_values["AnEnum"]

    def test_all_values_explicit(self):
        self.assertEqual(self.enum("    E_X = 1,\n    E_Y = 2,\n"),
                         {"E_X": "1", "E_Y": "2"})

    def test_all_values_implicit(self):
        self.assertEqual(self.enum("    E_X,\n    E_Y,\n"),
                         {"E_X": 0, "E_Y": 1})

    def test_first_value_explicit_and_the_rest_implicit(self):
        self.assertEqual(self.enum("    E_X = 5,\n    E_Y,\n    E_Z,\n"),
                         {"E_X": "5", "E_Y": 6, "E_Z": 7})

    def test_a_lone_explicit_value_must_come_first(self):
        with self.assertRaises(ParseError):
            self.enum("    E_X,\n    E_Y = 9,\n")

    def test_several_explicit_values_among_implicit_ones(self):
        with self.assertRaises(ParseError):
            self.enum("    E_X = 1,\n    E_Y = 2,\n    E_Z,\n")

    def test_an_implicit_run_must_follow_an_integer_literal(self):
        with self.assertRaises(ParseError):
            self.enum("    E_X = SOME_MACRO,\n    E_Y,\n")

    def test_a_value_may_be_written_in_hexadecimal(self):
        self.assertEqual(self.enum("    E_X = 0x10,\n    E_Y,\n"),
                         {"E_X": "0x10", "E_Y": 17})

    def test_comment_before_the_first_value(self):
        self.assertEqual(self.enum("    /* leading */\n    E_X = 5,\n"
                                   "    E_Y,\n"),
                         {"E_X": "5", "E_Y": 6})

    def test_comment_after_a_value(self):
        self.assertEqual(self.enum("    E_X = 5, // trailing\n"
                                   "    E_Y, /* also trailing */\n"),
                         {"E_X": "5", "E_Y": 6})

    def test_comment_spanning_several_lines(self):
        self.assertEqual(self.enum("    /* one\n       two */\n"
                                   "    E_X = 5,\n    E_Y,\n"),
                         {"E_X": "5", "E_Y": 6})

    def test_whitespace_after_a_value(self):
        self.assertEqual(self.enum("    E_X = 1,   \n    E_Y = 2,\t\n"),
                         {"E_X": "1", "E_Y": "2"})

    def test_name_override(self):
        self.assertEqual(self.enum("    E_X,\n    E_Y,\n",
                                   "an_enum_e AnEnum E_X clearer_name"),
                         {"clearer_name": 0, "E_Y": 1})

    def test_overridden_names_are_recorded(self):
        constants = self.parse("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum E_X clearer_name
            """, {"file.h": "enum an_enum_e {\n    E_X,\n    E_Y,\n};\n"})

        self.assertEqual(constants.enum_overridden_names["AnEnum"],
                         {"clearer_name"})

    def test_several_values_on_one_line_raises(self):
        # Rather than reading the last one and dropping the rest.
        with self.assertRaises(ParseError):
            self.parse("""\
                file:
                file.h
                enum:
                an_enum_e AnEnum
                """, {"file.h": "enum an_enum_e { E_X = 1, E_Y = 2 };\n"})

    def test_a_value_containing_a_space_raises(self):
        with self.assertRaises(ParseError):
            self.enum("    E_X = 1 << 2,\n    E_Y,\n")

    def test_not_found_raises(self):
        with self.assertRaises(ParseError):
            self.parse("""\
                file:
                file.h
                enum:
                missing_e Missing
                """, {"file.h": "enum other_e {\n    O_X,\n};\n"})


class SpecificationTest(GeneratorTestCase):
    def test_data_line_before_any_section_raises(self):
        with self.assertRaises(ParseError):
            self.parse("stray line\n")

    def test_comments_and_blank_lines_are_ignored(self):
        constants = self.parse("""\
            # a comment

            manual:
            NAME value
            """)

        self.assertEqual(constants.constant_values, {"NAME": "value"})

    def test_manual_line_without_a_value_raises(self):
        with self.assertRaises(ParseError):
            self.parse("manual:\nLONELY\n")

    def test_manual_value_keeps_its_spaces(self):
        constants = self.parse("manual:\nNAME  1 + 2\n")

        self.assertEqual(constants.constant_values, {"NAME": "1 + 2"})

    def test_manual_is_an_alias_for_manual_suffix(self):
        constants = self.parse("""\
            manual:
            FIRST 1
            manual_suffix:
            SECOND 2
            """)

        self.assertEqual(list(constants.constant_values), ["FIRST", "SECOND"])

    def test_prefixes_come_before_and_suffixes_after_file_values(self):
        constants = self.parse("""\
            file:
            file.h
            constant:
            FROM_FILE
            manual_prefix:
            BEFORE 1
            manual_suffix:
            AFTER 3
            """, {"file.h": "#define FROM_FILE 2\n"})

        self.assertEqual(list(constants.constant_values),
                         ["BEFORE", "FROM_FILE", "AFTER"])

    def test_unknown_sections_are_ignored(self):
        # Not by design, but a change here should be a deliberate one.
        constants = self.parse("""\
            unknown:
            ignored data
            manual:
            NAME value
            """)

        self.assertEqual(constants.constant_values, {"NAME": "value"})

    def test_constant_line_with_too_many_names_raises(self):
        with self.assertRaises(ParseError):
            self.parse("constant:\nONE TWO THREE\n")

    def test_enum_line_without_a_destination_name_raises(self):
        with self.assertRaises(ParseError):
            self.parse("enum:\nan_enum_e\n")

    def test_unpaired_name_override_raises(self):
        with self.assertRaises(ParseError):
            self.parse("enum:\nan_enum_e AnEnum E_X clearer_name E_Y\n")


class PythonWriterTest(GeneratorTestCase):
    def generate_python(self, specification, sources=None):
        return self.generate(PythonWriter, specification, sources)

    def test_value_names_are_mangled(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            """, {"file.h": "enum an_enum_e {\n    E_BOOL,\n};\n"})

        self.assertIn("    bool = 0\n", generated)

    def test_a_name_without_an_underscore_is_kept_whole(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            """, {"file.h": "enum an_enum_e {\n    SOLO,\n};\n"})

        self.assertIn("    solo = 0\n", generated)

    def test_an_overridden_name_is_used_as_written(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum E_X clearer_name
            """, {"file.h": "enum an_enum_e {\n    E_X,\n    E_Y,\n};\n"})

        self.assertIn("    clearer_name = 0\n", generated)
        self.assertIn("    y = 1\n", generated)

    def test_unique_is_emitted_for_distinct_values(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            """, {"file.h": "enum an_enum_e {\n    E_X = 1,\n    E_Y = 2,\n};\n"})

        self.assertIn("@unique\nclass AnEnum(Enum):\n", generated)

    def test_unique_is_omitted_for_aliased_values(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            """, {"file.h": "enum an_enum_e {\n    E_X = 1,\n"
                            "    E_ALIAS = 0x1,\n};\n"})

        self.assertNotIn("@unique", generated)

    def test_generated_aliases_import(self):
        generated = self.generate_python("""\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            """, {"file.h": "enum an_enum_e {\n    E_X = 1,\n"
                            "    E_ALIAS = 1,\n};\n"})

        namespace = {}
        exec(compile(generated, "constants.py", "exec"), namespace)

        self.assertIs(namespace["AnEnum"].alias, namespace["AnEnum"].x)

    def test_constants_follow_the_enums(self):
        generated = self.generate_python("""\
            file:
            file.h
            constant:
            A_CONSTANT
            enum:
            an_enum_e AnEnum
            """, {"file.h": "#define A_CONSTANT 1\n"
                            "enum an_enum_e {\n    E_X,\n};\n"})

        self.assertLess(generated.index("class AnEnum"),
                        generated.index("A_CONSTANT = 1"))


class PHPWriterTest(GeneratorTestCase):
    def test_enum_values_become_defines_under_their_own_names(self):
        generated = self.generate(PHPWriter, """\
            file:
            file.h
            constant:
            A_CONSTANT
            enum:
            an_enum_e AnEnum
            """, {"file.h": "#define A_CONSTANT 1\n"
                            "enum an_enum_e {\n    E_X,\n};\n"})

        self.assertIn("define('E_X',", generated)
        self.assertIn("define('A_CONSTANT',", generated)
        self.assertNotIn("AnEnum", generated)


class LatexWriterTest(GeneratorTestCase):
    def test_underscores_are_removed_from_command_names(self):
        generated = self.generate(LatexWriter,
                                  "manual:\nA_CONSTANT 1\n")

        self.assertIn("\\newcommand{\\ACONSTANT}{1}\n", generated)

    def test_a_value_naming_a_constant_refers_to_its_command(self):
        generated = self.generate(LatexWriter, """\
            file:
            file.h
            constant:
            A_CONSTANT
            manual_suffix:
            DERIVED A_CONSTANT + 2
            """, {"file.h": "#define A_CONSTANT 1337\n"})

        self.assertIn("\\newcommand{\\DERIVED}{\\ACONSTANT + 2}\n", generated)

    def test_a_value_naming_an_enum_value_refers_to_its_command(self):
        generated = self.generate(LatexWriter, """\
            file:
            file.h
            enum:
            an_enum_e AnEnum
            manual_suffix:
            DERIVED E_X
            """, {"file.h": "enum an_enum_e {\n    E_X,\n};\n"})

        self.assertIn("\\newcommand{\\DERIVED}{\\EX}\n", generated)

    def test_other_underscores_are_escaped(self):
        generated = self.generate(LatexWriter,
                                  "manual:\nNAME SOME_MACRO\n")

        self.assertIn("\\newcommand{\\NAME}{SOME\\_MACRO}\n", generated)

    def test_a_hexadecimal_value_is_left_alone(self):
        generated = self.generate(LatexWriter,
                                  "manual:\nNAME 0xdeadbeef\n")

        self.assertIn("\\newcommand{\\NAME}{0xdeadbeef}\n", generated)


if __name__ == "__main__":
    unittest.main()
