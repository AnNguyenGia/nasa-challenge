import json
import pytest
from ml.train import train
from ml.promote import promote

def test_quality_gate_promotion_and_tamper(tmp_path,monkeypatch):
    monkeypatch.delenv('MLFLOW_TRACKING_URI',raising=False)
    meta=train(tmp_path)
    assert meta['approved_by_gate']
    promote(tmp_path,meta['version'])
    assert json.loads((tmp_path/'current.json').read_text())['sha256']==meta['sha256']
    (tmp_path/meta['artifact']).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):
        promote(tmp_path,meta['version'])

def test_inference_loads_promoted_model_and_rejects_corruption(tmp_path,monkeypatch):
    from app.core import config
    from app.modules.analytics import assess
    monkeypatch.setattr(config,'MODEL_DIR',tmp_path)
    monkeypatch.delenv('MLFLOW_TRACKING_URI',raising=False)
    sample={'heart_rate':72,'temperature':36.7,'sleep_hours':7.5,'mood':4}
    assert assess(sample)['kind']=='unavailable'
    meta=train(tmp_path)
    promote(tmp_path,meta['version'])
    assert assess(sample)['model_version']==meta['version']
    (tmp_path/meta['artifact']).write_bytes(b'corrupt')
    assert assess(sample)['kind']=='unavailable'
