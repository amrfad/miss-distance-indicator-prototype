"""
ECCCT Module: Envelope Cross-Correlation with Closure Tuning
Mengimplementasikan ekstraksi envelope daya, decimasi, korelasi silang sub-bin parabolik,
dan Gauss-Seidel geometric closure tuning untuk estimasi TDOA tahan distorsi Doppler supersonik.
"""

from typing import Dict, List, Tuple, Optional
import numpy as np


def boxcar_smooth(x: np.ndarray, width_s: float, fs: int) -> np.ndarray:
    """
    Moving-average boxcar smoothing 1D / 2D sepanjang sumbu waktu (axis=0).
    
    Args:
        x: Array 1D (n_samples,) atau 2D (n_samples, n_channels)
        width_s: Lebar jendela smoothing dalam detik
        fs: Sampling rate dalam Hz
        
    Returns:
        Array dengan bentuk sama setelah di-smooth
    """
    w = max(1, int(round(width_s * fs)))
    if w < 2:
        return x.copy()
    
    kernel = np.ones(w, dtype=float) / w
    
    if x.ndim == 1:
        return np.convolve(x, kernel, mode="same")
    
    out = np.zeros_like(x, dtype=float)
    for ch in range(x.shape[1]):
        out[:, ch] = np.convolve(x[:, ch], kernel, mode="same")
    return out


def extract_envelope_curves(
    signals: np.ndarray,
    fs: int,
    smooth_ms: float = 2.0,
    dec: int = 10,
    eps: float = 1e-12
) -> np.ndarray:
    """
    Mengekstrak kurva amplitude envelope daya ter-decimasi dari sinyal multichannel.
    Ternormalisasi global antar seluruh mikrofon untuk mempertahankan rasio energi spasial.
    
    Args:
        signals: Array sinyal audio (n_samples, n_channels)
        fs: Sampling rate dalam Hz
        smooth_ms: Lebar smoothing boxcar dalam milidetik (default: 2.0 ms)
        dec: Faktor desimasi (default: 10, misal 48 kHz -> 4.8 kHz)
        eps: Nilai epsilon untuk stabilitas numerik
        
    Returns:
        Array envelope E berbentuk (n_channels, n_decimated_samples)
    """
    n_samples, n_channels = signals.shape
    
    # 1. Power signal: kuadrat dari sinyal per channel
    power = signals ** 2
    
    # 2. Boxcar smoothing
    smoothed_power = boxcar_smooth(power, smooth_ms * 1e-3, fs)
    
    # 3. Decimasi dan akar kuadrat amplitudo
    decimated_curves = []
    p_max = 0.0
    
    for ch in range(n_channels):
        p_ch = smoothed_power[:, ch]
        p_dec = p_ch[::dec]
        if p_dec.size == 0:
            p_dec = np.zeros(1, dtype=float)
        r_ch = np.sqrt(np.clip(p_dec, 0.0, None))
        decimated_curves.append(r_ch)
        max_val = np.max(r_ch) if r_ch.size > 0 else 0.0
        if max_val > p_max:
            p_max = max_val
            
    # 4. Normalisasi global lintas kanal
    norm_factor = p_max + eps
    E = np.array([r / norm_factor for r in decimated_curves], dtype=float)
    return E


def cross_correlation_envelope_tdoa(
    env1: np.ndarray,
    env2: np.ndarray,
    fs: int,
    dec: int = 10
) -> Tuple[float, float]:
    """
    Menghitung TDOA antar dua kurva envelope menggunakan cross-correlation penuh
    dan interpolasi parabolik sub-bin (tanpa PHAT whitening).
    
    Konvensi tanda:
        tau_ij = t_i - t_j (positif jika mic1 menerima event lebih lambat dari mic2).
        
    Args:
        env1: Kurva envelope mikrofon 1 (1D array)
        env2: Kurva envelope mikrofon 2 (1D array)
        fs: Sampling rate asli sinyal (Hz)
        dec: Faktor desimasi
        
    Returns:
        tuple (tau_seconds, peak_correlation)
    """
    if len(env1) == 0 or len(env2) == 0:
        return 0.0, 0.0
        
    # Zero-mean agar tidak terbias oleh DC offset envelope
    a = env1 - np.mean(env1)
    b = env2 - np.mean(env2)
    n = len(a)
    
    if np.all(a == 0) or np.all(b == 0):
        return 0.0, 0.0
        
    r = np.correlate(a, b, mode="full")
    p = int(np.argmax(r))
    
    # Refinemen sub-bin parabolik di sekitar puncak integer
    alpha = 0.0
    if 1 <= p < len(r) - 1:
        denom = 2.0 * (r[p - 1] - 2.0 * r[p] + r[p + 1])
        if abs(denom) > 1e-12:
            alpha = (r[p - 1] - r[p + 1]) / denom
            alpha = float(np.clip(alpha, -0.5, 0.5))
            
    # Konversi lag diskrit ter-decimasi ke detik
    lag_frac = (p + alpha - (n - 1)) * dec / fs
    return float(lag_frac), float(r[p])


def closure_tune(
    tdoa_dict: Dict[Tuple[int, int], float],
    num_mics: int,
    max_iter: int = 50,
    tol: float = 1e-9
) -> Tuple[Dict[Tuple[int, int], float], float, float]:
    """
    Gauss-Seidel Closure Tuning:
    Memaksa konsistensi geometri segitiga (tau_ij + tau_jk = tau_ik) pada matriks TDOA.
    
    Untuk setiap pasangan (i, j), perbarui TDOA menuju rata-rata prediksi
    dari seluruh jalur segitiga k yang melibatkannya:
      T[i,j] -> T[i,j] + 0.5 * (mean_k(T[i,k] - T[j,k]) - T[i,j])
      
    Args:
        tdoa_dict: Dictionary {(i, j): tau_detik} dengan i < j
        num_mics: Jumlah mikrofon aktif M
        max_iter: Jumlah iterasi maksimum
        tol: Batas konvergensi perubahan maksimum
        
    Returns:
        tuple (tdoa_tuned_dict, residual_before, residual_after)
    """
    M = num_mics
    T = np.zeros((M, M), dtype=float)
    known = np.zeros((M, M), dtype=bool)
    
    for (i, j), val in tdoa_dict.items():
        if i < M and j < M:
            T[i, j] = val
            T[j, i] = -val
            known[i, j] = True
            known[j, i] = True
            
    def compute_closure_residual(mat: np.ndarray) -> float:
        tot = 0.0
        for i in range(M):
            for j in range(M):
                if not known[i, j]:
                    continue
                for k in range(M):
                    if known[j, k] and known[i, k]:
                        tot += abs(mat[i, j] + mat[j, k] - mat[i, k])
        return tot
        
    r0 = compute_closure_residual(T)
    Tn = T.copy()
    
    for _ in range(max_iter):
        delta = 0.0
        for i in range(M):
            for j in range(M):
                if i == j or not known[i, j]:
                    continue
                preds = []
                for k in range(M):
                    if k == i or k == j:
                        continue
                    if known[i, k] and known[j, k]:
                        preds.append(Tn[i, k] - Tn[j, k])
                if preds:
                    target = np.mean(preds)
                    new_val = Tn[i, j] + 0.5 * (target - Tn[i, j])
                    diff = abs(new_val - Tn[i, j])
                    if diff > delta:
                        delta = diff
                    Tn[i, j] = new_val
                    Tn[j, i] = -new_val
        if delta < tol:
            break
            
    r1 = compute_closure_residual(Tn)
    
    out = {}
    for (i, j) in tdoa_dict:
        if i < M and j < M:
            out[(i, j)] = float(Tn[i, j])
        else:
            out[(i, j)] = tdoa_dict[(i, j)]
            
    return out, r0, r1
