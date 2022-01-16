#!/usr/bin/env python
# coding: utf-8

# In[ ]:


from neuron import h, gui
from neuron.units import ms, mV
h.load_file('stdrun.hoc')
get_ipython().run_line_magic('matplotlib', 'notebook')
import matplotlib.pyplot as plt


# In[ ]:


class BallAndStick:
    def __init__(self, gid):
        self._gid = gid
        self._setup_morphology()
        self._setup_biophysics()
    def _setup_morphology(self):
        self.soma = h.Section(name='soma', cell=self)
        self.dend = h.Section(name='dend', cell=self)
        self.dend.connect(self.soma)
        self.all = self.soma.wholetree()
        self.soma.L = 100
        self.soma.diam = 500
        self.dend.L = 200
        self.dend.diam = 1
    def _setup_biophysics(self):
        for sec in self.all:
            sec.Ra = 212.47    # Axial resistance (ohm-cm)
            sec.cm = 0.77      # Membrane capacitance (uF/cm^2)
        # insert Hodgkin-Huxley channels in cell
        self.soma.insert('hh')                                                               
        for seg in self.soma:                                                     
            seg.hh.gnabar = 0.4  # Sodium conductance (uS/cm^2)                  
            seg.hh.gkbar = 0.37  # Potassium conductance (uS/cm^2)               
            seg.hh.gl = 0.0328   # Leak conductance in (uS/cm^2)                    
            seg.hh.el = -60         # Reversal potential (mV)       
        # Insert passive current in the dendrite                       
        self.dend.insert('pas')                                        
        for seg in self.dend:                                          
            seg.pas.g = 5.8e-11  # Passive conductance (uS/cm^2)      
            seg.pas.e = -55      # Leak reversal potential (mV)            
    def __repr__(self):
        return 'BallAndStick[{}]'.format(self._gid)
    
my_cell = BallAndStick(0)

h.topology()


# In[ ]:


# define and position current clamp object
stim = h.IClamp(my_cell.dend(1)) 

# check segment current clamp is inserted into
stim.get_segment() 

# set parameters:
stim.delay = 5
stim.dur = 1
stim.amp = 0.1

# record membrane potential:
soma_v = h.Vector().record(my_cell.soma(0.5)._ref_v)
t = h.Vector().record(h._ref_t)


# In[ ]:


h.load_file('stdrun.hoc')
h.finitialize(-55 * mV)
h.continuerun(500 * ms)


# In[ ]:


from bokeh.io import output_notebook
import bokeh.plotting as plt
output_notebook()


# In[ ]:


f = plt.figure(x_axis_label='Time (ms)', y_axis_label='Membrane Potential (mV)')
f.line(t, soma_v, line_width=2)
plt.show(f)

