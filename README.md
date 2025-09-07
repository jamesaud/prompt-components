# Prompt Components

This is a Python library for creating reusable, template-based components using dataclasses. Supports standard string formatting and Jinja2 templating (from strings or files), component nesting, lifecycle hooks, and swappable component interfaces.

This library emerged to fix the difficulty of maintaining shared text in prompts throughout a codebase (particularly for LLMs), and the lack of strong type hints with existing templating engines.

Have you ever written templates (Python/Jinja2) and wanted better type hint support? This library is for you!

## Overview

This library allows you to define structured prompt components using Python's `@dataclass`. These components can then be rendered into strings using associated templates. It's particularly useful for generating text like prompts where parts of the content are reusable and parameterizable.

Core tenets:

1. Composition over inheritance.

2. Unique text should be tested once and only once.

3. Type hints prevent bugs.

We find this philosophy leads to simplified refactoring and testing.



## Installation

**From Github**

Install directly from GitHub:

```bash
pip install git+https://github.com/jamesaud/prompt-components.git
```

**Locally**

Install from `pyproject.toml` with your favorite package manager - the only real dependency is `jinja2`.


## Usage Examples

### 1. Simple String Template

```python
import typing as t
from dataclasses import field
from prompt_components import dataclass_component, StringTemplate

@dataclass_component
class Greeting(StringTemplate):
    _template = "Hello, {name}! You are {age} years old."

    name: str
    age: int = 0 # Default field

# Usage
greeter = Greeting(name="Alice", age=30)
print(greeter.render())
# Output: Hello, Alice! You are 30 years old.

greeter_bob = Greeting(name="Bob")
print(greeter_bob.render())
# Output: Hello, Bob! You are 0 years old.
```

### 2. Jinja String Template

```python
import typing as t
from textwrap import dedent
from prompt_components import dataclass_component, JinjaStringTemplate

@dataclass_component
class ItemList(JinjaStringTemplate):
    _template = dedent("""
    Items:
    {% for item in items %}
    - {{ item }}
    {% endfor %}
    """).strip()
    items: list[str]

# Usage
lister = ItemList(items=["apple", "banana", "cherry"])
print(lister.render())
# Output:
# Items:
# - apple
# - banana
# - cherry
```

### 3. Nested Components

```python
import typing as t
from textwrap import dedent
from prompt_components import dataclass_component, StringTemplate


@dataclass_component
class Profile(StringTemplate):
    _template = dedent("""
    User Profile:
    {personal_greeting}
    Bio: {bio}
    """).strip()
    personal_greeting: Greeting # Nested component
    bio: str

# Usage
alice_profile = Profile(
    personal_greeting=Greeting(name="Alice", age=30),
    bio="Loves Python."
)
print(alice_profile.render())
# Output:
# User Profile:
# Hello, Alice! You are 30 years old.
# Bio: Loves Python.
```


### 4. Swappable Components

```python
@dataclass
class Tool:
    name: str
    description: str


@dataclass_swappable_component
class Docs(StringTemplate):
    tool: Tool

@dataclass_component
class JsonDocs(Docs):
    _template = dedent("""
    {
        tool_name: {tool.name}
        tool_description: {tool.description}
    }
    """).strip()

@dataclass_component
class YamlDocs(Docs):
    _template = dedent("""
    Tool:
      - name: {tool.name}
      - description: {tool.description}
    """).strip()

@dataclass_component
class ToolsDocs(JinjaStringTemplate):
    _template = dedent("""
    {% for tool_doc in tools_docs %}
    {{tool_doc}}
    {% endfor %}
    """).strip()

    # User Vars
    tools: list[Tool]
    docs_component: type[Docs] = JsonDocs # A swappable component

    # Template Vars
    tools_docs: list[Docs] = template_field()

    @classmethod
    def _pre_render(cls, self: t.Self):
        self.tools_docs = [self.docs_component(tool) for tool in self.tools]

tools = [Tool(name="a", description"a tool"), Tool(name="b", description="b tool")]

json_tools_docs = ToolsDocs(tools=tools)
yaml_tools_docs = ToolsDocs(tools=tools, docs_component=YamlDocs) # Swap out components easily!

```

The `dataclass_swappable_component` must be used for swappable components (`type[<Component>]`) or an error will be raised. This is to enforce [LSP](https://en.wikipedia.org/wiki/Liskov_substitution_principle) on the initialization of the component (i.e. disallows new required fields). Notice that in `_pre_render`, the line `self.docs_component(tool)` *relies* on the init signature of the dataclass component.

For example:

```python
@dataclass_swappable_component
class Docs(Component):
    tool: Tool

# This will raise an Exception, all children must be consistent with the parent signature
@dataclass_component
class CustomDocs(Docs):
    extra: str

# This is fine, as a default value makes the child initialization consistent with the parent
# It can safely be swapped out for the parent class.
@dataclass_component
class CustomDocs(Docs):
    extra: str = "default_value"
```


## Dataclass Concepts
Any class marked with `@dataclass_component` *is a dataclass* and follows all of the semantics of dataclasses. Familiarizing yourself with the [dataclasses api](https://docs.python.org/3/library/dataclasses.html) is well advised, since this library utilizes these features to great extent.

**Important:** Only fields that are visible after the dataclass initiliazation are sent to the template for rendering (i.e. returned by [fields](https://docs.python.org/3/library/dataclasses.html#dataclasses.fields)).


```python
from dataclasses import field

@dataclass_component
class MyTemplate(Component):
    # These are sent to template
    a: str
    b: int = field(init=False)

    # These are not sent
    c: t.ClassVar[str]
    e: InitVar[int]
    d = "no type hint"

MyTemplate.e = "dynamic_value" # Not sent
```

The @dataclass_component decorator is a wrapper around @dataclass, and is compatible with all the same features:

```python
@dataclass_component(kw_only=True, frozen=True)
class MyTemplate(Component):
    ...
```

## Template Fields

Template fields should be used for any field that's dynamically computed from other fields.

At some point you may try to print an object with an unintialized variable and encounter errors:

```python
@dataclass_component
class MyComponent(StringTemplate):
    _template = "a is {a}, b is {b}"

    a: str
    b: str = field(init=False)

    @classmethod
    def _pre_render(cls, self: t.Self):
        self.b = self.a.upper()

print(MyComponent(a="a")) # > AttributeError: 'MyComponent' object has no attribute 'b'
```

The attribute is not set until `_pre_render` runs, which hasn't happened yet. To safeguard against these cases, a function `template_field()` is provided. This is merely defined as a dataclass field with some defaults set: `template_field = functools.partial(field, init=False, repr=False, compare=False)`. Correct usage would be:


```python
@dataclass_component
class MyComponent(StringTemplate):
    _template = "a is {a}, b is {b}"

    a: str
    b: str = template_field()

    @classmethod
    def _pre_render(cls, self: t.Self):
        self.b = self.a.upper()

component = MyComponent(a="a")
print(component) # Prints MyComponent(a="a")
print(component.render()) # Prints a is a, b is A
```

**Key Features:**

* **Dataclass-based:** Leverages the simplicity and type-safety of dataclasses.
* **Templating:** Supports rendering using:
    * Standard Python `.format()` strings (`StringTemplate`).
    * Jinja2 templates defined as strings (`JinjaStringTemplate`).
    * Jinja2 templates loaded from files (`JinjaFileTemplateBase`).
    * Jinja2 templates loaded from files relative to the component definition (`JinjaRelativeFileTemplateBase`).
* **Nesting:** Components can contain other components, which are recursively rendered.
* **Lifecycle Hooks:** Provides `render`, `_pre_render`, and `_post_render` hooks for custom logic during initialization and rendering.
* **Swappability:** Define "swappable" components (`@dataclass_swappable_component`) that enforce a consistent initialization interface across subclasses, allowing them to be interchanged easily.
* **Type Safety:** Uses type hints and performs checks, especially for swappable component types. Encourages to use `jinja2` constructs only where necessary, preferring to write our logic as fully type hinted python code!


## Component Lifecycle and Rendering

Understanding the component lifecycle, primarily driven by the `.render()` method and influenced by optional hooks, is key to customizing behavior.

### Initialization (`__post_init__`)

* **What it is:** The standard method provided by Python's `dataclasses` (see [docs](https://docs.python.org/3/library/dataclasses.html#dataclasses.__post_init__)).
* **When it runs:** Immediately after the component instance has been created and its fields initialized by the dataclass-generated `__init__`. This happens *before* any rendering.
* **What it operates on:** The **original component instance** (`self`). Modifications are permanent for that instance.
* **When to use it:** For initial validation, computing derived attributes that should be part of the component's *permanent* state, or setting up internal state.

**Warning**: Using post_init is NOT recommended for most cases - if in doubt, always prefer `_pre_render`.

### Pre-Render Hook (`_pre_render`)

* **What it is:** A custom hook provided by this library.
* **When it runs:** During the `.render()` call, *after* a shallow copy of the instance is made but *before* template variables are extracted from it.
* **What it operates on:** A **shallow copy** of the component instance. Modifications **do not** affect the original object and only apply to the current render call.
* **When to use it:** For modifications or calculations needed *specifically for rendering* without altering the original component's state. Ideal for applying formatting, calculating temporary values based on the current state, and ensuring logic is always up-to-date at render time. Generally preferred over `__post_init__` for render-specific transformations.
* **Signature:** `def _pre_render(cls, self: t.Self):`

Pre-render should be used for template variables that rely on calculation based on user-supplied variables.

It's important to note that `_pre_render` is a classmethod and operates on *shallow copies* of the dataclass object. This lets us assign to attributes without overwriting the original instance:

```python
@dataclass_component
class Name(StringTemplate):
    _template = "Hello {first_name}, your full name is {full_name}."

    # User vars
    first_name: str
    last_name: str

    # Template vars
    full_name: str = template_field()

    @classmethod
    def _pre_render(cls, self: t.Self):
        self.full_name = self.first_name + " " + self.last_name
        self.first_name = self.first_name.upper()

name = Name("John", "Smith")
print(name.render()) # -> Hello JOHN your full name is John Smith
```

The reason that `_pre_render` works on a shallow copy is:
1. Provides safety across multiple renders.
2. Allows dynamically changing of attributes before rendering (common pitfall of post_init)

In a world where the same instance was mutated:
- if we were to call `.render()` twice in this example, the first render would be ``Hello JOHN your full name is John Smith`` and the second would become `Hello JOHN your full name is JOHN Smith`



### Post-Render Hook (`_post_render`)

* **What it is:** A custom hook provided by this library.
* **When it runs:** During the `.render()` call, *after* all fields (including nested renders) have been processed into a dictionary, but *before* this dictionary is passed to the template engine.
* **What it operates on:** The **dictionary of template variables** (`template_vars`). The hook **must return** a dictionary (potentially modified).
* **When to use it:** For final adjustments to the *entire context dictionary* just before template rendering. Useful for adding global template variables, renaming keys, or performing calculations based on the fully assembled context.
* **Signature:** `def _post_render(cls, template_vars: dict[str, t.Any]) -> dict[str, t.Any]:`

Post render is after the rendering of all child components, but NOT after the rendering of the component itself. Post render allows control over what variables are actually passed to the jinja template:

```python
@dataclass_component
class MyComponent(StringTemplate):
    _template = "a is {var_a}"

    a: str

    @classmethod
    def _post_render(cls, template_vars: dict[str, t.Any]):
        """Postprocessing before the dictionary is sent to the template"""
        # Adds `var_a` to the dict and removes `a`
        template_vars['var_a'] = template_vars.pop('a')
        return template_vars
```



### The Rendering Process (`render`)

* **What it is:** The main public method called to generate the component's string output.
* **When it runs:** Explicitly called by the user on a component instance.
* **What it does:**
    1.  Orchestrates the entire rendering sequence.
    2.  Internally triggers the preparation of template variables. This process involves:
        * Creating a shallow copy of the component instance.
        * Calling the `_pre_render` hook on this copy.
        * Processing all component fields, recursively calling `.render()` on any nested component instances.
        * Calling the `_post_render` hook on the assembled dictionary of variables.
    3.  Passes the final variable dictionary to the appropriate template engine (Jinja2 or `.format`).
    4.  Returns the final rendered string.
* **When to use it:** This is the method you call whenever you need the string representation of your configured component.
* **Signature:** `def render(self) -> str:`

This is the true post rendering hook for the entire component. It can be useful for operating on the final string:

```python
@dataclass_component
class MyComponent(StringTemplate):
    _template = "a is {a}"

    a: str

    def render(self) -> str:
        rendered_string = super().render()
        return rendered_string.lstrip() # Strips the left new line character.
```

### Component Protocol

An interface defining the expected structure of a component, including `render` and lifecycle hooks. Components should generally inherit from one of the template base classes, which implement this protocol.


## License

This project is licensed under the MIT License:

```
MIT License

Copyright (c) 2024 prompt-components

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
