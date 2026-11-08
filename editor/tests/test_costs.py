import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'engine'))
import costs

class CostLog(unittest.TestCase):
    def test_only_operations_of_five_seconds_or_more_are_logged(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(costs,'LOG',Path(folder)/'costes.jsonl'),\
             patch.object(costs.time,'monotonic',side_effect=[0,4,10,16]):
            with costs.measured('frame','/x/Proyecto A'):pass
            with costs.measured('render','/x/Proyecto A'):pass
            entries=[json.loads(line) for line in costs.LOG.read_text().splitlines()]
        self.assertEqual([(e['operation'],e['project'],e['seconds']) for e in entries],[('render','Proyecto A',6)])
    def test_nested_operation_counts_inside_the_outer_one(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(costs,'LOG',Path(folder)/'costes.jsonl'),\
             patch.object(costs.time,'monotonic',side_effect=[0,6]):
            with costs.measured('render','/x/Mid 07/Proyecto.studio'):
                with costs.measured('interna') as entry:entry['detail']='preview-gpu'
            entries=[json.loads(line) for line in costs.LOG.read_text().splitlines()]
        self.assertEqual([(e['operation'],e['detail'],e['project']) for e in entries],[('render','preview-gpu','Mid 07')])
    def test_energy_is_mean_power_between_publications_times_duration(self):
        readings=iter(['"SystemLoad"=9000,"AccumulatedSystemLoad"=1000000,"SystemLoadAccumulatorCount"=100','"SystemLoad"=12000,"AccumulatedSystemLoad"=1500000,"SystemLoadAccumulatorCount"=150'])
        class Reader:
            def communicate(self,timeout=None):return next(readings),None
        with tempfile.TemporaryDirectory() as folder,patch.object(costs,'LOG',Path(folder)/'costes.jsonl'),\
             patch.object(costs,'energy_reader',Reader),patch.object(costs.time,'monotonic',side_effect=[0,60]):
            with costs.measured('render'):pass
            self.assertEqual(json.loads(costs.LOG.read_text())['joules'],600)   # 10 W × 60 s
    def test_without_a_new_publication_the_last_load_is_used(self):
        reading='"SystemLoad"=12000,"AccumulatedSystemLoad"=1000000,"SystemLoadAccumulatorCount"=100'
        class Reader:
            def communicate(self,timeout=None):return reading,None
        with tempfile.TemporaryDirectory() as folder,patch.object(costs,'LOG',Path(folder)/'costes.jsonl'),\
             patch.object(costs,'energy_reader',Reader),patch.object(costs.time,'monotonic',side_effect=[0,6]):
            with costs.measured('render'):pass
            self.assertEqual(json.loads(costs.LOG.read_text())['joules'],72)   # 12 W × 6 s
    def test_missing_meter_never_fails_the_log(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(costs,'LOG',Path(folder)/'costes.jsonl'),\
             patch.object(costs,'ENERGY',[str(Path(folder)/'no-existe')]),patch.object(costs.time,'monotonic',side_effect=[0,6]):
            with costs.measured('render'):pass
            self.assertNotIn('joules',json.loads(costs.LOG.read_text()))
    def test_real_telemetry_is_readable(self):
        self.assertEqual(len(costs.energy_read(costs.energy_reader()) or ()),3)

if __name__=='__main__':unittest.main()
