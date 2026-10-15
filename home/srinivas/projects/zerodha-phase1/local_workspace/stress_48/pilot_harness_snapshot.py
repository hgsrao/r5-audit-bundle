"""Checkpointed-engine stress instrument; real bars, optional explicitly forced signal demand."""
from pathlib import Path
import argparse, collections, hashlib, json, math, sys, time
ROOT=Path('/home/srinivas/projects/zerodha-phase1')
sys.path.insert(0,str(ROOT))
import pandas as pd
from market_data_loader import MarketDataLoader
from revision2.dataset_manifest import DatasetManifest, verify_manifest
from revision2.contracts import PASignal, IDDecision
from revision2_external.orchestrator import Revision2ExternalEngineOrchestrator as Engine
from revision2_external.grid_context import SealedGridContextProvider
from revision5.ccpp_unified_plant import CentralPlantMasterDCS
from revision5.topology import BAY_IDS, bay_for_symbol
from scripts.run_r5_paper_replay import load_verified_grid_feeds

class StressEngine(Engine):
    def __init__(self,*args,inject=False,**kwargs):
        super().__init__(*args,**kwargs)
        self.inject=inject;self.tick=0;self.fault_bay=None;self.locked=False
        self.audit={'batch_sizes':[],'batch_order_invariance_checks':0,'fault_events':[],
                    'entry_fills_by_bay':collections.Counter(),'locked_exit_fills':0,
                    'lockout_entry_violations':0,'cap_violations':0,'peak_open_positions':0,
                    'peak_gross_fraction':0.0,'max_symbols_per_batch':0,'illegal_reclose_rejections':0,
                    'post_reset_entry_fills':0,'positive_cap_by_bay':collections.Counter(),
                    'locked_cap_rejections':0,'unaffected_bay_positive_caps':0}
        original=self.broker.place_order
        def audited_order(*args,**kwargs):
            symbol=kwargs.get('symbol',args[0] if args else None)
            is_entry=symbol not in self.open_trades
            bay=bay_for_symbol(symbol)
            if is_entry and self.locked and bay==self.fault_bay:
                self.audit['lockout_entry_violations']+=1
                raise AssertionError('An entry reached the broker during ANSI-86 lockout')
            result=original(*args,**kwargs)
            if result.get('passed'):
                if is_entry:
                    self.audit['entry_fills_by_bay'][bay]+=1
                    if self.inject and self.tick>=70 and bay==self.fault_bay:self.audit['post_reset_entry_fills']+=1
                elif self.locked and bay==self.fault_bay:self.audit['locked_exit_fills']+=1
            return result
        self.broker.place_order=audited_order

    def rank_simultaneous_entry_candidates(self,candidates):
        ordered=Engine.rank_simultaneous_entry_candidates(candidates)
        reversed_order=Engine.rank_simultaneous_entry_candidates(list(reversed(candidates)))
        assert [c['candidate_id'] for c in ordered]==[c['candidate_id'] for c in reversed_order]
        self.audit['batch_order_invariance_checks']+=1
        self.audit['batch_sizes'].append(len(candidates))
        self.audit['max_symbols_per_batch']=max(self.audit['max_symbols_per_batch'],len({c['symbol'] for c in candidates}))
        return ordered

    def _plant_control_shadow_step(self,timestamp,max_gross_fraction):
        self.tick+=1
        if self.inject and self.tick==10:
            self.fault_bay=bay_for_symbol(next(iter(self.open_trades),'INFY'))
            others={b:self.real_plant_dcs.electrical_network.unit_available(b) for b in BAY_IDS if b!=self.fault_bay}
            held=[s for s in self.open_trades if bay_for_symbol(s)==self.fault_bay]
            self.real_plant_dcs.trip_unit_breaker(bay_id=self.fault_bay,reason='STRESS_TEST_ANSI86',source='OFFLINE_TEST',lockout=True)
            assert others=={b:self.real_plant_dcs.electrical_network.unit_available(b) for b in others}
            self.locked=True
            self.audit['fault_events'].append({'tick':self.tick,'timestamp':str(timestamp),'action':'ANSI86_TRIP','bay':self.fault_bay,'held_symbols':held})
        if self.inject and self.tick in (10,20,60):
            try:self.real_plant_dcs.electrical_network.close_unit_breaker(self.fault_bay)
            except RuntimeError as e:
                assert 'ANSI-86' in str(e);self.audit['illegal_reclose_rejections']+=1
            else:raise AssertionError('Ordinary close bypassed ANSI-86 lockout')
        if self.inject and self.tick==70:
            self.real_plant_dcs.reset_unit_breaker(bay_id=self.fault_bay)
            self.locked=False
            self.audit['fault_events'].append({'tick':self.tick,'timestamp':str(timestamp),'action':'EXPLICIT_TEST_OPERATOR_RESET','bay':self.fault_bay})
        super()._plant_control_shadow_step(timestamp,max_gross_fraction)
        if self.locked:
            assert self.real_plant_dcs.electrical_network.unit_breaker(self.fault_bay).lockout_86
            assert dict(self._paper_plant_snapshot.dispatch.references_pu)[self.fault_bay]==0
        self.audit['peak_open_positions']=max(self.audit['peak_open_positions'],len(self.open_trades))
        self.audit['peak_gross_fraction']=max(self.audit['peak_gross_fraction'],self._gross_exposure_notional()/max(self._equity(),1))
        if self.tick%100==0:print(json.dumps({'progress_tick':self.tick,'fills':sum(self.audit['entry_fills_by_bay'].values()),'max_batch':self.audit['max_symbols_per_batch']}),flush=True)

    def _paper_plant_entry_limit(self,symbol,quantity,price,timestamp):
        allowed=super()._paper_plant_entry_limit(symbol,quantity,price,timestamp)
        bay=bay_for_symbol(symbol)
        if self.locked and bay==self.fault_bay:
            assert allowed==0;self.audit['locked_cap_rejections']+=1
        if allowed>0:
            self.audit['positive_cap_by_bay'][bay]+=1
            if self.locked and bay!=self.fault_bay:self.audit['unaffected_bay_positive_caps']+=1
            snap=self._paper_plant_snapshot;ref=next(x for x in snap.governor_references if x.bay_id==bay)
            budget=self._equity()*float(self.safety_contract.values['max_gross_exposure_fraction'])
            held=sum(t['quantity']*self._last_close.get(s,t['entry_price']) for s,t in self.open_trades.items() if bay_for_symbol(s)==bay)
            assert allowed<=quantity
            if (held+allowed*price>budget*ref.dispatch_reference_pu+1e-6 or
                    self._gross_exposure_notional()+allowed*price>budget*ref.plant_demand_reference_pu+1e-6):
                self.audit['cap_violations']+=1;raise AssertionError('Admission exceeded paper cap')
        return allowed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scenario',choices=['pilot','natural','storm'],required=True);parser.add_argument('--bars',type=int,required=True);a=parser.parse_args()
    out=ROOT/'local_workspace/stress_48'/a.scenario;out.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();manifest=DatasetManifest.load(str(ROOT/'revision2/DATASET_MANIFEST_48SYMBOL_1MIN.json'))
    verified=verify_manifest(manifest);assert verified.valid,verified.message
    feeds=load_verified_grid_feeds(ROOT/'local_workspace/records/grid-manifest-local.json');provider=SealedGridContextProvider(feeds['NIFTY_50_15MIN'],feeds['INDIA_VIX_15MIN']);end=min(f['timestamp'].max() for f in feeds.values()).tz_convert('Asia/Kolkata').date()
    data={};loader=MarketDataLoader(manifest.data_dir,synthetic_if_missing=False)
    for f in manifest.files:
        frame=loader._load_symbol_csv(f.symbol);dates=pd.to_datetime(frame['timestamp'],utc=True).dt.tz_convert('Asia/Kolkata').dt.date
        frame=frame[dates==end].head(a.bars) if a.scenario=='storm' else frame[dates<=end].tail(a.bars)
        assert len(frame)>60,(f.symbol,len(frame));data[f.symbol]=frame.reset_index(drop=True)
    assert len(data)==48
    loaded=time.perf_counter();engine=StressEngine(list(data),grid_context_provider=provider,
        real_plant_dcs=CentralPlantMasterDCS(total_capital=1000000,db_path=':memory:'),
        plant_control_mode='PAPER_APPLY',closed_loop_mode='active_paper',telemetry_mode='compact',inject=a.scenario=='storm')
    if a.scenario=='storm':
        # Explicit fault/load fixture: force upstream demand; preserve real prices, MPC, sizing,
        # admission, safety, fills, protection, and reconciliation. Not an alpha backtest.
        def forced_signal(snapshot,cfg):
            return PASignal(symbol=snapshot.symbol,timestamp=snapshot.timestamp,direction=1,
                confidence=.95,momentum=.5,volatility=.01,vwap_deviation=.1,volume_confirmation=.2,exit_confidence=.1),[]
        engine.pa.evaluate=forced_signal
        engine.id_box.evaluate=lambda *args,**kw:(IDDecision(True,'FORCED_STRESS_DEMAND',.95,2,.6),[])
        engine.id_box._current_regime=lambda *args,**kw:'calm'
        engine.chart_studies.evaluate=lambda *args,**kw:{'direction':1,'confidence':.95}
    report=engine.run(data,warmup=60);done=time.perf_counter();ledger=engine.entry_candidate_observations.report()
    audit=engine.audit;sizes=audit.pop('batch_sizes');audit.update({'max_batch':max(sizes,default=0),'batches_with_2plus':sum(x>=2 for x in sizes),'total_batch_candidates':sum(sizes),'timestamp_batches':len(sizes),
        'candidate_dispositions':ledger['dispositions'],'candidate_reasons':dict(collections.Counter(x['execution_reason'] for x in ledger['rows'])),
        'queue_semantics':'timestamp-local batch; no persistent backlog or automatic retry',
        'pending_after_run':sum(x['execution_disposition']=='PENDING' for x in ledger['rows']),
        'unclassified_after_run':sum(x['execution_disposition']=='NOT_FILLED_UNCLASSIFIED' for x in ledger['rows'])})
    assert audit['pending_after_run']==0
    assert report['safety_violations']==0
    if a.scenario=='storm':
        assert audit['max_symbols_per_batch']==48,audit['max_symbols_per_batch']
        assert audit['illegal_reclose_rejections']==3
        assert audit['locked_cap_rejections']>0
        assert audit['unaffected_bay_positive_caps']>0
    result={'scenario':a.scenario,'symbols':len(data),'bars_per_symbol':{s:len(f) for s,f in data.items()},'latest_common_date':str(end),
        'load_seconds':loaded-start,'replay_seconds':done-loaded,'total_seconds':done-start,
        'replay_events':sum(max(0,len(f)-61) for f in data.values()),'data_manifest_hash':manifest.manifest_hash,
        'forced_signals':a.scenario=='storm','operating_mode':'PAPER_APPLY','audit':audit,
        'result':{k:report[k] for k in ['fills','completed_trades','net_pnl','safety_violations','plant_control','execution_halted']}}
    (out/'report.json').write_text(json.dumps(report,indent=2,default=str));(out/'summary.json').write_text(json.dumps(result,indent=2,default=str));print(json.dumps(result,indent=2,default=str),flush=True)

if __name__=='__main__':main()
