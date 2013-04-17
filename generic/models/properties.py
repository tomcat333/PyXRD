# coding=UTF-8
# ex:ts=4:sw=4:et=on

# Copyright (c) 2013, Mathijs Dumon
# All rights reserved.
# Complete license can be found in the LICENSE file.

from warnings import warn
from generic.controllers.handlers import widget_types

class IndexProperty(object):
    """decorator used to create indexable properties (e.g. W[1,1])"""
    
    def __init__(self, fget=None, fset=None, fdel=None, doc=None):
        if doc is None and fget is not None and hasattr(fget, "__doc__"):
            doc = fget.__doc__
        self._get = fget
        self._set = fset
        self._del = fdel
        self.__doc__ = doc
    
    def __get__(self, instance, owner):
        if instance is None:
            return self
        else:
            return BoundIndexProperty(self, instance)
    
    def __set__(self, instance, value):
        raise AttributeError, "can't set attribute"
    
    def __delete__(self, instance):
        raise AttributeError, "can't delete attribute"
    
    def getter(self, fget):
        return IndexProperty(fget, self._set, self._del, self.__doc__)

    def setter(self, fset):
        return IndexProperty(self._get, fset, self._del, self.__doc__)
    
    def deleter(self, fdel):
        return IndexProperty(self._get, self._set, fdel, self.__doc__)

class BoundIndexProperty(object):
    
    def __init__(self, item_property, instance):
        self.__item_property = item_property
        self.__instance = instance

    def __getitem__(self, key):
        fget = self.__item_property._get
        if fget is None:
            raise AttributeError, "unreadable attribute item"
        return fget(self.__instance, key)
    
    def __setitem__(self, key, value):
        fset = self.__item_property._set
        if fset is None:
            raise AttributeError, "can't set attribute item"
        fset(self.__instance, key, value)
    
    def __delitem__(self, key):
        fdel = self.__item_property._del
        if fdel is None:
            raise AttributeError, "can't delete attribute item"
        fdel(self.__instance, key)

class MultiProperty(object):
    def __init__(self, value, mapper, callback, options):
        object.__init__(self)
        self.value = value
        self.mapper = mapper
        self.callback = callback
        self.options = options
        
    def create_accesors(self, prop):
        def getter(model):
            return getattr(model, prop)
        def setter(model, value):
            value = self.mapper(value)
            if value in self.options:
                setattr(model, prop, value)
                if callable(self.callback):
                    self.callback(model, prop, value)
            else:
                raise ValueError, "'%s' is not a valid value for %s!" % (value, prop)
        return getter, setter

class PropIntel(object):
    _container = None
    @property
    def container(self):
        return self._container
    @container.setter
    def container(self, value):
        self._container = value

    _label = ""
    @property
    def label(self):
        if callable(self._label):
            return self._label(self, self.container)
        else:
            return self._label
    @label.setter
    def label(self, value):
        self._label = value

    inh_name = None
    
    minimum = None
    maximum = None
    
    is_column = False
    data_type = object #type of the value instance
    widget_type = 'input' #string description of the widget type
    widget_handler = None
    refinable = False
    storable = False
    observable = True
    has_widget = False

    def __init__(self, **kwargs):
        object.__init__(self)
        
        if "ctype" in kwargs:
            #deprecated and ignored!
            ctype = kwargs.pop("ctype")
            warn("The use of the keyword '%s' is deprecated for %s!" % ("ctype", type(self)), DeprecationWarning)
        
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
            
        # check if the widget type matches with the data type:
        if 'widget_type' in kwargs:
            data_type = None
            for wid, tp in widget_types:
                if wid == self.widget_type:
                    data_type = tp
            if data_type != self.data_type:
                raise AttributeError, "Data type '%s' does not match with widget type '%s'!" % (self.data_type, self.widget_type)            
        else:
            # if the widget type is not explicitly set,
            # set manually:
            self.widget_type = self._get_default_widget_type()
            
    def __eq__(self, other):
        return other!=None and self.name == other.name

    def __neq__(self, other):
        return other!=None and self.name != other.name

    def _get_default_widget_type(self):
        for wid, tp in widget_types:
            if tp == self.data_type:
                return wid
                
    def get_widget_handler(self):
        if isinstance(self.widget_handler, basestring) and hasattr(self.container, self.widget_handler):
            self.widget_handler = getattr(self.container, self.widget_handler)
            return self.widget_handler

    pass #end of class
