"""Metaprogramming utilities.

This module provide a set of various metaprogramming utilities
such as general purpose metaclasses, mixins and decorators.
"""
# pylint: disable=W0613,W0212
from collections import OrderedDict
from functools import singledispatch, update_wrapper

# Decorators ------------------------------------------------------------------

def methdispatch(func):
    """Single dispatch for instance methods."""
    dispatcher = singledispatch(func)
    def wrapper(*args, **kwds):
        """Internal wrapper."""
        return dispatcher.dispatch(args[1].__class__)(*args, **kwds)
    wrapper.register = dispatcher.register
    update_wrapper(wrapper, func)
    return wrapper

# Metaclasses -----------------------------------------------------------------

def __getattr__(self, attr):
    """Attribute lookup for composable classes."""
    components_attr = '_'+self.__class__.__name__+'__components'
    components = [
        *(getattr(self, '__components').items() if '__components' in dir(self) else []),
        *(getattr(self, components_attr).items() if components_attr in dir(self) else [])
    ]
    bases = (self.__class__, *self.__class__.__bases__)
    for base in bases:
        components_attr = '_'+base.__name__+'__components'
        components = [ *components, *getattr(base, components_attr, {}).items() ]
    for nm, component in components:
        if nm == attr:
            return component
        try:
            return getattr(component, attr)
        except AttributeError:
            pass
    cn = self.__class__.__name__
    raise AttributeError(f"'{cn}' does not have attribute '{attr}'")

def getcomponents_(self, clsname=None):
    """Get components dictionary.

    Parameters
    ----------
    clsname : str or None
        Class name for which components dict should be returned.
        If `None` then instance level components dict is returned.
    """
    components_attr = '__components'
    if clsname:
        components_attr = '_'+clsname+components_attr
    return getattr(self, components_attr)

def getcomponent_(self, component, clsname=None):
    """Get single component by name.

    Parameters
    ----------
    component : str
        Component name.
    clsname : str or None
        Optional name of the class for component lookup.
        If `None` then instance level components are searched.
    """
    components = self.getcomponents_(clsname)
    try:
        return components[component]
    except KeyError:
        if not clsname:
            clsname = self.__class__.__name__
        raise AttributeError(f"'{clsname}' does not have '{component}' component")

def setcomponents_(self, components):
    """Set instance level components.

    Parameters
    ----------
    components : list or tuple of 2-tuples
        Specification of component objects.
        Each 2-tuple consist of component name and object.
    """
    for nm, component in components:
        if hasattr(self, nm):
            errmsg = f"Instance already has attribute '{nm}'"
            raise AttributeError(errmsg)
        setattr(self, nm, component)
    self.__components = OrderedDict(components)

def getattribute_(self, attr, component, clsname=None):
    """Get attribute value from a class components.

    Parameters
    ----------
    attr : str
        Attribute name.
    component : str
        Component name.
    clsname : str
        Optional class name.
        If `None` then instance components are searched.
    """
    components = self.getcomponents_(clsname)
    try:
        component = components[component]
    except KeyError:
        raise AttributeError(f"'{clsname}' does not have component '{component}'")
    return getattr(component, attr)

def setattribute_(self, attr, value, on_component=True):
    """Set attribute on instance or on a component.

    Parameters
    ----------
    attr : str
        Attribute name.
    value : any
        Value to assign.
    on_component : bool or str
        Should value be assigned to a first component with
        given attribute or should be assigned at the instance level.
        If is `str` then attribute is set on a component with a given name.

    Raises
    ------
    AttributeError
        If `on_component=True` and no component with given `attr` was found.
    """
    if not on_component:
        setattr(self, attr, value)
        return
    components = \
        [ *(getattr(self, '__components') if '__components' in dir(self) else {}).items() ]
    bases = (self.__class__, *self.__class__.__bases__)
    for base in bases:
        components_attr = '_'+base.__name__+'__components'
        components = [ *components, *getattr(base, components_attr, {}).items() ]
    for _, component in components:
        if hasattr(component, attr):
            setattr(component, attr, value)
            return
    raise AttributeError(f"No component with '{attr}' attribute was found")


class Composable(type):
    """Metaclass for injecting easy class composition functionality.

    Class components may be defined on two different level:
    class level and instance level.

    In both cases they are defined based on a private class/instance
    attribute ``__components``, and this name automatically expands to
    ``_<classname>__components``. In both cases ``__component`` attribute
    must be a tuple of 2-tuples providing name (str) and component instance.
    Automatic name expansion does not matter as the metaclass extends the
    standard ``__getattr__`` method that solves this problem.

    Injected components may be accessed as standard attributes using the
    provided names. Moreover, all attributes of injected components
    also became accessible in the standard fashion. However, it should be
    noted that the order of specification of components matter in the case
    when multiple components define the same attribute.

    Also method delegation order is important, as first instance level
    components will be searched and then class level components in
    the standard order.

    Notes
    -----
    Differentiation between instance and class level components
    is useful, as it allow to define components available only for
    specific instances and which may be initialized in runtime
    within the host object ``__init__`` method.

    Components attributes after assignment are internally represented
    as :py:class:`collections.OrderedDict` instances to facilitate
    accessing by name while keeping the order fixed.

    Special methods:

    * :py:meth:`{{ cookiecutter.repo_name }}.base.meta.getcomponents_`,
    * :py:meth:`{{ cookiecutter.repo_name }}.base.meta.setcomponents_`,
    * :py:meth:`{{ cookiecutter.repo_name }}.base.meta.getattribute_`
    * :py:meth:`{{ cookiecutter.repo_name }}.base.meta.setattribute_`,

    are defined with trailing underscore to avoid name collisions.
    """
    def __new__(cls, name, bases, namespace, **kwds):
        """Class instance constructor."""
        newclass = super().__new__(cls, name, bases, namespace)
        setattr(newclass, __getattr__.__name__, __getattr__)
        setattr(newclass, getcomponents_.__name__, getcomponents_)
        setattr(newclass, setcomponents_.__name__, setcomponents_)
        setattr(newclass, getcomponent_.__name__, getcomponent_)
        setattr(newclass, getattribute_.__name__, getattribute_)
        setattr(newclass, setattribute_.__name__, setattribute_)
        components_attr = '_'+newclass.__name__+'__components'
        components = getattr(newclass, components_attr, None)
        if components:
            setattr(newclass, components_attr, OrderedDict(components))
        for nm, component in getattr(newclass, components_attr, {}).items():
            if hasattr(newclass, nm):
                errmsg = f"Class '{nm}' already has attribute '{newclass.__name__}'"
                raise AttributeError(errmsg)
            setattr(newclass, nm, component)
        return newclass


class Singleton(type):
    """Singleton metaclass."""
    instance = None
    def __call__(cls, *args, **kwds):
        """Calling method."""
        if not cls.instance:
            cls.instance = super().__call__(*args, **kwds)
        return cls.instance
