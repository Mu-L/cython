"""
Serializes a Cython code tree to Cython code. This is primarily useful for
debugging and testing purposes.
The output is in a strict format, no whitespace or comments from the input
is preserved (and it could not be as it is not present in the code tree).
"""


from .Compiler.Visitor import TreeVisitor
from .Compiler.ExprNodes import *
from .Compiler.Nodes import CSimpleBaseTypeNode


class LinesResult:
    def __init__(self):
        self.lines = []
        self.s = ""

    def put(self, s):
        self.s += s

    def newline(self):
        self.lines.append(self.s)
        self.s = ""

    def putline(self, s):
        self.put(s)
        self.newline()


class DeclarationWriter(TreeVisitor):
    """
    A Cython code writer that is limited to declarations nodes.
    """

    indent_string = "    "

    def __init__(self, result=None):
        super().__init__()
        if result is None:
            result = LinesResult()
        self.result = result
        self.numindents = 0
        self.tempnames = {}
        self.tempblockindex = 0

    def write(self, tree):
        self.visit(tree)
        return self.result

    def indent(self):
        self.numindents += 1

    def dedent(self):
        self.numindents -= 1

    def startline(self, s=""):
        self.result.put(self.indent_string * self.numindents + s)

    def put(self, s):
        self.result.put(s)

    def putline(self, s):
        self.result.putline(self.indent_string * self.numindents + s)

    def endline(self, s=""):
        self.result.putline(s)

    def line(self, s):
        self.startline(s)
        self.endline()

    def comma_separated_list(self, items, output_rhs=False):
        if len(items) > 0:
            for item in items[:-1]:
                self.visit(item)
                if output_rhs and item.default is not None:
                    self.put(" = ")
                    self.visit(item.default)
                self.put(", ")
            self.visit(items[-1])
            if output_rhs and items[-1].default is not None:
                self.put(" = ")
                self.visit(items[-1].default)

    def _visit_indented(self, node):
        self.indent()
        self.visit(node)
        self.dedent()

    def visit_Node(self, node):
        raise AssertionError("Node not handled by serializer: %r" % node)

    def visit_ModuleNode(self, node):
        self.visitchildren(node)

    def visit_StatListNode(self, node):
        self.visitchildren(node)

    def visit_CDefExternNode(self, node):
        if node.include_file is None:
            file = '*'
        else:
            file = '"%s"' % node.include_file
        self.putline("cdef extern from %s:" % file)
        self._visit_indented(node.body)

    def visit_CPtrDeclaratorNode(self, node):
        self.put('*')
        self.visit(node.base)

    def visit_CReferenceDeclaratorNode(self, node):
        self.put('&')
        self.visit(node.base)

    def visit_CArrayDeclaratorNode(self, node):
        self.visit(node.base)
        self.put('[')
        if node.dimension is not None:
            self.visit(node.dimension)
        self.put(']')

    def visit_CFuncDeclaratorNode(self, node):
        # TODO: except, gil, etc.
        self.visit(node.base)
        self.put('(')
        self.comma_separated_list(node.args)
        self.endline(')')

    def visit_CNameDeclaratorNode(self, node):
        self.put(node.name)

    def visit_CSimpleBaseTypeNode(self, node):
        # See Parsing.p_sign_and_longness
        if node.is_basic_c_type:
            self.put(("unsigned ", "", "signed ")[node.signed])
            if node.longness < 0:
                self.put("short " * -node.longness)
            elif node.longness > 0:
                self.put("long " * node.longness)
        if node.name is not None:
            self.put(node.name)

    def visit_CComplexBaseTypeNode(self, node):
        self.visit(node.base_type)
        self.visit(node.declarator)

    def visit_CNestedBaseTypeNode(self, node):
        self.visit(node.base_type)
        self.put('.')
        self.put(node.name)

    def visit_TemplatedTypeNode(self, node):
        self.visit(node.base_type_node)
        self.put('[')
        self.comma_separated_list(node.positional_args + node.keyword_args.key_value_pairs)
        self.put(']')

    def visit_CVarDefNode(self, node):
        self.startline("cdef ")
        self.visit(node.base_type)
        self.put(" ")
        self.comma_separated_list(node.declarators, output_rhs=True)
        self.endline()

    def _visit_container_node(self, node, decl, extras, attributes):
        # TODO: visibility
        self.startline(decl)
        if node.name:
            self.put(' ')
            self.put(node.name)
            if node.cname is not None:
                self.put(' "%s"' % node.cname)
        if extras:
            self.put(extras)
        self.endline(':')
        self.indent()
        if not attributes:
            self.putline('pass')
        else:
            for attribute in attributes:
                self.visit(attribute)
        self.dedent()

    def visit_CStructOrUnionDefNode(self, node):
        if node.typedef_flag:
            decl = 'ctypedef '
        else:
            decl = 'cdef '
        if node.visibility == 'public':
            decl += 'public '
        if node.packed:
            decl += 'packed '
        decl += node.kind
        self._visit_container_node(node, decl, None, node.attributes)

    def visit_CppClassNode(self, node):
        extras = ""
        if node.templates:
            extras = "[%s]" % ", ".join(node.templates)
        if node.base_classes:
            extras += "(%s)" % ", ".join(node.base_classes)
        self._visit_container_node(node, "cdef cppclass", extras, node.attributes)

    def visit_CEnumDefNode(self, node):
        self._visit_container_node(node, "cdef enum", None, node.items)

    def visit_CEnumDefItemNode(self, node):
        self.startline(node.name)
        if node.cname:
            self.put(' "%s"' % node.cname)
        if node.value:
            self.put(" = ")
            self.visit(node.value)
        self.endline()

    def visit_CClassDefNode(self, node):
        assert not node.module_name
        if node.decorators:
            for decorator in node.decorators:
                self.visit(decorator)
        self.startline("cdef class ")
        self.put(node.class_name)
        if node.base_class_name:
            self.put("(")
            if node.base_class_module:
                self.put(node.base_class_module)
                self.put(".")
            self.put(node.base_class_name)
            self.put(")")
        self.endline(":")
        self._visit_indented(node.body)

    def visit_CTypeDefNode(self, node):
        self.startline("ctypedef ")
        self.visit(node.base_type)
        self.put(" ")
        self.visit(node.declarator)
        self.endline()

    def visit_FuncDefNode(self, node):
        # TODO: support cdef + cpdef functions
        self.startline("def %s(" % node.name)
        self.comma_separated_list(node.args)
        self.endline("):")
        self._visit_indented(node.body)

    def visit_CFuncDefNode(self, node):
        self.startline('cpdef ' if node.overridable else 'cdef ')
        if node.modifiers:
            self.put(' '.join(node.modifiers))
            self.put(' ')
        if node.visibility != 'private':
            self.put(node.visibility)
            self.put(' ')
        if node.api:
            self.put('api ')

        if node.base_type:
            self.visit(node.base_type)
            if node.base_type.name is not None:
                self.put(' ')

        # visit the CFuncDeclaratorNode, but put a `:` at the end of line
        self.visit(node.declarator.base)
        self.put('(')
        self.comma_separated_list(node.declarator.args)
        self.endline('):')

        self._visit_indented(node.body)

    def visit_CArgDeclNode(self, node):
        # For "CSimpleBaseTypeNode", the variable type may have been parsed as type.
        # For other node types, the "name" is always None.
        if not isinstance(node.base_type, CSimpleBaseTypeNode) or \
                node.base_type.name is not None:
            self.visit(node.base_type)

            # If we printed something for "node.base_type", we may need to print an extra ' '.
            #
            # Special case: if "node.declarator" is a "CNameDeclaratorNode",
            # its "name" might be an empty string, for example, for "cdef f(x)".
            if node.declarator.declared_name():
                self.put(" ")
        self.visit(node.declarator)
        if node.default is not None:
            self.put(" = ")
            self.visit(node.default)

    def visit_CImportStatNode(self, node):
        self.startline("cimport ")
        self.put(node.module_name)
        if node.as_name:
            self.put(" as ")
            self.put(node.as_name)
        self.endline()

    def visit_FromCImportStatNode(self, node):
        self.startline("from ")
        self.put(node.module_name)
        self.put(" cimport ")
        first = True
        for pos, name, as_name, kind in node.imported_names:
            assert kind is None
            if first:
                first = False
            else:
                self.put(", ")
            self.put(name)
            if as_name:
                self.put(" as ")
                self.put(as_name)
        self.endline()

    def visit_NameNode(self, node):
        self.put(node.name)

    def visit_DecoratorNode(self, node):
        self.startline("@")
        self.visit(node.decorator)
        self.endline()

    def visit_PassStatNode(self, node):
        self.startline("pass")
        self.endline()


class StatementWriter(DeclarationWriter):
    """
    A Cython code writer for most language statement features.
    """

    def visit_SingleAssignmentNode(self, node):
        self.startline()
        self.visit(node.lhs)
        self.put(" = ")
        self.visit(node.rhs)
        self.endline()

    def visit_CascadedAssignmentNode(self, node):
        self.startline()
        for lhs in node.lhs_list:
            self.visit(lhs)
            self.put(" = ")
        self.visit(node.rhs)
        self.endline()

    def visit_PrintStatNode(self, node):
        self.startline("print ")
        self.comma_separated_list(node.arg_tuple.args)
        if not node.append_newline:
            self.put(",")
        self.endline()

    def visit_ForInStatNode(self, node):
        self.startline("for ")
        if node.target.is_sequence_constructor:
            self.comma_separated_list(node.target.args)
        else:
            self.visit(node.target)
        self.put(" in ")
        self.visit(node.iterator.sequence)
        self.endline(":")
        self._visit_indented(node.body)
        if node.else_clause is not None:
            self.line("else:")
            self._visit_indented(node.else_clause)

    def visit_IfStatNode(self, node):
        # The IfClauseNode is handled directly without a separate match
        # for clariy.
        self.startline("if ")
        self.visit(node.if_clauses[0].condition)
        self.endline(":")
        self._visit_indented(node.if_clauses[0].body)
        for clause in node.if_clauses[1:]:
            self.startline("elif ")
            self.visit(clause.condition)
            self.endline(":")
            self._visit_indented(clause.body)
        if node.else_clause is not None:
            self.line("else:")
            self._visit_indented(node.else_clause)

    def visit_WhileStatNode(self, node):
        self.startline("while ")
        self.visit(node.condition)
        self.endline(":")
        self._visit_indented(node.body)
        if node.else_clause is not None:
            self.line("else:")
            self._visit_indented(node.else_clause)

    def visit_ContinueStatNode(self, node):
        self.line("continue")

    def visit_BreakStatNode(self, node):
        self.line("break")

    def visit_SequenceNode(self, node):
        self.comma_separated_list(node.args)  # Might need to discover whether we need () around tuples...hmm...

    def visit_ExprStatNode(self, node):
        self.startline()
        self.visit(node.expr)
        self.endline()

    def visit_InPlaceAssignmentNode(self, node):
        self.startline()
        self.visit(node.lhs)
        self.put(" %s= " % node.operator)
        self.visit(node.rhs)
        self.endline()

    def visit_WithStatNode(self, node):
        self.startline()
        self.put("with ")
        self.visit(node.manager)
        if node.target is not None:
            self.put(" as ")
            self.visit(node.target)
        self.endline(":")
        self._visit_indented(node.body)

    def visit_TryFinallyStatNode(self, node):
        self.line("try:")
        self._visit_indented(node.body)
        self.line("finally:")
        self._visit_indented(node.finally_clause)

    def visit_TryExceptStatNode(self, node):
        self.line("try:")
        self._visit_indented(node.body)
        for x in node.except_clauses:
            self.visit(x)
        if node.else_clause is not None:
            self.visit(node.else_clause)

    def visit_ExceptClauseNode(self, node):
        self.startline("except")
        if node.pattern is not None:
            self.put(" ")
            self.visit(node.pattern)
        if node.target is not None:
            self.put(", ")
            self.visit(node.target)
        self.endline(":")
        self._visit_indented(node.body)

    def visit_ReturnStatNode(self, node):
        self.startline("return")
        if node.value is not None:
            self.put(" ")
            self.visit(node.value)
        self.endline()

    def visit_ReraiseStatNode(self, node):
        self.line("raise")

    def visit_ImportNode(self, node):
        self.put("(import %s)" % node.module_name.value)

    def visit_TempsBlockNode(self, node):
        """
        Temporaries are output like $1_1', where the first number is
        an index of the TempsBlockNode and the second number is an index
        of the temporary which that block allocates.
        """
        idx = 0
        for handle in node.temps:
            self.tempnames[handle] = "$%d_%d" % (self.tempblockindex, idx)
            idx += 1
        self.tempblockindex += 1
        self.visit(node.body)

    def visit_TempRefNode(self, node):
        self.put(self.tempnames[node.handle])


class ExpressionWriter(TreeVisitor):
    """
    A Cython code writer that is intentionally limited to expressions.
    """

    def __init__(self, result=None, allow_unknown_nodes=False):
        super().__init__()
        if result is None:
            result = ""
        self.result = result
        self.allow_unknown_nodes = allow_unknown_nodes
        self.precedence = [0]

    def write(self, tree):
        self.visit(tree)
        return self.result

    def put(self, s):
        self.result += s

    def remove(self, s):
        if self.result.endswith(s):
            self.result = self.result[:-len(s)]

    def comma_separated_list(self, items):
        if len(items) > 0:
            for item in items[:-1]:
                self.visit(item)
                self.put(", ")
            self.visit(items[-1])

    def visit_Node(self, node):
        if self.allow_unknown_nodes:
            self.put("...")
        else:
            breakpoint()
            raise AssertionError("Node not handled by serializer: %r" % node)

    # TODO: Remove redundancy below. Most constants serialise fine as just "repr(node.value)".

    def visit_IntNode(self, node):
        self.put(node.value)

    def visit_FloatNode(self, node):
        self.put(node.value)

    def visit_NoneNode(self, node):
        self.put("None")

    def visit_NameNode(self, node):
        self.put(node.name)

    def visit_EllipsisNode(self, node):
        self.put("...")

    def visit_BoolNode(self, node):
        self.put(str(node.value))

    def visit_ConstNode(self, node):
        self.put(str(node.value))

    def visit_ImagNode(self, node):
        self.put(f"{node.value}j")

    def visit_BytesNode(self, node):
        self.put(repr(node.value))

    def visit_UnicodeNode(self, node):
        self.put(repr(node.value))

    def emit_sequence(self, node, parens=("", "")):
        open_paren, close_paren = parens
        items = node.subexpr_nodes()
        self.put(open_paren)
        self.comma_separated_list(items)
        self.put(close_paren)

    def visit_ListNode(self, node):
        self.emit_sequence(node, "[]")

    def visit_TupleNode(self, node):
        self.emit_sequence(node, "()")

    def visit_SetNode(self, node):
        if len(node.subexpr_nodes()) > 0:
            self.emit_sequence(node, "{}")
        else:
            self.put("set()")

    def visit_DictNode(self, node):
        self.emit_sequence(node, "{}")

    def visit_DictItemNode(self, node):
        self.visit(node.key)
        self.put(": ")
        self.visit(node.value)

    unop_precedence = {
        'not': 3, '!': 3,
        '+': 11, '-': 11, '~': 11,
    }
    binop_precedence = {
        'or': 1,
        'and': 2,
        # unary: 'not': 3, '!': 3,
        'in': 4, 'not_in': 4, 'is': 4, 'is_not': 4, '<': 4, '<=': 4, '>': 4, '>=': 4, '!=': 4, '==': 4,
        '|': 5,
        '^': 6,
        '&': 7,
        '<<': 8, '>>': 8,
        '+': 9, '-': 9,
        '*': 10, '@': 10, '/': 10, '//': 10, '%': 10,
        # unary: '+': 11, '-': 11, '~': 11
        '**': 12,
    }

    def operator_enter(self, new_prec):
        old_prec = self.precedence[-1]
        if old_prec > new_prec:
            self.put("(")
        self.precedence.append(new_prec)

    def operator_exit(self):
        old_prec, new_prec = self.precedence[-2:]
        if old_prec > new_prec:
            self.put(")")
        self.precedence.pop()

    def visit_NotNode(self, node):
        op = 'not'
        prec = self.unop_precedence[op]
        self.operator_enter(prec)
        self.put("not ")
        self.visit(node.operand)
        self.operator_exit()

    def visit_UnopNode(self, node):
        op = node.operator
        prec = self.unop_precedence[op]
        self.operator_enter(prec)
        self.put("%s" % node.operator)
        self.visit(node.operand)
        self.operator_exit()

    def visit_BinopNode(self, node):
        op = node.operator
        prec = self.binop_precedence.get(op, 0)
        self.operator_enter(prec)
        self.visit(node.operand1)
        self.put(" %s " % op.replace('_', ' '))
        self.visit(node.operand2)
        self.operator_exit()

    def visit_BoolBinopNode(self, node):
        self.visit_BinopNode(node)

    def visit_PrimaryCmpNode(self, node):
        self.visit_BinopNode(node)

    def visit_IndexNode(self, node):
        self.visit(node.base)
        self.put("[")
        if isinstance(node.index, TupleNode):
            if node.index.subexpr_nodes():
                self.emit_sequence(node.index)
            else:
                self.put("()")
        else:
            self.visit(node.index)
        self.put("]")

    def visit_SliceIndexNode(self, node):
        self.visit(node.base)
        self.put("[")
        if node.start:
            self.visit(node.start)
        self.put(":")
        if node.stop:
            self.visit(node.stop)
        if node.slice:
            self.put(":")
            self.visit(node.slice)
        self.put("]")

    def visit_SliceNode(self, node):
        if not node.start.is_none:
            self.visit(node.start)
        self.put(":")
        if not node.stop.is_none:
            self.visit(node.stop)
        if not node.step.is_none:
            self.put(":")
            self.visit(node.step)

    def visit_CondExprNode(self, node):
        self.visit(node.true_val)
        self.put(" if ")
        self.visit(node.test)
        self.put(" else ")
        self.visit(node.false_val)

    def visit_AttributeNode(self, node):
        self.visit(node.obj)
        self.put(".%s" % node.attribute)

    def visit_SimpleCallNode(self, node):
        self.visit(node.function)
        self.put("(")
        self.comma_separated_list(node.args)
        self.put(")")

    def emit_pos_args(self, node):
        if node is None:
            return
        if isinstance(node, AddNode):
            self.emit_pos_args(node.operand1)
            self.emit_pos_args(node.operand2)
        elif isinstance(node, TupleNode):
            for expr in node.subexpr_nodes():
                self.visit(expr)
                self.put(", ")
        elif isinstance(node, AsTupleNode):
            self.put("*")
            self.visit(node.arg)
            self.put(", ")
        else:
            self.visit(node)
            self.put(", ")

    def emit_kwd_args(self, node):
        if node is None:
            return
        if isinstance(node, MergedDictNode):
            for expr in node.subexpr_nodes():
                self.emit_kwd_args(expr)
        elif isinstance(node, DictNode):
            for expr in node.subexpr_nodes():
                self.put("%s=" % expr.key.value)
                self.visit(expr.value)
                self.put(", ")
        else:
            self.put("**")
            self.visit(node)
            self.put(", ")

    def visit_GeneralCallNode(self, node):
        self.visit(node.function)
        self.put("(")
        self.emit_pos_args(node.positional_args)
        self.emit_kwd_args(node.keyword_args)
        self.remove(", ")
        self.put(")")

    def emit_comprehension(self, body, target,
                           sequence, condition,
                           parens=("", "")):
        open_paren, close_paren = parens
        self.put(open_paren)
        self.visit(body)
        self.put(" for ")
        self.visit(target)
        self.put(" in ")
        self.visit(sequence)
        if condition:
            self.put(" if ")
            self.visit(condition)
        self.put(close_paren)

    def visit_ComprehensionAppendNode(self, node):
        self.visit(node.expr)

    def visit_DictComprehensionAppendNode(self, node):
        self.visit(node.key_expr)
        self.put(": ")
        self.visit(node.value_expr)

    def visit_ComprehensionNode(self, node):
        tpmap = {'list': "[]", 'dict': "{}", 'set': "{}"}
        parens = tpmap[node.type.py_type_name()]
        body = node.loop.body
        target = node.loop.target
        sequence = node.loop.iterator.sequence
        condition = None
        if hasattr(body, 'if_clauses'):
            # type(body) is Nodes.IfStatNode
            condition = body.if_clauses[0].condition
            body = body.if_clauses[0].body
        self.emit_comprehension(body, target, sequence, condition, parens)

    def visit_GeneratorExpressionNode(self, node):
        body = node.loop.body
        target = node.loop.target
        sequence = node.loop.iterator.sequence
        condition = None
        if hasattr(body, 'if_clauses'):
            # type(body) is Nodes.IfStatNode
            condition = body.if_clauses[0].condition
            body = body.if_clauses[0].body.expr.arg
        elif hasattr(body, 'expr'):
            # type(body) is Nodes.ExprStatNode
            body = body.expr.arg
        self.emit_comprehension(body, target, sequence, condition, "()")


class PxdWriter(DeclarationWriter, ExpressionWriter):
    """
    A Cython code writer for everything supported in pxd files.
    (currently unused)
    """

    def __call__(self, node):
        print('\n'.join(self.write(node).lines))
        return node

    def visit_CFuncDefNode(self, node):
        if node.overridable:
            self.startline('cpdef ')
        else:
            self.startline('cdef ')
        if node.modifiers:
            self.put(' '.join(node.modifiers))
            self.put(' ')
        if node.visibility != 'private':
            self.put(node.visibility)
            self.put(' ')
        if node.api:
            self.put('api ')
        self.visit(node.declarator)

    def visit_StatNode(self, node):
        pass


class CodeWriter(StatementWriter, ExpressionWriter):
    """
    A complete Cython code writer.
    """
