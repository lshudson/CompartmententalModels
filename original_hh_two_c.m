function x = hhTwoCompartmentModel;

resistivity = 1e-3; % MOhm mm; 

x.add('compartment', 'CellBody','A', 0.01)
x.add('compartment', 'Axon','A', 0.01)

x.CellBody.add('liu/NaV', 'gbar', 1000)
x.CellBody.add('liu/Kd', 'gbar', 300)
x.CellBody.add('Leak', 'gbar', 1)
x.CellBody.add('prinz/ACurrent', 'gbar', 104)

x.Axon.add('liu/NaV', 'gbar', 1000)
x.Axon.add('liu/Kd', 'gbar', 300)
x.Axon.add('Leak', 'gbar', 1)
x.Axon.add('prinz/ACurrent', 'gbar', 104)

x.CellBody.tree_idx = 0; % mark this as the cell body
x.connect('CellBody','Axon','Axial', 'resistivity',resistivity);
x.connect('Axon','CellBody','Axial', 'resistivity',resistivity);

% x.CellBody.I_ext = .2
% x.Axon.I_ext = .2

x.plot
x.manipulate
