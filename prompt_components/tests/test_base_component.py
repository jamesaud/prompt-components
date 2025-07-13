import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from jinja2 import BaseLoader, Environment, FileSystemLoader

from prompt_components import (
    Component,
    JinjaRelativeFileTemplateBase,
    JinjaStringTemplate,
    StringTemplate,
    dataclass_component,
    dataclass_swappable_component,
)
from prompt_components.decorators import is_dataclass_swappable_component


@dataclass_swappable_component
class MyComponent(Component):
    a: str

    def render(self) -> str: ...


def test_component():
    component = MyComponent(a="a")
    assert component.a == "a"


@dataclass_component
class MyChildComponent(MyComponent):
    a: str = "x"


def test_component_inheritance():
    component = MyChildComponent()
    assert component.a == "x"


def test_components_inheritance_fails_with_new_attrs():
    with pytest.raises(
        TypeError,
        match=re.escape(
            (
                "Extra required attributes not allowed in class `InvalidChildComponent` when subclassing `MyComponent`: b.\nChild components must be consistent with the parent's attributes in order to have a composable interface."
            )
        ),
    ):

        @dataclass_component
        class InvalidChildComponent(MyComponent):  # type: ignore[reportUnusedClass]
            b: str


# Check case of odd inheritance where this does not use the decorator
class MyChildComponent1(MyComponent):
    pass


def test_component_odd_inheritance_fails_with_new_attrs():
    with pytest.raises(TypeError):

        @dataclass_component
        class _(MyChildComponent1):
            b: str


# This should not error
@dataclass_component
class test_component_inheritance_default(MyComponent):
    b: str = ""


# This should not error
@dataclass_component
class test_component_inheritance_default_field(MyComponent):
    b: str = field(default="")


# This should not error
@dataclass_component
class test_component_inheritance_default_field_factory(MyComponent):
    b: str = field(default_factory=lambda: "")


@dataclass_component(kw_only=True)
class KwOnlyComponent(MyComponent):
    a: str


def test_kwargs_passes_to_dataclass():
    assert is_dataclass_swappable_component(KwOnlyComponent)
    with pytest.raises(TypeError):
        KwOnlyComponent("a")  # type:ignore[reportCallIssue]


@dataclass_component
class MyStringComponent(StringTemplate):
    _template = "hello {a} {b}"

    a: str
    b: int


def test_string_template():
    component = MyStringComponent(a="a", b=1)
    assert component.render() == "hello a 1"


@dataclass
class Parent:
    a: str


@dataclass_component
class MyStringComponentInheritance(Parent, StringTemplate):
    _template = "hello {a}"


def test_inheritance_with_string_template():
    component = MyStringComponentInheritance(a="a")
    assert component.render() == "hello a"


@dataclass_component
class MyJinjaStringComponent(JinjaStringTemplate):
    _template = "hello {{a.upper()}}"
    a: str


def test_jinja_template():
    component = MyJinjaStringComponent(a="a")
    assert component.render() == "hello A"


@dataclass_component
class Dog(StringTemplate):
    _template = "Dog says: {woof}"
    woof: str


@dataclass_component
class Cat(StringTemplate):
    _template = "Cat says: {meow}"
    meow: str


@dataclass_component
class Lynx(Cat):
    _template = "Lynx says: {meow} and {rawr}"
    rawr: str = "rawr"


@dataclass_component
class Daycare(StringTemplate):
    _template = "{dog} {cat}"
    dog: Dog
    cat: Cat


def daycare(dog_component: t.Type[Dog], cat_component: t.Type[Cat]):
    return Daycare(dog=dog_component(woof="woof"), cat=cat_component(meow="meow"))


def test_prompt_replace_components():
    component = daycare(Dog, Lynx)
    assert component.render() == "Dog says: woof Lynx says: meow and rawr"


@dataclass_component
class CustomPreprocess(MyStringComponent):
    @classmethod
    def _pre_render(cls, self: t.Self):
        self.a = self.a.upper()


def test_preprocess():
    component = CustomPreprocess(a="a", b=1)
    assert component.render() == "hello A 1"


@dataclass_component
class CustomPostprocess(MyStringComponent):
    _template = "hello {x}"

    @classmethod
    def _post_render(cls, template_vars: dict[str, t.Any]):
        template_vars["x"] = template_vars["a"]
        del template_vars["a"]
        del template_vars["b"]
        return template_vars


def test_postprocess():
    component = CustomPostprocess(a="a", b=1)
    assert component.render() == "hello a"


@dataclass_component
class NonSwappableComponent(Component):
    pass


def test_invalid_swappable():
    with pytest.raises(
        TypeError,
        match=re.escape(
            r"""In <class 'test_base_component.test_invalid_swappable.<locals>.Invalid'>, field `a: type[test_base_component.NonSwappableComponent]` is not valid because the class <class 'test_base_component.NonSwappableComponent'> is not swappable. Please decorate the class (or any parent) with @dataclass_swappable_component."""
        ),
    ):

        @dataclass_component
        class Invalid(Component):  # type: ignore
            a: type[NonSwappableComponent]


@dataclass_swappable_component
class SwappableComponent(Component):
    pass


# This should not error
class test_subclass_of_swappable_parent_is_valid(SwappableComponent):
    a: type[MyComponent]


@dataclass_component
class ComponentWithType(Component):
    a: type[SwappableComponent] = SwappableComponent

    def render(self):
        return ""


def test_type_component_renders():
    # test if type[Component] doesn't error when set in a dataclass after calling `.render()`
    # asserts this doesn't cause an exception
    ComponentWithType().render()


@dataclass_component
class ListComponent(StringTemplate):
    _template = "{components}"
    components: list[t.Any]


def test_list_components():
    assert (
        ListComponent(
            [
                MyStringComponent(a="a", b=1),
                MyStringComponent(a="a", b=2),
                "a",
                3,
            ]
        ).render()
        == "['hello a 1', 'hello a 2', 'a', 3]"
    )


@dataclass_component
class DictComponent(StringTemplate):
    _template = "{components}"
    components: dict[t.Any, t.Any]


def test_dict_components():
    assert (
        DictComponent(
            {
                "key1": MyStringComponent(a="a", b=1),
                "key2": MyStringComponent(a="b", b=2),
                "key3": "value3",
                "key4": 4,
            }
        ).render()
        == "{'key1': 'hello a 1', 'key2': 'hello b 2', 'key3': 'value3', 'key4': 4}"
    )


@dataclass_component
class TupleComponent(StringTemplate):
    _template = "{components}"
    components: tuple[t.Any, ...]


def test_tuple_components():
    assert (
        TupleComponent(
            (
                MyStringComponent(a="a", b=1),
                MyStringComponent(a="b", b=2),
                "c",
                3,
            )
        ).render()
        == "('hello a 1', 'hello b 2', 'c', 3)"
    )


# Make an environment that's 2 folder above this current file.
JINJA_TEST_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent.parent.parent.resolve())
)


class JinjaRelativeFileTemplate(JinjaRelativeFileTemplateBase):
    _jinja_environment = JINJA_TEST_ENV
    _template_path = "relative_path"


def test_relative_path_file_template():
    template = JinjaRelativeFileTemplate()
    assert template._get_template_path() == "prompt_components/tests/relative_path"  # pyright: ignore[reportPrivateUsage]


def test_relative_path_file_template_dissalows_non_file_loaders():
    with pytest.raises(TypeError):

        class _(JinjaRelativeFileTemplateBase):
            _jinja_environment = Environment(loader=BaseLoader())
            _template_path = "relative_path"
