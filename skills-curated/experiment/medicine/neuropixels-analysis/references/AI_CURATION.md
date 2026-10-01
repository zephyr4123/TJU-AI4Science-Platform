# AI-Assisted Curation Reference

Use visual review of spike-sorting plots for borderline units, complementing
quantitative quality metrics.

```
Traditional:  Metrics → Threshold → Labels
AI-Enhanced:  Metrics → Render plots → Visual review → Confidence → Labels
```

## Agent integration

When you run this skill inside an agent, the agent can inspect images directly.
Generate a unit summary figure and assess it:

```python
import spikeinterface.widgets as sw
import matplotlib.pyplot as plt

sw.plot_unit_summary(analyzer, unit_id=0)
plt.savefig("unit_0_summary.png", dpi=150, bbox_inches="tight")
# Then assess: "Is unit 0 a well-isolated single unit, MUA, or noise? Consider
# waveform consistency, the refractory gap in the autocorrelogram, and amplitude stability."
```

The agent can assess waveform shape/consistency, refractory-period violations, amplitude
stability over time, and overall isolation quality.

## Only review uncertain units

```python
uncertain = metrics.query(
    "snr > 2 and snr < 8 and isi_violations_ratio > 0.001 and isi_violations_ratio < 0.1"
).index.tolist()
```

Label clear cases from metrics (e.g. `snr > 10` and `isi_violations_ratio < 0.001` → good,
`snr < 1.5` → noise) and render summary figures only for the units in between.

## What each panel tells you

| Panel | Content | What to look for |
|-------|---------|------------------|
| Waveforms | Individual spike waveforms | Consistency, shape |
| Template | Mean ± std | Clean negative peak, physiological shape |
| Autocorrelogram | Spike timing | Gap at 0 ms (refractory period) |
| Amplitudes | Amplitude over time | Stability, no drift |
| ISI histogram | Inter-spike intervals | Refractory gap < ~1.5 ms |

## Best Practices

1. **Review uncertain cases only** — don't spend effort on obvious good/noise units.
2. **Combine with metrics and model-based curation** — visual review supplements, not
   replaces, quantitative measures (see [AUTOMATED_CURATION.md](AUTOMATED_CURATION.md)).
3. **Keep a human in the loop** for important analyses.
4. **Record reasoning** for each decision for reproducibility.

## References

- [SpikeInterface model-based curation](https://spikeinterface.readthedocs.io/en/stable/tutorials/curation/plot_1_automated_curation.html)
- [SpikeAgent](https://github.com/SpikeAgent/SpikeAgent) — AI-powered spike-sorting assistant
