"""
Deep FFT/spectral analysis of ASH_COATED_OSMIUM to find seasonal/cyclical patterns.
"""
import numpy as np
import matplotlib.pyplot as plt
import csv
from collections import defaultdict


def load_aco_mids(filepath):
    """Extract ACO mid prices from price CSV, filtering bad ticks."""
    timestamps = []
    mids = []
    with open(filepath) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row['product'] == 'ASH_COATED_OSMIUM':
                ts = int(row['timestamp'])
                bid = row.get('bid_price_1', '')
                ask = row.get('ask_price_1', '')
                mid_str = row.get('mid_price', '')
                # Use bid/ask mid if both present, else mid_price if reasonable
                if bid and ask:
                    mid = (float(bid) + float(ask)) / 2
                elif mid_str and float(mid_str) > 9000:
                    mid = float(mid_str)
                else:
                    continue  # skip ticks with missing/bad data
                timestamps.append(ts)
                mids.append(mid)
    return np.array(timestamps), np.array(mids)


# Load all 3 days
days = {}
DATA = '/opt/anaconda3/lib/python3.12/site-packages/prosperity4bt/resources/round1'
for day_label, day_file in [
    ('Day -2', f'{DATA}/prices_round_1_day_-2.csv'),
    ('Day -1', f'{DATA}/prices_round_1_day_-1.csv'),
    ('Day 0', f'{DATA}/prices_round_1_day_0.csv'),
]:
    ts, mid = load_aco_mids(day_file)
    days[day_label] = (ts, mid)
    print(f"{day_label}: {len(ts)} ticks, price range [{mid.min():.1f}, {mid.max():.1f}], mean={mid.mean():.2f}, std={mid.std():.2f}")

fig, axs = plt.subplots(4, 3, figsize=(24, 20))

for col, (day_label, (ts, mid)) in enumerate(days.items()):
    # Detrend: subtract mean
    detrended = mid - mid.mean()
    returns = np.diff(mid)

    # Tick interval (ms)
    dt = np.median(np.diff(ts))
    n = len(detrended)

    # ── FFT on detrended prices ──
    fft_vals = np.fft.rfft(detrended)
    power = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=dt / 1000)  # in Hz (cycles per second)
    periods = np.where(freqs > 0, 1.0 / freqs, 0)  # in seconds

    # ── FFT on returns ──
    fft_ret = np.fft.rfft(returns)
    power_ret = np.abs(fft_ret) ** 2
    freqs_ret = np.fft.rfftfreq(len(returns), d=dt / 1000)
    periods_ret = np.where(freqs_ret > 0, 1.0 / freqs_ret, 0)

    # Row 0: Raw price + detrended
    ax = axs[0, col]
    ax.plot(ts / 1000, mid, linewidth=0.5, alpha=0.8)
    ax.axhline(y=10000, color='red', linestyle='--', alpha=0.5, label='Fair=10000')
    ax.set_title(f'{day_label} - ACO Price')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Mid Price')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Row 1: FFT Power Spectrum (prices) - log scale, vs period
    ax = axs[1, col]
    mask = (periods > 0.5) & (periods < 500)  # 0.5s to 500s
    ax.semilogy(periods[mask], power[mask], linewidth=0.5, alpha=0.8)
    ax.set_title(f'{day_label} - FFT Power (Prices)')
    ax.set_xlabel('Period (seconds)')
    ax.set_ylabel('Power (log)')
    ax.grid(True, alpha=0.3)

    # Find top peaks
    peak_idx = np.argsort(power[1:])[::-1] + 1  # skip DC
    print(f"\n{day_label} - Top 10 FFT peaks (prices):")
    seen_periods = []
    count = 0
    for idx in peak_idx:
        if idx >= len(periods) or periods[idx] <= 0:
            continue
        p = periods[idx]
        # Skip if too close to an already-seen period
        if any(abs(p - sp) / max(p, sp) < 0.05 for sp in seen_periods):
            continue
        seen_periods.append(p)
        print(f"  Period={p:>8.1f}s ({p/60:>5.1f}min)  Power={power[idx]:>12.0f}  Freq={freqs[idx]:.4f}Hz")
        ax.axvline(x=p, color='red', alpha=0.3, linewidth=1)
        if p < 500:
            ax.annotate(f'{p:.0f}s', xy=(p, power[idx]), fontsize=7, color='red')
        count += 1
        if count >= 10:
            break

    # Row 2: FFT Power Spectrum (returns)
    ax = axs[2, col]
    mask_r = (periods_ret > 0.5) & (periods_ret < 500)
    ax.semilogy(periods_ret[mask_r], power_ret[mask_r], linewidth=0.5, alpha=0.8)
    ax.set_title(f'{day_label} - FFT Power (Returns)')
    ax.set_xlabel('Period (seconds)')
    ax.set_ylabel('Power (log)')
    ax.grid(True, alpha=0.3)

    print(f"\n{day_label} - Top 10 FFT peaks (returns):")
    peak_idx_r = np.argsort(power_ret[1:])[::-1] + 1
    seen_periods = []
    count = 0
    for idx in peak_idx_r:
        if idx >= len(periods_ret) or periods_ret[idx] <= 0:
            continue
        p = periods_ret[idx]
        if any(abs(p - sp) / max(p, sp) < 0.05 for sp in seen_periods):
            continue
        seen_periods.append(p)
        print(f"  Period={p:>8.1f}s ({p/60:>5.1f}min)  Power={power_ret[idx]:>12.0f}  Freq={freqs_ret[idx]:.4f}Hz")
        ax.axvline(x=p, color='red', alpha=0.3, linewidth=1)
        if p < 500:
            ax.annotate(f'{p:.0f}s', xy=(p, power_ret[idx]), fontsize=7, color='red')
        count += 1
        if count >= 10:
            break

    # Row 3: Autocorrelation of prices at longer lags (look for periodicity)
    ax = axs[3, col]
    max_lag = min(5000, n // 2)
    autocorr = np.correlate(detrended[:max_lag*2], detrended[:max_lag*2], mode='full')
    autocorr = autocorr[len(autocorr)//2:]  # positive lags only
    autocorr = autocorr / autocorr[0]  # normalize
    lags_sec = np.arange(len(autocorr)) * dt / 1000
    ax.plot(lags_sec, autocorr, linewidth=0.5)
    ax.set_title(f'{day_label} - Autocorrelation (prices)')
    ax.set_xlabel('Lag (seconds)')
    ax.set_ylabel('Autocorrelation')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linewidth=0.5)

    # Find peaks in autocorrelation (potential periods)
    from scipy.signal import find_peaks
    peaks, props = find_peaks(autocorr[10:], height=0.05, distance=50)
    peaks += 10  # offset
    if len(peaks) > 0:
        peak_lags = peaks * dt / 1000
        print(f"\n{day_label} - Autocorrelation peaks:")
        for pl, pidx in zip(peak_lags[:10], peaks[:10]):
            print(f"  Lag={pl:>7.1f}s ({pl/60:>5.1f}min)  Autocorr={autocorr[pidx]:.4f}")
            ax.axvline(x=pl, color='red', alpha=0.3, linewidth=1)

# Cross-day consistency: average the FFT power across days
print("\n" + "=" * 70)
print("CROSS-DAY ANALYSIS: Looking for consistent periods across all 3 days")
print("=" * 70)

# Bin periods and compare power across days
all_peaks = defaultdict(list)
for day_label, (ts, mid) in days.items():
    detrended = mid - mid.mean()
    dt = np.median(np.diff(ts))
    n = len(detrended)
    fft_vals = np.fft.rfft(detrended)
    power = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=dt / 1000)
    periods = np.where(freqs > 0, 1.0 / freqs, 0)

    # Bin into period buckets
    for idx in range(1, len(periods)):
        p = periods[idx]
        if 1 < p < 500:
            bucket = round(p)
            all_peaks[bucket].append((day_label, power[idx]))

# Find periods with consistently high power across all 3 days
print("\nPeriods with high power in ALL 3 days:")
consistent = []
for bucket, entries in all_peaks.items():
    day_names = set(e[0] for e in entries)
    if len(day_names) == 3:
        avg_power = np.mean([e[1] for e in entries])
        min_power = min(e[1] for e in entries)
        consistent.append((bucket, avg_power, min_power))

consistent.sort(key=lambda x: -x[1])
print(f"{'Period(s)':>10} {'Period(min)':>12} {'Avg Power':>12} {'Min Power':>12}")
for p, avg, mn in consistent[:20]:
    print(f"{p:>10} {p/60:>12.1f} {avg:>12.0f} {mn:>12.0f}")

plt.suptitle("ACO FFT / Spectral Analysis - Seasonal Pattern Search", fontsize=16, fontweight='bold')
plt.tight_layout()
plt.savefig("/Users/rohan/prosperity4/aco_fft_analysis.png", dpi=150)
print("\nPlot saved to aco_fft_analysis.png")
