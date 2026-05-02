import numpy as np
import itertools
from scipy.signal import correlate
from .config import IS_GCC_PHAT

def calculate_tdoa_gcc_phat(sig1, sig2, fs):
    """
    Menghitung TDOA menggunakan GCC-PHAT.
    
    Args:
        sig1 (np.ndarray): Sinyal mikrofon 1
        sig2 (np.ndarray): Sinyal mikrofon 2
        fs (int): Sampling rate
        
    Returns:
        float: TDOA dalam detik
    """
    n = len(sig1) + len(sig2) - 1
    n_fft = 2 ** int(np.ceil(np.log2(n)))
    
    sig1_pad = np.pad(sig1, (0, n_fft - len(sig1)))
    sig2_pad = np.pad(sig2, (0, n_fft - len(sig2)))
    
    X1 = np.fft.fft(sig1_pad)
    X2 = np.fft.fft(sig2_pad)
    
    eps = 1e-10
    G_phat = (X1 * np.conj(X2)) / (np.abs(X1 * np.conj(X2)) + eps)
    
    correlation = np.fft.ifft(G_phat)
    correlation = np.real(correlation)
    correlation_shifted = np.fft.fftshift(correlation)
    
    lags = np.arange(-n_fft // 2, n_fft // 2)
    peak_index = np.argmax(correlation_shifted)
    lag_samples = lags[peak_index]
    
    return lag_samples / fs

def calculate_cross_correlation(sig1, sig2, fs):
    s1 = np.asarray(sig1, dtype=float)
    s2 = np.asarray(sig2, dtype=float)

    corr = correlate(s1, s2, mode="full")
    lags = np.arange(-(len(s2)-1), len(s1))
    peak_idx = np.argmax(corr)
    lag_samples = lags[peak_idx]
    return float(lag_samples) / float(fs)

def calculate_all_tdoa(data, fs, channel_indices=None):
    """
    Menghitung TDOA untuk semua pasangan channel.
    
    Jumlah pasangan TDOA bergantung pada jumlah microphone:
    - 4 mic: C(4,2) = 6 pasang TDOA
    - 6 mic: C(6,2) = 15 pasang TDOA
    
    Args:
        data (np.ndarray): Audio data (n_samples, n_channels)
        fs (int): Sampling rate
        channel_indices (list, optional): List index channel yang aktif. 
                                          Jika None, gunakan semua channel di data.
                                          
    Returns:
        dict: Dictionary berisi TDOA untuk setiap pasangan (key: "micX-micY")
              Contoh untuk 6 mic: mic0-mic1, mic0-mic2, ..., mic4-mic5
    """
    n_channels = data.shape[1]
    
    # Tentukan mapping dari logical index (0,1,2...) ke physical index (channel_indices)
    if channel_indices:
        physical_indices = channel_indices
    else:
        physical_indices = range(n_channels)
        
    # Generate kombinasi berdasarkan logical index (0..N-1)
    # Agar outputnya mic0-mic1, mic0-mic2, dst.
    n_active = len(physical_indices)
    logical_pairs = list(itertools.combinations(range(n_active), 2))
    
    results = {}
    
    for log_idx1, log_idx2 in logical_pairs:
        phys_idx1 = physical_indices[log_idx1]
        phys_idx2 = physical_indices[log_idx2]
        
        # Pastikan index valid
        if phys_idx1 >= n_channels or phys_idx2 >= n_channels:
            continue
            
        sig1 = data[:, phys_idx1]
        sig2 = data[:, phys_idx2]
        
        # Skip jika sinyal kosong/silent (opsional check)
        if np.max(np.abs(sig1)) < 1e-6 or np.max(np.abs(sig2)) < 1e-6:
            tdoa = 0.0
        else:
            if IS_GCC_PHAT:
                tdoa = calculate_tdoa_gcc_phat(sig1, sig2, fs)
            else:
                tdoa = calculate_cross_correlation(sig1, sig2, fs)
            
        key = f"mic{log_idx1}-mic{log_idx2}"
        results[key] = tdoa
        
    return results
