class PythonWriter:
    def __init__(self, constants):
        self.constants = constants

    def write(self, out):
        out.write("# This file was generated by generate_constants.\n\n")
        out.write("from enum import Enum, unique\n\n")

        for name, enum in self.constants.enum_values.items():
            out.write("""
@unique
class {}(Enum):\n""".format(name))
            for base_name, value in enum.items():
                # For the enum value names remove everything up through the
                # first underscore and convert the remainder to lowercase. For
                # example the value NV_BOOL is assigned to bool. If there is no
                # underscore, find() returns -1 and the entire string is used.
                first_underscore = base_name.find("_")
                name = base_name[first_underscore + 1:].lower()

                out.write("    {} = {}\n".format(name, value))

            out.write("\n\n")

        for name, value in self.constants.constant_values.items():
            out.write("{} = {}\n".format(name, value))
