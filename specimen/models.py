# coding=UTF-8
# ex:ts=4:sw=4:et=on

# Author: Mathijs Dumon
# This work is licensed under the Creative Commons Attribution-ShareAlike 3.0 Unported License. 
# To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/3.0/ or send
# a letter to Creative Commons, 444 Castro Street, Suite 900, Mountain View, California, 94041, USA.

import os


import gtk
import gobject

from gtkmvc import Observable
from gtkmvc.model import Model, Signal, Observer

import matplotlib
import matplotlib.transforms as transforms
from matplotlib.transforms import offset_copy
from matplotlib.text import Text

import time

import numpy as np
from scipy import stats

from math import tan, asin, sin, cos, pi, sqrt, radians, degrees, exp, log

import settings

from generic.utils import interpolate, print_timing, u
from generic.io import Storable, PyXRDDecoder
from generic.models import XYData, ChildModel, CSVMixin, ObjectListStoreChildMixin, add_cbb_props
from generic.treemodels import ObjectListStore, XYListStore, Point
from generic.peak_detection import multi_peakdetect, peakdetect, smooth

from phases.models import Phase

class Specimen(ChildModel, ObjectListStoreChildMixin, Observable, Storable):

    #MODEL INTEL:
    __have_no_widget__ = ChildModel.__have_no_widget__ + [
        "statistics", "data_markers", "needs_update"
    ]
    __columns__ = [
        ('data_name', str),
        ('data_sample', str),
        ('data_sample_length', float),
        ('data_abs_scale', float),
        ('data_bg_shift', float),
        ('display_calculated', bool),
        ('display_experimental', bool),
        ('display_phases', bool),
        ('data_phases', object),
        ('data_calculated_pattern', object),
        ('data_experimental_pattern', object),
        ('data_exclusion_ranges', object),
        ('data_markers', object),
        ('inherit_calc_color', bool),
        ('calc_color', str),
        ('inherit_exp_color', bool),
        ('exp_color', str),
        ('statistics', object),
    ]
    __observables__ = [ key for key, val in __columns__] + ["needs_update"]
    __storables__ = [ val for val in __observables__ if not val in ("parent", "data_phases", "statistics", "needs_update") ]

    __parent_alias__ = 'project'

    __pctrl__ = None

    #SIGNALS:
    needs_update = None

    #PROPERTIES:
    _data_sample = ""
    _data_name = ""
    _display_calculated = True
    _display_experimental = True
    _display_phases = False
    
    @Model.getter("data_sample", "data_name", "display_calculated", "display_experimental", "display_phases")
    def get_data_name(self, prop_name):
        return getattr(self, "_%s" % prop_name)
    @Model.setter("data_sample", "data_name", "display_calculated", "display_experimental", "display_phases")
    def set_data_name(self, prop_name, value):
        setattr(self, "_%s" % prop_name, value)
        self.liststore_item_changed()
        self.needs_update.emit()
 
    _data_calculated_pattern = None
    def get_data_calculated_pattern_value(self): return self._data_calculated_pattern
    def set_data_calculated_pattern_value(self, value):
        if self._data_calculated_pattern != None: self.relieve_model(self._data_calculated_pattern)
        self._data_calculated_pattern = value
        if self._data_calculated_pattern != None: self.observe_model(self._data_calculated_pattern)
    _data_experimental_pattern = None
    def get_data_experimental_pattern_value(self): return self._data_experimental_pattern
    def set_data_experimental_pattern_value(self, value):
        if self._data_experimental_pattern != None: self.relieve_model(self._data_experimental_pattern)
        self._data_experimental_pattern = value
        if self._data_experimental_pattern != None: self.observe_model(self._data_experimental_pattern)    
    
    _data_exclusion_ranges = None
    def get_data_exclusion_ranges_value(self): return self._data_exclusion_ranges
    def set_data_exclusion_ranges_value(self, value):
        if value != self._data_exclusion_ranges:
            if self._data_exclusion_ranges!=None:
                pass
            self._data_exclusion_ranges = value
            if self._data_exclusion_ranges!=None:
                pass
    
    _data_sample_length = 3.0
    _data_abs_scale = 1.0
    _data_bg_shift = 0.0
    @Model.getter("data_sample_length", "data_abs_scale", "data_bg_shift")
    def get_data_sample_length_value(self, prop_name):
        return getattr(self, "_%s" % prop_name)
    @Model.setter("data_sample_length", "data_abs_scale", "data_bg_shift")
    def set_data_sample_length_value(self, prop_name, value):
        setattr(self, "_%s" % prop_name, value)
        self.needs_update.emit()
    
    statistics = None
    
    _inherit_calc_color = True
    def get_inherit_calc_color_value(self): return self._inherit_calc_color
    def set_inherit_calc_color_value(self, value):
        if value != self._inherit_calc_color:
            self._inherit_calc_color = value
            if self.data_calculated_pattern != None:
                self.data_calculated_pattern.color = self.calc_color
    
    _calc_color = "#666666"
    def get_calc_color_value(self):
        if self.inherit_calc_color and self.parent!=None:
            return self.parent.display_calc_color
        else:
            return self._calc_color
    def set_calc_color_value(self, value):
        if value != self._calc_color:
            self._calc_color = value
            self.data_calculated_pattern.color = self.calc_color
            
    _inherit_exp_color = True
    def get_inherit_exp_color_value(self):
        return self._inherit_exp_color
    def set_inherit_exp_color_value(self, value):
        if value != self._inherit_exp_color:
            self._inherit_exp_color = value
            if self.data_experimental_pattern != None:
                self.data_experimental_pattern.color = self.exp_color
            
    _exp_color = "#000000"
    def get_exp_color_value(self):
        if self.inherit_exp_color and self.parent!=None:
            return self.parent.display_exp_color
        else:
            return self._exp_color
    def set_exp_color_value(self, value):
        if value != self._exp_color:
            self._exp_color = value
            self.data_experimental_pattern.color = value
    
    def set_display_offset(self, new_offset):
        self.data_experimental_pattern.display_offset = new_offset
        self.data_calculated_pattern.display_offset = new_offset
    
    _data_phases = None
    def get_data_phases_value(self): return self._data_phases
        
    _data_markers = None
    def get_data_markers_value(self): return self._data_markers
    
    # ------------------------------------------------------------
    #      Initialisation and other internals
    # ------------------------------------------------------------
    def __init__(self, data_name="", data_sample="", data_sample_length=3.0, data_abs_scale=1.0, data_bg_shift=0.0,
                 display_calculated=True, display_experimental=True, display_phases=False,
                 data_experimental_pattern = None, data_calculated_pattern = None, data_exclusion_ranges = None, data_markers = None,
                 phase_indeces=None, calc_color=None, exp_color=None, 
                 inherit_calc_color=True, inherit_exp_color=True, parent=None):
        ChildModel.__init__(self, parent=parent)
        Observable.__init__(self)
        Storable.__init__(self)
               
        self.needs_update = Signal()
               
        self.data_name = data_name
        self.data_sample = data_sample
        self.data_sample_length = data_sample_length
        self.data_abs_scale  = data_abs_scale
        self.data_bg_shift = data_bg_shift

        self._calc_color = calc_color or self.calc_color
        self._exp_color = exp_color or self.exp_color
        
        self.inherit_calc_color = inherit_calc_color
        self.inherit_exp_color = inherit_exp_color
        
        self.data_calculated_pattern = data_calculated_pattern or XYData("Calculated Profile", color=self.calc_color, parent=self)
        self.data_experimental_pattern = data_experimental_pattern or XYData("Experimental Profile", color=self.exp_color, parent=self)
        self.data_exclusion_ranges = data_exclusion_ranges or XYListStore()
        self.data_exclusion_ranges.connect("item-removed", self.on_exclusion_range_changed)
        self.data_exclusion_ranges.connect("item-inserted", self.on_exclusion_range_changed)
        self.data_exclusion_ranges.connect("row-changed", self.on_exclusion_range_changed)
        
        self._data_markers = data_markers or ObjectListStore(Marker)
        for marker in self._data_markers._model_data:
            self.observe_model(marker)
        self.data_markers.connect("item-removed", self.on_marker_removed)
        self.data_markers.connect("item-inserted", self.on_marker_inserted)
        
        self.display_calculated = display_calculated
        self.display_experimental = display_experimental
        self.display_phases = display_phases
        
        self.statistics = Statistics(data_specimen=self)
        
        #Resolve JSON indeces:
        self._data_phases = dict()
        if phase_indeces is not None and self.parent is not None:
            if hasattr(phase_indeces, "iteritems"):
                for index, quantity in phase_indeces.iteritems():
                    self.add_phase(self.parent.data_phases.get_user_data_from_index(int(index)), float(quantity))
            else:
                for index in phase_indeces:
                    self.add_phase(self.parent.data_phases.get_user_data_from_index(int(index)), 0.0)
    
    def __str__(self):
        return "<Specimen %s(%s)>" % (self.data_name, repr(self))
    
    # ------------------------------------------------------------
    #      Notifications of observable properties
    # ------------------------------------------------------------
    @Observer.observe("needs_update", signal=True)
    def notify_needs_update(self, model, prop_name, info):
        self.needs_update.emit() #propagate signal
        
    def on_exclusion_range_changed(self, model, item, *args):
        self.needs_update.emit()
        
    def on_marker_removed(self, model, item):
        self.relieve_model(item)
        item.parent = None
        self.needs_update.emit()
        
    def on_marker_inserted(self, model, item):
        self.observe_model(item)
        item.parent = self
        if self.__pctrl__:
            self.__pctrl__.register(item, "on_update_plot", last=True)
        self.needs_update.emit()
                  
    # ------------------------------------------------------------
    #      Input/Output stuff
    # ------------------------------------------------------------   
    def json_properties(self):
        retval = Storable.json_properties(self)
        retval["phase_indeces"] = { self.parent.data_phases.index(phase): quantity for phase, quantity in self.data_phases.iteritems() if phase }
        retval["calc_color"] = self._calc_color
        retval["exp_color"] = self._exp_color
        return retval
    
    @staticmethod          
    def from_json(**kwargs):
        decoder = PyXRDDecoder()
        if "data_calculated_pattern" in kwargs:
            kwargs["data_calculated_pattern"] = decoder.__pyxrd_decode__(kwargs["data_calculated_pattern"])
        if "data_experimental_pattern" in kwargs:
            kwargs["data_experimental_pattern"] = decoder.__pyxrd_decode__(kwargs["data_experimental_pattern"])
        if "data_exclusion_ranges" in kwargs:
            kwargs["data_exclusion_ranges"] = decoder.__pyxrd_decode__(kwargs["data_exclusion_ranges"])
        if "data_markers" in kwargs:
            kwargs["data_markers"] = decoder.__pyxrd_decode__(kwargs["data_markers"])
        specimen = Specimen(**kwargs)
        for marker in specimen.data_markers._model_data:
            marker.parent = specimen
        specimen.data_calculated_pattern.parent = specimen
        specimen.data_experimental_pattern.parent = specimen
        return specimen
              
    @staticmethod
    def from_experimental_data(parent, data, format="DAT", filename=""):
        specimen = Specimen(parent=parent)
        
        if format=="DAT":        
            header, data = data.split("\n", 1)
            
            specimen.data_experimental_pattern.load_data(data, format=format, has_header=False)
            specimen.data_name = u(os.path.basename(filename))
            specimen.data_sample = u(header)
            
        elif format=="BIN":
            import struct
            
            f = open(data, 'rb')
            f.seek(146)
            specimen.data_sample = u(str(f.read(16)).replace("\0", ""))
            specimen.data_name = u(os.path.basename(data))
            specimen.data_experimental_pattern.load_data(data=f, format=format)
            f.close()
        
        return specimen
        
    # ------------------------------------------------------------
    #      Methods & Functions
    # ------------------------------------------------------------ 
    def add_phase(self, phase, quantity=0.0):
        if not phase in self._data_phases:
            self.observe_model(phase)
            self._data_phases.update({phase: quantity})

    def del_phase(self, phase):
        if phase in self._data_phases:
            self.relieve_model(phase)
            del self._data_phases[phase]
        
    def on_update_plot(self, figure, axes, pctrl):       
        if self.display_experimental:
            self.data_experimental_pattern.on_update_plot(figure, axes, pctrl)
        if self.display_calculated:
            self.data_calculated_pattern.on_update_plot(figure, axes, pctrl)
        pctrl.update_lim()

    _hatches = None        
    def on_update_hatches(self, figure, axes, pctrl):
        if self._hatches:
            for leftborder, hatch, rightborder in self._hatches:
                try:
                    hatch.remove()
                    leftborder.remove()
                    rightborder.remove()
                except: pass
        self._hatches = list()
        
        xmin, xmax = axes.get_xbound()
        ymin, ymax = axes.get_ybound()
        y0 = (self.data_experimental_pattern.display_offset - ymin) / (ymax - ymin)
        y1 = y0 + (1.0 - ymin) / (ymax - ymin)
        
        for i, (x0, x1) in enumerate(zip(*self.data_exclusion_ranges.get_raw_model_data())):        
            leftborder = axes.axvline(x0, y0, y1, c="#000000", alpha=0.5)
            hatch = axes.axvspan(x0, x1, y0, y1, fill=True, hatch="/", facecolor='none', edgecolor="#000000", linewidth=0, alpha=0.5)
            rightborder = axes.axvline(x1, y0, y1, c="#000000", alpha=0.5)
            
            self._hatches.append((leftborder, hatch, rightborder))        
        
    @property
    def max_intensity(self):
        return max(np.max(self.data_experimental_pattern.max_intensity), np.max(self.data_calculated_pattern.max_intensity))

    def get_phase_intensities(self, phases, lpf_callback, steps=2500):
        if phases!=None:
        
            l = self.parent.data_goniometer.data_lambda
            L_Rta =  self.data_sample_length / (self.parent.data_goniometer.data_radius * tan(radians(self.parent.data_goniometer.data_divergence)))
            min_theta = radians(self.parent.data_goniometer.data_min_2theta*0.5)
            max_theta = radians(self.parent.data_goniometer.data_max_2theta*0.5)
            delta_theta = float(max_theta - min_theta) / float(steps-1)
            theta_range = None
            torad = pi / 180.0
            if self.data_experimental_pattern.xy_data._model_data_x.size <= 1:
                theta_range = min_theta + delta_theta * np.array(range(0,steps-1), dtype=float)
            else:
                theta_range =  self.data_experimental_pattern.xy_data._model_data_x * torad * 0.5
            stl_range = 2 * np.sin(theta_range) / l
            
            correction_range = np.minimum(np.sin(theta_range) * L_Rta, 1)

            return theta_range, np.array([phase.get_diffracted_intensity(theta_range, stl_range, lpf_callback, 1.0, correction_range) if phase else np.zeros(shape=theta_range.shape) for phase in phases], dtype=np.float_)


    #@print_timing
    def calculate_pattern(self, lpf_callback, steps=2500):
        if len(self._data_phases) == 0:
            self.data_calculated_pattern.xy_data.clear()
            return None
        else:     
                    
            theta_range, intensities = self.get_phase_intensities(self._data_phases.keys(), lpf_callback, steps=steps)
            intensity_range = np.zeros(len(intensities[0]))
            
            fractions = np.array(self._data_phases.values())[:,np.newaxis]
            intensity_range = np.sum(intensities*fractions, axis=0) * self.data_abs_scale + self.data_bg_shift
            theta_range = theta_range * 360.0 / pi 
            
            self.data_calculated_pattern.update_from_data(theta_range, intensity_range)

            return (theta_range, intensity_range)
        
    def auto_add_peaks(self, tmodel):
    
        threshold = tmodel.sel_threshold
        data_base = 1 if (tmodel.pattern == "exp") else 2
        data_x, data_y = tmodel.get_xy()
        maxtab, mintab = peakdetect(data_y, data_x, 5, threshold)
        
        mpositions = []
        for marker in self.data_markers._model_data:
            mpositions.append(marker.data_position)

        i = 1
        for x, y in maxtab:
            if not x in mpositions:
                nm = 0
                if x != 0:
                    nm = self.parent.data_goniometer.data_lambda / (2.0*sin(radians(x/2.0)))
                new_marker = Marker("%%.%df" % (3 + min(int(log(nm, 10)), 0)) % nm, parent=self, data_position=x, data_base=data_base)
                self.data_markers.append(new_marker)
            i += 1
            
    def get_exclusion_selector(self, x):
        if x != None:
            selector = np.ones(x.shape, dtype=bool)
            for x0,x1 in zip(*np.sort(np.array(self.data_exclusion_ranges.get_raw_model_data()), axis=0)):
                new_selector = ((x < x0) | (x > x1))
                selector = selector & new_selector
            return selector
        return None
        
    def get_exclusion_xy(self):
        ex, ey = self.data_experimental_pattern.xy_data.get_raw_model_data()
        cx, cy = self.data_calculated_pattern.xy_data.get_raw_model_data()
        selector = self.get_exclusion_selector(ex)
        return ex[selector], ey[selector], cx[selector], cy[selector]
    
    pass #end of class
    
class ThresholdSelector(ChildModel, Observable):
    
    #MODEL INTEL:
    __have_no_widget__ = ChildModel.__have_no_widget__ + ["threshold_plot_data"]
    __observables__ = [ "pattern", "max_threshold", "steps", "sel_threshold", "threshold_plot_data", "sel_num_peaks" ]
    __parent_alias__ = 'specimen'
    
    #PROPERTIES:
    _pattern = "exp"
    _patterns = { "exp": "Experimental Pattern", "calc": "Calculated Pattern" } #FIXME!
    """@Model.getter("pattern")
    def get_pattern(self, prop_name):
        return self._pattern
    @Model.setter("pattern")
    def set_pattern(self, prop_name, value):
        if value in self._patterns: 
            self._pattern = value      
        else:
            raise ValueError, "'%s' is not a valid value for pattern!" % value
            self.update_threshold_plot_data()"""
        
    add_cbb_props(("pattern", lambda i: i, lambda self,p,v: self.update_threshold_plot_data()))
    
    
    _max_threshold = 0.32
    def get_max_threshold_value(self): return self._max_threshold
    def set_max_threshold_value(self, value):
        value = min(max(0, float(value)), 1) #set some bounds
        if value != self._max_threshold:
            self._max_threshold = value
            self.update_threshold_plot_data()
            
    _steps = 20
    def get_steps_value(self): return self._steps
    def set_steps_value(self, value):
        value = min(max(3, value), 50) #set some bounds
        if value != self._steps:
            self._steps = value
            self.update_threshold_plot_data()
            
    _sel_threshold = 0.1
    sel_num_peaks = 0
    def get_sel_threshold_value(self): return self._sel_threshold
    def set_sel_threshold_value(self, value):
        if value != self._sel_threshold:
            self._sel_threshold = value
            deltas, numpeaks = self.threshold_plot_data
            self.sel_num_peaks = int(interpolate(zip(deltas, numpeaks), self._sel_threshold))
    
    threshold_plot_data = None
   
    # ------------------------------------------------------------
    #      Initialisation and other internals
    # ------------------------------------------------------------ 
    def __init__(self, max_threshold=None, steps=None, sel_threshold=None, parent=None):
        ChildModel.__init__(self, parent=parent)
        Observable.__init__(self)
        
        self.max_threshold = max_threshold or self.max_threshold
        self.steps = steps or self.steps
        self.sel_threshold = sel_threshold or self.sel_threshold
        
        self.update_threshold_plot_data()
    
    # ------------------------------------------------------------
    #      Methods & Functions
    # ------------------------------------------------------------
    def get_xy(self):
        if self._pattern == "exp":
            data_y = self.parent.data_experimental_pattern.xy_data._model_data_y
            data_y = data_y / np.max(data_y)
            return self.parent.data_experimental_pattern.xy_data._model_data_x, data_y
        elif self._pattern == "calc":
            data_y = self.parent.data_calculated_pattern.xy_data._model_data_y
            data_y = data_y / np.max(data_y)
            return self.parent.data_calculated_pattern.xy_data._model_data_x, data_y
    
    def update_threshold_plot_data(self):
        if self.parent != None:
            data_x, data_y = self.get_xy()
            length = data_x.size
            
            if length > 2:
                resolution = length / (data_x[-1] - data_x[0])
                delta_angle = 0.05
                window = int(delta_angle * resolution)
                window += (window % 2)*2
                
                steps = max(self.steps, 2) - 1
                factor = self.max_threshold / steps

                deltas = [i*factor for i in range(0, self.steps)]
                
                numpeaks = []
                maxtabs, mintabs = multi_peakdetect(data_y, data_x, 5, deltas)
                for maxtab, mintab in zip(maxtabs, mintabs):
                    numpeak = len(maxtab)
                    numpeaks.append(numpeak)
                numpeaks = map(float, numpeaks)
                
                #update plot:
                self.threshold_plot_data = (deltas, numpeaks)
                
                #update auto selected threshold:
                ln = 4
                max_ln = len(deltas)
                stop = False
                while not stop:
                    x = deltas[0:ln]
                    y = numpeaks[0:ln]
                    slope, intercept, R, p_value, std_err = stats.linregress(x,y)
                    ln += 1
                    if abs(R) < 0.95 or ln >= max_ln:
                        stop = True
                    peak_x = -intercept / slope                

                self.sel_threshold = peak_x
    pass #end of class
            
class Marker(ChildModel, Observable, Storable, ObjectListStoreChildMixin, CSVMixin):
    
    #MODEL INTEL:
    __have_no_widget__ = ChildModel.__have_no_widget__ + ["needs_update"]
    __columns__ = [
        ('data_label', str),
        ('data_visible', bool),
        ('data_position', float),
        ('data_x_offset', float),
        ('data_y_offset', float),
        ('data_color', str),
        ('data_base', bool),
        ('data_angle', float),
        ('inherit_angle', bool),
        ('data_style', str)
    ]
    __storables__ = [ key for key, val in __columns__]
    __observables__ = __storables__ + ["needs_update"]
    __csv_storables__ = zip(__storables__, __storables__)
    __parent_alias__ = 'specimen'

    #SIGNALS:
    needs_update = None

    #PROPERTIES:
    _data_label = ""
    def get_data_label_value(self): return self._data_label
    def set_data_label_value(self, value):
        self._data_label = value
        self.liststore_item_changed()
        self.needs_update.emit()
    
    _data_visible = True
    _data_position = 0.0
    _data_x_offset = 0.0
    _data_y_offset = 0.05
    _data_color = "#000000"
    @Model.getter("data_visible", "data_position", "data_x_offset", "data_y_offset", "data_color")
    def get_data_plot_value(self, prop_name):
        return getattr(self, "_%s" % prop_name)
    @Model.setter("data_visible", "data_position", "data_x_offset", "data_y_offset", "data_color")
    def set_data_plot_value(self, prop_name, value):
        setattr(self, "_%s" % prop_name, value)
        self.needs_update.emit()

    _inherit_angle = True
    def get_inherit_angle_value(self): return self._inherit_angle
    def set_inherit_angle_value(self, value):
        self._inherit_angle = value
        if self._text!=None:
            self._text.set_rotation(90-self.data_angle)
        self.needs_update.emit()
            
    _data_angle = 0.0
    def get_data_angle_value(self):
        if self.inherit_angle and self.parent!=None and self.parent.parent!=None:
            return self.parent.parent.display_marker_angle
        else:
            return self._data_angle
    def set_data_angle_value(self, value):
        self._data_angle = value
        if self._text!=None:
            self._text.set_rotation(90-self.data_angle)
        self.needs_update.emit()

    _data_base = 1
    _data_bases = { 0: "X-axis", 1: "Experimental profile" }
    if not settings.VIEW_MODE:
        _data_bases.update({ 2: "Calculated profile", 3: "Lowest of both", 4: "Highest of both" })

    _data_style = "none"
    _data_styles = { "none": "Display at base", "solid": "Solid", "dashed": "Dash", "dotted": "Dotted", "dashdot": "Dash-Dotted", "offset": "Display at Y-offset" }
        
    def cbb_callback(self, prop_name, value):
        self.needs_update.emit()
    add_cbb_props(("data_base", int, cbb_callback), ("data_style", lambda i: i, cbb_callback))
    
    _vline = None
    _text = None
    
    # ------------------------------------------------------------
    #      Initialisation and other internals
    # ------------------------------------------------------------
    def __init__(self, data_label="", data_visible=True, data_position=0.0, data_x_offset=0.0, data_y_offset=0.05, 
                 data_color="#000000", data_base=1, data_angle=0.0, inherit_angle=True, data_style="none", parent=None):
        ChildModel.__init__(self, parent=parent)
        Observable.__init__(self)
        Storable.__init__(self)
        
        self.needs_update = Signal()
        
        self.data_label = data_label
        self.data_visible = data_visible
        self.data_position = float(data_position)
        self.data_x_offset = float(data_x_offset)
        self.data_y_offset = float(data_y_offset)
        self.data_color = data_color
        self.data_base = int(data_base)
        self.inherit_angle = inherit_angle
        self.data_angle = float(data_angle)
        self.data_style = data_style   
        
    # ------------------------------------------------------------
    #      Methods & Functions
    # ------------------------------------------------------------
    def get_ymin(self):
        return min(self.get_y(self.parent.data_experimental_pattern.line), 
                   self.get_y(self.parent.data_calculated_pattern.line))
    def get_ymax(self):
        return max(self.get_y(self.parent.data_experimental_pattern.line), 
                   self.get_y(self.parent.data_calculated_pattern.line))   
    def get_y(self, line):
        x_data, y_data = line.get_data()
        if len(x_data) > 0:
            return np.interp(self.data_position, x_data, y_data)
        else:
            return 0
    
    def update_text(self, figure, axes): #FIXME this should be part of a view, rather then a model...
        if self.data_style != "offset":
            kws = dict(text=self.data_label,
                       x=float(self.data_position)+float(self.data_x_offset), y=settings.PLOT_TOP,
                       clip_on=False,
                       transform=transforms.blended_transform_factory(axes.transData, figure.transFigure),
                       horizontalalignment="left", verticalalignment="center",
                       rotation=(90-self.data_angle), rotation_mode="anchor",
                       color=self.data_color,
                       weight="heavy")
           
            if self.data_style == "none":
                y = 0
                if int(self.data_base) == 1:
                    y = self.get_y(self.parent.data_experimental_pattern.line)
                elif self.data_base == 2:
                    y = self.get_y(self.parent.data_calculated_pattern.line)
                elif self.data_base == 3:
                    y = self.get_ymin()
                elif self.data_base == 4:
                    y = self.get_ymax()
                    
                ymin, ymax = axes.get_ybound()
                trans = transforms.blended_transform_factory(axes.transData, axes.transAxes)
                y = (y - ymin) / (ymax - ymin) + self.data_y_offset
                
                kws.update(dict(
                    y=y,
                    transform=trans,
                ))
            
            if self._text == None:
                self._text = Text(**kws)
            else:
                for key in kws:
                    getattr(self._text, "set_%s"%key)(kws[key])
            if not self._text in axes.get_children():
                axes.add_artist(self._text)     
    
    def update_vline(self, figure, axes): #FIXME this should be part of a view, rather then a model...
        y = 0
        if int(self.data_base) == 1:
            y = self.get_y(self.parent.data_experimental_pattern.line)
        elif self.data_base == 2:
            y = self.get_y(self.parent.data_calculated_pattern.line)
        elif self.data_base == 3:   
            y = self.get_ymin()
        elif self.data_base == 4:
            y = self.get_ymax()
            
        xmin, xmax = axes.get_xbound()
        ymin, ymax = axes.get_ybound()

        # We need to strip away the units for comparison with
        # non-unitized bounds
        #scalex = (self.data_position<xmin) or (self.data_position>xmax)
        trans = transforms.blended_transform_factory(axes.transData, axes.transAxes)
        y = (y - ymin) / (ymax - ymin)
            
        data_style = self.data_style
        data = [y,1]
        if data_style == "offset":
            data_style = "solid"
            y = (self.parent.data_experimental_pattern.display_offset - ymin) / (ymax - ymin)
            offset = y + (self.data_y_offset - ymin) / (ymax - ymin)
            
            data = [y,offset]
            
        if self._vline == None:
            self._vline = matplotlib.lines.Line2D([self.data_position,self.data_position], data , transform=trans, color=self.data_color, ls=data_style)
            self._vline.y_isdata = False
        else:
            self._vline.set_xdata(np.array([self.data_position,self.data_position]))
            self._vline.set_ydata(np.array(data))
            self._vline.set_transform(trans)
            self._vline.set_color(self.data_color)
            self._vline.set_linestyle(data_style)
            
        if not self._vline in axes.get_lines():
            axes.add_line(self._vline)
            #axes.autoscale_view(scalex=scalex, scaley=False)
    
    def on_update_plot(self, figure, axes, pctrl): #FIXME this should be part of a view, rather then a model...
        if self.parent!=None:
            self.update_vline(figure, axes)
            self.update_text(figure, axes)
               
    def get_nm_position(self):
        if self.parent != None:
            return self.parent.parent.data_goniometer.get_nm_from_2t(self.data_position)
        else:
            return 0.0
        
    def set_nm_position(self, position):
        if self.parent != None:
            self.data_position = self.parent.parent.data_goniometer.get_2t_from_nm(position)
        #else:
        #    self.data_position = 0.0
        
    pass #end of class
        
class Statistics(Model, Observable):

    #MODEL INTEL:
    __have_no_widget__ = ["data_specimen", "data_residual_pattern"]
    __observables__ = [ 
        "data_specimen", 
        "data_points", 
        "data_residual_pattern",
         "data_chi2", "data_Rp", "data_R2" 
    ]
    
    #PROPERTIES:
    _data_specimen = None
    def get_data_specimen_value(self): return self._data_specimen
    def set_data_specimen_value(self, value):
        if value != self._data_specimen:
            self._data_specimen = value
            self.update_statistics()
       
    def get_data_points_value(self):
        try:
            e_ex, e_ey, e_cx, e_cy = self.data_specimen.get_exclusion_xy()
            return e_ex.size
        except: pass
        return 0
    
    data_chi2 = None      
    data_R2 = None
    data_Rp = None
    data_residual_pattern = None
  
    # ------------------------------------------------------------
    #      Initialisation and other internals
    # ------------------------------------------------------------
    def __init__(self, data_specimen=None):
        Model.__init__(self)
        Observable.__init__(self)
        
        self.data_specimen = data_specimen or self.data_specimen        
        self.update_statistics()
        
    # ------------------------------------------------------------
    #      Methods & Functions
    # ------------------------------------------------------------ 
    def _get_experimental(self):
        if self._data_specimen != None:
            return self._data_specimen.data_experimental_pattern.xy_data.get_raw_model_data()
        else:
            return None, None
    def _get_calculated(self):
        if self._data_specimen != None:
            return self._data_specimen.data_calculated_pattern.xy_data.get_raw_model_data()
        else:
            return None, None 
        
    """def on_data_update(self, model, name, info):
        self.update_statistics()"""
      
    def update_statistics(self):
        self.data_chi2 = 0        
        self.data_Rp = 0
        self.data_R2 = 0
        if self.data_residual_pattern == None:
            self.data_residual_pattern = XYData(data_name="Residual Data", color="#000000")
        
        self.data_residual_pattern.clear()
        
        exp_x, exp_y = self._get_experimental()
        cal_x, cal_y = self._get_calculated()

        #if exp_x.shape != cal_x.shape:
        #    return

        if cal_y != None and exp_y != None and cal_y.size > 0 and exp_y.size > 0:
            residual_pattern = XYListStore()
            residual_pattern.set_from_data(exp_x, exp_y - cal_y)
            self.data_residual_pattern.xy_data = residual_pattern
            self.data_residual_pattern.update_data()

            e_ex, e_ey, e_cx, e_cy = self.data_specimen.get_exclusion_xy()

            self.data_chi2 = stats.chisquare(e_ey, e_cy)[0]
            self.data_Rp, self.data_R2 = self._calc_RpR2(e_ey, e_cy)
           
    @staticmethod
    def _calc_RpR2(o, e):
        avg = sum(o)/o.size
        sserr = np.sum((o - e)**2)
        sstot = np.sum((o - avg)**2)
        return Statistics._calc_Rp(o, e), 1 - (sserr / sstot)
        
    @staticmethod
    def _calc_Rp(o, e):
        return np.sum(np.abs(o - e)) / np.sum(np.abs(o)) * 100
        
    pass #end of class
