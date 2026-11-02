"""python -m InspectionOS: standalone mock-only end-to-end demonstration."""
import argparse
import json
import logging
from pathlib import Path
import uuid
from .app import Application
from .brain_adapter import BrainAdapter
from brain_v3.config import ProviderConfig
from data_pipeline.buffer import Buffer
from data_pipeline.collector import Collector
from data_pipeline.batch_writer import BatchWriter
from data_pipeline.sync_manager import SyncManager, MockRemote
from data_pipeline.retention import Retention
from observability.metrics import snapshot
import time


def main():
    parser=argparse.ArgumentParser(description='Mock-only task runtime; no robot control')
    parser.add_argument('--db',type=Path,default=Path('runtime/inspection-os.db'))
    parser.add_argument('--text',default='查询3号断路器的上周告警。')
    parser.add_argument('--provider',choices=('rules','mock','ollama'),default='rules')
    parser.add_argument('--idempotency-key')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--recover',action='store_true')
    args=parser.parse_args()
    retention=Retention(args.db.parent)
    handler=retention.log_handler()
    logger=logging.getLogger('InspectionOS');logger.addHandler(handler);logger.setLevel(logging.INFO)
    started=time.perf_counter()
    try:
        with Application(args.db) as app:
            app.network.online=not args.offline
            if args.recover:app.recovery.recover()
            config=ProviderConfig.from_environment() if args.provider=='ollama' else ProviderConfig(provider=args.provider)
            if args.provider=='ollama' and (config.provider!='ollama' or not config.enabled):
                parser.error('Ollama requires explicit BRAIN_V3_PROVIDER=ollama and BRAIN_V3_ENABLE_LLM=true')
            adapter=BrainAdapter(app.manager,config=config)
            mission=adapter.submit_text(args.text,idempotency_key=args.idempotency_key or uuid.uuid4().hex,
                                        mode='v2_rules' if args.provider=='rules' else 'v3_llm')
            app.worker.run_until_settled()
            buf=Buffer();collector=Collector(buf)
            collector.collect('transcript',{'text':args.text,'input_source':'manual'},trace_id=mission['trace_id'],source='manual')
            collector.ingest_mission(app.manager,mission['mission_id'])
            for span in adapter.recorder.records:
                collector.collect('task_log',span,trace_id=mission['trace_id'],source='observability')
            BatchWriter(app.db,buf).flush()
            remote=MockRemote(str(args.db)+'.remote.db')
            try:sync=SyncManager(app.db,app.network,remote).sync()
            finally:remote.close()
            result=app.manager.get(mission['mission_id'])
            print(json.dumps({'mission':result,'sync':sync,'metrics':snapshot(app,time.perf_counter()-started),
                              'spans':adapter.recorder.records,'hardware_commands_enabled':False},ensure_ascii=False,indent=2))
            return 0 if result['status']=='SUCCEEDED' else 1
    finally:
        logger.removeHandler(handler);handler.close()


if __name__=='__main__':raise SystemExit(main())
