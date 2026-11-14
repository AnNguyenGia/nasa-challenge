# Health Signal Agent

`HealthSignalAgent` orchestrates existing ECG inference and descriptive RR/HRV summaries. Lung ultrasound is reported as unavailable unless a real labeled image dataset and separately validated lung model are supplied.

Example:
```python
from src.agents import HealthSignalAgent
agent = HealthSignalAgent("models/ECG/best_model.pth")
result = agent.assess(rr_intervals_ms=[800, 790, 810], respiratory_metrics={"MeanHR": 75, "SDNN": 45})
print(result)
```

ECG inference expects one preprocessed beat of exactly 187 samples using the same scaling as training. This is a research prototype, not a clinical device.
