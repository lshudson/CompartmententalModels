
### NOTE: file should be run from directory:
### C:\\Users\\Tony\\Documents\\TonyThings\\Research\\Jeanne Lab\\code\\EManalysis\\LH dendritic computation\\mc_model\\population_model\\

import sys
import os
# path below should be where `run_local5` is located, unnecessary if `run_local5` is in the same folder as `pop_mc_model`
sys.path.append("C:\\Users\\Tony\\Documents\\TonyThings\\Research\\Jeanne Lab\\code\\EManalysis\\LH dendritic computation\\mc_model")
from run_local5 import *
from datetime import datetime
import seaborn as sns
from matplotlib import cm
from scipy import stats
import matplotlib
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

# import pop_sc_model to generate EPSP peaks given SC param sets
from pop_sc_model import *

# set up API connection to neuprint hemibrain server
from neuprint import Client
from neuprint import fetch_simple_connections, fetch_synapse_connections, fetch_neurons
from neuprint import SynapseCriteria as SC, NeuronCriteria as NC
try:
	c = Client('neuprint.janelia.org', dataset = 'hemibrain:v1.1',token='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6ImxpdXRvbnk2NkBnbWFpbC5jb20iLCJsZXZlbCI6Im5vYXV0aCIsImltYWdlLXVybCI6Imh0dHBzOi8vbGgzLmdvb2dsZXVzZXJjb250ZW50LmNvbS9hLS9BT2gxNEdoNWZBS29QYzQxdzR0S0V1cmFXeEplbm41ZHBoajFrU2tBVS1mVD9zej01MD9zej01MCIsImV4cCI6MTc2NTAwNTUwOH0.itiAhvsvMYHVECWFVMuolEJo64pwSQgt9OLN2npyrys')
except:
	print('neuprint client connection failed, likely no WiFi')

h.load_file('import3d.hoc')

class Cell():
	def __init__(self, fname, gid):
		'''
		fname - string: file path to SWC
		'''
		self._gid = gid
		self.fname = fname
		self.load_morphology(fname)
		self.sec_name = ""
		self.find_sec_name()
		#self.discretize_sections()
		#self.add_biophysics()
		self.tree = pd.DataFrame()
		self.body_id = 0

	def __str__(self):
		return 'Cell[{}]'.format(self._gid)

	def load_morphology(self, nom):
		#print(nom)
		cell = h.Import3d_SWC_read()
		cell.input(nom)
		i3d = h.Import3d_GUI(cell, 0)
		i3d.instantiate(self)

	def find_sec_name(self):
		secnames = []
		for sec in h.allsec():
			name = re.split('\.|\[', sec.name())[2]
			if name not in secnames:
				secnames.append(name)
		if 'axon' in secnames:
			self.sec_name = 'axon'
		elif 'soma' in secnames:
			self.sec_name = 'soma'

	def discretize_sections(self):
		''' 
			adds at least as many spatial compartments as d_lambda rule
			maximizing segment density also allows better synapse localization 
		'''
		for sec in h.allsec():
			sec.nseg = sec.n3d()

	def add_biophysics(self, ra, cm, gpas, epas):
		# insert passive density mechanism
		mt = h.MechanismType(0)
		mt.select("pas")
		for section in h.allsec():
			# insert distributed mechanism into section
			mt.make(sec=section)	

		change_R_a(ra)
		change_c_m(cm)
		change_g_pas(gpas)
		change_e_pas(epas)

	def trace_tree(self):
		'''
			create table of all specified 3d points (0 to section.n3d()-1), x, y, z coordinates, 
		    (note, 3d point != segment, but arc3d(point i)/section length does give "x position" (0 to 1) of point)
		    and their associated section number (re.split('\[|\]', cell1.axon[192].name())[3] gives 192)
		'''
		tree = [] # tree is initially a list, dict to DataFrame is fastest to create the pandas DataFrame
		for sec in self.axon:
			num_segs = sec.n3d()
			sec_index = re.split('\[|\]', sec.name())[3]
			'''
			for seg in sec:
				loc = seg.x
				toAppend = {}
				toAppend.update(sec=sec_index, i3d=i, 
								x=loc, y=sec.y3d(i), z=sec.z3d(i), 
								arc=sec.arc3d(i), gd = geodesic_dist)
			'''
			for i in range(num_segs):
				toAppend = {} 	# each row to add is a dictionary
				loc = sec.arc3d(i) / sec.L
				geodesic_dist = eval("h.distance(self.{}[0](0.5), sec(loc))".format(self.sec_name))
				toAppend.update(sec=sec_index, i3d=i, 
								x=sec.x3d(i), y=sec.y3d(i), z=sec.z3d(i), 
								arc=sec.arc3d(i), gd = geodesic_dist)
				tree.append(toAppend)
		tree = pd.DataFrame(tree)
		return tree

	def add_synapses(self, file_path, syn_strength):
		'''
			add Exp2Syn synapses to model, based on xyz synapse locations
			requires the "tree" DataFrame attribute to be populated
		'''
		#print(file_path)
		### import synaptic locations
		conn = pd.read_csv(file_path)
		#conn = conn.drop(columns = ['type', 'partner'])
		num_synapses = conn.shape[0]
		#print("imported " + str(num_synapses) + " synapses")
		if num_synapses == 0:
			return 0, 0, 0, 0

		### KNN to map each synapse x, y, z (scaled x0.008) to the closest segment
		tree_coords = self.tree.loc[:, 'x':'z']
		syn_coords = conn.loc[:, 'x':'z'] / 125
		nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(tree_coords)
		distances, indices = nbrs.kneighbors(syn_coords) 
		# indices: index in tree of closest section and point location to a synapse

		### add synapses onto morphology
		syns = h.List()
		j = 0 # index in syns
		for index in indices:
			sec = int(self.tree.loc[index, 'sec'])
			i3d = self.tree.loc[index, 'i3d']	# the 3d point index on the section
			#print("adding synapse " + str(j) + " to section " + str(sec))
			loc = eval("self.{}[sec].arc3d(i3d) / self.{}[sec].L".format(self.sec_name, self.sec_name))
			# 0 to 1, length along section
			#print("about to append")
			syns.append(h.Exp2Syn(self.axon[sec](loc)))

			### synapse parameters from Tobin et al paper: 
			syns.object(j).tau1 = 0.2 #ms
			syns.object(j).tau2 = 1.1 #ms
			syns.object(j).e = -10 #mV, synaptic reversal potential = -10 mV for acetylcholine? 
			# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3125135/
			#syns.object(j).g = 0.0001 #uS default ### seems to have no effect on the result

			h.pop_section() # clear the section stack to avoid overflow (triggered by using ".L" above?)
			j = j + 1

		### use NetStim to activate NetCon
		nc = h.NetStim()
		nc.number = 1
		nc.start = 0
		nc.noise = 0

		ncs = h.List()
		for i in range(len(list(syns))):
			ncs.append(h.NetCon(nc, syns.object(i)))
			ncs.object(i).weight[0] = syn_strength # uS, peak conductance change

		return syns, nc, ncs, num_synapses

	def add_synapses_xyz(self, xyz_locs, syn_strength):
		'''
			add new synapses based on loaded xyz locations
		'''
		num_synapses = xyz_locs.shape[0]
		#print("imported " + str(num_synapses) + " synapses")
		if num_synapses == 0:
			return 0, 0, 0, 0

		### KNN to map each synapse x, y, z (scaled x0.008) to the closest segment
		tree_coords = self.tree.loc[:, 'x':'z']
		syn_coords = xyz_locs.loc[:, 'x_post':'z_post'] / 125
		nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(tree_coords)
		distances, indices = nbrs.kneighbors(syn_coords) 
		# indices: index in tree of closest section and point location to a synapse

		### add synapses onto morphology
		syns = h.List()
		j = 0 # index in syns
		for index in indices:
			sec = int(self.tree.loc[index, 'sec'])
			i3d = self.tree.loc[index, 'i3d']	# the 3d point index on the section
			#print("adding synapse " + str(j) + " to section " + str(sec))
			# TODO: I think could replace with cell1.axon[`sec`].X (4/2/2021)
			loc = eval("self.{}[sec].arc3d(i3d) / self.{}[sec].L".format(self.sec_name, self.sec_name))
			# 0 to 1, length along section
			#print("about to append")
			syns.append(h.Exp2Syn(self.axon[sec](loc)))

			### synapse parameters from Tobin et al paper: 
			syns.object(j).tau1 = 0.2 #ms
			syns.object(j).tau2 = 1.1 #ms
			syns.object(j).e = -10 #mV, synaptic reversal potential = -10 mV for acetylcholine? 
			# syns.object(j).bodyId_pre = xyz_locs.loc[j, 'bodyId_pre'] unfortunately can't add attrs
			# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3125135/
			#syns.object(j).g = 0.0001 #uS default ### seems to have no effect on the result

			h.pop_section() # clear the section stack to avoid overflow (triggered by using ".L" above?)
			j = j + 1

		### use NetStim to activate NetCon, initially inactive
		nc = h.NetStim()
		nc.number = 0
		nc.start = 0
		nc.noise = 0

		ncs = h.List()
		for i in range(len(list(syns))):
			ncs.append(h.NetCon(nc, syns.object(i)))
			ncs.object(i).weight[0] = syn_strength # uS, peak conductance change

		return syns, nc, ncs, num_synapses

	def add_synapses_subtree(self, sec_for_subtree, syn_count, syn_strength):
		'''
			add <syn_count> synapses to random sections in the subtree of 
			self.axon[<sec_for_subtree>]
		'''

		# get section numbers in the subtree
		subtree_secs = self.axon[sec_for_subtree].subtree()
		subtree_sec_nums_brack = [str(sec).partition('axon')[2] for sec in subtree_secs]
		subtree_sec_nums = [re.findall("\[(.*?)\]", sec)[0] for sec in subtree_sec_nums_brack] # debracket 

		### add synapses onto morphology
		syns = h.List()
		j = 0
		for index in range(syn_count):

			sec = int(random.choice(subtree_sec_nums))
			loc = random.uniform(0, 1)

			syns.append(h.Exp2Syn(self.axon[sec](loc)))

			### synapse parameters from Tobin et al paper: 
			syns.object(j).tau1 = 0.2 #ms
			syns.object(j).tau2 = 1.1 #ms
			syns.object(j).e = -10 #mV, synaptic reversal potential = -10 mV for acetylcholine? 
			# https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3125135/
			#syns.object(j).g = 0.0001 #uS default ### seems to have no effect on the result

			h.pop_section() # clear the section stack to avoid overflow 
			j += 1

		### use NetStim to activate NetCon, initially inactive
		nc = h.NetStim()
		nc.number = 0
		nc.start = 0
		nc.noise = 0

		ncs = h.List()
		for i in range(len(list(syns))):
			ncs.append(h.NetCon(nc, syns.object(i)))
			ncs.object(i).weight[0] = syn_strength # uS, peak conductance change

		num_synapses = syn_count

		return syns, nc, ncs, num_synapses

	def total_length(self):
		total_length = 0
		for sec in self.axon: 
			total_length += sec.L
		return total_length

	def surf_area(self):
		total_area = 0
		for sec in h.allsec():
			for seg in sec:
				total_area += seg.area()
		return total_area

def time_to_percent_peak(t, v, perc):
	'''
		Given a time trace, voltage trace, and a percentage X%, give the closest time in the
		time trace to X% of the voltage's peak amplitude. 
	'''
	base, peak = min(v), max(v)
	peak_loc = np.where(np.array(v) == peak)[0][0] # index of peak location
	perc_of_peak = perc * (peak - base) + base # value of percent of peak amplitude
	if peak_loc == 0: # safety catch for if v trace is all 0, maybe replace with np.nan, then use nansum 
		return 0
	# interpolate t value where v reaches inputted percent of peak amplitude
	time_of_perc = np.interp(perc_of_peak, np.array(v)[0:peak_loc], np.array(t)[0:peak_loc])
	# subsets portion of trace up to the peak
	#ind_of_perc = np.abs(np.array(v)[0:peak_loc] - perc_of_peak).argmin() 
	#time_of_perc = np.array(t)[ind_of_perc]
	return time_of_perc

def modify_EPSP_in_all_conns():
	'''
		20-12-08: single use script to modify 'epsp_exp' column in 20-09-26_all_conns
			save out as a new csv 20-12-08_all_conns
			same as the 9-26 version, but with EPSP values refreshed to Jamie's 10/01 corrections

		update: change this to the revised 12-08 EPSP amplitudes
			save out as overwriting the csv 20-12-08_all_conns
	'''

	prev_conn = pd.read_csv("20-09-26_all_conns.csv")
	#epsp_dir = pd.read_csv("20-10-01_Jamie's refreshed epsp_peaks.csv", index_col = 0)
	epsp_dir = pd.read_csv("20-12-08_Jamie's epsp_peaks, max of avgs.csv", index_col = 0)
	for i in range(prev_conn.shape[0]):
		prev_conn.at[i, 'epsp_exp'] = epsp_dir.loc[prev_conn.iloc[i]['pn'], prev_conn.iloc[i]['lhn']]
	prev_conn.to_csv("20-12-08_all_conns.csv")

# previously was local5 params: epas = -55, cm = 1.2, synstrength = 3.5e-5, ra = 125, gpas = 4.4e-5
# now error peak no skip params
def find_peak_vals_MC(epas = -55, cm = 0.6, synstrength = 5.5e-5, ra = 350, gpas = 5.8e-5, params = 'abs_norm_noskip',
					save_excel = False, show_plot = False, show_scatter = False, show_kinetics_scatter = False,
					conn_file = "20-12-08_all_conns.csv"):
	'''
		Given biophysical parameter inputs, output the resulting simulated EPSPs across the 
		entire population. 

		TODO: change synstrength parameter name to gsyn
	'''

	###
	### START SIMULATION CODE: 
	### INPUTS:
	all_conns = pd.read_csv(conn_file)
	all_conns = all_conns.assign(num_syn=np.zeros(len(all_conns))) 	# num synapses
	all_conns = all_conns.assign(lhn_SA=np.zeros(len(all_conns)))	# surface area

	param_set = params
	e_pas = epas # mV, reversal potential
	c_m = cm #uF/cm^2
	syn_strength = synstrength # uS, peak synaptic conductance
	R_a = ra # ohm-cm
	g_pas = gpas # S/cm^2

	### parameters:
	### biophysical parameters:
	#if param_set == 0:
		### parameters not preloaded
	#	continue 
	if param_set == 1:
		### 8/23: from local5v1
		R_a = 125 # ohm-cm
		g_pas = 4.4e-5 # S/cm^2
		param_print = True # whether to print param values when changing them
	elif param_set == 2:
		### 8/31: small param search, optimize to peak:
		R_a = 300
		g_pas = 1.2e-5
	elif param_set == 3:
		### 8/31: small param search, optimize to total error:
		### don't use, too similar to local5 params
		R_a = 100
		g_pas = 4.e-5
	elif param_set == 4:
		### 9/1: optimize to peak values
		R_a = 350
		g_pas = 1.8e-5
		c_m = 1
	elif param_set == 5:
		### completed 9/10: optimize to peak values, after local5 back to v1.1
		syn_strength = 4.5e-5
		R_a = 350
		g_pas = 1.8e-5
		c_m = 1.2
	elif param_set == 6:
		### 9/12: fit to avgs of connection peak
		c_m = 0.6
		syn_strength = 3.5e-5
		R_a = 350
		g_pas = 3.4e-5

	### run through all PN-LHN instances, simulate unitary EPSP and track peak amplitude 
	sim_traces = []
	for i in range(len(all_conns)):
		curr_trace = {}
		curr_trace.update(lhn = all_conns.lhn[i], pn=all_conns.pn[i])

		swc_path = "swc\\{}-{}.swc".format(all_conns.lhn[i], all_conns.lhn_id[i])
		syn_path = "syn_locs\\{}-{}_{}-{}.csv".format(all_conns.lhn[i], all_conns.lhn_id[i], all_conns.pn[i], all_conns.pn_id[i])

		cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
		cell1.discretize_sections()
		cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
		cell1.tree = cell1.trace_tree()
		synapses, netstim, netcons, num = cell1.add_synapses(syn_path, syn_strength)

		all_conns.loc[i, 'lhn_SA'] = cell1.surf_area()

		if num > 0:
			netstim.number = 1
			netstim.start = 0

			# activate synapses
			h.load_file('stdrun.hoc')
			x = h.cvode.active(True)
			v_s = h.Vector().record(cell1.axon[0](0.5)._ref_v) 		# soma membrane potential
			#v_z = h.Vector().record(p_siz(siz_loc)._ref_v)		# putative SIZ membrane potential
			t = h.Vector().record(h._ref_t)                     # Time stamp vector
			h.finitialize(-55 * mV)
			h.continuerun(40*ms)

			all_conns.loc[i, 'epsp_sim'] = float(max(v_s)+55)
			all_conns.loc[i, 'num_syn'] = num

			# KINETICS:
			# time from 10 to 90% peak:
			t_10to90 = time_to_percent_peak(t, v_s, 0.90) - time_to_percent_peak(t, v_s, 0.10)
			# time from 0.1 to 80% peak:
			t_0to80 = time_to_percent_peak(t, v_s, 0.80) - time_to_percent_peak(t, v_s, 0.0001)

			# TODO: track average transfer impedance to SIZ and average geodesic distance to SIZ
			# perhaps also the stdevs of above

			curr_trace.update(t_sim = t, v_sim = v_s, v_sim_peak = max(v_s)+55, 
							  v_exp_peak = all_conns.epsp_exp[i], 
							  rise_time_10to90 = t_10to90, rise_time_0to80 = t_0to80)
		else:
			all_conns.loc[i, 'epsp_sim'] = 0 # EPSP size = 0 if no synapses
			all_conns.loc[i, 'num_syn'] = 0	

			curr_trace.update(t_sim = [0, 20], v_sim = [-55, -55], v_sim_peak = 0, 
							  v_exp_peak = all_conns.epsp_exp[i],
							  rise_time_10to90 = 0, rise_time_0to80 = 0)

		sim_traces.append(curr_trace)

	### average together traces: find instances of each connection, then average each set of instances
	# values per connection are found from the average trace
	# I verified that the EPSP sim peaks are virtually the same with this method and the old one
	# kinetic predictions should be improved
	sim_avgs_v2 = []
	lhn_list = ['CML2', 'L1', 'L11', 'L12', 'L13', 'L15', 'ML3', 'ML8', 'ML9', 'V2', 'V3', 'local2', 'local5', 'local6']
	pn_list = ['DA4l', 'DC1', 'DL4', 'DL5', 'DM1', 'DM3', 'DM4', 'DP1m', 'VA1v', 'VA2', 'VA4', 'VA6', 
				'VA7l', 'VC1', 'VC2', 'VL2a', 'VL2p']
	# display simulation averages per connection type (not individual traces)
	# then save as svg with param class
	for lhn in lhn_list:
		for pn in pn_list:
			trace_locs = [i for i in range(len(sim_traces)) if sim_traces[i]["lhn"]==lhn and sim_traces[i]["pn"]==pn]

			# average the traces at trace_locs if the LHN-PN pair exists
			if len(trace_locs) > 0:
				t_interp = np.arange(0, 21, 0.05)

				avg_sim = np.zeros(len(t_interp))
				for ind in trace_locs:
					interp_trace = np.interp(t_interp, sim_traces[ind]["t_sim"], [x+55 for x in sim_traces[ind]["v_sim"]])

					avg_sim = [sum(pair) for pair in zip(avg_sim, interp_trace)]

				avg_sim = [val/len(trace_locs) for val in avg_sim]

				# calculate kinetics for avg sim trace
				t_10to90_sim = time_to_percent_peak(t_interp, avg_sim, 0.90) - time_to_percent_peak(t_interp, avg_sim, 0.10)
				t_0to80_sim = time_to_percent_peak(t_interp, avg_sim, 0.80) - time_to_percent_peak(t_interp, avg_sim, 0.0001)

				# calculate kinetics for exp trace
				trace_exp = pd.read_csv('exp_traces\\{}_{}.csv'.format(lhn, pn), header = None, dtype = np.float64)
				t_exp = trace_exp[0]+1.25 # slightly adjust to align with rise time of EPSP
				v_exp = trace_exp[1]
				t_10to90_exp = time_to_percent_peak(t_exp, v_exp, 0.90) - time_to_percent_peak(t_exp, v_exp, 0.10)

				# add LHN, PN, and info about the simulated trace to data table:
				toAppend = {}
				toAppend.update(e_pas = epas, c_m = cm, syn_strength = synstrength,	R_a = ra, g_pas = gpas,
								lhn = lhn, pn = pn, epsp_sim = max(avg_sim),
								epsp_exp = sim_traces[trace_locs[0]]['v_exp_peak'],
								t_sim_10to90 = t_10to90_sim, t_sim_0to80 = t_0to80_sim,
								t_exp_10to90 = t_10to90_exp)
				sim_avgs_v2.append(toAppend)
	sim_avgs = pd.DataFrame(sim_avgs_v2)

	'''
	### old method:
	# values per connection (PN-LHN) are averages from each instance of the connection trace
	conn_indices = {} # keys are tuples of LHN, PN names; values are indices of the connections
	for i in range(len(sim_traces)):
		curr_conn = (sim_traces[i]["lhn"], sim_traces[i]["pn"])
		if curr_conn not in conn_indices:
			conn_indices[curr_conn] = [i]
		else:
			conn_indices[curr_conn].append(i)
	sim_avgs = []
	for conn in conn_indices:
		toAppend = {}
		curr_lhn = conn[0]
		curr_pn = conn[1]
		conn_peaks = [sim_traces[i]["v_sim_peak"] for i in conn_indices[conn]]
		conn_t_10to90 = [sim_traces[i]["rise_time_10to90"] for i in conn_indices[conn]]
		conn_t_0to80 = [sim_traces[i]["rise_time_0to80"] for i in conn_indices[conn]]

		# also pull out experimental 10 to 90 rise time
		trace_exp = pd.read_csv('exp_traces\\{}_{}.csv'.format(curr_lhn, curr_pn), header = None, dtype = np.float64)
		t_exp = trace_exp[0]+1.25 # slightly adjust to align with rise time of EPSP
		v_exp = trace_exp[1]
		t_10to90_exp = time_to_percent_peak(t_exp, v_exp, 0.90) - time_to_percent_peak(t_exp, v_exp, 0.10)

		toAppend.update(lhn = curr_lhn, pn = curr_pn, epsp_sim = np.mean(conn_peaks),
						epsp_exp = sim_traces[conn_indices[conn][0]]["v_exp_peak"], 
						t_sim_10to90 = np.mean(conn_t_10to90), t_sim_0to80 = np.mean(conn_t_0to80),
						t_exp_10to90 = t_10to90_exp)
		sim_avgs.append(toAppend)
	sim_avgs = pd.DataFrame(sim_avgs)
	'''

	# compute normalized RSS error
	sum_peak_err = 0
	for i in range(len(sim_avgs)):
		normalized_resid = (sim_avgs.loc[i, 'epsp_sim'] - sim_avgs.loc[i, 'epsp_exp']) / sim_avgs.loc[i, 'epsp_exp']
		sim_avgs.loc[i, 'resid'] = normalized_resid * sim_avgs.loc[i, 'epsp_exp']
		sim_avgs.loc[i, 'norm_resid'] = normalized_resid
		if sim_avgs.loc[i, 'lhn'] != 'local5' or sim_avgs.loc[i, 'pn'] != 'VL2a':
			sum_peak_err += np.abs(normalized_resid)
		#else:
			#print("skipping {}, {}".format(sim_avgs.loc[i, 'lhn'], sim_avgs.loc[i, 'pn']))
		#sum_peak_err += normalized_resid**2

	if show_plot:
		plot_traces(sim_traces, cm, synstrength, ra, gpas)
	if save_excel:
		all_conns.to_excel('{}_mcsim_params{}_each_inst.xlsx'.format(date.today().strftime("%y-%m-%d"), str(params)))
		sim_avgs.to_excel('{}_mcsim_params{}_avgs.xlsx'.format(date.today().strftime("%y-%m-%d"), str(params)))
	if show_scatter:
		plt.rcParams["figure.figsize"] = (15,15)

		fig, ax = plt.subplots(nrows = 1, ncols = 2)

		#plt.scatter(all_conns.loc[:, 'epsp_exp'], all_conns.loc[:, 'epsp_sim'], color = 'black')
		ax[0].scatter(sim_avgs.loc[:, 'epsp_exp'], sim_avgs.loc[:, 'epsp_sim'], 
					s = 2, color = 'black')
		ax[0].set_xlabel("experimental EPSP peak (mV)")
		ax[0].set_ylabel("simulated EPSP peak (mV)")
		ax[0].plot([0, 7], [0, 7], color = 'grey', ls = '--')
		props = ("g_pas = " + str(gpas) + " S/cm^2, g_syn = " + str(round(synstrength*1000, 4)) + 
			" nS, c_m = " + str(cm) + " uF/cm^2, R_a = " + str(ra) + 
			" Ohm-cm")
		#plt.suptitle(props + " [current params]", 
		#		 fontsize = 24, y = 0.96)

		# test out new averaging method for kinetics
		ax[1].scatter(sim_avgs_v2.loc[:, 'epsp_exp'], sim_avgs_v2.loc[:, 'epsp_sim'], 
					s = 2, color = 'black')
		ax[1].set_xlabel("experimental EPSP peak (mV)")
		ax[1].set_ylabel("simulated EPSP peak (mV)")
		ax[1].plot([0, 7], [0, 7], color = 'grey', ls = '--')

		'''
		draw()

		fig.savefig('{}_mcsim_params{}_scatter.svg'.format(date.today().strftime("%y-%m-%d"), str(params)))
		'''
		plt.show()
	### fig_mcmodel_kinetics_predictions
	### scatter of rise time predictions vs actual
	if show_kinetics_scatter:
		plt.rcParams['figure.figsize'] = (2, 2)

		fig, ax = plt.subplots(nrows=1, ncols=2)

		ax[0].scatter(sim_avgs["t_exp_10to90"], sim_avgs["t_sim_10to90"], color = 'blue', s = 2) # size = 2
		ax[0].plot([0, 11], [0, 11], color = 'grey', alpha = 0.3) # unity line
		ax[0].spines["top"].set_visible(False)
		ax[0].spines["right"].set_visible(False)
		ax[0].set_xlabel('experimental rise time (ms)', fontsize = 9)
		ax[0].set_ylabel('simulated rise time (ms)', fontsize = 9)

		# test out new averaging method for kinetics
		ax[1].scatter(sim_avgs_v2["t_exp_10to90"], sim_avgs_v2["t_sim_10to90"], color = 'blue', s = 2)
		ax[1].plot([0, 11], [0, 11], color = 'grey', alpha = 0.3) # unity line
		ax[1].spines["top"].set_visible(False)
		ax[1].spines["right"].set_visible(False)
		ax[1].set_xlabel('experimental rise time (ms)', fontsize = 9)
		ax[1].set_ylabel('simulated rise time (ms)', fontsize = 9)
		'''
		draw()
		fig.savefig("fig_mcmodel_kinetics_predictions.svg")
		'''
		plt.show()

	return sim_traces, sim_avgs, sum_peak_err

def plot_traces(sim_traces, cm, synstrength, ra, gpas):
	'''
		given inputs (to be described), overlay simulated and experimental traces
		in cells of a large grid
	'''

	plt.rcParams["figure.figsize"] = (9,7)

	# 14 LHN by 17 PN plot
	fig, axs = plt.subplots(nrows = 14, ncols = 17, sharex = True, sharey = True)
	lhn_list = ['CML2', 'L1', 'L11', 'L12', 'L13', 'L15', 'ML3', 'ML8', 'ML9', 'V2', 'V3', 'local2', 'local5', 'local6']
	pn_list = ['DA4l', 'DC1', 'DL4', 'DL5', 'DM1', 'DM3', 'DM4', 'DP1m', 'VA1v', 'VA2', 'VA4', 'VA6', 'VA7l', 'VC1', 'VC2', 'VL2a', 'VL2p']
	[ax.set_xlim(0,21) for subrow in axs for ax in subrow]
	[ax.set_ylim(0,7) for subrow in axs for ax in subrow]
	plt.subplots_adjust(wspace=0, hspace=0)
	[axs[0, i].set_title(pn_list[i]) for i in range(len(pn_list))]
	[axs[i, 0].set_ylabel(lhn_list[i]) for i in range(len(lhn_list))]
	[ax.set_frame_on(False) for subrow in axs for ax in subrow]


	avg_sim_traces = pd.DataFrame({'t': np.arange(0, 21, 0.1)})
	# display simulation averages per connection type (not individual traces)
	# then save as svg with param class
	for lhn in lhn_list:
		for pn in pn_list:
			trace_locs = [i for i in range(len(sim_traces)) if sim_traces[i]["lhn"]==lhn and sim_traces[i]["pn"]==pn]

			# average the traces at trace_locs
			if len(trace_locs) > 0:
				t_interp = np.arange(0, 21, 0.1)

				avg_trace = np.zeros(len(t_interp))
				for ind in trace_locs:
					interp_trace = np.interp(t_interp, sim_traces[ind]["t_sim"], [x+55 for x in sim_traces[ind]["v_sim"]])

					avg_trace = [sum(pair) for pair in zip(avg_trace, interp_trace)]

				avg_trace = [val/len(trace_locs) for val in avg_trace]

				### plot simulated traces in proper grid location
				row = lhn_list.index(lhn)
				col = pn_list.index(pn)
				axs[row, col].plot(t_interp, avg_trace, color = 'green', lw = 0.8) # plot 

				# save avg s
				avg_sim_traces['{}_{}_sim'.format(lhn, pn)] = avg_trace
	avg_sim_traces.to_csv('figdata_avg_sim_traces_mc.csv')


	for i in range(len(sim_traces)):

		### plot simulated and experimental traces
		row = lhn_list.index(sim_traces[i]["lhn"])
		col = pn_list.index(sim_traces[i]["pn"])
		# read & plot experimental trace
		trace_exp = pd.read_csv('exp_traces\\{}_{}.csv'.format(sim_traces[i]["lhn"], sim_traces[i]["pn"]), header = None, dtype = np.float64)
		t_exp = trace_exp[0]+1.25 # slightly adjust to align with rise time of EPSP
		v_exp = trace_exp[1]
		axs[row, col].plot(t_exp, v_exp, color = 'red', lw = 0.8)

		axs[row, col].plot(sim_traces[i]["t_sim"], [x+55 for x in sim_traces[i]["v_sim"]], color = 'grey', alpha = 0.2, lw = 0.4)

	props = ("g_pas = " + str(gpas) + " S/cm^2, g_syn = " + str(round(synstrength*1000, 4)) + 
			" nS, c_m = " + str(cm) + " uF/cm^2, R_a = " + str(ra) + 
			" Ohm-cm")
	plt.suptitle(props + " [current params]", 
				 fontsize = 15, y = 0.96)

	draw()
	fig.savefig('fig_pop_mc_traces.svg')

	plt.show()

###
### t1, v1 the simulated trace, t2, v2 the experimental trace to fit to
### weight error from VL2a x3 to normalize amplitudes
###
def find_error(t1, v1, t2, v2):

	# normalize both traces by peak of experimental trace
	v1_norm = (v1+55) / max(v2+55) 
	v2_norm = (v2+55) / max(v2+55)

	peak_err = np.abs(max(v2_norm) - max(v1_norm))

	trace_range = int(np.floor(max(t2)))
	t_discr = range(1, trace_range) # discretize time blocks

	v1_interp = np.interp(t_discr, t1, v1_norm) # sim
	v2_interp = np.interp(t_discr, t2, v2_norm) # exp

	# mean of absolute value of difference
	trace_err = np.mean(np.abs(v2_interp - v1_interp))

	return peak_err, trace_err

def param_search_MC(conn_file = "20-12-08_all_conns.csv"):
	'''
		conn_file: the file containing list of LHN and PN body IDs and EPSP sizes
					was 20-08-27_all_conns.csv prior to final body ID refresh on 20-09-26
					after EPSP refresh is now 20-12-08_all_conns.csv
	'''

	all_conns = pd.read_csv(conn_file)

	start_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')

	e_pas = -55 # mV

	# note: for other run tiling other part of g_pas:
	# need to use the refreshed version of all_conns, then re-run the below eventually too

	# 20-12-08 after refreshing EPSP peaks, local6 morphologies -- hopefully first of final
	# still likely need to tile other part of g_pas
	# 12 * 4 * 13 * 16 = 9984
	syn_strength_s = np.arange(2.5e-5, 8.1e-5, 0.5e-5)
	c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
	g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
	R_a_s = np.arange(75, 451, 25) # ohm-cm 

	# different types of errors evaluated (over all connections) per paramater set
	err_per_paramset = []
	# EPSP amplitude and kinetics per connection, for each parameter set
	sim_per_conn_per_paramset = pd.DataFrame()

	# iterate through all biophysical parameter combinations
	for syn_strength_i in syn_strength_s:
		for c_m_i in c_m_s:
			for g_pas_i in g_pas_s:
				for R_a_i in R_a_s:

					### following errors skip local5/vl2a
					abs_norm_skip = 0 # sum of absolute values of normalized residuals
					abs_nonorm_skip = 0 # sum of absolute values of non-normalized residuals
					squ_norm_skip = 0 # sum of squares of normalized residuals
					
					### doesn't skip local5/vl2a
					abs_norm_noskip = 0 # sum of absolute values of normalized residuals
					abs_nonorm_noskip = 0 # sum of absolute values of non-normalized residuals
					squ_norm_noskip = 0 # sum of squares of normalized residuals
					
					sim_traces, sim_avgs, rss_err = find_peak_vals_MC(cm = c_m_i, ra = R_a_i, synstrength = syn_strength_i,
														  gpas = g_pas_i, save_excel = False, show_scatter = False)

					for i in range(len(sim_avgs)):
						normalized_resid = (sim_avgs.loc[i, 'epsp_sim'] - sim_avgs.loc[i, 'epsp_exp']) / sim_avgs.loc[i, 'epsp_exp']
						
						abs_norm_noskip += np.abs(normalized_resid) # normalized residual
						abs_nonorm_noskip += np.abs(normalized_resid * sim_avgs.loc[i, 'epsp_exp']) # non-normalized residual
						squ_norm_noskip += normalized_resid**2 # squared normalized residual

						if sim_avgs.loc[i, 'lhn'] != 'local5' or sim_avgs.loc[i, 'pn'] != 'VL2a':
							abs_norm_skip += np.abs(normalized_resid) # normalized residual
						if sim_avgs.loc[i, 'lhn'] != 'local5' or sim_avgs.loc[i, 'pn'] != 'VL2a':
							abs_nonorm_skip += np.abs(normalized_resid * sim_avgs.loc[i, 'epsp_exp']) # non-normalized residual
						if sim_avgs.loc[i, 'lhn'] != 'local5' or sim_avgs.loc[i, 'pn'] != 'VL2a':
							squ_norm_skip += normalized_resid**2 # squared normalized residual

					# save parameter values, (output trace indices), fit errors
					params_toAppend = {}
					params_toAppend.update(g_syn = syn_strength_i, g_pas = g_pas_i, R_a = R_a_i, 
									c_m = c_m_i,
									err_abs_norm_skip = abs_norm_skip, err_abs_norm_noskip = abs_norm_noskip,
									err_abs_nonorm_skip = abs_nonorm_skip,
									err_squ_norm_skip = squ_norm_skip, 
									err_squ_norm_noskip = squ_norm_noskip,
									err_abs_nonorm_noskip = abs_nonorm_noskip)
					
					# save overall error summed over all connection for this parameter set
					err_per_paramset.append(params_toAppend)
					# save EPSP prediction per connection
					if sim_per_conn_per_paramset.empty:
						sim_per_conn_per_paramset = sim_avgs
					else:
						sim_per_conn_per_paramset = sim_per_conn_per_paramset.append(sim_avgs)

					# update a CSV every 2000 parameters
					if len(err_per_paramset) % 2000 == 1:
						pd.DataFrame(err_per_paramset).to_csv('{}_err_per_{}paramsets_temp.csv'.format(datetime.today().strftime("%y-%m-%d"), str(len(err_per_paramset))))
						sim_per_conn_per_paramset.to_csv('{}_sim_per_conn_{}paramsets_temp.csv'.format(datetime.today().strftime("%y-%m-%d"), str(len(err_per_paramset))))

				#print("finished running " + str(str(round(g_pas_i, 6))) + " S/cm^2")

	err_per_paramset = pd.DataFrame(err_per_paramset)

	err_per_paramset.to_csv('{}_err_per_{}paramsets.csv'.format(datetime.today().strftime("%y-%m-%d"), str(len(err_per_paramset))))
	sim_per_conn_per_paramset.to_csv('{}_sim_per_conn_{}paramsets.csv'.format(datetime.today().strftime("%y-%m-%d"), str(len(err_per_paramset))))

	end_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')
	print("start time: {}, end time: {}".format(start_time, end_time))

	return err_per_paramset, sim_per_conn_per_paramset

def update_sim_per_conn(sim_per_conn_path = 'fit_outs\\20-12-27_MC_sim_per_conn_9216+9984.csv',
						modified_targets = ['local6', 'V2'],
						conn_file = "20-12-08_all_conns.csv"):
	''' given a few modified SWCs for postsynaptic cells, re-run a partial set of body IDs for ALL params and 
		update the sim_per_conn spreadsheet, then generate new best params
	'''

	all_conns = pd.read_csv(conn_file)
	prev_sim_per_conn = pd.read_csv(sim_per_conn_path)

	start_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')

	e_pas_i = -55 # mV

	# 21-01-23 FINAL RUN: slightly updated local6 and V2 morphologies, finalized EPSP peaks
	# just updating local6 and V2, not re-running all other morphologies
	# 12 * 4 * 25 * 16 = 19200
	syn_strength_s = np.arange(2.5e-5, 8.1e-5, 0.5e-5)
	c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
	g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.2e-5) # S/cm^2, round to 6 places
	R_a_s = np.arange(75, 451, 25) # ohm-cm 

	# 20-12-21 re-running using refreshed EPSP peaks, hopefully final run!
	# 12 * 4 * 13 * 16 = 9984
	#syn_strength_s = np.arange(2.5e-5, 8.1e-5, 0.5e-5)
	#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
	#g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
	#R_a_s = np.arange(75, 451, 25) # ohm-cm 
	# start time: 20-12-21-19:46:23, end time: 20-12-27-08:07:34

	# 20-12-16 after refreshing EPSP peaks, local6 morphologies -- tiling other part of g_pas
	# also using the (slightly) updated 20-12-08_all_conns, with slightly lower exp EPSP vals
	# 12 * 4 * 12 * 16 = 9216
	#syn_strength_s = np.arange(2.5e-5, 8.1e-5, 0.5e-5)
	#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
	#g_pas_s = np.arange(1.2e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
	#R_a_s = np.arange(75, 451, 25) # ohm-cm 
	# start time: 20-12-16-01:05:25, end time: 20-12-21-03:34:35

	# 20-12-08 after refreshing EPSP peaks, local6 morphologies -- hopefully first of final
	# still likely need to tile other part of g_pas
	# 12 * 4 * 13 * 16 = 9984
	#syn_strength_s = np.arange(2.5e-5, 8.1e-5, 0.5e-5)
	#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
	#g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
	#R_a_s = np.arange(75, 451, 25) # ohm-cm 

	# different types of errors evaluated (over all connections) per paramater set
	err_per_paramset = []
	# EPSP amplitude and kinetics per connection, for each parameter set
	sim_per_conn_per_paramset = pd.DataFrame()

	param_iter = 0
	# iterate through all biophysical parameter combinations
	for syn_strength_i in syn_strength_s:
		for c_m_i in c_m_s:
			for g_pas_i in g_pas_s:
				for R_a_i in R_a_s:

					# only simulate peaks for target cell body IDs in modified_cells
					for cell_type in modified_targets:
						cell_ids = [cell_id for cell_name, cell_id in zip(all_conns.lhn, all_conns.lhn_id) 
											if cell_type in cell_name]

						# find PNs giving input to the LHN
						input_type_ids = all_conns.loc[all_conns.lhn == cell_type][['pn', 'pn_id']].drop_duplicates()

						# iterate through inputs onto the LHN (may only be 1)
						for i, type_id_row in input_type_ids.iterrows(): 
							input_type, input_id = type_id_row['pn'], type_id_row['pn_id']
							print(cell_type, input_type)
							print(all_conns.loc[(all_conns.lhn == cell_type) & \
										(all_conns.pn == input_type), 'epsp_exp'])
							epsp_exp = all_conns.loc[(all_conns.lhn == cell_type) & \
										(all_conns.pn == input_type), 'epsp_exp'].iloc[0] # all EPSPs for a conn equal

							uEPSP_outputs = []
							for cell_id in cell_ids: 
								# simulate the EPSP, kinetics for each target body ID and the corresponding input
								uEPSP_output = sim_uEPSP(target = cell_type, target_id = cell_id, 
														 upstream = input_type, upstream_id = input_id,
														 R_a = R_a_i, c_m = c_m_i, g_pas = g_pas_i, 
														 e_pas = e_pas_i, syn_strength = syn_strength_i)
								uEPSP_outputs.append(uEPSP_output)
							uEPSP_outputs = pd.DataFrame(uEPSP_outputs)
							if (uEPSP_outputs.EPSP_sim == 0).all():
								continue # skip this input if it has no synapses

							epsp_sim, t_sim_10to90, t_sim_0to80 = mean(uEPSP_outputs.EPSP_sim), \
											mean(uEPSP_outputs.t_sim_10to90), mean(uEPSP_outputs.t_sim_0to80)
							resid, norm_resid = epsp_sim - epsp_exp, (epsp_sim - epsp_exp) / epsp_exp

							print('uEPSP amp: ', [epsp_sim, t_sim_10to90, t_sim_0to80, resid, norm_resid])
							# find appropriate row to update in MC_sim_per_conn
							prev_sim_per_conn.loc[(prev_sim_per_conn.R_a==R_a_i) & (prev_sim_per_conn.g_pas==g_pas_i) \
								& (prev_sim_per_conn.c_m==c_m_i) & (prev_sim_per_conn.syn_strength==syn_strength_i) \
								& (prev_sim_per_conn.lhn==cell_type) & (prev_sim_per_conn.pn==input_type), \
								['epsp_sim', 't_sim_10to90', 't_sim_0to80', 'resid', 'norm_resid']] \
								= [epsp_sim, t_sim_10to90, t_sim_0to80, resid, norm_resid]

					param_iter += 1

					if param_iter % 2000 == 1:
						prev_sim_per_conn.to_csv(f'{datetime.today().strftime("%y-%m-%d")}_sim_per_conn_{param_iter}paramsets_temp.csv')

	prev_sim_per_conn.to_csv(f'{datetime.today().strftime("%y-%m-%d")}_sim_per_conn_newlocal6_V2_{param_iter}.csv')	

	end_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')
	print("start time: {}, end time: {}".format(start_time, end_time))
	
	return prev_sim_per_conn

def sim_uEPSP(target, target_id, upstream, upstream_id,
				R_a, c_m, g_pas, e_pas, syn_strength):
	'''	return uEPSP attributes given a target (postsynaptic) and upstream (presynaptic) cell
	'''
	swc_path = "swc\\{}-{}.swc".format(target, str(target_id))
	syn_path = "syn_locs\\{}-{}_{}-{}.csv".format(target, str(target_id), upstream, str(upstream_id))

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()
	synapses, netstim, netcons, num_syn = cell1.add_synapses(syn_path, syn_strength)

	surf_area = cell1.surf_area()

	if num_syn > 0:
		netstim.number = 1
		netstim.start = 0

		# activate synapses
		h.load_file('stdrun.hoc')
		x = h.cvode.active(True)
		v_trace_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v) 		# soma membrane potential
		#v_z = h.Vector().record(p_siz(siz_loc)._ref_v)		# putative SIZ membrane potential
		t_trace = h.Vector().record(h._ref_t)                     # Time stamp vector
		h.finitialize(-55 * mV)
		h.continuerun(40*ms)
		
		EPSP_sim = float(max(v_trace_soma)+55)

		# KINETICS:
		# time from 10 to 90% peak:
		t_10to90 = time_to_percent_peak(t_trace, v_trace_soma, 0.90) - time_to_percent_peak(t_trace, v_trace_soma, 0.10)
		# time from 0.1 to 80% peak:
		t_0to80 = time_to_percent_peak(t_trace, v_trace_soma, 0.80) - time_to_percent_peak(t_trace, v_trace_soma, 0.0001)

		# TODO: track average transfer impedance to SIZ and average geodesic distance to SIZ
		# perhaps also the stdevs of above
	else:
		EPSP_sim, t_trace, v_trace_soma = 0, [0, 20], [-55, -55]
		t_10to90, t_0to80 = None, None

	uEPSP_output = {'EPSP_sim': EPSP_sim, 'num_syn': num_syn, 't_sim_10to90': t_10to90, 
					't_sim_0to80': t_0to80, 't_trace': t_trace, 'v_trace_soma': v_trace_soma}
	return uEPSP_output

def analyze_fits():
	'''
		given a csv of errors per parameter set, for 
		SCv1, SCv2, and MC fits (each fit should use same error types).
		display for each error type the best param sets across fit types:
			1) scatter of simulated vs. exp. EPSP peaks across population
			2) [TODO] a bar chart of errors per connection
	'''

	# file paths of error per param CSVs, for the different model types
	err_per_param_csvs = {
		'SCv1': 'fit_outs//20-12-11_SCv1_err_per_6174paramsets.csv',
		'SCv2': 'fit_outs//20-12-11_SCv2_err_per_6174paramsets.csv',
		'MC': 'fit_outs//20-12-15_MC_err_per_9984+9216paramsets_raw.csv'
		# MC: added 20-12-21 9216 params, 9984 being re-run with slight modified EPSPs
	}

	# read in error tables
	err_per_params = {}
	for model_type, csv in err_per_param_csvs.items():
		err_per_params[model_type] = pd.read_csv(csv, index_col = False)

	# find the list of error types
	err_types = [col for col in err_per_params['MC'].columns if 'err' in col]

	# create a sim vs exp EPSP scatter for each error type
	for err_type in err_types:
		fig, ax = plt.subplots(nrows = 1, ncols = 1)

		# for each model type, plot scatter of EPSP values
		for model_type, err_per_param in err_per_params.items():
			print(f'plotting simulated EPSPs for {model_type}')
			best_param_set_ind = err_per_param[err_type].idxmin()
			best_param_set = {}
			if 'SC' in model_type:
				best_param_set['g_syn'] = round(err_per_param.iloc[best_param_set_ind]['g_syn'], 3)
				best_param_set['g_pas'] = round(err_per_param.iloc[best_param_set_ind]['g_pas'], 6)
				best_param_set['c_m'] = round(err_per_param.iloc[best_param_set_ind]['c_m'], 1)

				sim_traces, sim_avgs, sum_peak_err = find_peak_vals_SC(version = int(model_type[-1]), 
					gpas = best_param_set['g_pas'], cm = best_param_set['c_m'], gsyn = best_param_set['g_syn'])

				ax.scatter(sim_avgs.loc[:, 'epsp_exp'], sim_avgs.loc[:, 'epsp_sim'], s = 3.5,
							label = f"{model_type}: g_syn={best_param_set['g_syn']} nS, \n"\
									f"g_pas={best_param_set['g_pas']} S/cm^2, \nc_m={best_param_set['c_m']} \u03BCF/cm^2")
			elif 'MC' in model_type:
				best_param_set['g_syn'] = round(err_per_param.iloc[best_param_set_ind]['g_syn'], 6)
				best_param_set['g_pas'] = round(err_per_param.iloc[best_param_set_ind]['g_pas'], 6)
				best_param_set['c_m'] = round(err_per_param.iloc[best_param_set_ind]['c_m'], 1)
				best_param_set['R_a'] = round(err_per_param.iloc[best_param_set_ind]['R_a'], 1)

				sim_traces, sim_avgs, sum_peak_err = find_peak_vals_MC(ra = best_param_set['R_a'],
					gpas = best_param_set['g_pas'], cm = best_param_set['c_m'], synstrength = best_param_set['g_syn'],
					params = err_type)

				ax.scatter(sim_avgs.loc[:, 'epsp_exp'], sim_avgs.loc[:, 'epsp_sim'], s = 3.5,
							label = f"{model_type}: g_syn={round(best_param_set['g_syn']*1000,3)} nS, \n"\
									f"g_pas={best_param_set['g_pas']} S/cm^2, \nc_m={best_param_set['c_m']} \u03BCF/cm^2, "\
									f"\nR_a={best_param_set['R_a']} \u03A9m-cm")

		# add axis labels, horizontal line
		ax.legend(loc = 'center left', prop={'size': 8}, bbox_to_anchor = (1.01, 0.5), borderaxespad = 0)
		plt.subplots_adjust(right=0.75) # give room to legend on right
		ax.plot([0, 7], [0, 7], color = 'grey', ls = '--', alpha = 0.5)
		ax.set_xlabel("experimental EPSP peak (mV)")
		ax.set_ylabel("simulated EPSP peak (mV)")
		ax.set_title(f'error type: {err_type}')
		ax.spines['top'].set_visible(False)
		ax.spines['right'].set_visible(False)

		plt.savefig(f'fit_comp_{err_type}.png', format = 'png', bbox_inches='tight', dpi = 300)
		#plt.show()

def shelve_all_resids():
	toshelve = ['all_resids']
	shelf_name = '20-09-27_mcfit_all_resids.out'
	shelf = shelve.open(shelf_name, 'n')
	for key in dir():
		try: 
			if key in toshelve: 
				shelf[key] = globals()[key]
		except TypeError:
			#
        	# __builtins__, my_shelf, and imported modules can not be shelved.
        	#
			print('ERROR shelving: {0}'.format(key))
	shelf.close()

def transf_imped_of_inputs(down, down_id, up, up_id, siz_sec, siz_seg, transf_freq = 20, toPlot = False):
	'''
		after initiating a downstream cell and synapses onto the cell, 
		calculate the mean transfer impedance between the synaptic locations
		and a given section number of the cell 

		from docs for Impedance.transfer()
			The value returned can be thought of as either |v(loc)/i(x)| or |v(x)/i(loc)| 
			Probably the more useful way of thinking about it is to assume a current stimulus of 1nA 
			injected at x and the voltage in mV recorded at loc
	'''
	swc_path = "swc\\{}-{}.swc".format(down, down_id)
	syn_path = "syn_locs\\{}-{}_{}-{}.csv".format(down, down_id, up, up_id)

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()
	synapses, netstim, netcons, num = cell1.add_synapses(syn_path, syn_strength)

	# set up Impedance measurement class
	imp = h.Impedance()
	imp.loc(siz_seg, sec = cell1.axon[siz_sec])
	imp.compute(transf_freq)	# starts computing transfer impedance @ freq 

	syn_info = []
	# iterate through synapses
	for syn in synapses:
		# find Z_c from synapse to siz_loc AND distance between the points, append to list
		curr_loc = syn.get_segment()
		curr_transf_imp = imp.transfer(curr_loc)
		curr_distance = h.distance(cell1.axon[siz_sec](siz_seg), curr_loc)

		# convert to dictionary input with interpretable outputs
		toAppend = {}
		toAppend.update(dist_to_siz = curr_distance, Zc_to_siz = curr_transf_imp)
		syn_info.append(toAppend)

	# plot synapse to SIZ distance vs transfer impedance
	if toPlot:
		plt.scatter([val[dist_to_siz] for val in syn_info], [val[Zc_to_siz] for val in syn_info])
		plt.xlabel('synapse to SIZ (um)')
		plt.ylabel('transfer impedance (MOhm)')
		plt.show()

	return syn_info
# example code for above method:
d, d_id, u, u_id, s_sec, s_seg = 'local5', '5813105722', 'VA6', '1881751117', 996, 0
#transf_imped_of_inputs(down = d, down_id = d_id, up = u, up_id = u_id, 
#						siz_sec = s_sec, siz_seg = s_seg, transf_freq = 20)

def instantiate_lhns():
	'''
		code I copy pasted into the command line to manually
		look at the transfer impedance / other electrotonic measures
		in the GUI for two example LHNs
	'''

	# population fit biophysical parameters
	R_a = 350 # Ohm-cm
	c_m = 0.6 # uF/cm^2
	g_pas = 5.8e-5 # S/cm^2
	e_pas = -55 # mV
	syn_strength = 5.5e-5 # uS

	# change to path for hemibrain DM1 
	swc_path = "swc\\ML9-542634516.swc"
	# swc_path = "swc\\KCs (pasha)\\KCa'b'-ap1-487834111.swc"
	# swc_path = "swc\\KCs (pasha)\\KCab-s-331662717.swc"
	# swc_path = "swc\\KCs (pasha)\\KCg-m-354775482.swc"
	# swc_path = "swc\\L12-391609333.swc"
	# swc_path = "swc\\local5-5813105722.swc"

	# local5 params
	R_a = 375 # ohm-cm ### NOTE: tripling R_a from 125
	c_m = 1.2 # uF/cm^2
	g_pas = 4.4e-5 # S/cm^2 
	e_pas = -55 # mV
	syn_strength = 3.5e-5 # uS, peak synaptic conductance

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	syn_path = "syn_locs\\ML9-542634516_DM1-542634818.csv"

	synapses, netstim, netcons, num = cell1.add_synapses(syn_path, syn_strength)

def find_input_attrs_210217(target_name = 'ML9', target_body_id = 542634516, weight_threshold = 10, 
								measure_locs={'soma': (0,0.5), 'siz': (569,0.01), 'axon':(609,0.58)},
								imp_measure_sites=['soma', 'ax_start', 'dendr_first_branch'],
								transf_freq = 20, 
								toPlot = False,
								param_set = 'pop_fit',
								isopot_dendr_arbor = False, isopot_ax_arbor = False, isopot_prim_ax = False,
								isopot_whole_nrn = False,
								isopot_Ra_val = 0.001,
								highpot_prim_ax = False, highpot_Ra_val = 10000):
	'''
		given the name and body ID of an existing LHN (which has a skeleton in the swc folder)
		instantiate Cell and use hemibrain to add all synapses above a threshold weight
		return DataFrame with EPSP and impedance attributes about each unique connection type

	Parameters:
		measure_locs - dictionary
				TODO: is the format like this: {'dendr_start': (sec, seg), 'dendr_first_branch': (sec, seg), 
												'ax_start': (sec, seg), 'ax_first_branch': (sec, seg)}
				what are the keys that must be in there (which are referenced in code)
		imp_measure_sites - list of strings: must be keys in measure_locs, will measure transfer 
			resistance and transfer ratio with reference to these sites
		isopot_dendr_arbor, isopot_ax_arbor - bool: whether to set Ra of axonal or dendritic arbor=0
			** uses 'dendr_first_branch' and 'ax_first_branch' in measure_locs to set ax and dendr arbor

	Returns:
		all_conns - list of dicts: each dict corresponds to one input connection onto the target
	'''
	print(f'-------- evaluating inputs to {target_name} {target_body_id}')
	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')
	### add neuprint call if the SWC doesn't exist inside

	# get swc straight from neuprint:
	#skel = fetch_skeleton(body = target_body_id, format = 'swc') # import skeleton

	if param_set == 'pop_fit':
		# biophysical parameters from our fits
		R_a = 350
		c_m = 0.6
		g_pas = 5.8e-5
		e_pas = -55 # one parameter left same in both, we used -55 in our fits
		syn_strength = 5.5e-5 # uS
	elif param_set == 'retr_local5_fit':
		R_a = 375 # ohm-cm # x3 from 125
		c_m = 1.2 # uF/cm^2
		g_pas = 4.4e-5 # S/cm^2 
		e_pas = -55 # mV
		syn_strength = 3.5e-5 # uS, peak synaptic conductance

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	conns = fetch_simple_connections(upstream_criteria = None, downstream_criteria = target_body_id, min_weight = weight_threshold)
	
	# get number of post-synapses on the target neuron
	try:
		target, r = fetch_neurons(target_body_id)
		target_syn_count = target.post[0]
	except:
		print('likely no internet connection')

	if isopot_dendr_arbor:
		print(f'setting dendritic arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[measure_locs['dendr_first_branch'][0]].subtree() 
						if sec != cell1.axon[measure_locs['dendr_first_branch'][0]]]:
			sec.Ra = isopot_Ra_val
	if isopot_ax_arbor:
		print(f'setting axonal arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[measure_locs['ax_first_branch'][0]].subtree() 
						if sec != cell1.axon[measure_locs['ax_first_branch'][0]]]:
			sec.Ra = isopot_Ra_val
	if isopot_prim_ax:
		print(f'setting primary axon axial resistance to {isopot_Ra_val}')
		'''prim_ax_secs = [sec for sec in cell1.axon[siz_sec].subtree() \
												if sec not in cell1.axon[ax_branch_out_sec].subtree()[1:]]
								for sec in prim_ax_secs:
									sec.Ra = isopot_Ra_val'''
		print('todo')
	if highpot_prim_ax: # from 'N_ax_start_sec' = siz_sec to 'N_ax_first_branch_sec'
		print(f'setting primary axon axial resistance to {highpot_Ra_val}')
		'''prim_ax_secs = [sec for sec in cell1.axon[siz_sec].subtree() \
												if sec not in cell1.axon[ax_branch_out_sec].subtree()[1:]]
								for sec in prim_ax_secs:
									sec.Ra = highpot_Ra_val'''
		print('todo')
	if isopot_whole_nrn:
		print(f'setting entire neuron axial resistance to {isopot_Ra_val}')
		for sec in h.allsec():
			sec.Ra = isopot_Ra_val

	### instantiate synapses for each connection with weight > threshold
	all_conns = []
	for pre_name in set(conns.type_pre):
		# find all body IDs for this presynaptic neuron type
		pre_bodyIds = [conns.bodyId_pre[ind] for ind in range(len(conns.type_pre)) if conns.type_pre[ind] == pre_name]

		# get all synapse xyz locations for the body IDs in this neuron type (may be just 1 body ID)
		syn_locs = pd.DataFrame(columns = ['x_post', 'y_post', 'z_post'])
		for pre_id in pre_bodyIds:
			curr_syn_locs = fetch_synapse_connections(source_criteria = pre_id, target_criteria = target_body_id)
			syn_locs = syn_locs.append(curr_syn_locs[['x_post', 'y_post', 'z_post']])

		'''conns1 = fetch_simple_connections(upstream_criteria = input1, downstream_criteria = target_body_id)
		pre_bodyIds1 = conns1.bodyId_pre
		syn_locs1 = fetch_synapse_connections(source_criteria = pre_bodyIds1, target_criteria = target_body_id)
		curr_syns1, netstim1, netcons1, num1 = cell1.add_synapses_xyz(xyz_locs = syn_locs1, syn_strength = syn_strength)
						'''
		# add synapses onto skeleton
		curr_syns, netstim, netcons, num = cell1.add_synapses_xyz(xyz_locs = syn_locs, syn_strength = syn_strength)

		print('adding {} synapses from {} to {}'.format(str(num), pre_name, target_name))

		# evaluate percentage of synapses in dendritic arbor
		if 'dendr_start' in measure_locs.keys():
			num_in_dendr = 0
			for syn in curr_syns:
				if str(syn.get_segment()).partition('(')[0] in \
					[str(val) for val in cell1.axon[measure_locs['dendr_start'][0]].subtree()]:
					num_in_dendr += 1
			print('proportion synapses in dendrite: {}'.format(str(num_in_dendr/num)))

		toAppend = {}
		toAppend.update(post_name = target_name, post_id = target_body_id,
							pre_name = pre_name, pre_id = str(pre_bodyIds)[1:-1],
							syns = curr_syns, syn_count = len(curr_syns),
							syn_budget = len(curr_syns) / target_syn_count,
							perc_in_dendr = num_in_dendr/num,
							num_instances = len(pre_bodyIds), stim = [netstim])

		# activate ALL synapses, then all dendritic, then all axonal synapses & measure uEPSP
		for syn_type, syn_morph_feature in zip(['allSyns', 'dendrSyns', 'axSyns'], ['all', 'dendr_start', 'ax_start']):
			print(f'simulating uEPSP for {syn_type}')
			num_syn_in_type = 0
			if syn_morph_feature=='all': 
				for netcon in netcons: 
					netcon.weight[0] = syn_strength
					num_syn_in_type += 1
			else: # only activate dendritic OR axonal synapses
				for i, syn in enumerate(curr_syns):
					if str(syn.get_segment()).partition('(')[0] in \
						[str(val) for val in cell1.axon[measure_locs[syn_morph_feature][0]].subtree()]:
						netcons.object(i).weight[0] = syn_strength # uS, peak conductance change
						num_syn_in_type += 1

			if num_syn_in_type > 0: # if there are dendritic or axonal synapses (will be >0 for allSyns trivially)
				# activate + measure dendritic / axonal uEPSP
				netstim.number = 1
				h.load_file('stdrun.hoc')
				x = h.cvode.active(True)
				v_temp = {}
				for loc, (sec, seg) in measure_locs.items():
					if loc=='soma':
						# for some reason ML9-542634516's axon[0](1) is at the primary branch point
						try: v_temp[loc] = h.Vector().record(cell1.soma[0](0.5)._ref_v)
						except: v_temp[loc] = h.Vector().record(cell1.axon[0](0.5)._ref_v)
						continue
					v_temp[loc] = h.Vector().record(cell1.axon[sec](seg)._ref_v) # voltage trace vectors
				t_temp = h.Vector().record(h._ref_t)                     # time stamp vector
				h.finitialize(-55 * mV)
				h.continuerun(40*ms)
				netstim.number = 0
				# measure rise time of EPSP at pSIZ
				#t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)
				for loc, (sec, seg) in measure_locs.items():
					toAppend[f'uEPSP_max_{loc}_{syn_type}'] = max(list(v_temp[loc]))+55
			else: # may be no dendritic or axonal synapses... 
				for loc, (sec, seg) in measure_locs.items():
					toAppend[f'uEPSP_max_{loc}_{syn_type}'] = np.nan

			# set all synapses to weight 0 before activating next "set" of synapses
			for i in range(len(list(curr_syns))):
				netcons.object(i).weight[0] = 0 # uS, peak conductance change

		all_conns.append(toAppend)

	for measure_site in imp_measure_sites:
		# set up Impedance measurement class
		imp = h.Impedance()
		if measure_site=='soma': 
			try: meas_sec_seg = cell1.soma[0](0.5)
			except: meas_sec_seg = cell1.axon[0](0.5)
		else: meas_sec_seg = cell1.axon[measure_locs[measure_site][0]](measure_locs[measure_site][1])
		imp.loc(meas_sec_seg)
		imp.compute(transf_freq)	# starts computing transfer impedance @ freq 

		### iterate through all connections and measure impedances
		for conn in all_conns:
			curr_syns = conn['syns']

			# iterate through each synapse in the connection
			syn_info = []
			for syn in curr_syns:
				# find Z_c = transfer impedance from synapse to measure_site, # find Z_i = input impedance at synapse
				curr_transf_imp, curr_input_imp = imp.transfer(syn.get_segment()), imp.input(syn.get_segment())
				# find distance from synapse to measure_site
				curr_distance = h.distance(meas_sec_seg, syn.get_segment())
				# find voltage transfer ratio from synapse to measure_site
				curr_transf_ratio = imp.ratio(syn.get_segment())

				# record individual synapse info
				toAppend = {}
				toAppend.update(dist_to_site = curr_distance, Zc_to_site = curr_transf_imp, 
								Zi = curr_input_imp, K_to_site = curr_transf_ratio)
				syn_info.append(toAppend)

			# update connection info with average impedance properties
			conn['mean_Zi'] = mean([val['Zi'] for val in syn_info])
			conn['std_Zi'] = np.std([val['Zi'] for val in syn_info])
			for meas in ['dist_to_', 'Zc_to_', 'K_to_']:
				conn['mean_'+meas+measure_site] = mean([val[meas+'site'] for val in syn_info])
				conn['std_'+meas+measure_site] = np.std([val[meas+'site'] for val in syn_info])

	# measure mEPSP information for each connection
	# somewhat crude to use code that reinitializes the skeleton and re-adds the synapses, 
	# but hopefully there isn't some weird difference between how `visualize_inputs` and the initialization
	# above adds synapses
	for conn in all_conns:

		# NOTE: as of 21-02-22, only works for target body IDs in Jamie's labelled SWC's in Dropbox,
		# due to how siz_sec and siz_seg are identified
		per_synapse_df = probe_mEPSPs(target_name = conn['post_name'], target_body_id = conn['post_id'], 
							input_name = conn['pre_name'],
							siz_sec = None, siz_seg = None,
							lhn_morph_path = '21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv',
							isopot_dendr_arbor = isopot_dendr_arbor, isopot_ax_arbor = isopot_ax_arbor, 
							isopot_prim_ax = isopot_prim_ax,
							isopot_whole_nrn = isopot_whole_nrn,
							isopot_Ra_val = isopot_Ra_val,
							highpot_prim_ax = highpot_prim_ax, highpot_Ra_val = highpot_Ra_val)
		# TODO: turn swcpointno into global variable
		if not per_synapse_df.empty:
			conn.update(mEPSP_sum_eff_soma = per_synapse_df.sum_eff_soma,
						mEPSP_sum_eff_siz = per_synapse_df.sum_eff_siz,
						mEPSP_mean_soma = per_synapse_df.mEPSP_soma.mean(), 
						mEPSP_std_soma = per_synapse_df.mEPSP_soma.std(),
						mEPSP_mean_siz = per_synapse_df.mEPSP_siz.mean(),
						mEPSP_std_siz = per_synapse_df.mEPSP_siz.std(),
						mEPSP_mean_siz_dendrSyns = per_synapse_df.loc[per_synapse_df.ax_v_dendr=='dendritic']['mEPSP_siz'].mean(),
						mEPSP_std_siz_dendrSyns = per_synapse_df.loc[per_synapse_df.ax_v_dendr=='dendritic']['mEPSP_siz'].std(),
						mEPSP_mean_siz_axSyns = per_synapse_df.loc[per_synapse_df.ax_v_dendr=='axonal']['mEPSP_siz'].mean(),
						mEPSP_std_siz_axSyns = per_synapse_df.loc[per_synapse_df.ax_v_dendr=='axonal']['mEPSP_siz'].std())
			# compute mean mEPSP for dendritic-targeting synapses, and axonal-targeting synapses

	return all_conns

def attrs_per_LHNmEPSP(weight_threshold = 5, transf_freq = 0,
					   compt_manips = {'isopot_dendr_arbor': False, 'isopot_ax_arbor': False, 
					   'isopot_prim_ax': False, 'isopot_whole_nrn': False,
					   'isopot_Ra_val': 0.001,
					   'highpot_prim_ax': False, 
					   'highpot_Ra_val': 10000}):
	'''	21-03-01: measuring mEPSPs, impedance properties for all inputs >weight_threshold synapses at various
		locations on the neuron

		for each neuron in a list (i.e. a list of LHNs), find information about EACH mEPSP of its
		input connections, such as mEPSP size, impedance measures, synapse counts, etc.
		UPDATE: 21-03-06 went from `21-02-16...` file for variable nrns, to `21-03-06` (adding LHLNs)

		possible inputs: target_neuron_file = 'KC_list_siz_axon_locs.csv' # list of ~23 hand picked KCs
						 target_neuron_file = 'LHN_list_siz_axon_locs.csv' # list of our experimental-matched LHNs
	Parameters:
		weight_threshold - int: add synapses from inputs with >threshold total synapses onto the target
		transf_freq - int: freq at which to evaluate impedance properties
		compt_manips - dict: inputs into probe_mEPSPs, whether to make certain parts of the neuron more 
						or less compartmenalized
	'''
	nrns = pd.read_csv('21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv')

	# iterate through each target neuron, concatenate relevant file info
	mEPSPs_allLHNs_df = pd.DataFrame()
	for i in range(nrns.shape[0]):

		mEPSPs_oneLHN_df = probe_mEPSPs(target_name = nrns.iloc[i].lhn, target_body_id = nrns.iloc[i].body_id, 
									 input_name = 'all_inputs',
									 lhn_morph_path = '21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv',
									 all_input_min_weight = weight_threshold,
									 transf_freq = transf_freq,
									 **compt_manips)

		mEPSPs_allLHNs_df = mEPSPs_allLHNs_df.append(mEPSPs_oneLHN_df)

	date = datetime.today().strftime("%y-%m-%d")
	compt_manip_str = ''
	for key, val in compt_manips.items():
		if isinstance(val, bool) and val:
			compt_manip_str += '_' + key

	mEPSPs_allLHNs_df.to_csv(f'{date}_attrs_per_LHNmEPSP{compt_manip_str}.csv')
	return mEPSPs_allLHNs_df

def attrs_per_LHNinput(weight_threshold = 5, transf_freq = 0,
						param_set = 'pop_fit', 
						nrn_list_path = '21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv',
						compt_manips = {'isopot_dendr_arbor': False, 'isopot_ax_arbor': False, 
					   'isopot_prim_ax': False, 'isopot_whole_nrn': False,
					   'isopot_Ra_val': 0.001,
					   'highpot_prim_ax': False, 
					   'highpot_Ra_val': 10000}):
	'''	21-02-17: measuring uEPSPs, impedance properties for all inputs >weight_threshold synapses at various
		locations on the neuron

		testing Jamie's hypothesis that the voltage transfer ratio over the 
		primary neurite may be a key factor in increasing linearity of uEPSP size at the soma
		with synapse budget

		for each neuron in a list (i.e. a list of LHNs), find information about its
		input connections, such as EPSP size, impedance measures, synapse counts, etc.
		UPDATE: 21-03-06 went from `21-02-16...` file for variable nrns, to `21-03-06` (adding LHLNs)

		possible inputs: target_neuron_file = 'KC_list_siz_axon_locs.csv' # list of ~23 hand picked KCs
						target_neuron_file = 'LHN_list_siz_axon_locs.csv' # list of our experimental-matched LHNs

	TODO: once the proximal dendrite location is fixed, assign percentage of synapses to dendrite as a column
		measure the distance from dendr_start to dendr_first_branch (maybe a different method)

	Parameters:
		nrn_list_path - string: contains lhn names + id's, and the nodes that Jamie ID'd in SWC space 
								and the conversion into NEURON space
								'21-02-16_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv' - no LHLNs
								'21-03-06...' - includes LHLNs
		threeCompts - DEPRECATED: used to be a bool that would specify whether to set axon and dendrite to 
								isopotential
	'''
	nrns = pd.read_csv(nrn_list_path)

	# iterate through each target neuron, concatenate relevant file info
	nrns_input_attrs = pd.DataFrame()
	for i in range(nrns.shape[0]):
		measure_locs = {'dendr_start': None, 'dendr_first_branch': None, 'ax_start': None, 'ax_first_branch': None}
		for site in measure_locs.keys():
			measure_locs[site] = (nrns.iloc[i]['N_'+site+'_sec'], nrns.iloc[i]['N_'+site+'_seg'])
		measure_locs['soma'] = (0,0)

		curr_input_attrs = find_input_attrs_210217(target_name = nrns.iloc[i].lhn, 
								target_body_id = nrns.iloc[i].body_id,
								weight_threshold = weight_threshold, transf_freq = transf_freq,
								measure_locs=measure_locs,
								imp_measure_sites=['soma', 'ax_start', 'dendr_first_branch'],
								param_set = param_set,
								**compt_manips)

		nrns_input_attrs = nrns_input_attrs.append(curr_input_attrs)

	date = datetime.today().strftime("%y-%m-%d")
	compt_manip_str = ''
	for key, val in compt_manips.items():
		if isinstance(val, bool) and val:
			compt_manip_str += '_' + key

	nrns_input_attrs.to_csv(f'{date}_attrs_per_LHNinput{compt_manip_str}.csv')

	return nrns_input_attrs

def k_across_primary_dendrite(transf_freq = 0):
	'''	21-02-17: find the voltage transfer ratio from dendrite start to dendrite branch out point
	'''
	nrns = pd.read_csv('21-03-06_LHN_SWCPointNo_to_NEURON.csv')

	# iterate through each target neuron, concatenate relevant file info
	prim_dendr_per_nrn = []
	for i in range(nrns.shape[0]):
		measure_locs = {'dendr_start': None, 'dendr_first_branch': None, 'ax_start': None, 'ax_first_branch': None}
		for site in measure_locs.keys():
			measure_locs[site] = (nrns.iloc[i]['N_'+site+'_sec'], nrns.iloc[i]['N_'+site+'_seg'])
		measure_locs['soma'] = (0,0)

		cell1, curr_syns, netstim, netcons, num = visualize_inputs(target_name = nrns.iloc[i].lhn, 
													target_body_id = nrns.iloc[i].body_id, 
													input_name = None)

		dendr_start_sec_seg = cell1.axon[measure_locs['dendr_start'][0]](measure_locs['dendr_start'][1])
		branch_out_sec_seg = cell1.axon[measure_locs['dendr_first_branch'][0]](measure_locs['dendr_first_branch'][1])
		curr_distance = h.distance(dendr_start_sec_seg, branch_out_sec_seg)

		imp = h.Impedance()
		imp.loc(dendr_start_sec_seg)
		imp.compute(transf_freq)	# starts computing transfer impedance @ freq 
		curr_transf_ratio_d_d1 = imp.ratio(branch_out_sec_seg)

		imp = h.Impedance()
		imp.loc(branch_out_sec_seg)
		imp.compute(transf_freq)	# starts computing transfer impedance @ freq 
		curr_transf_ratio_d1_d = imp.ratio(dendr_start_sec_seg)

		toA = {}
		toA.update(target_name = nrns.iloc[i].lhn, target_body_id = nrns.iloc[i].body_id,
					dist_dstart_dbranch = curr_distance,
					k_dstart_dbranch = curr_transf_ratio_d_d1,
					k_dbranch_dstart = curr_transf_ratio_d1_d)
		prim_dendr_per_nrn.append(toA)

	prim_dendr_per_nrn = pd.DataFrame(prim_dendr_per_nrn)

	date = datetime.today().strftime("%y-%m-%d")
	prim_dendr_per_nrn.to_csv(f'{date}_k_across_primary_dendrite.csv')

	return prim_dendr_per_nrn

def find_input_attrs(target_name = 'ML9', target_body_id = 542634516, weight_threshold = 10, 
								siz_sec = 569, siz_seg = 0.01, transf_freq = 20, 
								axon_sec = 609, axon_seg = 0.58,
								toPlot = False,
								param_set = 'pop_fit'):
	'''
		given the name and body ID of an existing LHN (which has a skeleton in the swc folder)
		instantiate Cell and use hemibrain to add all synapses above a threshold weight
		return DataFrame with EPSP and impedance attributes about each unique connection type
	'''
	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')
	### add neuprint call if the SWC doesn't exist inside

	# get swc straight from neuprint:
	#skel = fetch_skeleton(body = target_body_id, format = 'swc') # import skeleton

	if param_set == 'pop_fit':
		# biophysical parameters from our fits
		R_a = 350
		c_m = 0.6
		g_pas = 5.8e-5
		e_pas = -55 # one parameter left same in both, we used -55 in our fits
		syn_strength = 5.5e-5 # uS
	elif param_set == 'retr_local5_fit':
		R_a = 375 # ohm-cm # x3 from 125
		c_m = 1.2 # uF/cm^2
		g_pas = 4.4e-5 # S/cm^2 
		e_pas = -55 # mV
		syn_strength = 3.5e-5 # uS, peak synaptic conductance

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	conns = fetch_simple_connections(upstream_criteria = None, downstream_criteria = target_body_id, min_weight = weight_threshold)
	
	# get number of post-synapses on the target neuron
	try:
		target, r = fetch_neurons(target_body_id)
		target_syn_count = target.post[0]
	except:
		print('likely no internet connection')

	### instantiate synapses for each connection with weight > threshold
	all_conns = []
	for pre_name in set(conns.type_pre):
		# find all body IDs for this presynaptic neuron type
		pre_bodyIds = [conns.bodyId_pre[ind] for ind in range(len(conns.type_pre)) if conns.type_pre[ind] == pre_name]

		# get all synapse xyz locations for the body IDs in this neuron type (may be just 1 body ID)
		syn_locs = pd.DataFrame(columns = ['x_post', 'y_post', 'z_post'])
		for pre_id in pre_bodyIds:
			curr_syn_locs = fetch_synapse_connections(source_criteria = pre_id, target_criteria = target_body_id)
			syn_locs = syn_locs.append(curr_syn_locs[['x_post', 'y_post', 'z_post']])

		# add synapses onto skeleton
		curr_syns, netstim, netcons, num = cell1.add_synapses_xyz(xyz_locs = syn_locs, syn_strength = syn_strength)

		print('adding {} synapses from {} to {}'.format(str(num), pre_name, target_name))

		# measure uEPSP for connection at pSIZ and distal axon
		# activate the stim
		netstim.number = 1
		h.load_file('stdrun.hoc')
		x = h.cvode.active(True)
		v_siz = h.Vector().record(cell1.axon[siz_sec](siz_seg)._ref_v)
		v_axon = h.Vector().record(cell1.axon[axon_sec](axon_seg)._ref_v)
		if target_name == 'ML9' and target_body_id == 542634516:
			# for some reason this ML9's axon[0](1) is at the primary branch point
			v_soma = h.Vector().record(cell1.soma[0](0.5)._ref_v)	
		else:
			v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
		t = h.Vector().record(h._ref_t)                     				# Time stamp vector
		h.finitialize(-55 * mV)
		h.continuerun(40*ms)
		if toPlot:
			plt.plot(list(t), list(v_siz), label = 'siz')
			plt.plot(list(t), list(v_axon), label = 'axon')
			plt.plot(list(t), list(v_soma), label = 'soma')
			plt.legend(loc = 'upper right')
			plt.show()
		netstim.number = 0

		# measure rise time of EPSP at pSIZ
		t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)

		toAppend = {}
		toAppend.update(post_name = target_name, post_id = target_body_id,
							pre_name = pre_name, pre_id = str(pre_bodyIds)[1:-1],
							syns = curr_syns, syn_count = len(curr_syns),
							syn_budget = len(curr_syns) / target_syn_count,
							num_instances = len(pre_bodyIds), stim = [netstim], 
							uEPSP_siz = max(list(v_siz))+55, uEPSP_axon = max(list(v_axon))+55, 
							uEPSP_soma = max(list(v_soma))+55,
							t_10to90_siz = t_10to90_siz)
		all_conns.append(toAppend)

	# set up Impedance measurement class
	imp = h.Impedance()
	imp.loc(siz_seg, sec = cell1.axon[siz_sec])
	imp.compute(transf_freq)	# starts computing transfer impedance @ freq 

	### iterate through all connections and measure impedances
	for conn in all_conns:
		curr_syns = conn['syns']

		# iterate through each synapse in the connection
		syn_info = []
		for syn in curr_syns:
			# find Z_c = transfer impedance from synapse to siz_loc 
			curr_transf_imp = imp.transfer(syn.get_segment())
			# find Z_i = input impedance at synapse
			curr_input_imp = imp.input(syn.get_segment())
			# find distance from synapse to siz_loc
			curr_distance = h.distance(cell1.axon[siz_sec](siz_seg), syn.get_segment())
			# find voltage transfer ratio from synapse to siz_loc
			curr_transf_ratio = imp.ratio(syn.get_segment())

			# record individual synapse info
			toAppend = {}
			toAppend.update(dist_to_siz = curr_distance, Zc_to_siz = curr_transf_imp, 
							Zi = curr_input_imp, V_ratio = curr_transf_ratio)
			syn_info.append(toAppend)

		# update 'conn'
		conn.update(mean_dist_to_siz = mean([val['dist_to_siz'] for val in syn_info]),
						mean_Zc_to_siz = mean([val['Zc_to_siz'] for val in syn_info]),
						mean_Zi = mean([val['Zi'] for val in syn_info]),
						mean_V_ratio = mean([val['V_ratio'] for val in syn_info]))

		if toPlot:
			plt.scatter([val['dist_to_siz'] for val in syn_info], [val['Zc_to_siz'] for val in syn_info], 
						label = "{} w/ {} synapses".format(conn['pre_name'], str(conn['syn_count'])),
						alpha = 0.2)

	if toPlot:
		# plot synapse to SIZ distance vs transfer impedance
		plt.legend(loc = 'upper right')
		plt.xlabel('distance, synapse to SIZ (um)')
		plt.ylabel('transfer impedance (MOhm)')
		plt.title('inputs onto {} {}'.format(target_name, str(target_body_id)))
		#plt.show()

		plt.rcParams["figure.figsize"] = (10,10)
		all_conns = pd.DataFrame(all_conns)
		subset = pd.DataFrame(all_conns[['syn_count', 'uEPSP_siz', 'uEPSP_axon', 't_10to90_siz', 'mean_dist_to_siz', 'mean_Zc_to_siz', 'mean_Zi', 'mean_V_ratio']])
		sns.set_theme(style="ticks")
		sns.set(font_scale = 0.5)
		g = sns.pairplot(subset, height = 1, aspect = 0.8, corner = True)
		g.savefig('{}_{}_scatter_matrix.svg'.format(target_name, str(target_body_id)))

	return all_conns

def conn_attrs(target_neuron_file = 'LHN_list_siz_axon_locs.csv', weight_threshold = 3, transf_freq = 20,
					param_set = 'pop_fit'):
	'''
		for each neuron in a list (i.e. a list of LHNs), find information about its
		input connections, such as EPSP size, impedance measures, synapse counts, etc.

		possible inputs: target_neuron_file = 'KC_list_siz_axon_locs.csv' # list of ~23 hand picked KCs
						target_neuron_file = 'LHN_list_siz_axon_locs.csv' # list of our experimental-matched LHNs
	'''
	nrns = pd.read_csv(target_neuron_file)

	# iterate through each target neuron, concatenate relevant file info
	nrns_input_attrs = pd.DataFrame()
	for i in range(nrns.shape[0]):
		curr_input_attrs = find_input_attrs(target_name = nrns.iloc[i].lhn, target_body_id = nrns.iloc[i].lhn_id,
												weight_threshold = weight_threshold, transf_freq = transf_freq,
												siz_sec=nrns.iloc[i].siz_sec, siz_seg = nrns.iloc[i].siz_seg,
												axon_sec=nrns.iloc[i].axon_sec, axon_seg = nrns.iloc[i].axon_seg,
												param_set = param_set)

		nrns_input_attrs = nrns_input_attrs.append(curr_input_attrs)

	return nrns_input_attrs

### TODO 11/30: try above using different parameter sets and see if it decreases KC uEPSPs @ soma
### 
### update KC swc files and KC_list.csv file with Pasha's updates
### perhaps try soma[0](0.5) rather than axon[0](0.5) for soma recording? 
### focus on shuffling analysis since we might not end up using KC analysis
### redo shuffling analysis for a few more ePN inputs onto LHN
### redo shuffling expanding to more classes of inputs as target locs

### should also test how well the retr local5 params do at predicting the population

def analyze_attrs(n):
	'''
		some analysis code for generating graphs about correlations among
		attributes for each connection
	'''
	import pandas as pd

	### analyze LHN data
	n = pd.read_csv('conn_attrs_all_LHNs.csv')
	n_pn = n.loc[(n['pre_name'].str.contains('adPN')) | (n['pre_name'].str.contains('lPN'))] # excitatory PN inputs
	n_pn_out = n_pn.loc[~(n_pn['post_name'].str.contains('local'))]	# excitatory PN inputs onto LHONs
	n_pn_local = n_pn.loc[(n_pn['post_name'].str.contains('local'))] # excitatory PN inputs onto LHLNs

	plt.scatter(n_pn_out.syn_count, n_pn_out.mean_Zc_to_siz, color = 'red', label = 'inputs to LHONs')
	plt.scatter(n_pn_local.syn_count, n_pn_local.mean_Zc_to_siz, color = 'blue', label = 'inputs to LHLNs')
	plt.legend(loc='upper right')

	plt.xlabel('number of synapses in connection')
	plt.ylabel('avg. transfer impedance from synapses to SIZ (MOhm)')
	plt.show()

	# plot connected points for geodesic distance vs Z_c (or perhaps uEPSP/# synapses/budget?)
	for lhn_id in set(n_pn_out.post_id):
	    lhn = n_pn_out.query('post_id == @lhn_id')['post_name'].iloc[0]
	    plt.plot(n_pn_out.query('post_id==@lhn_id')['mean_dist_to_siz'], n_pn_out.query('post_id==@lhn_id')['mean_Zc_to_siz'], label = '{}-{}'.format(lhn, str(lhn_id)))

	# pairplot scatter matrix
	sub_n = pd.DataFrame(n[['syn_count', 'uEPSP_siz', 'uEPSP_axon', 't_10to90_siz', 'mean_dist_to_siz', 'mean_Zc_to_siz', 'mean_Zi', 'mean_V_ratio']])
	sns.set_theme(style="ticks")
	sns.set(font_scale = 0.6)
	g_n = sns.pairplot(sub_n, height= 1, aspect = 0.8, corner = True, plot_kws = {"s":3})
	g_n.savefig('all_LHNs_scatter_mat.svg')

	### analyze KC data
	n = pd.read_csv('conn_attrs_some_KCs.csv')
	n_pn = n.loc[(n['pre_name'].str.contains('adPN')) | (n['pre_name'].str.contains('lPN'))] # excitatory PN inputs
	# plot transf impedance vs syn count of each KC, can also do EPSP at SIZ / anything else
	for kc_id in set(n_pn.post_id):
		kc = n_pn.query('post_id == @kc_id')['post_name'].iloc[0]
		plt.plot(n_pn.query('post_id==@kc_id')['syn_count'], n_pn.query('post_id==@kc_id')['mean_Zc_to_siz'], 
					label = "{}-{}".format(kc, str(kc_id)))
	plt.legend(loc = 'upper right')

def shuffle_syn_locs_by_class(target_name = 'ML9', target_body_id = 542634516, weight_threshold = 3, 
								input_names = ['DP1m_adPN', 'DM4_adPN'], 
								siz_sec = 569, siz_seg = 0.0153, transf_freq = 20, 
								axon_sec = 609, axon_seg = 0.58,
								toPlot = False,
								conn_class = ['adPN', 'lPN'],
								run_count = 2):
	'''
		given a downstream (target_name) neuron, an upstream (conn_class) neuron class, and 
		one representative of that class (input_name), repeatedly shuffle the synaptic locations of
		that one representative, using the synapse locations of other neurons of that
		class as potential shuffle locations. 
		weight_threshold = 0: thus, candidate synapse locations can come from a connection type in conn_class
			with as little as this # of synapses
		
		TODO: in this class potentially add info on clustering within a connection and relative to other
				connections within the class

		parameters: conn_class: list of strings; 
								= ['all_dendritic'] then use results of conn_attrs to filter targets by 
										whether EPSP_SIZ > EPSP_axon, i.e. they are dendritic targeting
										NOTE: would likely include non-PN inputs
								= ['adPN', 'lPN'] to use ePN locations as targets to potentially shuffle to
								= ['dendritic_ePNs'] ONLY IF TARGET = local5 or local6
										candidate synapses to shuffle to are dendritic ePNs (adPN, lPNs)
										LHONs naturally have all ePNs as dendritic-targeting, but local 
										neurons also have ePNs that target the axon
					axon_sec: integer; a point in the distal (far out) axon to measure uEPSP at

		return: shuffle_results: dictionary of shuffle data for each input type:
						keys: string of input connection type; 
						value: [base_attrs dictionary, run_attrs dataframe (row per shuffle with uEPSP values)]
						run_attrs: pd.DataFrame: includes columns for t_trace_shuff, v_trace_shuff
		potentially: will need param: input_body_id = 635062078 (ML9)
	'''
	print('shuffling inputs onto {} {}'.format(target_name, str(target_body_id)))

	# instantiate target (post-synaptic) cell
	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')
	# biophysical parameters from our fits
	R_a = 350
	c_m = 0.6
	g_pas = 5.8e-5
	e_pas = -55 # one parameter left same in both, we used -55 in our fits
	syn_strength = 5.5e-5 # uS

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	# get number of post-synapses on the target neuron
	target = None
	print('finding # of post-synapses')
	while target is None:
		try:
			target, r = fetch_neurons(target_body_id)
		except:
			print('server access failure, repeating')
			pass
	target_syn_count = target.post[0]

	# identify all potential synaptic sites for connections in class (xyz coordinates)
	# could consider a Regex search here:
	# fetch_simple_connections(upstream_criteria = NC(type='.*adPN.*', regex = True), downstream_criteria = target_body_id, min_weight = 0)
	conns = None
	print('finding names of inputs')
	while conns is None:
		try:
			conns = fetch_simple_connections(upstream_criteria = None, downstream_criteria = target_body_id, min_weight = weight_threshold)
			#print(conns)
		except:
			print('server access failure, repeating')
			pass
	# find names of input neurons which are of the 'to place' input class
	if 'all_dendritic' in conn_class:
		# add all neuron types which have uEPSP at the SIZ bigger than uEPSP at the axon
		# equivalent, roughly, to all neuron types with uEPSPs 
		conn_attrs = pd.read_csv('conn_attrs_all_LHNs_with_smallInputs.csv')
		conn_attrs = conn_attrs.loc[(conn_attrs['post_name']==target_name) & (conn_attrs['post_id']==target_body_id)]
		nrns_in_class = []
		for row_ind in range(conn_attrs.shape[0]):
			if conn_attrs.iloc[row_ind]['uEPSP_siz'] > conn_attrs.iloc[row_ind]['uEPSP_axon']:
				nrns_in_class.append(conn_attrs.iloc[row_ind]['pre_name'])
		print("neurons in the all_dendritic class: {}".format(str(nrns_in_class)))
	elif 'local5' in target_name and 'dendritic_ePNs' in conn_class:
		l5_dendr, _ = find_dendr_inputs_local5_6()
		nrns_in_class = [l[0] for l in l5_dendr[target_body_id] if 'adPN' in l[0] or 'lPN' in l[0]]
	elif 'local6' in target_name and 'dendritic_ePNs' in conn_class:
		_, l6_dendr = find_dendr_inputs_local5_6()
		nrns_in_class = [l[0] for l in l6_dendr[target_body_id] if 'adPN' in l[0] or 'lPN' in l[0]]
	else:
		# add all neuron types which have 
		nrns_in_class = [pre_name for pre_name in list(filter(None, conns.type_pre)) if any(class_marker in pre_name for class_marker in conn_class)]
		print("neurons in the \'to place\' class: {}".format(str(nrns_in_class)))

	# iterate through neuron types in 'to place' class and add their synapse locations
	potent_syn_locs = pd.DataFrame(columns = ['type_pre', 'bodyId_pre', 'x_post', 'y_post', 'z_post'])
	# treat each unique connection type as one:
	for nrn_name in set(nrns_in_class):
		# find all body IDs for this presynaptic neuron type
		pre_bodyIds = [conns.bodyId_pre[ind] for ind in range(len(conns.type_pre)) if conns.type_pre[ind] == nrn_name]

		# get all synapse xyz locations for the body IDs in this neuron type (may be just 1 body ID)
		nrn_syn_count = 0
		curr_syn_locs = None
		# neuprint sometimes throws 502 server errors, try to catch them:
		print('retrieving postsynapse locations for input {}'.format(nrn_name))
		print('presynaptic body IDs: ', pre_bodyIds)
		num_failures = 0
		while curr_syn_locs is None:
			try:
				curr_syn_locs = fetch_synapse_connections(source_criteria = pre_bodyIds, target_criteria = target_body_id)
			except:
				print('server access failure, repeating')
				num_failures += 1
				pass
			if num_failures > 10:
				break
		if num_failures > 10:
			continue
		curr_syn_locs = curr_syn_locs[['bodyId_pre', 'x_post', 'y_post', 'z_post']]
		curr_syn_locs = curr_syn_locs.assign(type_pre = nrn_name)
		potent_syn_locs = potent_syn_locs.append(curr_syn_locs)
		nrn_syn_count += curr_syn_locs.shape[0]

		print('added pot. syn locs from type {}, {} insts., {} total syns'.format(nrn_name, str(len(pre_bodyIds)), 
																					str(nrn_syn_count)))

	# KNN to map each potential synapse location x, y, z (scaled x0.008) to the closest segment
	tree_coords = cell1.tree.loc[:, 'x':'z']
	syn_coords = potent_syn_locs.loc[:, 'x_post':'z_post'] / 125
	nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(tree_coords)
	distances, indices = nbrs.kneighbors(syn_coords)
	# indices: index in tree of closest section and point location to a synapse

	# produce dictionary of shuffle data for each input type:
	# keys: string of input connection type; 
	# value: [base_attrs dictionary, run_attrs dataframe (row per shuffle), 10 example uEPSP traces]
	shuffle_results = {}
	for input_name in input_names:

		# instantiate sites of baseline specified input connection onto skeleton
		input_syn_locs = potent_syn_locs.loc[potent_syn_locs.type_pre == input_name]
		input_bodyIds = [conns.bodyId_pre[ind] for ind in range(len(conns.type_pre)) if conns.type_pre[ind] == input_name]
		curr_syns, netstim, netcons, num = cell1.add_synapses_xyz(xyz_locs = input_syn_locs, syn_strength = syn_strength)
		print('adding {} synapses from {} to {}'.format(str(num), input_name, target_name))

		# measure uEPSP for connection at pSIZ and distal axon and soma
		netstim.number = 1 # activate stim
		h.load_file('stdrun.hoc')
		x = h.cvode.active(True)
		v_siz = h.Vector().record(cell1.axon[siz_sec](siz_seg)._ref_v)
		v_axon = h.Vector().record(cell1.axon[axon_sec](axon_seg)._ref_v)
		if target_name == 'ML9' and target_body_id == 542634516:
			# for some reason this ML9's axon[0](1) is at the primary branch point
			v_soma = h.Vector().record(cell1.soma[0](0.5)._ref_v)	
		else:
			v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
		t = h.Vector().record(h._ref_t)                     				# Time stamp vector
		h.finitialize(-55 * mV)
		h.continuerun(40*ms)
		if toPlot:
			plt.plot(list(t), list(v_siz), label = 'siz')
			plt.plot(list(t), list(v_axon), label = 'axon')
			plt.plot(list(t), list(v_soma), label = 'soma')
			plt.legend(loc = 'upper right')
			plt.show()
		netstim.number = 0 # de-activate stim
		# measure rise time of EPSP at pSIZ
		t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)

		# save attributes of baseline input connection
		base_input_attrs = {}
		base_input_attrs.update(post_name = target_name, post_id = target_body_id,
							pre_name = input_name, pre_id = str(input_bodyIds)[1:-1],
							syns = curr_syns, syn_count = len(curr_syns),
							syn_budget = len(curr_syns) / target_syn_count,
							num_instances = len(input_bodyIds), stim = [netstim], 
							uEPSP_siz = max(list(v_siz))+55, uEPSP_axon = max(list(v_axon))+55, 
							uEPSP_soma = max(list(v_soma))+55,
							t_10to90_siz = t_10to90_siz,
							t_trace_siz_base = list(t), v_trace_siz_base = list(v_siz))

		# repeatedly permute synapses to other potential locations, record new connection attributes
		print('commence {} shuffles for input {}'.format(str(run_count), input_name))
		run_attrs = []
		for i in range(run_count):
			# locations (rows in potent_syn_locs) to permute each synapse to
			permute_locs = random.sample(range(potent_syn_locs.shape[0]), len(curr_syns))

			# for each synapse, move it to the new location
			original_loc = []
			for j in range(len(curr_syns)):
				# save current location
				original_loc.append(curr_syns.object(j).get_segment())

				# find section and segment info of new shuffle location
				new_tree_ind = indices[permute_locs[j]]
				sec = int(cell1.tree.loc[new_tree_ind, 'sec'])
				i3d = cell1.tree.loc[new_tree_ind, 'i3d']	# the 3d point index on the section
				loc = cell1.axon[sec].arc3d(i3d) / cell1.axon[sec].L

				# move synapse to new location
				curr_syns.object(j).loc(cell1.axon[sec](loc))
				h.pop_section()

			# for the new synapse distribution
			# record geodesic distribution / input impedance distribution / transfer imp distr

			# simulate EPSP
			# measure uEPSP for connection at pSIZ and distal axon and soma
			netstim.number = 1 # activate stim
			h.load_file('stdrun.hoc')
			x = h.cvode.active(True)
			v_siz = h.Vector().record(cell1.axon[siz_sec](siz_seg)._ref_v)
			v_axon = h.Vector().record(cell1.axon[axon_sec](axon_seg)._ref_v)
			if target_name == 'ML9' and target_body_id == 542634516:
				# for some reason this ML9's axon[0](1) is at the primary branch point
				v_soma = h.Vector().record(cell1.soma[0](0.5)._ref_v)	
			else:
				v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
			t = h.Vector().record(h._ref_t)                     				# Time stamp vector
			h.finitialize(-55 * mV)
			h.continuerun(40*ms)
			netstim.number = 0 # de-activate stim
			# measure rise time of EPSP at pSIZ
			t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)

			# save attributes of permuted input connection
			toAppend = {}
			toAppend.update(permute_ind = i, 
							uEPSP_siz = max(list(v_siz))+55, uEPSP_axon = max(list(v_axon))+55, 
							uEPSP_soma = max(list(v_soma))+55,
							t_trace_siz_shuff = list(t), v_trace_siz_shuff = list(v_siz))
			run_attrs.append(toAppend)

			if i % 100 == 1:
				print('permutation {}: uEPSP @ SIZ = {}'.format(str(i), str(toAppend['uEPSP_siz'])))

			# reset synaptic locations back to their old locations
			for j in range(len(curr_syns)):
				curr_syns.object(j).loc(original_loc[j])

		run_attrs = pd.DataFrame(run_attrs)

		# plot histogram of uEPSP (at SIZ, soma) sizes
		# plot overlay of various geodesic, Z_input, Z_c histograms

		shuffle_results[input_name] = [base_input_attrs, run_attrs]
		
	return shuffle_results

def test_shuffle_count():
	'''
		test number of runs needed to converge on stable uEPSP distribution when doing
		multiple runs of shuffling
	'''

	run_lengths = [2, 4, 6, 8]

	shuffle_run = {}

	for rc in run_lengths:
		b, r = shuffle_syn_locs_by_class(run_count = rc)
		shuffle_run[rc] = r

	fig, axs = plt.subplots(nrows = 2, ncols = 2)
	axs = axs.reshape(-1)	# allows us to linearly iterate through subplots
	i = 0
	for key, val in shuffle_run.items():
		axs[i].hist(val.uEPSP_siz, bins = 20)
		axs[i].set_title('shuffle synapses {} times'.format(str(key)))
		axs[i].axvline(b['uEPSP_siz'], color = 'red', linestyle = 'dashed')
		i += 1
	axs[0].set_ylabel('frequency')
	axs[-1].set_xlabel('uEPSP @ SIZ (mV)')
	plt.show()

	return shuffle_run

def fig_example_shuff_L1(input_PN = 'DP1m_adPN'):
	'''L1 483716037 example shuffle histogram
		just has one PN input 
		NOTE: to plot a different PN-LHN input, change siz and axon locations'''
	shuffles = shuffle_syn_locs_by_class(input_names = [input_PN], run_count = 500,
											target_name = 'L1', target_body_id = 483716037, 
											siz_sec=10, siz_seg = 0.996269,
											axon_sec=183, axon_seg = 0.5,
											conn_class = ['adPN', 'lPN'],
											weight_threshold = 3)

	# plot histogram of shuffled uEPSP amplitudes, with baseline uEPSP amplitude marked
	fig, axs = plt.subplots(nrows = 1, ncols = 1, constrained_layout = True, figsize = (2,2))
	for key, val in shuffles.items():
		#axs.hist(val[1].uEPSP_siz, bins = 30, density = True, color = 'grey') 
		# matplotlib histogram density plotting doesn't work for some dumb reason: https://github.com/matplotlib/matplotlib/issues/15603
		# need to do it manually:
		cts, edges = np.histogram(val[1].uEPSP_siz, bins = 30)
		axs.bar((edges[1:]+edges[:-1])/2, [c/sum(cts) for c in cts], width=np.diff(edges)[0],
					color = 'grey', alpha = 0.4)
		#axs.set_title('{}, {}s{}i.'.format(str(key), str(val[0]['syn_count']), str(val[0]['num_instances'])))
		#axs.axvline(val[0]['uEPSP_siz'], color = 'red', linestyle = 'dashed', label = 'baseline')
		# show baseline EPSP amplitude
		axs.scatter(val[0]['uEPSP_siz'], 0.12, color = 'black', marker = 'v', s = 20)
	axs.set(ylabel = 'frequency', xlabel = 'uEPSP at pSIZ (mV)',
			yticks = np.arange(0, 0.13, 0.025),
			xticks = np.arange(round(min(edges)-0.05, 1), round(max(edges),1)+0.05, 0.3))
	axs.spines['top'].set_visible(False), axs.spines['right'].set_visible(False)
	#axs.legend(frameon = False, prop = {'size':7},
	#			bbox_to_anchor=(0., 1.02, 1., .102), loc='lower left',
    #       		ncol=2, mode="expand", borderaxespad=0.)
	#fig.subplots_adjust(wspace=0, hspace=0)
	plt.savefig('figs\\example_shuff_L1_hist.svg', format = 'svg')
	#axs.set_title('{}, {}s{}i.'.format(str(key), str(val[0]['syn_count']), str(val[0]['num_instances'])))
	#plt.suptitle('target: {} {}, s=synapses, i=instances'.format(target_name, str(target_body_id)))
	plt.show()

	# plot 1 baseline and 10 example traces for uEPSPs measured at the SIZ
	fig, ax = plt.subplots(1,1, figsize=(2,2))
	t_b, v_b = shuffles[input_PN][0]['t_trace_siz_base'], shuffles[input_PN][0]['v_trace_siz_base']
	ax.plot(t_b, v_b, color = 'black', ls = 'dashed')
	for i in range(10):
		t_s, v_s = shuffles[input_PN][1].iloc[i]['t_trace_siz_shuff'], shuffles[input_PN][1].iloc[i]['v_trace_siz_shuff']
		ax.plot(t_s, v_s, color = 'grey', alpha = 0.3)
	#ax[0].xaxis.set_visible(False), ax[0].yaxis.set_visible(False)
	#ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	ax.set(xlim = [0.5, 10])
	add_scalebar(ax = ax, xlen=5, ylen=1, xlab=' ms', ylab=' mV', loc = 'lower right')
	plt.savefig('figs\\example_shuff_L1_traces.svg')
	plt.show()

	return axs, shuffles

# shuffling hypotheses:
# - is it mainly small inputs that have uEPSPs << mean shuffled uEPSPs? (bc less synapses=more clustering)
# - for these small inputs, is there something systematic about their Strahler order (i.e. very low)
#		moreover, are the inputs spread across many distal branches (i.e. not coincidentally low ordered)
def shuffle_inputs_on_targets(target_neuron_file = 'LHN_list_siz_axon_locs.csv', run_count = 500, 
							to_shuffle_weight_threshold = 10, to_place_weight_threshold = 3,
							to_shuffle_class = ['adPN', 'lPN'], to_place_class = ['all_dendritic']):
	'''
		NOTE: if running for different to_shuffle or to_place classes, change title of output CSV

		for each target neuron in a list (i.e. a list of LHNs):
			find instances within specified classes of inputs = "to shuffle" (with >threshold synapses), 
			shuffle their synapse locations using another specified 
			set of potential input class synapse locations = "to place" (>threshold synapses) 
			using shuffle_syn_locs method
		params: to_shuffle_class = ['adPN', 'lPN'] for excitatory PNs
								 = ['adPN', 'lPN', 'vPN'] if including inhibitory PNs
				to_place_class	 = ['all_dendritic'] then use results of conn_attrs to filter targets by 
										whether EPSP_SIZ > EPSP_axon, i.e. they are dendritic targeting
										NOTE: would likely include non-PN inputs
								 = ['adPN', 'lPN'] to use ePN locations as targets to potentially shuffle to

		if an input onto the target also happens to have multiple other instances of itself (i.e. sister PNs)
			synapsing onto the target, its instantiation (i.e. when synapses are added onto the target) will include
			the weaker, sub-weight threshold connections
			even if multiple instances of a connection type have a total synapse count >threshold, if each 
			individual instance is <threshold than it won't be identified as a 'to_shuffle' neuron
	'''
	start_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')

	nrns = pd.read_csv(target_neuron_file)

	all_shuffle_data = {}
	# for each target neuron in our list, shuffle its to_shuffle_class inputs
	for i in range(nrns.shape[0]):
		target_name = nrns.iloc[i].lhn
		target_body_id = nrns.iloc[i].lhn_id
		if to_place_class == 'all_dendritic' and 'local' in target_name:
			continue
		# find input neurons:
		conns = None
		print('preparing to find input neurons for {} {}'.format(target_name, str(target_body_id)))
		while conns is None:
			try:
				conns = fetch_simple_connections(upstream_criteria = None, downstream_criteria = target_body_id, 
											min_weight = to_shuffle_weight_threshold)
			except:
				print('server access failure, repeating')
				pass
		# filter input neurons by whether they are in to_shuffle_class: 
		ePN_inputs = [pre for pre in list(filter(None, conns.type_pre)) if any(class_type in pre for class_type in to_shuffle_class)]
		print(str(ePN_inputs))
		ePN_inputs = list(set(ePN_inputs)) # treat each input "type" as simultaneously active (i.e. sister PNs)
		print('# sig. inputs: {}, # rows: {}'.format(str(len(ePN_inputs)), 
						str(int(np.ceil(len(ePN_inputs)/3)))))
		# for each input neuron, function shuffle its synapses using to_place_class as candidate locations 
		# returns dictionary w/ keys as input neuron names, values as [base_attrs dictionary, run_attrs dataframe (row per shuffle)]
		if len(ePN_inputs) > 0:
			shuffles = shuffle_syn_locs_by_class(input_names = ePN_inputs, run_count = run_count,
												target_name = target_name, target_body_id = target_body_id, 
												siz_sec=nrns.iloc[i].siz_sec, siz_seg = nrns.iloc[i].siz_seg,
												axon_sec=nrns.iloc[i].axon_sec, axon_seg = nrns.iloc[i].axon_seg,
												conn_class = to_place_class,
												weight_threshold = to_place_weight_threshold)
		
			plt.rcParams["figure.figsize"] = (6,3)
			fig, axs = plt.subplots(nrows = int(np.ceil(len(ePN_inputs)/3)), ncols = 3,
										constrained_layout = True)
			axs = axs.reshape(-1)	# allows us to linearly iterate through subplots
			i = 0
			for key, val in shuffles.items():
				axs[i].hist(val[1].uEPSP_siz, bins = 30)
				axs[i].set_title('{}, {}s{}i.'.format(str(key), str(val[0]['syn_count']), str(val[0]['num_instances'])))
				axs[i].axvline(val[0]['uEPSP_siz'], color = 'red', linestyle = 'dashed')
				i += 1
			axs[0].set_ylabel('frequency')
			axs[-1].set_xlabel('uEPSP @ SIZ (mV)')
			#plt.subplots_adjust(wspace = 0.3, hspace = 0.3)
			plt.suptitle('target: {} {}, s=synapses, i=instances'.format(target_name, str(target_body_id)))
			#plt.show()
			#plt.tight_layout()
			plt.savefig('shuffles\\{}-{}.png'.format(target_name, str(target_body_id)), 
							format = 'png', bbox_inches='tight', dpi = 300)
		else:
			print('{} {}: no inputs w/ > threshold syns to shuffle'.format(target_name, str(target_body_id)))

		all_shuffle_data[(target_name, target_body_id)] = shuffles

	# save out some tabular data
	base_v_shuff_EPSP = []
	all_shuffles = [[lhn_info, shuffle_info] for lhn_info, shuffle_info in all_shuffle_data.items()]
	for lhn in all_shuffles:
		for pn, shuff in lhn[1].items():
			lhn_name, lhn_id = lhn[0][0], lhn[0][1]
			pn_name = pn
			base_EPSP = shuff[0]['uEPSP_siz']
			shuff_EPSP_med = np.median(shuff[1].uEPSP_siz)
			shuff_EPSP_mea = np.mean(shuff[1].uEPSP_siz)
			shuff_EPSP_std = np.std(shuff[1].uEPSP_siz)
			syn_count = shuff[0]['syn_count']
			num_instances = shuff[0]['num_instances']
			toA = {}
			toA.update(lhn_name = lhn_name, lhn_id = lhn_id, pn_name = pn_name, base_EPSP = base_EPSP, 
						shuff_EPSP_med = shuff_EPSP_med, shuff_EPSP_mea = shuff_EPSP_mea, 
						shuff_EPSP_std = shuff_EPSP_std, 
						syn_count = syn_count, num_instances = num_instances)
			base_v_shuff_EPSP.append(toA)
	base_v_shuff_EPSP = pd.DataFrame(base_v_shuff_EPSP)

	# base_v_shuff.to_csv('20-12-04_shuff_ePN2ePN_LHN_750.csv')

	end_time = datetime.now().strftime('%y-%m-%d-%H:%M:%S')
	print("start time: {}, end time: {}".format(start_time, end_time))

	return all_shuffle_data, base_v_shuff_EPSP

def shuffle_dendritic_ePNs_on_local5_6(target_neuron_file = 'LHN_list_siz_dendr_locs',
										run_count = 750):
	''' TODO: deprecate and merge into above function prior to running final version

	shuffle dendrite-targeting ePNs on local5, local6 using other
		dendrite targeting ePN synapses as candidate locations
		it basically recapitulates the above function (shuffling all ePNs on all LHNs), 
		but specifically for local5 and 6 using their manually identified dendrite targets

		returns: all_shuffle_data: dictionary; keys are 
				 base_v_shuff_EPSP: dataframe with base EPSP and median shuffled EPSP columns

	'''
	nrns = pd.read_csv(target_neuron_file)
	nrns_l5 = nrns.loc[(nrns.lhn=='local5')]
	nrns_l6 = nrns.loc[(nrns.lhn=='local6')]

	# perform shuffles on local5
	all_shuffle_data = {}
	for i, row in nrns_l5.iterrows():
		target_name, body_id = row.lhn, row.lhn_id
		siz_sec, siz_seg = row.siz_sec, row.siz_seg
		axon_sec, axon_seg = row.axon_sec, row.axon_seg

		l5_dendr, _ = find_dendr_inputs_local5_6(min_syn_count = 3)
		nrns_in_class = [l[0] for l in l5_dendr[body_id] if 'adPN' in l[0] or 'lPN' in l[0]]
		print('input names to shuffle: ', nrns_in_class)
		shuffle_results = shuffle_syn_locs_by_class(target_name = target_name, target_body_id = body_id, 
								weight_threshold = 0, 
								input_names = nrns_in_class, 
								siz_sec = siz_sec, siz_seg = siz_seg, transf_freq = 0, 
								axon_sec = axon_sec, axon_seg = axon_seg,
								toPlot = False,
								conn_class = ['dendritic_ePNs'],
								run_count = run_count)
		all_shuffle_data[(target_name, body_id)] = shuffle_results

	# perform shuffles on local6
	all_shuffle_data = {}
	for i, row in nrns_l6.iterrows():
		target_name, body_id = row.lhn, row.lhn_id
		siz_sec, siz_seg = row.siz_sec, row.siz_seg
		axon_sec, axon_seg = row.axon_sec, row.axon_seg

		_, l6_dendr = find_dendr_inputs_local5_6(min_syn_count = 3)
		nrns_in_class = [l[0] for l in l6_dendr[body_id] if 'adPN' in l[0] or 'lPN' in l[0]]
		print('input names to shuffle: ', nrns_in_class)
		shuffle_results = shuffle_syn_locs_by_class(target_name = target_name, target_body_id = body_id, 
								weight_threshold = 0, 
								input_names = nrns_in_class, 
								siz_sec = siz_sec, siz_seg = siz_seg, transf_freq = 0, 
								axon_sec = axon_sec, axon_seg = axon_seg,
								toPlot = False,
								conn_class = ['dendritic_ePNs'],
								run_count = run_count)
		all_shuffle_data[(target_name, body_id)] = shuffle_results

	# save out some tabular data
	base_v_shuff_EPSP = []
	all_shuffles = [[lhn_info, shuffle_info] for lhn_info, shuffle_info in all_shuffle_data.items()]
	for lhn in all_shuffles:
		for pn, shuff in lhn[1].items():
			lhn_name, lhn_id = lhn[0][0], lhn[0][1]
			pn_name = pn
			base_EPSP = shuff[0]['uEPSP_siz']
			shuff_EPSP_med = np.median(shuff[1].uEPSP_siz)
			shuff_EPSP_mea = np.mean(shuff[1].uEPSP_siz)
			shuff_EPSP_std = np.std(shuff[1].uEPSP_siz)
			syn_count = shuff[0]['syn_count']
			num_instances = shuff[0]['num_instances']
			toA = {}
			toA.update(lhn_name = lhn_name, lhn_id = lhn_id, pn_name = pn_name, base_EPSP = base_EPSP, 
						shuff_EPSP_med = shuff_EPSP_med, shuff_EPSP_mea = shuff_EPSP_mea, 
						shuff_EPSP_std = shuff_EPSP_std, 
						syn_count = syn_count, num_instances = num_instances)
			base_v_shuff_EPSP.append(toA)
	base_v_shuff_EPSP = pd.DataFrame(base_v_shuff_EPSP)

	base_v_shuff.to_csv('21-02-01_shuffle_dendritic_ePNs_on_local5_6_750.csv')

	return shuffle_results, base_v_shuff_EPSP

def fig_base_v_shuffle_uEPSPs(recent_shuff_path = '20-12-04_shuff_ePN2ePN_LHN_750.csv',
								dendr_thresh = 0.9):
	'''scatter baseline uEPSPs vs median shuffled uEPSPs
		**include dendrite-targeted ePNs, i.e. all inputs to LHONs and some to LHLNs

		dendr_thresh: float, 0<value<1; corresponds to % of inputs that need to be 
						dendritic for the PN to be classified as dendritic'''

	shuff_df = pd.read_csv('shuffles\\20-12-04_shuff_ePN2ePN_LHN_750.csv')

	shuff_out = shuff_df.loc[~shuff_df['lhn_name'].str.contains('local')]
	shuff_local = shuff_df.loc[shuff_df['lhn_name'].str.contains('local')]

	# next: scatter all in shuff_out, also those PNs in shuff_local whose inputs are mostly dendritic
	fig, ax = plt.subplots(1,1,figsize = (2,2))
	ax.scatter(shuff_out.base_EPSP, shuff_out.shuff_EPSP_med, color = 'grey', alpha = 0.5)
	ax.plot([0, 11], [0, 11], color = 'black', ls = 'dashed')
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	ax.set(xlabel = 'baseline uEPSP (mV)', ylabel = 'median shuffled uEPSP (mV)',
			xlim = [0,11.5], ylim = [0,11.5])

	# also plot dendritic inputs onto local neurons:
	# as of Feb 1: wait for fixing the dendritic inputs to local5/6
	'''
	l5_dendr, l6_dendr = find_dendr_inputs_local5_6(dendr_thresh)
	l5_shuffs = shuff_local.loc[shuff_local['lhn_name']=='local5']
	l6_shuffs = shuff_local.loc[shuff_local['lhn_name']=='local6']
	for i, row in l5_shuffs.iterrows():
		if row.pn_name in [l[0] for l in l5_dendr[row.lhn_id]]:
			ax.scatter(row.base_EPSP, row.shuff_EPSP_med, color = 'grey', alpha = 0.5)
	for i, row in l6_shuffs.iterrows():
		if row.pn_name in [l[0] for l in l6_dendr[row.lhn_id]]:
			ax.scatter(row.base_EPSP, row.shuff_EPSP_med, color = 'grey', alpha = 0.5)
	'''

	plt.savefig('figs\\base_v_shuffle_uEPSPs.svg')
	plt.show()


def find_dendr_inputs_local5_6(dendr_thresh = 0.9, min_syn_count = 0):
	'''output the inputs that exceed the dendr_thresh percentage of synapses onto the 
		local5 and local6 dendrite'''

	local5_dendr_inputs = {}
	local6_dendr_inputs = {}

	local5_ins = pd.read_csv('21-02-01 local5 inputs dendr vs axon.csv', index_col=[0,1])
	for body_id, subdf in local5_ins.groupby(level='body_id'):
		perc_dendritic = (subdf.iloc[0] / (subdf.iloc[0]+subdf.iloc[1])) # returns Series, index are input names
		# also filter based on total # of synapses in the connection
		local5_dendr_inputs[body_id] = [(lhn, perc) for (lhn, perc) in perc_dendritic.iteritems() \
											if perc > dendr_thresh and sum(subdf[lhn]) > min_syn_count]

	local6_ins = pd.read_csv('21-02-01 local6 inputs dendr vs axon.csv', index_col=[0,1])
	for body_id, subdf in local6_ins.groupby(level='body_id'):
		perc_dendritic = (subdf.iloc[0] / (subdf.iloc[0]+subdf.iloc[1])) # returns Series, index are input names
		local6_dendr_inputs[body_id] = [(lhn, perc) for (lhn, perc) in perc_dendritic.iteritems() \
											if perc > dendr_thresh]

	dendr_inputs = {'local5': local5_dendr_inputs, 'local6': local6_dendr_inputs}
	return local5_dendr_inputs, local6_dendr_inputs

def analyze_shuffs():
	'''
		some code to analyze shuffling EPSPs
	'''

	b = pd.read_csv('20-12-06_shuff_ePN2ePNiPN_LHN_1000.csv')
	b_out = b.loc[~b['lhn_name'].str.contains('local')]
	c = pd.read_csv('20-12-04_shuff_ePN2ePN_LHN_750.csv')
	c_out = c.loc[~c['lhn_name'].str.contains('local')]

	# scatter of median shuffled vs baseline

	# read the local5 section Jamie wrote, and all the other things he wrote and sent, incl. the transfer resistance 
	# thing on slack
	# start working on that figure

	# visualize z_scored amount of 
	#plt.scatter(b_out.syn_count, (b_out.base_EPSP - b_out.shuff_EPSP_med) / b_out.shuff_EPSP_std)

	# plot z-score (and best fit lines) of baseline vs shuffled EPSPs
	# for ePN to just ePN vs ePN to ePN+iPN on LHONs
	z= np.polyfit(b_out.syn_count, (b_out.base_EPSP - b_out.shuff_EPSP_med) / b_out.shuff_EPSP_std, 1)
	p = np.poly1d(z)
	plt.plot(b_out.syn_count, p(b_out.syn_count), c = 'tab:blue', ls = 'dashed', label = 'target ePN+iPN fit')
	plt.scatter(b_out.syn_count, (b_out.base_EPSP - b_out.shuff_EPSP_med) / b_out.shuff_EPSP_std, c = 'tab:blue', label = 'target ePN+iPN', s = 2.5)

	z= np.polyfit(c_out.syn_count, (c_out.base_EPSP - c_out.shuff_EPSP_med) / c_out.shuff_EPSP_std, 1)
	p = np.poly1d(z)
	plt.plot(c_out.syn_count, p(c_out.syn_count), c = 'tab:orange', ls = 'dashed', label = 'target ePN fit')
	plt.scatter(c_out.syn_count, (c_out.base_EPSP - c_out.shuff_EPSP_med) / c_out.shuff_EPSP_std, c = 'tab:orange', label = 'target ePN', s = 2.5)

	plt.axhline(2, color = 'red', linestyle = 'dashed')
	plt.axhline(-2, color = 'red', linestyle = 'dashed')

	plt.legend(loc = 'upper right')
	plt.xlabel('synapse count')
	plt.ylabel('z-score of baseline EPSP vs shuffled EPSPs')

def add_hh(downstream_of):
	# use to visualize the subtree of a particular section, i.e.
	# when trying to identify the dendritic proximal section
	# then go into Distributed Mech -> Manager -> HomogeneousMech -> hh
	global m
	m = h.MechanismType(0)
	m.select('hh')
	for sec in cell1.axon[downstream_of].subtree():
		m.make(sec=sec)
def remove_hh():
	for sec in h.allsec():
		m.remove(sec=sec)

def assign_LHLN_branch_points():
	'''read in Jamie's labelled Point Nodes and map onto NEURON swc nodes'''

	JJ_labels = pd.read_csv('axonDendriteNodes LHLN 20210112.csv')

	lhn_branch_points = {}	
	for i, row in JJ_labels.iterrows():
		if not pd.isna(row['axon start']):
			name, body_id = row['target_name'], row['target_body_id']
			a, d, a_1, d_1 = row['axon start'], row['dendrite start'], row['axon first branch'], row['dendrite first branch']

			lhn_branch_points[(name, body_id)] = assign_SWC_PointNo_to_NEURON_tree(target_name = name, 
													target_body_id = body_id, nodes_to_map = [d,d_1,a,a_1])

	# dictionary: key -- (lhln name, lhln id), value -- list of lists, each contained 
	# list structure -- [node id, section, segment]; dendrite, dendrite branch out, axon, axon branch out
	return lhn_branch_points

def move_LHLN_swc_files():
	''' 21-03-03: move LHLN files from Jamie's dropbox to my SWC file folder
	UPDATE: code written in 21-03-03 Jupyter notebook
	'''
	JJ_labels = pd.read_csv('C:\\Users\\Tony\\Dropbox\\synapse manuscript\\data\\axonDendriteNodes - all LHNs - 20210216 JJ.csv', 
					header = 1, nrows=85, usecols=list(range(9)))


def LHN_SWCPointNo_to_NEURON():
	''' 21-02-16: given Jamie's branch point IDs, return a CSV of SWC rows mapped to 
		NEURON section and segments

		21-03-06: update, added LHLN body IDs (with mixed inputs) to JJ_labels
	'''

	JJ_labels = pd.read_csv('C:\\Users\\Tony\\Dropbox\\synapse manuscript\\data\\axonDendriteNodes - all LHNs+LHLNs - 20210216 JJ.csv', 
					header = 1, nrows=85, usecols=list(range(9)))

	lhn_branch_points = {}	
	lhn_SWC_to_NEURON = []
	for i, row in JJ_labels.iterrows():
		if not pd.isna(row['axon start']):
			name, body_id = row['lhn_name'], row['lhn_body_id']
			a, d, a_1, d_1 = row['axon start'], row['dendrite start'], row['axon first branch'], row['dendrite first branch']

			lhn_branch_points[(name, body_id)] = assign_SWC_PointNo_to_NEURON_tree(target_name = name, 
													target_body_id = body_id, nodes_to_map = [d,d_1,a,a_1])
			d_swc_row, d_sec, d_seg = lhn_branch_points[(name, body_id)][0]
			d1_swc_row, d1_sec, d1_seg = lhn_branch_points[(name, body_id)][1]
			a_swc_row, a_sec, a_seg = lhn_branch_points[(name, body_id)][2]
			a1_swc_row, a1_sec, a1_seg = lhn_branch_points[(name, body_id)][3]

			toA = {'lhn': name, 'body_id': body_id,
				'swc_dendr_start': d, 'swc_dendr_first_branch': d_1, 'swc_ax_start': a, 'swc_ax_first_branch': a_1, 
				'N_dendr_start_sec': d_sec, 'N_dendr_start_seg': d_seg, 
				'N_dendr_first_branch_sec': d1_sec, 'N_dendr_first_branch_seg': d1_seg, 
				'N_ax_start_sec': a_sec, 'N_ax_start_seg': a_seg, 
				'N_ax_first_branch_sec': a1_sec, 'N_ax_first_branch_seg': a1_seg
			}
			lhn_SWC_to_NEURON.append(toA)
	lhn_SWC_to_NEURON = pd.DataFrame(lhn_SWC_to_NEURON)

	date = datetime.today().strftime("%y-%m-%d")
	lhn_SWC_to_NEURON.to_csv(f'{date}_LHN_SWCPointNo_to_NEURON.csv')

	return lhn_SWC_to_NEURON

def assign_SWC_PointNo_to_NEURON_tree(target_name = 'local6', target_body_id = 417186656,
									nodes_to_map = [241,1737,341,1745]):

	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')

	# get swc text file
	headers = ['PointNo', 'Label', 'X', 'Y', 'Z', 'Radius', 'Parent']
	raw_swc = pd.read_csv(swc_path, sep=' ', skiprows=4, names=headers)

	# instantiate NEURON cell object
	cell1, curr_syns, netstim, netcons, num = visualize_inputs(target_name=target_name, target_body_id=target_body_id,
												input_name = None)

	# map rows from text file to section+segments in NEURON object
	tree_coords = cell1.tree.loc[:, 'x':'z']
	nbrs = NearestNeighbors(n_neighbors=1, algorithm='auto').fit(tree_coords)
	pointno_to_sec = [] # values of [PointNo, NEURON section, NEURON segment]
	for node in nodes_to_map:
		node_coords = raw_swc.loc[raw_swc.PointNo==node][['X','Y','Z']]
		distances, indices = nbrs.kneighbors(node_coords)	# index is closest row in cell1.tree to PointNo
		node_section = int(cell1.tree.iloc[indices[0][0]]['sec'])
		node_i3d = int(cell1.tree.iloc[indices[0][0]]['i3d'])
		node_segment = cell1.axon[node_section].arc3d(node_i3d) / cell1.axon[node_section].L
		print(f'PointNo {str(node)} maps to section {str(node_section)} w/ dist {str(distances[0][0])}')
		
		pointno_to_sec.append([node, node_section, node_segment])

	return pointno_to_sec

def fix_Jamie_first_branch_labels(toFixPath = '21-03-06_LHN_SWCPointNo_to_NEURON.csv',
							wrongThresh = 0.1):
	'''21-02-21: Jamie often labelled the dendr_first_branch and ax_first_branch on points
	that were going into the arbor. Going through 21-02-16_LHN_SWCPointNo_to_NEURON.csv to try
	and fix the points where the segment < 0.1, i.e. most likely the segment is wrongly inside
	the arbor and at the very start of a section. Proper branch-out segments should be at the very
	end of their sections. 

	21-03-06: re-running with the LHLNs included
	currently only fixing dendr_first_branch and ax_first_branch
	'''
	nrns = pd.read_csv(toFixPath)
	fix_nrns = nrns

	for i, row in nrns.iterrows():

		cell1, curr_syns, netstim, netcons, num = visualize_inputs(target_name=row.lhn, 
													target_body_id=row.body_id,
													input_name = None)

		if row.N_dendr_first_branch_seg < wrongThresh:
			new_sec = re.findall(r'\d+', str(cell1.axon[row.N_dendr_first_branch_sec].parentseg().sec))[1]
			new_seg = cell1.axon[row.N_dendr_first_branch_sec].parentseg().x
			if int(new_sec)==0:
				print('problem with parsing dendr first branch for', row.lhn, row.body_id)
			fix_nrns.loc[i, 'N_dendr_first_branch_sec'] = new_sec
			fix_nrns.loc[i, 'N_dendr_first_branch_seg'] = new_seg

		if row.N_ax_first_branch_seg < wrongThresh:
			new_sec = re.findall(r'\d+', str(cell1.axon[row.N_ax_first_branch_sec].parentseg().sec))[1]
			new_seg = cell1.axon[row.N_ax_first_branch_sec].parentseg().x
			if int(new_sec)==0:
				print('problem with parsing ax first branch for', row.lhn, row.body_id)
			fix_nrns.loc[i, 'N_ax_first_branch_sec'] = new_sec
			fix_nrns.loc[i, 'N_ax_first_branch_seg'] = new_seg

	date = datetime.today().strftime("%y-%m-%d")
	fix_nrns.to_csv(toFixPath.split('.')[0] + '_fix_first_branch.csv')

	return fix_nrns

def visualize_inputs(target_name = 'local5', target_body_id = 5813105722, input_name = 'VA6_adPN', 
						get_neuprint_swc = True,
						syn_locs = pd.DataFrame(), all_input_min_weight = 3):
	'''
		given a downstream (target_name) neuron + ID, an upstream neuron, instantiate the
		downstream neuron, and potentially also instantiate synapses
		(potentially pulling from neuprint) for the sake of visualization
		utility function useful for rapidly looking at a neuron and its inputs
		i.e. go to ModelView in the GUI to see the morphology, synapse locations, etc.

		NOTE: preset model parameters (from Nov 2020 parameter fit) can be changed

		Parameters:
		---
		target_name (string): name of neuron
		target_body_id (int): body ID of neuron. Function will look for SWC files in the path
			`swc/[target_name]-[target_body_id].swc where the program is executed from. 
			If the file is not present and `get_neuprint_swc` is true, will attempt to pull the SWC
			file from neuprint directly using `fetch_skeleton`
		input_name (string): name/type of upstream pre-synaptic neuron in neuprint, i.e. "VA6_adPN"
			will use neuprint's `fetch_simple_connections` and `fetch_synapse_connections` to 
			find all the body IDs corresponding to the neuron type and pull in their synapse locations
			if "all_inputs", then will read in the synapses locations for all
			upstream neurons to the target neuron
			if `None`, then will skip adding synapses
		syn_locs (pd.DataFrame): must include x, y, z columns
			allows one to preload the synaptic locations
		all_input_min_weight (int): if `input_name` is 'all_inputs', then will find all input synapses
			onto the target neuron which have total synapse count in the connection >=`all_input_min_weight` 

		Returns
		-------
		cell1 (Cell class object): custom class defined in `pop_mc_model`
			can query specific segments of the cell via `cell1.axon[section number](segment value)
			where segment value between 0 and 1
		curr_syns (HOC List): list of HOC Exp2Syn objects (synapses w/ double exponential kinetics)
			added to the cell
		netstim (HOC NetStim object): NetStim object, can be changed to specify time when connections in 
			`netcons` are activated
		netcons (HOC List): list of HOC NetCon objects, one per synapse, that connects the Exp2Syn 
			objects to cell1 and specify the conductance/weight (in microSiemens) of synapses
		num (int): number of synapses added
		pre_body_ids (pd.Series): pandas series of the presynaptic (upstream) identity of each synapse
			should be trivially `input_name` if the neuron type is specified, but if the value of 
			`input_name` is 'all_inputs', then this is useful to know which neuron the synapse comes from
			*index within `pre_body_ids` should correspond to index within `curr_syns`
		pre_nrn_info (pd.DataFrame): rows for each unique input body ID returned by neuprint's 
			`fetch_neurons`, columns include body ID, neuron type, presynaptic neuron total input and
			output synapses, etc. 
			(most relevant for `input_name`='all_inputs')

		TODO: turn the output variables into a dictionary (allows for more modular addition of output
			variables, without modifying all downstream code to accept more outputs)

		EX: target_name = 'CML2', target_body_id = 572988717, input_name = 'VA6_adPN'
			target_name = 'CML2', target_body_id = 698180486, input_name = 'VA6_adPN'
			target_name = 'CML2', target_body_id = 696795331, input_name = 'VA6_adPN'
			target_name = 'ML9', target_body_id = 542634516, input_name = 'DP1m_adPN'
			target_name = 'ML9', target_body_id = 573329304, input_name = 'DM1_lPN'
			target_name = 'ML9', target_body_id = 573337611, input_name = 'DM1_lPN'
			target_name = 'L12', target_body_id = 452664348, input_name = 'VA1d_adPN' # 16+7 synapses
			target_name = 'L12', target_body_id = 421957711, input_name = 'DP1m_adPN'
			target_name = 'L12', target_body_id = 603681826, input_name = 'DP1m_adPN'
			target_name = 'L11', target_body_id = 360578457, input_name = 'DM1_lPN' # 18 
			target_name = 'L11', target_body_id = 297921527, input_name = 'DM1_lPN'
			target_name = 'L11', target_body_id = 572988605, input_name = 'DM1_lPN'
			target_name = 'L13', target_body_id = 544007573, input_name = 'VA2_adPN'
			target_name = 'L13', target_body_id = 793702856, input_name = 'VA2_adPN'
			target_name = 'L15', target_body_id = 422307542, input_name = 'DC1_adPN'
			target_name = 'L15', target_body_id = 5813009429, input_name = 'DC1_adPN'
			target_name = 'V2', target_body_id = 1037510115, input_name = 'VL2a_adPN'
			target_name = 'V2', target_body_id = 5813016204, input_name = 'VL2a_adPN'
			target_name = 'V2', target_body_id = 852302504, input_name = 'VL2a_adPN'
			target_name = 'V3', target_body_id = 883338122, input_name = 'VL2a_adPN'
			target_name = 'V3', target_body_id = 917450071, input_name = 'VL2a_adPN'
			target_name = 'ML3', target_body_id = 483017681, input_name = 'VL2p_adPN'
			target_name = 'ML3', target_body_id = 543321179, input_name = 'VL2p_adPN'
			target_name = 'ML3', target_body_id = 573683438, input_name = 'VL2p_adPN'
			target_name = 'CML2', target_body_id = 572988717, input_name = None # NO VA6 synapses
			target_name = 'ML8', target_body_id = 548872750, input_name = 'DM1_lPN' # synapse between 2 tufts
			target_name = 'ML8', target_body_id = 5813089504, input_name = 'DM1_lPN'
			target_name = 'ML8', target_body_id = 571666400, input_name = 'DM1_lPN'
			target_name = 'L1', target_body_id = 575806223, input_name = 'DM1_lPN'
			target_name = 'L1', target_body_id = 483716037, input_name = 'DM1_lPN'
	'''
    
	global cell1, curr_syns, netstim, netcons, num
    
	print(f'visualizing target: {target_name} {target_body_id}, input: {input_name}')

	# instantiate target (post-synaptic) cell
	swc_path = f"swc\\{target_name}-{target_body_id}.swc"
	if f"{target_name}-{target_body_id}.swc" not in os.listdir('swc'):
		if get_neuprint_swc:
			print(f'fetching neuprint swc for {target_name} {target_body_id}')
			from neuprint import fetch_skeleton
			swc_str = fetch_skeleton(body = target_body_id, format = 'swc') # import skeleton
			with open(swc_path, 'w') as new_swc_path:
				new_swc_path.write(swc_str)
		else:
			print('no SWC found, need to upload into folder `swc`')
			return

	# biophysical parameters from our fits
	R_a = 350 # ohm-cm
	c_m = 0.6 # uF/cm^2
	g_pas = 5.8e-5 # S/cm^2
	e_pas = -55 # mV one parameter left same in both, we used -55 in our fits
	syn_strength = 5.5e-5 # uS

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	# get number of post-synapses on the target neuron
	try:
		target, r = fetch_neurons(target_body_id)
		target_syn_count = target.post[0]
	except:
		print('likely no internet connection')

	# add all input synaptic site locations
	if input_name: # skip if input_name == None
		if not syn_locs.empty: # if synapse locs are pre-loaded, then use those locations
			pass # synapse locs are pre-loaded
		elif input_name == 'all_inputs': # find all incoming synapses
			min_weight = all_input_min_weight
			print(f'fetching all input synapse locations >{min_weight} synapses')
			syn_locs = fetch_synapse_connections(target_criteria = target_body_id, min_total_weight = min_weight)
		else:
			conns = fetch_simple_connections(upstream_criteria = input_name, downstream_criteria = target_body_id)
			pre_bodyIds = conns.bodyId_pre
			print(pre_bodyIds)
			syn_locs = fetch_synapse_connections(source_criteria = pre_bodyIds, target_criteria = target_body_id)
		curr_syns, netstim, netcons, num = cell1.add_synapses_xyz(xyz_locs = syn_locs, syn_strength = syn_strength)
		# read info about presynaptic neurons
		if 'bodyId_pre' in syn_locs.columns: 
			pre_body_ids = syn_locs.bodyId_pre
			pre_nrn_info, _ = fetch_neurons(pre_body_ids)
		else:
			pre_body_ids = [np.nan] * len(curr_syns)
			pre_nrn_info = pd.DataFrame()
			print('need to pass in presynaptic body IDs')
		print('adding {} synapses from {} to {}; budget = {}'.format(str(num), input_name, target_name, str(num/target_syn_count)))
		if target_name == 'local5' and target_body_id == 5813105722:
			# dendrite initial section is axon[195] for un-retraced local5
			num_in_dendr = 0
			for syn in curr_syns:
				if str(syn.get_segment()).partition('(')[0] in [str(val) for val in cell1.axon[195].subtree()]:
					num_in_dendr += 1
			print('proportion synapses in dendrite: {}'.format(str(num_in_dendr/num)))
	else:
		print('not adding synapses')
		curr_syns, netstim, netcons, num = None, None, None, None

	# access a random section
	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)
	v_siz = h.Vector().record(cell1.axon[0](0.5)._ref_v)

	return cell1, curr_syns, netstim, netcons, num, pre_body_ids, pre_nrn_info

def visualize_2PNs():
	''' 21-02-22 from Jamie: DP1m adPN and one DA1 lPN (so, for example, bodyIds 722817260 and 635062078).
	 a plot of transfer resistance for those two body IDs would be sufficient 
	 (showing entire cell, not just dendrite arbor)

	 722817260 seems to have soma cut off
	'''
	visualize_inputs(target_name='DP1m_adPN', target_body_id = 635062078, input_name = None)
	visualize_inputs(target_name='DA1_lPN', target_body_id = 754534424, input_name = None)

	visualize_inputs(target_name='DA1_lPN', target_body_id = 722817260, input_name = None)

def visualize_custom_var(prox_sec, custom_var):
	''' plot custom variable within dummy variable 
		then can superimpose custom variable onto ShapePlot
		prox_sec = collect all impedance attrs downstream of this section
		custom_var = which variable to ShapePlot
			transfer / ratio / input
	'''
	global inps, ratios, transf, gd 	# for plotting

	m = h.MechanismType(0)
	m.select('var')
	for sec in h.allsec():
		m.make(sec=sec)
	# measure impedance
	imp = h.Impedance()
	imp.loc(0.5, sec= cell1.axon[prox_sec])
	imp.compute(0)

	# assign custom variable (i.e. input impedance) to the dummy variable
	for sec in h.allsec():
		for seg in sec:
			seg.zin_var = eval(f'imp.{custom_var}(seg)') # mystery is why zin_var is the attribute (not `var`)
	# then open Shape Plot and visualize! can also set it up w pyplot

	inps, ratios, transf, gd = [], [], [], []
	# assign input impedance to the dummy variable
	for sec in cell1.axon[prox_sec].subtree():
		for seg in sec:
			inps.append(imp.input(seg))
			ratios.append(imp.ratio(seg))
			gd.append(h.distance(cell1.axon[prox_sec](0.5), seg))
			transf.append(imp.transfer(seg))

	return inps, ratios, transf, gd

def fig_dendrite_linearity():
	'''plotting sub-figures for case study of impedance properties'''
	# fig_5 plot: (dendritic linearity) L1 horizontal plot
	fig, axs = plt.subplots(1,3, figsize=(6, 1.5), sharey=True)
	plt.rcParams.update({'font.size': 9})
	rock = sns.color_palette('rocket_r', as_cmap=True)
	axs[0].scatter(inps, gd, c=inps, s=1, cmap=rock, vmin=0, vmax = 4000)
	axs[0].set(xlim=[0,4500], xlabel = 'input resistance (MOhm)', ylabel = 'distance from pSIZ (\u03BCm)')
	#axs[0].set_xlabel(fontsize = 9), axs[0].set_ylabel(fontsize = 9)
	axs[1].scatter(ratios, gd, c=ratios, s=1, cmap=rock, vmin=0, vmax=1)
	axs[1].set(xlim=[0,1], xlabel = 'voltage transfer ratio')
	axs[2].scatter(transf, gd, c=transf, s=1, cmap=rock, vmin=0, vmax=1700)
	axs[2].set(xlim=[0,1600], xlabel = 'transfer resistance (MOhm)')
	for i in range(3):
	    axs[i].spines["top"].set_visible(False), axs[i].spines["right"].set_visible(False)
	for ax in [axs[0], axs[1], axs[2]]:
	    for item in ([ax.title, ax.xaxis.label, ax.yaxis.label] + ax.get_xticklabels() + ax.get_yticklabels()):
	        item.set_fontsize(9)
	plt.savefig('L1_dendr_imp_measures.svg', format = 'svg')

def fig_local5_dendr_ax_linrty(target_name='local5', target_body_id=5813105722, savefig = False):
	'''passive norm plots for local5 (zc vs gd with lines fit)'''
	# DEPRECATED:
	'''
	#custom_var = 'input'
	#visualize_inputs(target_name = 'local5', target_body_id = 5813105722, input_name = None)
	# visualize_custom_var returns inps, ratios, transf, gd
	#i_d, r_d, t_d, g_d = visualize_custom_var(prox_sec = 195, custom_var = custom_var) # dendrite 
	#i_a, r_a, t_a, g_a = visualize_custom_var(prox_sec = 996, custom_var = custom_var) # axons
	#fig_imp_props_vs_gd(i_d, r_d, t_d, g_d,
	#					i_a, r_a, t_a, g_a,
	#					target_name = 'local5', i_range=[0,3500], t_range=[0,800])
	#plt.show() # to generate and save the figure'''


	# params: target_name, target_body_id, dendr_sec, dendr_seg, branchout_sec = None, branchout_seg = None
	# return: gd, zi, zc, k, branchout_dist
	g_d, i_d, t_d, r_d, branchout_dist_d = subtree_imp_props(target_name, target_body_id, 195, 0.1,
												196, 0.99)
	g_a, i_a, t_a, r_a, branchout_dist_a = subtree_imp_props(target_name, target_body_id, 998, 0.01,
												1002, 0.99)
	fig, axs = plt.subplots(1,1, figsize = (3,2))
	scatter_size = 0.3
	rock = sns.color_palette('rocket_r', as_cmap=True)
	t_range = [0, 800] # 0 to largest value of transfer resistance

	axs.scatter([g for g in g_d], t_d, c=t_d, s=scatter_size, cmap=rock, vmin=t_range[0], vmax = t_range[1])
	axs.scatter(g_a, t_a, c=t_a, s=scatter_size, cmap=rock, vmin=t_range[0], vmax = t_range[1])
	axs.set(ylim=t_range, ylabel = 'transfer resistance (M\u03A9)', xlabel = 'distance from pSIZ (\u03BCm)')
	axs.spines['top'].set_visible(False), axs.spines['right'].set_visible(False)

	# fit line to dendritic (_d_) arbor
	g_d_arbor = [g for g in g_d if g > branchout_dist_d]
	t_d_arbor = [z for ind, z in enumerate(t_d) if g_d[ind] > branchout_dist_d]
	d_arbor_fit = stats.linregress(g_d_arbor, t_d_arbor)
	#d_arbor_range = np.arange(-1*max(g_d)-20, -1*branchout_dist_d, 1)
	d_arbor_range = np.arange(branchout_dist_d, max(g_d)+20, 1)
	axs.plot(d_arbor_range, d_arbor_fit.intercept + d_arbor_range*d_arbor_fit.slope, 
				color='black', ls = 'dashed', 
				label = f'dendritic linear fit slope = {str(round(d_arbor_fit.slope,2))}')
	# dendritic slope = -0.97 as of early Feb

	# fit line to axonal (_a_) arbor
	g_a_arbor = [g for g in g_a if g > branchout_dist_a]
	t_a_arbor = [z for ind, z in enumerate(t_a) if g_a[ind] > branchout_dist_a]
	a_arbor_fit = stats.linregress(g_a_arbor, t_a_arbor)
	a_arbor_range = np.arange(branchout_dist_a, max(g_a)+20, 1)
	axs.plot(a_arbor_range, a_arbor_fit.intercept + a_arbor_range*a_arbor_fit.slope, 
				color='grey', alpha=0.6, ls = 'dashed',
				label = f'axonal linear fit slope = {str(round(a_arbor_fit.slope,2))}')
	axs.legend(frameon = False, prop = {'size': 7})
	# axonal slope = -0.58 as of early Feb

	if savefig:
		plt.savefig('figs\\local5_dendr_ax_linrty.svg')

	plt.show()

def fig_imp_props_vs_gd(target_name = 'L1', i_range=[0,4000], t_range=[0,1700], toSave=False,
						scatter_size = 0.3):
	'''
		fig 5 (dendritic linearity) L1 vertical plot:
		t_range - array of two ints: 0 to largest value of transfer resistance
					used for color map of transfer resistance vs gd scatter
	'''
	visualize_inputs(target_name = 'L1', target_body_id = 483716037, input_name = None)
	custom_var = 'transfer' # only needed bc of way code was previously designed, can deprecate
	i_d, r_d, t_d, g_d = visualize_custom_var(prox_sec = 205, custom_var = custom_var) # dendrite 
	i_a, r_a, t_a, g_a = visualize_custom_var(prox_sec = 11, custom_var = custom_var) # axons

	g_d, i_d, t_d, r_d, _ = subtree_imp_props('L1', 483716037, 205, 0.5)
	g_a, i_a, t_a, r_a, _ = subtree_imp_props('L1', 483716037, 11, 0.5)

	# get mEPSP sizes
	# TODO: potentially try using the arbor branch out point?!
	dendr_mEPSP_df = probe_mEPSPs(target_name = 'L1', target_body_id = 483716037, input_name = 'all_inputs',
					siz_sec = 205, siz_seg = 0.5, all_input_min_weight = 0)
	ax_mEPSP_df = probe_mEPSPs(target_name = 'L1', target_body_id = 483716037, input_name = 'all_inputs',
					siz_sec = 11, siz_seg = 0.5, all_input_min_weight = 0)
	dendr_mEPSP_df = dendr_mEPSP_df.loc[dendr_mEPSP_df.ax_v_dendr=='dendritic']
	ax_mEPSP_df = ax_mEPSP_df.loc[ax_mEPSP_df.ax_v_dendr=='axonal']

	#  run after running visualize_custom_var to collect lists
	fig, axs = plt.subplots(4,1, figsize=(2, 8), sharex=True)
	plt.rcParams.update({'font.size': 9})
	rock = sns.color_palette('rocket_r', as_cmap=True)
	axs[0].scatter([-1*g for g in g_d], i_d, c=i_d, s=scatter_size, cmap=rock, vmin=i_range[0], vmax = i_range[1])
	axs[0].scatter(g_a, i_a, c=i_a, s=scatter_size, cmap=rock, vmin=i_range[0], vmax = i_range[1])
	axs[0].set(ylim=i_range, ylabel = 'input resistance (M\u03A9)')
	#axs[0].set_xlabel(fontsize = 9), axs[0].set_ylabel(fontsize = 9)
	axs[1].scatter([-1*g for g in g_d], r_d, c=r_d, s=scatter_size, cmap=rock, vmin=0, vmax=1)
	axs[1].scatter(g_a, r_a, c=r_a, s=scatter_size, cmap=rock, vmin=0, vmax=1)
	axs[1].set(ylim=[0,1], ylabel = 'voltage transfer ratio')
	axs[2].scatter([-1*g for g in g_d], t_d, c=t_d, s=scatter_size, cmap=rock, vmin=t_range[0], vmax = t_range[1])
	axs[2].scatter(g_a, t_a, c=t_a, s=scatter_size, cmap=rock, vmin=t_range[0], vmax = t_range[1])
	axs[2].set(ylim=t_range, ylabel = 'transfer resistance (M\u03A9)')

	# mEPSP plot vs gd (using siz sec as 10 results in slightly off geodesic distances)
	axs[3].scatter([-1*g for g in dendr_mEPSP_df.dist_to_siz], dendr_mEPSP_df.mEPSP_siz,
					c=dendr_mEPSP_df.mEPSP_siz, s=scatter_size, cmap=rock, vmin=0, vmax=0.40)
	axs[3].scatter(ax_mEPSP_df.dist_to_siz, ax_mEPSP_df.mEPSP_siz,
					c=ax_mEPSP_df.mEPSP_siz, s=scatter_size, cmap=rock, vmin=0, vmax=0.40)
	axs[3].set(ylim=(0,0.4), ylabel='mEPSP amplitude (mV)', xlabel = 'distance from pSIZ (\u03BCm)')

	for i in range(4):
		axs[i].spines["top"].set_visible(False), axs[i].spines["right"].set_visible(False)
	# this font thing seems to do nothing
	for ax in [axs[0], axs[1], axs[2], axs[3]]:
		for item in [ax.title, ax.xaxis.label, ax.yaxis.label]:
			item.set_fontsize(9)
		for item in (ax.get_xticklabels() + ax.get_yticklabels()):
			item.set_fontsize(8)

	if toSave:
		plt.savefig(f'figs\\{target_name}_imp_props_vs_gd.svg', format = 'svg')

	return g_d, g_a, dendr_mEPSP_df, ax_mEPSP_df

def destroying_passive_norm():

	visualize_inputs(target_name = 'L1', target_body_id = 483716037, input_name = None)



def fig_zi_vs_k_L1():
	# plot z_i vs k for L1:

	inps, ratios, transf, gd = visualize_inputs(target_name = 'L1', 
									target_body_id = 483716037, input_name = None)

	fig, axs = plt.subplots(1,1, figsize=(2, 2))
	# then can plot any variables against each other, i.e.:
	axs.scatter(ratios, inps, c=transf, cmap=rock, s=1, vmin=0, vmax=1700)  # color is voltage transfer resistance
	axs.set(xlabel='voltage transfer ratio', ylabel='input resistance (MOhm)',
			xlim=[0,1], ylim=[0,7500])
	# inverse fit:
	inv_fit = lambda x: 5585 * 0.2/x
	# calculate R^2
	r_ss= sum([(z_i - inv_fit(ratios[k_ind]))**2 for k_ind, z_i in enumerate(inps)]) # residual sum of squares
	mean_inps = mean(inps)
	t_ss = sum([(z_i - mean_inps)**2 for z_i in inps])
	Rsqu = 1 - r_ss/t_ss
	axs.plot(np.arange(0.15, 1.05, 0.05), [inv_fit(x) for x in np.arange(0.15, 1.05, 0.05)], color = 'orange', 
				ls = 'dashed', label = f'$R^2={{{round(Rsqu,3)}}}$')
	axs.legend(loc='upper right', frameon = False, prop={'size':7})
	axs.spines["top"].set_visible(False), axs.spines["right"].set_visible(False)
	plt.tight_layout()
	plt.savefig('figs\\zi_vs_k_L1.svg')

def plot_imp_on_dendrites(custom_var = 'transfer', var_min = 0, var_max = 1700):
	'''plot z_c/z_i/k onto the 2D morphology of a neuron
		NOTE: change colormap by altering nrn.def file in C:/nrn/lib/
		NOTE: the code is NOT executable as a function, copy paste into command line
	'''

	custom_var = 'transfer'
	var_min = 0
	var_max = 1700

	custom_var = 'ratio'
	var_min = 0
	var_max = 1

	custom_var = 'input'
	var_min = 0
	var_max = 4000

	visualize_inputs(target_name = 'L1', target_body_id = 483716037, input_name = None)
	i_d, r_d, t_d, g_d = visualize_custom_var(prox_sec = 205, custom_var = custom_var) # dendrite 
	i_a, r_a, t_a, g_a = visualize_custom_var(prox_sec = 11, custom_var = custom_var) # axons
	ps = h.PlotShape(True)
	# L1: to orient into hemibrain 'coordinates' (dorsal up, facing brain)
	# ps.rotate(0,0,0,275*(np.pi/180),-15*(np.pi/180),0)
	ps.scale(var_min, var_max)
	ps.variable('zin_var')

	ax = ps.plot(plt, cmap = cm.hsv) # try rainbow colormap
	plt.show()

	ps = h.PlotShape(True)
	ps.scale(var_min, var_max)
	ps.scale(var_min, var_max)

	''' code to print RGB values for magma colormap (close to seaborn's rocket), to plug
		into a shape.cm file for nrn.def to read
	rock = sns.color_palette('rocket_r', as_cmap=True)
	for i in np.arange(0, 1.01, 0.05):
		rgb = [str(round(val*256)) for val in rock(i)]
		print('\t'.join(rgb[:3]))

	To generate a vertical standalone colorbar:
	plt.figure(figsize=(0.1,1))
	plt.imshow([[0,1]], cmap=sns.color_palette('rocket_r', as_cmap=True))
	plt.gca().set_visible(False)
	cax = plt.axes([0.1,0.1,0.05,0.6])
	plt.colorbar(orientation='vertical', cax=cax)

	plt.figure(figsize=(1,0.1)) # horizontal colorbar
	plt.imshow([[0,1]], cmap=sns.color_palette('rocket_r', as_cmap=True))
	plt.gca().set_visible(False)
	cax = plt.axes([0.1,0.5,0.6,0.05])
	plt.colorbar(orientation='horizontal', cax=cax)
	'''

def allLHNs_imp_props_subtree_perc_whole_neuron(target_neuron_file = 'LHN_list_siz_dendr_locs.csv',
		subtree = 'dendrite', toPlot = True):
	'''
		for a given neuron, find the percentage of [impedance property] space that
		the arbor (post branch-out point of axon or dendrite) spans compared to the 
		rest of the neuron, where [imp prop] 
		includes input resistance, voltage transfer ratio, or transfer resistance

		NOTE: skips CML2 because of its truncated cross-hemispheric connection, and one of the local2's
			that Jamie didn't label

		TODO: recompute after changes to local6 (already made), and V2, L13 (need to be made, see Notion)

	subtree - string: 'dendrite' or 'axon'; which arbor to compare to the rest of the neuron
	'''

	nrns = pd.read_csv(target_neuron_file)

	imp_props_perc_df = pd.DataFrame()
	for i, r in nrns.iterrows():
		if pd.notna(r['dendr_branch_out_sec']) and r['lhn'] != 'CML2' and r['lhn_id'] != 5813055963:
			# dendritic side props:
			gd_d, zi_d, zc_d, k_d, _ = subtree_imp_props(r['lhn'], r['lhn_id'], int(r['prox_dendr_sec']), float(r['prox_dendr_seg']))
			# axonal side props:
			gd_a, zi_a, zc_a, k_a, _ = subtree_imp_props(r['lhn'], r['lhn_id'], int(r['prox_ax_sec']), float(r['prox_ax_seg']))
			# dendritic arbor (post branch-out point) props:
			gd_da, zi_da, zc_da, k_da, _ = subtree_imp_props(r['lhn'], r['lhn_id'], int(r['dendr_branch_out_sec']), float(r['dendr_branch_out_seg']))
			# axonal arbor (post branch-out point) props:
			gd_aa, zi_aa, zc_aa, k_aa, _ = subtree_imp_props(r['lhn'], r['lhn_id'], int(r['ax_branch_out_sec']), float(r['ax_branch_out_seg']))

			# find range of zi, zc, and k values across entire neuron
			zi_range = np.abs(max(zi_d+zi_a) - min(zi_d+zi_a))
			zc_range = np.abs(max(zc_d+zc_a) - min(zc_d+zc_a))
			k_range = np.abs(max(k_d+k_a) - min(k_d+k_a))
			# find range of zi, zc, and k values across dendritic arbor
			zi_range_da = np.abs(max(zi_da) - min(zi_da))
			zc_range_da = np.abs(max(zc_da) - min(zc_da))
			k_range_da = np.abs(max(k_da) - min(k_da))
			# find range of zi, zc, and k values across axonal arbor
			zi_range_aa = np.abs(max(zi_aa) - min(zi_aa))
			zc_range_aa = np.abs(max(zc_aa) - min(zc_aa))
			k_range_aa = np.abs(max(k_aa) - min(k_aa))

			toAppend = {'lhn': r['lhn'], 'lhn_id': r['lhn_id'],
						'zi_range': zi_range, 'zc_range': zc_range, 'k_range': k_range,
						'zi_range_da': zi_range_da, 'zc_range_da': zc_range_da, 'k_range_da': k_range_da,
						'zi_range_aa': zi_range_aa, 'zc_range_aa': zc_range_aa, 'k_range_aa': k_range_aa,
						'dendr_arbor_%_zi': zi_range_da/zi_range, 'dendr_arbor_%_zc': zc_range_da/zc_range,
						'dendr_arbor_%_k': k_range_da/k_range,
						'ax_arbor_%_zi': zi_range_aa/zi_range, 'ax_arbor_%_zc': zc_range_aa/zc_range,
						'ax_arbor_%_k': k_range_aa/k_range}
			imp_props_perc_df = imp_props_perc_df.append(toAppend, ignore_index = True)

	date = datetime.today().strftime("%y-%m-%d")
	imp_props_perc_df.to_csv(f'{date} allLHNs_imp_props_subtree_perc_whole_neuron.csv')

	if toPlot:
		ax = sns.stripplot(data=imp_props_perc_df[['dendr_arbor_%_zi', 'dendr_arbor_%_k', 'dendr_arbor_%_zc']])
		plt.show()

	return imp_props_perc_df

def fig_imp_prop_range_subtree_perc_whole_neuron(preload = True):
	if preload:
		i_df = pd.read_csv('21-02-09 allLHNs_imp_props_subtree_perc_whole_neuron.csv')
	else:
		i_df = allLHNs_imp_props_subtree_perc_whole_neuron(toPlot = False)

	# input resistance plot (zi)
	fig, ax = plt.subplots(figsize=(2,2))
	ax = sns.stripplot(data=i_df[['zi_range', 'zi_range_aa', 'zi_range_da']], color= 'green')
	ax.set(ylabel = 'input resistance range (M\u03A9)', ylim = (0, None),
				xticklabels = ['full \nneuron', 'axon \narbor', 'dendrite \narbor'])
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	plt.savefig('figs\\zi_range_subtree_perc_whole_neuron.svg')
	plt.show()

	# transfer ratio plot (k)
	fig, ax = plt.subplots(figsize=(2,2))
	ax = sns.stripplot(data=i_df[['k_range', 'k_range_aa', 'k_range_da']], color= 'blue')
	ax.set(ylabel = 'transfer ratio range', ylim = (0, 1),
				xticklabels = ['full \nneuron', 'axon \narbor', 'dendrite \narbor'])
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	plt.savefig('figs\\k_range_subtree_perc_whole_neuron.svg')
	plt.show()

	# transfer resistance plot (zc)
	fig, ax = plt.subplots(figsize=(2,2))
	ax = sns.stripplot(data=i_df[['zc_range', 'zc_range_aa', 'zc_range_da']], color= 'red')
	ax.set(ylabel = 'transfer resistance range (M\u03A9)', ylim = (0, None),
				xticklabels = ['full \nneuron', 'axon \narbor', 'dendrite \narbor'])
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	plt.savefig('figs\\zc_range_subtree_perc_whole_neuron.svg')
	plt.show()


def fig_allLHNs_dendr_imp_props(target_neuron_file = 'LHN_list_siz_dendr_locs.csv', toPlot = 'zc_v_gd',
							downsample = False, downsample_by = 12, 
							align_branch_out = True, save_out = False, fit_line = True,
							plot_raw_pts = False):
	'''
		across LHNs, plot input resistance vs transfer ratio for dendritic segments
		we only iterate over dendritic subtrees here, as specified by 'prox_dendr_sec' in the csv
		
		toPlot = 'zi_v_k' or 'zc_v_gd'
		target_neuron_file = 'LHN_list_siz_axon_locs.csv' doesn't include dendritic branch out pts
															and has fewer neurons (less clutter?)
		align_branch_out: aligns branch out point to x-axis (geodesic dist)
		fit_line: fit and plot a straight line to the arbor points
	'''
	nrns = pd.read_csv(target_neuron_file)

	iters = 0

	lhns_colormap = {}
	import matplotlib
	rainbow = matplotlib.cm.get_cmap('hsv')
	for i, lhn in enumerate(nrns.lhn.unique()):
		lhns_colormap[lhn] = rainbow(i * 1/len(nrns.lhn.unique()))

	lhns_plotted = []
	arbor_fits = []
	if toPlot == 'zc_v_gd': sz = (3,2)
	if toPlot == 'zi_v_k': sz = (2,2)
	fig, ax = plt.subplots(1, 1, figsize=sz)
	for i, row in nrns.iterrows():
		if pd.notna(row['prox_dendr_sec']):

			target_name, target_body_id = row['lhn'], row['lhn_id']

			# capture initial dendritic section, and branch out point of arbor
			#prox_dendr_secs = [int(val) for val in row['prox_dendr_sec'].split(', ')]
			prox_dendr_secs = int(row['prox_dendr_sec'])
			#prox_dendr_segs = [float(val) for val in row['prox_dendr_seg'].split(', ')]
			prox_dendr_segs = float(row['prox_dendr_seg'])
			dendr_sec, dendr_seg = prox_dendr_secs, prox_dendr_segs
			branchout_sec, branchout_seg = None, None
			if pd.notna(row['dendr_branch_out_sec']):
				branchout_sec, branchout_seg = int(row['dendr_branch_out_sec']), row['dendr_branch_out_seg']

			# currently only look into one of the dendritic sections (if multiple arbors)
			gd, zi, zc, k, branchout_dist = subtree_imp_props(target_name, target_body_id, dendr_sec, dendr_seg,
												branchout_sec, branchout_seg)
			if not branchout_dist:
				branchout_dist = 0
			# add code to realign zc_v_gd plots to the dendritic branch out points
			if align_branch_out and toPlot=='zc_v_gd':
				gd = [val-branchout_dist for val in gd]

			# for zc_v_gd, fit a straight line to the dendritic arbor 
			if toPlot=='zc_v_gd' and fit_line:
				print('fitting line')
				gd_arbor = [g for g in gd if g > 0]
				zc_arbor = [z for ind, z in enumerate(zc) if gd[ind] > 0]
				try:
					arbor_fit = stats.linregress(gd_arbor, zc_arbor)
				except:
					print('fit failed, gd and zc are: ', gd_arbor, zc_arbor)
				toAppend = {'lhn': target_name, 'lhn_id': target_body_id, 
								'fit_type': 'arbor', 'fit_vars': 'zc_v_gd',
								'slope': arbor_fit.slope, 'intercept': arbor_fit.intercept,
								'r^2': arbor_fit.rvalue**2}
				arbor_fits.append(toAppend)
				# dendritic initial section
				gd_dis = [g for g in gd if g < 0]
				zc_dis = [z for ind, z in enumerate(zc) if gd[ind] < 0]
				if len(gd_dis)>0:
					DIS_fit = stats.linregress(gd_dis, zc_dis)
					toAppend = {'lhn': target_name, 'lhn_id': target_body_id, 
									'fit_type': 'DIS', 'fit_vars': 'zc_v_gd',
									'slope': DIS_fit.slope, 'intercept': DIS_fit.intercept,
									'r^2': DIS_fit.rvalue**2}
					arbor_fits.append(toAppend)
				#coeffs = np.polyfit(gd_arbor, zc_arbor, 1)
				#arbor_fit = np.poly1d(coeffs)
			# for zi_v_k, fit an inverse curve to the entire scatter
			if toPlot=='zi_v_k' and fit_line:
				print('fitting inverse curve')
				#inv_coeff = np.interp(0.5, k, zi) * 0.5
				inv_coeff = mean([zi_i*k_i for zi_i, k_i in zip(zi, k)])
				print(inv_coeff)
				inv_fit = lambda x: inv_coeff/x
				# calculate R^2
				r_ss= sum([(z_i - inv_fit(k[k_ind]))**2 for k_ind, z_i in enumerate(zi)]) # residual sum of squares
				mean_zi = mean(zi) # calculate just once for speedups
				t_ss = sum([(z_i - mean_zi)**2 for z_i in zi])
				Rsqu = 1 - r_ss/t_ss
				toAppend = {'lhn': target_name, 'lhn_id': target_body_id, 
								'fit_type': 'dendritic arbor', 'fit_vars': 'zi_v_k',
								'inv_coeff': inv_coeff,
								'r^2': Rsqu}
				arbor_fits.append(toAppend)
			
			if downsample:
				ds_len = int(np.floor(len(gd)/downsample_by)) # length of downsampled lists
				ds_idxs = random.sample(range(len(gd)), ds_len)
				# TODO: create a loop for this:
				gd = [val for i, val in enumerate(gd) if i in ds_idxs]
				zi = [val for i, val in enumerate(zi) if i in ds_idxs]
				zc = [val for i, val in enumerate(zc) if i in ds_idxs]
				k = [val for i, val in enumerate(k) if i in ds_idxs]
			print('preparing to plot')
			if target_name not in lhns_plotted or target_body_id == 483716037:
				if toPlot=='zi_v_k':
					if plot_raw_pts:
						pts = ax.scatter(k, zi, s=1, alpha= 0.2, color=lhns_colormap[target_name],
								 label = target_name)
					if fit_line:
						ax.plot(np.arange(0.1, 1.05, 0.05), [inv_fit(x) for x in np.arange(0.1, 1.05, 0.05)],
								color=lhns_colormap[target_name], alpha=0.6, label = target_name)
				elif toPlot=='zc_v_gd':

					# skip L13, local2 for now until I re-ID the most distal arbor
					if target_name == 'L13' or target_name == 'local2':
						continue

					if plot_raw_pts:
						pts = ax.scatter(gd, zc, s=1, alpha= 0.2, color=lhns_colormap[target_name],
									 label = target_name)
					ax.plot(range(180), arbor_fit.intercept + range(180)*arbor_fit.slope, 
									color=lhns_colormap[target_name], alpha=0.6,
									lw = 1, label = target_name)
					if len(gd_dis)>0:
						ax.plot(range(-80,0), DIS_fit.intercept + range(-80,0)*DIS_fit.slope,
									color=lhns_colormap[target_name], linestyle = 'dashed', alpha=0.6,
									lw = 1)
				lhns_plotted.append(target_name)
			else:
				if toPlot=='zi_v_k':
					if plot_raw_pts:
						ax.scatter(k, zi, s=1, alpha = 0.2, color = lhns_colormap[target_name])
					if fit_line:
						ax.plot(np.arange(0.15, 1.05, 0.05), [inv_fit(x) for x in np.arange(0.15, 1.05, 0.05)],
								color=lhns_colormap[target_name], alpha=0.6)
				elif toPlot=='zc_v_gd':

					# skip L13 for now until I re-ID the most distal arbor
					if target_name == 'L13' or target_name == 'local2':
						continue

					if plot_raw_pts:
						ax.scatter(gd, zc, s=1, alpha = 0.2, color = lhns_colormap[target_name])
					ax.plot(range(180), arbor_fit.intercept + range(180)*arbor_fit.slope, 
								color=lhns_colormap[target_name], alpha=0.6,
								lw = 1)
					if len(gd_dis)>0:
						ax.plot(range(-80,0), DIS_fit.intercept + range(-80,0)*DIS_fit.slope,
									color=lhns_colormap[target_name], linestyle = 'dashed', alpha=0.6,
									lw = 1)

			iters += 1
			#if iters > 4: break
	arbor_fits = pd.DataFrame(arbor_fits)

	# testing fitting to L12
	#inv_fit = lambda x: 2180 / x
	#ax.plot(np.arange(0.15, 1.05, 0.05), [inv_fit(x) for x in np.arange(0.15, 1.05, 0.05)], color = 'black',
	#		ls = 'dashed')

	if toPlot=='zi_v_k':
		ax.set(xlabel='voltage transfer ratio', ylabel='input resistance (M\u03A9)', xlim=[0,1], ylim=[0,7500])
	elif toPlot=='zc_v_gd':
		if align_branch_out: xlab = 'distance from dendritic branch out point (\u03BCm)'
		else: xlab = 'distance from pSIZ (\u03BCm)'
		ax.set(xlabel=xlab, ylabel='transfer resistance (M\u03A9)', ylim=[0,1800])
		if align_branch_out: ax.axvline(0, color = 'grey', ls = 'dashed', alpha = 0.2)
	lgnd = ax.legend(loc = 'center left', prop={'size':7}, ncol = 1, frameon=False, bbox_to_anchor = (1.01, 0.5),
						borderaxespad = 0)
	# TODO: change legend to the names of each LHN colored by the corresponding
	#for handle in lgnd.legendHandles:
	#	handle.set_sizes([6.0]) # increase size of points in legend
	ax.spines["top"].set_visible(False), ax.spines["right"].set_visible(False)
	plt.subplots_adjust(right=0.9) # give room to legend on right
	
	if save_out:
		if toPlot=='zi_v_k':
			#plt.savefig('figs\\allLHNs_Zi_vs_k.jpg', format = 'jpg', bbox_inches='tight', dpi = 500)
			plt.savefig(f'figs\\allLHNs_{toPlot}.svg', format='svg')
			#plt.savefig('figs\\allLHNs_Zc_vs_gd.jpg', format = 'jpg', bbox_inches='tight', dpi = 500)
	plt.show()

	# plot R^2 values in a histogram
	if fit_line:
		fig, ax = plt.subplots(1,1,figsize=(1.5,1))
		if toPlot=='zi_v_k':
			ax.hist(arbor_fits['r^2'], bins = 85, color = 'grey')
			ax.set(ylabel = 'frequency', xlabel = f'inverse fit $R^2$', xticks = np.arange(0, 1.01, 0.25))
		if toPlot=='zc_v_gd':
			ax.hist(arbor_fits.loc[arbor_fits.fit_type=='arbor']['r^2'], bins = 25, color = 'grey')
			ax.set(ylabel = 'frequency', xlabel = f'linear fit $R^2$', xticks = np.arange(0, 1.01, 0.25))
		ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
		if save_out:
			plt.savefig(f'figs\\allLHNs_{toPlot}_RsqHist.svg')
		plt.show()

	# compare slopes for DIS and dendritic arbor
	if fit_line and toPlot=='zc_v_gd':
		fig, ax = plt.subplots(1,1,figsize=(2,1))
		ax.hist(arbor_fits.loc[arbor_fits['fit_type']=='arbor']['slope'], label = 'arbor fit', 
				alpha = 0.8, bins = 40, color = 'black')
		ax.hist(arbor_fits.loc[arbor_fits['fit_type']=='DIS']['slope'], label = 'dendritic initial section fit', 
				alpha=0.3, bins=50, color = 'grey')
		ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
		ax.set(xlabel = 'linear fit slopes', ylabel = 'frequency')
		if save_out:
			plt.savefig('figs\\allLHNs_zc_v_gd_DISdendr_slopeHist.svg')
		plt.show()
	
	return arbor_fits

def fig_allLHNs_dendr_ax_linearity(target_neuron_file = 'LHN_list_siz_dendr_locs.csv'):
	'''fit lines to the axonal and dendritic arbors across all LHNs, in TRANSFER RESISTANCE
		SPACE, compare slopes of the two sets of best fit lines'''

	nrns = pd.read_csv(target_neuron_file)

	arbor_fits = []
	for i, row in nrns.iterrows():
		if pd.notna(row['prox_dendr_sec']):

			target_name, target_body_id = row['lhn'], row['lhn_id']
			isLocal = False
			if 'local' in target_name:
				isLocal = True

			d_branch_sec, d_branch_seg = int(row['dendr_branch_out_sec']), float(row['dendr_branch_out_seg'])
			a_branch_sec, a_branch_seg = int(row['ax_branch_out_sec']), float(row['ax_branch_out_seg'])

			# evaluate dendritic arbor (after first branch point)
			gd, zi, zc, k, branchout_dist = subtree_imp_props(target_name, target_body_id, 
												d_branch_sec, d_branch_seg)
			arbor_fit = stats.linregress(gd, zc)
			toAppend = {'lhn': target_name, 'lhn_id': target_body_id, 'is_local': isLocal, 
							'slope_dendr': arbor_fit.slope, 'intercept_dendr': arbor_fit.intercept,
							'r2_dendr': arbor_fit.rvalue**2}

			# evaluate axonal arbor (after first branch point)
			gd, zi, zc, k, branchout_dist = subtree_imp_props(target_name, target_body_id, 
												a_branch_sec, a_branch_seg)
			arbor_fit = stats.linregress(gd, zc)

			toAppend.update(slope_ax=arbor_fit.slope, intercept_ax = arbor_fit.intercept,
							r2_ax=arbor_fit.rvalue**2)

			arbor_fits.append(toAppend)
	arbor_fits = pd.DataFrame(arbor_fits)
	# quick and dirty plot comparing slopes of dendrite and axon
	a = pd.read_csv('21-01-19_dendr_vs_ax_linearity.csv')
	a = arbor_fits
	fig, ax = plt.subplots(1,1, figsize=(2,2))
	ax.scatter(a['slope_dendr'], a['slope_ax'], color = 'black', alpha = 0.6, s = 3)
	#ax.scatter(a.loc[~a.is_local]['slope_dendr'], a.loc[~a.is_local]['slope_ax'], label = 'output neurons')
	#ax.scatter(a.loc[a.is_local]['slope_dendr'], a.loc[a.is_local]['slope_ax'], label = 'local neurons')
	#plt.legend()
	ax.plot([0,-10], [0,-10], ls = 'dashed', color = 'grey', alpha = 0.3)
	ax.set(xlim=[-10, 0], ylim=[-10, 0], xlabel = 'dendritic linear fit slope',
				ylabel = 'axonal linear fit slope')
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	plt.savefig('figs\\allLHNs_dendr_ax_linearity.svg')
	plt.show()
	return arbor_fits

def analyze_arbor_fits(arbor_fits):

	lhns_colormap = {}
	import matplotlib
	rainbow = matplotlib.cm.get_cmap('hsv')
	for i, lhn in enumerate(arbor_fits.lhn.unique()):
		lhns_colormap[lhn] = rainbow(i * 1/len(arbor_fits.lhn.unique()))

	fig, ax = plt.subplots(1,1)
	for name, sub in arbor_fits.groupby('lhn'):
		ax.scatter(sub['slope'], sub['r^2'], label = name, color = lhns_colormap[name])
	ax.legend()

	#boxplot
	sns.boxplot(x='lhn', y='slope', data=arbor_fits)
	#compare DIS vs arbor fits
	plt.hist(arbor_fits.loc[arbor_fits['fit_type']=='arbor']['slope'], label = 'arbor fit', alpha = 0.3, bins = 10)
	plt.hist(arbor_fits.loc[arbor_fits['fit_type']=='DIS']['slope'], label = 'dendritic initial section fit', alpha=0.3, bins=10)
	plt.legend()
	plt.xlabel('slope')
	plt.hist(arbor_fits.loc[arbor_fits['fit_type']=='arbor']['r^2'], label = 'arbor fit', alpha = 0.3, bins = 10)
	plt.hist(arbor_fits.loc[arbor_fits['fit_type']=='DIS']['r^2'], label = 'dendritic initial section fit', alpha=0.3, bins=10)
	plt.legend()
	plt.xlabel('r^2')

def subtree_imp_props(target_name, target_body_id, dendr_sec, dendr_seg,
						branchout_sec = None, branchout_seg = None):
	'''given an LHN and a proximal dendritic section and segment, 
		measure the impedance properties of that section's subtree, 
		referenced to that section
	
	RETURNS:
	gd, zi, zc, k - lists: geodesic distance, input resistance, transfer
		resistance, and voltage transfer ratio
	branchout_dist - integer: geodesic distance from the reference dendr_sec
		at which the branchout_sec occurs (in micrometers)
	'''

	# biophysical parameters from our fits (NEEDS UPDATING)
	R_a = 350
	c_m = 0.6
	g_pas = 5.8e-5
	e_pas = -55 # one parameter left same in both, we used -55 in our fits
	syn_strength = 5.5e-5 # uS
	# instantiate target (post-synaptic) cell
	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')
	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	print(target_name)	
	gd, zi, zc, k = [], [], [], [] # collect impedance measures for all dendritic segments
	branchout_dist = None
	imp = h.Impedance()
	imp.loc(dendr_seg, sec= cell1.axon[dendr_sec])
	imp.compute(0)
	for sec in cell1.axon[dendr_sec].subtree():
		for seg in sec:
			#try:
			gd.append(h.distance(cell1.axon[dendr_sec](dendr_seg), seg))
			zi.append(imp.input(seg))
			zc.append(imp.transfer(seg))
			k.append(imp.ratio(seg))
			# identify branch_out point (seg w/in 3 um of branchout):
			if branchout_sec and branchout_seg: # check if values are in spreadsheet
				if h.distance(cell1.axon[branchout_sec](branchout_seg), seg) < 3 and not branchout_dist:
					branchout_dist = gd[len(gd)-1]
			#except:
			#	print('error in evaluating impedance properties')

	return gd, zi, zc, k, branchout_dist

def analyze_passive_norm():
	'''
		code for brainstorming how to visually show passive normalization/
		the dendritic linearity part of the paper
	'''

	dendritic_sec = 3 # for ML9 542634516

	### after initializing ML9 using `visualize` code above!
	### one of the first dendritic sections distal to the SIZ is axon[3]
	gd, zi, zc, k = [], [], [], []
	imp = h.Impedance()
	imp.loc(0.5, sec= cell1.axon[dendritic_sec])
	imp.compute(0)
	for sec in cell1.axon[dendritic_sec].subtree():
		for seg in sec:
			gd.append(h.distance(cell1.axon[dendritic_sec](0.5), seg))
			zi.append(imp.input(seg))
			zc.append(imp.transfer(seg))
			k.append(imp.ratio(seg))
	# then can plot any variables against each other, i.e.:
	plt.scatter(k, [z/max(zi) for z in zi], s = 4, label = 'dendritic segments') # cool inverse relationship
	plt.plot(np.arange(0.2, 1.05, 0.05), [0.2/x for x in np.arange(0.2, 1.05, 0.05)], color = 'red', ls = 'dashed', label = 'y=0.2/x')
	plt.legend(loc='upper right')
	# calculate R^2
	norm_zi = [z/max(zi) for z in zi]
	r_ss= sum([(z - 0.2/k[k_ind])**2 for k_ind, z in enumerate(norm_zi)]) # residual sum of squares
	t_ss = sum([(z - mean(norm_zi))**2 for z in norm_zi])
	Rsqu = 1 - r_ss/t_ss

def heatmap_AISmanips(target_neuron= 'local5', target_body_id = 5813105722,
						dendr_input = 'VA6_adPN', axon_input = 'VL2a_adPN',
						ais = 1002, uEPSP_measure_sec = 996, uEPSP_measure_seg = 0.5,
						toPrune = True,
						plot_heatmap_riseTime = False,
						plot_heatmap_somaAmp = True, preload = False): 
	'''
		given a neuron and its axon initial section (local5 or local6) and one input
		targeting the axon and one targeting the dendrite, 
		produce a heatmap of the effect on the difference between axon and dendrite targeting
		uEPSPs, under the influence of thickening and shortening 

		for each combination of thicken and shorten, run a sub-method which produces the 
			EPSP sizes of VL2a and VA6

	PARAMETERS:
		target_neuron= 'local5', target_body_id = 5813105722,
						dendr_input = 'VA6_adPN', axon_input = 'VL2a_adPN',
						ais = 1002, uEPSP_measure_sec = 996, uEPSP_measure_seg = 0.5,
						toPrune = True
		target_neuron= 'local6', target_body_id = 386825553,
						dendr_input = 'DA4l_adPN', axon_input = 'VL2a_adPN',
						ais = 1002, uEPSP_measure_sec = 996, uEPSP_measure_seg = 0.5,
						toPrune = True
	RETURNS:
		AIS_change_siz, AIS_change_soma, AIS_change_soma_t: pd.DataFrames
						idx: amount of change in thickness to AIS; col: amount of change in length to AIS
	'''

	thickness_range = np.arange(-0.3, 1.4, 0.1)
	length_range = np.arange(-60, 31, 5)
	#thickness_range = np.arange(-0.3, 1.0, 0.5)
	#length_range = np.arange(-60, 31, 40)

	conns = fetch_simple_connections(upstream_criteria = dendr_input, downstream_criteria = target_body_id)
	pre_bodyIds = conns.bodyId_pre
	dendr_syn_locs = fetch_synapse_connections(source_criteria = pre_bodyIds, target_criteria = target_body_id)
	conns = fetch_simple_connections(upstream_criteria = axon_input, downstream_criteria = target_body_id)
	pre_bodyIds = conns.bodyId_pre
	axon_syn_locs = fetch_synapse_connections(source_criteria = pre_bodyIds, target_criteria = target_body_id)

	if toPrune:
		dendr_syn_locs = dendr_syn_locs.iloc[0:len(axon_syn_locs)]	

	# track EPSP differences (dendritic and axonal EPSPs) at different l and w alterations
	AIS_change_siz = pd.DataFrame(columns = list(length_range))
	AIS_change_soma = pd.DataFrame(columns = list(length_range))
	AIS_change_soma_t = pd.DataFrame(columns = list(length_range))

	# track absolute length and width of AIS after alterations
	ais_dendrEPSP = pd.DataFrame(columns = list(length_range)) 
	ais_axEPSP = pd.DataFrame(columns = list(length_range))
	for t in thickness_range:
		EPSPs_per_thickness_siz, EPSPs_per_thickness_soma, t_per_thickness_soma = [], [], []
		ais_perT_dendrEPSP, ais_perT_axEPSP = [], []
		for l in length_range:
			# first simulate dendritic input (with relevant AIS changes), then axonal
			dendr_out = change_AIS_sim_EPSP(target_neuron, target_body_id, dendr_input,
												uEPSP_measure_sec, uEPSP_measure_seg, dendr_syn_locs, ais, t, l)
			ax_out = change_AIS_sim_EPSP(target_neuron, target_body_id, axon_input,
												uEPSP_measure_sec, uEPSP_measure_seg, axon_syn_locs, ais, t, l)
			EPSPs_per_thickness_siz.append(dendr_out['v_peak_siz'] - ax_out['v_peak_siz'])
			EPSPs_per_thickness_soma.append(dendr_out['v_peak_soma'] - ax_out['v_peak_soma'])
			t_per_thickness_soma.append(dendr_out['t_10to90_soma'] - ax_out['t_10to90_soma'])

			ais_perT_dendrEPSP.append((dendr_out['newLength'], dendr_out['newDiam']))
			ais_perT_axEPSP.append((ax_out['newLength'], ax_out['newDiam']))

		AIS_change_siz.loc[t] = EPSPs_per_thickness_siz
		AIS_change_soma.loc[t] = EPSPs_per_thickness_soma
		AIS_change_soma_t.loc[t] = t_per_thickness_soma

		ais_dendrEPSP.loc[t] = ais_perT_dendrEPSP
		ais_axEPSP.loc[t] = ais_perT_axEPSP

	# fix index and cols to be absolute diameter and lengths:
	for df in [AIS_change_siz, AIS_change_soma, AIS_change_soma_t]:
		df.index = [round(new_w,2) for (new_l, new_w) in ais_dendrEPSP.iloc[:,0]] # iterate down column (w's change)
		df.columns = [round(new_l,1) for (new_l, new_w) in ais_dendrEPSP.iloc[0]] # iterate across row (l's change)

	date = datetime.today().strftime("%y-%m-%d")
	AIS_change_siz.to_csv(f'change_AIS\\{date}_heatmap_AISmanips_{target_neuron}siz.csv')
	AIS_change_soma.to_csv(f'change_AIS\\{date}_heatmap_AISmanips_{target_neuron}soma.csv')
	AIS_change_soma_t.to_csv(f'change_AIS\\{date}_heatmap_AISmanips_{target_neuron}soma_riseTime.csv')

	if ais_dendrEPSP.equals(ais_axEPSP):
		print('as expected, changing the length and diameter is consistent across EPSPs')

	if plot_heatmap_somaAmp:
		if preload:
			AIS_change_soma = pd.read_csv('change_AIS\\21-01-27_heatmap_AISmanips_local5soma.csv',
											index_col = 0)
			target_neuron = 'local5'
		fig, ax = plt.subplots(figsize = (2, 3))
		sns.heatmap(AIS_change_soma, ax = ax, vmin = 0, linewidths = 0.1)
		ax.tick_params(axis='y', labelrotation = 0)
		plt.savefig(f'figs\\heatmap_AISmanips_{target_neuron}soma_Amp.svg')

	if plot_heatmap_riseTime:
		fig, ax = plt.subplots(figsize = (2, 3))
		sns.heatmap(AIS_change_soma_t, ax = ax, vmax = 0, linewidths = 0.1)
		ax.tick_params(axis='y', labelrotation = 0)
		plt.savefig(f'figs\\heatmap_AISmanips_{target_neuron}soma_riseTime.svg')

	return AIS_change_siz, AIS_change_soma, AIS_change_soma_t
	#ax = sns.heatmap(AIS_change_matrix)

def fig_heatmap_AISmanips():
	
	AIS_change_soma = pd.read_csv('change_AIS\\21-01-27_heatmap_AISmanips_local5soma.csv',
									index_col = 0)
	target_neuron = 'local5'

	rock = sns.color_palette('rocket_r', as_cmap=True)

	AIS_change_soma=AIS_change_soma.unstack().reset_index()
	AIS_change_soma.columns=["len","diam","diff"]

	# Make the plot
	fig = plt.figure()
	ax = fig.gca(projection='3d')
	surf = ax.plot_trisurf(AIS_change_soma['diam'], AIS_change_soma['len'], AIS_change_soma['diff'], 
				cmap=rock, vmin = 0)
	ax.set(ylabel = 'AIS length (\u03BCm)', xlabel = 'AIS diameter (\u03BCm)', 
			zlabel = 'uEPSP amplitude difference (mV)')
	plt.show()
	#fig.colorbar( surf, shrink=0.5, aspect=5)
	
	# Rotate it
	#ax.view_init(30, 45)

	AIS_change_somaT = pd.read_csv('change_AIS\\21-01-27_heatmap_AISmanips_local5soma_riseTime.csv',
									index_col = 0)

	AIS_change_somaT=AIS_change_somaT.unstack().reset_index()
	AIS_change_somaT.columns=["len","diam","diff"]
	AIS_change_somaT['diff'] = np.abs(AIS_change_somaT['diff'])

	# Make the plot
	fig = plt.figure()
	ax = fig.gca(projection='3d')
	surf = ax.plot_trisurf(AIS_change_somaT['diam'], AIS_change_somaT['len'], AIS_change_somaT['diff'], 
				cmap=rock, vmin = 0)
	ax.set(ylabel = 'AIS length (\u03BCm)', xlabel = 'AIS diameter (\u03BCm)', 
			zlabel = 'rise time difference (ms)')
	plt.show()

	
	''' conventional heatmap
	fig, ax = plt.subplots(figsize = (2, 3))
	sns.heatmap(AIS_change_soma, ax = ax, vmin = 0, linewidths = 0.1)
	ax.tick_params(axis='y', labelrotation = 0)
	plt.savefig(f'figs\\heatmap_AISmanips_{target_neuron}soma_Amp.svg')
	'''

def change_AIS_sim_EPSP(target_neuron, target_body_id, input_neuron, 
							uEPSP_measure_sec, uEPSP_measure_seg, syn_locs, ais, t, l):
	''' t: amount to thicken/thin; l: amount to lengthen/shorten, in micrometers
	'''

	# instantiate neuron and synapses
	cell1, curr_syns, netstim, netcons, num = visualize_inputs(target_name = target_neuron, 
													target_body_id = target_body_id, 
													input_name = input_neuron, 
													syn_locs = syn_locs)

	# store original length and thickness
	origLength = cell1.axon[ais].L
	origDiam = mean([seg.diam for seg in cell1.axon[ais]])

	# alter AIS length and thickness
	cell1.axon[ais].L = cell1.axon[ais].L + l
	for seg in cell1.axon[ais]:
		seg.diam = seg.diam + t
	newLength = cell1.axon[ais].L
	newDiam = mean([seg.diam for seg in cell1.axon[ais]])

	if newLength != origLength + l: print(f'improperly lengthened: {newLength} {origLength}')
	print(f'expected new mean diam {origDiam + t}, new mean diam {newDiam}')

	# simulate EPSP
	# measure uEPSP for connection at pSIZ and distal axon and soma
	netstim.number = 1 # activate stim
	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)
	v_siz = h.Vector().record(cell1.axon[uEPSP_measure_sec](uEPSP_measure_seg)._ref_v)
	v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
	t = h.Vector().record(h._ref_t)                     				# Time stamp vector
	h.finitialize(-55 * mV)
	h.continuerun(40*ms)
	netstim.number = 0 # de-activate stim
	# measure rise time of EPSP at pSIZ and soma
	t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)
	t_10to90_soma = time_to_percent_peak(t, v_soma, 0.90) - time_to_percent_peak(t, v_soma, 0.10)

	changeAIS_out = {'v_peak_siz': max(v_siz), 'v_peak_soma': max(v_soma), 
						't_10to90_siz': t_10to90_siz, 't_10to90_soma': t_10to90_soma,
						'newLength': newLength, 'newDiam': newDiam}
	return changeAIS_out

def testTimingDiffs(target_name = 'local5', target_body_id = 5813105722,
					input1 = 'VA6_adPN', input2 = 'simulated_dendritic_input', sim_syn_count = 290, 
					seed_set = 420,
					plot_loc = 'prox_axon', 
					plot_EPSP = False, plot_dVdt = False,
					lhn_morph_path = '21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv',
					isopot_dendr_arbor = False, isopot_ax_arbor = False, isopot_prim_ax = False,
					isopot_whole_nrn = False,
					isopot_Ra_val = 0.001,
					highpot_prim_ax = False, highpot_Ra_val = 10000):
	'''
		instantiate a neuron (i.e. local5), add 2 inputs (i.e. VA6, VL2a), stimulate these
			inputs at various time lags and measure relative joint EPSP size at SIZ vs 
			temporal offset;
			also time to 80% of max EPSP size vs temporal offset 

		Params:
		input1 (str): i.e. 'VA6_adPN'
		input2 (str): 'VL2a_adPN' or 'simulated_dendritic_input'
			if 'simulated_dendritic_input', then places synapses distal to 'dendr_start'
		seed_set: change each time to get different random synapse placements 
					(I think the random seed carries into method calls)
		plot_loc: 'dendr_start', 'dendr_first_branch', 'ax_start', 'ax_first_branch'
				DEPRECATED:'soma', 'prox_axon' (=axon branch out point), 'dist_axon', 'prox_dendr', 'siz'
			
		sim_syn_count: integer; number of synapses in simulated dendritic input
		Returns:
			v_df - pd.DataFrame: 
				each row represents a different input1 spike time (in ms), where input2 is always at 50 ms
				thus, row 50 represents simultaneous activation of input1 and input2
			max_v_per_loc - pd.DataFrame: 
	'''
	global cell1, curr_syns1, curr_syns2
	
	print(f'--- staggered activation onto {target_name} of inputs {input1} and {input2}')

	random.seed(seed_set)
	if target_name == 'local5' and target_body_id == 5813105722:
		dendr_init_sec = 195

	# instantiate target (post-synaptic) cell
	try:
		swc_path = "swc\\{}-{}.swc".format(target_name, str(target_body_id))
	except:
		print('no SWC found')
	# biophysical parameters from our fits
	R_a = 350
	c_m = 0.6
	g_pas = 5.8e-5
	e_pas = -55 # one parameter left same in both, we used -55 in our fits
	syn_strength = 5.5e-5 # uS

	# read in morphology labels (recording locations at proximal axon, dendrite, etc): 
	measure_locs = {'dendr_start': [None, 0.5], 'dendr_first_branch': [None, 0.5], 
                	'ax_start': [None, 0.5], 'ax_first_branch': [None, 0.5],
                	'ax_distal': [0, 0.5], 
                	'soma': [0, 0.5]}
	if lhn_morph_path:
	    lhn_list = pd.read_csv(lhn_morph_path)
	    if 'LHN_SWCPointNo_to_NEURON' in lhn_morph_path:
	        try:
	        	for loc, (sec, seg) in measure_locs.items():
	        		try:
	        			measure_locs[loc][0] = int(lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.body_id==target_body_id)]['N_'+loc+'_sec'].iloc[0])
	        			measure_locs[loc][1] = float(lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.body_id==target_body_id)]['N_'+loc+'_seg'].iloc[0])
	        		except:
	        			print(f'WARNING: program unsuccessfully tried to find morphology label for {loc}, will use (possibly wrong) default')
	        except:
	            print('neuron is unlabeled in morphology file')
	    else:
	        print('unrecognized morphology file type')
	print('measure_locs acquired:', measure_locs)

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	# get number of post-synapses on the target neuron
	target, r = fetch_neurons(target_body_id)
	target_syn_count = target.post[0]

	# add all input1 synaptic site locations
	conns1 = fetch_simple_connections(upstream_criteria = input1, downstream_criteria = target_body_id)
	pre_bodyIds1 = conns1.bodyId_pre
	syn_locs1 = fetch_synapse_connections(source_criteria = pre_bodyIds1, target_criteria = target_body_id)
	curr_syns1, netstim1, netcons1, num1 = cell1.add_synapses_xyz(xyz_locs = syn_locs1, syn_strength = syn_strength)
	print('adding {} synapses from {} to {}; budget = {}'.format(str(num1), input1, target_name, str(num1/target_syn_count)))
	if target_name == 'local5' and target_body_id == 5813105722:
		# dendrite initial section is axon[195] for un-retraced local5
		num_in_dendr = 0
		for syn in curr_syns1:
			if str(syn.get_segment()).partition('(')[0] in [str(val) for val in cell1.axon[dendr_init_sec].subtree()]:
				num_in_dendr += 1
		print('proportion synapses in dendrite: {}'.format(str(num_in_dendr/num1)))

	# add all input2 synaptic site locations
	if input2 == 'simulated_dendritic_input':
		print('creating a simulated dendritic connection')
		### CHANGE: we'll make 75 fake dendritic synapses to correspond to VL2a's synapse count
		curr_syns2, netstim2, netcons2, num2 = cell1.add_synapses_subtree(sec_for_subtree = measure_locs['dendr_start'][0], 
																			syn_count = sim_syn_count,
																			syn_strength = syn_strength)
		print('adding {} synapses from {} to {}; budget = {}'.format(str(num2), input2, target_name, str(num2/target_syn_count)))
		if target_name == 'local5' and target_body_id == 5813105722:
			# dendrite initial section is axon[195] for un-retraced local5
			num_in_dendr = 0
			for syn in curr_syns2:
				if str(syn.get_segment()).partition('(')[0] in [str(val) for val in cell1.axon[dendr_init_sec].subtree()]:
					num_in_dendr += 1
			print('proportion synapses in dendrite: {}'.format(str(num_in_dendr/num2)))
	else:
		conns2 = fetch_simple_connections(upstream_criteria = input2, downstream_criteria = target_body_id)
		pre_bodyIds2 = conns2.bodyId_pre
		syn_locs2 = fetch_synapse_connections(source_criteria = pre_bodyIds2, target_criteria = target_body_id)
		curr_syns2, netstim2, netcons2, num2 = cell1.add_synapses_xyz(xyz_locs = syn_locs2, syn_strength = syn_strength)
		print('adding {} synapses from {} to {}; budget = {}'.format(str(num2), input2, target_name, str(num2/target_syn_count)))
		if target_name == 'local5' and target_body_id == 5813105722:
			# dendrite initial section is axon[195] for un-retraced local5
			num_in_dendr = 0
			for syn in curr_syns2:
				if str(syn.get_segment()).partition('(')[0] in [str(val) for val in cell1.axon[dendr_init_sec].subtree()]:
					num_in_dendr += 1
			print('proportion synapses in dendrite: {}'.format(str(num_in_dendr/num2)))
	
	### perturb isopotentiality of certain aspects of morphology
	if isopot_dendr_arbor:
		print(f'setting dendritic arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[measure_locs['dendr_first_branch'][0]].subtree() 
						if sec != cell1.axon[measure_locs['dendr_first_branch'][0]]]:
			sec.Ra = isopot_Ra_val
	if isopot_ax_arbor:
		print(f'setting axonal arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[measure_locs['ax_first_branch'][0]].subtree() 
						if sec != cell1.axon[measure_locs['ax_first_branch'][0]]]:
			sec.Ra = isopot_Ra_val
	if isopot_prim_ax:
		print(f'setting primary axon axial resistance to {isopot_Ra_val}')
		prim_ax_secs = [sec for sec in cell1.axon[measure_locs['ax_start'][0]].subtree() \
						if sec not in cell1.axon[measure_locs['ax_first_branch'][0]].subtree()[1:]]
		for sec in prim_ax_secs:
			sec.Ra = isopot_Ra_val
	if highpot_prim_ax: # from 'N_ax_start_sec' = siz_sec to 'N_ax_first_branch_sec'
		print(f'setting primary axon axial resistance to {highpot_Ra_val}')
		prim_ax_secs = [sec for sec in cell1.axon[measure_locs['ax_start'][0]].subtree() \
						if sec not in cell1.axon[measure_locs['ax_first_branch'][0]].subtree()[1:]]
		for sec in prim_ax_secs:
			sec.Ra = highpot_Ra_val
	if isopot_whole_nrn:
		print(f'setting entire neuron axial resistance to {isopot_Ra_val}')
		for sec in h.allsec():
			sec.Ra = isopot_Ra_val

	# previous (deprecated) measure_locs for local5
	'''if target_name == 'local5' and target_body_id == 5813105722:
					measure_locs = {'soma': (93, 0.5), 'prox_axon': (1003, 0.5), 'dist_axon': (1429, 0.5), 
									'prox_dendr': (197, 0.5), 'siz': (996, 0.5)}'''

	# set recording structures + locations
	# v: keys are recording locations, values are lists of voltage traces, index is input1 timing
	# t: list of time traces, index is input1 timing (matches index for v)
	t = []
	v = {}
	for key, val in measure_locs.items():
		v[key] = []

	# measure individual maximum amplitudes at each measure_loc for linearity analysis:
	# max amplitude for input1:
	netstim1.number = 1
	netstim1.start = 0
	netstim2.number = 0
	netstim2.start = 0
	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)
	v_temp = {}
	for loc, (sec, seg) in measure_locs.items():
		v_temp[loc] = h.Vector().record(cell1.axon[sec](seg)._ref_v) # voltage trace vectors
	t_temp = h.Vector().record(h._ref_t)                     # time stamp vector
	h.finitialize(-55 * mV)
	h.continuerun(130*ms)
	max_v, locs = [], []
	for loc, (sec, seg) in measure_locs.items():
		max_v.append(max(list(v_temp[loc])))
		locs.append(loc)
	max_v_per_loc = pd.DataFrame(data = max_v, index = locs, columns = [input1])
	# max amplitude for input2:
	netstim1.number = 0
	netstim1.start = 0
	netstim2.number = 1
	netstim2.start = 0
	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)
	v_temp = {}
	for loc, (sec, seg) in measure_locs.items():
		v_temp[loc] = h.Vector().record(cell1.axon[sec](seg)._ref_v) # voltage trace vectors
	t_temp = h.Vector().record(h._ref_t)                     # time stamp vector
	h.finitialize(-55 * mV)
	h.continuerun(130*ms)
	max_v, locs = [], []
	for loc, (sec, seg) in measure_locs.items():
		max_v.append(max(list(v_temp[loc])))
		locs.append(loc)
	max_v_per_loc[input2] = max_v

	# input2 timing is set: 
	netstim2.number = 1
	netstim2.start = 50
	netstim1_start = 0
	netstim1_end = 101
	print(f'input 2 activating at {netstim2.start} ms')
	print(f'input 1 time ranges from {netstim1_start} to {netstim1_end} ms')

	# input1 timing varies:
	print('initiating staggered input activation')
	for i in np.arange(netstim1_start,netstim1_end):
		netstim1.number = 1
		netstim1.start = i
		
		h.load_file('stdrun.hoc')
		x = h.cvode.active(True)
		v_temp = {}
		for loc, (sec, seg) in measure_locs.items():
			v_temp[loc] = h.Vector().record(cell1.axon[sec](seg)._ref_v) # voltage trace vectors
		t_temp = h.Vector().record(h._ref_t)                     # time stamp vector
		h.finitialize(-55 * mV)
		h.continuerun(130*ms)
		t.append(list(t_temp))
		for loc, (sec, seg) in measure_locs.items():
			v[loc].append(list(v_temp[loc]))

	# plot peak EPSP at plot_loc for different timing
	if plot_EPSP:
		plot_peak_EPSP(plot_loc = plot_loc, v = v, t = t, input1 = input1, input2 = input2,
					max_v_per_loc = max_v_per_loc, netstim2start = netstim2.start)
	if plot_dVdt:
		try:
			plot_peak_dVdt(plot_loc = plot_loc, v = v, t = t, input1 = input1, input2 = input2,
					max_v_per_loc = max_v_per_loc, netstim2start = netstim2.start)
		except:
			print('dV/dt plotting failed')

	v_df = pd.DataFrame(v)
	v_df['time_trace'] = t
	return v_df, max_v_per_loc

def fig_seq_PN_activ(preload = True, plot_dVdt = False, plot_loc = 'ax_first_branch', sim_syn_count = 290):
	'''show asymmetric EPSP amplitude from sequential PN activation (VA6-VL2a onto local5)
	'''

	if preload:
		v_df = pd.read_csv('21-01-26 va6_timing_vl2a@idx50.csv')
		v_df_sim = pd.read_csv('21-01-28 va6_timing_dendrSim@idx50_290simSyns.csv') 
		# baseline 75 sim syns: 21-01-26 va6_timing_dendrSim@idx50.csv
		for col in v_df.columns: #['time_trace', 'soma', 'prox_axon', 'dist_axon', 'prox_dendr', 'siz']:
			v_df[col] = v_df[col].apply(lambda x: eval(x))
			v_df_sim[col] = v_df_sim[col].apply(lambda x: eval(x))
		#v_df_sim, _ = testTimingDiffs(input2 = 'simulated_dendritic_input', sim_syn_count = sim_syn_count)
	else:
		v_df, max_v_per_loc = testTimingDiffs()
		v_df_sim, _ = testTimingDiffs(input2 = 'simulated_dendritic_input', sim_syn_count = sim_syn_count)

	if plot_dVdt:
		plot_peak_dVdt(plot_loc = 'siz', v = v_df, t = v_df['time_trace'], 
					input1 = 'VA6', input2 = 'VL2a', netstim2start = 50)

	# plot peak amplitude vs ISI for real and sim inputs
	fig, ax = plt.subplots(1, 1, figsize = (1.5,3))
	real_input_trace = [max([val-e_pas for val in trace]) for trace in v_df[plot_loc]]
	sim_trace = [max([val-e_pas for val in trace]) for trace in v_df_sim[plot_loc]]
	ax.plot([t - 50 for t in np.arange(0,101)], real_input_trace, 
					label = 'dendritic (VA6) + \naxonal (VL2a)'.format(plot_loc), color = 'purple')
	ax.plot([t - 50 for t in np.arange(0,101)], sim_trace, 
					label = 'dendritic (VA6) + \ndendritic (simulated)'.format(plot_loc), color = 'orange')
	ax.set(xlabel = 'inter-spike interval', ylabel = 'compound EPSP peak amplitude (mV)',
			xlim = [-30, 30])
	ax.vlines([-5, 5], min(sim_trace)-0.5, 19, color = 'grey', alpha = 0.3)
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	#l = ax.legend(loc = 'center right', frameon = False, prop = {'size': 7}, handlelength=0)
	#l.get_texts()[0].set_color('purple'), l.get_texts()[1].set_color('orange')
	plt.savefig('figs\\seq_PN_activ_amp_vs_ISI.svg')
	plt.show()

	t_simult = 50
	t_lag_amt = 5 
	# plot two example traces, idx 40 (VA6 leads by 10 s), idx 60 (VL2a leads by 10 s)
	fig, ax = plt.subplots(1, 2, sharey = True, figsize = (2.5,3))
	ax[0].plot(v_df['time_trace'][t_simult-t_lag_amt], v_df[plot_loc][t_simult-t_lag_amt], color = 'purple')
	ax[0].plot(v_df_sim['time_trace'][t_simult-t_lag_amt], v_df_sim[plot_loc][t_simult-t_lag_amt], color = 'orange')
	ax[1].plot(v_df['time_trace'][t_simult+t_lag_amt], v_df[plot_loc][t_simult+t_lag_amt], color = 'purple',
				label = 'dendritic (VA6) + \naxonal (VL2a) inputs')
	ax[1].plot(v_df_sim['time_trace'][t_simult+t_lag_amt], v_df_sim[plot_loc][t_simult+t_lag_amt], color = 'orange',
				label = 'dendritic (VA6) + \ndendritic (sim.) inputs')
	ax[0].set(xlim=[44,80], title=f'VA6 leads \nby {t_lag_amt} ms')
	ax[1].set(xlim=[44,80], title=f'VL2a leads \nby {t_lag_amt} ms')
	#ax.set(xlabel = 'inter-spike interval', ylabel = 'compound EPSP peak @ axon branch-out (mV)')
	ax[0].set_frame_on(False)
	ax[0].axis('off')
	#ax[0].xaxis.set_visible(False), ax[0].yaxis.set_visible(False)
	#ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	l = ax[1].legend(loc = 'upper right', frameon = False, prop = {'size': 7}, handlelength=0)
	l.get_texts()[0].set_color('purple'), l.get_texts()[1].set_color('orange')
	# set legend text color: https://stackoverflow.com/questions/18909696/how-to-change-the-text-color-of-font-in-legend
	add_scalebar(ax = ax[1], xlen=10, ylen=2, xlab=' ms', ylab=' mV', loc = 'lower right')
	plt.tight_layout()
	plt.savefig('figs\\seq_PN_activ_exTraces.svg')
	plt.show()

	return ax, v_df, v_df_sim

def plot_peak_EPSP(plot_loc, v, t, input1, input2, max_v_per_loc, netstim2start):
	fig, ax = plt.subplots(nrows = 1, ncols = 1)
	ax.plot(np.arange(0,101), [max([val-e_pas for val in trace]) for trace in v[plot_loc]], 
					label = 'compound EPSP max @ {}'.format(plot_loc))
	ax.axvline(netstim2start, label = '{} activation time'.format(input2), color = 'red', ls = 'dashed')
	ax.axhline((max_v_per_loc['input1'][plot_loc]+55) + (max_v_per_loc['input2'][plot_loc]+55),
					label = 'linear sum of individual EPSPs', color = 'orange', ls = 'dashed')

	# plot example traces
	ax.plot(t[20], np.array(v[plot_loc][20])-e_pas, label = '{} precedes {} by 30 ms'.format(input1, input2))
	ax.plot(t[int(netstim2start)], np.array(v[plot_loc][int(netstim2start)])-e_pas, 
				label = 'simultaneous activation')
	ax.plot(t[80], np.array(v[plot_loc][80])-e_pas, label = '{} lags {} by 30 ms'.format(input1, input2))
	ax.legend(loc = 'upper right')
	ax.set_ylabel("depolarization (mV)")
	ax.set_xlabel("{} activation time".format(input1, input2))
	ax.spines["top"].set_visible(False)
	ax.spines["right"].set_visible(False)
	plt.show()

def plot_peak_dVdt(plot_loc, v, t, input1, input2, netstim2start):
	'''for each time lag between inputs, plot the peak dV/dt of the EPSP'''
	fig, ax = plt.subplots(nrows = 1, ncols = 1)
	v_deriv = [np.diff(v_trace)/np.diff(t_trace) for t_trace, v_trace in zip(t, v[plot_loc])]
	ax.plot(np.arange(0,101), [max(trace) for trace in v_deriv], 
					label = 'compound EPSP max dV/dt @ {}'.format(plot_loc))
	ax.axvline(netstim2start, label = '{} activation time'.format(input2), color = 'red', ls = 'dashed')
	ax.legend(loc = 'upper right')
	ax.set(ylabel = "dV/dt (mV/ms)", xlabel = "{} activation time".format(input1, input2))
	ax.spines["top"].set_visible(False)
	ax.spines["right"].set_visible(False)
	plt.show()

	''' visualize the derivatives
	plt.plot(t[40][0:len(t[40])-1], v_deriv[40], color = 'blue')
	plt.plot(t[40], v_df[plot_loc][40], color = 'red')

	'''

def mEPSPs_for_all_LHNs(lhn_morph_path = 'LHN_list_siz_dendr_locs.csv'):
	'''given list of LHNs, i.e. LHN_list_siz_dendr_locs, probe ALL mEPSPs 
		and provide information for each synapse, i.e. amplitude, rise times, 
		and critically, whether it's dendritic or axonal

		calls visualize_inputs and adds all synapses from inputs with >3 
			total synapses, to save on time and memory
	'''

	# read in list of LHNs and morphology information
	lhn_list = pd.read_csv(lhn_morph_path)

	all_LHN_mEPSP_df = pd.DataFrame()
	for ind, row in lhn_list.iterrows():

		lhn_name, lhn_body_id = row.lhn, row.lhn_id
		lhn_siz_sec, lhn_siz_seg = row.siz_sec, row.siz_seg

		if 'CML2' in lhn_name or lhn_body_id==5813055963: 
		# skip CML2 due to its bilaterally-projecting nature and the unlabelled local2
			continue 

		mEPSP_out = probe_mEPSPs(target_name = lhn_name, target_body_id = lhn_body_id, 
									input_name = 'all_inputs',
									siz_sec = lhn_siz_sec, siz_seg = lhn_siz_seg,
									toPlot = False)

		all_LHN_mEPSP_df = all_LHN_mEPSP_df.append(mEPSP_out)

	date = datetime.today().strftime("%y-%m-%d")
	all_LHN_mEPSP_df.to_csv(f'{date}_mEPSPs_for_all_LHNs.csv')

	return all_LHN_mEPSP_df

def probe_mEPSPs(target_name = 'ML9', target_body_id = 542634516, input_name = 'DP1m_adPN',
					siz_sec = 569, siz_seg = 0.01,
					toPlot = False, lhn_morph_path = '21-03-06_LHN_SWCPointNo_to_NEURON_fix_first_branch.csv',
					all_input_min_weight = 3,
					transf_freq = 0,
					isopot_dendr_arbor = False, isopot_ax_arbor = False, isopot_prim_ax = False,
					isopot_whole_nrn = False,
					isopot_Ra_val = 0.001,
					highpot_prim_ax = False, highpot_Ra_val = 10000):
	'''
		given a downstream (target_name) neuron + ID, an upstream neuron, instantiate synapses
		(potentially pulling from neuprint) and simulate each mEPSP individually, allowing for
		recording of mEPSP amplitude, kinetics, location of synapse in axon vs dendrite 
		(based on lhn_morph_path CSV NEURON coordinates) etc. 

		TODO: 4/2/21: refactor code for reading in morphology locations from lhn_morph_path, using them to 
			measure voltages throughout the neuron, measure kinetics, etc. right now very ad hoc and 
			messily using different nomenclature; see testTimingDiffs for model of reading in morph_locs

		input_name - string: upstream input name, i.e. "DP1m_adPN", or "all_inputs" to simulate
							mEPSPs for all synaptic inputs
		lhn_morph_path - string: path to file with labelled morphology locations 
							contains 'LHN_SWCPointNo_to_NEURON' then is from Jamie's labels
							contains 'LHN_list_siz_dendr_locs.csv' then is my manual labels (slightly older)
		all_input_min_weight - int: if input_name is 'all_inputs', this sets the minimum number of 
							synapses for connections whose mEPSPs are simulated
		transf_freq - int: frequency at which to measure transfer impedance (=0 is transfer resistance)
		isopot_dendr/ax/prim_ax_arbor - bool: whether to set the axial resistance of the dendritic arbor/
							axonal arbor/primary axon to 0.00001 (isopotential) or 1000 (high potential)

	RETURNS: per_synapse_data - pd.DataFrame: each row contains attributes of a particular synapse, incl:
								ax_v_dendr - string: 'dendritic', 'axonal', or 'unknown'
								ATTRIBUTES: (access via df.attr)
								sum_eff_soma - float: uEPSP @ soma / sum of mEPSPs @ soma
								sum_eff_siz - float: uEPSP @ siz / sum of mEPSPs @ siz
								SIZ = first axonal sec for Jamie's labels
	'''

	# Change syn_strength to new fit values!
	syn_strength = 5.5e-5 # uS

	# instantiate the cell and input synapses of interest
	cell1, curr_syns, netstim, netcons, num, pre_body_ids, pre_nrn_info = visualize_inputs(target_name = target_name, 
												target_body_id = target_body_id, input_name = input_name,
												all_input_min_weight = all_input_min_weight)
	if not netstim or not curr_syns or not netcons:
		print(f'no synapses found for {input_name}, returning empty dataframe')
		return pd.DataFrame()

	# read in proximal axon and dendrite section: 
	if lhn_morph_path:
		lhn_list = pd.read_csv(lhn_morph_path)
		if 'LHN_list_siz_dendr_locs' in lhn_morph_path:
			try:
				morph_locs = lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.lhn_id==target_body_id)] \
								[['dendr_branch_out_sec', 'ax_branch_out_sec', 'siz_sec', 'siz_seg']].iloc[0]
				dendr_branch_out_sec, ax_branch_out_sec, siz_sec = [int(m) for m in morph_locs[0:3]]
				siz_seg = float(morph_locs[3])
			except ValueError:
				print('neuron has unclear dendritic branch out point, using prox dendritic point')
				morph_locs = lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.lhn_id==target_body_id)] \
								[['prox_dendr_sec', 'prox_ax_sec', 'siz_sec', 'siz_seg']].iloc[0]
				dendr_branch_out_sec, ax_branch_out_sec, siz_sec, siz_seg = [int(m) for m in morph_locs]
			except:
				print('neuron is unlabeled in morphology file')
		elif 'LHN_SWCPointNo_to_NEURON' in lhn_morph_path:
			try:
				morph_locs = lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.body_id==target_body_id)] \
								[['N_dendr_first_branch_sec', 'N_ax_first_branch_sec', 'N_ax_start_sec', 'N_ax_start_seg', \
								  'N_dendr_first_branch_seg', 'N_ax_first_branch_seg']].iloc[0]
				dendr_branch_out_sec, ax_branch_out_sec, siz_sec, _, \
					dendr_branch_out_seg, ax_branch_out_seg = [int(m) for m in morph_locs]
				siz_seg = float(morph_locs[3])
			except ValueError: # MODIFY FOR THIS CASE
				print('neuron has unclear dendritic branch out point, using prox dendritic point')
				morph_locs = lhn_list.loc[(lhn_list.lhn==target_name) & (lhn_list.lhn_id==target_body_id)] \
								[['N_dendr_first_branch_sec', 'N_ax_first_branch_sec', 'N_ax_start_sec', 'N_ax_start_seg']].iloc[0]
				dendr_branch_out_sec, ax_branch_out_sec, siz_sec, siz_seg = [int(m) for m in morph_locs]
			except:
				print('neuron is unlabeled in morphology file')

	if isopot_dendr_arbor:
		print(f'setting dendritic arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[dendr_branch_out_sec].subtree() 
						if sec != cell1.axon[dendr_branch_out_sec]]:
			sec.Ra = isopot_Ra_val
	if isopot_ax_arbor:
		print(f'setting axonal arbor axial resistance to {isopot_Ra_val}')
		for sec in [sec for sec in cell1.axon[ax_branch_out_sec].subtree() 
						if sec != cell1.axon[ax_branch_out_sec]]:
			sec.Ra = isopot_Ra_val
	if isopot_prim_ax:
		print(f'setting primary axon axial resistance to {isopot_Ra_val}')
		prim_ax_secs = [sec for sec in cell1.axon[siz_sec].subtree() \
						if sec not in cell1.axon[ax_branch_out_sec].subtree()[1:]]
		for sec in prim_ax_secs:
			sec.Ra = isopot_Ra_val
		'''if target_name=='local5' and target_body_id==5813105722:
			cell1.axon[1002].Ra = isopot_Ra_val
		else:
			print('need to access primary axon section number')'''
	if highpot_prim_ax: # from 'N_ax_start_sec' = siz_sec to 'N_ax_first_branch_sec'
		print(f'setting primary axon axial resistance to {highpot_Ra_val}')
		prim_ax_secs = [sec for sec in cell1.axon[siz_sec].subtree() \
						if sec not in cell1.axon[ax_branch_out_sec].subtree()[1:]]
		for sec in prim_ax_secs:
			sec.Ra = highpot_Ra_val
	if isopot_whole_nrn:
		print(f'setting entire neuron axial resistance to {isopot_Ra_val}')
		for sec in h.allsec():
			sec.Ra = isopot_Ra_val

	# calculate uEPSP size at siz and soma
	# measure uEPSP for connection at sites in measure_locs
	# activate the stim
	netstim.number = 1
	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)
	v_siz = h.Vector().record(cell1.axon[siz_sec](siz_seg)._ref_v)
	v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
	t = h.Vector().record(h._ref_t)                     				# Time stamp vector
	h.finitialize(-55 * mV)
	h.continuerun(40*ms)
	netstim.number = 0
	uEPSP_siz, uEPSP_soma = max(list(v_siz))+55, max(list(v_soma))+55
	t_trace_uEPSP = list(t)
	v_trace_uEPSP_siz, v_trace_uEPSP_soma = list(v_siz), list(v_soma)

	# first set all synapses to weight 0
	for i in range(len(list(curr_syns))):
		netcons.object(i).weight[0] = 0 # uS, peak conductance change

	# sequentially activate all input synapses
	per_synapse_data = []
	# re-run mEPSP simulation for each synapse
	for i in (range(len(list(curr_syns)))):

		# activate a single synapse
		netcons.object(i).weight[0] = syn_strength
		if i % 100 == 1:
			print("probing mEPSP for synapse " + str(i))
		# measure mEPSP for connection at pSIZ 
		# activate the stim
		netstim.number = 1
		h.load_file('stdrun.hoc')
		x = h.cvode.active(True)
		v_siz = h.Vector().record(cell1.axon[siz_sec](siz_seg)._ref_v)
		#v_axon = h.Vector().record(cell1.axon[axon_sec](axon_seg)._ref_v)
		v_soma = h.Vector().record(cell1.axon[0](0.5)._ref_v)
		v_dendr_first_branch = h.Vector().record(cell1.axon[dendr_branch_out_sec](dendr_branch_out_seg)._ref_v)
		v_ax_first_branch = h.Vector().record(cell1.axon[ax_branch_out_sec](ax_branch_out_seg)._ref_v)
		v_synloc = h.Vector().record(curr_syns.object(i).get_segment()._ref_v)
		t = h.Vector().record(h._ref_t)                     				# Time stamp vector
		h.finitialize(-55 * mV)
		h.continuerun(40*ms)	# initiate run
		netstim.number = 0
		# measure rise time of EPSP at pSIZ
		t_10to90_siz = time_to_percent_peak(t, v_siz, 0.90) - time_to_percent_peak(t, v_siz, 0.10)
		t_10to90_soma = time_to_percent_peak(t, v_soma, 0.90) - time_to_percent_peak(t, v_soma, 0.10)
		t_PNspiketo100_siz = time_to_percent_peak(t, v_siz, 0.999)
		t_PNspiketo100_dendr_first_branch = time_to_percent_peak(t, v_dendr_first_branch, 0.999)
		t_PNspiketo100_ax_first_branch = time_to_percent_peak(t, v_ax_first_branch, 0.999)
		# determine if synapse is in axon or dendrite subtree
		ax_vs_dendr_loc = 'unknown'
		if str(curr_syns.object(i).get_segment()).partition('(')[0] in \
				[str(val) for val in cell1.axon[dendr_branch_out_sec].subtree()]:
			ax_vs_dendr_loc = 'dendritic'
		elif str(curr_syns.object(i).get_segment()).partition('(')[0] in \
				[str(val) for val in cell1.axon[ax_branch_out_sec].subtree()]:
			ax_vs_dendr_loc = 'axonal'

		# if `input_name` is 'all_inputs', use `pre_nrn_info` to get actual identity of presynaptic input
		syn_input_name = input_name
		if input_name=='all_inputs':
			syn_input_name = pre_nrn_info.loc[pre_nrn_info.bodyId==pre_body_ids[i]]['type'].iloc[0]

		toAppend = {}
		''' debugging synapse.get_segment() 
		print(curr_syns.object(i).get_segment())
		loc = str(curr_syns.object(i).get_segment())
		sec_num = int(re.findall('\d+', loc)[1]) #loc.partition('axon[')[2].partition(']')[0]
		seg_num = float(re.findall('\d+', loc)[2])
		print('get_seg ', h.distance(cell1.axon[siz_sec](siz_seg), curr_syns.object(i).get_segment()))
		print('manual ', h.distance(cell1.axon[siz_sec](siz_seg), cell1.axon[sec_num](seg_num)))'''
		toAppend.update(target_name = target_name, target_body_id = target_body_id,
							input_name = syn_input_name,
							input_body_id = pre_body_ids[i], 
							synapse_number = i, syn_object = curr_syns.object(i),
							syn_loc = curr_syns.object(i).get_segment(),
							ax_v_dendr = ax_vs_dendr_loc,
							mEPSP_siz = max(list(v_siz))+55, mEPSP_soma = max(list(v_soma))+55,
							mEPSP_synloc = max(list(v_synloc))+55,
							mEPSP_t10to90_siz = t_10to90_siz,
							mEPSP_t10to90_soma = t_10to90_soma,
							mEPSP_tPNspiketo100_siz = t_PNspiketo100_siz,
							mEPSP_tPNspiketo100_dendr_first_branch = t_PNspiketo100_dendr_first_branch,
							mEPSP_tPNspiketo100_ax_first_branch = t_PNspiketo100_ax_first_branch,
							syn_count = len(curr_syns),
							local_diam = curr_syns.object(i).get_segment().diam,
							dist_to_siz = h.distance(cell1.axon[siz_sec](siz_seg), curr_syns.object(i).get_segment()),
							dist_to_soma = h.distance(cell1.axon[0](0.5), curr_syns.object(i).get_segment()),
							t_trace = list(t), v_trace_soma = list(v_soma), v_trace_siz = list(v_siz),
							v_trace_synloc = list(v_synloc),
							t_trace_uEPSP = t_trace_uEPSP,
							v_trace_uEPSP_soma = v_trace_uEPSP_soma, v_trace_uEPSP_siz = v_trace_uEPSP_siz)
		per_synapse_data.append(toAppend)

		# de-activate the synapse
		netcons.object(i).weight[0] = 0
	per_synapse_data = pd.DataFrame(per_synapse_data)

	# reset all synapse strengths before other tests:
	for i in range(len(list(curr_syns))):
		netcons.object(i).weight[0] = syn_strength # uS, peak conductance change

	# compute summation efficacy and tack them on as ATTRIBUTES of the dataframe (not columns)
	per_synapse_data.sum_eff_soma = uEPSP_soma/per_synapse_data.mEPSP_soma.sum()
	per_synapse_data.sum_eff_siz = uEPSP_siz/per_synapse_data.mEPSP_siz.sum()
	per_synapse_data.uEPSP_siz = uEPSP_siz
	per_synapse_data.uEPSP_soma = uEPSP_soma
	print(f'soma summation efficacy: {per_synapse_data.sum_eff_soma}')
	print(f'SIZ summation efficacy: {per_synapse_data.sum_eff_siz}')

	# add impedance metrics
	imp_measure_sites = ['soma', 'ax_start', 'dendr_first_branch']
	measure_locs = {'soma': (0, 0.5), 'ax_start': (siz_sec, siz_seg), 
					'dendr_first_branch': (dendr_branch_out_sec, 1)} 
					# dendr_first_branch seg set manually, in the spreadsheet they are all = 1 anyways
	for measure_site in imp_measure_sites:
		# set up Impedance measurement class
		imp = h.Impedance()
		if measure_site=='soma': 
			try: meas_sec_seg = cell1.soma[0](0.5)
			except: meas_sec_seg = cell1.axon[0](0.5)
		else: meas_sec_seg = cell1.axon[measure_locs[measure_site][0]](measure_locs[measure_site][1])
		imp.loc(meas_sec_seg)
		imp.compute(transf_freq)	# starts computing transfer impedance @ freq 

		# iterate through each synapse in the connection & measure impedance
		syn_imp_info = []
		for syn in per_synapse_data.syn_object:
			# find Z_c = transfer impedance from synapse to measure_site, # find Z_i = input impedance at synapse
			curr_transf_imp, curr_input_imp = imp.transfer(syn.get_segment()), imp.input(syn.get_segment())
			# find distance from synapse to measure_site
			curr_distance = h.distance(meas_sec_seg, syn.get_segment())
			# find voltage transfer ratio from synapse to measure_site
			curr_transf_ratio = imp.ratio(syn.get_segment())

			# record individual synapse info
			toAppend = {}
			toAppend.update(Zi = curr_input_imp)
			for meas, meas_val in zip(['dist_to_', 'Zc_to_', 'K_to_'], [curr_distance, curr_transf_imp, curr_transf_ratio]):
				toAppend[meas+measure_site] = meas_val
			syn_imp_info.append(toAppend)
		syn_imp_info = pd.DataFrame(syn_imp_info, index = per_synapse_data.index)
		print(f'adding imp. measurements to {measure_site}')
		# concatenate impedance measure columns (at this meas_site) to existing DataFrame
		for col_name, series in syn_imp_info.iteritems():
			per_synapse_data[col_name] = series
		#per_synapse_data = pd.merge(per_synapse_data, syn_imp_info, on = per_synapse_data.index)

	# add dendritic and total surface area:
	surf_area_dendr_arbor = 0
	for sec in [sec for sec in cell1.axon[dendr_branch_out_sec].subtree() \
						if sec != cell1.axon[dendr_branch_out_sec]]:
		for seg in sec:
			surf_area_dendr_arbor += seg.area()
	per_synapse_data['target_surf_area_total'] = cell1.surf_area()
	per_synapse_data['target_surf_area_dendr_arbor'] = surf_area_dendr_arbor

	if toPlot:
		fig, axs = plt.subplots(nrows = 2, ncols = 2)

		axs[0,0].scatter(per_synapse_data.dist_to_siz, per_synapse_data.mEPSP_siz)
		axs[0,0].set_xlabel('distance to SIZ (um)'), axs[0,0].set_ylabel('mEPSP @ SIZ (mV)')
		axs[0,1].scatter(per_synapse_data.local_diam, per_synapse_data.mEPSP_siz)
		axs[0,1].set_xlabel('local diameter (um)'), axs[0,1].set_ylabel('mEPSP @ SIZ (mV)')
		axs[1,0].scatter(per_synapse_data.dist_to_siz, per_synapse_data.mEPSP_t10to90_siz)
		axs[1,0].set_xlabel('distance to SIZ (um)'), axs[1,0].set_ylabel('t 10 to 90% peak @ SIZ (ms)')
		axs[1,1].scatter(per_synapse_data.local_diam, per_synapse_data.mEPSP_t10to90_siz)
		axs[1,1].set_xlabel('local diameter (um)'), axs[1,1].set_ylabel('t 10 to 90% peak @ SIZ (ms)')

		fig.suptitle(f"{input_name} inputs onto {target_name} {target_body_id}")

	return per_synapse_data

def fit_mEPSPriseT_vs_gd_ax_v_dendr(mEPSP_prop_path = '21-02-07_mEPSPs_for_all_LHNs.csv',
		plot_ax_v_dendr_slopes = True, plotLoc = 'pSIZ'):
	'''across all LHNs, compare average change in mEPSP rise time vs distance from soma
		for axonal synapses vs dendritic
		e.g. fit a line to points in mEPSP rise time vs distance from soma plot
	
	mEPSP_prop_path - string: 
		'21-01-31_mEPSPs_for_all_LHNs.csv': in end-of-Jan figure generation, used to fit
			lines to the mEPSP rise time vs distance referenced to the SOMA 
			(eventually all_LHN_mEPSP_timing_ax_vs_dendr.svg)
		'21-02-07_mEPSPs_for_all_LHNs.csv': added SIZ time PN spike to mEPSP peak

	plotLoc - string: 'soma' or 'pSIZ'
		if pSIZ, fit line to mEPSP_tPNspiketo100_siz vs distance to SIZ
		if soma, subtely different -- we use the mEPSP t10 to 90% peak at soma

	returns: 
		riseT_v_gd_fits: pd.DataFrame; for each body ID and arbor type (ax vs dendr), the
							set of relevant parameters for a linear fit to the arbor, i.e.
							slope, intercept, R^2'''

	mEPSP_props = pd.read_csv(mEPSP_prop_path)

	riseT_v_gd_fits = []
	for (lhn_name, lhn_id, ax_v_dendr), sub_df in \
			mEPSP_props.groupby(['target_name', 'target_body_id', 'ax_v_dendr']):
		if ax_v_dendr == 'unknown':
			continue

		if plotLoc == 'soma':
			rise_time_fit = stats.linregress(sub_df.dist_to_soma, sub_df.mEPSP_t10to90_soma)
		elif plotLoc == 'pSIZ':
			rise_time_fit = stats.linregress(sub_df.dist_to_siz, sub_df.mEPSP_tPNspiketo100_siz)
		toAppend = {'lhn_name': lhn_name, 'lhn_id': lhn_id, 
			'arbor_type': ax_v_dendr, 'num_points': len(sub_df.dist_to_soma),
			'slope': rise_time_fit.slope, 'intercept': rise_time_fit.intercept,
			'r^2': rise_time_fit.rvalue**2}

		riseT_v_gd_fits.append(toAppend)
	riseT_v_gd_fits = pd.DataFrame(riseT_v_gd_fits)

	if plot_ax_v_dendr_slopes:
		try:
			fig_all_LHN_mEPSP_timing_ax_vs_dendr(riseT_v_gd_fits, preload = False, plotLoc = plotLoc)
		except:
			print('plot error')

	date = datetime.today().strftime("%y-%m-%d")
	riseT_v_gd_fits.to_csv(f'{date} fit_mEPSPriseT_vs_gd_ax_v_dendr @ {plotLoc}.csv')
	return riseT_v_gd_fits	

def fig_all_LHN_mEPSP_timing_ax_vs_dendr(riseT_v_gd_fits, plotLoc = 'pSIZ', preload = True):
	'''
	plotLoc - string: pSIZ or soma, dictated by `fit_mEPSPriseT_vs_gd_ax_v_dendr` and whether
		it was fit to mEPSPs measured at the soma or SIZ
	'''
	if preload and plotLoc=='soma':
		riseT_v_gd_fits = pd.read_csv('21-01-31 fit_mEPSPriseT_vs_gd_ax_v_dendr @ soma.csv')
	elif preload and plotLoc=='pSIZ':
		riseT_v_gd_fits = pd.read_csv('21-02-07 fit_mEPSPriseT_vs_gd_ax_v_dendr @ pSIZ.csv')

	lhns_colormap = {}
	import matplotlib
	rainbow = matplotlib.cm.get_cmap('hsv')
	for i, lhn in enumerate(riseT_v_gd_fits.lhn_name.unique()):
		lhns_colormap[lhn] = rainbow(i * 1/len(riseT_v_gd_fits.lhn_name.unique()))

	fig, ax = plt.subplots(1,1, figsize = (2,2))
	for (lhn_name, lhn_id), sub_df in riseT_v_gd_fits.groupby(['lhn_name', 'lhn_id']):
		print('plotting ', lhn_name, lhn_id)
		dendr_slope = sub_df.loc[sub_df.arbor_type.str.contains('dendr')]['slope']
		ax_slope = sub_df.loc[sub_df.arbor_type.str.contains('ax')]['slope']
		try:
			if sub_df.iloc[0]['num_points'] > 2:
				ax.scatter(dendr_slope, ax_slope, color = lhns_colormap[lhn_name], s = 3)
			else:
				print(f'{lhn_name} {lhn_id} dendr and ax slope error')
		except:
			print('only axon or dendrite synapses found')

	# TODO: range to 0.05 for each
	if plotLoc == 'soma': rangemax = 0.025
	if plotLoc == 'pSIZ': rangemax = 0.05
	ax.plot([0, rangemax], [0, rangemax], color = 'grey', alpha = 0.3, ls = 'dashed')
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	ax.set(xlabel = 'dendritic rise time slope', ylabel = 'axonal rise time slope',
			xlim=(0, rangemax), ylim=(0, rangemax))
	
	plt.savefig(f'figs\\all_LHN_mEPSP_timing_ax_vs_dendr_slopes @ {plotLoc}.svg')
	plt.show()

	fig, ax = plt.subplots(1,1, figsize = (2,2))
	for (lhn_name, lhn_id), sub_df in riseT_v_gd_fits.groupby(['lhn_name', 'lhn_id']):
		print('plotting ', lhn_name, lhn_id)
		dendr_int = sub_df.loc[sub_df.arbor_type.str.contains('dendr')]['intercept']
		ax_int = sub_df.loc[sub_df.arbor_type.str.contains('ax')]['intercept']
		try:
			if sub_df.iloc[0]['num_points'] > 2:
				ax.scatter(dendr_int, ax_int, color = lhns_colormap[lhn_name], s = 3)
			else:
				print(f'{lhn_name} {lhn_id} dendr and ax intercept error')
		except:
			print('only axon or dendrite synapses found')

	# TODO: range to 7.1
	if plotLoc == 'soma': rangemax = 6
	if plotLoc == 'pSIZ': rangemax = 7.1
	ax.plot([0, rangemax], [0, rangemax], color = 'grey', alpha = 0.3, ls = 'dashed')
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	ax.set(xlabel = 'dendritic rise time intercept', ylabel = 'axonal rise time intercept',
		xlim = (0,rangemax), ylim=(0,rangemax))
	
	plt.savefig(f'figs\\all_LHN_mEPSP_timing_ax_vs_dendr_intercepts @ {plotLoc}.svg')
	plt.show()

def fig_local5_VA6_VL2a_mEPSP_timing(preload = True, toSave = False, plotLoc = 'pSIZ'):
	'''plot the mEPSP rise time vs geodesic distance for VL2a and VA6 inputs onto local5
		demonstrate that AIS implements temporal delays, i.e. even synapses of same geodesic
		distance have different rise times if on ax vs dendrite

	plotLoc - string, 'soma' or 'pSIZ':
		cellular location where the rise times and example traces are measured from
		currenty plotting somatic timing info'''

	if preload:
		# prior to updating to 21-02-07 and more SIZ measures, was 21-01-25
		syn_info_VA6 = pd.read_csv('21-02-07 syn_info_VA6.csv')
		syn_info_VL2a = pd.read_csv('21-02-07 syn_info_VL2a.csv')
		# convert list from string to list
		for df in [syn_info_VA6, syn_info_VL2a]:
			for col in ['t_trace', 'v_trace_soma', 'v_trace_siz']:
				df[col] = df[col].apply(lambda x: eval(x))
	else:
		syn_info_VA6 = probe_mEPSPs(target_name = 'local5', target_body_id = 5813105722, input_name = 'VA6_adPN',
						siz_sec = 996, siz_seg = 0.5,
						toPlot = False)
		syn_info_VL2a = probe_mEPSPs(target_name = 'local5', target_body_id = 5813105722, input_name = 'VL2a_adPN',
						siz_sec = 996, siz_seg = 0.5,
						toPlot = False)
		syn_info_VA6.to_csv('21-02-07 syn_info_VA6.csv')
		syn_info_VL2a.to_csv('21-02-07 syn_info_VL2a.csv')

	### plot scatter: mEPSP rise time vs distance from recording site (soma/SIZ)
	fig, ax = plt.subplots(1,1,figsize=(2,1.6))
	if plotLoc == 'soma':
		ax.scatter(syn_info_VA6.dist_to_soma, syn_info_VA6.mEPSP_t10to90_soma, label='VA6', 
						color='red', alpha = 0.5, s = 3)
		ax.scatter(syn_info_VL2a.dist_to_soma, syn_info_VL2a.mEPSP_t10to90_soma, label='VL2a', 
						color='blue', alpha = 0.5, s = 3)
		# fit line to VA6 and VL2a scatter
		# ONLY VA6 points <64 um from the soma (within dendritic arbor)
		va6_dist = [gd for gd in syn_info_VA6.dist_to_soma if gd < 178]
		va6_times = [t for ind, t in enumerate(syn_info_VA6.mEPSP_t10to90_soma) 
						if syn_info_VA6.dist_to_soma.iloc[ind] < 178]
		va6_t_fit = stats.linregress(va6_dist, va6_times)
		vl2a_t_fit = stats.linregress(syn_info_VL2a.dist_to_soma, syn_info_VL2a.mEPSP_t10to90_soma)
		linfit_range = np.arange(280)
		ax.plot(linfit_range, va6_t_fit.intercept + linfit_range*va6_t_fit.slope, 
					color='black', ls = 'dashed', lw=0.6)
		ax.plot(linfit_range, vl2a_t_fit.intercept + linfit_range*vl2a_t_fit.slope, 
					color='black', ls = 'dashed', lw=0.6)
		print(f'VA6 linear fit slope = {str(round(va6_t_fit.slope,4))}')
		print(f'VL2a linear fit slope = {str(round(vl2a_t_fit.slope,4))}')
		ax.set(xlabel = 'distance from soma (\u03BCm)', ylabel = 'mEPSP rise time (ms)')
	if plotLoc == 'pSIZ':
		ax.scatter(syn_info_VA6.dist_to_siz, syn_info_VA6.mEPSP_tPNspiketo100_siz, label='VA6', 
						color='red', alpha = 0.5, s = 3)
		ax.scatter(syn_info_VL2a.dist_to_siz, syn_info_VL2a.mEPSP_tPNspiketo100_siz, label='VL2a', 
						color='blue', alpha = 0.5, s = 3)
		# fit line to VA6 and VL2a scatter
		# ONLY VA6 points <64 um from the SIZ (within dendritic arbor)
		va6_dist = [gd for gd in syn_info_VA6.dist_to_siz if gd < 64]
		va6_times = [t for ind, t in enumerate(syn_info_VA6.mEPSP_tPNspiketo100_siz) 
						if syn_info_VA6.dist_to_siz.iloc[ind] < 64]
		va6_t_fit = stats.linregress(va6_dist, va6_times)
		vl2a_t_fit = stats.linregress(syn_info_VL2a.dist_to_siz, syn_info_VL2a.mEPSP_tPNspiketo100_siz)
		linfit_range = np.arange(170)
		ax.plot(linfit_range, va6_t_fit.intercept + linfit_range*va6_t_fit.slope, 
					color='black', ls = 'dashed', lw=0.6)
		ax.plot(linfit_range, vl2a_t_fit.intercept + linfit_range*vl2a_t_fit.slope, 
					color='black', ls = 'dashed', lw=0.6)
		print(f'VA6 linear fit slope = {str(round(va6_t_fit.slope,4))}')
		print(f'VL2a linear fit slope = {str(round(vl2a_t_fit.slope,4))}')
		ax.set(xlabel = 'distance from pSIZ (\u03BCm)', ylabel = 'mEPSP rise time (ms)')
	ax.set(xlim=(0,None))
	ax.spines['top'].set_visible(False), ax.spines['right'].set_visible(False)
	l = ax.legend(loc = 'upper left', frameon = False, prop = {'size': 7}, markerscale=0)
	l.get_texts()[0].set_color('red'), l.get_texts()[1].set_color('blue')

	# TODO: add best fit lines
	if toSave:
		date = datetime.today().strftime("%y-%m-%d")
		plt.savefig(f'figs\\{date} local5_VA6_VL2a_mEPSP_timing_riseTscatter @ {plotLoc}.svg')
	plt.show()

	### plot traces: closest and farthest VL2a and VA6 (restrict VA6 to dendrite MANUALLY)
	# (c/f)_(VA6/VL2a)_(t/v) = closes/farthest_VA6/VL2a_time/voltage
	if plotLoc == 'soma': v_loc, ymax, t_range = 'v_trace_soma', 104, (0.1, 0.9)
	elif plotLoc == 'pSIZ': v_loc, ymax, t_range = 'v_trace_siz', 290, (0, 0.999)
	fig, ax = plt.subplots(1,1,figsize=(2,2))
	c_VL2a_idx = syn_info_VL2a.dist_to_soma.argmin()
	f_VL2a_idx = syn_info_VL2a.dist_to_soma.argmax()
	c_VA6_idx = syn_info_VA6.dist_to_soma.argmin()
	f_VA6_idx = syn_info_VA6.index[(syn_info_VA6.dist_to_soma > 175) & (syn_info_VA6.dist_to_soma < 178)][0]
	c_VL2a_t, c_VL2a_v = syn_info_VL2a.iloc[c_VL2a_idx]['t_trace'], \
						 [(v+55)*1000 for v in syn_info_VL2a.iloc[c_VL2a_idx][v_loc]]
	f_VL2a_t, f_VL2a_v = syn_info_VL2a.iloc[f_VL2a_idx]['t_trace'], \
						 [(v+55)*1000 for v in syn_info_VL2a.iloc[f_VL2a_idx][v_loc]]
	c_VA6_t, c_VA6_v = syn_info_VA6.iloc[c_VA6_idx]['t_trace'],\
					   [(v+55)*1000 for v in syn_info_VA6.iloc[c_VA6_idx][v_loc]]
	f_VA6_t, f_VA6_v = syn_info_VA6.iloc[f_VA6_idx]['t_trace'], \
					   [(v+55)*1000 for v in syn_info_VA6.iloc[f_VA6_idx][v_loc]]
	ax.plot(c_VL2a_t, c_VL2a_v, color='blue')
	ax.plot(f_VL2a_t, f_VL2a_v, color='blue')
	ax.plot(c_VA6_t, c_VA6_v, color='red')
	ax.plot(f_VA6_t, f_VA6_v, color='red')
	ax.set(xlabel = 'time (ms)', ylabel = f'mEPSP recording at {plotLoc} (\u03BCV)',
				ylim = [-10, ymax], xlim = [0, 20]) # set range to allow for text, arrows, scalebar

	# add vertical and horizontal scale bar
	if plotLoc == 'soma': vscale = 10
	elif plotLoc == 'pSIZ': vscale = 40
	add_scalebar(ax = ax, xlen=5, ylen=vscale, xlab=' ms', ylab=' \u03BCV', loc = 'lower right')

	# add double sided arrows to denote rise times of peaks
	ax.annotate("", xy=(time_to_percent_peak(c_VL2a_t, c_VL2a_v, t_range[0]), -2), xycoords='data',
            xytext=(time_to_percent_peak(c_VL2a_t, c_VL2a_v, t_range[1]),-2), textcoords='data',
            arrowprops=dict(arrowstyle="<->",
                            connectionstyle="arc3", color='b', lw=1),)
	ax.annotate("", xy=(time_to_percent_peak(f_VL2a_t, f_VL2a_v, t_range[0]), -6), xycoords='data',
            xytext=(time_to_percent_peak(f_VL2a_t, f_VL2a_v, t_range[1]),-6), textcoords='data',
            arrowprops=dict(arrowstyle="<->",
                            connectionstyle="arc3", color='b', lw=1),)
	ax.annotate("", xy=(time_to_percent_peak(c_VA6_t, c_VA6_v, t_range[0]), ymax-4), xycoords='data',
            xytext=(time_to_percent_peak(c_VA6_t, c_VA6_v, t_range[1]), ymax-4), textcoords='data',
            arrowprops=dict(arrowstyle="<->",
                            connectionstyle="arc3", color='r', lw=1),)
	ax.annotate("", xy=(time_to_percent_peak(f_VA6_t, f_VA6_v, t_range[0]), ymax), xycoords='data',
            xytext=(time_to_percent_peak(f_VA6_t, f_VA6_v, t_range[1]), ymax), textcoords='data',
            arrowprops=dict(arrowstyle="<->",
                            connectionstyle="arc3", color='r', lw=1),)

	#time_of_perc = np.interp(perc_of_peak, np.array(v)[0:peak_loc], np.array(t)[0:peak_loc])
	# add verticle dashed lines matching arrows to curves
	# showing closest VL2a and farthest (dendritic) VA6
	def add_vline(ax, trace_t, trace_v, ylevel, color):
		ax.vlines(x=time_to_percent_peak(trace_t, trace_v, t_range[0]), ymin = ylevel, 
						ymax=np.interp(time_to_percent_peak(trace_t, trace_v, t_range[0]), trace_t, trace_v),
						colors=color, ls='dashed', alpha=0.3)
		ax.vlines(x=time_to_percent_peak(trace_t, trace_v, t_range[1]), ymin = ylevel, 
						ymax=np.interp(time_to_percent_peak(trace_t, trace_v, t_range[1]), trace_t, trace_v),
						colors=color, ls='dashed', alpha=0.3)

	add_vline(ax=ax, trace_t=c_VL2a_t, trace_v=c_VL2a_v, ylevel=-2, color='blue')
	add_vline(ax=ax, trace_t=f_VL2a_t, trace_v=f_VL2a_v, ylevel=-6, color='blue')
	add_vline(ax=ax, trace_t=c_VA6_t, trace_v=c_VA6_v, ylevel=ymax-4, color='red')
	add_vline(ax=ax, trace_t=f_VA6_t, trace_v=f_VA6_v, ylevel=ymax, color='red')

	# add text annotations
	if plotLoc == 'soma': t_loc = 'mEPSP_t10to90_soma'
	elif plotLoc == 'pSIZ': t_loc = 'mEPSP_tPNspiketo100_siz'
	ax.text(x = time_to_percent_peak(c_VA6_t, c_VA6_v, t_range[0]) + 1, y = ymax+8, size = 7, color = 'red', \
				s = f"{str(round(syn_info_VA6.iloc[c_VA6_idx][t_loc], 2))} ms" +
					f" to {str(round(syn_info_VA6.iloc[f_VA6_idx][t_loc], 2))} ms")
	ax.text(x = time_to_percent_peak(c_VA6_t, c_VA6_v, t_range[0]) + 1, y = -18, size = 7, color = 'blue', \
				s = f"{str(round(syn_info_VL2a.iloc[c_VL2a_idx][t_loc], 2))} ms" + 
					f" to {str(round(syn_info_VL2a.iloc[f_VL2a_idx][t_loc], 2))}")

	plt.tight_layout()

	if toSave:
		date = datetime.today().strftime("%y-%m-%d")
		plt.savefig(f'figs\\{date} local5_VA6_VL2a_mEPSP_timing_traces @ {plotLoc}.svg')

	plt.show()
	
	#ax[1].annotate(text='', xy=(1,1), xytext=(0,0), arrowprops=dict(arrowstyle='<->'))

#	import matplotlib.patches as patches

#	p1 = patches.FancyArrowPatch((time_to_percent_peak(c_VL2a_t, c_VL2a_v, 0.90), 
#				time_to_percent_peak(c_VL2a_t, c_VL2a_v, 0.10)), 
	#			(-2, -2), color = 'blue', arrowstyle='<->', mutation_scale=20)

	#for loc in ['top', 'right', 'left', 'bottom']:
	#	ax[1].spines[loc].set_visible(False)

	return ax

# from: https://gist.github.com/dmeliza/3251476
# Adapted from mpl_toolkits.axes_grid1
# LICENSE: Python Software Foundation (http://docs.python.org/license.html)

from matplotlib.offsetbox import AnchoredOffsetbox
class AnchoredScaleBar(AnchoredOffsetbox):
    def __init__(self, transform, sizex=0, sizey=0, labelx=None, labely=None, loc=4,
                 pad=0.1, borderpad=0.1, sep=2, prop=None, barcolor="black", barwidth=None, 
                 **kwargs):
        """
        Draw a horizontal and/or vertical  bar with the size in data coordinate
        of the give axes. A label will be drawn underneath (center-aligned).
        - transform : the coordinate frame (typically axes.transData)
        - sizex,sizey : width of x,y bar, in data units. 0 to omit
        - labelx,labely : labels for x,y bars; None to omit
        - loc : position in containing axes
        - pad, borderpad : padding, in fraction of the legend font size (or prop)
        - sep : separation between labels and bars in points.
        - **kwargs : additional arguments passed to base class constructor
        """
        from matplotlib.patches import Rectangle
        from matplotlib.offsetbox import AuxTransformBox, VPacker, HPacker, TextArea, DrawingArea
        bars = AuxTransformBox(transform)
        if sizex:
            bars.add_artist(Rectangle((0,0), sizex, 0, ec=barcolor, lw=barwidth, fc="none"))
        if sizey:
            bars.add_artist(Rectangle((0,0), 0, sizey, ec=barcolor, lw=barwidth, fc="none"))

        if sizex and labelx:
            self.xlabel = TextArea(labelx, minimumdescent=False)
            bars = VPacker(children=[bars, self.xlabel], align="center", pad=0, sep=sep)
        if sizey and labely:
            self.ylabel = TextArea(labely)
            bars = HPacker(children=[self.ylabel, bars], align="center", pad=0, sep=sep)

        AnchoredOffsetbox.__init__(self, loc, pad=pad, borderpad=borderpad,
                                   child=bars, prop=prop, frameon=False, **kwargs)

        
def add_scalebar(ax, xlen=None, ylen=None, xlab=None, ylab=None,
					matchx=True, matchy=True, 
					hidex=True, hidey=True, **kwargs):
    """ Add scalebars to axes
    Adds a set of scale bars to *ax*, matching the size to the ticks of the plot
    and optionally hiding the x and y axes
    - ax : the axis to attach ticks to
    - xlen, ylen : integers, manually set the size of the scale bars
    - xlab, ylab : string, append this label to the end of the scale bar labels
    - matchx,matchy : if True, set size of scale bars to spacing between ticks
                    if False, size should be set using sizex and sizey params
    - hidex,hidey : if True, hide x-axis and y-axis of parent
    - **kwargs : additional arguments passed to AnchoredScaleBars
    Returns created scalebar object
    """
    def f(axis):
        l = axis.get_majorticklocs()
        return len(l)>1 and (l[1] - l[0])
    
    if xlen:
    	kwargs['sizex'] = xlen
    	kwargs['labelx'] = str(kwargs['sizex']) + xlab
    elif matchx:
        kwargs['sizex'] = f(ax.xaxis)
        kwargs['labelx'] = str(kwargs['sizex'])
    if ylen:
    	kwargs['sizey'] = ylen
    	kwargs['labely'] = str(kwargs['sizey']) + ylab
    elif matchy:
        kwargs['sizey'] = f(ax.yaxis)
        kwargs['labely'] = str(kwargs['sizey'])
        
    sb = AnchoredScaleBar(ax.transData, **kwargs)
    ax.add_artist(sb)

    if hidex : ax.xaxis.set_visible(False)
    if hidey : ax.yaxis.set_visible(False)
    if hidex and hidey: ax.set_frame_on(False)

    return sb

def sim_DM1(params = 'Gouwens'):
	'''
		Simulate a uEPSP to the DM1 neuron from the hemibrain, to compare 
		attenuation between the hemibrain version and the Gouwens version
		Goal: to understand how true is Gouwens' claim that:
			"EPSPs still did not cause substantial voltage changes at the axon terminals"
		Our results suggest that fly neurons, including PNs, are electrotonically compact
		enough that EPSPs would cause substantial voltage changes

		params: 'Gouwens' for Gouwens 2009 parameters
				'our fit' for our population-level MC model fit parameters
	'''

	# change to path for hemibrain DM1 
	swc_path = "swc\\DM1-542634818_hemibrain.swc"

	# biophysical parameters from Gouwens or from our fits
	if params == 'Gouwens':
		R_a = 266.1
		c_m = 0.79
		g_pas = 4.8e-5
		e_pas = -60
		syn_strength = 0.00027 # uS, peak synaptic conductance, g_syn
	elif params == 'our fit':
		R_a = 350
		c_m = 0.6
		g_pas = 5.8e-5
		e_pas = -60 # one parameter left same in both, we used -55 in our fits
		syn_strength = 5.5e-5 # uS

	cell1 = Cell(swc_path, 0) # first argument is name of swc file, second is a gid'
	cell1.discretize_sections()
	cell1.add_biophysics(R_a, c_m, g_pas, e_pas) # ra, cm, gpas, epas
	cell1.tree = cell1.trace_tree()

	# from using Point Group GUI to find sections in dendrite, randomly chosen to mimic fig 6D
	syn_secs = [2894, 2479, 6150, 2716, 6037, 5259, 3611, 5178, 5100, 5036, 4947, 4436, 2637,
				2447, 3838, 2873, 4780, 6468, 3297, 2435, 4073, 2438, 6119, 4476, 2768]

	syns = h.List()
	for i in range(len(syn_secs)):
		syns.append(h.Exp2Syn(cell1.axon[syn_secs[i]](0.5)))
		### synapse parameters from Tobin et al paper: 
		syns.object(i).tau1 = 0.2 #ms
		syns.object(i).tau2 = 1.1 #ms
		syns.object(i).e = -10 #mV, synaptic reversal potential = -10 mV for acetylcholine? 

	### use NetStim to activate NetCon
	nc = h.NetStim()
	nc.number = 1
	nc.start = 0
	nc.noise = 0

	ncs = h.List()
	for i in range(len(list(syns))):
		ncs.append(h.NetCon(nc, syns.object(i)))
		ncs.object(i).weight[0] = syn_strength # uS, peak conductance change

	### measure the depolarization at the synapse locations, and at a few points in the distal axon
	### compare the attenuation for both Gouwens and the hemibrain DM1

	h.load_file('stdrun.hoc')
	x = h.cvode.active(True)

	# establish recordings at all input synapse locations
	v_input = []
	for i in range(len(list(syns))):
		record_loc = syns.object(i).get_segment()
		v_input.append(h.Vector().record(record_loc._ref_v))

	# establish recordings at a few axon locations, in both MB and LH
	v_record = []
	axon_secs = [2094, 1925, 1878, 1740, 647, 896, 1339, 1217]
	for i in range(len(axon_secs)):
		v_record.append(h.Vector().record(cell1.axon[axon_secs[i]](0.5)._ref_v))

	v_soma = h.Vector().record(cell1.soma[0](0.75)._ref_v) 		# soma membrane potential
	t = h.Vector().record(h._ref_t)                     # Time stamp vector

	h.finitialize(-60 * mV)
	h.continuerun(60*ms)

	# plot

	plt.rcParams["figure.figsize"] = (15,15)
	plt.plot(list(t), list(v_soma), color = 'red', label = 'soma recording')
	for trace in v_input:
		if v_input.index(trace) == 0:
			plt.plot(list(t), list(trace), color = 'blue', label = 'synapse site recording')
		else:
			plt.plot(list(t), list(trace), color = 'blue')
	for trace in v_record:
		if v_record.index(trace) == 0:
			plt.plot(list(t), list(trace), color = 'green', label = 'axon site recording')
		else:
			plt.plot(list(t), list(trace), color = 'green')
	plt.xlabel('time (ms)')
	plt.ylim([-60, -40])
	plt.ylabel('membrane potential (mV)')
	plt.legend(loc = 'upper right')
	plt.title('Hemibrain DM1 uEPSP, parameters from {}'.format(params))
	plt.show()

	# print area
	print("DM1 area: {} um^2".format(str(cell1.surf_area())))

def find_KC_classes():
	'''
		cycle through folder of KC SWCs, pull out body IDs and search for their subclasses
		output csv of body ID and KC 
	'''
	print('todo')

'''
Past parameter fits: 

# 20-10-05 tile other portion of g_pas w/ finer granularity of R_a
# 8 * 4 * 12 * 13 = 4992
#syn_strength_s = [2.5e-5, 3.0e-5, 3.5e-5, 4.0e-5, 4.5e-5, 5.0e-5, 5.5e-5, 6.0e-5]
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.2e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 25) # ohm-cm 
# ended 20-10-07

# 20-10-01 tile other portion of R_a
# 8 * 4 * 13 * 6 = 2496
#syn_strength_s = [2.5e-5, 3.0e-5, 3.5e-5, 4.0e-5, 4.5e-5, 5.0e-5, 5.5e-5, 6.0e-5]
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(75, 351, 50) # ohm-cm 
# start time: 20-10-01-01:59:30, end time: 20-10-02-12:14:34

# 20-09-27 after refreshing body IDs after Pasha's final revisions, saving all_resids
# 8 * 4 * 13 * 7 = 2912
#syn_strength_s = [2.5e-5, 3.0e-5, 3.5e-5, 4.0e-5, 4.5e-5, 5.0e-5, 5.5e-5, 6.0e-5]
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 50) # ohm-cm 

# 20-09-27 after refreshing body IDs after Pasha's final revisions, saving all_resids
# 8 * 4 * 13 * 7 = 2912
#syn_strength_s = [2.5e-5, 3.0e-5, 3.5e-5, 4.0e-5, 4.5e-5, 5.0e-5, 5.5e-5, 6.0e-5]
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.9e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 50) # ohm-cm 
# ended 20-09-29

# 20-09-13_broader search range: 
# 4 x 4 x 12 x 7 = 1344 + 144 from previous search!
#syn_strength_s = [3.0e-5, 4.0e-5, 5.0e-5, 5.5e-5]
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.8e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 50) # ohm-cm

# 20-09-12_after changing error term to peak residual sum of squares PER connection: 
# 2 x 3 x 6 x 4 = 144
#syn_strength_s = np.arange(0.000035, 0.000046, 0.00001) # uS
#c_m_s = np.arange(0.6, 1.21, 0.3) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.8e-5, 0.8e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 100) # ohm-cm

# 20-09-10_refit after local5 reverted to v1.1
# 1440
#syn_strength_s = np.arange(0.000030, 0.000056, 0.000005) # uS
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.8e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 75) # ohm-cm

# 20-09-04_change syn conductance: 1:28am to 
#syn_strength_s = np.arange(0.0000325, 0.00005, 0.000005) # uS
#c_m_s = np.arange(0.6, 1.21, 0.2) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.8e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 75) # ohm-cm
# define g_pas and R_a

# 20-08-31_larger_param_search
#c_m_s = np.arange(1.0, 1.21, 0.1) # uF/cm^2
#g_pas_s = np.arange(1.0e-5, 5.4e-5, 0.2e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 351, 25) # ohm-cm

# 20-08-31_small_param_search: 11*6*105 = 6930 possibilities
#g_pas_s = np.arange(1.2e-5, 5.4e-5, 0.4e-5) # S/cm^2, round to 6 places
#R_a_s = np.arange(50, 350, 50) # ohm-cm

'''

'''
filename = "swc\\local6-356467849.swc"
#def instantiate_swc(filename):
"""load an swc file and instantiate it"""

# a helper library, included with NEURON
h.load_file('import3d.hoc')

# load the data. Use Import3d_SWC_read for swc, Import3d_Neurolucida3 for
# Neurolucida V3, Import3d_MorphML for MorphML (level 1 of NeuroML), or
# Import3d_Eutectic_read for Eutectic. (There is also an 
# Import3d_Neurolucida_read for old Neurolucida files, but I've never seen one
# in practice; try Import3d_Neurolucida3 first.)
cell = h.Import3d_SWC_read()
cell.input(filename)

# easiest to instantiate by passing the loaded morphology to the Import3d_GUI
# tool; with a second argument of 0, it won't display the GUI, but it will allow
# use of the GUI's features
i3d = h.Import3d_GUI(cell, 0)
i3d.instantiate(None)
#i3d.cbexport()
'''

# If you have a CellBuilder cb, the management tab options are in cb.manage, 
# and the main function for exporting as a HOC template is cb.manage.save_class.
# cb = h.CellBuild(0)

### LEGACY Code:
'''
### select LHN
	if which_LHN == "local6":
		if which_LHN_vers == 1:
			LHN_ID = 'local6-356467849'
		elif which_LHN_vers == 2:
			LHN_ID = 'local6-417186656'
		elif which_LHN_vers == 3:
			LHN_ID = 'local6-479917037'
		elif which_LHN_vers == 4:
			LHN_ID = 'local6-418865948'
	if which_LHN == "local5":
		if which_LHN_vers == 1:
			LHN_ID = 'local5-5813105722'
		elif which_LHN_vers == 2:
			LHN_ID = 'local5-696126258'
	if which_LHN == "local2":
		if which_LHN_vers == 1:
			LHN_ID = 'local2-5813055963'
		elif which_LHN_vers == 2:
			LHN_ID = 'local2-666450841'
	if which_LHN == "L1":
		if which_LHN_vers == 1:
			LHN_ID = 'L1-483716037'
	if which_LHN == "L12":
		if which_LHN_vers == 1:
			LHN_ID = 'L12-5813077898'
	if which_LHN == "L13":
		if which_LHN_vers == 1:
			LHN_ID = 'L13-793702856'
	if which_LHN == "ML3":
		if which_LHN_vers == 1:
			LHN_ID = 'ML3-574040939'
	if which_LHN == "ML8":
		if which_LHN_vers == 1:
			LHN_ID = 'ML8-509928512'
	if which_LHN == "ML9":
		if which_LHN_vers == 1:
			LHN_ID = 'ML9-640963556'
		if which_LHN_vers == 2:
			LHN_ID = 'ML9-573337611'
	if which_LHN == "V2":
		if which_LHN_vers == 1:
			LHN_ID = 'V2-1037510115'
	if which_LHN == "V3":
		if which_LHN_vers == 1:
			LHN_ID = 'V3-915724147'

	### select PN
	if which_PN == "DA4l":
		PN_ID = 'DA4l-544021095'
	if which_PN == "VA6":
		PN_ID = "VA6-1881751117"
	if which_PN == "VL2a":
		PN_ID = "VL2a-5813069089"
	if which_PN == "VL2p":
		PN_ID = "VL2p-1944507292"
	if which_PN == "DL5":
		PN_ID = "DL5-693483018"
	if which_PN == "DM1":
		PN_ID = "DM1-542634818"
	if which_PN == "DM4":
		PN_ID = "DM4-573333835"
	if which_PN == "DP1m":
		PN_ID = "DP1m-635062078"
	if which_PN == "VA2":
		PN_ID = "VA2-1977579449"
	if which_PN == "VC1":
		PN_ID = "VC1-606090268"
'''