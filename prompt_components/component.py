import inspect
import os
import typing as t
from copy import copy
from dataclasses import (
    fields,
    is_dataclass,
)
from inspect import isclass

from jinja2 import BaseLoader, Environment, StrictUndefined
from jinja2.loaders import FileSystemLoader


# An isinstance check that only checks for object instances (returns False for subclsases)
def is_component_instance(value: t.Any):
    return isinstance(value, Component) and not (
        isclass(value) and issubclass(value, Component)
    )


def recursively_render(obj: t.Any) -> t.Any:
    if is_component_instance(obj):
        return obj.render()
    if isinstance(obj, list):
        return [recursively_render(item) for item in obj]  # type: ignore[reportUnknownVariableType]
    if isinstance(obj, tuple):
        return tuple(recursively_render(item) for item in obj)  # type: ignore[reportUnknownVariableType]
    if isinstance(obj, dict):
        return {k: recursively_render(v) for k, v in obj.items()}  # type: ignore[reportUnknownVariableType]
    return obj


def render_component_vars(component: "Component") -> dict[t.Any, t.Any]:
    """Makes a shallow copy of the component and recursively calls `.render()` on fields that are Components.
    The default `asdict` implementation has no way to provide custom serialization because `Component` is a dataclass, and by default
    it will it simply render its fields."""
    # Shallow copy into a new dataclass object, to avoid overwriting fields
    component = copy(component)
    #  Calls class method
    component._pre_render(component)  # pyright: ignore[reportPrivateUsage]

    if not is_dataclass(component):
        raise ValueError(f"Expected dataclass received {component}")

    # Recursively render fields and add them to dict
    rendered_vars: dict[str, t.Any] = {}
    for field_ in fields(component):
        value = getattr(component, field_.name)
        value = recursively_render(value)
        if isinstance(value, Component):
            value = value.render()  # Recursively render.
        rendered_vars[field_.name] = value

    exported_vars = component._post_render(rendered_vars)  # pyright: ignore[reportPrivateUsage]
    return exported_vars


@t.runtime_checkable
class Component(t.Protocol):
    """This class is a protocol to deal with the fact that dataclasses do not respect `is_instance` checks for inheritance.
    We must use runtime_checkable to check for subclasses of `Component`.

    Use the @dataclass_component on your components.

    Exported fields follow the rules of dataclasses:
     - underscore variables are private
     - t.ClassVar variables are private
     - dynamically set attributes are not exported

     There are 3 hooks:
      - __post_init__: Modify the original instance.
      - _pre_render: Modify a shallow copy of the dataclass before it's rendered.
      - _post_render: Modify the rendered dict that will be sent as variables to the template.

    Prefer `_pre_render` over `__post_init__` since it doesn't modify the original state of the object.
    _pre_render will not be stale (like post_init) if attributes are mutated.
    """

    def __post_init__(self):
        """Modify to run a custom init for dataclasses, see https://docs.python.org/3/library/dataclasses.html#dataclasses.__post_init__"""
        pass

    @classmethod
    def _pre_render(cls, self: t.Self):
        """Operates on a shallow copy of `self` before rendering.
        Modify existing attributes on the component to change them.
        This avoids modifying the original object."""
        pass

    @classmethod
    def _post_render(cls, template_vars: dict[str, t.Any]):
        """Postprocessing before the dictionary is sent to the template"""
        return template_vars

    def render(self) -> str:
        raise NotImplementedError()


DEFAULT_JINJA_ENV = Environment(loader=BaseLoader(), undefined=StrictUndefined)


class JinjaStringTemplate(Component, t.Protocol):
    """This class can be subclassed to override the jinja environment.
    A default environment for rendering strings is used."""

    _template: t.ClassVar[str]
    _jinja_environment: t.ClassVar[Environment] = DEFAULT_JINJA_ENV

    def render(self) -> str:
        template = self._jinja_environment.from_string(self._template)
        return template.render(**render_component_vars(self))  # pyright: ignore[reportArgumentType]


class StringTemplate(Component, t.Protocol):
    _template: t.ClassVar[str]

    def render(self) -> str:
        return self._template.format(**render_component_vars(self))  # pyright: ignore[reportArgumentType]


class JinjaFileTemplateBase(Component, t.Protocol):
    """This class is intended to be subclass, first with the environment set as a class var. E.g.
    ```
    my_environment = SandboxedEnvironment(...)

    class JinjaFileTemplate(JinjaFileTemplateBase):
        _jinja_environment: my_environment

    class MyTemplate(JinjaFileTemplate):
        _template = "path_to_template"
        var_a = "a"
    ```

    """

    _template_path: t.ClassVar[str]
    _jinja_environment: t.ClassVar[Environment]

    def _get_template_path(self) -> str:
        return self._template_path

    def render(self) -> str:
        template = self._jinja_environment.get_template(self._get_template_path())
        return template.render(**render_component_vars(self))  # pyright: ignore[reportArgumentType]


class JinjaRelativeFileTemplateBase(JinjaFileTemplateBase, t.Protocol):
    """
    Allows for defining templates as relative file paths to the current file.
    Absolute paths still must exist in the FileSystemLoader path(s) provided in the environment config.

    Subclasses must define:
      - _jinja_environment: an Environment with a FileSystemLoader
      - _template_path: a relative path to the template file (relative to the file where the subclass is defined)

    Example:

        my_environment = SandboxedEnvironment(
            loader=FileSystemLoader(searchpath=PROMPT_DIR),
            undefined=jinja2.StrictUndefined,
        )

        class JinjaFileTemplate(JinjaRelativeFileTemplateBase):
            _jinja_environment = my_environment

        # In some other file
        class MyTemplate(JinjaFileTemplate):
            _template_path = "relative_path_to_template.jinja2"
            var_a = "a"
    """

    def __init_subclass__(cls, **kwargs: t.Any):
        super().__init_subclass__(**kwargs)
        # Check that _jinja_environment is defined and its loader is a FileSystemLoader.
        env = getattr(cls, "_jinja_environment", None)
        if env is not None:
            loader = getattr(env, "loader", None)
            if not isinstance(loader, FileSystemLoader):
                raise TypeError(
                    "The Jinja environment's loader must be an instance of FileSystemLoader"
                )

    def _get_template_path(self) -> str:
        """
        Computes the template path relative to one of the loader's search paths.

        1. Determine the absolute path of the template based on where the subclass is defined.
        2. Iterate over all search directories in the loader.
        3. For the first search directory that is a prefix of the template's absolute path,
           compute and return the relative path.
        4. If none match, raise an error.
        """
        relative_template_path = super()._get_template_path()
        # Get the file where the subclass is defined.
        subclass_file = inspect.getfile(self.__class__)
        base_dir = os.path.dirname(os.path.abspath(subclass_file))
        abs_template_path = os.path.join(base_dir, relative_template_path)
        loader = t.cast(FileSystemLoader, self._jinja_environment.loader)
        # Iterate over all search directories
        for search_dir in loader.searchpath:
            norm_search_dir = os.path.abspath(search_dir)
            if abs_template_path.startswith(norm_search_dir):
                return os.path.relpath(abs_template_path, start=norm_search_dir)

        raise ValueError(
            f"Template '{abs_template_path}' is not within any of the search paths: "
            f"{loader.searchpath}"
        )
