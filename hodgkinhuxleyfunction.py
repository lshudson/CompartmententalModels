#!/usr/bin/env python
# coding: utf-8

# In[1]:


def hodgkinhuxley(state,t):
    v = state[0]
    n = state[1]
    m = state[2]
    h = state[3]
    
    # Nernst reversal potentials
    e_Na = 72
    e_K = -12
    e_L = -60
    
    # Maximum sodium channel conductance
    gbar_Na = 120
    g_Na = gbar_Na * h * m**3
    
    # Maximum potassium channel conductance
    gbar_K = 36
    g_K = gbar_K * (n**4)
    
    # Leakage channel conductance
    gbar_L = 0.0328
    
    # Membrane capacitance
    C_m = 0.77
    
    # Channel currents
    I_Na = g_Na * (v-e_Na)
    I_K = g_K * (v-e_K)
    I_L = gbar_L
    I_app = 10
    
    # ina = I_Na(v,m,h)
    # ik = I_K(v,n)
    # il = I_L(v)
    
    # Channel Gating Kinetics for Potassium (K) channel n
    # n is the activation variable for the Potassium (K) Channel
    # Potassium channel does not inactivate, so there is no inactivation variable
    a_n = 0.01*(10-v)/(np.exp((10-v)/10)-1)
    b_n = 0.125*np.exp(-v/80)
    
    # Channel Gating Kinetics for Sodium (Na) Channel m
    # m is the activation variable for the Sodium (Na) Channel
    a_m = 0.1*(25-v)/(np.exp((25-v)/10)-1)
    b_m = 4*np.exp(-v/18)
    
    # Channel Gating Kinetics for Sodium (Na) Channel h
    # h is the inactivation variable for the Sodium (Na) Channel
    b_h = 1/(np.exp((30-v)/10)+1)    #should be +1?
    a_h = 0.07*np.exp(-v/20)
    
    # Differential Equations
    dvdt = (-I_Na - I_K - I_L + I_app)/C_m
    dndt = a_n*(1-n) - b_n*n
    dmdt = a_m*(1-m) - b_m*m
    dhdt = a_h*(1-h) - b_h*h
    
    return dvdt, dndt, dmdt, dhdt

