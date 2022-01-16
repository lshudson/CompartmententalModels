function V=realNcompartmentModel(Gsyn_dend,Gsyn_axon,r,cablelength,meanDendriteSurfAreaCM2,meanAxonSurfAreaCM2)
%Set simulation parameters
numTimeSteps = 1000;
dt = 0.0001; %in seconds
%timevec = dt:dt:dt*numTimeSteps;

%Set parameters for connecting cable:
%r = 0.25 * (1/10000);    %in cm: radius of cable;
delta_x = 1 * (1/10000); %in cm. length step of cable.
totalSegments = cablelength; %102;     %each segment is isopotential. 1st segment is dendrite compartment, last segment is axon compartment.

%Set basic electrical properties (in units normalized to surface area or length):
rho_i = 350   ; %ohm-cm (specific resistance of each segment)
g_L = 5.8e-5  ; %1/(ohm-cm2): leak conductance through the membrane.
cm = 0.6*1e-6 ; %in uF/cm2: capacitance per unit area of membrane.

%Set specific electrical properties (in "true" units):
RA = (rho_i * delta_x /pi/r^2);
R  = (2*pi*r*delta_x*g_L)      *ones(1,totalSegments);
C  = 2*pi*r*delta_x*cm         *ones(1,totalSegments);

%define size of axon and dendrite compartments:
%meanDendriteSurfAreaCM2 = 1.2537e-05;
%meanAxonSurfAreaCM2 = 5.3566e-06;
%meanPrimaryAxonLengthCM = 0.0108;
%meanPrimaryAxonDiameterCM = 5.1422e-05;

R(totalSegments)=g_L* meanAxonSurfAreaCM2;
C(totalSegments)=meanAxonSurfAreaCM2*cm;
R(1)=g_L*meanDendriteSurfAreaCM2;
C(1)=meanDendriteSurfAreaCM2*cm;

%define synaptic conductance waveform.
% n_syn = 100; %number of synapses for a connection.
% 
% tau1 = 0.2/1000; %in seconds;
% tau2 = 1.1/1000; %in seconds
% weight = 55e-12*n_syn; %in siemens. (on the order of picosiemens)
% factor = 1;
% Gsyn_raw = (exp(-timevec/tau2) - exp(-timevec/tau1));
% Gsyn = (Gsyn_raw/max(Gsyn_raw)) * weight;

%Initialize voltage vector.
V = zeros(numTimeSteps,totalSegments);

%run simulation.
for t = 1:numTimeSteps-1 %time iterator
    
    %Backward Euler integration. (See Hines and Carnevale, NEURON book for
    %details)
    
    %define system of equations.
    A = zeros(totalSegments,totalSegments);
    %build A matrix
    for m = 2:totalSegments-1
        A(m,m-1:m+1) = [-dt/C(m)/RA (1+dt/C(m)*(R(m)+(2/RA))) -dt/C(m)/RA];
    end
    A(1,1:2) = [(1+dt/C(1)*(R(1)+(1/RA))) -dt/C(1)/RA];
    A(totalSegments,totalSegments-1:totalSegments) = [-dt/C(totalSegments)/RA (1+dt/C(totalSegments)*(R(totalSegments)+(1/RA)))];
    
    b = V(t,:)';
    newValues = A\b;%inv(A)*b; %solve the system of equations for V(t+1) values.
    V(t+1,:) = newValues;
    
    Isyn_dend(t+1) = Gsyn_dend(t+1) * (0.045 - V(t+1,1) );
    Isyn_axon(t+1) = Gsyn_axon(t+1) * (0.045 - V(t+1,totalSegments) );
    
    V(t+1,1) = V(t+1,1)+Isyn_dend(t+1)*dt/C(1);
    V(t+1,totalSegments) = V(t+1,totalSegments)+Isyn_axon(t+1)*dt/C(totalSegments);
end

%figure
plot(dt:dt:dt*numTimeSteps, 1000*V(:,[1 end])')




