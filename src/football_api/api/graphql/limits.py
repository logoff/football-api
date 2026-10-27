"""Query limits checked during validation, before anything runs (design D6).

One walk over each operation, with fragments and the request's variables resolved, measures its
depth, aliases, page sizes and cost. Introspection fields (`__schema`, `__type`, `__typename`) count
for none of them.
"""

from collections.abc import Iterator
from typing import Any, cast

from graphql import (
    FieldNode,
    FragmentSpreadNode,
    GraphQLError,
    GraphQLNamedType,
    GraphQLObjectType,
    InlineFragmentNode,
    IntValueNode,
    OperationDefinitionNode,
    SelectionSetNode,
    ValidationContext,
    ValidationRule,
    VariableNode,
    get_named_type,
)
from strawberry.extensions import SchemaExtension

from football_api.api.pagination import DEFAULT_LIMIT, MAX_LIMIT

MAX_DEPTH = 10
MAX_ALIASES = 20
MAX_COST = 50_000  # admits the largest REST page: 200 matches with every relation (~38,400)

# Plain lists without `first`: the size counted for each (graphql-api spec, Query cost).
LIST_SIZES = {
    ("Match", "scorers"): 10,
    ("Match", "substitutions"): 12,
    ("Match", "cards"): 12,
    ("Lineup", "entries"): 25,
    ("Team", "seasons"): 40,
    ("Standings", "tables"): 12,
    ("StandingTable", "rows"): 24,
    ("StandingRow", "adjustments"): 2,
}


class _Walk:
    def __init__(self, context: ValidationContext, variables: dict[str, Any]) -> None:
        self.context = context
        self.variables = variables
        self.aliases = 0
        self.pages: list[tuple[FieldNode, int]] = []

    def fields(self, selections: SelectionSetNode, parent: GraphQLObjectType, seen: frozenset[str]) -> Iterator[tuple[FieldNode, GraphQLObjectType]]:
        for node in selections.selections:
            if isinstance(node, FieldNode):
                yield node, parent
            elif isinstance(node, InlineFragmentNode):
                yield from self.fields(node.selection_set, self._type(node.type_condition.name.value) if node.type_condition else parent, seen)
            elif isinstance(node, FragmentSpreadNode) and node.name.value not in seen:
                fragment = self.context.get_fragment(node.name.value)
                if fragment:
                    yield from self.fields(fragment.selection_set, self._type(fragment.type_condition.name.value), seen | {node.name.value})

    def _type(self, name: str) -> GraphQLObjectType:
        named = self.context.schema.get_type(name)
        assert isinstance(named, GraphQLObjectType)
        return named

    def first(self, node: FieldNode) -> int | None:
        """The `first` argument's value, from a literal or a variable; None when it isn't given."""
        for arg in node.arguments or ():
            if arg.name.value == "first":
                if isinstance(arg.value, IntValueNode):
                    return int(arg.value.value)
                if isinstance(arg.value, VariableNode):
                    value = self.variables.get(arg.value.name.value)
                    return value if isinstance(value, int) else None
        return None

    def measure(self, selections: SelectionSetNode, parent: GraphQLObjectType, level: int, seen: frozenset[str] = frozenset()) -> tuple[int, int]:
        """(depth, cost) of a selection set at `level`; stops descending past the depth limit."""
        depth = cost = 0
        for node, owner in self.fields(selections, parent, seen):
            name = node.name.value
            if name.startswith("__"):
                continue
            if node.alias:
                self.aliases += 1
            field = owner.fields.get(name)
            if field is None:
                continue  # unknown fields are reported by the standard rules
            child = cast(GraphQLNamedType, get_named_type(field.type))  # pyright reads graphql-core's overloads as unknown
            # a connection's `edges` and an edge's `node` add no depth (graphql-depth-by-objects D1)
            step = 0 if _wrapper(owner.name, name) else 1
            sub_depth = sub_cost = 0
            if node.selection_set and isinstance(child, GraphQLObjectType) and level < MAX_DEPTH + 1:
                sub_depth, sub_cost = self.measure(node.selection_set, child, level + step, seen)
            depth = max(depth, step + sub_depth)
            if not isinstance(child, GraphQLObjectType):
                continue  # scalars and enums cost nothing
            if "first" in field.args:  # a connection: its page size times what each node selects
                first = self.first(node) or DEFAULT_LIMIT
                self.pages.append((node, first))
                cost += first * (1 + sub_cost)
            else:
                cost += LIST_SIZES.get((owner.name, name), 1) * (1 + sub_cost)
        return depth, cost


def _wrapper(type_name: str, field_name: str) -> bool:
    return (field_name == "edges" and type_name.endswith("Connection")) or (field_name == "node" and type_name.endswith("Edge"))


def _refuse(node: Any, message: str, code: str, measured: int, limit: int) -> GraphQLError:
    return GraphQLError(message, nodes=node, extensions={"code": code, "measured": measured, "limit": limit})


def limits_rule(variables: dict[str, Any]) -> type[ValidationRule]:
    class QueryLimits(ValidationRule):
        def enter_operation_definition(self, node: OperationDefinitionNode, *_: object) -> None:
            root = self.context.schema.get_root_type(node.operation)
            if root is None:
                return  # mutations and subscriptions: the standard rules refuse them
            walk = _Walk(self.context, variables)
            depth, cost = walk.measure(node.selection_set, root, 1)
            if depth > MAX_DEPTH:
                # `depth` stops at MAX_DEPTH + 1: the walk doesn't descend further
                self.report_error(_refuse(node, f"Query is deeper than {MAX_DEPTH} levels", "query_too_deep", depth, MAX_DEPTH))
                return  # the walk stopped below the limit, so its cost is incomplete
            if walk.aliases > MAX_ALIASES:
                self.report_error(
                    _refuse(node, f"{walk.aliases} aliases exceed {MAX_ALIASES}", "too_many_aliases", walk.aliases, MAX_ALIASES)
                )
            for field, first in walk.pages:
                if first > MAX_LIMIT:
                    self.report_error(_refuse(field, f"`first` is at most {MAX_LIMIT}", "page_too_large", first, MAX_LIMIT))
            if cost > MAX_COST:
                self.report_error(_refuse(node, f"Query cost {cost} exceeds {MAX_COST}", "query_too_costly", cost, MAX_COST))

    return QueryLimits


class QueryLimitsExtension(SchemaExtension):
    """Adds the limits rule with this request's variables, which plain validation never sees."""

    def on_operation(self) -> Iterator[None]:
        ctx = self.execution_context
        ctx.validation_rules = (*ctx.validation_rules, limits_rule(ctx.variables or {}))
        yield
