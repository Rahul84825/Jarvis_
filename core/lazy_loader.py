"""
Thread-safe lazy import utilities for Jarvis.
Provides LazyModuleProxy and LazyAttrProxy to defer heavy third-party module imports
(e.g., sounddevice, pyautogui, faster_whisper, edge_tts, av, PIL) until runtime invocation.
"""

import sys
import types
import importlib
import threading
from typing import Any, Optional


class LazyModuleProxy(types.ModuleType):
    """
    Transparent proxy for an unimported module.
    Delegates all attribute accesses, calls, and operations to the real module
    once accessed for the first time.
    """

    def __init__(self, module_name: str, package: Optional[str] = None):
        super().__init__(module_name)
        self.__dict__["_lazy_module_name"] = module_name
        self.__dict__["_lazy_package"] = package
        self.__dict__["_lazy_real_module"] = None
        self.__dict__["_lazy_lock"] = threading.RLock()

    def _resolve(self) -> types.ModuleType:
        real = self.__dict__.get("_lazy_real_module")
        if real is not None:
            return real

        with self.__dict__["_lazy_lock"]:
            real = self.__dict__.get("_lazy_real_module")
            if real is not None:
                return real

            name = self.__dict__["_lazy_module_name"]
            pkg = self.__dict__["_lazy_package"]

            # If sys.modules already has the module (e.g. patched by unittest.mock), reuse it
            if name in sys.modules and sys.modules[name] is not self:
                real = sys.modules[name]
            else:
                real = importlib.import_module(name, package=pkg)

            self.__dict__["_lazy_real_module"] = real
            return real

    def __getattr__(self, name: str) -> Any:
        module = self._resolve()
        return getattr(module, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_lazy_"):
            super().__setattr__(name, value)
        else:
            module = self._resolve()
            setattr(module, name, value)

    def __delattr__(self, name: str) -> None:
        if name.startswith("_lazy_"):
            super().__delattr__(name)
        else:
            module = self._resolve()
            delattr(module, name)

    def __dir__(self):
        return dir(self._resolve())

    def __call__(self, *args, **kwargs) -> Any:
        module = self._resolve()
        return module(*args, **kwargs)

    def __repr__(self) -> str:
        real = self.__dict__.get("_lazy_real_module")
        if real is not None:
            return repr(real)
        return f"<LazyModuleProxy for '{self.__dict__['_lazy_module_name']}'>"

    def __bool__(self) -> bool:
        return True


class LazyAttrProxy:
    """
    Transparent proxy for a class, function, or attribute inside a module.
    Defers importing the parent module until the attribute is called, instantiated,
    or inspected.
    """

    def __init__(self, module_name: str, attr_name: str, package: Optional[str] = None):
        self._lazy_module_name = module_name
        self._lazy_attr_name = attr_name
        self._lazy_package = package
        self._lazy_target = None
        self._lazy_lock = threading.RLock()

    def _resolve(self) -> Any:
        if self._lazy_target is not None:
            return self._lazy_target

        with self._lazy_lock:
            if self._lazy_target is not None:
                return self._lazy_target

            # Check if module already in sys.modules (e.g., mock.patch)
            if self._lazy_module_name in sys.modules and sys.modules[self._lazy_module_name] is not None:
                mod = sys.modules[self._lazy_module_name]
            else:
                mod = importlib.import_module(self._lazy_module_name, package=self._lazy_package)

            self._lazy_target = getattr(mod, self._lazy_attr_name)
            return self._lazy_target

    def __call__(self, *args, **kwargs) -> Any:
        target = self._resolve()
        return target(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        target = self._resolve()
        return getattr(target, name)

    def __repr__(self) -> str:
        if self._lazy_target is not None:
            return repr(self._lazy_target)
        return f"<LazyAttrProxy for '{self._lazy_module_name}.{self._lazy_attr_name}'>"

    def __bool__(self) -> bool:
        return True


def lazy_import(name: str, package: Optional[str] = None) -> Any:
    """
    Lazily import a module. Returns a proxy that triggers the real import
    only upon the first attribute access or call.
    """
    return LazyModuleProxy(name, package=package)


def lazy_attr(module_name: str, attr_name: str, package: Optional[str] = None) -> Any:
    """
    Lazily import an attribute, class, or function from a module.
    """
    return LazyAttrProxy(module_name, attr_name, package=package)


def is_loaded(module_name: str) -> bool:
    """
    Return True if the specified module has actually been imported into sys.modules
    and is not just an unexecuted LazyModuleProxy.
    """
    mod = sys.modules.get(module_name)
    if mod is None:
        return False
    if isinstance(mod, LazyModuleProxy) and mod.__dict__.get("_lazy_real_module") is None:
        return False
    return True
