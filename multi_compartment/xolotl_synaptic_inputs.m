x = xolotl
x.add('compartment', 'HH','A', 0.01)
x.HH.add('liu/NaV', 'gbar', 1000)
x.HH.add('liu/Kd', 'gbar', 300)
x.HH.add('Leak', 'gbar', 1)
x.HH.add('prinz/ACurrent', 'gbar', 104)
x.HH.add('liu/IntegralController')
x.plot
x.manipulate
