import ast

# Lista de módulos e funções estritamente proibidas para execução remota no BlenderMCP
FORBIDDEN_IMPORTS = {
    'os', 'sys', 'subprocess', 'shutil', 'socket', 
    'urllib', 'requests', 'pathlib', 'pty', 'gc', 'platform'
}

FORBIDDEN_CALLS = {
    'eval', 'exec', 'open', '__import__', 'compile', 
    'globals', 'locals', 'getattr', 'setattr', 'delattr'
}

class SecurityValidator(ast.NodeVisitor):
    """
    Visitor AST que inspeciona o código em busca de padrões maliciosos
    ou importações não autorizadas.
    """
    def __init__(self):
        self.errors = []
        
    def visit_Import(self, node):
        for alias in node.names:
            base_module = alias.name.split('.')[0]
            if base_module in FORBIDDEN_IMPORTS:
                self.errors.append(f"Importação do módulo '{alias.name}' foi bloqueada por política de segurança.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            base_module = node.module.split('.')[0]
            if base_module in FORBIDDEN_IMPORTS:
                self.errors.append(f"Importação do módulo '{node.module}' foi bloqueada por política de segurança.")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.errors.append(f"Uso da função built-in '{node.func.id}()' foi bloqueado por política de segurança.")
        self.generic_visit(node)


def validate_code(code: str) -> list[str]:
    """
    Faz o parse do código e valida contra a política de segurança.
    Retorna uma lista de erros (vazia se seguro).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"Erro de Sintaxe no código recebido: {str(e)}"]
    
    validator = SecurityValidator()
    validator.visit(tree)
    return validator.errors


def execute_safely(code: str, namespace: dict):
    """
    Executa o código de forma segura, garantindo que passou no crivo do Sandbox AST.
    """
    errors = validate_code(code)
    if errors:
        raise PermissionError("Execução bloqueada pelo Sandbox de Segurança:\n" + "\n".join(errors))
    
    # Previne poluição do global built-ins
    if '__builtins__' not in namespace:
        # Permitindo um subset muito restrito de built-ins
        safe_builtins = {
            'print': print,
            'range': range,
            'len': len,
            'enumerate': enumerate,
            'zip': zip,
            'list': list,
            'dict': dict,
            'set': set,
            'tuple': tuple,
            'int': int,
            'float': float,
            'str': str,
            'bool': bool,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'isinstance': isinstance,
            'type': type,
            'Exception': Exception,
            'ValueError': ValueError,
            'TypeError': TypeError,
        }
        namespace['__builtins__'] = safe_builtins

    exec(code, namespace)
