import numpy as np

SIZE = 32
LENGTHS = (256., 32., 4.)


def seeds(speed, direction, fetch, spread):
    rng = np.random.default_rng(1729)
    bands = []
    for band, length in enumerate(LENGTHS):
        dk = 2*np.pi/length
        x,z = np.meshgrid(np.fft.fftfreq(SIZE)*SIZE*dk,np.fft.fftfreq(SIZE)*SIZE*dk)
        k = np.maximum(np.hypot(x,z),1e-12)
        omega = np.sqrt(9.81*k)
        peak = 22*(9.81**2/(max(speed,0.01)*fetch))**(1/3)
        sigma = np.where(omega<peak,0.07,0.09)
        gamma = 3.3**np.exp(-0.5*((omega-peak)/(sigma*peak))**2)
        alpha = 0.076*(max(speed,0.01)**2/(fetch*9.81))**0.22
        spectrum = alpha*9.81**2/omega**5*np.exp(-1.25*(peak/omega)**4)*gamma
        theta = np.arctan2(z,x)-direction
        angles = np.arange(2048)*2*np.pi/2048
        norm = np.maximum(0,np.cos(angles))**spread
        angular = np.maximum(0,np.cos(theta))**spread/(2*np.pi*norm.mean())
        def fade(low, high):
            t = np.clip((k-low)/(high-low),0,1)
            return t*t*(3-2*t)
        a,b = fade(.20,.35),fade(1.6,2.8)
        weight = (1-a,a-b,b)[band]
        variance = spectrum*angular*weight*dk**2*omega/(2*k*k)
        phase = (rng.normal(size=k.shape)+1j*rng.normal(size=k.shape))*np.sqrt(variance/4)
        phase[0,0]=0
        phase[SIZE//2,:]=phase[:,SIZE//2]=0
        bands.append(phase*bool(speed))
    return np.stack(bands).astype(np.complex64)
