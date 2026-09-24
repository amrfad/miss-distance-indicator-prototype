import numpy as np
import itertools
from scipy.signal import correlate
from ..core.config_manager import get_global_config_manager
from .eccct import (
    extract_envelope_curves,
    cross_correlation_envelope_tdoa,
    closure_tune,
)

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

def calculate_all_tdoa_eccct(data, fs, channel_indices=None, smooth_ms=2.0, dec=10, do_closure=True):
    """
    Menghitung TDOA menggunakan metode ECCCT:
    1. Ekstraksi power envelope per mic dengan boxcar smoothing (2 ms)
    2. Decimasi x10 dan normalisasi global
    3. Pairwise cross-correlation dengan interpolasi parabolik sub-bin
    4. Gauss-Seidel closure tuning untuk memaksa konsistensi geometri segitiga
    
    Args:
        data (np.ndarray): Audio data (n_samples, n_channels)
        fs (int): Sampling rate (Hz)
        channel_indices (list, optional): List index physical channel yang aktif
        smooth_ms (float): Smoothing envelope (ms)
        dec (int): Faktor desimasi
        do_closure (bool): Terapkan Gauss-Seidel closure tuning
        
    Returns:
        dict: Dictionary pasangan TDOA {"micX-micY": tau_detik}
    """
    n_channels = data.shape[1]
    physical_indices = list(channel_indices) if channel_indices else list(range(n_channels))
    n_active = len(physical_indices)
    
    if n_active < 2:
        return {}
        
    # Ambil matriks data hanya untuk channel aktif
    active_data = data[:, physical_indices]
    
    # 1 & 2: Ekstraksi kurva envelope ternormalisasi global (M, K)
    E = extract_envelope_curves(active_data, fs, smooth_ms=smooth_ms, dec=dec)
    
    # 3: Pairwise envelope cross-correlation
    logical_pairs = list(itertools.combinations(range(n_active), 2))
    raw_tdoa = {}
    
    for log_idx1, log_idx2 in logical_pairs:
        # Cek jika sinyal silent/kosong
        sig1 = active_data[:, log_idx1]
        sig2 = active_data[:, log_idx2]
        if np.max(np.abs(sig1)) < 1e-6 or np.max(np.abs(sig2)) < 1e-6:
            tau = 0.0
        else:
            tau, _ = cross_correlation_envelope_tdoa(E[log_idx1], E[log_idx2], fs=fs, dec=dec)
        raw_tdoa[(log_idx1, log_idx2)] = tau
        
    # 4: Geometric closure tuning
    final_tdoa = raw_tdoa
    if do_closure and n_active >= 3:
        final_tdoa, _, _ = closure_tune(raw_tdoa, num_mics=n_active)
        
    results = {}
    for log_idx1, log_idx2 in logical_pairs:
        tau_val = final_tdoa.get((log_idx1, log_idx2), 0.0)
        key = f"mic{log_idx1}-mic{log_idx2}"
        results[key] = round(float(tau_val), 7)
        
    return results

def calculate_all_tdoa(data, fs, channel_indices=None):
    """
    Menghitung TDOA untuk semua pasangan channel.
    Mendukung metode:
      - 'eccct': Envelope Cross-Correlation with Closure Tuning (rekomendasi untuk proyektil supersonik)
      - 'gcc_phat': Generalized Cross-Correlation with Phase Transform
      - 'cross_correlation': Standard cross-correlation
      
    Args:
        data (np.ndarray): Audio data (n_samples, n_channels)
        fs (int): Sampling rate
        channel_indices (list, optional): List index channel yang aktif. 
                                          Jika None, gunakan semua channel di data.
                                          
    Returns:
        dict: Dictionary berisi TDOA untuk setiap pasangan (key: "micX-micY")
    """
    cfg = get_global_config_manager().get_config()
    tdoa_method = cfg.get("tdoa_method", "eccct").lower()
        
    if tdoa_method == "eccct":
        smooth_ms = cfg.get("env_smooth_ms", 2.0)
        dec = cfg.get("env_decimation", 10)
        do_closure = cfg.get("do_closure_tuning", True)
        return calculate_all_tdoa_eccct(
            data, fs,
            channel_indices=channel_indices,
            smooth_ms=smooth_ms,
            dec=dec,
            do_closure=do_closure
        )

    # Metode standar (GCC-PHAT atau Cross-Correlation)
    n_channels = data.shape[1]
    if channel_indices:
        physical_indices = channel_indices
    else:
        physical_indices = range(n_channels)
        
    n_active = len(physical_indices)
    logical_pairs = list(itertools.combinations(range(n_active), 2))
    
    results = {}
    
    for log_idx1, log_idx2 in logical_pairs:
        phys_idx1 = physical_indices[log_idx1]
        phys_idx2 = physical_indices[log_idx2]
        
        if phys_idx1 >= n_channels or phys_idx2 >= n_channels:
            continue
            
        sig1 = data[:, phys_idx1]
        sig2 = data[:, phys_idx2]
        
        if np.max(np.abs(sig1)) < 1e-6 or np.max(np.abs(sig2)) < 1e-6:
            tdoa = 0.0
        else:
            if tdoa_method == "gcc_phat":
                tdoa = calculate_tdoa_gcc_phat(sig1, sig2, fs)
            else:
                tdoa = calculate_cross_correlation(sig1, sig2, fs)
            
        key = f"mic{log_idx1}-mic{log_idx2}"
        results[key] = round(float(tdoa), 7)
        
    return results

