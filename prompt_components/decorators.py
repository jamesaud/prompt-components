import functools
import typing as t
from dataclasses import (
    _FIELDS as _DATACLASS_FIELDS,  # type: ignore
)
from dataclasses import (
    _MISSING_TYPE,  # pyright: ignore
    Field,
    dataclass,
    field,
    fields,
)

from .component import Component

if t.TYPE_CHECKING:
    from _typeshed import DataclassInstance


_DATACLASS_COMPONENT_SWAPPABLE = "__is_dataclass_component__"


def is_missing(val: t.Any) -> bool:
    return val is _MISSING_TYPE or isinstance(val, _MISSING_TYPE)


def is_required(field: Field[t.Any]) -> bool:
    """Checks whether a dataclass field is required or not."""
    if not is_missing(field.default):
        return False
    if not is_missing(field.default_factory):  # type: ignore
        return False
    if field.init is True:
        return True
    return False


def required_fields(cls: "DataclassInstance") -> list[Field[t.Any]]:
    return [f for f in fields(cls) if is_required(f)]


def is_dataclass_swappable_component(obj: object) -> bool:
    return hasattr(obj, _DATACLASS_COMPONENT_SWAPPABLE)


def check_swappable_fields(cls: "DataclassInstance"):
    for field_ in fields(cls):
        origin = t.get_origin(field_.type)
        args = t.get_args(field_.type)
        # If the field was defined as: type[Component]
        if origin is type:
            type_arg = args[0]

            if issubclass(type_arg, Component) and not is_dataclass_swappable_component(
                type_arg
            ):
                raise TypeError(
                    f"""In {cls}, field `{field_.name}: {field_.type}` is not valid because the class {type_arg} is not swappable. Please decorate the class (or any parent) with @dataclass_swappable_component."""
                )


@functools.wraps(dataclass)
def _dataclass_component(  # type: ignore[reportUnusedFunction]
    cls: t.Type[object] | None = None, /, swappable: bool = False, **kwargs: t.Any
):
    """Wrapper around dataclass that turns a class into a dataclass component.
    If swappable=True, enforces that child classes adhere to parent component's interface (i.e. has the same initialization interface).
    """
    # Handles case of calling with parenthesis: @dataclass(...)
    if cls is None:
        # Call this class again with a closure where the `cls` is first converted to a dataclass called with kwargs
        return lambda cls: _dataclass_component(dataclass(**kwargs)(cls))  # type: ignore[reportUnknownVariableType]

    # Handles case of calling without parenthesis: @dataclass
    if _DATACLASS_FIELDS not in cls.__dict__:
        cls = dataclass(cls)

    # Check if any fields are t.Type[Component] and validate it is a swappable component
    check_swappable_fields(cls)  # type: ignore

    # Need to dynamically modify the existing class to specify it is a dataclass_component.
    if swappable:
        setattr(cls, _DATACLASS_COMPONENT_SWAPPABLE, True)

    # Get the field names
    cls_fields = {f.name for f in required_fields(cls)}  # type: ignore

    # If a parent class is a dataclass, check that no extra required fields are present in the child class.
    # It's ok to only check direct with `__bases__` and not `__mro__` since fields(base) will contain all ancestors fields.
    for base in cls.__bases__:
        if is_dataclass_swappable_component(base):  # true if any ancestor is swappable
            # A class will have all fields of its ancestors plus any new fields it defined
            allowed_fields = {f.name for f in fields(base)}
            extra_fields = cls_fields - allowed_fields
            if extra_fields:
                raise TypeError(
                    f"Extra required attributes not allowed in class `{cls.__name__}` when subclassing `{base.__name__}`: {', '.join(extra_fields)}."
                    "\nChild components must be consistent with the parent's attributes in order to have a composable interface."
                )
    return cls


# There are special stubs for dataclass that are difficult to recreate so for typechecking just use dataclass

dataclass_component = dataclass if t.TYPE_CHECKING else _dataclass_component
dataclass_swappable_component = (
    dataclass
    if t.TYPE_CHECKING
    else functools.partial(_dataclass_component, swappable=True)
)


# Component Dataclass Helpers
template_field = functools.partial(field, init=False, repr=False, compare=False)
