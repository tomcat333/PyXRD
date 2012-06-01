# coding=UTF-8
# ex:ts=4:sw=4:et=on

# Author: Mathijs Dumon
# This work is licensed under the Creative Commons Attribution-ShareAlike 3.0 Unported License. 
# To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/3.0/ or send
# a letter to Creative Commons, 444 Castro Street, Suite 900, Mountain View, California, 94041, USA.

from collections import namedtuple
from generic.utils import whoami, smart_repos

import numpy as np
from scipy.interpolate import interp1d

from generic.io import Storable, PyXRDDecoder, get_json_type, json_type

from gtkmvc import Model, Observer

import gtk
import gobject
import json

class _BaseObjectListStore(gtk.GenericTreeModel):
    _columns = None #list of tuples (name, type)
    _class_type = None

    def __init__(self, class_type):
        gtk.GenericTreeModel.__init__(self)
        self.set_property("leak-references", False)
        if class_type is None:
            raise ValueError, 'Invalid class_type for %s! Expecting object, but None was given' % type(self)
        elif not hasattr(class_type, '__columns__'):
            raise ValueError, 'Invalid class_type for %s! %s does not have __columns__ attribute!' % (type(self), type(class_type))
        else:
            self.setup_class_type(class_type)

    def setup_class_type(self, class_type):
        self._class_type = class_type
        self._columns = self._class_type.__columns__
        i = 0
        for col in self._columns:
            setattr(self, "c_%s" % col[0], i)
            i += 1

    def on_get_flags(self):
        return gtk.TREE_MODEL_LIST_ONLY | gtk.TREE_MODEL_ITERS_PERSIST

    def on_get_n_columns(self):
        return len(self._columns)

    def on_get_column_type(self, index):
        return self._columns[index][1]

    def get_user_data_from_path(self, path):
        return self.on_get_iter(path)
        
    def convert(self, col, new_val):
        return self._columns[col][1](new_val)
        
    def get_raw_model_data(self):
        raise NotImplementedError

class ObjectListStore(_BaseObjectListStore, Storable):
    _model_data = None #list of objects of class_type

    __gsignals__ = { 
        'item-removed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'item-inserted' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }

    def __init__(self, class_type):
        _BaseObjectListStore.__init__(self, class_type)
        Storable.__init__(self)
        self._model_data = list()

    def json_properties(self):
        return { 'class_type': json_type(self._class_type),
                 'model_data': self._model_data }
        
    @classmethod
    def from_json(type, parent=None, class_type=None, model_data=None, **kwargs):
        class_type = get_json_type(class_type)
        store = type(class_type)
        decoder = PyXRDDecoder(parent=parent)
        for obj in model_data:
            item = decoder.__pyxrd_decode__(obj, parent=parent)
            store._model_data.append(item)
        store.invalidate_iters()
        return store

    def on_get_iter(self, path):
        try:
            return self._model_data[path[0]]
        except IndexError, msg:
            return None

    def on_get_path(self, rowref):
        try:
            return (self._model_data.index(rowref),)
        except ValueError:
            print "ValueError in on_get_path of %s caused by %s" % (self, rowref)
            return None

    def set_value(self, itr, column, value):
        user_data = self.get_user_data(itr)
        setattr(user_data, self._columns[column][0], value)
        self.row_changed(self.get_path(itr), itr)

    def on_get_value(self, rowref, column):
        return getattr(rowref, self._columns[column][0])

    def on_iter_next(self, rowref):
        n, = self.on_get_path(rowref)
        try:
            rowref = self._model_data[n+1]
        except IndexError, msg:
            rowref = None
        return rowref

    def on_iter_children(self, rowref):
        if rowref:
            return None
        if self._model_data:
            return self.on_get_iter((0,))
        return None

    def on_iter_has_child(self, rowref):
        if rowref:
            return False
        if len(self._model_data) > 0:
            return True
        return False

    def on_iter_n_children(self, rowref):
        if rowref:
            return 0
        return len(self._model_data)

    def on_iter_nth_child(self, parent, n):
        if parent:
            return None
        if n < 0 or n >= len(self._model_data):
            return None
        return self._model_data[n]

    def on_iter_parent(self, rowref):
        return None
        
    def append(self, item):
        if not isinstance(item, self._class_type):
            raise ValueError, 'Invalid type, must be %s but got %s instead' % (self._class_type, type(item))
        elif not self.item_in_model(item):
            self._model_data.append(item)
            return self._emit_added(item)          
    def insert(self, pos, item):
        if not isinstance(item, self._class_type):
            raise ValueError, 'Invalid type, must be %s but got %s instead' % (self._class_type, type(item))
        elif not self.item_in_model(item):
            self._model_data.insert(pos, item)
            return self._emit_added(item)
    def _emit_added(self, item):
        if hasattr(item, "__list_store__"):
            item.__list_store__ = self
        itr = self.create_tree_iter(item)
        path = self.get_path(itr)
        self.row_inserted(path, itr)
        self.emit('item-inserted', item)
        return path
                
    def remove(self, itr):
        self.remove_item(self.get_user_data(itr))
    def remove_item(self, item):
        self.__remove_item_index(item, self._model_data.index(item))
    def __remove_item_index(self, item, index):
        del self._model_data[index]
        if hasattr(item, "__list_store__"):
            item.__list_store__ = None
        self.emit('item-removed', item)
        self.row_deleted((index,))

    def clear(self, callback=None):
        data = list(self._model_data) #make a copy
        def reverse_enum(L):
           for index in reversed(xrange(len(L))):
              yield index, L[index]
        for i, item in reverse_enum(data):
            self.__remove_item_index(item, i)
            if callable(callback): callback(item)

    def on_item_changed(self, item):
        itr = self.create_tree_iter(item)
        path = self.get_path(itr)
        self.row_changed(path, itr)

    def item_in_model(self, item):
        return item in self._model_data

    def index(self, item):
        return self._model_data.index(item)
        
    def get_user_data_from_index(self, index):
        return self._model_data[index]
        
    def reposition_item(self, item, new_pos):
        old_pos = self._model_data.index(item)
        if old_pos != new_pos:
            new_order = smart_repos(len(self._model_data), old_pos, new_pos)   
            
            self._model_data.remove(item)
            self._model_data.insert(new_pos, item)
            
            itr = self.create_tree_iter(item)
            path = self.get_path(itr)
            self.rows_reordered(None, None, new_order)
    
    def move_item_down(self, item):
        if item!=None:
            old_pos = self._model_data.index(item)
            new_pos = old_pos + 1            
            if new_pos < len(self._model_data):
                self.reposition_item(item, new_pos)
    def move_item_up(self, item):
        if item!=None:
            old_pos = self._model_data.index(item)
            new_pos = old_pos - 1            
            if new_pos >= 0:
                self.reposition_item(item, new_pos) 
                
    def get_raw_model_data(self):
        return self._model_data

    pass #end of class

gobject.type_register(ObjectListStore)

class IndexListStore(ObjectListStore):
    
    _index_column_name = None
    _index = None
    
    _item_observer = None
    class ItemObserver(Observer):
        liststore = None
        
        ignore_next_notification = False
        
        def __init__(self, liststore, *args, **kwargs):
            self.liststore = liststore
            self.index_column_name = liststore._index_column_name
            Observer.__init__(self, *args, **kwargs)
            self.observe(self.notification, liststore._index_column_name, assign=True)
        
        def notification(self, model, prop_name, info):
            if not self.ignore_next_notification:
                if self.liststore.index_in_model(info["new"]):
                    self.ignore_next_notification = True
                    info["new"] = "%s_2" % info["new"]
                    setattr(model, self.liststore._index_column_name, info["new"])
                    self.liststore._index[info["new"]] = model
                    del self.liststore._index[info["old"]]
                    return
                else:
                    self.liststore._index[info["new"]] = model
                    del self.liststore._index[info["old"]]
            self.ignore_next_notification = False
    
    def __init__(self, class_type):
        if not hasattr(class_type, '__index_column__'):
            raise TypeError, "class_type should have an __index_column__ attribute, but %s has not" % class_type
        if not class_type.__index_column__ in zip(*class_type.__columns__)[0]:
            raise AttributeError, "The index column '%s' should be a member of the __columns__" % class_type.__index_column__
        if not class_type.__index_column__ in class_type.__observables__:
            raise AttributeError, "The index column '%s' should be a member of the __observables__" % class_type.__index_column__
        ObjectListStore.__init__(self, class_type)
        self._index = dict()
        self._index_column_name = class_type.__index_column__
        self._item_observer = IndexListStore.ItemObserver(liststore=self)
       
    def append(self, item):
        assert not self.item_in_model(item)
        return ObjectListStore.append(self, item)
    def insert(self, pos, item):
        assert not self.item_in_model(item)
        return ObjectListStore.insert(self, pos, item)
    def _emit_added(self, item):
        path = ObjectListStore._emit_added(self, item)
        self._index[getattr(item, self._index_column_name)] = item
        self._item_observer.observe_model(item)
        return path

    def remove_item(self, item):
        assert self.item_in_model(item)
        self._item_observer.relieve_model(item)
        del self._index[getattr(item, self._index_column_name)]
        ObjectListStore.remove_item(self, item)

    def clear(self):
        self._index.clear()
        ObjectListStore.clear(self, self._item_observer.relieve_model)
       
    def item_in_model(self, item):
        index = getattr(item, self._index_column_name)
        if index in self._index:
            print index
        return index in self._index

    def index_in_model(self, index):
        return (index in self._index)
        
    def get_item_by_index(self, index):
        if self.index_in_model(index):
            return self._index[index]
        else:
            return None
            
    def get_raw_model_data(self):
        return self._index

    pass #end of class

gobject.type_register(IndexListStore)

Point = namedtuple('Point', ['x', 'y'], verbose=False)
Point.__columns__ = [
    ('x', float),
    ('y', float)
]

#TODO: make use of numpy array for XYListStore

class XYListStore(_BaseObjectListStore, Storable):

    __gsignals__ = { 
        'item-removed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,)),
        'item-inserted' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
    }

    _model_data_x = None
    _model_data_y = None

    def __init__(self):
        _BaseObjectListStore.__init__(self, Point)
        Storable.__init__(self)
        self.set_property("leak-references", True)
        self._model_data_x = np.array([], dtype=float)
        self._model_data_y = np.array([], dtype=float)
        
    def json_properties(self):
        return {
            "data": "[%s]" % ",".join(["[%f,%f]"%(x,y) for x,y in zip(self._model_data_x,self._model_data_y)])
        }
        
    @staticmethod
    def from_json(data=None, **kwargs):
        xy = XYListStore()
        data = data.replace("nan", "0.0")
        data = zip(*json.JSONDecoder().decode(data))
        if data != []:
            xy.set_from_data(*data)
        return xy

    def on_get_iter(self, path): #returns a rowref
        try:
            path = path[0]
            if path < self._model_data_x.size:
                return (path, self._model_data_x[path], self._model_data_y[path])
            else:
                return None
        except IndexError, msg:
            return None
            
    def on_get_path(self, rowref):
        return (rowref[0],)

    def set_value(self, itr, column, value):
        i = self.get_user_data(itr)[0]
        if i < self._model_data_x.size:
            if column == self.c_x:
                self._model_data_x[i] = value
            elif column == self.c_y:
                self._model_data_y[i] = value
            else:
                raise AttributeError
        else:
            raise IndexError
        self.row_changed((i,), itr)

    def on_get_value(self, rowref, column):
        i = rowref[0]
        if column == self.c_x:
            return self._model_data_x[i]
        elif column == self.c_y:
           return self._model_data_y[i]
        else:
            raise AttributeError

    def on_iter_next(self, rowref):
        i = rowref[0]
        return self.on_get_iter((i+1,))

    def on_iter_children(self, rowref):
        if rowref is not None:
            return None
        elif self._model_data_x and self._model_data_y and self._model_data_x.size > 0:
            return 0
        return None

    def on_iter_has_child(self, rowref):
        if rowref is not None:
            return False
        elif self._model_data_x and self._model_data_y and self._model_data_x.size > 0:
            return True
        return False

    def on_iter_n_children(self, rowref):
        if rowref:
            return 0
        return self._model_data_x.size

    def on_iter_nth_child(self, parent, n):
        if parent:
            return None
        if n < 0 or n >= self._model_data_x.size:
            return None
        return self.on_get_iter((n,))

    def on_iter_parent(self, rowref):
        return None
        
    def append(self, x, y, silent=False):
        self._model_data_x = np.append(self._model_data_x, x)
        self._model_data_y = np.append(self._model_data_y, y)
        path = (self._model_data_x.size-1,)
        self._emit_added(path)
        return path
    
    def insert(self, pos, x, y):
        self._model_data_x = np.insert(self._model_data_x, pos, x)
        self._model_data_y = np.insert(self._model_data_y, pos, y)
        self._emit_added((pos,))
      
    def _emit_added(self, path):
        index = int(path[0])
        self.emit('item-inserted', (self._model_data_x[index], self._model_data_y[index]))
        itr = self.get_iter(path)
        self.row_inserted(path, itr)

    def remove_from_index(self, *indeces):
        if indeces != []:
            indeces = np.sort(indeces)[::-1]
            for index in indeces:
                self.emit('item-removed', (self._model_data_x[index], self._model_data_y[index]))
                self._model_data_x = np.delete(self._model_data_x, index)
                self._model_data_y = np.delete(self._model_data_y, index)
                self.row_deleted((index,))

    def remove(self, itr):
        path = self.get_path(itr)
        self.remove_from_index(path[0])

    def clear(self):
        if self._model_data_x.shape[0] > 0:
            self.remove_from_index(*range(self._model_data_x.shape[0]))              
        
    def set_from_data(self, data_x, data_y):
        self.clear()
        self._model_data_x = np.array(data_x)
        self._model_data_y = np.array(data_y)
        for pos in range(self._model_data_x.shape[0]):
            self._emit_added((pos,))
        
    def update_from_data(self, data_x, data_y):
        if data_x.shape == self._model_data_x.shape and data_y.shape == self._model_data_y.shape:
            self._model_data_x = data_x
            self._model_data_y = data_y
        else:
            self.set_from_data(data_x, data_y)
        
    def get_raw_model_data(self):
        return self._model_data_x, self._model_data_y
        
    def interpolate(self, *x_vals):
        f = interp1d(self._model_data_x, self._model_data_y)
        return zip(x_vals, f(x_vals))
        
    def save_data(self, header, filename):
        f = open(filename, 'w')
        f.write("%s\n" % header)
        np.savetxt(f, zip(self._model_data_x, self._model_data_y), fmt="%.8f")
        f.close()
        
    def load_data(self, data, format="DAT", has_header=True, clear=True):
        if clear:
            self.clear()

        f = None
        close = False
        if type(data) is file:
            f = data
        elif type(data) is str:
            if format=="BIN":
                f = open(data, 'rb')
            else:
                f = open(data, 'r')
            close = True
        else:
            raise TypeError, "Wrong data type supplied for binary format, must be either file or string, but %s was given" % type(data)

        if format=="DAT":
            for line in f:
                if has_header:
                    has_header=False #skip header
                elif line != "":
                    x, y = map(float, line.split())
                    self.append(x,y)
        if format=="BIN":
            if f != None:
                import struct
                #seek data limits
                f.seek(214)
                stepx, minx, maxx = struct.unpack("ddd", f.read(24))
                nx = int((maxx-minx)/stepx)
                #read values                          
                f.seek(250)
                n = 0
                while n < nx:
                    y, = struct.unpack("H", f.read(2))
                    self.append(minx + stepx*n, float(y))
                    n += 1
                    
        #close file
        if close: f.close()
        
    pass #end of class
    
gobject.type_register(XYListStore)
