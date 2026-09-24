"""규칙 파일의 조건식을 안전하게 평가합니다.

eval()을 쓰지 않고, 비교·and/or/not·사칙연산·이름·숫자/문자열만 허용합니다.
이름이 context에 없으면 Missing 예외를 던져 '데이터 없음'으로 처리됩니다.
"""
import ast
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.Eq: operator.eq, ast.NotEq: operator.ne}
_CONST = {'True': True, 'False': False, 'true': True, 'false': False}


class Missing(Exception):
    """조건식에 필요한 값이 없음."""


class RuleError(ValueError):
    """허용되지 않는 문법."""


def compile_rule(text):
    try:
        tree = ast.parse(str(text), mode='eval')
    except SyntaxError as e:
        raise RuleError(f'조건식 문법 오류: {text!r}') from e
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub,
                                 ast.Compare, ast.Name, ast.Constant, ast.BinOp, ast.Load, *_BIN, *_CMP)):
            raise RuleError(f'허용되지 않는 표현: {type(node).__name__} in {text!r}')
    return tree


def evaluate(text, context):
    return _eval(compile_rule(text).body, context)


def _eval(node, ctx):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONST:
            return _CONST[node.id]
        if node.id not in ctx or ctx[node.id] is None:
            raise Missing(node.id)
        return ctx[node.id]
    if isinstance(node, ast.BoolOp):
        values = (_eval(v, ctx) for v in node.values)
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, ctx)
        return (not v) if isinstance(node.op, ast.Not) else -v
    if isinstance(node, ast.BinOp):
        return _BIN[type(node.op)](_eval(node.left, ctx), _eval(node.right, ctx))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, ctx)
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise RuleError(type(node).__name__)
