{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": 2,
   "metadata": {},
   "outputs": [],
   "source": [
    "import numpy as np\n",
    "from scipy.integrate import odeint\n",
    "import matplotlib.pyplot as plt\n",
    "from matplotlib import pyplot\n",
    "import math"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "metadata": {},
   "outputs": [
    {
     "ename": "TypeError",
     "evalue": "Field elements must be 2- or 3-tuples, got '50'",
     "output_type": "error",
     "traceback": [
      "\u001b[1;31m---------------------------------------------------------------------------\u001b[0m",
      "\u001b[1;31mTypeError\u001b[0m                                 Traceback (most recent call last)",
      "\u001b[1;32m<ipython-input-3-efe1f6e74ec7>\u001b[0m in \u001b[0;36m<module>\u001b[1;34m\u001b[0m\n\u001b[0;32m     20\u001b[0m \u001b[0mV_dend\u001b[0m \u001b[1;33m=\u001b[0m \u001b[1;33m[\u001b[0m\u001b[1;33m]\u001b[0m\u001b[1;33m\u001b[0m\u001b[1;33m\u001b[0m\u001b[0m\n\u001b[0;32m     21\u001b[0m \u001b[1;32mfor\u001b[0m \u001b[0mi\u001b[0m \u001b[1;32min\u001b[0m \u001b[0mrange\u001b[0m \u001b[1;33m(\u001b[0m\u001b[1;36m1\u001b[0m\u001b[1;33m,\u001b[0m \u001b[0mlen\u001b[0m\u001b[1;33m(\u001b[0m\u001b[0mtimeoffset\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m:\u001b[0m\u001b[1;33m\u001b[0m\u001b[1;33m\u001b[0m\u001b[0m\n\u001b[1;32m---> 22\u001b[1;33m     \u001b[0mGsyn_raw_delay1\u001b[0m \u001b[1;33m=\u001b[0m \u001b[1;33m[\u001b[0m\u001b[0mnp\u001b[0m\u001b[1;33m.\u001b[0m\u001b[0mzeros\u001b[0m\u001b[1;33m(\u001b[0m\u001b[1;36m1\u001b[0m\u001b[1;33m,\u001b[0m\u001b[0mtimeoffset\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m,\u001b[0m \u001b[0mGsyn_raw\u001b[0m\u001b[1;33m(\u001b[0m\u001b[0marange\u001b[0m\u001b[1;33m(\u001b[0m\u001b[1;36m1\u001b[0m\u001b[1;33m,\u001b[0m \u001b[0mtimeoffset\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m]\u001b[0m\u001b[1;33m;\u001b[0m\u001b[1;33m\u001b[0m\u001b[1;33m\u001b[0m\u001b[0m\n\u001b[0m\u001b[0;32m     23\u001b[0m     \u001b[0mGsyn_raw_delay\u001b[0m \u001b[1;33m=\u001b[0m \u001b[1;33m[\u001b[0m\u001b[0mnp\u001b[0m\u001b[1;33m.\u001b[0m\u001b[0mzeros\u001b[0m\u001b[1;33m(\u001b[0m\u001b[1;36m1\u001b[0m\u001b[1;33m,\u001b[0m\u001b[1;36m100\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m,\u001b[0m \u001b[0mGsyn_raw\u001b[0m\u001b[1;33m(\u001b[0m\u001b[0marange\u001b[0m\u001b[1;33m(\u001b[0m\u001b[1;36m1\u001b[0m\u001b[1;33m,\u001b[0m \u001b[0mend\u001b[0m\u001b[1;33m-\u001b[0m\u001b[1;36m100\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m)\u001b[0m\u001b[1;33m]\u001b[0m\u001b[1;33m;\u001b[0m\u001b[1;33m\u001b[0m\u001b[1;33m\u001b[0m\u001b[0m\n\u001b[0;32m     24\u001b[0m \u001b[1;33m\u001b[0m\u001b[0m\n",
      "\u001b[1;31mTypeError\u001b[0m: Field elements must be 2- or 3-tuples, got '50'"
     ]
    }
   ],
   "source": [
    "n_syn = 1 # number of synapses for a connection\n",
    "dt = 0.0001\n",
    "numTimeSteps = 1000\n",
    "\n",
    "tau1 = 0.2/1000 # (seconds)\n",
    "tau2 = 1.1/1000 # (seconds)\n",
    "factor = 1;\n",
    "timevec = np.arange(dt, 0, dt*numTimeSteps)\n",
    "\n",
    "timeoffset = [50, 100, 150]\n",
    "def Gsyn_raw(timevec): (np.exp(-timevec/tau2) - np.exp(-timevec/tau1))\n",
    "\n",
    "# Set parameters for a \"median\" LHN\n",
    "dendriteSurfAreaCM2 =  1.2537e-05 # (cm^2)\n",
    "axonSurfAreaCM2 = 5.3566e-06 # (cm^2)\n",
    "r = 0.25 * (1/10000)\n",
    "cablelength = 102\n",
    "\n",
    "V_axon = []\n",
    "V_dend = []\n",
    "for i in range (1, len(timeoffset)):\n",
    "    Gsyn_raw_delay1 = [np.zeros(1,timeoffset), Gsyn_raw(arange(1, timeoffset))];\n",
    "    Gsyn_raw_delay = [np.zeros(1,100), Gsyn_raw(arange(1, end-100))];\n",
    "\n",
    "    weight = 55e-12*n_syn # (picosiemens)\n",
    "    Gsyn_dend = (Gsyn_raw_delay1/max(Gsyn_raw_delay1)) * weight\n",
    "    Gsyn_axon = (Gsyn_raw_delay/max(Gsyn_raw_delay)) * weight\n",
    "    # V_all = realNcompartmentModel(Gsyn_dend*4, Gsyn_axon, r, cablelength,dendriteSurfAreaCM2,axonSurfAreaCM2)\n",
    "    V_axon[:, i-1] = 1000*V_all[:, 101]\n",
    "    V_dend[:, i-1] = 1000*V_all[:, 0]\n",
    "    \n",
    "for i in range (1, 3):\n",
    "    plt.subplot(2,3,i)\n",
    "    plt.plot(timevec,V_axon[:, i-1])\n",
    "    plt.ylim(0, 1.6)\n",
    "    plt.xlim(0, 0.05)\n",
    "    plt.subplot(2,3,i+3)\n",
    "    plt.plot(timevec,V_dend[:,i-1])\n",
    "    plt.ylim(0, 1.6)\n",
    "    plt.xlim(0, 0.05)"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "Python 3",
   "language": "python",
   "name": "python3"
  },
  "language_info": {
   "codemirror_mode": {
    "name": "ipython",
    "version": 3
   },
   "file_extension": ".py",
   "mimetype": "text/x-python",
   "name": "python",
   "nbconvert_exporter": "python",
   "pygments_lexer": "ipython3",
   "version": "3.8.5"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 4
}
