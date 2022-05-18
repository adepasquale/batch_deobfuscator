import argparse
import copy
import os
import re

QUOTED_CHARS = ["|", ">", "<", '"', "^", "&"]


class BatchDeobfuscator:
    def __init__(self):
        self.variables = {}
        self.exec_cmd = []
        if os.name == "nt":
            for env_var, value in os.environ.items():
                self.variables[env_var.lower()] = value
        # fake it till you make it
        else:
            self.variables = {
                "allusersprofile": "C:\\ProgramData",
                "appdata": "C:\\Users\\puncher\\AppData\\Roaming",
                "commonprogramfiles": "C:\\Program Files\\Common Files",
                "commonprogramfiles(x86)": "C:\\Program Files (x86)\\Common Files",
                "commonprogramw6432": "C:\\Program Files\\Common Files",
                "computername": "MISCREANTTEARS",
                "comspec": "C:\\WINDOWS\\system32\\cmd.exe",
                "driverdata": "C:\\Windows\\System32\\Drivers\\DriverData",
                "errorlevel": "0",  # Because nothing fails.
                "fps_browser_app_profile_string": "Internet Explorer",
                "fps_browser_user_profile_string": "Default",
                "homedrive": "C:",
                "homepath": "\\Users\\puncher",
                "java_home": "C:\\Program Files\\Amazon Corretto\\jdk11.0.7_10",
                "localappdata": "C:\\Users\\puncher\\AppData\\Local",
                "logonserver": "\\\\MISCREANTTEARS",
                "number_of_processors": "4",
                "onedrive": "C:\\Users\\puncher\\OneDrive",
                "os": "Windows_NT",
                "path": "C:\\Program Files\\Amazon Corretto\\jdk11.0.7_10\\bin;C:\\WINDOWS\\system32;C:\\WINDOWS;C:\\WINDOWS\\System32\\Wbem;C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\;C:\\Program Files\\dotnet\\;C:\\Program Files\\Microsoft SQL Server\\130\\Tools\\Binn\\;C:\\Users\\puncher\\AppData\\Local\\Microsoft\\WindowsApps;%USERPROFILE%\\AppData\\Local\\Microsoft\\WindowsApps;",
                "pathext": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC",
                "processor_architecture": "AMD64",
                "processor_identifier": "Intel Core Ti-83 Family 6 Model 158 Stepping 10, GenuineIntel",
                "processor_level": "6",
                "processor_revision": "9e0a",
                "programdata": "C:\\ProgramData",
                "programfiles": "C:\\Program Files",
                "programfiles(x86)": "C:\\Program Files (x86)",
                "programw6432": "C:\\Program Files",
                "psmodulepath": "C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\Modules\\",
                "public": "C:\\Users\\Public",
                "sessionname": "Console",
                "systemdrive": "C:",
                "systemroot": "C:\\WINDOWS",
                "temp": "C:\\Users\\puncher\\AppData\\Local\\Temp",
                "tmp": "C:\\Users\\puncher\\AppData\\Local\\Temp",
                "userdomain": "MISCREANTTEARS",
                "userdomain_roamingprofile": "MISCREANTTEARS",
                "username": "puncher",
                "userprofile": "C:\\Users\\puncher",
                "windir": "C:\\WINDOWS",
                "__compat_layer": "DetectorsMessageBoxErrors",
            }

    def read_logical_line(self, path):
        with open(path, "r", encoding="utf-8", errors="ignore") as input_file:
            logical_line = ""
            for line in input_file:
                if not line.endswith("^"):
                    logical_line += line
                    yield logical_line
                    logical_line = ""
                else:
                    logical_line += line + "\n"

    def split_if_statement(self, statement):
        if_statement = r"(?P<conditional>(?P<if_statement>if)\s+(not\s+)?(?P<type>errorlevel\s+\d+\s+|exist\s+(\".*\"|[^\s]+)\s+|.+?==.+?\s+|(\/i\s+)?[^\s]+\s+(equ|neq|lss|leq|gtr|geq)\s+[^\s]+\s+|cmdextversion\s+\d\s+|defined\s+[^\s]+\s+)(?P<open_paren>\()?)(?P<true_statement>[^\)]*)(?P<close_paren>\))?(\s+else\s+(\()?\s*(?P<false_statement>[^\)]*)(\))?)?"
        match = re.search(if_statement, statement, re.IGNORECASE)
        if match is not None:
            conditional = match.group("conditional")
            if match.group("open_paren") is None:
                conditional = f"{conditional}("
            yield conditional
            yield match.group("true_statement")
            if match.group("false_statement") is None:
                if match.group("open_paren") is None or match.group("close_paren") is not None:
                    yield ")"
            else:
                # Got an ELSE statement
                if match.group("if_statement") == "if":
                    yield ") else ("
                else:
                    yield ") ELSE ("
                yield match.group("false_statement")
                yield ")"
        else:
            # Broken if statement, maybe a re-run
            yield statement

    def get_commands_special_statement(self, statement):
        if statement.lower().startswith("if "):
            for part in self.split_if_statement(statement):
                if part.strip() != "":
                    yield part
        # Potential for adding the for statement at some point
        else:
            yield statement

    def get_commands(self, logical_line):
        state = "init"
        counter = 0
        start_command = 0
        for char in logical_line:
            # print(f"C:{char}, S:{state}")
            if state == "init":  # init state
                if char == '"':  # quote is on
                    state = "str_s"
                elif char == "^":
                    state = "escape"
                elif char == "&" and logical_line[counter - 1] == ">":
                    # Usually an output redirection, we want to keep it on the same line
                    pass
                elif char == "&" or char == "|":
                    cmd = logical_line[start_command:counter].strip()
                    if cmd != "":
                        for part in self.get_commands_special_statement(cmd):
                            yield part
                    start_command = counter + 1
            elif state == "str_s":
                if char == '"':
                    state = "init"
            elif state == "escape":
                state = "init"

            counter += 1

        last_com = logical_line[start_command:].strip()
        if last_com != "":
            for part in self.get_commands_special_statement(last_com):
                yield part

    def get_value(self, variable):

        str_substitution = (
            r"([%!])(?P<variable>[\"^|!\w#$'()*+,-.?@\[\]`{}~\s+]+)"
            r"("
            r"(:~\s*(?P<index>[+-]?\d+)\s*(?:,\s*(?P<length>[+-]?\d+))?\s*)|"
            r"(:(?P<s1>[^=]+)=(?P<s2>[^=]*))"
            r")?(\1)"
        )

        matches = re.finditer(str_substitution, variable, re.MULTILINE)

        value = ""

        for matchNum, match in enumerate(matches):
            var_name = match.group("variable").lower()
            if var_name in self.variables:
                value = self.variables[var_name]
                if match.group("index") is not None:
                    index = int(match.group("index"))
                    if index < 0 and -index >= len(value):
                        index = 0
                    elif index < 0:
                        index = len(value) + index
                    if match.group("length") is not None:
                        length = int(match.group("length"))
                    else:
                        length = len(value) - index
                    if length >= 0:
                        value = value[index : index + length]
                    else:
                        value = value[index:length]
                elif match.group("s1") is not None:
                    s1 = match.group("s1")
                    s2 = match.group("s2")
                    if s1.startswith("*") and s1[1:].lower() in value.lower():
                        value = f"{s2}{value[value.lower().index(s1[1:].lower())+len(s1)-1:]}"
                    else:
                        pattern = re.compile(re.escape(s1), re.IGNORECASE)
                        value = pattern.sub(s2, value)
            else:
                # It should be "variable", and interpret the empty echo later, but that would need a better simulator
                return value

        if value == "^":
            return value
        return value.rstrip("^")

    def interpret_set(self, cmd):
        state = "init"
        option = None
        var_name = ""
        var_value = ""
        quote = None
        old_state = None
        stop_parsing = len(cmd)

        for idx, char in enumerate(cmd):
            # print(f"{idx}. C: {char} S: {state}, {var_value}")
            if idx >= stop_parsing:
                break
            if state == "init":
                if char == " ":
                    continue
                elif char == "/":
                    state = "option"
                elif char == '"':
                    quote = '"'
                    stop_parsing = cmd.rfind('"')
                    if idx == stop_parsing:
                        stop_parsing = len(cmd)
                    state = "var"
                elif char == "^":
                    old_state = state
                    state = "escape"
                else:
                    state = "var"
                    var_name += char
            elif state == "option":
                option = char.lower()
                state = "init"
            elif state == "var":
                if char == "=":
                    state = "value"
                elif not quote and char == '"':
                    quote = '"'
                    var_name += char
                elif char == "^":
                    old_state = state
                    state = "escape"
                else:
                    var_name += char
            elif state == "value":
                if char == "^":
                    old_state = state
                    state = "escape"
                else:
                    var_value += char
            elif state == "escape":
                if old_state == "init":
                    if char == '"':
                        quote = '^"'
                        stop_parsing = cmd.rfind('"')
                        if idx == stop_parsing:
                            stop_parsing = len(cmd)
                        state = "init"
                        old_state = None
                    else:
                        state = "var"
                        var_name += char
                        old_state = None
                elif old_state == "var":
                    if quote == '"' and char in QUOTED_CHARS:
                        var_name += "^"
                    if not quote and char == '"':
                        quote = '^"'
                    var_name += char
                    state = old_state
                    old_state = None
                elif old_state == "value":
                    var_value += char
                    state = old_state
                    old_state = None

        if option == "a":
            var_name = var_name.strip(" ")
            for char in QUOTED_CHARS:
                var_name = var_name.replace(char, "")
            var_value = f"({var_value.strip(' ')})"
        elif option == "p":
            var_value = "__input__"

        var_name = var_name.lstrip(" ")
        if not quote:
            var_name = var_name.lstrip('^"').replace('^"', '"')

        return (var_name, var_value)

    def interpret_command(self, normalized_comm):
        # We need to keep the last space in case the command is "set EXP=43 " so that the value will be "43 "
        # normalized_comm = normalized_comm.strip()

        # remove paranthesis
        index = 0
        last = len(normalized_comm) - 1
        while index < last and (normalized_comm[index] == " " or normalized_comm[index] == "("):
            if normalized_comm[index] == "(":
                while last > index and (normalized_comm[last] == " " or normalized_comm[last] == ")"):
                    if normalized_comm[last] == ")":
                        last -= 1
                        break
                    last -= 1
            index += 1
        normalized_comm = normalized_comm[index : last + 1]

        if normalized_comm.lower().startswith("cmd"):
            set_command = (
                r"\s*(call)?cmd(.exe)?\s*((\/A|\/U|\/Q|\/D)\s+|((\/E|\/F|\/V):(ON|OFF))\s*)*(\/c|\/r)\s*(?P<cmd>.*)"
            )
            match = re.search(set_command, normalized_comm, re.IGNORECASE)
            if match is not None and match.group("cmd") is not None:
                cmd = match.group("cmd").strip('"')
                self.exec_cmd.append(cmd)

        else:
            # interpreting set command
            set_command = r"\s*(call)?\s*set(?P<cmd>(\s|\/).*)"
            match = re.search(set_command, normalized_comm, re.IGNORECASE)
            if match is not None:
                var_name, var_value = self.interpret_set(match.group("cmd"))
                if var_value == "":
                    if var_name.lower() in self.variables:
                        del self.variables[var_name.lower()]
                else:
                    self.variables[var_name.lower()] = var_value

    # pushdown automata
    def normalize_command(self, command):
        state = "init"
        normalized_com = ""
        stack = []
        for char in command:
            # print(f"C:{char} S:{state} N:{normalized_com}")
            if state == "init":  # init state
                if char == '"':  # quote is on
                    state = "str_s"
                    normalized_com += char
                elif char == "," or char == ";":  # or char == "\t": EDIT: How about we keep those tabs?
                    # commas (",") are replaced by spaces, unless they are part of a string in doublequotes
                    # semicolons (";") are replaced by spaces, unless they are part of a string in doublequotes
                    # tabs are replaced by a single space
                    # http://www.robvanderwoude.com/parameters.php
                    normalized_com += " "
                elif char == "^":  # next character must be escaped
                    stack.append(state)
                    state = "escape"
                elif char == "%":  # variable start
                    variable_start = len(normalized_com)
                    normalized_com += char
                    stack.append(state)
                    state = "var_s"
                elif char == "!":
                    variable_start = len(normalized_com)
                    normalized_com += char
                    stack.append(state)
                    state = "var_s_2"
                else:
                    normalized_com += char
            elif state == "str_s":
                if char == '"':
                    state = "init"
                    normalized_com += char
                elif char == "%":
                    variable_start = len(normalized_com)
                    normalized_com += char
                    stack.append("str_s")
                    state = "var_s"  # seen %
                elif char == "!":
                    variable_start = len(normalized_com)
                    normalized_com += char
                    stack.append("str_s")
                    state = "var_s_2"  # seen !
                elif char == "^":
                    state = "escape"
                    stack.append("str_s")
                else:
                    normalized_com += char
            elif state == "var_s":
                if char == "%" and normalized_com[-1] != char:
                    normalized_com += char
                    value = self.get_value(normalized_com[variable_start:])
                    normalized_com = normalized_com[:variable_start]
                    normalized_com += self.normalize_command(value)
                    state = stack.pop()
                elif char == "%":  # Two % in a row
                    normalized_com += char
                    state = stack.pop()
                elif char == '"':
                    if stack[-1] == "str_s":
                        normalized_com += char
                        stack.pop()
                        state = "init"
                    else:
                        normalized_com += char
                elif char == "^":
                    # Do not escape in vars?
                    # state = "escape"
                    # stack.append("var_s")
                    normalized_com += char
                elif char.isdigit() and len(normalized_com) == variable_start + 1:
                    normalized_com += char
                    if char == "0":
                        value = "script.bat"
                    else:
                        value = ""  # Assume no parameter were passed
                    normalized_com = normalized_com[:variable_start]
                    normalized_com += value
                    state = stack.pop()
                else:
                    normalized_com += char
            elif state == "var_s_2":
                if char == "!" and normalized_com[-1] != char:
                    normalized_com += char
                    value = self.get_value(normalized_com[variable_start:])
                    normalized_com = normalized_com[:variable_start]
                    normalized_com += self.normalize_command(value)
                    state = stack.pop()
                elif char == "!":
                    normalized_com += char
                elif char == '"':
                    if stack[-1] == "str_s":
                        normalized_com += char
                        stack.pop()
                        state = "init"
                    else:
                        normalized_com += char
                elif char == "^":
                    state = "escape"
                    stack.append("var_s_2")
                else:
                    normalized_com += char
            elif state == "escape":
                if char in QUOTED_CHARS:
                    normalized_com += "^"
                normalized_com += char
                state = stack.pop()
                if char == "%":
                    if state == "var_s":
                        value = self.get_value(normalized_com[variable_start:])
                        normalized_com = normalized_com[:variable_start]
                        normalized_com += self.normalize_command(value)
                        state = stack.pop()
                    else:
                        variable_start = len(normalized_com) - 1
                        stack.append(state)
                        state = "var_s"
                elif char == "!":
                    if state == "var_s_2":
                        value = self.get_value(normalized_com[variable_start:])
                        normalized_com = normalized_com[:variable_start]
                        normalized_com += self.normalize_command(value)
                        state = stack.pop()
                    else:
                        variable_start = len(normalized_com) - 1
                        stack.append(state)
                        state = "var_s_2"

        if state in ["var_s", "var_s_2"]:
            normalized_com = normalized_com[:variable_start] + normalized_com[variable_start + 1 :]
        if state == "escape":
            normalized_com += "^"

        return normalized_com


def interpret_logical_line(deobfuscator, logical_line, tab=""):
    commands = deobfuscator.get_commands(logical_line)
    for command in commands:
        normalized_comm = deobfuscator.normalize_command(command)
        deobfuscator.interpret_command(normalized_comm)
        print(tab + normalized_comm)
        if len(deobfuscator.exec_cmd) > 0:
            print(tab + "[CHILD CMD]")
            for child_cmd in deobfuscator.exec_cmd:
                child_deobfuscator = copy.deepcopy(deobfuscator)
                child_deobfuscator.exec_cmd.clear()
                interpret_logical_line(child_deobfuscator, child_cmd, tab=tab + "\t")
            deobfuscator.exec_cmd.clear()
            print(tab + "[END OF CHILD CMD]")


def interpret_logical_line_str(deobfuscator, logical_line, tab=""):
    str = ""
    commands = deobfuscator.get_commands(logical_line)
    for command in commands:
        normalized_comm = deobfuscator.normalize_command(command)
        deobfuscator.interpret_command(normalized_comm)
        str = str + tab + normalized_comm
        if len(deobfuscator.exec_cmd) > 0:
            str = str + tab + "[CHILD CMD]"
            for child_cmd in deobfuscator.exec_cmd:
                child_deobfuscator = copy.deepcopy(deobfuscator)
                child_deobfuscator.exec_cmd.clear()
                interpret_logical_line(child_deobfuscator, child_cmd, tab=tab + "\t")
            deobfuscator.exec_cmd.clear()
            str = str + tab + "[END OF CHILD CMD]"
    return str


def handle_bat_file(deobfuscator, fpath):
    strs = []
    if os.path.isfile(fpath):
        try:
            for logical_line in deobfuscator.read_logical_line(fpath):
                try:
                    strs.append(interpret_logical_line_str(deobfuscator, logical_line))
                except Exception as e:
                    print(e)
                    pass
        except Exception as e:
            print(e)
            pass
    if strs:
        return "\r\n".join(strs)
    else:
        return ""


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--file", type=str, help="The path of obfuscated batch file")
    args = parser.parse_known_args()

    deobfuscator = BatchDeobfuscator()

    if args[0].file is not None:

        file_path = args[0].file

        for logical_line in deobfuscator.read_logical_line(args[0].file):
            interpret_logical_line(deobfuscator, logical_line)
    else:
        print("Please enter an obfuscated batch command:")
        interpret_logical_line(deobfuscator, input())
