"""Every public name of the core is documented and fully annotated.

The public surface of the core is what ``symq``, ``symq.sat``, ``symq.backends`` and
``symq.generators`` list in ``__all__``. A name there is something users are invited to call, so
it must say what it does, and its signature must be typed: the signatures are about to be frozen
in an API snapshot, and an unannotated parameter freezes as "anything".

Rules, checked on the live objects:

* each of the four packages has a module docstring and an ``__all__`` whose names all resolve;
* every public class and function has a docstring of its own. The text a ``@dataclass`` generates
  from its fields (``Name(field: type, ...)``) does not count;
* every public method and property of a public class has a docstring, its own or the one it
  inherits from the method it overrides (the ``Algebra`` operations are documented once, on the
  base class);
* every public function and method annotates all its parameters and its return value.

Constants (``BACKENDS``, ``POLICIES``, ...) are documented where they are defined and are not
checked here. ``symq.experimental`` and ``symq.labs`` carry no API promise and are out of scope.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
from collections.abc import Iterator
from typing import Any

import pytest

PACKAGES = ("symq", "symq.sat", "symq.backends", "symq.generators")


def exported(package: str) -> Iterator[tuple[str, Any]]:
    module = importlib.import_module(package)
    for name in module.__all__:
        value = getattr(module, name)
        if value is not None:  # the native algebras are ``None`` when the C core is not built
            yield f"{package}.{name}", value


def own_docstring(value: Any) -> str:
    """The object's own docstring, or ``""`` when it has none or only a generated one."""
    text = (value.__doc__ or "").strip()
    if inspect.isclass(value):
        if "__doc__" not in vars(value):
            return ""  # inherited from a base class: the class itself says nothing
        if dataclasses.is_dataclass(value) and text.startswith(f"{value.__name__}("):
            return ""
    return text


def members(cls: type) -> Iterator[tuple[str, Any, Any]]:
    """``(name, descriptor, function)`` for the public methods and properties ``cls`` defines."""
    for name, member in vars(cls).items():
        if name.startswith("_"):
            continue
        if isinstance(member, property):
            yield name, member, member.fget
        elif isinstance(member, (staticmethod, classmethod)):
            yield name, member, member.__func__
        elif inspect.isfunction(member):
            yield name, member, member


def member_docstring(cls: type, name: str) -> str:
    """A member's docstring: its own, or the nearest one along the MRO for what it overrides."""
    for base in cls.__mro__:
        if name not in vars(base):
            continue  # asking ``None`` instead would find ``NoneType``'s docstring (3.13+)
        candidate = vars(base)[name]
        candidate = getattr(candidate, "__func__", candidate)  # static and class methods
        text = (getattr(candidate, "__doc__", None) or "").strip()
        if text:
            return text
    return ""


def unannotated(function: Any) -> list[str]:
    signature = inspect.signature(function)
    missing = [parameter.name for parameter in signature.parameters.values()
               if parameter.annotation is parameter.empty and parameter.name not in ("self", "cls")]
    if signature.return_annotation is signature.empty:
        missing.append("return")
    return missing


def undocumented(qualified: str, value: Any) -> list[str]:
    found = []
    if inspect.isclass(value):
        if not own_docstring(value):
            found.append(qualified)
        found += [f"{qualified}.{name}" for name, _member, _function in members(value)
                  if not member_docstring(value, name)]
    elif inspect.isfunction(value) and not own_docstring(value):
        found.append(qualified)
    return found


def untyped(qualified: str, value: Any) -> list[str]:
    found = []
    if inspect.isclass(value):
        for name, _member, function in members(value):
            missing = unannotated(function)
            if missing:
                found.append(f"{qualified}.{name}: {missing}")
    elif inspect.isfunction(value):
        missing = unannotated(value)
        if missing:
            found.append(f"{qualified}: {missing}")
    return found


@pytest.mark.parametrize("package", PACKAGES)
def test_the_package_states_its_public_names(package):
    module = importlib.import_module(package)
    assert (module.__doc__ or "").strip(), f"{package} has no module docstring"
    assert isinstance(module.__all__, list) and len(set(module.__all__)) == len(module.__all__), \
        f"{package}.__all__ must be a list without repetition"
    for name in module.__all__:
        getattr(module, name)  # raises AttributeError for a name that does not resolve


@pytest.mark.parametrize("package", PACKAGES)
def test_every_public_name_is_documented(package):
    missing = [entry for qualified, value in exported(package)
               for entry in undocumented(qualified, value)]
    assert not missing, f"public names without a docstring: {missing}"


@pytest.mark.parametrize("package", PACKAGES)
def test_every_public_signature_is_annotated(package):
    missing = [entry for qualified, value in exported(package)
               for entry in untyped(qualified, value)]
    assert not missing, f"public signatures with missing annotations: {missing}"


def test_the_checks_see_what_they_claim():
    """The helpers above on small objects written for the purpose."""

    @dataclasses.dataclass
    class Generated:
        field: int

    @dataclasses.dataclass
    class Written:
        """A record with a real docstring."""

        field: int

    class Base:
        """A documented base."""

        def operation(self, value: int) -> int:
            """Documented once, here."""
            return value

        @property
        def size(self) -> int:
            """Documented once, here."""
            return 0

    class Override(Base):
        def operation(self, value: int) -> int:
            return value + 1

        @property
        def size(self) -> int:
            return 1

        def extra(self, value):
            return value

    def plain(left, right: int):
        return left

    assert undocumented("m.Generated", Generated) == ["m.Generated"]
    assert undocumented("m.Written", Written) == []
    assert undocumented("m.Base", Base) == []
    # The class has no docstring of its own; its overrides inherit theirs; ``extra`` has none.
    assert undocumented("m.Override", Override) == ["m.Override", "m.Override.extra"]
    assert undocumented("m.plain", plain) == ["m.plain"]
    assert untyped("m.Override", Override) == ["m.Override.extra: ['value', 'return']"]
    assert untyped("m.plain", plain) == ["m.plain: ['left', 'return']"]
    assert untyped("m.Base", Base) == []
