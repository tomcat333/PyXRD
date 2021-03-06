#!/usr/bin/python

# coding=UTF-8
# ex:ts=4:sw=4:et=on

# Copyright (c) 2013, Mathijs Dumon
# All rights reserved.
# Complete license can be found in the LICENSE file.

import unittest

import numpy as np

from pyxrd.calculations.data_objects import AtomData, AtomTypeData
from pyxrd.calculations.atoms import get_atomic_scattering_factor, get_structure_factor

__all__ = [
    'TestAtomCalcs',
]

class TestAtomCalcs(unittest.TestCase):

    def setUp(self):
        self.atom_type_data = AtomTypeData( # this is the data for a H atom
            par_a = np.asanyarray([0.413048,0.294953,0.187491,0.080701,0.023736]),
            par_b = np.asanyarray([15.569946,32.398468,5.711404,61.889874,1.334118]),
            par_c = 0.000049,
            debye = 0
        )
        self.atom_data = AtomData(
            atom_type = self.atom_type_data,
            pn = 1,
            default_z = 0,
            z = 0
        )       

    def tearDown(self):
        del self.atom_data
        del self.atom_type_data

    def test_not_none(self):
        self.assertIsNotNone(self.atom_type_data)
        self.assertIsNotNone(self.atom_data)

    def test_scattering_factor(self):
        result = get_atomic_scattering_factor(
            np.asanyarray([2.2551711385, 2.478038901, 2.7001518288, 2.9214422642, 3.1418428, 3.3612863, 3.5797059197, 3.7970351263]),
            self.atom_type_data
        )
        self.assertIsNotNone(result)

    def test_structure_factor(self):
        result = get_structure_factor(
            np.asanyarray([2.2551711385, 2.478038901, 2.7001518288, 2.9214422642, 3.1418428, 3.3612863, 3.5797059197, 3.7970351263]),
            self.atom_data
        )
        self.assertIsNotNone(result)

    pass # end of class
