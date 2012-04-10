#!/usr/bin/python

# coding=UTF-8
# ex:ts=4:sw=4:et=on

# Author: Mathijs Dumon
# This work is licensed under the Creative Commons Attribution-ShareAlike 3.0 Unported License. 
# To view a copy of this license, visit http://creativecommons.org/licenses/by-sa/3.0/ or send
# a letter to Creative Commons, 444 Castro Street, Suite 900, Mountain View, California, 94041, USA.

import gtk
import matplotlib

font = {'weight' : 'heavy', 'size': 14}
matplotlib.rc('font', **font)
mathtext = {'default': 'regular'}
matplotlib.rc('mathtext', **mathtext)

from application.models import AppModel
from application.views import AppView
from application.controllers import AppController


import sys
import settings

class MyWriter: 
    def __init__(self, stdout, filename): 
        self.stdout = stdout 
        self.logfile = file(filename, 'w') 
    def write(self, text): 
        self.stdout.write(text) 
        self.logfile.write(text) 
    def close(self): 
        self.stdout.close() 
        self.logfile.close()
writer = MyWriter(sys.stdout, settings.LOG_FILENAME) 

saveout = sys.stdout
saveerr = sys.stderr
sys.stdout = writer 
sys.stderr = writer

import logging
logger = logging.getLogger("gtkmvc")
hdlr = logging.StreamHandler(writer)
logger.addHandler(hdlr)
#if settings.DEBUG:
#    logger.setLevel(logging.DEBUG)

if __name__ == "__main__":

    m = AppModel()
    v = AppView()
    c = AppController(m, v)
    gtk.main()
    
# restore stdout
sys.stdout = saveout
sys.stderr = saveerr
