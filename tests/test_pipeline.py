import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from InspectionOS.app import Application
from InspectionOS.simulation.fault_injector import storage_failure,restore_storage
from InspectionOS.storage.database import CapacityError
from data_pipeline.buffer import Buffer,BackpressureError
from data_pipeline.collector import Collector
from data_pipeline.batch_writer import BatchWriter,compare_writes
from data_pipeline.integrity import verify
from data_pipeline.retention import Retention,storage_status
from data_pipeline.sync_manager import SyncManager,MockRemote


class PipelineTests(unittest.TestCase):
    def test_bounded_buffer_no_silent_drop_and_atomic_retry(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            buf=Buffer(1);collector=Collector(buf);writer=BatchWriter(app.db,buf)
            collector.collect('transcript',{'text':'test'},trace_id='t',source='manual')
            with self.assertRaises(BackpressureError):collector.collect('transcript',{},trace_id='t',source='manual')
            storage_failure(app.db)
            with self.assertRaises(sqlite3.OperationalError):writer.flush()
            self.assertEqual(len(buf),1);self.assertEqual(app.db.rows('SELECT * FROM evidence'),[])
            restore_storage(app.db);self.assertEqual(writer.flush(),1);self.assertEqual(len(buf),0)
            row=app.db.rows('SELECT * FROM evidence')[0]
            self.assertTrue(verify(json.loads(row['payload']),row['sha256']))
            self.assertFalse(verify({'text':'tampered'},row['sha256']))
            writer.export_jsonl(Path(d)/'evidence.jsonl')
            with self.assertRaises(FileExistsError):writer.export_jsonl(Path(d)/'evidence.jsonl')

    def test_capacity_retains_buffer_and_audit(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            buf=Buffer();c=Collector(buf);w=BatchWriter(app.db,buf)
            c.collect('task_log',{},trace_id='t',source='test')
            app.db.max_bytes=1
            with self.assertRaises(CapacityError):w.flush()
            self.assertEqual(len(buf),1);self.assertTrue(storage_status(app.db)['warning'])

    def test_retention_only_explicit_non_audit_files(self):
        with tempfile.TemporaryDirectory() as d:
            r=Retention(d)
            audit=Path(d)/'audit.jsonl';audit.write_text('protected')
            cache=r.temporary/'old.tmp';cache.write_text('cache')
            misleading=r.temporary/'audit.jsonl';misleading.write_text('keep')
            outside=Path(d)/'outside.tmp';outside.write_text('keep')
            (r.temporary/'link.tmp').symlink_to(outside)
            deleted=r.clean(max_cache_bytes=0)
            self.assertIn(str(cache),deleted);self.assertTrue(audit.exists());self.assertTrue(misleading.exists());self.assertTrue(outside.exists())
            handler=r.log_handler(max_bytes=30,backups=1)
            import logging
            log=logging.getLogger('retention-test');log.addHandler(handler);log.setLevel(logging.INFO)
            for i in range(5):log.info('diagnostic %s',i)
            log.removeHandler(handler);handler.close()
            self.assertTrue((r.diagnostic/'runtime.log.1').exists())

    def test_collect_task_trace_and_delayed_sync(self):
        with tempfile.TemporaryDirectory() as d,Application(Path(d)/'db') as app:
            m=app.manager.create('mock.reinspection',{'device_id':'MOCK-CB-3'},idempotency_key='x')
            app.worker.drain();buf=Buffer();c=Collector(buf);c.ingest_mission(app.manager,m['mission_id'])
            BatchWriter(app.db,buf).flush()
            self.assertTrue(app.db.rows('SELECT * FROM evidence'))
            with self.assertRaises(ValueError):c.collect('mock_alarm',{'is_mock':False},trace_id='x',source='fake')
            remote=MockRemote(str(Path(d)/'remote'))
            try:
                app.network.online=False;s=SyncManager(app.db,app.network,remote);self.assertGreater(s.sync()['failed'],0)
                app.network.online=True;self.assertEqual(s.sync()['pending'],0)
            finally:remote.close()

    def test_single_batch_measurements_have_actual_records(self):
        with tempfile.TemporaryDirectory() as d:
            rows=compare_writes(d,10)
            self.assertEqual(len(rows),3)
            for r in rows:self.assertGreater(r['seconds'],0);self.assertEqual(r['records'],10)
