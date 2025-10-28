


def walk(node, source_code:str, symbol_table: dict, declared_table: dict, used_table: dict, is_global_var, ignored_lines, ignored_blocks) -> list[dict]:

    violations = []

    ignored_line_nums  = {il["line"] - 1 for il in ignored_lines}
    ignored_block_nums = {ib["line"] - 1 for ib in ignored_blocks}

    if node.start_point[0] in ignored_block_nums:
        
        return violations  

    if node.start_point[0] not in ignored_line_nums:
        # Check for banned functions including new and delete
        if node.type == "call_expression":
            violations += check_banned_funcs(node, source_code)


        # Ban delete and new
        elif node.type == "new_expression":
            violations.append({
                "line": node.start_point[0] + 1,
                "function": "new",
                "message": "Usage of 'new' is banned. Use static or stack allocation instead."
            })


        elif node.type == "delete_expression":
            violations.append({
                "line": node.start_point[0] + 1,
                "function": "delete",
                "message": "Usage of 'delete' is banned. Use RAII or static allocation instead."
            })

        #Check for misuse of switch statements
        elif node.type == "switch_statement":
            violations += check_switch_statement(node, source_code)

        #Ban goto
        elif node.type == "goto":
            violations.append({
                "line": node.start_point[0] + 1,
                "message": "Usage of 'goto' and any uncontrolled jumps are banned."
            })
        
        #Ban function-like macros
        elif node.type == "preproc_function_def":
            violations.append({
                "line": node.start_point[0] + 1,
                "message": "Definition of function-like macros are banned. Consider using 'inline'."
            })
    

        for child in node.children:
            violations += walk(child, source_code, symbol_table, declared_table, used_table, is_global_var,
                               ignored_lines, ignored_blocks)
            

    return violations


# CHECKS


def check_banned_funcs(node, source_code: str) -> list[dict]:
    """
    Ensures function call is not banned. Unsafe functions are defined as those who either dynamically allocate memory or
    have the potential to cause overflow. 
    """

    banned_functions = {
        "malloc", "calloc", "realloc", "free",
        "printf", "sprintf", "scanf", "gets", "fgets",
        "rand", "srand", "time", "clock", "gettimeofday",
        "system", "fork", "exec", "exit",
        "va_start", "va_arg", "va_end",
        "cin", "cout", "cerr"
    }

    violations = []

    function_node = node.child_by_field_name('function')
    if function_node is not None:
        name = source_code[function_node.start_byte:function_node.end_byte].decode("utf-8")

        if '::' in name:
            name = name.split('::')[-1]
        
        
        if name in banned_functions:
            violations.append({
                "line": node.start_point[0] + 1,
                "function": name,
                "message": f"Usage of function '{name}' is banned. Please use safer alternative."
            })
    return violations

#Ban unsafe switch statement practices
def check_switch_statement(node, source_code: str) -> list[dict]:
    violations = []

    def is_default_case(n) -> bool:
        # Covers both grammars:
        # - 'default_statement'
        # - 'case_statement' without a 'value' field → default
        if n.type == "default_statement":
            return True
        if n.type == "case_statement" and n.child_by_field_name("value") is None:
            return True
        return False

    def contains_terminator(n) -> bool:
        # Accept only break/return as a proper terminator for a case.
        # 'continue' is *not* a terminator in a switch.
        if n.type in {"break_statement", "return_statement"}:
            return True
        # Some grammars expose raw tokens:
        if n.type in {"break", "return"}:
            return True
        for ch in getattr(n, "named_children", []):
            if contains_terminator(ch):
                return True
        # Fallback to raw children in case statements are non-named
        for ch in getattr(n, "children", []):
            if contains_terminator(ch):
                return True
        return False

    body = node.child_by_field_name("body")
    if not body:
        return violations

    has_default = False

    # Iterate the switch body and evaluate only case/default nodes
    for item in getattr(body, "named_children", body.children):
        if item.type in {"case_statement", "default_statement"}:
            if is_default_case(item):
                has_default = True
            if not contains_terminator(item):
                violations.append({
                    "line": item.start_point[0] + 1,
                    "message": "Case falls through implicitly. Add 'break;' or 'return;'."
                })

    if not has_default:
        violations.append({
            "line": node.start_point[0] + 1,
            "message": "Switch statement missing 'default' case."
        })

    return violations




