import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from multiprocessing import TimeoutError
import run_s2_shard as shard
import pandas as pd
from coordinate_s2_split import import_checkpoints


def plan():
    return dict(local={'N1':[380,500], 'N5':[2,500], 'N6':[1,500], 'M1':[1,500]},
                remote={'N1':[0,380]}, preserved={'N5':[0,2], 'N6':[0,1], 'M1':[0,1]},
                local_workers=32, remote_workers=2, local_stop_at='2026-10-19T17:45:00+08:00')


class ShardTests(unittest.TestCase):
    def test_partition_is_complete_disjoint_and_rejects_overlap(self):
        p=plan(); groups=shard.assignments(p)
        self.assertEqual([len(groups[k]) for k in ('local','remote','preserved')], [1616,380,4])
        p['local']['N1']=[379,500]
        with self.assertRaises(AssertionError): shard.assignments(p)

    def test_deadline_terminates_queued_work(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'results/simulation';out.mkdir(parents=True)
            (out/'S1_status.json').write_text('{"status":"complete"}')
            p=plan(); before=datetime.fromisoformat(p['local_stop_at'])-timedelta(seconds=1)
            after=before+timedelta(seconds=2)
            pool=MagicMock();pool.imap_unordered.return_value.next.side_effect=TimeoutError
            with patch.object(shard,'Pool') as factory, patch.object(shard,'datetime') as clock:
                factory.return_value.__enter__.return_value=pool
                clock.fromisoformat.side_effect=datetime.fromisoformat
                clock.now.side_effect=[before,before,before,after,after,after]
                shard.run_shard(root,p,'local')
            pool.terminate.assert_called_once()
            state=json.loads((out/'S2_local_shard_status.json').read_text())
            self.assertEqual(state['status'],'deadline_reached')
            self.assertEqual(state['completed'],0)

    def test_already_expired_never_starts_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);out=root/'results/simulation';out.mkdir(parents=True)
            (out/'S1_status.json').write_text('{"status":"complete"}')
            p=plan();p['local_stop_at']='2000-01-01T00:00:00+00:00'
            with patch.object(shard,'Pool') as pool:
                shard.run_shard(root,p,'local')
            pool.assert_not_called()

    def test_import_preserves_unique_repetitions_and_rejects_wrong_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'incoming';dest=root/'merged'
            (source/'N1').mkdir(parents=True)
            metrics=pd.DataFrame([dict(stage='S2',scenario='N1',repetition=380,
                domain='L2',family=str(i),method=m) for i in range(13) for m in ['BF','Holm','BH']])
            pairs=pd.DataFrame(dict(A=[str(i) for i in range(1740)],B=['B']*1740))
            metrics.to_parquet(source/'N1/0380.parquet',index=False)
            pairs.to_parquet(source/'N1/0380.pairs.parquet',index=False)
            self.assertEqual(import_checkpoints(source,dest,{('N1',380)}),1)
            self.assertEqual(import_checkpoints(source,dest,{('N1',380)}),1)
            pd.testing.assert_frame_equal(metrics,pd.read_parquet(dest/'N1/0380.parquet'))
            with self.assertRaises(AssertionError): import_checkpoints(source,root/'wrong',{('N1',381)})
